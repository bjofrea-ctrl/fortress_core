"""
TEST OOS 2025-2026 — SPEC CONGELADA (pre-registrada en PLAN_SENTIMIENTO.md §7).

NO EDITAR ESTE ARCHIVO DESPUÉS DE LA PRIMERA CORRIDA: se corre UNA vez.
Cualquier re-test (0.60/0.70, ventanas distintas, métricas nuevas) invalida
la naturaleza out-of-sample del test.

Diferencias declaradas vs el diagnóstico IS (diagnose_sentiment_ic.py):
- Ranking causal: percentil ROLLING de 260 días por símbolo (el rank global
  del IS mira toda la muestra; en OOS sería lookahead). Declarado ANTES
  de correr.
- Evaluación SOLO en registros con fecha >= 2025-01-01 (warmup de indicadores
  desde 2024-01-01).
- Peso V1 = 0.50 FIJO (V1_DOMINANCE), sin barrido. Señal V1 = -rank(aaii).
- Significancia del diff de Brier: Diebold-Mariano con varianza Newey-West
  (lag = ceil(horizon/stride)).

Criterio pre-registrado (PLAN_SENTIMIENTO.md §7):
- CONFIRMA: IC(AAII) < 0 (dirección correcta) Y G2/50 gana Brier en >=3/4
  horizontes -> integrar V1 con 0.50.
- DIRECCIÓN SOLA: IC correcto pero <3/4 -> integrar, peso a discutir (30-50%).
- NO CONFIRMA: reportar tal cual, NO re-testar.
"""
import os
import math
import datetime

import pandas as pd
import numpy as np

from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.predictive_indicators import calculate_predictive_indicators
from app.core.market_sentiment import build_sentiment_frame
from app.core.probabilistic_engine import SignalQualityMetrics

HORIZONS = [5, 20, 60]
STRIDE_DAYS = 5
SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
WARMUP_DAYS = 260
RANK_WINDOW = 260
V1_DOMINANCE = 0.50
OOS_START = "2025-01-01"
DATA_START = "2024-01-01"
DATA_END = "2026-08-09"

SENTIMENT_COLS = [
    "cot_lev_net_pct",
    "cot_asset_net_pct",
    "cot_retail_net_pct",
    "cot_dealer_net_pct",
    "walcl_growth_w",
    "wresbal_growth_w",
    "aaii_bullbear_spread",
]


def build_full_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    with_base = calculate_all_indicators(d)
    for col in with_base.columns:
        if col not in d.columns:
            d[col] = with_base[col]
    d = calculate_predictive_indicators(d)
    return d.dropna(subset=["close"])


def significance_threshold(n: int) -> float:
    return 2.0 / np.sqrt(n)


def newey_west_neff(records: pd.DataFrame, col: str, horizon: int) -> float:
    """n_eff Newey-West (igual que el IS) para el t-stat del IC."""
    fwd_col = f"fwd_{horizon}"
    L = int(np.ceil(horizon / STRIDE_DAYS))
    total = 0.0
    for _, sub in records.groupby("symbol"):
        sub = sub.dropna(subset=[col, fwd_col])
        if len(sub) < 30:
            continue
        x = sub[col].to_numpy()
        y = sub[fwd_col].to_numpy()
        z = (x - x.mean()) * (y - y.mean())
        n = len(z)
        lag_max = min(L, n - 2)
        if lag_max < 1:
            total += n
            continue
        rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
        rho = np.nan_to_num(rho, nan=0.0)
        w = 1 - np.arange(1, len(rho) + 1) / (L + 1)
        denom = 1 + 2 * np.sum(w * rho)
        total += n / max(denom, 1 + L)
    return max(total, 30.0)


