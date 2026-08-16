"""PLAN_MEJORA_MATEMATICA §23 — TRIPLE BARRIER como target (Tarea A, PLAN_LARGO_PLAZO.md).

PRE-REGISTRADO antes de correr (2026-08-16, ver §23 en el plan). Este script aplica
el criterio pre-registrado MECÁNICAMENTE y no decide nada por sí mismo.

Pregunta: los factores refutados contra `fwd_return_20d` (momentum_score, rsi_score,
adx_score) tienen poder de selección intra-día contra el objetivo que el motor persigue
de verdad — el label binario de barrera (M1, barrier_labeling): ¿toca TP antes que SL?

Metodología (idéntica a §0.5a/§21/§21.1):
  - Panel eligible del factor_panel_*.parquet (stride 5d, universo 50).
  - Labels con barrier_labeling.label_symbol() (NO se toca ese módulo), max_horizon=60,
    costo settings.COST_PER_SIDE, régimen del panel.
  - rank IC intra-día (Spearman por fecha) entre factor y label, SE Newey-West.
  - Lags NW por ventana: L = min(12, max(1, floor(n_dias/8))) — regla pre-registrada.
  - Ventanas W1/W2/W3 + total como referencia. Bonferroni-9 --> |t| > 2.78, signo +1.
  - Exclusión del borde (§23): últimos 60 barras por símbolo sin ventana completa.

El script aborta sin interpretar si el cheque de fidelidad del label no pasa.
"""
import datetime
import glob
import math
import os

import numpy as np
import pandas as pd
from app.config import settings
from app.core.barrier_labeling import label_symbol, summarize
from app.core.data_ingestion import load_universe
from app.core.indicators import atr
from scipy import stats
from scripts.fetch_universe_data import NEW_UNIVERSE

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + NEW_UNIVERSE
START = "2019-01-01"
END = "2026-08-04"
FACTORS = {"momentum_score": +1, "rsi_score": +1, "adx_score": +1}
WINDOWS = {
    "W1": ("2020-01-01", "2021-12-31"),
    "W2": ("2022-01-01", "2023-12-31"),
    "W3": ("2024-01-01", "2099-12-31"),  # el extremo real lo impone el fin del panel
}
MIN_SYMBOLS = 5
MAX_HORIZON = 60                      # espejo de barrier_labeling.DEFAULT_MAX_HORIZON
Z_BONFERRONI_9 = float(stats.norm.ppf(1 - 0.05 / (2 * 9)))
STRIDE_DAYS = 5
MAX_LAG = int(math.ceil(MAX_HORIZON / STRIDE_DAYS))  # 12


def latest_panel() -> str:
    files = sorted(glob.glob(os.path.join("data", "cache", "factor_panel_*.parquet")))
    if not files:
        raise SystemExit("No hay factor_panel_*.parquet")
    return files[-1]


def newey_west_se(z: np.ndarray, lags: int) -> float:
    n = len(z)
    if n < 3:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    lag_max = min(lags, n - 2)
    if lag_max < 1:
        return float(np.std(z, ddof=1) / np.sqrt(n))
    rho = np.array([np.corrcoef(z[:-j], z[j:])[0, 1] for j in range(1, lag_max + 1)])
    rho = np.nan_to_num(rho, nan=0.0)
    w = 1 - np.arange(1, len(rho) + 1) / (lags + 1)
    denom = 1 + 2 * np.sum(w * rho)
    n_eff = n / max(denom, 1.0)
    return float(np.std(z, ddof=1) / np.sqrt(n_eff))


def build_labels(price_data: dict, panel: pd.DataFrame) -> pd.DataFrame:
    """Etiqueta cada fecha válida de cada símbolo con M1 (barreras reales).

    - `atr14` calculado con indicators.atr (misma definición que indicators.py).
    - `regime` por (date, symbol) tomado del panel (HMM causal); si falta -> 0.
    - EXCLUSIÓN DEL BORDE pre-registrada (§23): se corta la serie antes de los
      últimos MAX_HORIZON barras para que TODA etiqueta tenga ventana completa.
    """
    reg_by_sym: dict = {}
    for sym, g in panel.groupby("symbol"):
        reg_by_sym[sym] = dict(zip(g["date"], g["regime"]))

    frames = []
    for sym, d in price_data.items():
        d = d.sort_index()
        if len(d) < MAX_HORIZON + 20:
            continue
        df = pd.DataFrame(
            {
                "close": d["close"].to_numpy(dtype=float),
                "atr14": atr(d["high"], d["low"], d["close"], 14).to_numpy(dtype=float),
            },
            index=d.index,
        )
        # Exclusión del borde: solo fechas con >= MAX_HORIZON barras futuras.
        df_cut = df[df.index < df.index[-MAX_HORIZON]]

        reg_map = reg_by_sym.get(sym, {})
        regimes = np.array([reg_map.get(ts, 0) for ts in df_cut.index], dtype=int)
        lab = label_symbol(
            df_cut,
            regimes=regimes,
            max_horizon=MAX_HORIZON,
            cost_per_side=settings.COST_PER_SIDE,
        )
        if lab.empty:
            continue
        lab["symbol"] = sym
        frames.append(lab)

    if not frames:
        raise SystemExit("No se pudo etiquetar ningún símbolo — fidelidad abortada.")
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out
def daily_ics(merged: pd.DataFrame, factor: str, target: str) -> np.ndarray:
    """Rank IC intra-día: Spearman por fecha entre factor y target (patrón §0.5a)."""
    ics = []
    for date in sorted(pd.DatetimeIndex(merged["date"].unique())):
        day = merged[merged["date"] == date]
        day = day[day[factor].notna() & day[target].notna()]
        if len(day) < MIN_SYMBOLS:
            continue
        rho, _ = stats.spearmanr(day[factor], day[target])
        if np.isfinite(rho):
            ics.append(rho)
    return np.array(ics)


