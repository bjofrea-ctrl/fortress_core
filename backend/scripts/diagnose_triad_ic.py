"""
IC de los scores DETERMINISTAS de la tríada (BULL/BEAR/CONTRARIAN/consenso),
sin llamadas a LLM — sobre el mismo pipeline de indicadores que usa
PredictiveEngine.analyze() de verdad (calculate_all_indicators +
calculate_predictive_indicators), no sólo el primero. Con sólo
calculate_all_indicators varias reglas (CMF, divergencias RSI, Smart Money
Index) nunca podían activarse porque esas columnas no existían.
"""
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.advanced_agents import NvidiaNIMClient
from app.core.triad_agents import TriadEvaluator
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZON_DAYS = 20
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
WARMUP_DAYS = 260  # cubre el warmup de ema200/momentum_12_1 (252d)


def build_full_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Replica exactamente el pipeline de PredictiveEngine.analyze() (líneas
    989-999): calculate_all_indicators mergeado + calculate_predictive_indicators
    encima, sin recortar filas por NaN salvo en 'close'."""
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

    dummy_client = NvidiaNIMClient(api_key="")  # 100% determinista, sin red (bug ya arreglado)
    triad = TriadEvaluator(nim_client=dummy_client)

    pooled = {"bull": [], "bear": [], "contrarian": [], "consensus": []}
    pooled_returns = []

    for symbol in SYMBOLS:
        df = indicators_cache[symbol]
        n = len(df)
        if n < WARMUP_DAYS + HORIZON_DAYS:
            continue
        for i in range(WARMUP_DAYS, n - HORIZON_DAYS, STRIDE_DAYS):
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
    print(f"\n=== IC DETERMINISTA DE LA TRÍADA (n={n}, pipeline completo, sin red) ===")
    returns = pd.Series(pooled_returns)
    for name, values in pooled.items():
        ic = SignalQualityMetrics.compute_ic(pd.Series(values), returns)
        rank_ic = SignalQualityMetrics.compute_rank_ic(pd.Series(values), returns)
        print(f"{name:12s}  ic={ic:+.4f}  rank_ic={rank_ic:+.4f}")


if __name__ == "__main__":
    main()
