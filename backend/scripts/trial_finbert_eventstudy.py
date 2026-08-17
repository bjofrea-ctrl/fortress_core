"""
PLAN_MEJORA_MATEMATICA §27 (2026-08-17) — Trial FinBERT PASO 2 (Tarea B, PLAN_LARGO_PLAZO.md).

Test pre-registrado (ver PLAN_MEJORA_MATEMATICA.md §27, escrito ANTES de correr):

1. CHEQUE DE FIDELIDAD: la store debe coincidir con el artefacto de corrida
   earnings_sentiment_run_20260817_120713.txt (369 filas, 48 símbolos, 0 NULLs,
   modelo ProsusAI/finbert, fechas 2024-08-13→2026-08-12). Si falla -> exit 2.
2. TEST PRINCIPAL (decide): pendiente HAC Newey-West de rel_evento ~ score_evento
   sobre la serie cronológica de eventos, por ventana E1/E2/E3
   (L = min(40, n_eventos//8)). Criterio: |t| > 2.77 (Bonferroni-9 bilateral)
   con signo +1 en >=2/3 ventanas.
3. TEST SECUNDARIO (contexto, nunca hallazgo): premia de terciles alto vs bajo
   sobre ret relativo, con reserva de clustering/overlap declarada.

Target pre-registrado: retorno RELATIVO al mercado (lección §6.2 — el absoluto
confunde señal con dirección de mercado), 20 ruedas hábiles post-filing.

Reglas del proyecto aplicadas:
- Python 3.9 real (backend/.venv).
- NO toca el motor ni earnings_sentiment.py: solo lee la store y el cache de precios.
- Ventanas, umbral y signo esperados pre-registrados en §27.
"""
import datetime
import glob
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy import stats

DB_PATH = os.path.join("data", "cache", "earnings_sentiment.db")
HORIZON = 20
BENCH = "SPY"

# Cheque de fidelidad contra el artefacto de la corrida de acumulación.
FID_EXPECTED_ROWS = 369
FID_EXPECTED_SYMBOLS = 48
FID_MODEL = "ProsusAI/finbert"
FID_DATE_MIN = "2024-08-13"
FID_DATE_MAX = "2026-08-12"

# Umbral pre-registrado §27: Bonferroni-9 bilateral -> z = ppf(1 - 0.05/18) ~ 2.77
ALPHA_PER = 0.05 / 18.0
THRESHOLD = float(stats.norm.ppf(1 - ALPHA_PER))

WINDOWS = {
    "E1": (pd.Timestamp("2024-08-13"), pd.Timestamp("2025-06-30")),
    "E2": (pd.Timestamp("2025-07-01"), pd.Timestamp("2026-01-31")),
    "E3": (pd.Timestamp("2026-02-01"), pd.Timestamp("2026-08-12")),
}


def _nw_regression_t(x: np.ndarray, y: np.ndarray, lags: int):
    """t de la pendiente de OLS y ~ 1 + x con covarianza HAC Newey-West.

    Es la interpretación fiel del pre-registro §27: la significancia de la
    relación score -> rel se mide sobre la SERIE cronológica de eventos (los
    returns forward de 20 ruedas se solapan entre filings vecinos -> HAC), no
    con un i.i.d. ni con la media de rel (eso mediría drift de mercado, no
    predicción). Devuelve (beta, se_hac, t).
    """
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ beta
    # meat HAC: Gamma_0 + sum_j w_j (Gamma_j + Gamma_j')
    k = X.shape[1]
    meat = np.zeros((k, k))
    for t in range(n):
        xt = X[t][:, None]
        meat += (e[t] ** 2) * (xt @ xt.T)
    for j in range(1, min(lags, n - 1) + 1):
        w = 1.0 - j / (lags + 1)
        G = np.zeros((k, k))
        for t in range(j, n):
            G += np.outer(X[t] * e[t], X[t - j] * e[t - j])
        meat += w * (G + G.T)
    inv_xx = np.linalg.inv(X.T @ X)
    V = inv_xx @ meat @ inv_xx * (n / (n - k))  # corrección small-sample
    se = float(np.sqrt(max(V[1, 1], 0.0)))
    t = float(beta[1] / se) if se > 0 else 0.0
    return float(beta[1]), se, t


def load_prices() -> dict:
    """Cierre de cada símbolo como Serie indexada por Timestamp.

    Solo archivos de precio OHLCV (columna 'Close'); el cache también guarda
    factor_panel_*.parquet y otros con esquemas distintos.
    """
    cache = {}
    for path in glob.glob(os.path.join("data", "cache", "*.parquet")):
        df = pd.read_parquet(path)
        if "Close" not in df.columns:
            continue
        sym = os.path.basename(path)[:-8]
        close = df["Close"]
        close.index = pd.to_datetime(close.index)
        cache[sym] = close.sort_index()
    return cache


