"""Tests de M7 — pipeline integrado M1+M2+M3 (app/core/diagnostic_pipeline.py).

Los dos tests que más importan acá no son "el pipeline corre" — son:
1. calibración y predicción de M2 nunca comparten fechas (verificado desde afuera,
   no solo confiado en el código).
2. la compuerta M3 es un AND explícito con la abstención de M2, nunca un OR — se
   verifica la ecuación booleana fila por fila sobre la salida real del pipeline.
"""
import numpy as np
import pandas as pd
import pytest
from app.core.diagnostic_pipeline import run_diagnostic_pipeline

MACRO_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG"]
STOCK_TICKERS = ["AAPL", "MSFT"]


def _synthetic_price_data(n_days=550, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n_days)
    data = {}
    for i, t in enumerate(MACRO_TICKERS + STOCK_TICKERS):
        drift = (i - 5) * 0.0003
        returns = rng.normal(drift, 0.012, n_days)
        close = 100 * np.cumprod(1 + returns)
        df = pd.DataFrame({"close": close}, index=dates)
        if t in STOCK_TICKERS:
            # M1 necesita atr14 -- una serie simple, no hace falta que sea el
            # indicador real, solo que tenga la forma correcta.
            df["atr14"] = pd.Series(close, index=dates).rolling(14).std().bfill()
        data[t] = df
    return data


def _synthetic_scores(price_data, seed=2):
    """Score sintético correlacionado con el retorno futuro cercano, para que M2
    tenga algo real que calibrar (no ruido puro)."""
    rng = np.random.default_rng(seed)
    scores = {}
    for t in STOCK_TICKERS:
        close = price_data[t]["close"]
        fwd = close.shift(-5) / close - 1
        noise = rng.normal(0, fwd.std() * 2, len(close))
        scores[t] = (fwd.fillna(0) + noise).rename("score")
    return scores


def test_price_data_vacio_falla():
    with pytest.raises(ValueError, match="price_data"):
        run_diagnostic_pipeline({}, {"AAPL": pd.Series(dtype=float)}, pd.Timestamp("2020-01-01"))


def test_scores_vacio_falla():
    price_data = _synthetic_price_data(n_days=100)
    with pytest.raises(ValueError, match="scores"):
        run_diagnostic_pipeline(price_data, {}, pd.Timestamp("2020-01-01"))


def test_sin_fechas_en_comun_falla():
    price_data = _synthetic_price_data(n_days=100)
    scores_futuros = {"AAPL": pd.Series([1.0], index=[pd.Timestamp("2099-01-01")])}
    with pytest.raises(ValueError, match="común"):
        run_diagnostic_pipeline(price_data, scores_futuros, pd.Timestamp("2020-01-01"))


def test_sin_favorable_states_es_igual_a_m1_m2_solos():
    """Invariante 1: sin M3 activo, la decisión de operar es EXACTAMENTE la
    negación de la abstención de M2 -- el gate no puede tocar nada."""
    price_data = _synthetic_price_data(n_days=400)
    scores = _synthetic_scores(price_data)
    cutoff = price_data["AAPL"].index[300]

    result = run_diagnostic_pipeline(price_data, scores, cutoff, favorable_states=None)

    assert (result.detalle["gate_operar"] == True).all()  # noqa: E712
    assert (result.detalle["operar"] == ~result.detalle["abstenerse_m2"]).all()


def test_calibracion_y_prediccion_nunca_comparten_fechas():
    """Invariante 2 (la que sostiene la garantía de cobertura de M2): ninguna
    fecha de calibración es >= cutoff, ninguna fecha de predicción es < cutoff."""
    price_data = _synthetic_price_data(n_days=400)
    scores = _synthetic_scores(price_data)
    cutoff = price_data["AAPL"].index[300]

    result = run_diagnostic_pipeline(price_data, scores, cutoff, favorable_states=None)

    fin_calibracion = pd.Timestamp(result.ventana_calibracion.split(" a ")[1])
    inicio_prediccion = pd.Timestamp(result.ventana_prediccion.split(" a ")[0])

    assert fin_calibracion < cutoff
    assert inicio_prediccion >= cutoff
    # Ninguna fecha del detalle (todas son predicción) cae antes del cutoff
    assert (result.detalle["date"] >= cutoff).all()


