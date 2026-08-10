"""Fetch del universo expandido (proyecto pre-registrado, fase A0).

Regla estática pre-registrada: los 7 símbolos actuales (SPY/QQQ/AAPL/MSFT/
GOOGL/AMZN/NVDA) + top-43 US-listed por market cap (corte estático 2026-08),
con historial >= 2015-01-01 en yfinance. Sin lookahead: la lista se fija AHORA
y no se re-elige mirando resultados.
"""
import sys

from app.core.data_ingestion import download_data

NEW_UNIVERSE = [
    "META", "TSLA", "AVGO", "BRK-B", "LLY", "JPM", "WMT", "V", "UNH",
    "XOM", "MA", "ORCL", "PG", "COST", "HD", "JNJ", "ABBV", "BAC",
    "MRK", "CRM", "KO", "ADBE", "PEP", "AMD", "NFLX", "TMO", "CVX",
    "CSCO", "ACN", "MCD", "IBM", "LIN", "QCOM", "GE", "INTU", "PM",
    "CMCSA", "DIS", "TXN", "CAT", "AMGN", "PFE", "SPGI",
]


def main():
    failed = []
    for ticker in NEW_UNIVERSE:
        try:
            df = download_data(ticker, "2015-01-01")
            first = df.index[0].strftime("%Y-%m-%d") if len(df) else "SIN DATOS"
            last = df.index[-1].strftime("%Y-%m-%d") if len(df) else "-"
            print(f"{ticker:6s} filas={len(df):5d} {first} -> {last}")
        except Exception as exc:  # noqa: BLE001
            failed.append((ticker, str(exc)))
            print(f"{ticker:6s} ERROR: {exc}", file=sys.stderr)
    if failed:
        print(f"\nFALLARON {len(failed)}: {failed}")
        sys.exit(1)
    print(f"\nOK: {len(NEW_UNIVERSE) - len(failed)}/{len(NEW_UNIVERSE)} tickers en cache")


if __name__ == "__main__":
    main()
