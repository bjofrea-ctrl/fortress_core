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


