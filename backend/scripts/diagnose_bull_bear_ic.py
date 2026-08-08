"""
IC por regla individual de BullAgent y BearAgent, usando rule_components()
directamente (sin duplicar la lógica de las reglas) — mismo pipeline de
indicadores que la tríada real recibe en producción.
"""
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.triad_agents import BullAgent, BearAgent
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZON_DAYS = 20
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
WARMUP_DAYS = 260


def build_full_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    with_base = calculate_all_indicators(d)
    for col in with_base.columns:
        if col not in d.columns:
            d[col] = with_base[col]
    d = calculate_predictive_indicators(d)
    return d.dropna(subset=["close"])


def main():
    print("Descargando datos...")
    price_data = load_universe(SYMBOLS, "2019-01-01", "2024-12-31")
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}

    bull = BullAgent()
    bear = BearAgent()

    bull_records, bear_records = [], []

    for symbol in SYMBOLS:
        df = indicators_cache[symbol]
        n = len(df)
        if n < WARMUP_DAYS + HORIZON_DAYS:
            continue
        for i in range(WARMUP_DAYS, n - HORIZON_DAYS, STRIDE_DAYS):
            window = df.iloc[:i + 1]
            entry = df["close"].iloc[i]
            future = df["close"].iloc[i + HORIZON_DAYS]
            fwd_return = future / entry - 1

            bull_row = {c.name: c.score for c in bull.rule_components(window)}
            bull_row["_return"] = fwd_return
            bull_records.append(bull_row)

            bear_row = {c.name: c.score for c in bear.rule_components(window)}
            bear_row["_return"] = fwd_return
            bear_records.append(bear_row)

    for agent_name, records in (("BULL", bull_records), ("BEAR", bear_records)):
        df_records = pd.DataFrame(records)
        returns = df_records["_return"]
        baseline_mean = returns.mean()
        print(f"\n=== IC por regla — {agent_name} (n={len(df_records)}, retorno base promedio={baseline_mean:+.4f}) ===")
        results = []
        for col in df_records.columns:
            if col == "_return":
                continue
            values = df_records[col]
            n_fired = values.notna().sum()
            if n_fired < 20:
                print(f"{col:24s}  n_disparos={n_fired} (insuficiente, se salta)")
                continue
            fired_mean = returns[values.notna()].mean()
            # IC (correlación) no sirve si la regla es binaria/valor fijo
            # (varianza cero cuando dispara) -> comparar la media de retorno
            # cuando dispara contra la media base es el test correcto ahí.
            if values.dropna().nunique() <= 1:
                diff = fired_mean - baseline_mean
                print(f"{col:24s}  [binario] retorno_si_dispara={fired_mean:+.4f}  "
                      f"vs base={baseline_mean:+.4f}  diff={diff:+.4f}  n_disparos={n_fired}")
                continue
            ic = SignalQualityMetrics.compute_ic(values, returns)
            rank_ic = SignalQualityMetrics.compute_rank_ic(values, returns)
            results.append((col, ic, rank_ic, n_fired))
        results.sort(key=lambda r: abs(r[1]), reverse=True)
        for name, ic, rank_ic, n_fired in results:
            print(f"{name:24s}  ic={ic:+.4f}  rank_ic={rank_ic:+.4f}  n_disparos={n_fired}")


if __name__ == "__main__":
    main()
