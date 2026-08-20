import os
import time

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException

from app.api.routes.opportunities_universe import SYMBOLS

router = APIRouter(prefix="/api/market/live", tags=["live"])

# Cache live data for 30 seconds to avoid hitting Yahoo Finance too often
_cache: dict = {}
_CACHE_TTL = 30  # seconds


def _get_cached(key: str):
    """Get cached data if still fresh."""
    if key in _cache:
        data, timestamp = _cache[key]
        if time.time() - timestamp < _CACHE_TTL:
            return data
    return None


def _set_cached(key: str, data):
    """Cache data with current timestamp."""
    _cache[key] = (data, time.time())


@router.get("/overview")
async def get_live_overview():
    """Retorna precios en tiempo real para todos los símbolos del universo canónico."""
    cached = _get_cached("overview")
    if cached:
        return cached

    results = []

    for symbol in sorted(SYMBOLS):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info

            last_price = float(info.get("last_price", 0) or info.get("lastPrice", 0) or 0)
            if last_price == 0:
                # Try fast_info attributes
                try:
                    last_price = float(info.last_price)
                except (AttributeError, TypeError, ValueError):
                    continue

            previous = float(info.get("previous_close", 0) or 0)
            change = last_price - previous if previous > 0 else 0
            change_pct = (change / previous * 100) if previous > 0 else 0

            results.append({
                "symbol": symbol,
                "price": round(last_price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "previous_close": round(previous, 2),
                "market_cap": int(info.get("market_cap", 0) or 0),
            })
        except Exception:
            continue

    response = {"symbols": results, "timestamp": time.time()}
    _set_cached("overview", response)
    return response


@router.get("/{symbol}")
async def get_live_symbol(symbol: str):
    """Retorna datos en tiempo real detallados para un símbolo."""
    cache_key = f"symbol_{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Get intraday data (1-minute intervals for last 5 days)
        intraday = yf.download(symbol, period="5d", interval="5m", progress=False)
        intraday_data = []
        if not intraday.empty:
            # Flatten MultiIndex if present
            if isinstance(intraday.columns, pd.MultiIndex):
                intraday.columns = intraday.columns.get_level_values(0)

            for idx, row in intraday.tail(100).iterrows():
                intraday_data.append({
                    "datetime": idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, 'strftime') else str(idx)[:16],
                    "close": round(float(row.get("Close", 0)), 2),
                    "volume": int(row.get("Volume", 0)),
                })

        response = {
            "symbol": symbol,
            "price": round(float(info.get("regularMarketPrice", 0)), 2),
            "change": round(float(info.get("regularMarketChange", 0)), 2),
            "change_pct": round(float(info.get("regularMarketChangePercent", 0)), 2),
            "previous_close": round(float(info.get("regularMarketPreviousClose", 0)), 2),
            "open": round(float(info.get("regularMarketOpen", 0)), 2),
            "day_high": round(float(info.get("regularMarketDayHigh", 0)), 2),
            "day_low": round(float(info.get("regularMarketDayLow", 0)), 2),
            "volume": int(info.get("regularMarketVolume", 0) or 0),
            "market_cap": int(info.get("marketCap", 0) or 0),
            "fifty_two_week_high": round(float(info.get("fiftyTwoWeekHigh", 0)), 2),
            "fifty_two_week_low": round(float(info.get("fiftyTwoWeekLow", 0)), 2),
            "pe_ratio": round(float(info.get("trailingPE", 0)), 2) if info.get("trailingPE") else None,
            "eps": round(float(info.get("trailingEps", 0)), 2) if info.get("trailingEps") else None,
            "dividend_yield": round(float(info.get("dividendYield", 0)) * 100, 2) if info.get("dividendYield") else None,
            "beta": round(float(info.get("beta", 0)), 3) if info.get("beta") else None,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "currency": info.get("currency", "USD"),
            "exchange": info.get("exchange", "N/A"),
            "short_name": info.get("shortName", symbol),
            "long_name": info.get("longName", symbol),
            "intraday": intraday_data,
            "timestamp": time.time(),
        }
        _set_cached(cache_key, response)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo datos en vivo de {symbol}: {str(e)}")
