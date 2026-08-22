"""
PRE-REGISTRO PBO/CSCV §3.3 — momentum+RSI sobre 21 configs (Bailey et al. 2014–2017)

Implementación fiel a PRE_REGISTRO_PBO_CSCV_MOM_RSI.md §3.3 / §4 / §6:

- S = 16 particiones cronológicas → C(16,8)=12 870 splits IS/OOS (fallback S=12 si
  particiones <60 días efectivos). Cada observación pertenece a IS en la mitad
  de los splits (balanceo combinatorio, no k-fold contiguo).
- N = consumed_budget(signal_diagnosis) leído vía app.core.trial_registry
  (lista congelada §6.1 = 21 a 2026-08-22). No hardcodea Sharpe; los 21 Sharpes
  se RECALCULAN como parametrizaciones vecinas del baseline momentum+RSI
  (w_mom × RSI_band × mom_hi) sobre datos reales 2019-01-01→2026-08-04,
  universo 50 canónico (opportunities_universe.SYMBOLS). Proxy declarado §8:
  las 21 no son réplicas literales de cada diagnóstico heterogéneo (gap,
  MA200, FinBERT…); son el vecindario combinatorio del baseline — mide
  overfitting de selección en el entorno del score que sobrevivió.
- Métrica: Sharpe anualizado OOS por split (retornos mensuales netos ×√12,
  misma lógica que backtest_engine.calculate_metrics pero en panel mensual
  para costo computacional; ranking IS de las N, PBO = P(rank_OOS < mediana),
  histograma de logits = log(rel_rank/(1-rel_rank)).
- Determinista: seed 42 donde aplique, random_state=42 en HMM donde se use
  (no se usa acá, pero se fija por contrato). Enumeración combinatoria
  determinista vía itertools.combinations.
- Ventana: 2019-01-01→2026-08-04 (OHLC diario vía cache parquet, mismo universo
  50 del baseline limpio). Warmup 252d implícito en momentum_12_1; no entra al
  ranking IS/OOS.
- Costos: COST_PER_SIDE=0.0005 + slippage=0.0005 → 0.001 por lado,
  0.002 por rebalanceo completo (compra+venta), EXECUTION_LAG_DAYS=1 (señal
  cierre mes anterior → retorno mes siguiente). Mismos costos para las N.

Por qué este N=21 es el válido y el previo N=1 no:
  backend/scripts/pbo_cscv.py calcula PBO = P(sharpe_test - sharpe_train < 0)
  con UNA sola configuración y splits balanceados. El logit es ANTISIMÉTRICO
  por construcción (cada combo tiene su complementaria con signo invertido)
  → PBO converge a 0.5 SIEMPRE. No mide selección. La información ahí es
  la dispersión del logit, no el PBO. Este script con N=21 rankea 21 Sharpes
  IS y mide rank_OOS del mejor IS — ahí el logit NO es antisimétrico y el
  PBO sí informa sobre overfitting de proceso (haber mirado 21 candidatos).

Uso:
  cd backend && .venv/bin/python -m scripts.pbo_cscv_mom_rsi
Salida:
  data/cache/pbo_cscv_mom_rsi_<YYYYMMDD_HHMMSS>.txt + .json
"""
import datetime
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd

# N dinámico desde ledger (no hardcodear 21)
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.indicators import calculate_all_indicators
from app.core.trial_registry import all_trials, consumed_budget

CACHE_DIR = os.path.join("data", "cache")
OUT_DIR = os.path.join("data", "cache")

# Grid pre-registrado §39 (mismo que pbo_cscv_baseline.py) — 3×3×3=27
# El script toma los primeros N (=consumed_budget) de este grid ordenado
# lexicográficamente. Garantiza determinismo y que el ACTUAL esté incluido.
W_MOM_GRID = [0.50, 0.664, 0.80]  # ACTUAL = 0.664 (IC-derived)
RSI_BAND_GRID = [(40, 65), (45, 70), (50, 75)]  # ACTUAL = (45,70)
MOM_HI_GRID = [75.0, 100.0, 125.0]  # ACTUAL = 100 (piso -50 fijo)

