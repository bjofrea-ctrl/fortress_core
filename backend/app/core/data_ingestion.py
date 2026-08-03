import yfinance as yf
import pandas as pd
import os
from datetime import datetime

CACHE_DIR = "data/cache"


def download_data(ticker: str, start="2010-01-01", end=None) -> pd.DataFrame:
    end = end or datetime.today().strftime("%Y-%m-%d")
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = f"{CACHE_DIR}/{ticker}.parquet"

    if os.path.exists(cache_path):
        df = pd.read_parquet(cache_path)
        last_date = df.index[-1].strftime("%Y-%m-%d")
        if last_date < end:
            new = yf.download(ticker, start=last_date, end=end, progress=False)
            if not new.empty:
                df = pd.concat([df, new[~new.index.isin(df.index)]])
                df.to_parquet(cache_path)
    else:
        df = yf.download(ticker, start=start, end=end, progress=False)
        if not df.empty:
            df.to_parquet(cache_path)

    df.columns = [str(c).lower() for c in df.columns]
    return df


def load_universe(tickers: list, start: str, end: str) -> dict:
    data = {}
    for t in tickers:
        df = download_data(t, start, end)
        if len(df) > 200:
            data[t] = df
    return data