from fastapi import APIRouter
import pandas as pd
import os
from app.core.data_ingestion import download_data
from app.core.indicators import calculate_all_indicators

router = APIRouter(prefix="/api/market", tags=["market"])

CACHE_DIR = "data/cache"


@router.get("/symbols")
async def get_symbols():
    """Lista los símbolos disponibles en el cache."""
    if not os.path.exists(CACHE_DIR):
        return {"symbols": []}

    files = [f.replace(".parquet", "") for f in os.listdir(CACHE_DIR) if f.endswith(".parquet")]
    return {"symbols": sorted(files)}


@router.get("/prices/{symbol}")
async def get_prices(symbol: str, limit: int = 500):
    """Retorna datos de precios para un símbolo."""
    try:
        df = download_data(symbol, "2015-01-01", "2024-12-31")
        # Take last N rows
        df = df.tail(limit)

        # Format for charts
        data = []
        for idx, row in df.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10],
                "open": round(float(row.get("open", 0)), 2),
                "high": round(float(row.get("high", 0)), 2),
                "low": round(float(row.get("low", 0)), 2),
                "close": round(float(row.get("close", 0)), 2),
                "volume": int(row.get("volume", 0)),
            })

        return {"symbol": symbol, "data": data}
    except Exception as e:
        return {"error": str(e), "symbol": symbol, "data": []}


@router.get("/indicators/{symbol}")
async def get_indicators(symbol: str, limit: int = 500):
    """Retorna indicadores técnicos para un símbolo."""
    try:
        df = download_data(symbol, "2015-01-01", "2024-12-31")
        df = calculate_all_indicators(df)
        df = df.tail(limit)

        # Format for charts
        data = []
        for idx, row in df.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10],
                "close": round(float(row.get("close", 0)), 2),
                "ema20": round(float(row.get("ema20", 0)), 2),
                "ema50": round(float(row.get("ema50", 0)), 2),
                "ema200": round(float(row.get("ema200", 0)), 2),
                "rsi14": round(float(row.get("rsi14", 0)), 2) if pd.notna(row.get("rsi14")) else None,
                "adx14": round(float(row.get("adx14", 0)), 2) if pd.notna(row.get("adx14")) else None,
                "atr14": round(float(row.get("atr14", 0)), 2) if pd.notna(row.get("atr14")) else None,
                "macd": round(float(row.get("macd", 0)), 4) if pd.notna(row.get("macd")) else None,
                "macd_signal": round(float(row.get("macd_signal", 0)), 4) if pd.notna(row.get("macd_signal")) else None,
                "volume_ratio": round(float(row.get("volume_ratio", 1)), 2) if pd.notna(row.get("volume_ratio")) else None,
                "momentum_12_1": round(float(row.get("momentum_12_1", 0)), 2) if pd.notna(row.get("momentum_12_1")) else None,
            })

        return {"symbol": symbol, "data": data}
    except Exception as e:
        return {"error": str(e), "symbol": symbol, "data": []}


@router.get("/summary/{symbol}")
async def get_symbol_summary(symbol: str):
    """Retorna un resumen con KPIs de un símbolo."""
    try:
        df = download_data(symbol, "2015-01-01", "2024-12-31")
        df = calculate_all_indicators(df)

        latest = df.iloc[-1]
        first = df.iloc[0]

        # Calculate returns
        total_return = ((latest["close"] - first["close"]) / first["close"]) * 100
        days = (df.index[-1] - df.index[0]).days
        annual_return = ((1 + total_return / 100) ** (365.0 / days) - 1) * 100 if days > 0 else 0

        # Calculate volatility
        returns = df["close"].pct_change().dropna()
        volatility = returns.std() * (252 ** 0.5) * 100

        return {
            "symbol": symbol,
            "last_price": round(float(latest["close"]), 2),
            "total_return_pct": round(float(total_return), 2),
            "annual_return_pct": round(float(annual_return), 2),
            "annual_volatility_pct": round(float(volatility), 2),
            "rsi14": round(float(latest.get("rsi14", 0)), 2) if pd.notna(latest.get("rsi14")) else None,
            "adx14": round(float(latest.get("adx14", 0)), 2) if pd.notna(latest.get("adx14")) else None,
            "trend_bullish": bool(latest.get("trend_bullish", False)),
            "ema20": round(float(latest.get("ema20", 0)), 2),
            "ema50": round(float(latest.get("ema50", 0)), 2),
            "ema200": round(float(latest.get("ema200", 0)), 2),
            "momentum_12_1": round(float(latest.get("momentum_12_1", 0)), 2) if pd.notna(latest.get("momentum_12_1")) else None,
            "date_range": f"{first.name.strftime('%Y-%m-%d')} to {latest.name.strftime('%Y-%m-%d')}",
            "total_days": len(df),
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}