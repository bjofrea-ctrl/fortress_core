"""
§43 — PBO/CSCV de FIDELIDAD COMPLETA (pre-registrado en PLAN_MEJORA_MATEMATICA.md §43,
ANTES de correr). Reconstruye los candidatos de selección como configuraciones REALES
de backtest_engine.run() (stops, regime-gating, calibrador walk-forward,
execution_lag_days=1, costos vigentes) en vez de vecinos proxy vectorizados de §40.

N=9 configuraciones ejecutables (mapeo honesto §43.1-§43.2, congelado):
un-eje-a-la-vez alrededor del baseline ACTUAL + alternativa ADX-in-blend (§0.5a)
+ horizonte de calibración 10d (auditoría M1).

SIN tocar signal_engine.py ni backtest_engine.py: subclasificación paramétrica +
patch temporal de la constante de módulo CALIBRATION_HORIZON_DAYS (restore garantizado).

Uso:
  cd backend && .venv/bin/python -m scripts.pbo_cscv_fidelidad_completa --timing   # PASO 3: 1 corrida baseline, wall-clock
  cd backend && .venv/bin/python -m scripts.pbo_cscv_fidelidad_completa            # PASO 4: corrida completa única
Salida:
  data/cache/pbo_cscv_fidelidad_<ts>.txt + .json
"""
import argparse
import datetime
import itertools
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np
import pandas as pd

from app.config import settings
from app.core import backtest_engine as bt_mod
from app.core.backtest_engine import BacktestEngine
from app.core.indicators import calculate_all_indicators
from app.core.signal_engine import SignalEngine

CACHE_DIR = os.path.join("data", "cache")
OUT_DIR = os.path.join("data", "cache")

SYMBOLS_UNIVERSE = None  # set en main desde opportunities_universe.SYMBOLS
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
WARMUP_START = "2015-01-02"
START_DATE = "2019-01-01"
END_DATE = "2026-08-14"

S_DEFAULT = 16
S_FALLBACK = 12
MIN_PARTITION_DAYS = 60
MIN_T_MONTHS = 72
SLIPPAGE = 0.0005
INITIAL_CAPITAL = 25000.0
SEED = 42

# N=9 congelado §43.2: (label, w_mom|None=IC-derived, banda, techo, horizonte, adx_blend)
CONFIGS = [
    ("ACTUAL",      None, (45.0, 70.0), 100.0, 20, False),
    ("W_EQUAL",     0.50, (45.0, 70.0), 100.0, 20, False),
    ("W_MOM80",     0.80, (45.0, 70.0), 100.0, 20, False),
    ("BAND_WIDE",   None, (40.0, 65.0), 100.0, 20, False),
    ("BAND_NARROW", None, (50.0, 75.0), 100.0, 20, False),
    ("CAP_LOW",     None, (45.0, 70.0),  75.0, 20, False),
    ("CAP_HIGH",    None, (45.0, 70.0), 125.0, 20, False),
    ("HORIZON10",   None, (45.0, 70.0), 100.0, 10, False),
    ("ADX_BLEND",   None, (45.0, 70.0), 100.0, 20, True),
]

_WORKER_DATA = {}


class ConfigurableSignalEngine(SignalEngine):
    def __init__(self, regime_classifier, bayesian_updater=None,
                 w_mom=None, band=(45.0, 70.0), mom_hi=100.0, adx_in_blend=False):
        super().__init__(regime_classifier, bayesian_updater=bayesian_updater)
        self.cfg_band = band
        self.cfg_mom_hi = mom_hi
        if adx_in_blend:
            ic_mom, ic_rsi, ic_adx = 0.0637, 0.0322, 0.0679
            tot = ic_mom + ic_rsi + ic_adx
            ws = {"momentum": round(ic_mom / tot, 4),
                  "rsi": round(ic_rsi / tot, 4),
                  "adx": round(ic_adx / tot, 4)}
            self.factor_weights = {r: dict(ws) for r in (0, 1, 2, 3)}
        elif w_mom is not None:
            self.factor_weights = {
                r: {"momentum": round(w_mom, 4), "rsi": round(1.0 - w_mom, 4)}
                for r in (0, 1, 2, 3)
            }

    def _factor_scores(self, stock_data):
        latest = stock_data.iloc[-1]
        mom = latest.get("momentum_12_1")
        momentum_score = self._normalize(mom, -50, self.cfg_mom_hi) if pd.notna(mom) else 0.5
        rsi_v = latest.get("rsi14")
        lo, hi = self.cfg_band
        rsi_score = (0.8 if lo < rsi_v < hi else 0.4) if pd.notna(rsi_v) else 0.5
        scores = {"momentum": momentum_score, "rsi": rsi_score}
        if "adx" in self.factor_weights[0]:
            adx_v = latest.get("adx14")
            scores["adx"] = (0.9 if adx_v > 25 else 0.3) if pd.notna(adx_v) else 0.5
        return scores


