"""
IC de los scores DETERMINISTAS de la tríada (BULL/BEAR/CONTRARIAN/consenso),
sin llamadas a LLM — el harness real (validate_triad_llm.py) encontró un IC
de -0.29 en sólo 33 muestras con muchos timeouts de NIM; esto corre la
misma medición 100% local, con muestra mucho más grande, para confirmar si
es real o ruido de muestra chica.
"""
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.advanced_agents import NvidiaNIMClient
from app.core.triad_agents import TriadEvaluator
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZON_DAYS = 20
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def main():
    print("Descargando datos...")
    price_data = load_universe(SYMBOLS, "2019-01-01", "2024-12-31")
    indicators_cache = {s: calculate_all_indicators(df) for s, df in price_data.items()}

    dummy_client = NvidiaNIMClient(api_key="")  # 100% determinista, sin red
    triad = TriadEvaluator(nim_client=dummy_client)

    pooled = {"bull": [], "bear": [], "contrarian": [], "consensus": []}
    pooled_returns = []

    for symbol in SYMBOLS:
        df = indicators_cache[symbol]
        n = len(df)
        if n < 220:
            continue
        for i in range(200, n - HORIZON_DAYS, STRIDE_DAYS):
            window = df.iloc[:i + 1]
            consensus = triad.evaluate(window, symbol=symbol)

            entry = df["close"].iloc[i]
            future = df["close"].iloc[i + HORIZON_DAYS]
            fwd_return = future / entry - 1

            pooled["bull"].append(consensus.bull_score)
            pooled["bear"].append(consensus.bear_score)
            pooled["contrarian"].append(consensus.contrarian_score)
            pooled["consensus"].append(consensus.consensus_score)
            pooled_returns.append(fwd_return)

    n = len(pooled_returns)
    print(f"\n=== IC DETERMINISTA DE LA TRÍADA (n={n}, sin llamadas a red) ===")
    returns = pd.Series(pooled_returns)
    for name, values in pooled.items():
        ic = SignalQualityMetrics.compute_ic(pd.Series(values), returns)
        rank_ic = SignalQualityMetrics.compute_rank_ic(pd.Series(values), returns)
        print(f"{name:12s}  ic={ic:+.4f}  rank_ic={rank_ic:+.4f}")


if __name__ == "__main__":
    main()
