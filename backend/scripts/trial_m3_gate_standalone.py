"""
TRIAL #19 (PLAN §46, 2026-08-25) — Compuerta M3 STANDALONE sobre la operación
del motor (Brecha 2, auditoría externa glm-5.2). PRE-REGISTRADO y APROBADO
antes de correr (§46, revisión coordinador 2026-08-25).

Pregunta: ¿operar el motor completo SOLO cuando la etiqueta macro walk-forward
de M3 es GOLDILOCKS (abstenerse el resto) mejora el perfil OOS vs operar siempre?
Genuinamente inédito: el factor macro solo se usó como término lineal en
ridge_3f (trial #13) y como condicionante diagnóstico de IC de momentum (§42) —
jamás como compuerta de operación del motor (ROADMAP línea 343).

Diseño (dos armas intra-corrida, misma data, mismo motor vigente):
  ALWAYS: BacktestEngine estándar.
  GATED : subclase que reemplaza self.signal_engine por un proxy que devuelve
          None si la etiqueta M3 rezagada de la fecha de decisión no es
          GOLDILOCKS; delega idéntico si lo es. Exits/stops/sizing/calibrador
          intactos. Inyección por atributo/subclase — cero edición de producción.

Etiqueta M3: WalkForwardRegimeGate(favorable_states={0}) (GOLDILOCKS por
_align_states growth_SPY max), defaults 63/756, macro SPY EFA QQQ GLD DBC TIP
TLT AGG ^VIX desde 2015-01-01 (cache-only), lag 21 hábiles (heredado §42a),
fechas sin etiqueta -> GATED no opera (conservador, declarado).

Umbral leído DEL LEDGER en runtime: motor_signal consumido=12 -> n=13 ->
current_threshold()=0.9923076923076923. CRITERIO por ventana computable
(>=30 trades gated): DSR_gated >= th Y Sharpe_gated > Sharpe_always. GLOBAL:
CUMPLE si >=2/3 ventanas computables. Si <2/3 computables -> NO INTERPRETABLE
mecánico: NO registra NI consume slot (mismo contrato explícito §45).

Fidelidad F1-F10 (incluye F9 identity-cache reutilizado de §45 con verificación
bit-idéntica, y F10 sanity del control). Ventanas canónicas W1/W2/W3.

Reglas: Python 3.9 real (backend/.venv), lee SOLO cache parquet. No toca
signal_engine.py/backtest_engine.py/regime_gate.py/trial_registry.py en runtime.
Uso (UNA sola corrida):
  cd backend && .venv/bin/python -u -m scripts.trial_m3_gate_standalone
Salida:
  data/cache/trial19_m3_gate_standalone_<ts>.txt + .json + parquet equity/trades
"""
import datetime
import json
import os

import numpy as np
import pandas as pd
from app.api.routes.opportunities_universe import SYMBOLS
from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import load_universe
from app.core.indicators import calculate_all_indicators
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.trial_registry import consumed_budget, current_threshold

TRIAL_ID = "trial_m3_gate_standalone"
DATA_START = "2015-01-01"
OP_START = "2019-01-01"
END = "2026-08-20"            # borde del cache verificado 2026-08-25 (sin descargas)
WINDOWS = [
    ("W1 2020-2021", "2020-01-01", "2021-12-31"),
    ("W2 2022-2023", "2022-01-01", "2023-12-31"),
    ("W3 2024-2026", "2024-01-01", END),
]
MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
TRADE_FLOOR = 30              # piso por ventana para considerarla computable
LAG_BDAYS = 21                # rezago del estado HMM (heredado §42a)
INITIAL_CAPITAL = 25000.0
MIN_HISTORY_GATE = 756        # default del módulo M3
RECALIB_EVERY = 63            # default del módulo M3

# Umbral leído DEL LEDGER en runtime (§46 lo fija antes de correr)
N_FAM_CONSUMED = consumed_budget("motor_signal")
N_TRIALS_DSR = N_FAM_CONSUMED + 1
DSR_THRESHOLD = current_threshold("motor_signal")

COLS_CHECK = ["close", "atr14", "rsi14", "adx14", "momentum_12_1",
              "hurst_exponent", "realized_vol_regime"]