S_DEFAULT = 16
S_FALLBACK = 12
ENTRY_THRESHOLD = 0.6
COST_PER_SIDE = 0.0005
SLIPPAGE = 0.0005
COST_PER_REBALANCE = 2 * (COST_PER_SIDE + SLIPPAGE)  # 0.002 por mes con posición
MIN_PARTITION_DAYS = 60
MIN_T_MONTHS = 72  # ventana pre-registrada 2019→2026 = 92 meses; tras truncar a múltiplo de 16 queda 80 — suficiente para CSCV (§8: ~960 ruedas por split)
START_DATE = "2019-01-01"
END_DATE = "2026-08-04"


def load_symbol_frame(symbol: str):
    path = os.path.join(CACHE_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    df.columns = [c.lower() for c in df.columns]
    # filtrar ventana pre-registrada + warmup previo si existe
    # carga completa para indicadores; el filtrado de ranking se hace después
    df = calculate_all_indicators(df)
    if len(df) == 0:
        return None
    return df


def build_monthly_panels():
    """Pivot por columna-indicador: filas = últimos días de trading de cada mes,
    columnas = símbolos. Filtra ventana START→END para Sharpe."""
    frames = []
    for sym in SYMBOLS:
        df = load_symbol_frame(sym)
        if df is None or len(df) < 300:
            continue
        df = df.copy()
        df["symbol"] = sym
        # recortar a ventana + warmup (momentum_12_1 necesita 252d previos)
        # mantenemos desde 2016 para warmup, luego filtramos meses
        df = df[(df.index >= "2016-01-01") & (df.index <= END_DATE)]
        frames.append(df)
    if not frames:
        raise RuntimeError("No se pudo cargar ningún símbolo del universo 50")
    all_df = pd.concat(frames)
    all_df["ym"] = all_df.index.to_period("M")
    last = all_df.groupby(["symbol", "ym"]).tail(1)
    panels = {}
    for col in ("close", "ema50", "ema200", "adx14", "rsi14", "volume_ratio", "momentum_12_1"):
        piv = last.pivot(index="ym", columns="symbol", values=col).sort_index()
        # filtrar meses a ventana pre-registrada
        piv = piv[(piv.index >= pd.Period(START_DATE, freq="M")) & (piv.index <= pd.Period(END_DATE, freq="M"))]
        panels[col] = piv
    return panels


def config_monthly_returns(panels, w_mom, band_lo, band_hi, mom_hi):
    """Retornos mensuales netos de UNA configuración (serie T mensual)."""
    close, ema50, ema200 = panels["close"], panels["ema50"], panels["ema200"]
    adx, rsi, vr, mom = panels["adx14"], panels["rsi14"], panels["volume_ratio"], panels["momentum_12_1"]

    momentum_score = ((mom + 50.0) / (mom_hi + 50.0)).clip(0.0, 1.0)
    rsi_score = pd.DataFrame(
        np.where((rsi > band_lo) & (rsi < band_hi), 0.8, 0.4),
        index=rsi.index, columns=rsi.columns,
    )
    overall = w_mom * momentum_score + (1.0 - w_mom) * rsi_score

    eligible = ((close > ema50) & (ema50 > ema200) & (adx >= 20) & (rsi > 40) & (rsi < 75) & (vr >= 1.0))
    signal = eligible & (overall >= ENTRY_THRESHOLD)

    rets = close.pct_change()  # retorno mes m (close[m-1] -> close[m])
    sel_prev = signal.shift(1)  # señal decidida al cierre del mes anterior (lag 1)

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
    net = gross - np.where(has_pos, COST_PER_REBALANCE, 0.0)
    net = pd.Series(net, index=rets.index)
    # pandas 2.0: attrs no propaga bien con infer_objects; usar objeto simple
    net.attrs["n_signals"] = np.array(n_sig_rows)
    return net


def ann_sharpe_monthly(x):
    sd = x.std(ddof=1)
    if not np.isfinite(sd) or sd <= 0 or len(x) < 3:
        return float("nan")
    return float(x.mean() / sd * np.sqrt(12))


def choose_S(T_total):
    # T_total en meses; cada mes ≈21 ruedas
    for S in (S_DEFAULT, S_FALLBACK):
        B = T_total // S
        if B == 0:
            continue
        days_per_partition = B * 21
        if days_per_partition >= MIN_PARTITION_DAYS:
            return S
    return S_FALLBACK


def main():
    t0 = datetime.datetime.now()
    # determinismo
    np.random.seed(42)

    # N dinámico desde ledger
    try:
        n_ledger = consumed_budget("signal_diagnosis")
    except Exception as e:
        print(f"[error] no se pudo leer ledger: {e}", file=sys.stderr)
        n_ledger = 21
    entries = [e for e in all_trials() if e["familia"] == "signal_diagnosis"]
    ledger_ids = [e["id"] for e in entries]
    N = int(n_ledger) if n_ledger > 0 else 21
    # Enforce mínimo 2 para PBO con selección
    if N < 2:
        print(f"[warn] N={N} ledger signal_diagnosis <2 → usando N=2 mínimo para PBO con selección", file=sys.stderr)
        N = 2

    print(f"Universo: {len(SYMBOLS)} símbolos (canónico opportunities_universe.py)")
    print(f"Ventana: {START_DATE} → {END_DATE} | Costos: {COST_PER_SIDE}+{SLIPPAGE} por lado (rebalance {COST_PER_REBALANCE})")
    print(f"Ledger signal_diagnosis: consumed_budget={n_ledger} → N={N} (ids: {', '.join(ledger_ids[:5])}...)")
    print("Cargando paneles mensuales desde cache...", flush=True)
    panels = build_monthly_panels()
    # sanity universo
    n_symbols_loaded = len(panels["close"].columns)
    print(f"  símbolos con datos: {n_symbols_loaded} | meses: {len(panels['close'])} ({panels['close'].index[0]} → {panels['close'].index[-1]})")

    # Construir grid completo y tomar N
    all_configs = [(w, lo, hi, mh) for w in W_MOM_GRID for (lo, hi) in RSI_BAND_GRID for mh in MOM_HI_GRID]
    # Orden determinista ya lexicográfico por construcción
    configs = all_configs[:N]
    # Garantizar que el ACTUAL esté incluido (si N recorta el grid y lo deja afuera, reemplazar último)
    actual_cfg = (0.664, 45, 70, 100.0)
    if actual_cfg not in configs:
        configs[-1] = actual_cfg
        print(f"  [ajuste] actual {actual_cfg} forzado al final del grid para N={N}")

    actual_idx = configs.index(actual_cfg) if actual_cfg in configs else -1

    series, sig_counts = [], []
    for cfg in configs:
        s = config_monthly_returns(panels, *cfg)
        series.append(s.values)
        sig_counts.append(np.array(s.attrs["n_signals"]))
    M = np.vstack(series)  # N x T_total
    labels = [f"w={w:.3f} band=({lo},{hi}) hi={mh:g}" for (w, lo, hi, mh) in configs]
    # etiquetas enriquecidas con ids del ledger para trazabilidad §6.1
    # si N <= len(ledger_ids), asignar 1:1 en orden de registro; si no, reciclar
    ledger_labels = []
    for i, cfg_label in enumerate(labels):
        lid = ledger_ids[i] if i < len(ledger_ids) else f"cfg_{i:02d}"
        ledger_labels.append(f"{lid} | {cfg_label}")

    T_total = M.shape[1]
    S = choose_S(T_total)
    # truncar al múltiplo de S reteniendo meses más recientes (§39)
    T = (T_total // S) * S
    if T < T_total:
        print(f"  truncando T_total={T_total} → T={T} (múltiplo de S={S}, reteniendo meses recientes)")
    M = M[:, -T:]
    sig_counts = [c[-T:] for c in sig_counts]
    months = [str(p) for p in panels["close"].index[-T:]]

    # checks fidelidad (§39)
    if actual_idx >= 0:
        act = M[actual_idx]
        act_sig = sig_counts[actual_idx]
        n_active = float((act_sig > 0).mean()) if len(act_sig) else 0.0
        gross_mean_ex_costs = float(act.mean() + COST_PER_REBALANCE * n_active) if len(act) else 0.0
    else:
        n_active = 0.0
        gross_mean_ex_costs = 0.0
        act_sig = np.array([])
    checks = {
        "T_total": int(T_total),
        "T_final": int(T),
        "S_elegido": int(S),
        "T_ge_min": bool(T >= MIN_T_MONTHS),
        "fallback_usado": bool(S == S_FALLBACK),
        "n_symbols_loaded": int(n_symbols_loaded),
        "universo_esperado": 50,
        "universo_ok": bool(n_symbols_loaded >= 45),
        "cobertura_actual": {
            "meses_con_senal": int((act_sig > 0).sum()) if len(act_sig) else 0,
            "ratio": round(n_active, 4),
            "ge_30pct": bool(n_active >= 0.30),
        },
        "edge_positivo_sin_costos": {
            "mean_mensual_ex_costos": round(gross_mean_ex_costs, 6),
            "positivo": bool(gross_mean_ex_costs > 0),
        },
        "costos": {"per_side": COST_PER_SIDE, "slippage": SLIPPAGE, "per_rebalance": COST_PER_REBALANCE},
        "ventana": f"{START_DATE}→{END_DATE}",
    }
    fidelity_ok = bool(checks["T_ge_min"] and checks["cobertura_actual"]["ge_30pct"] and checks["edge_positivo_sin_costos"]["positivo"] and checks["universo_ok"])
    if not fidelity_ok:
        print("[warn] checks de fidelidad no pasaron — la corrida sigue pero artefacto marca FIDELIDAD FALLIDA", file=sys.stderr)

    # CSCV: agregación por bloques para Sharpe de cualquier unión O(1)
    B = T // S
    # blk_sum shape S x N : suma de retornos por bloque y config
    # M is N x T, we want per block sums
    blk_sum = np.stack([M[:, i * B:(i + 1) * B].sum(axis=1) for i in range(S)])  # S x N
    blk_sumsq = np.stack([np.square(M[:, i * B:(i + 1) * B]).sum(axis=1) for i in range(S)])  # S x N
    # transpose to N x S for easier indexing per config? keep as S x N, sum over blocks axis 0
    N_CFG = len(configs)

    def sharpe_of_blockset(block_ids):
        """block_ids: iterable de índices de bloques (0..S-1). Retorna array N con Sharpe mensual anualizado."""
        ids = list(block_ids)
        n = B * len(ids)
        if n < 3:
            return np.full(N_CFG, np.nan)
        # sum over selected blocks
        s = blk_sum[ids, :].sum(axis=0)  # N
        q = blk_sumsq[ids, :].sum(axis=0)  # N
        mean = s / n
        # var = (q - n*mean^2)/(n-1)
        var = (q - n * mean ** 2) / (n - 1)
        # clamp
        var = np.maximum(var, 1e-18)
        sd = np.sqrt(var)
        # handle sd=0 or inf
        sharpe = np.where(sd > 0, mean / sd * np.sqrt(12.0), 0.0)
        # where var originally zero due to constant series, sharpe 0
        return sharpe

    # Enumerar C(S, S/2) combos
    combos = list(itertools.combinations(range(S), S // 2))
    n_combos = len(combos)
    print(f"Bloques S={S} de {B} meses (~{B*21} ruedas) | Combinaciones C({S},{S//2})={n_combos}")

    lambdas = []
    perf_degradations = []
    rank_is_best_oos = []
    spearman_rhos = []

    for train_ids in combos:
        test_ids = tuple(i for i in range(S) if i not in train_ids)
        is_sh = sharpe_of_blockset(train_ids)
        oos_sh = sharpe_of_blockset(test_ids)
        # ranking IS: mejor IS
        # handle nan: nan argmax would be 0; mask nans to -inf
        is_sh_for_rank = np.where(np.isfinite(is_sh), is_sh, -1e9)
        oos_sh_for_rank = np.where(np.isfinite(oos_sh), oos_sh, -1e9)
        best_is = int(np.argmax(is_sh_for_rank))
        # rank OOS del best_is (1 = peor, N = mejor)
        # usar rank average como en baseline
        # pandas rank
        ranks = pd.Series(oos_sh_for_rank).rank(method="average").values  # 1..N
        rank_oos = float(ranks[best_is])
        rel_rank = (rank_oos - 1) / max(N_CFG - 1, 1)
        w = min(max(rel_rank, 1e-9), 1.0 - 1e-9)
        lam = float(np.log(w / (1.0 - w)))
        lambdas.append(lam)
        rank_is_best_oos.append(rank_oos)
        # perf degradation: Sharpe_OOS(best) - Sharpe_IS(best) (para ese best)
        deg = float(oos_sh[best_is] - is_sh[best_is]) if np.isfinite(oos_sh[best_is]) and np.isfinite(is_sh[best_is]) else float("nan")
        perf_degradations.append(deg)
        # spearman IS vs OOS (para diagnóstico de estabilidad)
        # compute rho
        if np.isfinite(is_sh).sum() > 2 and np.isfinite(oos_sh).sum() > 2:
            # use spearman via rank correlation
            try:
                rho = float(pd.Series(is_sh_for_rank).corr(pd.Series(oos_sh_for_rank), method="spearman"))
            except Exception:
                rho = float("nan")
        else:
            rho = float("nan")
        spearman_rhos.append(rho)

    lam = np.array(lambdas)
    pbo = float((lam <= 0).mean()) if len(lam) else float("nan")
    # histogram stats
    hist = {
        "p5": float(np.percentile(lam, 5)) if len(lam) else float("nan"),
        "p25": float(np.percentile(lam, 25)) if len(lam) else float("nan"),
        "p50": float(np.median(lam)) if len(lam) else float("nan"),
        "p75": float(np.percentile(lam, 75)) if len(lam) else float("nan"),
        "p95": float(np.percentile(lam, 95)) if len(lam) else float("nan"),
        "mean": float(np.mean(lam)) if len(lam) else float("nan"),
        "std": float(np.std(lam, ddof=1)) if len(lam) > 1 else float("nan"),
    }
    # full-period Sharpes
    full_sharpes = [ann_sharpe_monthly(M[i]) for i in range(N_CFG)]
    # rank actual full period
    if actual_idx >= 0 and np.isfinite(full_sharpes[actual_idx]):
        rank_actual = 1 + sum(1 for i in range(N_CFG) if (full_sharpes[i] is not None and np.isfinite(full_sharpes[i]) and full_sharpes[i] > full_sharpes[actual_idx]))
    else:
        rank_actual = None

    # median degradation and spearman median
    perf_deg_median = float(np.nanmedian(perf_degradations)) if len(perf_degradations) else float("nan")
    perf_deg_p5 = float(np.nanpercentile(perf_degradations, 5)) if len(perf_degradations) else float("nan")
    spearman_median = float(np.nanmedian(spearman_rhos)) if len(spearman_rhos) else float("nan")

    # criterio §4 pre-registrado
    if pbo < 0.10:
        bucket = "CUMPLE"
        verdict = "NO OVERFITTING de proceso — ranking IS informativo (PBO<0.10 estricto)"
        verdict_bin = "CUMPLE"
    elif pbo < 0.20:
        bucket = "gris"
        verdict = "ZONA GRIS 0.10-0.20 — no se declara artefacto pero no se afirma robustez; exige evidencia adicional (gris → NO_CUMPLE binario)"
        verdict_bin = "NO_CUMPLE"
    else:
        bucket = "overfitting"
        verdict = "OVERFITTING de proceso — NO_CUMPLE (PBO≥0.20, selección no mejor que azar)"
        verdict_bin = "NO_CUMPLE"
    if pbo >= 0.30:
        verdict += " | OVERFITTING sustancial (≥0.30)"

    # Construir artefacto txt
    lines = []
    out = lines.append
    out("=" * 78)
    out("PRE-REGISTRO PBO/CSCV §3.3 — momentum+RSI sobre N configs (Bailey et al.)")
    out(f"Generado: {t0:%Y-%m-%d %H:%M:%S} → {datetime.datetime.now():%Y-%m-%d %H:%M:%S} | Duración: {(datetime.datetime.now()-t0).total_seconds():.1f}s")
    out(f"Universo: {n_symbols_loaded} símbolos (esperado 50) | Ventana: {START_DATE}→{END_DATE} | Costos: {COST_PER_SIDE}+{SLIPPAGE} por lado")
    out(f"N (ledger signal_diagnosis): {N} (consumed_budget={n_ledger}) | S={S} bloques de {B} meses (~{B*21} ruedas) | Combinaciones: {n_combos}")
    out(f"Meses: {T} ({months[0]} → {months[-1]}) | T_total={T_total} | Costo rebalance: {COST_PER_REBALANCE}")
    out("=" * 78)
    out("")
    out("--- N configs (grid vecino del baseline, §6.1 proxy — limitación §8 heterogeneidad) ---")
    for i, (lbl, sh) in enumerate(zip(ledger_labels, full_sharpes)):
        mark = "  <== ACTUAL (w=0.664 band 45-70 hi=100)" if i == actual_idx else ""
        sh_str = f"{sh:+.3f}" if np.isfinite(sh) else "nan"
        out(f"  {i+1:02d}. {lbl:55s} Sharpe_full={sh_str}{mark}")
    if rank_actual is not None:
        out(f"  Rank ACTUAL entre {N_CFG} (full period): {rank_actual} (1=mejor)")
    out("")
    out("--- Checks de fidelidad (pre-registrados §39; fallar alguno invalida) ---")
    for k, v in checks.items():
        out(f"  {k}: {v}")
    out(f"  FIDELIDAD GLOBAL: {'OK' if fidelity_ok else 'FALLIDA — corrida no interpretable como PBO válido'}")
    out("")
    out("--- Resultado primario (§4) ---")
    out(f"  PBO = {pbo:.4f}  ({int(round(pbo * len(lam)))}/{len(lam)} combos con λ≤0)")
    out(f"  λ (logit rank_OOS): media={hist['mean']:+.3f} mediana={hist['p50']:+.3f} "
        f"p5={hist['p5']:+.3f} p25={hist['p25']:+.3f} p75={hist['p75']:+.3f} p95={hist['p95']:+.3f} std={hist['std']:.3f}")
    out(f"  Degradación Sharpe_OOS - Sharpe_IS (del best IS): mediana={perf_deg_median:+.3f} p5={perf_deg_p5:+.3f}")
    out(f"  Estabilidad rank IS vs OOS (Spearman): mediana rho={spearman_median:+.3f}")
    out("  Buckets §4: <0.10 CUMPLE | 0.10-0.20 gris (binario NO_CUMPLE) | ≥0.20 NO_CUMPLE | ≥0.30 sustancial")
    out(f"  VEREDICTO (§4 mecánico): {verdict}")
    out(f"  VEREDICTO BINARIO ledger (PBO<0.10): {verdict_bin}")
    out(f"  Bucket: {bucket}")
    out("")
    out("--- Por qué N=1 PBO=0.5 no mide selección (advertencia metodológica) ---")
    out("  backend/scripts/pbo_cscv.py con UNA config y splits balanceados tiene logit")
    out("  ANTISIMÉTRICO por construcción (cada combo tiene su complementaria con signo")
    out("  invertido) → PBO=0.5 SIEMPRE. No es '50% overfitting', es el NULO de")
    out("  selección. Este N=21 SÍ mide selección: el logit ya no es antisimétrico,")
    out("  PBO informa P(rank_OOS < mediana) del mejor IS entre 21.")
    out("")
    out("--- Secundarios ---")
    out("  Histograma logits (λ):")
    for q in [5, 25, 50, 75, 95]:
        out(f"    p{q}: {np.percentile(lam, q):+.4f}")
    out(f"    media: {np.mean(lam):+.4f} | desv: {np.std(lam, ddof=1):.4f}")
    out(f"  Rank_OOS del best IS: mediana={np.median(rank_is_best_oos):.1f} (mediana teórica N/2={(N+1)/2:.1f})")
    out(f"  P(rank_OOS < mediana N/2): {pbo:.4f}  [=PBO]")
    out("")
    out("--- Limitaciones declaradas ANTES de correr (§8) ---")
    out("  1. Heterogeneidad: las 21 del ledger son 21 familias distintas (gap, MA200,")
    out("     FinBERT, OFI, CVD...), no 21 parametrizaciones del mismo modelo. Este")
    out("     proxy de 21 parametrizaciones vecinas del baseline (w_mom×RSI×mom_hi)")
    out("     asume estrategias comparables rankeadas por mismo Sharpe. Es aproximación")
    out("     declarada; la alternativa limpia (reconstruir las 21 como backtests con")
    out("     backtest_engine.run) queda para slot futuro si se exige fidelidad total.")
    out("  2. Autocorrelación y tamaño IS/OOS: cada split IS/OOS ≈ T/2 meses (~45 meses)")
    out("     → Sharpe por split con SE ≈0.15 (mensual). Suficiente pero ruidoso.")
    out("  3. Costos y ejecución: 0.002 por rebalanceo mensual, lag 1 ya incorporado vía")
    out("     signal.shift(1). Todas las N con mismos costos — PBO mide selección, no")
    out("     sensibilidad a costos.")
    out("  4. Lookahead del baseline: el baseline se calibró con datos 2019-2026; las")
    out("     particiones reutilizan esos datos. PBO mide selección entre 21 tal como")
    out("     existen hoy, no pureza del baseline aislado.")
    out("")
    out("--- Reproducción ---")
    out(f"  Seed: 42 | S={S} | N={N} | n_combos={n_combos} | random_state=42 (donde aplique)")
    out(f"  Ledger ids: {', '.join(ledger_ids)}")
    out("  Out: data/cache/pbo_cscv_mom_rsi_<ts>.txt/.json")

    txt = "\n".join(lines) + "\n"
    os.makedirs(OUT_DIR, exist_ok=True)
    ts = f"{datetime.datetime.now():%Y%m%d_%H%M%S}"
    txt_path = os.path.join(OUT_DIR, f"pbo_cscv_mom_rsi_{ts}.txt")
    json_path = txt_path.replace(".txt", ".json")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(txt)
    # JSON con campos requeridos
    payload = {
        "pbo": float(pbo),
        "pbo_bucket": bucket,
        "veredicto": verdict,
        "veredicto_binario": verdict_bin,
        "umbral_aplicado": "PBO<0.10 (Bailey et al.)",
        "histograma_logits": hist,
        "logits": [float(x) for x in lam.tolist()],
        "sharpe_is_rank1_median": None,  # no single IS rank1 sharpe; se reporta distribución
        "perf_degradation_median": float(perf_deg_median),
        "perf_degradation_p5": float(perf_deg_p5),
        "spearman_median": float(spearman_median),
        "S": int(S),
        "N": int(N_CFG),
        "n_splits": int(n_combos),
        "T_meses": int(T),
        "T_total_meses": int(T_total),
        "B_meses_por_bloque": int(B),
        "months": months,
        "configs": ledger_labels,
        "full_sharpes": [float(x) if np.isfinite(x) else None for x in full_sharpes],
        "actual_idx": int(actual_idx) if actual_idx >= 0 else None,
        "rank_actual_full": int(rank_actual) if rank_actual is not None else None,
        "checks": checks,
        "fidelity_ok": bool(fidelity_ok),
        "ledger_ids": ledger_ids,
        "timestamp": ts,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "cost_per_side": COST_PER_SIDE,
        "slippage": SLIPPAGE,
        "cost_per_rebalance": COST_PER_REBALANCE,
        "seed": 42,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(txt)
    print(f"\nOut: {txt_path}")
    print(f"Out: {json_path}")
    # also log why N=1 invalid
    print("\n[nota] N=1 PBO=0.5 de pbo_cscv.py es NULO por antisimétria — este N=21 SÍ mide selección.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
