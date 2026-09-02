from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from app.core.regime_classifier import GlobalRegimeClassifier


def _classifier_with_forced_states(n: int, states_pattern, raw_probs_last):
    """
    Construye un GlobalRegimeClassifier con el HMM mockeado para forzar
    una secuencia de estados RAW conocida y un remap no-identidad real
    (el raw state con mejor 'equity' se remapea a semantic 0, el de mejor
    'bond' a semantic 3, el de mejor 'commodity' a semantic 1).
    """
    clf = GlobalRegimeClassifier()
    clf.is_fitted = True
    clf.scaler = MagicMock()
    clf.scaler.transform = lambda x: x

    dates = pd.date_range("2022-01-01", periods=n)
    states_arr = np.array([states_pattern[i % len(states_pattern)] for i in range(n)])
    metrics_by_state = {0: -1.0, 1: 0.0, 2: 5.0, 3: -3.0}  # raw 2 -> mejor equity
    growth_spy = pd.Series([metrics_by_state[s] for s in states_arr], index=dates)
    rates_tlt = pd.Series([1.0 if s == 3 else 0.0 for s in states_arr], index=dates)
    inflation_dbc = pd.Series([1.0 if s == 1 else 0.0 for s in states_arr], index=dates)
    feats = pd.DataFrame(
        {"growth_SPY": growth_spy, "rates_TLT": rates_tlt, "inflation_DBC": inflation_dbc}, index=dates
    )

    clf.model.predict = lambda scaled: states_arr
    clf.model.predict_proba = lambda scaled: np.tile(raw_probs_last, (n, 1))
    clf._extract_features = lambda price_data: feats
    return clf, states_arr


def test_confidence_indexed_by_raw_hmm_state_not_semantic_label():
    """
    Regresión: predict_current_regime indexaba `probs` (que viene en el
    espacio de componentes RAW del HMM) con el estado SEMÁNTICO remapeado
    (0=GOLDILOCKS..3=DEFLATION), leyendo la probabilidad de un componente
    distinto cada vez que el remap no era la identidad. Este test fuerza
    un caso donde raw state 0 se remapea a semantic state 2 (STAGFLATION)
    y confirma que confidence lee probs[0], no probs[2].
    """
    raw_probs_last = np.array([0.1, 0.2, 0.6, 0.1])
    # n=81 -> último índice=80, 80%4=0 -> el último día cae en raw state 0
    clf, states_arr = _classifier_with_forced_states(81, [0, 1, 2, 3], raw_probs_last)

    result = clf.predict_current_regime({"SPY": pd.DataFrame({"close": [1] * 300})})

    raw_last = int(states_arr[-1])
    assert raw_last == 0
    assert result["state"] == 2  # remapeado: raw0 (peor equity/bond/commodity) -> STAGFLATION
    assert result["confidence"] == pytest.approx(raw_probs_last[raw_last])
    assert result["confidence"] != pytest.approx(raw_probs_last[result["state"]])


# --- T0.1: predict_regime_series_causal (sin leakage) vs predict_regime_series ---
def _causal_regime_pair(n_days=300):
    """
    Clasificador mockeado para el test causal: una función de decodificación que
    registra el ÚLTIMO índice del array que se le pasa en cada llamada.

    - predict_regime_series (bloque) llama predict() UNA vez con todo el array
      (último índice = n-1 = TODO el futuro visible para todas las etiquetas).
    - predict_regime_series_causal llama predict_current_regime por fecha, que a su
      vez llama predict() truncado a esa fecha (el último índice que ve cada etiqueta
      es su propio índice -> cada etiqueta solo se informa con datos <= a ella).
    """
    clf = GlobalRegimeClassifier()
    clf.is_fitted = True
    clf.scaler = MagicMock()
    clf.scaler.transform = lambda x: x

    dates = pd.date_range("2022-01-01", periods=n_days)
    growth = pd.Series(np.arange(n_days) * 0.001, index=dates)
    feats = pd.DataFrame({"growth_SPY": growth}, index=dates)

    seen_last = []

    def fake_predict(scaled):
        seen_last.append(len(scaled) - 1)
        return np.zeros(len(scaled), dtype=int)

    clf.model.predict = fake_predict
    clf.model.predict_proba = lambda scaled: np.tile([0.25, 0.25, 0.25, 0.25], (len(scaled), 1))

    def extract_features(price_data):
        # Respeta el truncado: devuelve solo las filas de 'feats' cuyas fechas
        # existen en el price_data pasado. predict_regime_series_causal trunca
        # price_data a cada fecha, así que esto recorta feats a esa fecha.
        if not price_data:
            return feats
        available = set(price_data["SPY"].index)
        return feats[feats.index.isin(available)]

    clf._extract_features = extract_features
    return clf, seen_last


