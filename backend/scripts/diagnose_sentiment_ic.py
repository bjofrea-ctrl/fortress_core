"""
Diagnóstico ola 1 — Sentimiento (COT) y liquidez (FRED) vs retornos futuros.
Ola 2 — V1: AAII bull-bear spread (sentimiento directo del minorista).

Valida las hipótesis H5/H6 de la Fase E.1 v3:
- H5 (posicionamiento): el neto especulativo/retail/institucional del COT del
  E-MINI S&P 500 predice el retorno futuro del universo. La tesis del usuario:
  retail/inversores posicionados en el mismo lado del mercado = institución
  distribuye -> caída; posicionamiento en contra = institución acumula -> subida.
- H6 (liquidez): WALCL/reservas en crecimiento y reverse repo en caída (liquidez
  liberada) habilitan el mecanismo -> retornos futuros positivos; e interactúa
  con el sentimiento (2x2: liquidez alta/baja x sentimiento extremo).
- Ola 2 (V1, AAII): el sentimiento DIRECTO de la gente (encuesta bull-bear)
  debe comportarse como el usuario predice: sentimiento NEGATIVO -> la gente
  no compra -> el sistema compra barato -> la bolsa sube (máx. históricos en
  sentimiento bajo); sentimiento POSITIVO -> el sistema distribuye -> cae.
- H2': relación sentimiento -> posiciones: AAII alto/bajo vs COT retail neto
  (la gente actúa según su actitud; la institución se posiciona en contra).
- Paso 2 (cuestionar las demás variables): IC de momentum/RSI/ER DENTRO de cada
  bucket de sentimiento y de liquidez — si una variable pierde poder predictivo
  en un estado de sentimiento extremo, esa es la evidencia para modular su peso.

Misma disciplina que los demás diagnósticos: datos reales, IC con significancia
|IC| > 2/sqrt(n), dirección dictada por los datos, no por la narrativa.
"""
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

SENTIMENT_COLS = [
    "cot_lev_net_pct",
    "cot_asset_net_pct",
    "cot_retail_net_pct",
    "cot_dealer_net_pct",
    "walcl_growth_w",
    "wresbal_growth_w",
    "aaii_bullbear_spread",
]
LIQUIDITY_COLS = ["walcl_growth_w", "wresbal_growth_w"]


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
    """Tamaño de muestra efectivo (Newey-West, pesos Bartlett) para el IC.

    El panel repite el predictor semanal forward-filled (AAII) y solapa los
    retornos futuros (stride 5d contra horizonte h). Sin corrección, n=3633
    infla la significancia. Se estima la autocorrelación de z_t = (x-xbar)(y-ybar)
    por símbolo con L = ceil(horizon/stride) lags, y se suman los n_eff por
    símbolo (series entre sí casi independientes).
    """
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
        n_eff_sym = n / max(denom, 1 + L)  # piso: el peor caso rho=1 da 1+L
        total += n_eff_sym
    return max(total, 30.0)


def collect_records(price_data: dict, sentiment: pd.DataFrame) -> pd.DataFrame:
    records = []
    for symbol in SYMBOLS:
        df = price_data.get(symbol)
        if df is None:
            continue
        n = len(df)
        if n < WARMUP_DAYS + max(HORIZONS):
            continue
        for i in range(WARMUP_DAYS, n - max(HORIZONS), STRIDE_DAYS):
            date = df.index[i]
            if date not in sentiment.index:
                continue
            row = {"symbol": symbol}
            for col in SENTIMENT_COLS:
                row[col] = sentiment.loc[date, col]
            row["rsi14"] = df["rsi14"].iloc[i]
            row["momentum_12_1"] = df["momentum_12_1"].iloc[i] if "momentum_12_1" in df else np.nan
            row["er20"] = df["er20"].iloc[i]
            entry = df["close"].iloc[i]
            for h in HORIZONS + [1]:
                row[f"fwd_{h}"] = df["close"].iloc[i + h] / entry - 1
            records.append(row)
    return pd.DataFrame(records)


