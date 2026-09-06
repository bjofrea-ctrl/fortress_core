"""Colector de superficie IV diaria (B2 — PLAN_REMEDIO_BRECHAS_20260903).

I3-equivalente: acumulación de datos, CERO hipótesis. Sin superficie de IV
acumulada NO EXISTE la familia opciones (VRP, GEX, PEAD-vía-options) — con
ella acumulando desde hoy, el primer trial post-gate tiene historial propio
en vez de empezar de cero. El caño antes de que pase el agua.

Snapshot POST-CIERRE (22:35, tras fundamentals_screen) de las cadenas de
opciones yfinance por símbolo: strikes, expiry, last, IV, OI, volume, spot
→ un parquet DIARIO en data/cache/iv_surface/iv_snapshot_<YYYYMMDD>.parquet
(con columna symbol — un archivo por día, append solo si el día está
incompleto; un día ya completo no se re-escribe: snapshot = inmutable).

Los 30 símbolos de B1/B2 ("SPY, QQQ + 28 de mayor liquidez del universo
102") derivados por dollar-volume medio de las últimas 63 ruedas del cache
local (criterio medible y determinista, verificado 2026-09-03; lista fija en
IV_SYMBOLS — el colector NO re-deriva por corrida para que la serie sea
estable; re-derivación solo manual y documentada).

Datos del snapshot (una fila por contrato):
    symbol, option_type (call/put), expiry, dte, strike, last, bid, ask,
    implied_volatility, open_interest, volume, in_the_money, spot,
    snapshot_date
spot = último close del cache diario local (misma fuente que el motor —
NO fast_info de yfinance, que devolvió None en el probe 2026-09-03 y
agregaría una segunda fuente de precio).

Fallos por símbolo NO cortan la corrida (patrón collect_intraday_1min);
el resumen del log reporta n_ok/n_fail. yfinance rate-limita: pausa
asignable (--sleep-s) y reintentos cortos por expiry. Un día parcialmente
colectado queda marcado en el propio parquet (columnas de los símbolos
fallidos ausentes) y el run del día siguiente arranca de cero (snapshot
diario nuevo, no append de parciales: los parciales NO se mezclan con
días completos).

Uso:
  PYTHONPATH=backend .venv/bin/python -m scripts.collect_iv_surface
  # subset/manual: --symbols SPY,QQQ --max-expiries 6 --sleep-s 1.5

Cron:
  launchd 22:35 diario (scripts/com.fortresscore.ivcollector.plist).
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

# Permite `python -m scripts.collect_iv_surface` y `python scripts/...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 30 símbolos B2 = la MISMA lista staged de B1 (collect_intraday_1min.
# STAGED_SYMBOLS: SPY, QQQ + 28 de mayor liquidez medida del universo 102,
# ranking por dollar-volume del tramo 2026, 2026-09-04). UNA sola fuente
# canónica — bug de auditoría 2026-09-05: IV_SYMBOLS era una lista paralela
# propia (derivada 2026-09-03 con ventana de 63 ruedas) que se desincronizó
# de B1: 26/30 comunes, y MRVL/AMAT/LRCX/PANW fallaban "sin spot" en
# cualquier cache que descargue por opportunities_universe (no están en el
# universo 50). Patrón de bug conocido del proyecto (listas duplicadas que
# divergen) — jamás una tercera lista: importar la de B1.
# Fallback defensivo: si B1 no existe (worktree viejo sin collect_intraday),
# se usa opportunities_universe.SYMBOLS + warning — el colector sigue vivo
# con el universo disponible, pero la serie IV queda documentada como
# divergente de B1 hasta correr sobre un repo con B1.
try:
    from scripts.collect_intraday_1min import STAGED_SYMBOLS as IV_SYMBOLS
except ImportError:  # worktree sin B1 — fallback explícito, no silencioso
    import warnings as _w

    from app.api.routes.opportunities_universe import SYMBOLS as IV_SYMBOLS
    _w.warn(
        "collect_intraday_1min.STAGED_SYMBOLS (B1) no disponible — IV_SYMBOLS "
        "cae a opportunities_universe.SYMBOLS: la serie IV diverge de B1 "
        "hasta correr sobre un repo con B1.", stacklevel=2)
DEFAULT_MAX_EXPIRIES = 12   # expiries por símbolo (los cercanos, ~trimestre)
DEFAULT_SLEEP_S = 1.0       # pausa entre expiries (rate-limit yfinance)
DAILY_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def snapshot_path(day: datetime) -> Path:
    d = DAILY_CACHE_DIR / "iv_surface"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"iv_snapshot_{day.strftime('%Y%m%d')}.parquet"


def _spot_from_local_cache(symbol: str) -> Optional[float]:
    """Último close del cache diario local (misma fuente que el motor).

    Columnas case-insensitive: el saneo A0 re-descargó los parquets con
    lowercase (yfinance 1.2.0), los viejos eran TitleCase.
    """
    p = DAILY_CACHE_DIR / f"{symbol}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        cols = {str(c).lower(): c for c in df.columns}
        if "close" not in cols or len(df) == 0:
            return None
        return float(df[cols["close"]].iloc[-1])
    except Exception:  # noqa: BLE001 — sin spot la fila no es interpretable
        return None


def collect_symbol(symbol: str, spot: Optional[float], max_expiries: int,
                   sleep_s: float,
                   today: Optional[datetime] = None) -> pd.DataFrame:
    """Snapshot de TODAS las cadenas (calls+puts) de un símbolo.

    Un fallo de red levanta y el caller marca el símbolo como fallido —
    prefiero día parcial visible a día silenciosamente vacío.

    ``today`` (default: reloj real) es inyectable para tests: el dte y el
    snapshot_date quedan deterministas contra fechas fijas del fixture, sin
    depender de cuándo corre la suite (bug de auditoría 2026-09-05: expiries
    hardcodeadas del fixture pasaban a pasado y el dte daba negativo).
    """
    import yfinance as yf

    now = today or datetime.now()
    t = yf.Ticker(symbol)
    expiries: List[str] = list(t.options)
    if not expiries:
        raise RuntimeError("sin expiries disponibles")
    expiries = expiries[:max_expiries]
    today_ts = pd.Timestamp(now.date())
    frames = []
    for i, exp in enumerate(expiries):
        if i:
            time.sleep(sleep_s)  # rate-limit: pausa entre expiries
        for opt_type, chain_df in (("call", t.option_chain(exp).calls),
                                   ("put", t.option_chain(exp).puts)):
            if chain_df is None or chain_df.empty:
                continue
            d = chain_df.copy()
            d["option_type"] = opt_type
            d["expiry"] = exp
            frames.append(d)
    if not frames:
        raise RuntimeError("todas las cadenas vacías")
    out = pd.concat(frames, ignore_index=True)
    keep = {
        "contractSymbol": "contract_symbol",
        "strike": "strike",
        "lastPrice": "last",
        "bid": "bid",
        "ask": "ask",
        "impliedVolatility": "implied_volatility",
        "openInterest": "open_interest",
        "volume": "volume",
        "inTheMoney": "in_the_money",
    }
    out = out.rename(columns={k: v for k, v in keep.items() if k in out.columns})
    out = out[[c for c in out.columns if c in keep.values() or c in ("option_type", "expiry")]]
    out["dte"] = (pd.to_datetime(out["expiry"]) - today_ts).dt.days
    out["symbol"] = symbol
    out["spot"] = spot
    out["snapshot_date"] = now.date().isoformat()
    return out


def symbols_already_collected(day_parquet: Path, symbols: List[str]) -> set:
    """Símbolos presentes en el snapshot del día (para --resume de parciales)."""
    if not day_parquet.exists():
        return set()
    try:
        df = pd.read_parquet(day_parquet)
        return {str(s) for s in df["symbol"].unique()} & set(symbols)
    except Exception:  # noqa: BLE001 — parquet roto: se re-colecta completo
        return set()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=",".join(IV_SYMBOLS),
                        help="CSV de símbolos (default: 30 de B1/B2)")
    parser.add_argument("--max-expiries", type=int, default=DEFAULT_MAX_EXPIRIES,
                        help=f"expiries por símbolo (default {DEFAULT_MAX_EXPIRIES})")
    parser.add_argument("--sleep-s", type=float, default=DEFAULT_SLEEP_S,
                        help="pausa entre expiries en s (default 1.0)")
    parser.add_argument("--resume", action="store_true",
                        help="completa símbolos faltantes del snapshot de HOY")
    args = parser.parse_args(argv)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    day = datetime.now()
    out_path = snapshot_path(day)

    done: set = set()
    if args.resume:
        done = symbols_already_collected(out_path, symbols)
        if done:
            print(f"[iv] resume: {len(done)} símbolos ya en {out_path.name}")

    n_ok = n_fail = 0
    total_rows = 0
    frames = []
    if done and out_path.exists():
        frames.append(pd.read_parquet(out_path))  # conservar lo ya colectado hoy

    for sym in symbols:
        if sym in done:
            continue
        spot = _spot_from_local_cache(sym)
        if spot is None:
            print(f"[{sym}] FAIL: sin spot en cache diario local — skip", file=sys.stderr)
            n_fail += 1
            continue
        try:
            df = collect_symbol(sym, spot, args.max_expiries, args.sleep_s)
            frames.append(df)
            n_ok += 1
            total_rows += len(df)
            print(f"[{sym}] OK {len(df)} contratos (spot {spot:.2f})")
        except Exception as exc:  # noqa: BLE001 — un símbolo no corta la corrida
            print(f"[{sym}] FAIL: {str(exc)[:120]}", file=sys.stderr)
            n_fail += 1
            continue

    if not frames:
        print("[iv] SIN DATOS: 0 símbolos colectados — no se escribe parquet", file=sys.stderr)
        return 1

    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(out_path, index=False)
    mb = out_path.stat().st_size / 1e6
    print(f"[iv] snapshot {day.date()} -> {out_path.name}: "
          f"{len(out)} filas, {n_ok} OK / {n_fail} FAIL, {mb:.1f} MB")
    return 0 if (n_ok > 0 and n_fail == 0) else (0 if n_ok > 0 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