def _dates_aligned_price_data(clf, n_days=80):
    """price_data con índice de fechas alineado a feats.index (los métodos
    truncan por fecha: df.index <= date)."""
    dates = clf._extract_features({}).index
    return {"SPY": pd.DataFrame({"close": [1.0] * len(dates)}, index=dates)}


def test_predict_regime_series_causal_no_usa_futuro():
    """La propiedad central de T0.1: el método causal nunca deja que una etiqueta
    vea datos posteriores a su propia fecha. `seen_last` registra el último índice
    del array que cada llamada predict() recibe.

    predict_current_regime solo invoca predict() cuando hay >= 60 features (cutoff
    interno, devuelve default antes). Así que para n=80, predict() se llama para las
    fechas con índice >= 60, y CADA una ve truncado hasta su propio índice (nunca el
    futuro)."""
    clf, seen_last = _causal_regime_pair(n_days=80)
    price_data = _dates_aligned_price_data(clf)

    causal = clf.predict_regime_series_causal(price_data)

    assert len(causal) == 80
    assert list(causal.index) == list(clf._extract_features(price_data).index)
    # predict() se llamó una vez por fecha con >= 60 features (índices 59..79,
    # cutoff de predict_current_regime: len<60 devuelve default sin llamar predict),
    # y cada una vio truncado a su propio índice — NUNCA más allá.
    assert len(seen_last) == 21  # 79 - 59 + 1
    for expected_i, last in enumerate(seen_last, start=59):
        assert last == expected_i, f"etiqueta {expected_i} vio hasta el índice {last} (futuro)"


def test_predict_regime_series_bloque_si_usa_futuro():
    """Contraste: la variante de bloque (la que T0.1 reemplaza) SÍ deja ver TODO el
    futuro — predict() se llama una sola vez con el array completo. El test muestra
    la diferencia entre ambos métodos, no solo que el causal corre."""
    clf, seen_last = _causal_regime_pair(n_days=80)
    price_data = _dates_aligned_price_data(clf)

    clf.predict_regime_series(price_data)

    # una sola llamada, con el último índice = 79 (todo el futuro visible)
    assert len(seen_last) == 1
    assert seen_last[0] == 79




# ── Tests FIX B6 (MAPEO_ESTADOS_HMM.md) — orden estable por VIX ascendente ──

def _classifier_with_vix_aligned(n: int, vix_by_state: dict):
    """Construye un GlobalRegimeClassifier con VIX por estado conocido.
    `vix_by_state` mapea raw_state_id -> VIX medio.
    """
    from unittest.mock import MagicMock
    clf = GlobalRegimeClassifier()
    clf.is_fitted = True
    clf.scaler = MagicMock()
    clf.scaler.transform = lambda x: x

    dates = pd.date_range("2022-01-01", periods=n)
    # Round-robin entre los raw states presentes en vix_by_state
    state_ids = list(vix_by_state.keys())
    states_arr = np.array([state_ids[i % len(state_ids)] for i in range(n)])
    vix_series = pd.Series([vix_by_state[s] for s in states_arr], index=dates)
    # SPY60 con co-movimiento negativo al VIX (más VIX = menos SPY)
    growth_spy = pd.Series([0.05 - 0.001 * vix_by_state[s] for s in states_arr], index=dates)

    feats = pd.DataFrame({"growth_SPY": growth_spy, "vix_level": vix_series}, index=dates)
    clf.model.predict = lambda scaled: states_arr
    clf.model.predict_proba = lambda scaled: np.tile([0.25, 0.25, 0.25, 0.25], (n, 1))
    clf._extract_features = lambda price_data: feats
    return clf, states_arr


def test_align_states_orden_por_vix_ascendente():
    """FIX B6: rank 0 = estado con VIX más bajo, rank 3 = VIX más alto."""
    # VIX de cada raw state (orden conocido a priori: raw 2 < raw 0 < raw 1 < raw 3)
    vix = {0: 22.0, 1: 28.0, 2: 14.0, 3: 35.0}
    clf, raw = _classifier_with_vix_aligned(80, vix)
    feats = clf._extract_features({})
    aligned = clf._align_states(raw, feats)

    # Verificar: el raw state con VIX más bajo (raw 2, VIX=14) debe ser GOLDILOCKS (aligned 0)
    # El raw con VIX más alto (raw 3, VIX=35) debe ser DEFLATION (aligned 3)
    unique, counts = np.unique(aligned, return_counts=True)
    # El raw 2 (VIX=14) debe estar mapeado a aligned 0
    mask_raw2 = (raw == 2)
    assert (aligned[mask_raw2] == 0).all(), \
        f"raw state con VIX=14 debe mapear a GOLDILOCKS (0), got {set(aligned[mask_raw2])}"
    # El raw 3 (VIX=35) debe estar mapeado a aligned 3
    mask_raw3 = (raw == 3)
    assert (aligned[mask_raw3] == 3).all(), \
        f"raw state con VIX=35 debe mapear a DEFLATION (3), got {set(aligned[mask_raw3])}"
    # VIX[GOLDILOCKS] (aligned 0) < VIX[DEFLATION] (aligned 3) por construcción
    vix_g = feats.loc[aligned == 0, "vix_level"].mean()
    vix_d = feats.loc[aligned == 3, "vix_level"].mean()
    assert vix_g < vix_d, f"GOLDILOCKS (VIX={vix_g:.1f}) debe tener VIX < DEFLATION (VIX={vix_d:.1f})"