def report_univariate(records: pd.DataFrame, horizon: int):
    fwd = records[f"fwd_{horizon}"]
    n = len(records)
    print(f"\n  IC univariado {horizon}d (n={n}, base_ret={fwd.mean():+.4f}):")
    print(f"    {'col':22s} {'ic':>8s} {'rank_ic':>8s} {'n':>6s} {'n_eff':>7s} {'sig':>5s}")
    results = []
    for col in SENTIMENT_COLS:
        values = records[col]
        mask = values.notna()
        if mask.sum() < 100:
            print(f"    {col:22s}  n={mask.sum()} insuficiente")
            continue
        ic = SignalQualityMetrics.compute_ic(values[mask], fwd[mask])
        rank_ic = SignalQualityMetrics.compute_rank_ic(values[mask], fwd[mask])
        n_eff = newey_west_neff(records, col, horizon)
        thresh = significance_threshold(n_eff)
        sig = " ***" if abs(ic) > thresh else ""
        results.append((col, ic, rank_ic, mask.sum(), n_eff, sig))
    results.sort(key=lambda r: abs(r[1]), reverse=True)
    for col, ic, rank_ic, cnt, n_eff, sig in results:
        print(f"    {col:22s} {ic:+8.4f} {rank_ic:+8.4f} {cnt:6d} {n_eff:7.0f}{sig}")


def report_terciles(records: pd.DataFrame, horizon: int, col: str, label: str):
    sub = records[records[col].notna()].copy()
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    try:
        sub["bucket"] = pd.qcut(sub[col], 3, labels=["bajo", "medio", "alto"], duplicates="drop")
    except ValueError:
        return
    print(f"    [{label}] retorno {horizon}d por tercil de {col} (base={fwd.mean():+.4f}, n={len(sub)})"
          f" — EVIDENCIA DIRECCIONAL, sin significancia (autocorrelación semanal/solapada):")
    for bucket in ["bajo", "medio", "alto"]:
        cell = sub[sub["bucket"] == bucket]
        print(f"      {bucket:6s}  retorno={cell[f'fwd_{horizon}'].mean():+.4f}  n={len(cell)}")


def report_sentiment_to_positions(records: pd.DataFrame):
    """H2': ¿el sentimiento directo (AAII) anticipa el posicionamiento retail (COT)?
    Correlación contemporánea y rezagada — la gente actúa según su actitud."""
    sub = records[records[["aaii_bullbear_spread", "cot_retail_net_pct"]].notna().all(axis=1)]
    if len(sub) < 100:
        return
    print("\n  [H2'] sentimiento (AAII) -> posiciones (COT retail), Spearman:")
    for lag in [0, 1, 4, 8]:
        col = "cot_retail_net_pct"
        a = sub["aaii_bullbear_spread"]
        b = sub.groupby("symbol")[col].shift(lag)
        mask = a.notna() & b.notna()
        if mask.sum() < 100:
            continue
        rho = a[mask].corr(b[mask], method="spearman")
        print(f"    AAII hoy  vs  COT retail lag{lag}:  rho={rho:+.3f}  n={mask.sum()}")


def report_liquidity_x_sentiment(records: pd.DataFrame, horizon: int):
    """H6: tabla 2x2 liquidez (WALCL growth alta/baja) x retail COT (alto/bajo)."""
    sub = records[records[["walcl_growth_w", "cot_retail_net_pct"]].notna().all(axis=1)].copy()
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    try:
        sub["liq_bucket"] = pd.qcut(sub["walcl_growth_w"], 2, labels=["liq_baja", "liq_alta"], duplicates="drop")
        sub["ret_bucket"] = pd.qcut(sub["cot_retail_net_pct"], 2, labels=["ret_baja", "ret_alta"], duplicates="drop")
    except ValueError:
        return
    print(f"\n  [H6] 2x2 liquidez x retail COT, retorno {horizon}d (base={fwd.mean():+.4f}):")
    for liq in ["liq_baja", "liq_alta"]:
        row = []
        for ret in ["ret_baja", "ret_alta"]:
            cell = sub[(sub["liq_bucket"] == liq) & (sub["ret_bucket"] == ret)]
            row.append(f"{cell[f'fwd_{horizon}'].mean():+.4f} (n={len(cell)})")
        print(f"      {liq:9s} | ret_baja: {row[0]} | ret_alta: {row[1]}")


