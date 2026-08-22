"""
§39 PLAN_MEJORA_MATEMATICA.md — PBO vía CSCV del baseline momentum+RSI.

Auditoría de proceso (NO trial, NO consume ledger): mide si el score
momentum+RSI del motor es un artefacto de selección entre configuraciones
vecinas, siguiendo Bailey/Borwein/López de Prado/Zhu (2017) — Combinatorially
Symmetric Cross-Validation.

PRE-REGISTRO: §39 fue escrito ANTES de correr este script. Criterio:
  PBO ≤ 0.20 bajo · 0.20–0.50 intermedio · > 0.50 alto (sin revocación automática).

Aproximación declarada en el pre-registro: portafolio equal-weight mensual
reconstruido vectorialmente con los gates EXACTOS del motor, SIN stops/barriers/
regime-gating — mide el edge del score, no el backtest completo.

Uso: cd backend && .venv/bin/python -m scripts.pbo_cscv_baseline
Output: data/cache/pbo_cscv_baseline_<ts>.txt (+ .json)
"""
import datetime
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.indicators import calculate_all_indicators

CACHE_DIR = os.path.join("data", "cache")
OUT_DIR = os.path.join("data", "cache")

# --- Familia de configuraciones (pre-registrada en §39) ---------------------
W_MOM_GRID = [0.50, 0.664, 0.80]          # ACTUAL = 0.664 (IC-derived)
RSI_BAND_GRID = [(40, 65), (45, 70), (50, 75)]  # ACTUAL = (45, 70)
MOM_HI_GRID = [75.0, 100.0, 125.0]        # ACTUAL = 100 (piso -50 fijo)

S_BLOCKS = 16
ENTRY_THRESHOLD = 0.6                     # umbral real de generate_signal
COST_PER_REBALANCE = 2 * (0.001 + 0.0005) # 2 lados x (comision + slippage)
MIN_T = 96                                # check fidelidad


