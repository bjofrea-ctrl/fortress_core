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

Uso: python scripts/fetch_edgar_universe_facts.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

# Universo canónico; excluimos ETFs (sin fundamentales).
try:
    from app.api.routes.opportunities_universe import SYMBOLS  # type: ignore
except Exception:  # pragma: no cover
    SYMBOLS = []

ETF_EXCLUDE = {"SPY", "QQQ"}

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "edgar"
TICKERS_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
USER_AGENT = "Fortress Core research contact@fortresscore.local"


def load_cik_map() -> dict:
    req = urllib.request.Request(
        TICKERS_MAP_URL, headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    # data: { "0": {"cik_str": "...", "ticker": "...", ...}, ... }
    out = {}
    for v in data.values():
        t = (v.get("ticker") or "").upper()
        if t:
            out[t] = str(v["cik_str"]).zfill(10)
    return out


def fetch(cik: str, out_path: Path) -> bool:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    try:
        data = json.loads(raw)
    except UnicodeDecodeError:
        import gzip

        data = json.loads(gzip.decompress(raw))
    with open(out_path, "w") as fh:
        json.dump(data, fh)
    return True


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cik_map = load_cik_map()
    print(f"CIK map cargado: {len(cik_map)} tickers")

    operating = [s for s in SYMBOLS if s not in ETF_EXCLUDE]
    print(f"Universo operativo (sin ETF): {len(operating)} símbolos")

    ok, skip, fail = 0, 0, 0
    for symbol in operating:
        out = CACHE_DIR / f"{symbol}_companyfacts.json"
        if out.exists() and out.stat().st_size > 100_000:
            skip += 1
            continue
        cik = cik_map.get(symbol)
        if not cik:
            print(f"{symbol}: NO encontrado en mapa SEC, skip")
            fail += 1
            continue
        try:
            fetch(cik, out)
            ok += 1
            print(f"{symbol}: descargado CIK {cik} ({out.stat().st_size // 1024} KB)")
        except Exception as exc:  # noqa: BLE001
            print(f"{symbol}: ERROR {exc}")
            fail += 1
        time.sleep(0.2)
    print(f"Listo. ok={ok} skip_cache={skip} fail={fail} -> total={ok + skip}/{len(operating)}")


if __name__ == "__main__":
    sys.exit(main())
