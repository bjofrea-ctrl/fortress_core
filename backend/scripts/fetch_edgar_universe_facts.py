"""
Fase 0 de A5 (§47) — fetch de company facts XBRL de SEC EDGAR para el universo 50.

Descarga data.sec.gov/api/xbrl/companyfacts/<CIK>.json para las EMPRESAS OPERATIVAS
del universo canónico (los 48 que no son ETF; SPY/QQQ se excluyen — los ETF no
tienen fundamentales en ninguna fuente). Los guarda en data/cache/edgar/ con el
mismo nombre que espera build_fundamentals_panel.py ({SYMBOL}_companyfacts.json).

Point-in-time: cada fact trae su fecha de filing real (la empresa PUBLICÓ el dato)
— no hay lookahead. "As originally reported": companyfacts conserva el valor del
filing original.

NO consume presupuesto del ledger (es acumulación de datos, no un trial).

Throttling SEC: la API acepta <=10 req/s y responde 429/503 si te pasas en una
ventana deslizante corta (el universo son ~48 requests al hilo; caso ACN en el
commit 9062307: cayo por throttling y NO se re-intento). Ahora cada fetch()
reintenta con backoff exponencial + jitter hasta SEC_MAX_RETRIES, respetando
Retry-After, y escribe con rename atomico (nunca queda un parcial). Re-correr
este script es barato: el skip por tamano (>1KB) hace que SOLO se re-baje lo que
falta. Pace entre OK = SEC_PACE_SECONDS (default 0.2s). Ajustes por env:
SEC_PACE_SECONDS / SEC_MAX_RETRIES / SEC_BASE_BACKOFF / SEC_MAX_BACKOFF /
SEC_EDGAR_CACHE_DIR (para verificar un burst sin pisar el cache real).

Limite conocido (no un bug): XOM (Exxon Mobil) solo expone 10-Q en companyfacts,
sin serie anual 10-K; por eso build_fmp_shaped_payload() le devuelve None y NO
entra al panel EDGAR (47/48 empresas operativas cubiertas; ver LIMITACION 10-K en
app/core/edgar_fundamentals.py). Se cubre con FMP como fallback.

Uso: python scripts/fetch_edgar_universe_facts.py
"""
import gzip
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Universo canónico; excluimos ETFs (sin fundamentales).
try:
    from app.api.routes.opportunities_universe import SYMBOLS  # type: ignore
except Exception:  # pragma: no cover
    SYMBOLS = []

ETF_EXCLUDE = {"SPY", "QQQ"}

CACHE_DIR = Path(os.environ.get("SEC_EDGAR_CACHE_DIR")
                 or (Path(__file__).resolve().parent.parent / "data" / "cache" / "edgar"))
TICKERS_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
USER_AGENT = "Fortress Core research contact@fortresscore.local"

# --- Throttling SEC (<=10 req/s; responde 429/503 si te pasas) ---------------
# El fetch del universo hace ~48 requests al hilo: en una ventana deslizante
# corta SEC estrangula y tiraba HTTPError 429/503 que el loop anterior tragaba
# como `fail` SIN reintentar (caso ACN en el commit 9062307). Se añade backoff
# exponencial con jitter y respeto de Retry-After. Ajustables por env para poder
# verificar un burst completo sin pisar el cache real.
SEC_MIN_INTERVAL = float(os.environ.get("SEC_PACE_SECONDS", "0.2"))   # pace entre OK
SEC_MAX_RETRIES = int(os.environ.get("SEC_MAX_RETRIES", "6"))         # reintentos / ticker
SEC_BASE_BACKOFF = float(os.environ.get("SEC_BASE_BACKOFF", "1.0"))   # s; x2 por intento
SEC_MAX_BACKOFF = float(os.environ.get("SEC_MAX_BACKOFF", "30.0"))    # tope por espera

# Codigos que valen reintento con backoff (transitorios de throttling/red).
RETRY_STATUSES = {429, 500, 502, 503, 504}