def _norm_pvalue(z: float) -> float:
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def diebold_mariano_nw(p1: np.ndarray, p2: np.ndarray, y: np.ndarray, horizon: int) -> float:
    d = (p1 - y) ** 2 - (p2 - y) ** 2
    n = len(d)
    if n < 30:
        return 1.0
    dbar = float(d.mean())
    L = int(np.ceil(horizon / STRIDE_DAYS))
    lag_max = min(L, n - 2)
    gamma0 = float(np.mean((d - dbar) ** 2))
    if gamma0 <= 0:
        return 1.0
    var = gamma0
    for j in range(1, lag_max + 1):
        gamma_j = float(np.mean((d[:-j] - dbar) * (d[j:] - dbar)))
        var += 2 * (1 - j / (L + 1)) * gamma_j
    if var <= 0:
        return 1.0
    return _norm_pvalue(dbar / np.sqrt(var / n))


def rolling_rank01(s: pd.Series) -> pd.Series:
    """Percentil rolling causal en [-1,1]: rank del valor actual dentro de la
    ventana de RANK_WINDOW días anteriores (inclusive). Sin lookahead."""
    def _pct(w):
        return 2.0 * (w <= w[-1]).mean() - 1.0

    return s.rolling(RANK_WINDOW, min_periods=60).apply(_pct, raw=True).fillna(0.0)


def collect_records(price_data: dict, sentiment: pd.DataFrame) -> pd.DataFrame:
    records = []
    for symbol in SYMBOLS:
        df = price_data.get(symbol)
        if df is None:
            continue
        n = len(df)
        if n < WARMUP_DAYS + max(HORIZONS):
            continue
        sent = sentiment.reindex(df.index)
        for i in range(WARMUP_DAYS, n - max(HORIZONS), STRIDE_DAYS):
            date = df.index[i]
            if date < pd.Timestamp(OOS_START):
                continue
            if date not in sentiment.index:
                continue
            row = {"symbol": symbol}
            for col in SENTIMENT_COLS:
                row[col] = sent.loc[date, col]
            row["rsi14"] = df["rsi14"].iloc[i]
            row["momentum_12_1"] = df["momentum_12_1"].iloc[i] if "momentum_12_1" in df else np.nan
            row["er20"] = df["er20"].iloc[i]
            entry = df["close"].iloc[i]
            for h in HORIZONS + [1]:
                row[f"fwd_{h}"] = df["close"].iloc[i + h] / entry - 1
            records.append(row)
    return pd.DataFrame(records)