def report_liquidity_x_aaii(records: pd.DataFrame, horizon: int):
    """H6/V1: 2x2 liquidez x AAII bull-bear (sentimiento directo). La tesis
    del usuario: la celda 'sentimiento bajo x liquidez' (el sistema compra
    barato con liquidez disponible) debe ser la más alta."""
    sub = records[records[["walcl_growth_w", "aaii_bullbear_spread"]].notna().all(axis=1)].copy()
    if len(sub) < 150:
        return
    fwd = sub[f"fwd_{horizon}"]
    try:
        sub["liq_bucket"] = pd.qcut(sub["walcl_growth_w"], 2, labels=["liq_baja", "liq_alta"], duplicates="drop")
        sub["aaii_bucket"] = pd.qcut(sub["aaii_bullbear_spread"], 2, labels=["sent_baja", "sent_alta"], duplicates="drop")
    except ValueError:
        return
    print(f"\n  [H6/V1] 2x2 liquidez x AAII, retorno {horizon}d (base={fwd.mean():+.4f}):")
    for liq in ["liq_baja", "liq_alta"]:
        row = []
        for sent in ["sent_baja", "sent_alta"]:
            cell = sub[(sub["liq_bucket"] == liq) & (sub["aaii_bucket"] == sent)]
            row.append(f"{cell[f'fwd_{horizon}'].mean():+.4f} (n={len(cell)})")
        print(f"      {liq:9s} | sent_baja: {row[0]} | sent_alta: {row[1]}")


def report_conditional_ic(records: pd.DataFrame, horizon: int):
    """Paso 2: IC de momentum/rsi/er DENTRO de cada bucket de sentimiento y
    liquidez — el 'cuestionar las demás variables contra la principal'."""
    factors = [("momentum_12_1", "momentum"), ("rsi14", "rsi"), ("er20", "er")]
    for cond_col in ["cot_retail_net_pct", "cot_lev_net_pct", "walcl_growth_w", "aaii_bullbear_spread"]:
        sub = records[records[cond_col].notna()].copy()
        if len(sub) < 150:
            continue
        try:
            sub["bucket"] = pd.qcut(sub[cond_col], 3, labels=["bajo", "medio", "alto"], duplicates="drop")
        except ValueError:
            continue
        print(f"\n  [Paso 2] IC de cada factor DENTRO de buckets de {cond_col} ({horizon}d):")
        print(f"    {'bucket':7s} {'factor':10s} {'ic':>8s} {'n':>6s}")
        for bucket in ["bajo", "medio", "alto"]:
            cell = sub[sub["bucket"] == bucket]
            fwd = cell[f"fwd_{horizon}"]
            for col, name in factors:
                values = cell[col]
                mask = values.notna() & fwd.notna()
                if mask.sum() < 100:
                    continue
                ic = SignalQualityMetrics.compute_ic(values[mask], fwd[mask])
                print(f"    {bucket:7s} {name:10s} {ic:+8.4f} {mask.sum():6d}")


def _rank01(s: pd.Series) -> pd.Series:
    """Percentil rank en [0,1], centrado en 0 -> señal en [-1,1]."""
    r = s.rank(pct=True)
    return (r * 2 - 1).fillna(0.0)


def _score_from_rank(s: pd.Series) -> pd.Series:
    """Probabilidad empírica tipo motor: sigmoid del score (misma forma que
    _probability_from_score del motor, sin tocar el motor)."""
    import numpy as _np

    return 1.0 / (1.0 + _np.exp(-1.5 * s))


V1_DOMINANCE = 0.50  # peso pre-registrado del plan v4.2 (límite inferior del rango 50-70%)


