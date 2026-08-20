"""Tests de M3 — compuerta de régimen walk-forward (app/core/regime_gate.py).

El test que más importa acá NO es "clasifica bien el régimen" (eso ya lo prueba
GlobalRegimeClassifier en su propio código) — es que el walk-forward NUNCA usa datos
futuros para etiquetar una fecha pasada. Esa es la propiedad que este módulo existe
para garantizar.
"""
import inspect

import numpy as np
import pandas as pd
import pytest
from app.core.regime_gate import (
    WalkForwardDiagnostics,
    WalkForwardRegimeGate,
)

TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG"]


def _synthetic_price_data(n_days=400, seed=7):
    """Random walks con drift distinto por ticker para que el HMM tenga algo que
    diferenciar — no importa que sea realista, importa que tenga la forma correcta
    (columna 'close', índice de fechas hábiles)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n_days)
    data = {}
    for i, t in enumerate(TICKERS):
        drift = (i - len(TICKERS) / 2) * 0.0003
        returns = rng.normal(drift, 0.01, n_days)
        close = 100 * np.cumprod(1 + returns)
        data[t] = pd.DataFrame({"close": close}, index=dates)
    return data


def test_favorable_states_vacio_falla():
    with pytest.raises(ValueError, match="favorable_states"):
        WalkForwardRegimeGate(favorable_states=frozenset())


def test_historia_insuficiente_falla_explicito():
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0}), min_history=100, recalib_every=20)
    price_data = _synthetic_price_data(n_days=150)  # muy poco (bajo 252 feature-días que exige fit())
    with pytest.raises(ValueError, match="Historia insuficiente"):
        gate.label_series(price_data)


def test_walk_forward_recalibra_en_los_intervalos_declarados():
    price_data = _synthetic_price_data(n_days=365, seed=1)
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0}), min_history=255, recalib_every=20)
    _, diag = gate.label_series(price_data)

    assert isinstance(diag, WalkForwardDiagnostics)
    assert diag.n_recalibraciones >= 3
    # Las fechas de recalibración deben estar espaciadas ~recalib_every días hábiles
    dates = diag.fechas_recalibracion
    for a, b in zip(dates, dates[1:]):
        gap = (b - a).days
        assert 25 <= gap <= 45, f"gap entre recalibraciones {gap}d fuera de rango esperado (recalib_every=20)"


def test_ninguna_fecha_se_etiqueta_antes_de_su_recalibracion():
    """La propiedad central del módulo: anti-lookahead. Si esto pasara, el assert
    interno ya habría matado el test — acá se verifica el resultado publicado
    también respeta el invariante desde afuera."""
    price_data = _synthetic_price_data(n_days=340, seed=2)
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0, 1}), min_history=255, recalib_every=20)
    series, diag = gate.label_series(price_data)

    # Cada fecha etiquetada debe ser >= alguna fecha de recalibración <= ella misma
    for d in series.index:
        recalibs_validas = [r for r in diag.fechas_recalibracion if r <= d]
        assert len(recalibs_validas) > 0, f"fecha {d} etiquetada sin recalibración previa"


def test_label_series_usa_decodificacion_causal_no_de_bloque():
    """T0.1 (PLAN_INTEGRACION_INDICAGENT): label_series debe etiquetar día por día
    (predict_regime_series_causal), no decodificar el bloque completo en una sola
    llamada Viterbi (predict_regime_series, que filtra hasta recalib_every días de
    información futura). Verificamos que el método que label_series invoca es el
    causal — sin re-implementar el clasificador completo."""
    import app.core.regime_classifier as rc
    import app.core.regime_gate as rg

    # label_series construye su propio GlobalRegimeClassifier y le llama
    # predict_regime_series_causal; la variante de bloque (con leakage) NO debe
    # invocarse. Verificamos por inspección del método llamado (string en el
    # código fuente) + el invariante anti-lookahead ya cubierto por el test anterior.
    source = inspect.getsource(rg.WalkForwardRegimeGate.label_series)
    assert "predict_regime_series_causal" in source
    assert "predict_regime_series(predict_data)" not in source

    # El clasificador expone ambos métodos (causal y bloque) — el causal es el que
    # label_series usa.
    clf_methods = [m for m in dir(rc.GlobalRegimeClassifier) if "predict_regime_series" in m]
    assert "predict_regime_series_causal" in clf_methods


def test_operar_es_booleano_y_coincide_con_favorable_states():
    price_data = _synthetic_price_data(n_days=340, seed=3)
    # Declarar TODOS los estados como favorables -> operar debe ser True siempre
    gate_todo = WalkForwardRegimeGate(favorable_states=frozenset({0, 1, 2, 3}),
                                       min_history=255, recalib_every=20)
    series_todo, _ = gate_todo.label_series(price_data)
    assert series_todo.dtype == bool
    assert series_todo.all()

    # Declarar NINGUNO favorable (imposible por validación) -> probamos con un solo
    # estado que es improbable que domine, comparando contra "todos favorables"
    gate_uno = WalkForwardRegimeGate(favorable_states=frozenset({0}),
                                      min_history=255, recalib_every=20)
    series_uno, _ = gate_uno.label_series(price_data)
    # Con un solo estado favorable, operar=True nunca puede superar al caso "todos"
    assert series_uno.sum() <= series_todo.sum()


def test_distribucion_de_regimenes_suma_al_total_etiquetado():
    price_data = _synthetic_price_data(n_days=340, seed=4)
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0}), min_history=255, recalib_every=20)
    _, diag = gate.label_series(price_data)
    assert sum(diag.distribucion_regimenes.values()) == diag.n_fechas_etiquetadas


def test_label_symbol_dates_abstiene_fuera_de_rango():
    price_data = _synthetic_price_data(n_days=340, seed=5)
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0, 1, 2, 3}),
                                  min_history=255, recalib_every=20)

    fechas_validas = price_data["SPY"].index[150:160]
    fecha_futura_invalida = pd.Timestamp("2099-01-01")
    consulta = list(fechas_validas) + [fecha_futura_invalida]

    result = gate.label_symbol_dates(price_data, consulta)
    assert len(result) == len(consulta)
    # La fecha inventada, fuera de todo rango conocido, se abstiene (False) por defecto
    assert result.loc[fecha_futura_invalida] == False  # noqa: E712 (bool explícito intencional)


def test_label_symbol_dates_devuelve_serie_indexada_por_fecha():
    price_data = _synthetic_price_data(n_days=340, seed=6)
    gate = WalkForwardRegimeGate(favorable_states=frozenset({0, 1, 2, 3}),
                                  min_history=255, recalib_every=20)
    fechas = list(price_data["SPY"].index[150:155])
    result = gate.label_symbol_dates(price_data, fechas)
    assert list(result.index) == fechas
    assert result.dtype == bool
