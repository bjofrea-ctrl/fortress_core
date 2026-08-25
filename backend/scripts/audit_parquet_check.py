"""Verificacion de auditoria ronda 2 - fechas de inicio + splits."""
import pandas as pd
import os

cache = "data/cache"
syms = [
    "SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "AVGO", "BRK-B", "LLY", "JPM", "WMT", "V", "UNH", "XOM", "MA", "ORCL",
    "PG", "COST", "HD", "JNJ", "ABBV", "BAC", "MRK", "CRM", "KO", "ADBE",
    "PEP", "AMD", "NFLX", "TMO", "CVX", "CSCO", "ACN", "MCD", "IBM", "LIN",
    "QCOM", "GE", "INTU", "PM", "CMCSA", "DIS", "TXN", "CAT", "AMGN",
    "PFE", "SPGI",
]

print("=== FECHAS DE INICIO ===")
late = []
for s in sorted(syms):
    p = os.path.join(cache, f"{s}.parquet")
    if os.path.exists(p):
        df = pd.read_parquet(p)
        first = str(df.index[0].date()) if len(df) else "SIN_DATOS"
        rows = len(df)
        flag = " <== POSTERIOR A 2015" if first > "2015-01-01" else ""
        if first > "2015-01-01":
            late.append(s)
        print(f"{s:8s} {first} filas={rows}{flag}")
    else:
        print(f"{s:8s} SIN_PARQUET")

print(f"\nTotal con primer dato posterior a 2015-01-01: {len(late)}")
print(f"Simbolos: {late}")
print()

# Detectar nombre de columna close
df0 = pd.read_parquet(os.path.join(cache, "AAPL.parquet"))
close_col = "Close" if "Close" in df0.columns else "close"
print(f"Columna close detectada: '{close_col}'")
print(f"Columnas: {list(df0.columns)}")
print()

print("=== SPLITS (precio close dia antes/despues) ===")
for sym, date in [
    ("AAPL", "2020-08-31"),
    ("NVDA", "2024-06-10"),
    ("GOOGL", "2022-07-18"),
    ("AVGO", "2024-07-15"),
]:
    p = os.path.join(cache, f"{sym}.parquet")
    if os.path.exists(p):
        df = pd.read_parquet(p)
        c = "Close" if "Close" in df.columns else "close"
        ts = pd.Timestamp(date)
        idx = df.index.get_indexer([ts], method="nearest")[0]
        if idx > 0 and idx < len(df) - 1:
            prev_c = float(df[c].iloc[idx - 1])
            day_c = float(df[c].iloc[idx])
            next_c = float(df[c].iloc[idx + 1])
            ratio = prev_c / day_c if day_c else 0
            idx_date = str(df.index[idx].date())
            print(
                f"{sym:6s} target={date} actual={idx_date}: "
                f"prev={prev_c:.2f} day={day_c:.2f} next={next_c:.2f} "
                f"ratio_prev/day={ratio:.2f}"
            )