def summarize_ic(ics: np.ndarray, lags: int) -> dict:
    if len(ics) == 0:
        return {"n_days": 0, "mean_ic": float("nan"), "se_nw": float("nan"),
                "t": float("nan"), "lags": lags}
    mean_ic = float(ics.mean())
    se_nw = newey_west_se(ics, lags)
    t = mean_ic / se_nw if se_nw > 0 else 0.0
    return {"n_days": int(len(ics)), "mean_ic": mean_ic, "se_nw": se_nw,
            "t": t, "lags": lags}


def main() -> None:
    out_path = os.path.join(
        "data", "cache", f"retest_triple_barrier_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    def log(msg: str = ""):
        print(msg)
        with open(out_path, "a") as fh:
            fh.write(msg + "\n")

    log("=" * 80)
    log("PLAN §23 — TRIPLE BARRIER: re-test de factores refutados (Tarea A)")
    log("PRE-REGISTRADO el 2026-08-16 (ver §23) | este script no decide nada solo")
    log("=" * 80)

    # --- Datos ------------------------------------------------------------- #
    panel_path = latest_panel()
    panel = pd.read_parquet(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    elig = panel[panel["eligible"]].copy()
    panel_end = str(panel["date"].max().date())
    log(f"Panel: {os.path.basename(panel_path)} | filas eligible: {len(elig)}")
    log(f"Ventanas: W1 2020-2021 | W2 2022-2023 | W3 2024-{panel_end}")

    log("Cargando precios y etiquetando (M1, barreras reales)...")
    price_data = load_universe(SYMBOLS, START, END)
    labels = build_labels(price_data, panel)
    log(f"Labels etiquetados: {len(labels)} filas | "
        f"{labels['symbol'].nunique()} símbolos | "
        f"{labels['date'].nunique()} fechas")

    # --- Cheque de fidelidad del etiquetado (aborta si no es sano) --------- #
    summ_total = summarize(labels)
    win_rate = float(summ_total.get("win_rate_neto", 0.0))
    n_valid = int(summ_total.get("n", 0))
    pct_time = float(summ_total.get("pct_barrera_temporal", 0.0))
    log("--- CHEQUE DE FIDELIDAD (label) ---")
    log(f"labels n={n_valid} | win_rate_neto={win_rate:.3f} "
        f"| toco_parcial={summ_total.get('pct_toco_parcial', 0):.2%} "
        f"| barrera_temporal={pct_time:.2%}")
    fid_ok = (n_valid >= 200 and 0.30 < win_rate < 0.90 and pct_time < 0.9)
    log(f"FIDELIDAD: {'OK -> se evalua' if fid_ok else 'FALLA -> NO se interpreta'}")
    if not fid_ok:
        log("\nAbortado por fidelidad del etiquetado.")
        log(f"\nOut: {out_path}")
        return

    merged = elig.merge(labels[["date", "symbol", "label"]], on=["date", "symbol"],
                        how="inner")
    log(f"Filas merged (factor+label: {len(merged)}")

    windows = {"TOTAL": (str(panel["date"].min()), str(panel["date"].max()))}
    windows.update({w: (a, b) for w, (a, b) in WINDOWS.items()})

    hallazgos = []
    log(f"\n{'factor':16s} {'ventana':>10s} {'n_dias':>6s} {'mean_IC':>9s} "
        f"{'SE_NW':>8s} {'t':>7s} {'L':>3s} {'sig(Bonf9)':>11s}")
    for factor, sign in FACTORS.items():
        for wname, (a, b) in windows.items():
            sub = merged[(merged["date"] >= a) & (merged["date"] <= b)]
            ics = daily_ics(sub, factor, "label")
            n = len(ics)
            lags = min(MAX_LAG, max(1, n // 8)) if n else 0
            res = summarize_ic(ics, lags)
            sig = (res["n_days"] >= 20 and not math.isnan(res["t"])
                   and abs(res["t"]) > Z_BONFERRONI_9
                   and np.sign(res["mean_ic"]) == sign)
            if sig:
                hallazgos.append((factor, wname, res))
            log(f"{factor:16s} {wname:>10s} {res['n_days']:6d} {res['mean_ic']:+9.4f} "
                f"{res['se_nw']:8.4f} {res['t']:+7.2f} {res['lags']:3d} {str(sig):>13s}")

    log("\n--- VEREDICTO (§23, pre-registrado) ---")
    log(f"Criterio: |t| > {Z_BONFERRONI_9:.2f} (Bonferroni-9 bilateral), signo esperado +1")
    if hallazgos:
        log(f"=> {len(hallazgos)} hallazgo(s): el target de barreras importa")
        for factor, wname, res in hallazgos:
            log(f"   {factor} @ {wname}: IC {res['mean_ic']:+.4f}, t-NW {res['t']:+.2f}")
        log("   -> candidato(s) a pre-registro de motor con el target de barreras.")
    else:
        log("=> Ningún factor cruza Bonferroni-9 en ninguna ventana con signo esperado.")
        log("   La hipótesis de generador vacío queda reforzada incluso contra el")
        log("   target binario de barreras que el motor persigue. Los |t|>2 nominales")
        log("   se reportan como contexto, nunca como hallazgo.")

    log(f"\nOut: {out_path}")


if __name__ == "__main__":
    main()
