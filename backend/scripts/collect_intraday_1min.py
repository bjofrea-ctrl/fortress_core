"""
Colector intradía 1-min — I3 (infraestructura, no investigación).

Acumula barras 1-min vía Alpaca Market Data (feed iex, gratis con paper)
para STAGED_SYMBOLS (30; B1 del PLAN_REMEDIO_BRECHAS_20260903.md). Incremental:
solo descarga desde el último timestamp ya guardado (mismo patrón que
data_updater.sh para daily). No diseña hipótesis de trading — solo acumula
historial para futuro.

Uso:
  PYTHONPATH=backend ~/Desktop/fortress_core/backend/.venv/bin/python -m scripts.collect_intraday_1min
  # staged 30 (default):            -> STAGED_SYMBOLS
  # rollback trivial a los 7 BASE:  --base
  # subset manual:                   --symbols SPY,QQQ --days 7

Storage:
  data/cache/intraday_1min/{SYMBOL}.parquet  (columnas: timestamp UTC, open/high/low/close/volume/trade_count/vwap)
  Parquet particionado por símbolo, append incremental, dedup por timestamp.

Cron:
  launchd cada 30 min (ver DISENO_COLECTOR_INTRADIA.md). Fuera de horario
  no hace nada (0 barras nuevas).

B1 — lista staged (SPY, QQQ + 28 de mayor liquidez del universo 102 de
opportunities_universe.SYMBOLS): el ranking es MEDIDO, no de opinión —
mediana del dollar-volume (close*volume) 2026 sobre el cache diario real
del proyecto. La lista vive aquí como default del parámetro --symbols;
rollback a los 7 BASE = --base (o --symbols con CSV). Sin tocar el
universo de decisión del motor.

Rate/cuota Alpaca: el colector loguea por corrida el presupuesto consumido
(requests hechos + barras) y, si la response lo expone, los headers de
rate limit (X-RateLimit-*) — ver RateMonitor abajo. Es solo observabilidad
en el propio log (B1: "monitor de rate/cuota Alpaca en el propio log").
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

# ---------------------------------------------------------------------------
# B1 — lista staged 30: SPY, QQQ + 28 de mayor liquidez del universo 102
# (opportunities_universe.SYMBOLS = 7 BASE + NEW_UNIVERSE de
# fetch_universe_data). Ranking medido el 2026-09-04: mediana del
# dollar-volume (close*volume) del tramo 2026 sobre el cache diario real.
# Top-28 tras SPY/QQQ (los BASE que quedan fuera del top-28 medido — MSFT,
# AAPL, GOOGL, AMZN están dentro; NVDA lidera — no se excluye nada por
# criterio distinto de la liquidez medida).
STAGED_SYMBOLS = [
    "SPY", "QQQ",
    "NVDA", "TSLA", "MSFT", "AAPL", "AMD", "AMZN", "GOOGL", "META",
    "AVGO", "ORCL", "MRVL", "NFLX", "AMAT", "LLY", "JPM", "LRCX",
    "WMT", "XOM", "V", "CRM", "BRK-B", "UNH", "CAT", "COST",
    "CSCO", "MA", "BAC", "JNJ",
]
# Validación estructural en import (falla ruidoso si la lista se edita a mano
# mal): 30 únicos, subconjunto del universo 102 de opportunities_universe.
def _validate_staged() -> None:
    from app.api.routes.opportunities_universe import SYMBOLS as UNIVERSE_102
    if len(STAGED_SYMBOLS) != 30 or len(set(STAGED_SYMBOLS)) != 30:
        raise ValueError(f"STAGED_SYMBOLS debe tener 30 únicos, tiene {len(STAGED_SYMBOLS)}")
    fuera = [s for s in STAGED_SYMBOLS if s not in UNIVERSE_102]
    if fuera:
        raise ValueError(f"STAGED_SYMBOLS fuera del universo 102: {fuera}")


# ---------------------------------------------------------------------------
# Monitor de rate/cuota (observabilidad en el propio log — B1)
# ---------------------------------------------------------------------------
class RateMonitor:
    """Cuenta requests/barras por corrida y captura headers de rate limit.

    El colector inyecta `monitor_note(response)` en el cliente: get_bars ya
    expone cada response cruda vía el hook `on_response` (ver
    execution_costs.py) para que el monitor registre los headers
    X-RateLimit-* cuando la API los envía, sin duplicar la lógica HTTP.
    Al final de la corrida, `summary()` imprime el presupuesto consumido:
    30 símbolos × 1 request (+ paginación) cada 30 min = ~1.4k requests/día,
    muy por debajo del límite 200/min de Alpaca — el número en el log es la
    evidencia de que sigue siendo así.
    """

    def __init__(self) -> None:
        self.requests = 0
        self.bars = 0
        self.rate_headers: dict = {}

    def note_request(self, n_bars: int = 0) -> None:
        self.requests += 1
        self.bars += n_bars

    def note_headers(self, headers) -> None:
        """Registra headers de rate limit si vienen (X-RateLimit-*)."""
        try:
            for k, v in headers.items():
                if k.lower().startswith("x-ratelimit"):
                    self.rate_headers[k] = v
        except Exception:  # noqa: BLE001 — el monitor jamás rompe la corrida
            pass

    def summary(self, n_symbols: int) -> str:
        base = f"[rate] requests={self.requests} barras={self.bars} en {n_symbols} símbolos"
        if self.rate_headers:
            hdr = " ".join(f"{k}={v}" for k, v in sorted(self.rate_headers.items()))
            return f"{base} | {hdr}"
        return base + " | headers de rate limit no expuestos por la API en esta corrida"


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

def _fetch_bars(client: AlpacaPaperClient, symbol: str, start_iso: str, end_iso: str, monitor: "RateMonitor" = None):
    """Llama a client.get_bars con paginación ya manejada por el cliente.

    Si se pasa un RateMonitor, engancha el hook on_response del cliente para
    capturar headers de rate limit de cada response HTTP (incluida la
    paginación interna) y cuenta el request al volver."""
    hook_installed = False
    if monitor is not None:
        client.on_response = monitor.note_headers
        hook_installed = True
    try:
        bars = client.get_bars(symbol=symbol, timeframe="1Min", start=start_iso, end=end_iso, limit=10000, feed="iex", adjustment="raw")
        if monitor is not None:
            monitor.note_request(len(bars))
        return bars
    finally:
        if hook_installed:
            client.on_response = None

def collect_one(client: AlpacaPaperClient, symbol: str, days_back: int = DEFAULT_DAYS_BACK, monitor: "RateMonitor" = None) -> int:
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
        bars = _fetch_bars(client, symbol, start_iso, end_iso, monitor=monitor)
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
    _validate_staged()  # fail ruidoso si la staged se rompe al editarla
    parser = argparse.ArgumentParser(
        description="Colector 1-min incremental (Alpaca iex, staged 30 B1; --base = rollback a 7)"
    )
    parser.add_argument("--symbols", type=str, default=None,
                        help="CSV de símbolos (default: STAGED_SYMBOLS 30 de B1)")
    parser.add_argument("--base", action="store_true",
                        help="rollback trivial a los 7 BASE_SYMBOLS (pre-B1)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help="días hacia atrás si no hay cache (default 7)")
    args = parser.parse_args()

    if args.symbols is not None:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    elif args.base:
        symbols = list(BASE_SYMBOLS)
    else:
        symbols = list(STAGED_SYMBOLS)
    # Filtrar BRK-B -> BRK.B se maneja dentro del cliente
    _ensure_cache_dir()

    try:
        client = AlpacaPaperClient()
    except Exception as exc:  # noqa: BLE001
        print(f"[collect] ERROR credenciales Alpaca: {exc}", file=sys.stderr)
        print("[collect] Set ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY en env o .env", file=sys.stderr)
        return 1

    monitor = RateMonitor()
    total_new = 0
    for sym in symbols:
        try:
            total_new += collect_one(client, sym, days_back=args.days, monitor=monitor)
        except Exception as exc:  # noqa: BLE001
            print(f"[{sym}] ERROR inesperado: {exc}", file=sys.stderr)
            continue

    try:
        client.close()
    except Exception:
        pass

    print(f"[collect] done: {total_new} barras nuevas en {len(symbols)} símbolos -> {CACHE_DIR}")
    print(monitor.summary(len(symbols)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
