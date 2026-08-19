"""Universo de decisión CANÓNICO del dashboard (fuente única).

MOTIVO (bug 2026-08-19, Tarea F): el dashboard mostraba 44 símbolos y no 50 porque
`opportunities.SYMBOLS` era una lista curada HARDCODED de 44, distinta del "universo
50" (7 base + NEW_UNIVERSE de 43) que usan los trials de investigación y la medición
de costos. La raíz era la DUPLICACIÓN manual de la lista — dos lugares, dos números,
se desincronizaron.

SOLUCIÓN: un solo lugar canónico. Este módulo define el universo de decisión
derivándolo de la fuente de verdad `scripts/fetch_universe_data.NEW_UNIVERSE` (los 43
añadidos por market cap, corte estático 2026-08) + los 7 originales. Todo el que
necesite el universo importa de acá (o de opportunities.py, que re-exporta).

Regla de oro: NUNCA reescribir la lista a mano en otro archivo. Si el universo cambia,
se cambia en `fetch_universe_data.NEW_UNIVERSE` (la fuente) y esto se actualiza solo.
"""

# Los 7 símbolos originales del motor (BASE_SYMBOLS).
_BASE_SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

try:
    from scripts.fetch_universe_data import NEW_UNIVERSE  # type: ignore
except Exception:  # pragma: no cover - solo si scripts/ no está en el path
    # Fallback explícito a la lista curada histórica (evita romper el runtime si
    # el script de fetch no es importable en algún entorno); documenta el origen.
    NEW_UNIVERSE = [
        "META", "TSLA", "AVGO", "BRK-B", "LLY", "JPM", "WMT", "V", "UNH",
        "XOM", "MA", "ORCL", "PG", "COST", "HD", "JNJ", "ABBV", "BAC",
        "MRK", "CRM", "KO", "ADBE", "PEP", "AMD", "NFLX", "TMO", "CVX",
        "CSCO", "ACN", "MCD", "IBM", "LIN", "QCOM", "GE", "INTU", "PM",
        "CMCSA", "DIS", "TXN", "CAT", "AMGN", "PFE", "SPGI",
    ]

# Universo de decisión = 7 base + 43 expandidos = 50, sin duplicados.
SYMBOLS = list(dict.fromkeys(_BASE_SYMBOLS + list(NEW_UNIVERSE)))

# Tickers de mercado para el clasificador de régimen (macro).
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
