import os

import pandas as pd
from fastapi import APIRouter, HTTPException

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
        df = download_data(symbol, "2015-01-01")
        df = df.tail(limit)

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
        raise HTTPException(status_code=500, detail=f"Error obteniendo datos de {symbol}: {str(e)}")


@router.get("/indicators/{symbol}")
async def get_indicators(symbol: str, limit: int = 500):
    """Retorna indicadores técnicos para un símbolo."""
    try:
        df = download_data(symbol, "2015-01-01")
        df = calculate_all_indicators(df)
        df = df.tail(limit)

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
                "bb_upper": round(float(row.get("bb_upper", 0)), 2) if pd.notna(row.get("bb_upper")) else None,
                "bb_middle": round(float(row.get("bb_middle", 0)), 2) if pd.notna(row.get("bb_middle")) else None,
                "bb_lower": round(float(row.get("bb_lower", 0)), 2) if pd.notna(row.get("bb_lower")) else None,
                "stoch_k": round(float(row.get("stoch_k", 0)), 2) if pd.notna(row.get("stoch_k")) else None,
                "stoch_d": round(float(row.get("stoch_d", 0)), 2) if pd.notna(row.get("stoch_d")) else None,
                "volume": int(row.get("volume", 0)),
            })

        return {"symbol": symbol, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo datos de {symbol}: {str(e)}")


@router.get("/summary/{symbol}")
async def get_symbol_summary(symbol: str):
    """Retorna un resumen completo con KPIs de un símbolo."""
    try:
        df = download_data(symbol, "2015-01-01")
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

        # 52-week high/low
        last_252 = df.tail(252) if len(df) >= 252 else df
        high_52w = float(last_252["high"].max())
        low_52w = float(last_252["low"].min())

        # Distance from 52-week high/low
        pct_from_high = ((latest["close"] - high_52w) / high_52w) * 100
        pct_from_low = ((latest["close"] - low_52w) / low_52w) * 100

        # Average volume
        avg_volume = int(last_252["volume"].mean()) if len(last_252) > 0 else 0

        # Sharpe-like ratio (simplified)
        sharpe_like = annual_return / volatility if volatility > 0 else 0

        # Max drawdown
        cummax = df["close"].cummax()
        drawdown = (df["close"] - cummax) / cummax
        max_dd = float(drawdown.min()) * 100

        return {
            "symbol": symbol,
            "last_price": round(float(latest["close"]), 2),
            "total_return_pct": round(float(total_return), 2),
            "annual_return_pct": round(float(annual_return), 2),
            "annual_volatility_pct": round(float(volatility), 2),
            "sharpe_like": round(float(sharpe_like), 3),
            "max_drawdown_pct": round(float(max_dd), 2),
            "rsi14": round(float(latest.get("rsi14", 0)), 2) if pd.notna(latest.get("rsi14")) else None,
            "adx14": round(float(latest.get("adx14", 0)), 2) if pd.notna(latest.get("adx14")) else None,
            "stoch_k": round(float(latest.get("stoch_k", 0)), 2) if pd.notna(latest.get("stoch_k")) else None,
            "trend_bullish": bool(latest.get("trend_bullish", False)),
            "ema20": round(float(latest.get("ema20", 0)), 2),
            "ema50": round(float(latest.get("ema50", 0)), 2),
            "ema200": round(float(latest.get("ema200", 0)), 2),
            "bb_upper": round(float(latest.get("bb_upper", 0)), 2) if pd.notna(latest.get("bb_upper")) else None,
            "bb_lower": round(float(latest.get("bb_lower", 0)), 2) if pd.notna(latest.get("bb_lower")) else None,
            "momentum_12_1": round(float(latest.get("momentum_12_1", 0)), 2) if pd.notna(latest.get("momentum_12_1")) else None,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "pct_from_high": round(float(pct_from_high), 2),
            "pct_from_low": round(float(pct_from_low), 2),
            "avg_volume": avg_volume,
            "date_range": f"{first.name.strftime('%Y-%m-%d')} to {latest.name.strftime('%Y-%m-%d')}",
            "total_days": len(df),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo datos de {symbol}: {str(e)}")


@router.get("/overview")
async def get_market_overview():
    """Retorna un resumen de todos los símbolos para el market overview."""
    if not os.path.exists(CACHE_DIR):
        return {"symbols": []}

    files = [f.replace(".parquet", "") for f in os.listdir(CACHE_DIR) if f.endswith(".parquet")]
    overview = []

    for symbol in sorted(files):
        try:
            df = download_data(symbol, "2015-01-01")
            if len(df) < 200:
                continue

            latest = df.iloc[-1]
            first = df.iloc[0]

            # Total return
            total_return = ((latest["close"] - first["close"]) / first["close"]) * 100

            # 30-day return
            if len(df) >= 30:
                ret_30d = ((latest["close"] - df.iloc[-30]["close"]) / df.iloc[-30]["close"]) * 100
            else:
                ret_30d = 0

            # 90-day return
            if len(df) >= 90:
                ret_90d = ((latest["close"] - df.iloc[-90]["close"]) / df.iloc[-90]["close"]) * 100
            else:
                ret_90d = 0

            # Volatility
            returns = df["close"].pct_change().dropna()
            volatility = returns.std() * (252 ** 0.5) * 100

            # 52-week range
            last_252 = df.tail(252) if len(df) >= 252 else df
            high_52w = float(last_252["high"].max())
            low_52w = float(last_252["low"].min())

            # Position in 52-week range (0 = at low, 100 = at high)
            range_pos = ((latest["close"] - low_52w) / (high_52w - low_52w) * 100) if (high_52w - low_52w) > 0 else 50

            overview.append({
                "symbol": symbol,
                "price": round(float(latest["close"]), 2),
                "total_return_pct": round(float(total_return), 2),
                "return_30d_pct": round(float(ret_30d), 2),
                "return_90d_pct": round(float(ret_90d), 2),
                "volatility_pct": round(float(volatility), 2),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "range_position": round(float(range_pos), 1),
                "volume": int(latest.get("volume", 0)),
            })
        except Exception:
            continue

    # Sort by total return descending
    overview.sort(key=lambda x: x["total_return_pct"], reverse=True)
    return {"symbols": overview}
