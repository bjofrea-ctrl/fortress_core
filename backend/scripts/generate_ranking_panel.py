"""
Script para generar panel de ranking con los 50 símbolos COMPLETOS.

Diferencia clave vs factor_panel: NO aplica filtro eligible.
Esto permite calcular percentiles reales dentro del universo.

Uso: python scripts/generate_ranking_panel.py
"""

import os
import sys
import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuración
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")
UNIVERSE = [
    "SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "ABBV", "ACN", "ADBE", "AMD", "AMGN", "AVGO", "BAC",
    "BRK-B", "CAT", "CMCSA", "COST", "CRM", "CSCO", "CVX", "DIS", "GE",
    "HD", "IBM", "INTU", "JNJ", "JPM", "KO", "LIN", "LLY", "MA",
    "MCD", "META", "MRK", "ORCL", "PEP", "PFE",
    "PG", "PM", "QCOM", "SPGI", "TMO", "TSLA", "TXN", "UNH",
    "V", "WMT", "XOM",
]


def load_price_data(symbol: str) -> pd.DataFrame:
    """Cargar datos OHLCV de un símbolo desde parquet."""
    path = os.path.join(CACHE_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        print(f"  WARN: {symbol}.parquet not found, skipping")
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df.columns = [c.lower() for c in df.columns]
    return df


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calcular indicadores técnicos sobre el dataframe completo."""
    df = df.copy()

    # Momentum 12-1
    df["momentum_12_1"] = df["close"].pct_change(1) / df["close"].pct_change(12).abs()

    # RSI 14
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # ADX 14
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=14).mean()
    plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=14).mean() / atr)
    dx = abs(plus_di - minus_di) / (plus_di + minus_di)
    df["adx_14"] = dx.rolling(window=14).mean() * 100

    # EMA 20 y 50
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    # Volume ratio (20-day avg)
    df["volume_20_avg"] = df["volume"].rolling(window=20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_20_avg"]

    # Trend OK (EMA20 > EMA50)
    df["trend_ok"] = df["ema20"] > df["ema50"]

    return df


def calculate_rankings(all_data: Dict[str, pd.DataFrame], date: str) -> pd.DataFrame:
    """Calcular percentiles de cada indicador para una fecha específica."""
    date_df = pd.DataFrame(index=UNIVERSE, columns=[
        "momentum_rank", "rsi_rank", "adx_rank", "trend_rank",
        "momentum_score", "rsi_score", "adx_score"
    ])

    for symbol in UNIVERSE:
        if symbol not in all_data:
            continue
        df = all_data[symbol]
        if date not in df.index:
            continue

        row = df.loc[date]
        date_df.loc[symbol, "momentum_score"] = row.get("momentum_12_1", 0)
        date_df.loc[symbol, "rsi_score"] = row.get("rsi_14", 50)
        date_df.loc[symbol, "adx_score"] = row.get("adx_14", 0)
        date_df.loc[symbol, "trend_ok"] = row.get("trend_ok", False)

    # Calcular percentiles (0-100)
    for col in ["momentum_score", "rsi_score", "adx_score"]:
        rank_col = col.replace("_score", "_rank")
        date_df[rank_col] = date_df[col].rank(pct=True) * 100

    # Trend rank: 100 si trend_ok, 0 si no
    date_df["trend_rank"] = date_df["trend_ok"].astype(int) * 100

    return date_df


def main():
    """Generar panel de ranking completo."""
    print("Generando panel de ranking para 50 símbolos...")

    # Cargar todos los datos
    all_data = {}
    for symbol in UNIVERSE:
        df = load_price_data(symbol)
        if not df.empty:
            df = calculate_indicators(df)
            all_data[symbol] = df

    print(f"Cargados {len(all_data)} símbolos con indicadores")

    # Obtener fechas comunes
    all_dates = set()
    for symbol, df in all_data.items():
        all_dates.update(df.index.astype(str))

    common_dates = sorted(list(all_dates))
    print(f"Fechas disponibles: {len(common_dates)}")

    # Calcular rankings para cada fecha
    rankings = []
    for date in common_dates:
        date_ranking = calculate_rankings(all_data, date)
        date_ranking["date"] = date
        rankings.append(date_ranking)

    # Guardar como parquet
    result = pd.concat(rankings, ignore_index=True)
    result = result.sort_values("date")

    output_path = os.path.join(CACHE_DIR, "ranking_panel.parquet")
    result.to_parquet(output_path)
    print(f"Panel de ranking guardado en {output_path}")
    print(f"Forma: {result.shape}")
    print(f"Columnas: {list(result.columns)}")

    # Mostrar ejemplo
    print("\nEjemplo (última fecha):")
    print(result.tail(10).to_string())


if __name__ == "__main__":
    main()
