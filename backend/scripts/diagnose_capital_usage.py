"""
SUB-TRIAL PRE-REGISTRADO (PLAN §9.3) — Diagnóstico de uso de capital.

Corre el backtest V1 sobre el universo de 50 símbolos con instrumentación de
uso de capital (track_capital_usage). EL DELIVERABLE ES EL INFORME, NO UN
CAMBIO DE MECÁNICA: si el diagnóstico muestra capital infra-utilizada, relajar
los topes (5 concurrentes / 10% posición / Kelly 25%) sería un trial NUEVO
(N_TRIALS 17 -> 18) con decisión separada del usuario. Este script NO cambia
nada del motor y NO consume presupuesto DSR.

Métricas por día y por régimen: % de capital desplegado, señales que pasaron
el gate (n_gate_signals), posiciones simultáneas, y oportunidades perdidas
por topes (gate > 5 top-5).
"""
import datetime
import os

import pandas as pd

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.market_sentiment import build_sentiment_frame
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
START = "2019-01-01"
END = "2026-08-04"


def main():
    out_path = os.path.join("data", "cache", f"capital_usage_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("SUB-TRIAL §9.3 — Diagnóstico de uso de capital (universo 50, V1)")
    log("Deliverable: INFORME. No cambia mecánica. No consume N_TRIALS.")
    log("=" * 72)

    market_data = load_universe(MARKET_TICKERS, "2015-01-01", END)
    price_data = load_universe(SYMBOLS, START, END)

    trading_dates = price_data["SPY"].index
    sentiment = build_sentiment_frame(trading_dates)
    sent_map = {ts: float(v) for ts, v in sentiment["aaii_bullbear_spread"].items() if pd.notna(v)}

    log("Corriendo V1-ranking con instrumentación de capital...")
    res = BacktestEngine(initial_capital=25000).run(
        price_data, market_data, pd.Timestamp(START), pd.Timestamp(END),
        sentiment_data=sent_map, track_capital_usage=True,
    )

    log = log
    usage = pd.DataFrame(res["capital_usage_log"])
    usage.to_parquet(out_path.replace(".txt", "_usage.parquet"))
    trades = pd.DataFrame(res["trades"])
    trades.to_parquet(out_path.replace(".txt", "_trades.parquet"))

    log(f"\nDías con señales en el log: {len(usage)}")
    log(f"Capital inicial: $25,000 | TOPES: 5 concurrentes / 10% por posición / Kelly 25%")

    # --- Uso de capital general ---
    deployed = usage["capital_deployed_pct"].replace(0, float("nan"))
    log("\n--- USO DE CAPITAL (todos los días) ---")
    log(f"  promedio: {deployed.mean():.1%} | mediana: {deployed.median():.1%} | p25: {deployed.quantile(0.25):.1%} | p90: {deployed.quantile(0.90):.1%} | máx: {deployed.max():.1%}")
    idle = (usage["capital_deployed_pct"] < 0.10).mean()
    log(f"  días con <10% desplegado: {idle:.1%} ({int(idle * len(usage))}/{len(usage)})")
    over50 = (usage["capital_deployed_pct"] > 0.50).mean()
    log(f"  días con >50% desplegado: {over50:.1%} ({int(over50 * len(usage))}/{len(usage)})")

    # --- Por régimen ---
    log("\n--- USO DE CAPITAL POR RÉGIMEN ---")
    by_regime = usage.groupby("regime_name")["capital_deployed_pct"].agg(["mean", "median", "max", "count"])
    by_regime = by_regime.sort_values("mean", ascending=False)
    for regime, row in by_regime.iterrows():
        log(f"  {regime:12s} n_dias={int(row['count']):5d} mean={row['mean']:.1%} mediana={row['median']:.1%} máx={row['max']:.1%}")

    # --- Señales gate vs tomadas ---
    log("\n--- SEÑALES DEL GATE vs TOMADAS (top-5) ---")
    gate_days = usage[usage["n_gate_signals"] > 0]
    log(f"  días con >=1 señal de gate: {len(gate_days)}/{len(usage)} ({len(gate_days) / len(usage):.1%})")
    log(f"  señales de gate por día (cuando hay): mean={gate_days['n_gate_signals'].mean():.1f} mediana={gate_days['n_gate_signals'].median():.0f} máx={gate_days['n_gate_signals'].max()}")
    truncated = gate_days[gate_days["n_gate_signals"] > 5]
    log(f"  días donde el gate dio >5 señales (top-5 recorta): {len(truncated)} ({len(truncated) / len(gate_days):.1%} de días con señales)")
    log(f"  señales totales de gate: {gate_days['n_gate_signals'].sum():.0f} | recortadas por top-5: {max(gate_days['n_gate_signals'].sum() - 5 * len(gate_days), 0):.0f}")

    # --- Posiciones simultáneas ---
    log("\n--- POSICIONES SIMULTÁNEAS ---")
    pos = usage["n_positions"]
    log(f"  mean={pos.mean():.2f} mediana={pos.median():.0f} máx={pos.max()}")
    log(f"  días con 0 posiciones: {(pos == 0).mean():.1%} | con >=2: {(pos >= 2).mean():.1%} | con 5 (tope): {(pos >= 5).mean():.1%}")

    # --- Oportunidades perdidas (gate - top-5), por ventana ---
    log("\n--- OPORTUNIDADES PERDIDAS POR TOP-5, POR VENTANA OOS ---")
    for label, s, e in [("W1 2020-2021", "2020-01-01", "2021-12-31"),
                        ("W2 2022-2023", "2022-01-01", "2023-12-31"),
                        ("W3 2024-2026", "2024-01-01", END)]:
        w = gate_days[(gate_days["date"] >= s) & (gate_days["date"] <= e)]
        if len(w):
            lost = int(max(w["n_gate_signals"].sum() - 5 * len(w), 0))
            log(f"  {label:14s} señales gate={w['n_gate_signals'].sum():5.0f}  perdidas por top-5={lost:5d}  ({lost / w['n_gate_signals'].sum():.0%})")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
