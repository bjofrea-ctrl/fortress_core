"""Tests de M2 — instrumento conforme (app/core/conformal.py).

El test que más importa NO es "el código corre" — es "la cobertura empírica se
acerca a la nominal". Un instrumento de abstención que promete 90% de cobertura
y da 60% está mintiendo, y eso es peor que no tener instrumento.
"""
import numpy as np
import pytest
from app.core.conformal import (
    ConformalAbstentionEngine,
    vpp_bajo_abstencion,
)


def _synthetic_linear_data(n=2000, noise_std=0.02, seed=42):
    """score y=0.05*score+ruido gaussiano — relación real conocida para poder
    verificar que la calibración recupera cobertura correcta."""
    rng = np.random.default_rng(seed)
    scores = rng.uniform(-1, 1, n)
    outcomes = 0.05 * scores + rng.normal(0, noise_std, n)
    return scores, outcomes


def test_calibrate_exige_minimo_de_muestras():
    engine = ConformalAbstentionEngine()
    with pytest.raises(ValueError, match="< 30"):
        engine.calibrate([0.1] * 10, [0.01] * 10)


def test_calibrate_exige_igual_longitud():
    engine = ConformalAbstentionEngine()
    with pytest.raises(ValueError, match="igual longitud"):
        engine.calibrate([0.1] * 50, [0.01] * 40)


def test_alpha_fuera_de_rango_falla():
    with pytest.raises(ValueError, match="alpha"):
        ConformalAbstentionEngine(alpha=1.5)
    with pytest.raises(ValueError, match="alpha"):
        ConformalAbstentionEngine(alpha=0.0)


def test_predict_sin_calibrar_falla_ruidoso():
    engine = ConformalAbstentionEngine()
    with pytest.raises(RuntimeError, match="sin calibrar"):
        engine.predict(0.5)


def test_cobertura_empirica_se_acerca_a_la_nominal_90():
    """El test central del módulo. Calibra con 1000, valida con 1000 DISTINTOS
    (nunca el mismo set para calibración y validación — es lo que sostiene la
    garantía)."""
    scores, outcomes = _synthetic_linear_data(n=2000, seed=1)
    calib_s, calib_o = scores[:1000], outcomes[:1000]
    val_s, val_o = scores[1000:], outcomes[1000:]

    engine = ConformalAbstentionEngine(alpha=0.10)
    engine.calibrate(calib_s, calib_o)

    coverage = engine.empirical_coverage(val_s, val_o)
    # Tolerancia razonable para n=1000 (error estándar del binomial ~1%)
    assert 0.85 <= coverage <= 0.95, f"cobertura {coverage:.3f} lejos del 90% nominal"


def test_cobertura_empirica_80_tambien_calibra():
    scores, outcomes = _synthetic_linear_data(n=2000, seed=2)
    calib_s, calib_o = scores[:1000], outcomes[:1000]
    val_s, val_o = scores[1000:], outcomes[1000:]

    engine = ConformalAbstentionEngine(alpha=0.20)  # 80% nominal
    engine.calibrate(calib_s, calib_o)

    coverage = engine.empirical_coverage(val_s, val_o)
    assert 0.74 <= coverage <= 0.86, f"cobertura {coverage:.3f} lejos del 80% nominal"


def test_intervalo_mas_ancho_con_mas_ruido():
    """Más ruido en los outcomes debe producir intervalos más anchos — sanity
    check de que el instrumento reacciona a la incertidumbre real, no a un
    número fijo."""
    s_bajo, o_bajo = _synthetic_linear_data(n=500, noise_std=0.01, seed=3)
    s_alto, o_alto = _synthetic_linear_data(n=500, noise_std=0.10, seed=3)

    e_bajo = ConformalAbstentionEngine(alpha=0.10, max_interval_width=999)
    e_bajo.calibrate(s_bajo, o_bajo)
    e_alto = ConformalAbstentionEngine(alpha=0.10, max_interval_width=999)
    e_alto.calibrate(s_alto, o_alto)

    p_bajo = e_bajo.predict(0.5)
    p_alto = e_alto.predict(0.5)
    assert p_alto.interval_width > p_bajo.interval_width