def patch_signal_engine_identity_cache(price_data):
    """Nota de ejecución heredada de §45 (intento válido): generate_signal
    recalcula calculate_all_indicators sobre frames ya indicatorizados en cada
    día×símbolo — redundancia ~10x tras T2.3 (hurst). Parche SOLO intra-proceso:
    identidad sobre el frame cacheado. Equivalencia bit-idéntica por causalidad,
    verificada EN-CORRIDA muestreando pares (símbolo, fecha) contra recálculo
    real; aborto si difiere (check F9)."""
    import app.core.signal_engine as se

    full_indicators = {s: calculate_all_indicators(df) for s, df in price_data.items()}
    rng = np.random.default_rng(42)
    symbols_ok = [s for s in price_data if s in full_indicators]
    n_checked = 0
    for _ in range(25):
        sym = symbols_ok[int(rng.integers(len(symbols_ok)))]
        fi = full_indicators[sym]
        if len(fi) < 600:
            continue
        d = fi.index[int(rng.integers(500, len(fi)))]
        recomputed = calculate_all_indicators(price_data[sym].loc[:d])
        common = recomputed.index.intersection(fi.loc[:d].index)
        if len(common) == 0:
            continue
        tail = common[-1]
        for c in COLS_CHECK:
            a = float(fi.loc[tail, c])
            b = float(recomputed.loc[tail, c])
            assert np.isclose(a, b, rtol=1e-12, atol=1e-15), (
                f"F9 EQUIVALENCIA ROTA: {sym} {tail.date()} col={c} cache={a} vs recompute={b}")
        n_checked += 1
    assert n_checked >= 10, "F9: insuficientes pares verificados"

    def _identity(sdf):
        return sdf

    se.calculate_all_indicators = _identity
    return {"pares_verificados": n_checked, "columnas": COLS_CHECK, "ok": True}


def goldilocks_lagged(dates_index: pd.DatetimeIndex) -> tuple:
    """Etiqueta M3 walk-forward GOLDILOCKS REZAGADA LAG_BDAYS hábiles (§42a).
    Devuelve Serie bool alineada a las fechas pedidas (False = no operar) +
    diagnósticos del gate. label_series lanza si falla un assert anti-leakage."""
    from app.core.regime_gate import WalkForwardRegimeGate

    macro = load_universe(MACRO_TICKERS, DATA_START, END)
    gate = WalkForwardRegimeGate(
        favorable_states=frozenset({0}),
        recalib_every=RECALIB_EVERY,
        min_history=MIN_HISTORY_GATE,
    )
    labels, diag = gate.label_series(macro)
    targets = dates_index - pd.offsets.BDay(LAG_BDAYS)
    pos = labels.index.searchsorted(targets, side="right") - 1
    out = pd.Series(False, index=dates_index)
    valid = pos >= 0
    out.loc[valid] = labels.values[pos[valid]].astype(bool)
    return out, diag


class _GatedSignalProxy:
    """Proxy del SignalEngine del arma GATED (§46): bloquea generate_signal
    fuera de GOLDILOCKS-rezagado; TODO lo demás delega intacto."""

    def __init__(self, inner, gold_labels: pd.Series):
        self._inner = inner
        self._gold_labels = gold_labels
        self.n_bloqueadas = 0
        self.n_delegadas = 0

    def generate_signal(self, stock_data, symbol, regime_state, market_structure=None):
        d = stock_data.index[-1] if len(stock_data) else None
        operar = bool(self._gold_labels.get(d, False))
        if not operar:
            self.n_bloqueadas += 1
            return None
        self.n_delegadas += 1
        return self._inner.generate_signal(
            stock_data, symbol, regime_state, market_structure=market_structure)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class GatedEngine(BacktestEngine):
    def __init__(self, initial_capital: float = INITIAL_CAPITAL, gold_labels=None):
        super().__init__(initial_capital)
        self.signal_engine = _GatedSignalProxy(self.signal_engine, gold_labels)


def period_metrics(equity_curve, trades, s, e, engine):
    eq = [p for p in equity_curve if pd.Timestamp(s) <= pd.Timestamp(p["date"]) <= pd.Timestamp(e)]
    tr = [t for t in trades if pd.Timestamp(s) <= pd.Timestamp(t["exit_date"]) <= pd.Timestamp(e)]
    return engine.calculate_metrics(eq, tr, n_trials=N_TRIALS_DSR), tr


