"""Tests de M1 — etiquetado por barreras (app/core/barrier_labeling.py).

El objetivo de estos tests NO es cubrir líneas: es probar que las barreras replican
`adaptive_risk.check_all_stops` con fidelidad, incluida la PRIORIDAD entre ellas.
Cada test construye una serie de precios donde se sabe de antemano qué barrera debe
disparar y en qué barra.
"""
import numpy as np
import pandas as pd
import pytest
from app.core.barrier_labeling import (
    ABSOLUTE_CEILING,
    REGIME_POSITION_STOP,
    label_entry,
    label_symbol,
    summarize,
    verify_fidelity,
)


def _flat_atr(n, value=1.0):
    return np.full(n, value)


def test_stop_de_regimen_dispara_en_la_barra_correcta():
    # Entrada 100. Stop régimen 0 = 5% -> cierra cuando el cierre toca 95 o menos.
    closes = np.array([100.0, 99.0, 97.0, 94.0, 120.0])
    out = label_entry(closes, _flat_atr(5, 50.0), 0, position_stop=0.05)
    assert out.exit_reason == "REGIME_STOP_HIT"
    assert out.exit_index == 3          # la barra de 94, no la de 97
    assert out.ret_net < 0
    assert out.label == -1


def test_techo_absoluto_tiene_prioridad_sobre_stop_de_regimen():
    # Caída que supera el techo absoluto y el stop de régimen en la MISMA barra.
    # El motor evalúa el techo PRIMERO, así que esa debe ser la razón.
    # El precio se deriva de la constante: si alguien cambia el techo, el test sigue.
    bajo_el_techo = 100.0 * (1.0 - ABSOLUTE_CEILING - 0.03)
    closes = np.array([100.0, bajo_el_techo, bajo_el_techo - 5])
    out = label_entry(closes, _flat_atr(3, 50.0), 0, position_stop=0.05)
    assert out.exit_reason == "ABSOLUTE_CEILING_BREACH"
    assert out.exit_index == 1


def test_stop_de_regimen_depende_del_regimen():
    # -4%: dispara el stop del régimen 3 (3%) pero NO el del régimen 0 (5%).
    closes = np.array([100.0, 96.0, 101.0, 102.0])
    atr = _flat_atr(4, 50.0)

    r3 = label_entry(closes, atr, 0, position_stop=REGIME_POSITION_STOP[3])
    assert r3.exit_reason == "REGIME_STOP_HIT"

    r0 = label_entry(closes, atr, 0, position_stop=REGIME_POSITION_STOP[0])
    assert r0.exit_reason != "REGIME_STOP_HIT"


def test_toma_parcial_no_cierra_la_posicion():
    # ATR=1 -> PARTIAL_TP a +2. Sube a 103 (dispara) y sigue sin tocar otra barrera.
    closes = np.array([100.0, 103.0, 103.5, 104.0])
    out = label_entry(closes, _flat_atr(4, 1.0), 0, position_stop=0.05, max_horizon=10)
    assert out.partial_tp_hit is True
    assert out.exit_reason == "TIME_BARRIER"   # no salió por la parcial
    assert out.exit_index == 3


def test_trailing_stop_se_arma_recien_tras_superar_1_5_atr():
    # ATR=1. Sube a 102 (max-entry=2 > 1.5 -> arma). Trailing = 102-2 = 100.
    # Cae a 99.5 <= 100 -> TRAILING_STOP.
    closes = np.array([100.0, 102.0, 99.5, 99.4])
    out = label_entry(closes, _flat_atr(4, 1.0), 0, position_stop=0.50)
    assert out.exit_reason == "TRAILING_STOP"
    assert out.exit_index == 2


def test_trailing_no_dispara_si_nunca_se_armo():
    # ATR=10 -> hace falta subir >15 para armar. Sube 1 y baja: nunca se arma.
    closes = np.array([100.0, 101.0, 99.0, 98.5])
    out = label_entry(closes, _flat_atr(4, 10.0), 0, position_stop=0.50, max_horizon=10)
    assert out.exit_reason == "TIME_BARRIER"


def test_barrera_temporal_se_marca_como_artificial():
    closes = np.array([100.0, 100.1, 100.2, 100.3])
    out = label_entry(closes, _flat_atr(4, 50.0), 0, position_stop=0.50, max_horizon=2)
    assert out.exit_reason == "TIME_BARRIER"
    assert out.hit_time_barrier is True
    assert out.bars_held == 2