def _decode_json(raw: bytes):
    """Decodifica el body de SEC: puede venir gzip (magic 0x1f 0x8b) o plano.

    urllib NO descomprime automaticamente pese a pedir Accept-Encoding: gzip;
    el fallback viejo (catch UnicodeDecodeError) era fragil porque json.loads
    sobre bytes gzip lanza a veces JSONDecodeError, no UnicodeDecodeError.
    Detectamos el magic header y descomprimemos si corresponde.
    """
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8", "replace"))


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def load_cik_map() -> dict:
    # Un solo request, pero con reintentos: si SEC throttlea el mapa, morir aca
    # dejaria el universo entero sin bajar (peor que fallar un ticker suelto).
    for attempt in range(SEC_MAX_RETRIES + 1):
        try:
            data = _decode_json(_http_get(TICKERS_MAP_URL))
            break
        except Exception as exc:  # noqa: BLE001
            if attempt < SEC_MAX_RETRIES:
                time.sleep(_backoff_seconds(attempt))
                continue
            raise exc
    # data: { "0": {"cik_str": "...", "ticker": "...", ...}, ... }
    out = {}
    for v in data.values():
        t = (v.get("ticker") or "").upper()
        if t:
            out[t] = str(v["cik_str"]).zfill(10)
    return out


def fetch(cik: str, out_path: Path) -> bool:
    """Descarga companyfacts con reintentos + backoff exponencial ante throttling.

    SEC responde 429/503 cuando el burst supera su ventana deslizante (caso ACN).
    Estrategia: hasta SEC_MAX_RETRIES intentos; en cada 429/503/timeout se espera
    base * 2^n con jitter (o Retry-After si lo trae) y reintenta. Escribe a un
    archivo temporal y hace rename atomico: nunca queda un companyfacts truncado
    que el skip por tamano (>100KB) tomaria como valido.
    """
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    last_err = None
    for attempt in range(SEC_MAX_RETRIES + 1):
        try:
            data = _decode_json(_http_get(url))
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in RETRY_STATUSES and attempt < SEC_MAX_RETRIES:
                time.sleep(_backoff_seconds(attempt, exc.headers.get("Retry-After")))
                continue
            print(f"  CIK {cik}: HTTP {exc.code} (no reintentable o agotados), fallando")
            return False
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            if attempt < SEC_MAX_RETRIES:
                time.sleep(_backoff_seconds(attempt))
                continue
            print(f"  CIK {cik}: error de red {exc!r} tras {attempt + 1} intentos")
            return False
        except Exception as exc:  # noqa: BLE001 - JSON corrupto/inesperado: reintentar
            last_err = exc
            if attempt < SEC_MAX_RETRIES:
                time.sleep(_backoff_seconds(attempt))
                continue
            print(f"  CIK {cik}: fallo inesperado {exc!r}")
            return False
        else:
            with open(tmp, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, out_path)  # atomico: o queda completo o queda el previo
            return True
    _ = last_err
    return False


def _backoff_seconds(attempt: int, retry_after=None) -> float:
    """Espera exponencial con jitter; respeta Retry-After numerico de SEC."""
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0) + random.uniform(0, 0.5), SEC_MAX_BACKOFF)
        except (TypeError, ValueError):
            pass
    delay = min(SEC_BASE_BACKOFF * (2 ** attempt), SEC_MAX_BACKOFF)
    return delay * random.uniform(0.75, 1.25)  # jitter: desacopla reintentos sincronizados


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cik_map = load_cik_map()
    print(f"CIK map cargado: {len(cik_map)} tickers")

    operating = [s for s in SYMBOLS if s not in ETF_EXCLUDE]
    print(f"Universo operativo (sin ETF): {len(operating)} símbolos")

    ok, skip, fail = 0, 0, 0
    for symbol in operating:
        out = CACHE_DIR / f"{symbol}_companyfacts.json"
        # Skip solo si ya existe un companyfacts COMPLETO. Con el rename atomico
        # de fetch() un archivo presente es valido; el piso de 1KB descarta
        # parciales/0-byte dejados por el codigo viejo no-atomico (y no re-baja
        # XOM, legitimo pero pequeno ~10KB, en cada corrida).
        if out.exists() and out.stat().st_size > 1_024:
            skip += 1
            continue
        cik = cik_map.get(symbol)
        if not cik:
            print(f"{symbol}: NO encontrado en mapa SEC, skip")
            fail += 1
            continue
        if fetch(cik, out):
            ok += 1
            print(f"{symbol}: descargado CIK {cik} ({out.stat().st_size // 1024} KB)")
        else:
            fail += 1
        time.sleep(SEC_MIN_INTERVAL)  # pace entre OK; el backoff de reintentos lo pone fetch()
    print(f"Listo. ok={ok} skip_cache={skip} fail={fail} -> total={ok + skip}/{len(operating)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