def test_abstencion_dispara_sobre_el_umbral():
    scores, outcomes = _synthetic_linear_data(n=500, seed=4)
    engine = ConformalAbstentionEngine(alpha=0.10, max_interval_width=0.001)
    engine.calibrate(scores, outcomes)
    pred = engine.predict(0.5)
    assert pred.abstenerse is True
    assert "supera el umbral" in pred.razon


def test_no_abstencion_bajo_el_umbral():
    scores, outcomes = _synthetic_linear_data(n=500, seed=5)
    engine = ConformalAbstentionEngine(alpha=0.10, max_interval_width=999.0)
    engine.calibrate(scores, outcomes)
    pred = engine.predict(0.5)
    assert pred.abstenerse is False
    assert "dentro del umbral" in pred.razon


def test_umbral_default_es_el_doble_de_la_mediana_de_residuos():
    scores, outcomes = _synthetic_linear_data(n=500, seed=6)
    engine = ConformalAbstentionEngine(alpha=0.10)
    calib = engine.calibrate(scores, outcomes)
    assert engine.max_interval_width == pytest.approx(2.0 * calib.residuals_median)


def test_calibracion_reporta_metadatos_correctos():
    scores, outcomes = _synthetic_linear_data(n=500, seed=7)
    engine = ConformalAbstentionEngine(alpha=0.10)
    calib = engine.calibrate(scores, outcomes)
    assert calib.n_calibration == 500
    assert calib.alpha == 0.10
    assert calib.residuals_p90 >= calib.residuals_median


def test_vpp_bajo_abstencion_separa_acierto_de_decision_de_operar():
    scores, outcomes = _synthetic_linear_data(n=500, seed=8)
    engine = ConformalAbstentionEngine(alpha=0.10)
    engine.calibrate(scores, outcomes)

    # Umbral muy laxo: el instrumento opera casi siempre
    engine.max_interval_width = 999.0
    preds = [engine.predict(s) for s in scores]
    result = vpp_bajo_abstencion(preds, outcomes)

    assert result["n_total"] == 500
    assert result["tasa_abstencion"] < 0.05
    assert 0.0 <= result["vpp"] <= 1.0


def test_vpp_bajo_abstencion_total_devuelve_nan_no_crash():
    scores, outcomes = _synthetic_linear_data(n=500, seed=9)
    engine = ConformalAbstentionEngine(alpha=0.10, max_interval_width=0.0)
    engine.calibrate(scores, outcomes)
    preds = [engine.predict(s) for s in scores]
    result = vpp_bajo_abstencion(preds, outcomes)
    assert result["n_operados"] == 0
    assert np.isnan(result["vpp"])


def test_vpp_bajo_abstencion_longitudes_distintas_falla():
    with pytest.raises(ValueError, match="igual longitud"):
        vpp_bajo_abstencion([], [1.0])


def test_calibrar_dos_veces_reemplaza_la_calibracion_anterior():
    s1, o1 = _synthetic_linear_data(n=500, noise_std=0.01, seed=10)
    s2, o2 = _synthetic_linear_data(n=500, noise_std=0.20, seed=10)

    engine = ConformalAbstentionEngine(alpha=0.10)
    engine.calibrate(s1, o1)
    width_1 = engine.predict(0.5).interval_width

    engine.max_interval_width = None  # forzar recalculo del default con la 2da calibracion
    engine.calibrate(s2, o2)
    width_2 = engine.predict(0.5).interval_width

    assert width_2 > width_1


def test_prediccion_puntual_sigue_la_pendiente_conocida():
    """Con relacion lineal conocida (y=0.05x), el punto estimado debe acercarse
    a esa pendiente — no es el foco del modulo pero si esta muy lejos, algo esta mal."""
    scores, outcomes = _synthetic_linear_data(n=2000, noise_std=0.005, seed=11)
    engine = ConformalAbstentionEngine(alpha=0.10)
    engine.calibrate(scores, outcomes)
    pred = engine.predict(1.0)
    assert pred.point_estimate == pytest.approx(0.05, abs=0.01)