def bench_nearest(series: pd.Series, day, offset: int) -> pd.Timestamp:
    """Rueda de trading del bench <= day + offset ruedas (searchsorted, sin ffill)."""
    idx = series.index
    pos = idx.searchsorted(day, side="right") - 1
    if pos < 0:
        raise ValueError(f"bench sin ruedas <= {day}")
    return idx[pos + offset]


def build_events(prices: dict, out) -> pd.DataFrame:
    """Un evento por filing: (symbol, filing_date, score, ret_s, ret_b, rel).

    Exclusión pre-declarada (§27): eventos sin 20 ruedas hábiles completas
    después del filing_date en el cache del símbolo. Se devuelven los eventos
    individuales (NO agregados): el rank IC diario necesita la cross-section.
    """
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT symbol, filing_date, score FROM sentiment ORDER BY filing_date"
    ).fetchall()
    con.close()

    bench = prices[BENCH]
    n_dropped = 0
    events = []
    for sym, d, score in rows:
        c = prices[sym]
        prior = c.index[c.index <= pd.Timestamp(d)]
        fut = c.index[c.index > pd.Timestamp(d)]
        if len(prior) == 0 or len(fut) < HORIZON:
            n_dropped += 1
            continue
        t0, t1 = prior[-1], fut[HORIZON - 1]
        try:
            b0 = bench_nearest(bench, t0, 0)
            b1 = bench_nearest(bench, t1, 0)
        except Exception as exc:
            n_dropped += 1
            out(f"  [DROP] {sym} {d}: bench imposible ({exc})")
            continue
        ret_s = float(c[t1] / c[t0] - 1.0)
        ret_b = float(bench[b1] / bench[b0] - 1.0)
        events.append(
            {"symbol": sym, "d": pd.Timestamp(d), "score": float(score),
             "ret_s": ret_s, "ret_b": ret_b}
        )
    df = pd.DataFrame(events)
    df["rel"] = df["ret_s"] - df["ret_b"]
    out(f"Eventos: {len(rows)} en store -> {len(df)} con ventana fwd-{HORIZON} "
        f"completa ({n_dropped} excluidos por ventana incompleta, pre-declarado)")
    return df


def aggregate_by_day(df: pd.DataFrame) -> pd.DataFrame:
    """Agregación por día de filing pre-declarada en §27: para fechas con >1
    filing, score_día y rel_día = medias. Un punto por día de filing."""
    agg = df.groupby("d", as_index=False).agg(score=("score", "mean"), rel=("rel", "mean"), n=("score", "size"))
    return agg.sort_values("d")


def series_stats(x: np.ndarray, y: np.ndarray, lags: int) -> dict:
    """Pendiente HAC de rel ~ score sobre la serie cronológica de eventos
    (pre-registrado §27). Un t sobre la media mediría drift, no predicción —
    por eso el estadístico de decisión es la pendiente con covarianza HAC."""
    n = len(x)
    if n < 10:
        return {"n": n, "spearman": np.nan, "se_nw": np.nan, "t": np.nan}
    rho, _ = stats.spearmanr(x, y)
    _beta, se, t = _nw_regression_t(x, y, lags)
    return {"n": int(n), "spearman": float(rho), "se_nw": se, "t": t}