def test_no_evalua_la_barra_de_entrada_evita_lookahead():
    # Si la barra de entrada se evaluara, este -20% cerraría en la barra 0.
    # Debe evaluarse recién desde la barra 1.
    closes = np.array([100.0, 80.0])
    out = label_entry(closes, _flat_atr(2, 50.0), 0, position_stop=0.05)
    assert out.exit_index == 1
    assert out.bars_held == 1


def test_neto_es_menor_que_bruto_por_los_costos():
    closes = np.array([100.0, 110.0, 110.0])
    out = label_entry(closes, _flat_atr(3, 50.0), 0, position_stop=0.50,
                      max_horizon=2, cost_per_side=0.0015)
    assert out.ret_gross > out.ret_net
    assert out.ret_gross == pytest.approx(0.10, abs=1e-9)


def test_costo_cero_hace_neto_igual_a_bruto():
    closes = np.array([100.0, 107.0, 107.0])
    out = label_entry(closes, _flat_atr(3, 50.0), 0, position_stop=0.50,
                      max_horizon=2, cost_per_side=0.0)
    assert out.ret_net == pytest.approx(out.ret_gross, abs=1e-12)


def test_con_parcial_el_retorno_promedia_las_dos_patas():
    # ATR=1: parcial en 102 (vende mitad). Barrera temporal cierra el resto en 110.
    # Bruto esperado = 0.5*(0.02) + 0.5*(0.10) = 0.06
    closes = np.array([100.0, 102.0, 110.0])
    out = label_entry(closes, _flat_atr(3, 1.0), 0, position_stop=0.50,
                      max_horizon=2, cost_per_side=0.0)
    assert out.partial_tp_hit is True
    assert out.ret_gross == pytest.approx(0.06, abs=1e-9)


def test_entrada_al_borde_del_panel_devuelve_none():
    closes = np.array([100.0, 101.0])
    assert label_entry(closes, _flat_atr(2), 1) is None   # última barra
    assert label_entry(closes, _flat_atr(2), 5) is None   # fuera de rango


def test_label_symbol_produce_una_fila_por_fecha_evaluable():
    n = 30
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "close": np.linspace(100, 130, n),
        "atr14": np.full(n, 1.0),
    }, index=idx)
    out = label_symbol(df, max_horizon=5)
    assert len(out) == n - 1          # la última barra no es evaluable
    assert {"date", "exit_reason", "ret_net", "label"} <= set(out.columns)


def test_label_symbol_usa_la_serie_de_regimen_cuando_se_provee():
    n = 12
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Caída sostenida de ~4% diario: dispara stop de régimen 3 antes que el de régimen 0
    closes = 100 * (0.96 ** np.arange(n))
    df = pd.DataFrame({"close": closes, "atr14": np.full(n, 50.0)}, index=idx)

    r0 = label_symbol(df, regimes=[0] * n, max_horizon=10)
    r3 = label_symbol(df, regimes=[3] * n, max_horizon=10)
    # Con stop 3% se sale antes (o igual) que con stop 5%
    assert r3["bars_held"].mean() <= r0["bars_held"].mean()


def test_label_symbol_exige_las_columnas():
    df = pd.DataFrame({"close": [1.0, 2.0]})
    with pytest.raises(ValueError, match="Faltan columnas"):
        label_symbol(df)


def test_summarize_reporta_peso_de_la_barrera_artificial():
    n = 20
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "close": np.full(n, 100.0),      # plano: nada dispara salvo el tiempo
        "atr14": np.full(n, 50.0),
    }, index=idx)
    s = summarize(label_symbol(df, max_horizon=3))
    assert s["pct_barrera_temporal"] == pytest.approx(1.0)
    assert s["n"] == n - 1


def test_summarize_con_dataframe_vacio():
    assert summarize(pd.DataFrame())["n"] == 0


def test_verify_fidelity_verifica_espejo_con_adaptive_risk():
    # El contrato de fidelidad del módulo (T0.2): las reglas de barrera deben
    # espejar adaptive_risk.check_all_stops. verify_fidelity() lo comprueba.
    result = verify_fidelity()
    assert result["fidelity_ok"] is True
    assert result["issues"] == []