def test_compuerta_es_and_no_or_verificado_en_la_salida_real():
    """Invariante 3, la más importante: se verifica la ECUACIÓN booleana sobre la
    salida real del pipeline, no una expectativa estadística. Si algún día el
    cableado se cambia a OR por error, este test lo revienta."""
    price_data = _synthetic_price_data(n_days=550, seed=3)
    scores = _synthetic_scores(price_data, seed=4)
    cutoff = price_data["AAPL"].index[400]

    result = run_diagnostic_pipeline(
        price_data, scores, cutoff,
        favorable_states=frozenset({0, 1}),
        regime_recalib_every=70, regime_min_history=320,
    )

    esperado = (~result.detalle["abstenerse_m2"]) & result.detalle["gate_operar"]
    assert (result.detalle["operar"] == esperado).all()

    # Y la propiedad de negocio que la ecuación garantiza: nunca opera si el
    # régimen es desfavorable, sin importar qué diga M2.
    bloqueados_por_gate = result.detalle[~result.detalle["gate_operar"]]
    if len(bloqueados_por_gate) > 0:
        assert not bloqueados_por_gate["operar"].any()


def test_gate_con_todos_los_estados_favorables_nunca_bloquea_mas_que_sin_gate():
    price_data = _synthetic_price_data(n_days=550, seed=5)
    scores = _synthetic_scores(price_data, seed=6)
    cutoff = price_data["AAPL"].index[400]

    sin_gate = run_diagnostic_pipeline(price_data, scores, cutoff, favorable_states=None)
    con_gate_amplio = run_diagnostic_pipeline(
        price_data, scores, cutoff,
        favorable_states=frozenset({0, 1, 2, 3}),
        regime_recalib_every=70, regime_min_history=320,
    )
    assert con_gate_amplio.detalle["operar"].sum() <= sin_gate.detalle["operar"].sum()


def test_resumen_coincide_con_recalculo_manual():
    price_data = _synthetic_price_data(n_days=400, seed=7)
    scores = _synthetic_scores(price_data, seed=8)
    cutoff = price_data["AAPL"].index[300]

    result = run_diagnostic_pipeline(price_data, scores, cutoff, favorable_states=None)

    operados = result.detalle[result.detalle["operar"]]
    if len(operados) == 0:
        assert result.resumen["n_operados"] == 0
        return

    aciertos_manual = (np.sign(operados["point_estimate"]) == np.sign(operados["ret_net"]))
    aciertos_manual = aciertos_manual[operados["ret_net"] != 0]
    vpp_manual = aciertos_manual.sum() / len(operados)

    assert result.resumen["n_operados"] == len(operados)
    assert result.resumen["vpp"] == pytest.approx(vpp_manual, abs=1e-9)


def test_calibracion_con_muy_pocos_datos_falla_con_el_mismo_error_que_m2():
    price_data = _synthetic_price_data(n_days=60)
    scores = _synthetic_scores(price_data)
    cutoff = price_data["AAPL"].index[10]  # deja <30 filas de calibración

    with pytest.raises(ValueError, match="30"):
        run_diagnostic_pipeline(price_data, scores, cutoff, favorable_states=None)


def test_detalle_incluye_n_simbolos_correcto():
    price_data = _synthetic_price_data(n_days=400)
    scores = _synthetic_scores(price_data)
    cutoff = price_data["AAPL"].index[300]

    result = run_diagnostic_pipeline(price_data, scores, cutoff, favorable_states=None)
    assert result.n_simbolos == len(STOCK_TICKERS)
    assert set(result.detalle["symbol"].unique()) <= set(STOCK_TICKERS)
