import yfinance as yf
import pandas as pd
import os
from datetime import datetime, timedelta

CACHE_DIR = "data/cache"


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex or tuple columns from yfinance 1.x."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    elif any(isinstance(c, tuple) for c in df.columns):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def download_data(ticker: str, start="2010-01-01", end=None) -> pd.DataFrame:
    end = end or datetime.today().strftime("%Y-%m-%d")
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = f"{CACHE_DIR}/{ticker}.parquet"

    if os.path.exists(cache_path):
        df = pd.read_parquet(cache_path)
        df = _flatten_columns(df)

        # Check if we need to download earlier data (skip if diff < 7 days)
        first_date = pd.Timestamp(df.index[0])
        start_ts = pd.Timestamp(start)
        if (first_date - start_ts).days > 7:
            old = yf.download(ticker, start=start, end=first_date.strftime("%Y-%m-%d"), progress=False)
            if not old.empty:
                old = _flatten_columns(old)
                df = pd.concat([old[~old.index.isin(df.index)], df])
                df = _flatten_columns(df)
                df.to_parquet(cache_path)

        # Check if we need to download newer data
        last_date = pd.Timestamp(df.index[-1])
        end_ts = pd.Timestamp(end)
        if (end_ts - last_date).days > 7:
            new = yf.download(ticker, start=last_date.strftime("%Y-%m-%d"), end=end, progress=False)
            if not new.empty:
                new = _flatten_columns(new)
                df = pd.concat([df, new[~new.index.isin(df.index)]])
                df = _flatten_columns(df)
                df.to_parquet(cache_path)
    else:
        df = yf.download(ticker, start=start, end=end, progress=False)
        if not df.empty:
            df = _flatten_columns(df)
            df.to_parquet(cache_path)

    df = _flatten_columns(df)
    df.columns = [str(c).lower() for c in df.columns]
    return df


def load_universe(tickers: list, start: str, end: str) -> dict:
    data = {}
    for t in tickers:
        df = download_data(t, start, end)
        if len(df) > 200:
            data[t] = df
    return data