def _norm_pvalue(z: float) -> float:
    """p-value de dos colas con distribución normal (sin dependencias extra)."""
    import math

    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def diebold_mariano_nw(p1: np.ndarray, p2: np.ndarray, y: np.ndarray, horizon: int) -> float:
    """Test de Diebold-Mariano sobre el diff de Brier, con varianza Newey-West.

    d_t = (p1-y)^2 - (p2-y)^2  (negativo = G2 mejor calibrado).
    H0: media de d = 0 (misma calidad de probabilidad). Varianza NW con pesos
    Bartlett y L = ceil(horizon/stride) lags para errores solapados. Retorna
    el p-value de dos colas.
    """
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
        w = 1 - j / (L + 1)
        var += 2 * w * gamma_j
    if var <= 0:
        return 1.0
    t = dbar / np.sqrt(var / n)
    return _norm_pvalue(t)


def report_block_test(records: pd.DataFrame):
    """H7 (plan v4.2): prueba de bloques — ¿V1 con efecto dominante mejora la
    calidad probabilística del motor frente al baseline de pesos actuales?

    Grupo 1 (baseline): señales existentes con pesos RELATIVOS actuales del
      régimen (REGIME_WEIGHTS[0]): momentum .35, reversion .10, liquidez .05,
      sentimiento-posiciones .10 -> normalizados a suma 1.
    Grupo 2 (hipótesis): Grupo 1 + V1 (AAII) con peso PRE-REGISTRADO
      V1_DOMINANCE = 0.50. Sin barrido de pesos: probar 0.60/0.70 y quedarse
      con el mejor sería multiple testing (mismo problema que el deflated
      Sharpe). La señal V1 entra con el signo que dictan los datos.

    Métricas: Brier por horizonte 1/5/20/60d, con significancia del diff de
    Brier vía Diebold-Mariano + varianza Newey-West (corrige solapamiento).

    VEREDICTO PRE-REGISTRADO:
      - V1 integra con 0.50 si p<0.05 en >=1 horizonte Y diff<0 en >=3/4.
      - Dirección consistente sin significancia -> recalibrar (30-50%).
      - Si no -> descartar.
    """
    engine_w = {
        "momentum_12_1": 0.35,
        "rsi14": 0.10,
        "walcl_growth_w": 0.05,
        "cot_retail_net_pct": 0.10,
    }
    tot = sum(engine_w.values())
    w1 = {k: v / tot for k, v in engine_w.items()}

    sub = records[["momentum_12_1", "rsi14", "walcl_growth_w", "cot_retail_net_pct", "aaii_bullbear_spread"] + [f"fwd_{h}" for h in HORIZONS + [1]]].copy()

    s_mom = _rank01(sub["momentum_12_1"])
    s_rsi = -_rank01(sub["rsi14"])  # sobrecompra -> señal negativa (reversion)
    s_liq = _rank01(sub["walcl_growth_w"])
    s_ret = _rank01(sub["cot_retail_net_pct"])
    s_v1 = -_rank01(sub["aaii_bullbear_spread"])  # IC negativo: pesimismo -> sube

    score1 = (w1["momentum_12_1"] * s_mom + w1["rsi14"] * s_rsi +
              w1["walcl_growth_w"] * s_liq + w1["cot_retail_net_pct"] * s_ret)
    score2 = (1 - V1_DOMINANCE) * score1 + V1_DOMINANCE * s_v1

    print("\n" + "=" * 72)
    print("[H7] PRUEBA DE BLOQUES — V1 pre-registrado 0.50 vs baseline (pesos actuales)")
    print(f"    Grupo 1 (baseline): momentum {w1['momentum_12_1']:.2f}, reversion {w1['rsi14']:.2f}, "
          f"liquidez {w1['walcl_growth_w']:.2f}, posiciones {w1['cot_retail_net_pct']:.2f}")
    print(f"    Grupo 2: 0.50*G1 + 0.50*V1  (peso fijo, SIN barrido)")
    print(f"    {'horizon':8s} {'grupo':9s} {'brier':>7s} {'acc_dir':>8s} {'ic_score':>9s} {'dm_p':>7s} {'n':>6s}")

    wins = 0
    sig = 0
    n_horizons = 0
    for h in HORIZONS + [1]:
        fwd = sub[f"fwd_{h}"]
        mask = fwd.notna()
        if mask.sum() < 100:
            continue
        n_horizons += 1
        y = (fwd[mask] > 0).astype(float).to_numpy()
        rows = []
        for label, score in [("G1", score1), ("G2/50", score2)]:
            s = score[mask].to_numpy()
            p = _score_from_rank(pd.Series(s)).to_numpy()
            brier = float(((p - y) ** 2).mean())
            acc = float(((s > 0) == (fwd[mask].to_numpy() > 0)).mean())
            ic = SignalQualityMetrics.compute_ic(pd.Series(s), fwd[mask])
            rows.append((label, brier, acc, ic))
        p1 = _score_from_rank(score1[mask]).to_numpy()
        p2 = _score_from_rank(score2[mask]).to_numpy()
        dm_p = diebold_mariano_nw(p1, p2, y, h)
        for label, brier, acc, ic in rows:
            print(f"    {h:8d} {label:9s} {brier:.4f} {acc:.4f} {ic:+9.4f} {dm_p:7.3f} {int(mask.sum()):6d}")
        if rows[1][1] < rows[0][1]:
            wins += 1
        if dm_p < 0.05:
            sig += 1

    print(f"    -> G2/50 gana en Brier en {wins}/{n_horizons} horizontes; diff significativo (p<0.05) en {sig}/{n_horizons}")
    if sig >= 1 and wins >= 3:
        print("    -> VEREDICTO: V1 se integra con peso dominante 0.50")
    elif wins >= 3:
        print("    -> VEREDICTO PARCIAL: dirección consistente sin significancia -> recalibrar (30-50%)")
    else:
        print("    -> VEREDICTO: V1 no mejora el baseline, descartar o revisar")


