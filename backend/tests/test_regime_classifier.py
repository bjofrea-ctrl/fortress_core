import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

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


import pytest  # noqa: E402 (import al final para no interferir con el docstring del módulo)
