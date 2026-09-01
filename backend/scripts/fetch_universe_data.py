"""Fetch del universo expandido (proyecto pre-registrado, fase A0).

Regla estática pre-registrada: los 7 símbolos actuales (SPY/QQQ/AAPL/MSFT/
GOOGL/AMZN/NVDA) + top-43 US-listed por market cap (corte estático 2026-08),
con historial >= 2015-01-01 en yfinance. Sin lookahead: la lista se fija AHORA
y no se re-elige mirando resultados.
"""
import sys

from app.core.data_ingestion import download_data

NEW_UNIVERSE = [
    # --- Bloque original (43, corte 2026-08, large/mega-cap) ---
    "META", "TSLA", "AVGO", "BRK-B", "LLY", "JPM", "WMT", "V", "UNH",
    "XOM", "MA", "ORCL", "PG", "COST", "HD", "JNJ", "ABBV", "BAC",
    "MRK", "CRM", "KO", "ADBE", "PEP", "AMD", "NFLX", "TMO", "CVX",
    "CSCO", "ACN", "MCD", "IBM", "LIN", "QCOM", "GE", "INTU", "PM",
    "CMCSA", "DIS", "TXN", "CAT", "AMGN", "PFE", "SPGI",
    # --- Ampliación 2026-09-01 (52, propuesta corregida y verificada 2015) ---
    # Tecnología / Software (10)
    "SNPS", "CDNS", "TYL", "PTC", "AKAM", "FFIV", "EPAM", "CHKP", "PANW", "QLYS",
    # Semiconductores / Hardware (6)
    "MRVL", "SWKS", "QRVO", "MPWR", "AMAT", "LRCX",
    # Salud / Biotech / Devices (7)
    "DXCM", "ISRG", "VEEV", "ALGN", "BIIB", "REGN", "ZTS",
    # Financieros / Fintech (6)
    "PYPL", "BR", "STAG", "AXP", "SCHW", "BLK",
    # Industrial / Transporte / Logística (6)
    "UPS", "UNP", "DE", "ETN", "PH", "WM",
    # Consumo discrecional / Retail (4)
    "MAR", "SBUX", "RCL", "DRI",
    # Energía / Materiales (5)
    "SLB", "OKE", "VLO", "FCX", "NEM",
    # Real Estate / Utilities (5)
    "PLD", "EQIX", "DLR", "WELL", "XEL",
    # Comunicación / Medios (3)
    "TMUS", "CHTR", "EBAY",
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