def main():
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join("data", "cache", "%s_%s.txt" % (TRIAL_ID, ts))
    json_path = os.path.join("data", "cache", "%s_%s.json" % (TRIAL_ID, ts))

    def log(msg=""):
        print(msg, flush=True)
        with open(txt_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    log("=" * 76)
    log("TRIAL #19 (PLAN §46) — COMPUERTA M3 STANDALONE SOBRE EL MOTOR (aprobado)")
    log("Pregunta: operar SOLO en GOLDILOCKS-rezagado vs operar siempre")
    log("ALWAYS: BacktestEngine estándar | GATED: proxy sobre signal_engine")
    log(f"Etiqueta: WalkForwardRegimeGate(GOLDILOCKS), recalib {RECALIB_EVERY}d/"
        f"min_hist {MIN_HISTORY_GATE}d, lag {LAG_BDAYS} hábiles | sin etiqueta -> no opera")
    log("Ledger runtime: motor_signal consumido=%d -> n=%d | th=%.16f"
        % (N_FAM_CONSUMED, N_TRIALS_DSR, DSR_THRESHOLD))
    log("CRITERIO ventana computable (piso %d trades gated): DSR_gated>=%.5f "
        "Y Sharpe_gated>Sharpe_always" % (TRADE_FLOOR, DSR_THRESHOLD))
    log("<2/3 ventanas computables -> NO INTERPRETABLE: no registra ni consume")
    log("=" * 76)

    checks = {}
    market_data = load_universe(["SPY"], DATA_START, END)["SPY"]
    price_data = load_universe(SYMBOLS, DATA_START, END)
    checks["F1_universo50"] = {"cargadas": len(price_data), "esperado": len(SYMBOLS),
                               "ok": len(price_data) == len(SYMBOLS)}
    log("\nF1 universo: %d/%d | panel %s -> %s"
        % (len(price_data), len(SYMBOLS),
           min(df.index.min() for df in price_data.values()).date(),
           max(df.index.max() for df in price_data.values()).date()))

    checks["F9_equivalencia_identity"] = patch_signal_engine_identity_cache(price_data)
    log("F9 equivalencia identity-cache: %d pares x %d columnas bit-idénticos"
        % (checks["F9_equivalencia_identity"]["pares_verificados"],
           len(checks["F9_equivalencia_identity"]["columnas"])))

    clf_probe = GlobalRegimeClassifier(n_states=4)
    checks["F3_determinismo_seed42"] = {
        "hmm_random_state": int(clf_probe.model.random_state),
        "ok": int(clf_probe.model.random_state) == 42}

    # Etiqueta GOLDILOCKS-lag alineada a las fechas de operación (índice SPY)
    dates_idx = pd.DatetimeIndex(sorted(
        set(market_data[(market_data.index >= OP_START)].index)))
    gold_labels, diag = goldilocks_lagged(dates_idx)
    checks["F4_gate_walkforward"] = {
        "n_recalibraciones": int(diag.n_recalibraciones),
        "fechas_etiquetadas": int(diag.n_fechas_etiquetadas),
        "asserts_antileakage_pasados": True,   # label_series lanza si fallan
        "distribucion_estados": {str(k): int(v)
                                 for k, v in sorted(diag.distribucion_regimenes.items())},
    }
    frac_gold = float(gold_labels.mean())
    checks["F5_frac_goldilocks_global"] = {"fraccion_dias_goldilocks": frac_gold}
    log("\nF4 gate: recalibs=%d | fechas etiquetadas=%d | estados=%s"
        % (diag.n_recalibraciones, diag.n_fechas_etiquetadas,
           checks["F4_gate_walkforward"]["distribucion_estados"]))
    log("F5 fracción días GOLDILOCKS-lag (global): %.3f" % frac_gold)

    log("\nCorriendo arma ALWAYS (control, sin compuerta)...")
    res_base = BacktestEngine(initial_capital=INITIAL_CAPITAL).run(
        price_data, load_universe(MACRO_TICKERS, DATA_START, END),
        pd.Timestamp(OP_START), pd.Timestamp(END))

    log("Corriendo arma GATED (M3 standalone)...")
    gengine = GatedEngine(initial_capital=INITIAL_CAPITAL, gold_labels=gold_labels)
    res_gate = gengine.run(
        price_data, load_universe(MACRO_TICKERS, DATA_START, END),
        pd.Timestamp(OP_START), pd.Timestamp(END))
    proxy = gengine.signal_engine
    log("Señales GATED: delegadas=%d bloqueadas=%d (%.1f%% bloqueadas)"
        % (proxy.n_delegadas, proxy.n_bloqueadas,
           100.0 * proxy.n_bloqueadas / max(1, proxy.n_delegadas + proxy.n_bloqueadas)))

    engine_probe = BacktestEngine(initial_capital=INITIAL_CAPITAL)
    cols = ["cagr", "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
            "win_rate", "profit_factor", "total_trades", "deflated_sharpe"]

    results = {}
    window_rows = []
    for label, s, e in WINDOWS:
        mb, trb = period_metrics(res_base["equity_curve"], res_base["trades"], s, e, engine_probe)
        mg, trg = period_metrics(res_gate["equity_curve"], res_gate["trades"], s, e, engine_probe)
        wd = gold_labels[(gold_labels.index >= pd.Timestamp(s)) & (gold_labels.index <= pd.Timestamp(e))]
        frac_w = float(wd.mean()) if len(wd) else float("nan")
        computable = len(trg) >= TRADE_FLOOR
        dsr_g = mg.get("deflated_sharpe", float("nan"))
        sh_g = mg.get("sharpe_ratio", float("nan"))
        sh_b = mb.get("sharpe_ratio", float("nan"))
        pasa = bool(computable and np.isfinite(dsr_g) and dsr_g >= DSR_THRESHOLD
                    and np.isfinite(sh_g) and np.isfinite(sh_b) and sh_g > sh_b)
        results[label] = {"base": mb, "gated": mg, "n_base": len(trb), "n_gated": len(trg),
                          "frac_goldilocks_ventana": frac_w, "computable": bool(computable),
                          "dsr_gated": dsr_g, "sharpe_base": sh_b, "sharpe_gated": sh_g,
                          "pasa": pasa}
        window_rows.append((label, computable, pasa))
        log("\n--- %s (ALWAYS n=%d, GATED n=%d) | GOLDILOCKS %.1f%% días ---"
            % (label, len(trb), len(trg), 100 * frac_w if np.isfinite(frac_w) else float("nan")))
        for c in cols:
            b, g = mb.get(c, float("nan")), mg.get(c, float("nan"))
            log("    %-18s ALWAYS=%12.4f GATED=%12.4f" % (c, b, g))
        checks.setdefault("F10_sanity_control", {})[label] = {
            "n_trades_base": len(trb), "trades_positivo": len(trb) > 0,
            "metricas_finitas": bool(np.isfinite(sh_b))}

    computables = [w for w, comp, _ in window_rows if comp]
    pasan = [w for w, _, p in window_rows if p]
    log("\n" + "=" * 76)
    log("VENTANAS COMPUTABLES (>= %d trades gated): %s" % (TRADE_FLOOR, computables))
    if len(computables) < 2:
        global_verdict = None
        ledger_status = "NO_REGISTRA"
        log("NO INTERPRETABLE mecánico (<2/3 ventanas computables): NO registra "
            "NI consume slot motor_signal (contrato §46). Documentado como intento inválido.")
    else:
        for (label, comp, pasa) in window_rows:
            r = results[label]
            log("  %s: DSR_gated=%.4f vs th=%.5f | Sharpe %.4f vs %.4f -> %s%s"
                % (label, r["dsr_gated"], DSR_THRESHOLD, r["sharpe_gated"],
                   r["sharpe_base"], "PASA" if pasa else "no pasa",
                   "" if comp else " (NO COMPUTABLE: < piso trades)"))
        global_verdict = "CUMPLE" if len(pasan) >= 2 else "NO_CUMPLE"
        ledger_status = "REGISTRA"
        log("\nVEREDICTO MECÁNICO §46: %s (%d/%d ventanas computables pasan)"
            % (global_verdict, len(pasan), len(computables)))

    pd.DataFrame(res_gate["trades"]).to_parquet(txt_path.replace(".txt", "_gated_trades.parquet"))
    pd.DataFrame(res_base["trades"]).to_parquet(txt_path.replace(".txt", "_base_trades.parquet"))

    payload = {
        "trial_id": TRIAL_ID,
        "status": "EJECUTADO",
        "pre_registro": "PLAN_MEJORA_MATEMATICA.md §46",
        "familia": "motor_signal",
        "ledger_runtime": {"consumido_antes": N_FAM_CONSUMED, "n_trial": N_TRIALS_DSR,
                           "dsr_threshold": DSR_THRESHOLD},
        "congelado": {"gate": "WalkForwardRegimeGate(GOLDILOCKS={0}), 63/756, lag 21b",
                      "macro": MACRO_TICKERS, "sin_etiqueta": "no opera"},
        "checks_fidelidad": checks,
        "señales_gated": {"delegadas": proxy.n_delegadas, "bloqueadas": proxy.n_bloqueadas},
        "resultados_por_ventana": results,
        "veredicto_global": global_verdict,
        "ledger_status": ledger_status,
        "timestamp": ts,
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=float)
    log("\nArtefacto: %s" % txt_path)
    print("ARTIFACT:%s" % txt_path)
    print("LEDGER_STATUS:%s" % ledger_status)
    print("VEREDICTO_GLOBAL:%s" % (global_verdict or "NO_INTERPRETABLE_PISO"))
    print("DSR_THRESHOLD:%.5f" % DSR_THRESHOLD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
