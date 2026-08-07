"""
Mide si la tríada de LLMs (BULL/BEAR/CONTRARIAN vía NVIDIA NIM) agrega valor
predictivo real sobre el determinista puro. Hace llamadas REALES a NIM
(consume tu cuota free-tier) — muestra deliberadamente chica (n~30) para no
gastar cuota ni tardar demasiado; suficiente para una lectura direccional,
no para una conclusión estadísticamente sólida.

Compara IC(consenso con LLM) vs IC(consenso 100% determinista) contra
retornos futuros reales de precio.
"""
from datetime import datetime
import pandas as pd

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.advanced_agents import NvidiaNIMClient
from app.core.triad_agents import TriadEvaluator
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZON_DAYS = 20
SYMBOLS = ["AAPL", "MSFT", "NVDA"]
N_DATES_PER_SYMBOL = 10


def main():
    print("Descargando datos...")
    price_data = load_universe(SYMBOLS, "2022-01-01", "2024-12-31")
    indicators_cache = {s: calculate_all_indicators(df) for s, df in price_data.items()}

    llm_client = NvidiaNIMClient()  # usa la key real de .env
    if not llm_client.is_available():
        print("NVIDIA_NIM_API_KEY no está configurada — no hay nada que medir.")
        return
    triad_with_llm = TriadEvaluator(nim_client=llm_client)

    dummy_client = NvidiaNIMClient(api_key="")  # fuerza modo 100% determinista
    triad_deterministic = TriadEvaluator(nim_client=dummy_client)

    with_llm_scores, deterministic_scores, forward_returns = [], [], []

    for symbol in SYMBOLS:
        df = indicators_cache[symbol]
        n = len(df)
        if n < 220 + HORIZON_DAYS:
            print(f"  {symbol}: historial insuficiente, se salta")
            continue
        usable_range = n - HORIZON_DAYS - 200
        stride = max(usable_range // N_DATES_PER_SYMBOL, 1)

        for i in range(200, n - HORIZON_DAYS, stride):
            window = df.iloc[:i + 1]
            date = df.index[i]

            det_consensus = triad_deterministic.evaluate(window, symbol=symbol)
            print(f"  [{symbol} {date.date()}] llamando a NIM real (BULL/BEAR/CONTRARIAN)...")
            llm_consensus = triad_with_llm.evaluate(window, symbol=symbol)

            entry = df["close"].iloc[i]
            future = df["close"].iloc[i + HORIZON_DAYS]
            fwd_return = future / entry - 1

            deterministic_scores.append(det_consensus.consensus_score)
            with_llm_scores.append(llm_consensus.consensus_score)
            forward_returns.append(fwd_return)

    n = len(forward_returns)
    if n < 20:
        print(f"\nSólo {n} muestras válidas — insuficiente para un IC confiable (mínimo 20).")
        return

    ic_det = SignalQualityMetrics.compute_ic(pd.Series(deterministic_scores), pd.Series(forward_returns))
    ic_llm = SignalQualityMetrics.compute_ic(pd.Series(with_llm_scores), pd.Series(forward_returns))
    rank_ic_det = SignalQualityMetrics.compute_rank_ic(pd.Series(deterministic_scores), pd.Series(forward_returns))
    rank_ic_llm = SignalQualityMetrics.compute_rank_ic(pd.Series(with_llm_scores), pd.Series(forward_returns))

    print(f"\n=== RESULTADO (n={n}, muestra chica — lectura direccional, no concluyente) ===")
    print(f"IC determinista puro:  {ic_det:+.4f}  (rank_ic={rank_ic_det:+.4f})")
    print(f"IC con tríada LLM:     {ic_llm:+.4f}  (rank_ic={rank_ic_llm:+.4f})")
    diff = ic_llm - ic_det
    veredicto = "la tríada LLM agrega valor sobre el determinista" if diff > 0.01 else (
        "la tríada LLM NO agrega valor medible sobre el determinista" if diff < -0.01 else
        "diferencia despreciable, no hay evidencia de que la tríada LLM agregue valor"
    )
    print(f"Diferencia: {diff:+.4f} -> {veredicto}")


if __name__ == "__main__":
    main()