class ConfigurableBacktest(BacktestEngine):
    def __init__(self, w_mom=None, band=(45.0, 70.0), mom_hi=100.0, adx_in_blend=False):
        super().__init__(initial_capital=INITIAL_CAPITAL)
        self.signal_engine = ConfigurableSignalEngine(
            self.regime_classifier, bayesian_updater=self.bayesian_updater,
            w_mom=w_mom, band=band, mom_hi=mom_hi, adx_in_blend=adx_in_blend,
        )


def load_cached(tickers):
    out = {}
    for t in tickers:
        path = os.path.join(CACHE_DIR, f"{t}.parquet")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        df.columns = [str(c).lower() for c in df.columns]
        df = df[(df.index >= WARMUP_START) & (df.index <= END_DATE)].sort_index()
        if len(df) > 200:
            out[t] = df
    return out


def _init_worker(price_data, market_data):
    _WORKER_DATA["price"] = price_data
    _WORKER_DATA["market"] = market_data


def run_one_config(args, price_data=None, market_data=None):
    """Corre UNA configuración real por backtest_engine.run() completo.
    Devuelve serie mensual neta + métricas + eco de parámetros de ejecución."""
    label, w_mom, band, mom_hi, horizon, adx_blend = args
    if price_data is None:
        price_data, market_data = _WORKER_DATA["price"], _WORKER_DATA["market"]

    np.random.seed(SEED)
    t0 = time.time()
    engine = ConfigurableBacktest(w_mom=w_mom, band=band, mom_hi=mom_hi, adx_in_blend=adx_blend)

    old_horizon = bt_mod.CALIBRATION_HORIZON_DAYS
    patched = horizon != old_horizon
    if patched:
        bt_mod.CALIBRATION_HORIZON_DAYS = horizon
    try:
        res = engine.run(
            price_data, market_data,
            pd.Timestamp(START_DATE), pd.Timestamp(END_DATE),
            commission=float(settings.COST_PER_SIDE),
            slippage=SLIPPAGE,
            execution_lag_days=int(settings.EXECUTION_LAG_DAYS),
            use_market_structure=False,
        )
    finally:
        if patched:
            bt_mod.CALIBRATION_HORIZON_DAYS = old_horizon
    wall = time.time() - t0

    eq = pd.DataFrame(res["equity_curve"]).set_index("date")["equity"]
    monthly_eq = eq.resample("M").last()
    monthly = monthly_eq.pct_change().dropna()

    trades = res["trades"]
    exit_months = {pd.Timestamp(t["exit_date"]).to_period("M") for t in trades}
    sharpe_full = float(monthly.mean() / monthly.std(ddof=1) * np.sqrt(12)) \
        if len(monthly) > 3 and monthly.std(ddof=1) > 0 else float("nan")

    exec_echo = {
        "execution_lag_days": int(settings.EXECUTION_LAG_DAYS),
        "commission_cost_per_side": float(settings.COST_PER_SIDE),
        "slippage": SLIPPAGE,
        "use_market_structure": False,
        "calibration_horizon_days_effective": int(bt_mod.CALIBRATION_HORIZON_DAYS) if not patched else int(horizon),
    }
    fidelity_exec_ok = (
        exec_echo["execution_lag_days"] == 1
        and exec_echo["commission_cost_per_side"] == 0.0005
        and exec_echo["slippage"] == 0.0005
    )
    return {
        "label": label,
        "params": {"w_mom": w_mom, "band": list(band), "mom_hi": mom_hi,
                   "horizon": horizon, "adx_in_blend": adx_blend},
        "monthly_returns": {str(p): float(v) for p, v in monthly.items()},
        "n_months": int(len(monthly)),
        "first_month": str(monthly.index[0]) if len(monthly) else None,
        "last_month": str(monthly.index[-1]) if len(monthly) else None,
        "sharpe_full_monthly_ann": sharpe_full,
        "mean_monthly_net": float(monthly.mean()) if len(monthly) else float("nan"),
        "total_trades": int(len(trades)),
        "months_with_trades": int(len(exit_months)),
        "wall_seconds": round(wall, 1),
        "exec_echo": exec_echo,
        "exec_fidelity_ok": bool(fidelity_exec_ok),
    }