def main() -> int:
    out_path = os.path.join(
        "data", "cache", f"trial_finbert_eventstudy_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def out(msg: str = ""):
        print(msg)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")

    out("=" * 78)
    out("PLAN_MEJORA_MATEMATICA §27 — Trial FinBERT PASO 2 (2026-08-17)")
    out(f"Store: {DB_PATH} | target: ret relativo a {BENCH}, {HORIZON} ruedas post-filing")
    out(f"Umbral pre-registrado: |t| > {THRESHOLD:.3f} (Bonferroni-9 bilateral) con signo +1 en >=2/3 ventanas E1/E2/E3")
    out("=" * 78)

    prices = load_prices()

    # --- Cheque de fidelidad contra el artefacto de la corrida ---
    out("\n--- CHEQUE DE FIDELIDAD contra earnings_sentiment_run_20260817_120713.txt ---")
    con = sqlite3.connect(DB_PATH)
    n_rows = con.execute("SELECT COUNT(*) FROM sentiment").fetchone()[0]
    n_syms = con.execute("SELECT COUNT(DISTINCT symbol) FROM sentiment").fetchone()[0]
    n_null = con.execute("SELECT COUNT(*) FROM sentiment WHERE score IS NULL").fetchone()[0]
    models = set(r[0] for r in con.execute("SELECT DISTINCT model_version FROM sentiment"))
    dmin, dmax = con.execute("SELECT MIN(filing_date), MAX(filing_date) FROM sentiment").fetchone()
    con.close()
    checks = [
        ("filas", n_rows, FID_EXPECTED_ROWS, n_rows == FID_EXPECTED_ROWS),
        ("símbolos", n_syms, FID_EXPECTED_SYMBOLS, n_syms == FID_EXPECTED_SYMBOLS),
        ("NULLs score", n_null, 0, n_null == 0),
        ("modelo", sorted(models), {FID_MODEL}, models == {FID_MODEL}),
        ("fecha min", dmin, FID_DATE_MIN, dmin == FID_DATE_MIN),
        ("fecha max", dmax, FID_DATE_MAX, dmax == FID_DATE_MAX),
    ]
    ok = True
    for name, got, exp, passed in checks:
        out(f"  {name}: medido={got} esperado={exp} -> {'OK' if passed else 'FALLO'}")
        ok = ok and passed
    if not ok:
        out("  -> ABORTA sin interpretar (regla §14): la store no es la evidencia pre-registrada")
        return 2
    out("  OK: la store coincide con el artefacto de la corrida de acumulación")

    # --- Construcción de eventos ---
    out("\n--- Construcción de eventos ---")
    df = build_events(prices, out)
    agg = aggregate_by_day(df)
    out(f"Días de filing agregados: {len(agg)} (1 serie temporal por ventana)")

    # --- Test principal ---
    out("\n--- TEST PRINCIPAL (pre-registrado §27): Spearman score_día ~ rel_día por ventana ---")
    out(f"{'ventana':7s} {'rango':27s} {'n_dias':>6s} {'spearman':>9s} {'SE_NW':>8s} {'t':>7s} {'L':>3s} {'signo':>5s} {'SIG':>5s}")
    results = {}
    for name, (start, end) in WINDOWS.items():
        wdf = df[(df["d"] >= start) & (df["d"] <= end)].sort_values("d")
        L = min(40, len(wdf) // 8)
        res = series_stats(wdf["score"].to_numpy(), wdf["rel"].to_numpy(), L)
        results[name] = res
        signo = "+" if (np.isfinite(res["t"]) and res["t"] > 0) else "-"
        sig = "SIG" if (np.isfinite(res["t"]) and abs(res["t"]) > THRESHOLD and res["t"] > 0) else "no"
        out(f"{name:7s} {str(start.date()) + ' -> ' + str(end.date()):27s} {res['n']:6d} "
            f"{res['spearman']:+9.4f} {res['se_nw']:8.4f} {res['t']:+7.2f} {L:3d} {signo:>5s} {sig:>5s}")

    L_tot = min(40, len(df) // 8)
    tot = series_stats(df["score"].to_numpy(), df["rel"].to_numpy(), L_tot)
    out(f"TOTAL(ref) {str(agg['d'].min().date())} -> {str(agg['d'].max().date())} {tot['n']:6d} "
        f"{tot['spearman']:+9.4f} {tot['se_nw']:8.4f} {tot['t']:+7.2f} (no cuenta)")

    n_sig = sum(
        1 for r in results.values()
        if np.isfinite(r["t"]) and abs(r["t"]) > THRESHOLD and r["t"] > 0
    )
    cumple = n_sig >= 2
    out(f"\nCriterio pre-registrado: |t| > {THRESHOLD:.2f} con signo +1 en >=2/3 ventanas -> SIG: {n_sig}/3")
    out(f"VEREDICTO: {'CUMPLE' if cumple else 'NO_CUMPLE'}")

    # --- Test secundario (contexto) ---
    out("\n--- TEST SECUNDARIO (contexto, NUNCA hallazgo): premia terciles alto vs bajo sobre rel ---")
    for name, (start, end) in WINDOWS.items():
        wdf = agg[(agg["d"] >= start) & (agg["d"] <= end)]
        if len(wdf) < 9:
            out(f"{name}: n insuficiente para terciles")
            continue
        q = pd.qcut(wdf["score"], 3, labels=False, duplicates="drop")
        hi = wdf[q == q.max()]["rel"]
        lo = wdf[q == q.min()]["rel"]
        if len(hi) == 0 or len(lo) == 0:
            out(f"{name}: terciles vacíos")
            continue
        premia = float(hi.mean() - lo.mean())
        sp2 = ((len(hi) - 1) * hi.var(ddof=1) + (len(lo) - 1) * lo.var(ddof=1)) / (len(hi) + len(lo) - 2)
        se = float(np.sqrt(sp2 * (1.0 / len(hi) + 1.0 / len(lo))))
        t = premia / se if se > 0 else np.nan
        out(f"{name}: n_hi={len(hi)} n_lo={len(lo)} premia={premia:+.5f} t_pooled={t:+.2f}")
    out("  Reserva pre-registrada (§27): clustering por día de filing y overlap de ventanas forward —")
    out("  el t secundario pooled se lee solo como magnitud, nunca como hallazgo.")

    out(f"\nOut: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
