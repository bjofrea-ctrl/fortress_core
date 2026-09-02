"""
Colector intradía 1-min — I3 (infraestructura, no investigación).

Acumula barras 1-min vía Alpaca Market Data (feed iex, gratis con paper)
para los 7 BASE_SYMBOLS. Incremental: solo descarga desde el último
timestamp ya guardado (mismo patrón que data_updater.sh para daily).
No diseña hipótesis de trading — solo acumula historial para futuro.

Uso:
  PYTHONPATH=backend ~/Desktop/fortress_core/backend/.venv/bin/python -m scripts.collect_intraday_1min
  # o con subset: --symbols SPY,QQQ --days 7

Storage:
  data/cache/intraday_1min/{SYMBOL}.parquet  (columnas: timestamp UTC, open/high/low/close/volume/trade_count/vwap)
  Parquet particionado por símbolo, append incremental, dedup por timestamp.

Cron:
  launchd cada 30 min durante horario de mercado (ver DISENO_COLECTOR_INTRADIA.md).
  Fuera de horario no hace nada (0 barras nuevas).
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# Permite `python -m scripts.collect_intraday_1min` y también `python scripts/...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.execution_costs import AlpacaPaperClient  # noqa: E402

BASE_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
DEFAULT_DAYS_BACK = 7
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "intraday_1min"
# Fallback para worktree vs main: si se corre desde worktree, CACHE_DIR es worktree/backend/data/...
# El launchd usa REPO absoluto, así que siempre escribe en main/backend/data/cache/intraday_1min

def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _parquet_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}.parquet"

def _load_existing(symbol: str) -> pd.DataFrame:
    p = _parquet_path(symbol)
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            return df.sort_values("timestamp")
        except Exception as exc:  # noqa: BLE001
            print(f"[{symbol}] warn: no se pudo leer parquet existente, se recreará: {exc}", file=sys.stderr)
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"])

def _fetch_bars(client: AlpacaPaperClient, symbol: str, start_iso: str, end_iso: str):
    """Llama a client.get_bars con paginación ya manejada por el cliente."""
    return client.get_bars(symbol=symbol, timeframe="1Min", start=start_iso, end=end_iso, limit=10000, feed="iex", adjustment="raw")

def collect_one(client: AlpacaPaperClient, symbol: str, days_back: int = DEFAULT_DAYS_BACK) -> int:
    existing = _load_existing(symbol)
    if not existing.empty:
        last_ts = pd.to_datetime(existing["timestamp"].max(), utc=True)
        # start = last + 1 minuto
        start_dt = last_ts + timedelta(minutes=1)
    else:
        start_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
        # Alinear a inicio de día UTC para no perder barras
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    end_dt = datetime.now(timezone.utc)

    # Si start >= end, nada que hacer
    if start_dt >= end_dt:
        print(f"[{symbol}] up-to-date hasta {last_ts if not existing.empty else 'vacío'} — 0 barras nuevas")
        return 0

    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        bars = _fetch_bars(client, symbol, start_iso, end_iso)
    except Exception as exc:  # noqa: BLE001
        print(f"[{symbol}] ERROR fetch {start_iso}->{end_iso}: {exc}", file=sys.stderr)
        return 0

    if not bars:
        print(f"[{symbol}] 0 barras nuevas ({start_iso}->{end_iso})")
        return 0

    # Normalizar a DataFrame
    rows = []
    for b in bars:
        # Alpaca bar: {"t": "2024-01-01T09:30:00Z", "o": 100, "h":..., "l":..., "c":..., "v":..., "n":..., "vw":...}
        try:
            rows.append({
                "timestamp": pd.to_datetime(b.get("t"), utc=True),
                "open": float(b.get("o", 0)),
                "high": float(b.get("h", 0)),
                "low": float(b.get("l", 0)),
                "close": float(b.get("c", 0)),
                "volume": int(b.get("v", 0)),
                "trade_count": int(b.get("n", 0)),
                "vwap": float(b.get("vw", 0)) if b.get("vw") is not None else None,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[{symbol}] warn: bar inválida {b}: {exc}", file=sys.stderr)
            continue

    new_df = pd.DataFrame(rows).sort_values("timestamp")
    if new_df.empty:
        print(f"[{symbol}] 0 barras válidas")
        return 0

    # Merge incremental + dedup
    if not existing.empty:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")

    # Guardar
    _ensure_cache_dir()
    # Asegurar tipos
    combined["timestamp"] = pd.to_datetime(combined["timestamp"], utc=True)
    combined.to_parquet(_parquet_path(symbol), index=False)

    added = len(combined) - len(existing)
    print(f"[{symbol}] +{len(new_df)} nuevas, total {len(combined)} (+{added} netas) {combined['timestamp'].min()} -> {combined['timestamp'].max()}")
    return len(new_df)

def main() -> int:
    parser = argparse.ArgumentParser(description="Colector 1-min incremental (Alpaca iex, 7 BASE_SYMBOLS)")
    parser.add_argument("--symbols", type=str, default=",".join(BASE_SYMBOLS), help="CSV de símbolos (default BASE 7)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help="días hacia atrás si no hay cache (default 7)")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    # Filtrar BRK-B -> BRK.B se maneja dentro del cliente
    _ensure_cache_dir()

    try:
        client = AlpacaPaperClient()
    except Exception as exc:  # noqa: BLE001
        print(f"[collect] ERROR credenciales Alpaca: {exc}", file=sys.stderr)
        print("[collect] Set ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY en env o .env", file=sys.stderr)
        return 1

    total_new = 0
    for sym in symbols:
        try:
            total_new += collect_one(client, sym, days_back=args.days)
        except Exception as exc:  # noqa: BLE001
            print(f"[{sym}] ERROR inesperado: {exc}", file=sys.stderr)
            continue

    try:
        client.close()
    except Exception:
        pass

    print(f"[collect] done: {total_new} barras nuevas en {len(symbols)} símbolos -> {CACHE_DIR}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