def main():
    print("Descargando datos...")
    price_data = load_universe(SYMBOLS, "2019-01-01", "2024-12-31")
    indicators_cache = {s: build_full_indicators(df) for s, df in price_data.items()}

    trading_dates = indicators_cache["SPY"].index
    print("Construyendo panel de sentimiento/liquidez (FRED + COT)...")
    sentiment = build_sentiment_frame(trading_dates)
    print(f"Panel: {len(sentiment)} filas, {len(sentiment.columns)} columnas")
    print(sentiment[["cot_retail_net_pct", "cot_lev_net_pct", "walcl_growth_w"]].describe().to_string())

    records = collect_records(indicators_cache, sentiment)
    print(f"Registros totales: {len(records)}")

    for horizon in HORIZONS:
        print(f"\n{'='*72}\n=== HORIZONTE {horizon}d ===")
        report_univariate(records, horizon)
        for col in ["cot_retail_net_pct", "cot_lev_net_pct", "walcl_growth_w", "aaii_bullbear_spread"]:
            report_terciles(records, horizon, col, f"terciles {col}")
        report_liquidity_x_sentiment(records, horizon)
        report_liquidity_x_aaii(records, horizon)
        report_conditional_ic(records, horizon)

    report_sentiment_to_positions(records)
    report_block_test(records)

    print("\nInterpretación:")
    print("- H5: si el IC de cot_*_net es NEGATIVO, posicionamiento alto (retail/specs")
    print("  comprados) predice caída — confirma 'instituciones distribuyen a retail'.")
    print("- H6: si walcl_growth_w es POSITIVO, más liquidez -> retornos más altos;")
    print("  la celda liq_alta x ret_baja debe ser la más alta del 2x2.")
    print("- V1/AAII: si aaii_bullbear_spread es NEGATIVO, sentimiento bajo de la gente")
    print("  predice SUBIDA (el sistema compra barato y el mercado sube sin ellos);")
    print("  la celda liq x sent_baja debe ser la más alta del 2x2 (H6/V1).")


if __name__ == "__main__":
    main()