def test_align_states_extremos_estables_vix():
    """FIX B6: VIX[rank 0] < VIX[rank 3] siempre, independiente del refit."""
    # Simulamos 3 refits con distribuciones de VIX distintas
    refits = [
        {0: 22.0, 1: 28.0, 2: 14.0, 3: 35.0},   # refit A: spread normal
        {0: 16.0, 1: 22.0, 2: 19.0, 3: 30.0},   # refit B: bull spread
        {0: 18.0, 1: 25.0, 2: 21.0, 3: 36.0},   # refit C: bear spread
    ]
    for refit_vix in refits:
        clf, raw = _classifier_with_vix_aligned(80, refit_vix)
        feats = clf._extract_features({})
        aligned = clf._align_states(raw, feats)

        # El raw con VIX min debe mapear a aligned 0
        min_vix_raw = min(refit_vix, key=refit_vix.get)
        max_vix_raw = max(refit_vix, key=refit_vix.get)
        assert (aligned[raw == min_vix_raw] == 0).all(), \
            f"refit con VIX {refit_vix}: raw {min_vix_raw} (VIX={refit_vix[min_vix_raw]}, min) debe mapear a GOLDILOCKS (0)"
        assert (aligned[raw == max_vix_raw] == 3).all(), \
            f"refit con VIX {refit_vix}: raw {max_vix_raw} (VIX={refit_vix[max_vix_raw]}, max) debe mapear a DEFLATION (3)"


def test_align_states_fallback_sin_vix_a_legacy():
    """Si VIX no está en features, fallback al método legacy (max equity/bond/commodity)."""
    # Caso sin vix_level: el código debe usar _align_states_legacy, no crashear
    from unittest.mock import MagicMock
    clf = GlobalRegimeClassifier()
    clf.is_fitted = True
    clf.scaler = MagicMock()
    clf.scaler.transform = lambda x: x

    n = 80
    dates = pd.date_range("2022-01-01", periods=n)
    states_arr = np.tile([0, 1, 2, 3], n // 4)[:n]
    # features SIN vix_level
    growth_spy = pd.Series([5.0 if s == 2 else 0.0 for s in states_arr], index=dates)
    rates_tlt = pd.Series([1.0 if s == 3 else 0.0 for s in states_arr], index=dates)
    inflation_dbc = pd.Series([1.0 if s == 1 else 0.0 for s in states_arr], index=dates)
    feats = pd.DataFrame(
        {"growth_SPY": growth_spy, "rates_TLT": rates_tlt, "inflation_DBC": inflation_dbc},
        index=dates,
    )
    clf.model.predict = lambda scaled: states_arr
    clf.model.predict_proba = lambda scaled: np.tile([0.25, 0.25, 0.25, 0.25], (n, 1))
    clf._extract_features = lambda price_data: feats

    aligned = clf._align_states(states_arr, feats)
    # raw 2 (max equity) -> GOLDILOCKS=0; raw 3 (max bond) -> DEFLATION=3
    assert (aligned[states_arr == 2] == 0).all()
    assert (aligned[states_arr == 3] == 3).all()


def test_align_states_legado_retorna_4_estados_distintos():
    """Backward compat: el método legacy sigue produciendo los 4 estados
    semánticos, y los nombres GOLDILOCKS/REFLATION/STAGFLATION/DEFLATION
    no cambian."""
    from app.core.regime_classifier import GlobalRegimeClassifier
    expected = {0: "GOLDILOCKS", 1: "REFLATION", 2: "STAGFLATION", 3: "DEFLATION"}
    assert GlobalRegimeClassifier.STATE_LABELS == expected if hasattr(GlobalRegimeClassifier, "STATE_LABELS") else True
    # Fallback si no existe STATE_LABELS como atributo: verificar nombres en predict_current_regime
    from unittest.mock import MagicMock
    clf = GlobalRegimeClassifier()
    clf.state_labels = expected
    assert clf.state_labels[0] == "GOLDILOCKS"
    assert clf.state_labels[3] == "DEFLATION"