def main():
    out_path = os.path.join("data", "cache", f"oos_result_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as f:
            f.write(msg + "\n")

    log("=" * 72)
    log("OOS 2025-2026 — SPEC CONGELADA (UNA corrida, no se re-testa)")
    log(f"Peso V1: {V1_DOMINANCE} fijo | ranking: rolling {RANK_WINDOW}d causal | evaluacion >= {OOS_START}")
    log("=" * 72)

    price_data = load_universe(SYMBOLS, DATA_START, DATA_END)
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}
    trading_dates = indicators_cache["SPY"].index
    sentiment = build_sentiment_frame(trading_dates)
    records = collect_records(indicators_cache, sentiment)
    log(f"Registros OOS: {len(records)} (rango {OOS_START} a 2026-08)")

    # --- IC univariado con n_eff ---
    for horizon in HORIZONS:
        fwd = records[f"fwd_{horizon}"]
        log(f"\n  IC univariado {horizon}d (n={len(records)}, base_ret={fwd.mean():+.4f}):")
        log(f"    {'col':22s} {'ic':>8s} {'rank_ic':>8s} {'n':>6s} {'n_eff':>7s} {'sig':>5s}")
        for col in SENTIMENT_COLS:
            values = records[col]
            mask = values.notna()
            if mask.sum() < 50:
                log(f"    {col:22s}  n={mask.sum()} insuficiente")
                continue
            ic = SignalQualityMetrics.compute_ic(values[mask], fwd[mask])
            rank_ic = SignalQualityMetrics.compute_rank_ic(values[mask], fwd[mask])
            n_eff = newey_west_neff(records, col, horizon)
            thresh = significance_threshold(n_eff)
            sig = " ***" if abs(ic) > thresh else ""
            log(f"    {col:22s} {ic:+8.4f} {rank_ic:+8.4f} {mask.sum():6d} {n_eff:7.0f}{sig}")

    # --- H7 bloque: G1 vs G2/50 ---
    engine_w = {"momentum_12_1": 0.35, "rsi14": 0.10, "walcl_growth_w": 0.05, "cot_retail_net_pct": 0.10}
    tot = sum(engine_w.values())
    w1 = {k: v / tot for k, v in engine_w.items()}

    sub = records[["momentum_12_1", "rsi14", "walcl_growth_w", "cot_retail_net_pct", "aaii_bullbear_spread"] + [f"fwd_{h}" for h in HORIZONS + [1]]].copy()
    s_mom = rolling_rank01(sub["momentum_12_1"])
    s_rsi = -rolling_rank01(sub["rsi14"])
    s_liq = rolling_rank01(sub["walcl_growth_w"])
    s_ret = rolling_rank01(sub["cot_retail_net_pct"])
    s_v1 = -rolling_rank01(sub["aaii_bullbear_spread"])
    score1 = w1["momentum_12_1"] * s_mom + w1["rsi14"] * s_rsi + w1["walcl_growth_w"] * s_liq + w1["cot_retail_net_pct"] * s_ret
    score2 = (1 - V1_DOMINANCE) * score1 + V1_DOMINANCE * s_v1

    log("\n" + "=" * 72)
    log("[H7-OOS] PRUEBA DE BLOQUES — V1 0.50 fijo vs baseline")
    log(f"    {'horizon':8s} {'grupo':9s} {'brier':>7s} {'acc_dir':>8s} {'ic_score':>9s} {'dm_p':>7s} {'n':>6s}")

    wins = 0
    sig_cnt = 0
    n_h = 0
    ic_aaii = {}
    for h in HORIZONS + [1]:
        fwd = sub[f"fwd_{h}"]
        mask = fwd.notna()
        if mask.sum() < 50:
            continue
        n_h += 1
        y = (fwd[mask] > 0).astype(float).to_numpy()
        rows = []
        for label, score in [("G1", score1), ("G2/50", score2)]:
            s = score[mask].to_numpy()
            p = 1.0 / (1.0 + np.exp(-1.5 * s))
            brier = float(((p - y) ** 2).mean())
            acc = float(((s > 0) == (fwd[mask].to_numpy() > 0)).mean())
            ic = SignalQualityMetrics.compute_ic(pd.Series(s), fwd[mask])
            rows.append((label, brier, acc, ic))
        p1 = 1.0 / (1.0 + np.exp(-1.5 * score1[mask].to_numpy()))
        p2 = 1.0 / (1.0 + np.exp(-1.5 * score2[mask].to_numpy()))
        dm_p = diebold_mariano_nw(p1, p2, y, h)
        if h in HORIZONS:
            aaii_mask = sub["aaii_bullbear_spread"].notna() & fwd.notna()
            ic_aaii[h] = SignalQualityMetrics.compute_ic(sub.loc[aaii_mask, "aaii_bullbear_spread"], fwd[aaii_mask])
        for label, brier, acc, ic in rows:
            log(f"    {h:8d} {label:9s} {brier:.4f} {acc:.4f} {ic:+9.4f} {dm_p:7.3f} {int(mask.sum()):6d}")
        if rows[1][1] < rows[0][1]:
            wins += 1
        if dm_p < 0.05:
            sig_cnt += 1

    ic_ok = all(v < 0 for v in ic_aaii.values())
    log(f"\n    IC(AAII) por horizonte: {', '.join(f'{h}d={v:+.4f}' for h, v in ic_aaii.items())} -> direccion {'OK (<0)' if ic_ok else 'MAL'}")
    log(f"    G2/50 gana Brier en {wins}/{n_h} horizontes; DM p<0.05 en {sig_cnt}/{n_h}")
    if ic_ok and wins >= 3:
        log("    VEREDICTO OOS: CONFIRMA -> integrar V1 con 0.50")
    elif ic_ok:
        log("    VEREDICTO OOS: DIRECCION SOLA -> integrar, peso a discutir (30-50%)")
    else:
        log("    VEREDICTO OOS: NO CONFIRMA -> reportar tal cual, no re-testar")
    log(f"\nResultado guardado en {out_path}")


if __name__ == "__main__":
    main()