def load_symbol_frame(symbol):
    path = os.path.join(CACHE_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    df.columns = [c.lower() for c in df.columns]
    df = calculate_all_indicators(df)
    if len(df) == 0:
        return None
    return df


def build_monthly_panels():
    """Pivot por columna-indicador: filas = últimos días de trading de cada mes,
    columnas = símbolos."""
    frames = []
    for sym in SYMBOLS:
        df = load_symbol_frame(sym)
        if df is None or len(df) < 300:
            continue
        df = df.copy()
        df["symbol"] = sym
        frames.append(df)
    all_df = pd.concat(frames)
    all_df["ym"] = all_df.index.to_period("M")
    last = all_df.groupby(["symbol", "ym"]).tail(1)
    panels = {}
    for col in ("close", "ema50", "ema200", "adx14", "rsi14", "volume_ratio",
                "momentum_12_1"):
        panels[col] = last.pivot(index="ym", columns="symbol",
                                 values=col).sort_index()
    return panels


def config_matrix(panels, w_mom, band_lo, band_hi, mom_hi):
    """Retornos mensuales netos de UNA configuración (serie T)."""
    close, ema50, ema200 = panels["close"], panels["ema50"], panels["ema200"]
    adx, rsi, vr, mom = (panels["adx14"], panels["rsi14"],
                         panels["volume_ratio"], panels["momentum_12_1"])

    momentum_score = ((mom + 50.0) / (mom_hi + 50.0)).clip(0.0, 1.0)
    rsi_score = pd.DataFrame(
        np.where((rsi > band_lo) & (rsi < band_hi), 0.8, 0.4),
        index=rsi.index, columns=rsi.columns)
    overall = w_mom * momentum_score + (1.0 - w_mom) * rsi_score

    eligible = ((close > ema50) & (ema50 > ema200) & (adx >= 20)
                & (rsi > 40) & (rsi < 75) & (vr >= 1.0))
    signal = eligible & (overall >= ENTRY_THRESHOLD)

    rets = close.pct_change()      # retorno del mes m (close[m-1] -> close[m])
    sel_prev = signal.shift(1)     # señal decidida al cierre del mes anterior

    gross_rows, n_sig_rows = [], []
    for idx in rets.index:
        sel = sel_prev.loc[idx].fillna(False)
        r = rets.loc[idx][sel].dropna()
        if len(r) == 0:
            gross_rows.append(0.0)
            n_sig_rows.append(0)
        else:
            gross_rows.append(float(r.mean()))
            n_sig_rows.append(int(len(r)))
    gross = pd.Series(gross_rows, index=rets.index)
    has_pos = gross != 0.0
    net = gross - np.where(has_pos, COST_PER_REBALANCE, 0.0)  # cash si vacío
    net = pd.Series(net, index=rets.index)
    net.attrs["n_signals"] = np.array(n_sig_rows)
    return net


def ann_sharpe(x):
    sd = x.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0 or len(x) < 3:
        return float("nan")
    return float(x.mean() / sd * np.sqrt(12))


def main():
    t0 = datetime.datetime.now()
    print(f"Cargando {len(SYMBOLS)} símbolos desde cache...", flush=True)
    panels = build_monthly_panels()

    configs = [(w, lo, hi, mh)
               for w in W_MOM_GRID
               for (lo, hi) in RSI_BAND_GRID
               for mh in MOM_HI_GRID]
    actual_idx = configs.index((0.664, 45, 70, 100.0))

    series, sig_counts = [], []
    for cfg in configs:
        s = config_matrix(panels, *cfg)
        series.append(s.values)
        sig_counts.append(np.array(s.attrs["n_signals"]))
    M = np.vstack(series)  # N x T
    labels = [f"w={w:.3f} band=({lo},{hi}) hi={mh:g}"
              for (w, lo, hi, mh) in configs]

    # truncar al múltiplo de S reteniendo los meses más recientes (§39)
    T_total = M.shape[1]
    T = (T_total // S_BLOCKS) * S_BLOCKS
    M = M[:, -T:]
    sig_counts = [c[-T:] for c in sig_counts]
    months = [str(p) for p in panels["close"].index[-T:]]

    # checks de fidelidad (pre-registro §39; fallar alguno invalida la corrida)
    act = M[actual_idx]
    act_sig = sig_counts[actual_idx]
    n_active = float((act_sig > 0).mean())
    gross_mean_ex_costs = float(act.mean() + COST_PER_REBALANCE * n_active)
    checks = {
        "T_final": int(T),
        "T_ge_96": bool(T >= MIN_T),
        "cobertura_actual": {
            "meses_con_senal": int((act_sig > 0).sum()),
            "ratio": round(n_active, 4),
            "ge_30pct": bool(n_active >= 0.30),
        },
        "edge_positivo_sin_costos": {
            "mean_mensual_ex_costos": round(gross_mean_ex_costs, 6),
            "positivo": bool(gross_mean_ex_costs > 0),
        },
    }
    fidelity_ok = bool(checks["T_ge_96"]
                       and checks["cobertura_actual"]["ge_30pct"]
                       and checks["edge_positivo_sin_costos"]["positivo"])

    # CSCV — agregación por bloques: sumas => Sharpe de cualquier unión O(1)
    B = T // S_BLOCKS
    blk_sum = np.stack([M[:, i*B:(i+1)*B].sum(axis=1) for i in range(S_BLOCKS)])
    blk_sumsq = np.stack([np.square(M[:, i*B:(i+1)*B]).sum(axis=1)
                          for i in range(S_BLOCKS)])
    N_CFG = len(configs)

    def sharpe_of(block_ids):
        ids = list(block_ids)
        n = B * len(ids)
        s = blk_sum[:, ids].sum(axis=1)
        q = blk_sumsq[:, ids].sum(axis=1)
        mean = s / n
        var = (q - n * mean ** 2) / (n - 1)
        sd = np.sqrt(np.maximum(var, 1e-18))
        return mean / sd * np.sqrt(12.0)

    lambdas = []
    combos = itertools.combinations(range(S_BLOCKS), S_BLOCKS // 2)
    for train_ids in combos:
        test_ids = tuple(i for i in range(S_BLOCKS) if i not in train_ids)
        is_sh = sharpe_of(train_ids)
        oos_sh = sharpe_of(test_ids)
        best = int(np.argmax(is_sh))
        ranks = pd.Series(oos_sh).rank(method="average").values
        rel_rank = (ranks[best] - 1) / max(N_CFG - 1, 1)
        w = min(max(rel_rank, 1e-9), 1.0 - 1e-9)
        lambdas.append(np.log(w / (1.0 - w)))

    lam = np.array(lambdas)
    pbo = float((lam <= 0).mean())
    full_sharpes = [ann_sharpe(M[i]) for i in range(N_CFG)]

    # criterio pre-registrado en §39
    if pbo <= 0.20:
        bucket = "bajo"
        verdict = "BAJO — baseline parado con evidencia propia; nada cambia"
    elif pbo <= 0.50:
        bucket = "intermedio"
        verdict = "INTERMEDIO — documentado; Tarea O/P deben citarlo al evaluarse"
    else:
        bucket = "alto"
        verdict = ("ALTO — veredicto del baseline marcado no fiable por sí solo "
                   "ante el proceso selectivo; sin revocación automática")

    rank_actual = 1 + sum(1 for i in range(N_CFG)
                          if (full_sharpes[i] or -9) > (full_sharpes[actual_idx] or -9))

    lines = []
    out = lines.append
    out("=" * 78)
    out("§39 — PBO/CSCV del baseline momentum+RSI (auditoría de proceso, NO trial)")
    out(f"Generado: {t0:%Y-%m-%d %H:%M:%S} | Duración: "
        f"{(datetime.datetime.now() - t0).total_seconds():.1f}s")
    out(f"Universo: {len(panels['close'].columns)} símbolos | Meses: {T} "
        f"({months[0]} → {months[-1]}) | Configs: {N_CFG}")
    out(f"Bloques S={S_BLOCKS} de {B} meses | Combinaciones: {lam.size}")
    out("=" * 78)
    out("")
    out("--- Checks de fidelidad (pre-registrados; fallar alguno invalida) ---")
    for k, v in checks.items():
        out(f"  {k}: {v}")
    out(f"  FIDELIDAD GLOBAL: {'OK' if fidelity_ok else 'FALLIDA'}")
    out("")
    out("--- Resultado ---")
    out(f"  PBO = {pbo:.4f}  ({int(round(pbo * lam.size))}/{lam.size} combos con λ≤0)")
    out(f"  λ: media={lam.mean():+.3f} mediana={np.median(lam):+.3f} "
        f"p5={np.percentile(lam, 5):+.3f} p95={np.percentile(lam, 95):+.3f}")
    out(f"  VEREDICTO ({bucket}): {verdict}")
    out("")
    out("--- Sharpe full-período por configuración (orden descendente) ---")
    order = sorted(range(N_CFG), key=lambda i: -(full_sharpes[i] if np.isfinite(full_sharpes[i]) else -9))
    for i in order:
        mark = "  <== ACTUAL" if i == actual_idx else ""
        sh = full_sharpes[i] if np.isfinite(full_sharpes[i]) else float("nan")
        out(f"  {labels[i]:34s} Sharpe={sh:+.3f}{mark}")
    out(f"\n  Rank de la config ACTUAL entre {N_CFG}: {rank_actual}")

    os.makedirs(OUT_DIR, exist_ok=True)
    ts = f"{datetime.datetime.now():%Y%m%d_%H%M%S}"
    txt_path = os.path.join(OUT_DIR, f"pbo_cscv_baseline_{ts}.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(txt_path.replace(".txt", ".json"), "w", encoding="utf-8") as fh:
        json.dump({"pbo": pbo, "bucket": bucket, "verdict": verdict,
                   "lambda_median": float(np.median(lam)),
                   "lambda_mean": float(lam.mean()),
                   "n_combos": int(lam.size), "T": int(T),
                   "first_month": months[0], "last_month": months[-1],
                   "configs": labels, "full_sharpes": full_sharpes,
                   "actual_idx": actual_idx, "rank_actual": rank_actual,
                   "checks": checks, "fidelity_ok": fidelity_ok},
                  fh, indent=2)
    print("\n".join(lines))
    print(f"\nOut: {txt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