def ann_sharpe_vec(block_sum, block_sumsq, ids, B):
    ids = list(ids)
    n = B * len(ids)
    if n < 3:
        return None
    s = block_sum[ids, :].sum(axis=0)
    q = block_sumsq[ids, :].sum(axis=0)
    mean = s / n
    var = np.maximum((q - n * mean ** 2) / (n - 1), 1e-18)
    sd = np.sqrt(var)
    return np.where(sd > 0, mean / sd * np.sqrt(12.0), 0.0)


def main():
    global SYMBOLS_UNIVERSE
    parser = argparse.ArgumentParser()
    parser.add_argument("--timing", action="store_true",
                        help="PASO 3: corre SOLO el baseline midiendo wall-clock")
    cli_args = parser.parse_args()

    from app.api.routes.opportunities_universe import SYMBOLS as syms
    SYMBOLS_UNIVERSE = syms
    t_start = datetime.datetime.now()
    np.random.seed(SEED)

    print(f"Universo canónico: {len(SYMBOLS_UNIVERSE)} símbolos | ventana {START_DATE}→{END_DATE} "
          f"(warmup {WARMUP_START}) | costos {settings.COST_PER_SIDE}+{SLIPPAGE} lag {settings.EXECUTION_LAG_DAYS}")
    print("Cargando cache parquet local (sin descargas)...", flush=True)
    price_data = load_cached(SYMBOLS_UNIVERSE)
    market_data = load_cached(MARKET_TICKERS)
    n_loaded = len(price_data)
    print(f"  price_data: {n_loaded}/50 | market_data: {len(market_data)}/{len(MARKET_TICKERS)}", flush=True)

    ledger_n = None
    try:
        from app.core.trial_registry import consumed_budget
        ledger_n = consumed_budget("signal_diagnosis")
    except Exception as exc:
        print(f"[warn] ledger no leíble: {exc}", file=sys.stderr)

    if cli_args.timing:
        r = run_one_config(CONFIGS[0], price_data=price_data, market_data=market_data)
        print(json.dumps({k: v for k, v in r.items() if k != "monthly_returns"}, indent=2))
        print(f"\nTIMING baseline: {r['wall_seconds']}s | trades={r['total_trades']} "
              f"| sharpe_full={r['sharpe_full_monthly_ann']:+.3f}")
        print(f"Forecast secuencial 9 configs: {9 * r['wall_seconds'] / 3600:.2f}h | "
              f"paralelo 6 workers: {2 * r['wall_seconds'] / 3600:.2f}h")
        return 0

    # ---- corrida completa (PASO 4): una sola vez ----
    n_workers = max(1, (os.cpu_count() or 2) - 2)
    print(f"Lanzando {len(CONFIGS)} configs en Pool({n_workers})...", flush=True)
    t_pool = time.time()
    if n_workers <= 1:
        results = [run_one_config(c, price_data=price_data, market_data=market_data) for c in CONFIGS]
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(n_workers, initializer=_init_worker, initargs=(price_data, market_data)) as pool:
            results = pool.map(run_one_config, CONFIGS)
    pool_wall = time.time() - t_pool
    print(f"Pool terminado en {pool_wall:.1f}s", flush=True)

    labels = [r["label"] for r in results]
    base = results[0]
    month_index = [m for m in base["monthly_returns"]]
    M = np.vstack([[r["monthly_returns"].get(m, np.nan) for m in month_index] for r in results])
    if np.isnan(M).any():
        print("[fallo] meses desalineados entre configs — FALLO HONESTO", file=sys.stderr)
        T = 0
        S = S_DEFAULT
        checks_fidelity = False
    else:
        T_total = M.shape[1]
        S = S_DEFAULT
        for cand in (S_DEFAULT, S_FALLBACK):
            B_c = T_total // cand
            if B_c * 21 >= MIN_PARTITION_DAYS:
                S = cand
                break
        T = (T_total // S) * S
        M = M[:, -T:]
        months_used = month_index[-T:]
        B = T // S

    # ---- checks de fidelidad §43.5 ----
    act_sig_months = base["months_with_trades"]
    cobertura_ratio = act_sig_months / max(base["n_months"], 1)
    checks = {
        "universo_esperado": 50,
        "n_symbols_loaded": int(n_loaded),
        "universo_ok": bool(n_loaded >= 45),
        "T_total_meses": int(len(month_index)),
        "S_elegido": int(S),
        "T_final": int(T),
        "T_ge_min": bool(T >= MIN_T_MONTHS),
        "fallback_S_usado": bool(S == S_FALLBACK),
        "cobertura_baseline": {"meses_con_trades": act_sig_months, "ratio": round(cobertura_ratio, 4),
                               "ge_30pct": bool(cobertura_ratio >= 0.30)},
        "edge_positivo_baseline": {
            "mean_mensual_neto": round(base["mean_monthly_net"], 6),
            "positivo": bool(base["mean_monthly_net"] > 0),
            "total_trades": base["total_trades"],
            "trades_ge_100": bool(base["total_trades"] >= 100),
            "sharpe_full_actual": round(base["sharpe_full_monthly_ann"], 4),
            "sharpe_positivo": bool(np.isfinite(base["sharpe_full_monthly_ann"]) and base["sharpe_full_monthly_ann"] > 0),
        },
        "exec_fidelity_por_config": {r["label"]: r["exec_fidelity_ok"] for r in results},
        "exec_echo_baseline": base["exec_echo"],
        "costos": {"commission_per_side": float(settings.COST_PER_SIDE), "slippage": SLIPPAGE},
        "ventana": f"{START_DATE}→{END_DATE}",
        "warmup_desde": WARMUP_START,
    }
    fidelity_ok = bool(
        checks["universo_ok"] and checks["T_ge_min"] and checks["cobertura_baseline"]["ge_30pct"]
        and checks["edge_positivo_baseline"]["positivo"] and checks["edge_positivo_baseline"]["trades_ge_100"]
        and checks["edge_positivo_baseline"]["sharpe_positivo"] and all(checks["exec_fidelity_por_config"].values())
        and not np.isnan(M).any()
    )

    if not fidelity_ok:
        print("[warn] CHECKS DE FIDELIDAD FALLIDOS — artefacto marcado NO INTERPRETABLE", file=sys.stderr)

    # ---- CSCV S bloques ----
    lambdas, degs, rhos, ranks_oos_best = [], [], [], []
    spearman_median = perf_deg_median = perf_deg_p5 = float("nan")
    n_combos = 0
    PBO = float("nan")
    if fidelity_ok:
        blk_sum = np.stack([M[:, i * B:(i + 1) * B].sum(axis=1) for i in range(S)])
        blk_sumsq = np.stack([np.square(M[:, i * B:(i + 1) * B]).sum(axis=1) for i in range(S)])
        combos = list(itertools.combinations(range(S), S // 2))
        n_combos = len(combos)
        for train_ids in combos:
            test_ids = tuple(i for i in range(S) if i not in train_ids)
            is_sh = ann_sharpe_vec(blk_sum, blk_sumsq, train_ids, B)
            oos_sh = ann_sharpe_vec(blk_sum, blk_sumsq, test_ids, B)
            is_mask = np.where(np.isfinite(is_sh), is_sh, -1e9)
            oos_mask = np.where(np.isfinite(oos_sh), oos_sh, -1e9)
            best_is = int(np.argmax(is_mask))
            rank_oos = float(pd.Series(oos_mask).rank(method="average").values[best_is])
            rel = min(max((rank_oos - 1) / max(len(labels) - 1, 1), 1e-9), 1.0 - 1e-9)
            lambdas.append(float(np.log(rel / (1.0 - rel))))
            ranks_oos_best.append(rank_oos)
            degs.append(float(oos_sh[best_is] - is_sh[best_is])
                        if np.isfinite(oos_sh[best_is]) and np.isfinite(is_sh[best_is]) else np.nan)
            try:
                rhos.append(float(pd.Series(is_mask).corr(pd.Series(oos_mask), method="spearman")))
            except Exception:
                rhos.append(np.nan)
        lam = np.array(lambdas)
        PBO = float((lam <= 0).mean())
        hist = {q: float(np.percentile(lam, q)) for q in (5, 25, 50, 75, 95)}
        hist.update({"mean": float(np.mean(lam)), "std": float(np.std(lam, ddof=1))})
        perf_deg_median = float(np.nanmedian(degs))
        perf_deg_p5 = float(np.nanpercentile(degs, 5))
        spearman_median = float(np.nanmedian(rhos))

    # ---- veredicto mecánico §43.4 ----
    if not fidelity_ok:
        verdict_bin, bucket, verdict = "NO_INTERPRETABLE", "fallo_fidelidad", "CHECKS DE FIDELIDAD FALLIDOS — NO INTERPRETABLE (no es NO_CUMPLE)"
    elif PBO < 0.10:
        verdict_bin, bucket = "CUMPLE", "cumple"
        verdict = "NO OVERFITTING de proceso — ranking IS informativo (PBO<0.10 estricto)"
    elif PBO < 0.20:
        verdict_bin, bucket = "NO_CUMPLE", "gris"
        verdict = "ZONA GRIS 0.10-0.20 — binario NO_CUMPLE (no se afirma robustez)"
    else:
        verdict_bin, bucket = "NO_CUMPLE", "overfitting"
        verdict = "OVERFITTING de proceso — NO_CUMPLE (PBO≥0.20, selección no mejor que azar)"
        if PBO >= 0.30:
            verdict += " | OVERFITTING sustancial (≥0.30)"

    full_sharpes = [r["sharpe_full_monthly_ann"] for r in results]
    rank_actual = 1 + sum(1 for s_ in full_sharpes if np.isfinite(s_) and s_ > full_sharpes[0])

    ts = f"{datetime.datetime.now():%Y%m%d_%H%M%S}"
    txt_path = os.path.join(OUT_DIR, f"pbo_cscv_fidelidad_{ts}.txt")
    json_path = txt_path.replace(".txt", ".json")
    os.makedirs(OUT_DIR, exist_ok=True)

    L = []
    out = L.append
    out("=" * 78)
    out("PBO/CSCV FIDELIDAD COMPLETA §43 — candidatos como configuraciones REALES del motor")
    out(f"Generado: {t_start:%Y-%m-%d %H:%M:%S} → {datetime.datetime.now():%H:%M:%S} | "
        f"pool {pool_wall:.1f}s | suma walls {sum(r['wall_seconds'] for r in results):.1f}s | workers {n_workers}")
    out(f"Universo: {n_loaded}/50 | Ventana evaluada: {START_DATE}→{END_DATE} | warmup desde {WARMUP_START}")
    out(f"Costos: commission={settings.COST_PER_SIDE} slippage={SLIPPAGE} por lado | EXECUTION_LAG_DAYS={settings.EXECUTION_LAG_DAYS}")
    out(f"Ledger signal_diagnosis al correr: consumido={ledger_n} (este trial = slot +1)")
    out("=" * 78)
    out("")
    out("--- N configs ejecutables (mapeo honesto §43.1; N≠21 declarado) ---")
    for i, r in enumerate(results):
        p = r["params"]
        mark = "  <== BASELINE ACTUAL" if i == 0 else ""
        out(f"  {i+1:02d}. {r['label']:12s} w={str(p['w_mom']) if p['w_mom'] is not None else 'IC-derived':>10s} "
            f"band={tuple(p['band'])} hi={p['mom_hi']:g} H={p['horizon']} adx_blend={p['adx_in_blend']} | "
            f"Sharpe_full={full_sharpes[i]:+.3f} trades={r['total_trades']:3d} "
            f"meses_ctrd={r['months_with_trades']:2d}/{r['n_months']} wall={r['wall_seconds']}s{mark}")
    out(f"  Rank ACTUAL (full): {rank_actual}/{len(results)}")
    out("")
    out("--- Checks de fidelidad §43.5 (fallar alguno → NO INTERPRETABLE) ---")
    for k, v in checks.items():
        out(f"  {k}: {v}")
    out(f"  FIDELIDAD GLOBAL: {'OK' if fidelity_ok else 'FALLIDA — NO INTERPRETABLE'}")
    out("")
    out("--- Resultado primario §43.4 ---")
    if fidelity_ok:
        out(f"  N={len(results)} | S={S} bloques de {B} meses (~{B*21} ruedas) | C({S},{S//2})={n_combos} splits")
        out(f"  Meses usados: {T} ({months_used[0]} → {months_used[-1]}) de T_total={len(month_index)}")
        out(f"  PBO = {PBO:.4f}  ({int(round(PBO * n_combos))}/{n_combos} splits con λ≤0)")
        out(f"  λ: media={hist['mean']:+.3f} mediana={hist['50']:+.3f} p5={hist['5']:+.3f} "
            f"p25={hist['25']:+.3f} p75={hist['75']:+.3f} p95={hist['95']:+.3f} std={hist['std']:.3f}")
        out(f"  Degradación Sharpe_OOS−IS del best IS: mediana={perf_deg_median:+.3f} p5={perf_deg_p5:+.3f}")
        out(f"  Spearman rank IS vs OOS: mediana={spearman_median:+.3f}")
        out(f"  Rank_OOS del best IS: mediana={float(np.median(ranks_oos_best)):.1f} (teórica {(len(results)+1)/2:.1f})")
    out(f"  Buckets §43.4: <0.10 CUMPLE | 0.10-0.20 gris (binario NO_CUMPLE) | ≥0.20 NO_CUMPLE | ≥0.30 sustancial")
    out(f"  VEREDICTO MECÁNICO: {verdict}")
    out(f"  VEREDICTO BINARIO ledger (PBO<0.10): {verdict_bin}")
    out("")
    out("--- Observación comparativa vs §40 (permitida como OBSERVACIÓN, no cambia veredicto) ---")
    out("  §40 proxy: N=21 vecinos vectorizados SIN stops/regime/calibrador, fin 2026-08-04 → PBO 0.4688.")
    out("  Este: N=9 configs un-eje reales CON motor completo, fin 2026-08-14. Diferencias declaradas §43.7.")
    out("")
    out("--- Riesgos materializados/declarados §43.7 ---")
    out("  Correlación vecinos un-eje alta (N_eff bajo esperado); meses sin trades = retorno cash;")
    out("  patch horizonte afecta solo labels de calibración (default-arg diagnóstico queda 20).")
    out("")
    out(f"Reproducción: seed {SEED} | python -m scripts.pbo_cscv_fidelidad_completa | una sola corrida")
    txt = "\n".join(L) + "\n"
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(txt)

    payload = {
        "pbo": PBO if fidelity_ok else None,
        "veredicto_binario": verdict_bin,
        "bucket": bucket,
        "veredicto": verdict,
        "umbral_aplicado": "PBO<0.10 (Bailey et al.)",
        "fidelity_ok": fidelity_ok,
        "checks": checks,
        "N_configs": len(results),
        "configs": [{"label": r["label"], "params": r["params"],
                     "sharpe_full": r["sharpe_full_monthly_ann"],
                     "total_trades": r["total_trades"],
                     "wall_seconds": r["wall_seconds"]} for r in results],
        "rank_actual_full": rank_actual,
        "S": int(S) if fidelity_ok else None,
        "B_meses_por_bloque": int(B) if fidelity_ok else None,
        "T_meses": int(T) if fidelity_ok else None,
        "n_splits": int(n_combos) if fidelity_ok else None,
        "logits": [float(x) for x in lambdas],
        "lambda_hist": hist if fidelity_ok else None,
        "perf_degradation_median": perf_deg_median,
        "perf_degradation_p5": perf_deg_p5,
        "spearman_median": spearman_median,
        "rank_oos_best_median": float(np.median(ranks_oos_best)) if ranks_oos_best else None,
        "ledger_consumido_al_correr": ledger_n,
        "months": months_used if fidelity_ok else month_index,
        "start_date": START_DATE, "end_date": END_DATE, "warmup_start": WARMUP_START,
        "seed": SEED, "workers": int(n_workers), "pool_wall_seconds": round(pool_wall, 1),
        "timestamp": ts,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(txt)
    print(f"\nOut: {txt_path}\nOut: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
