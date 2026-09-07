"""Tests de B5 (PLAN_REMEDIO_BRECHAS_20260903 §B5) — gate de potencia ex-ante MDE.

Cobertura:
  - matemática del MDE_IC: decrece con más símbolos/fechas, crece con el
    horizonte (solapamiento) y con Bonferroni (más trials de la familia);
  - fórmula del ruido puro (sigma_IC = 1/sqrt(n-1)) y T efectivo;
  - diseño bien dimensionado -> ejecutable; sub-potente -> INEJECUTABLE;
  - GATE DEL PRE-REGISTRO (el test que pide el ticket): un trial con diseño
    sub-potente se registra como STATUS_INEJECUTABLE — no consume slot
    Bonferroni (consumed_budget no cambia) ni cuenta como refutación (sin
    veredicto, y no puede ser objetivo de re_test);
  - diseño bien dimensionado se registra RESERVED normal;
  - sin diseno_mde declarado no se juzga (backward-compat, patrón B4);
  - diseno_mde malformado falla ruidoso;
  - cálculo aplicado: el gate de diciembre es matemáticamente casi imposible.
"""
import math
from datetime import date

import pytest
from app.core.trial_registry import (
    STATUS_INEJECUTABLE,
    STATUS_RESERVED,
    TrialRegistryError,
    all_trials,
    consumed_budget,
    register_trial_reservation,
)
from scripts.mde_power import (
    DEFAULT_EFFECT_PLAUSIBLE,
    effective_T,
    gate_diciembre_2026,
    ic_null_std,
    mde_ic,
)

_UMBRAL = "DSR>=0.90 2/3 ventanas (n_trials=17)"


def _res_entry(**overrides):
    entry = {
        "id": "trial_b5_x",
        "fecha": "2026-08-14",
        "familia": "motor_signal",
        "hipotesis": "hipotesis de prueba B5",
        "n_trials_consumidos": 1,
        "umbral_aplicado": _UMBRAL,
        "seccion_doc": "§b5",
        "status": "RESERVED",
    }
    entry.update(overrides)
    return entry


def _preregistro():
    return (
        "# Pre-registro B5\n## Criterio de exito\n"
        f"umbral_aplicado: {_UMBRAL}\n## Diseno\n"
    )


# ------------------------------------------------------------ matemática MDE

def test_mde_decrece_con_mas_fechas_y_simbolos():
    base = mde_ic(n_symbols=50, T_dates=60, horizon_days=1)["mde_ic"]
    mas_fechas = mde_ic(n_symbols=50, T_dates=250, horizon_days=1)["mde_ic"]
    mas_simbolos = mde_ic(n_symbols=200, T_dates=60, horizon_days=1)["mde_ic"]
    # más datos (fechas O símbolos) -> detecta efectos MENORES (MDE menor)
    assert mas_fechas < mas_simbolos < base


def test_mde_crece_con_horizonte_solapado_y_bonferroni():
    iid = mde_ic(n_symbols=50, T_dates=250, horizon_days=1, n_family=1)["mde_ic"]
    overlap = mde_ic(n_symbols=50, T_dates=250, horizon_days=20, n_family=1)["mde_ic"]
    bonferroni = mde_ic(n_symbols=50, T_dates=250, horizon_days=1, n_family=30)["mde_ic"]
    assert overlap > iid  # retornos solapados: menos obs independientes
    assert bonferroni > iid  # más trials de la familia: umbral más duro


def test_mde_ic_bien_dimensionado_detecta_el_rango_realista():
    """El diseño estándar del proyecto (50 símbolos, 250 fechas, horizonte
    diario, familia de 17) debe detectar ICs del rango realista 0.02-0.08
    (brecha #1 del plan): el MDE queda por debajo del techo del rango."""
    m = mde_ic(n_symbols=50, T_dates=250, horizon_days=1, n_family=17)
    assert m["ejecutable"] is True
    assert m["mde_ic"] < 0.05  # detecta la mayor parte del rango realista
    assert m["mde_ic"] == pytest.approx(0.0249, abs=1e-3)  # valor exacto estable


def test_mde_ic_sub_potente_supera_el_efecto_plausible():
    m = mde_ic(n_symbols=50, T_dates=250, horizon_days=20, n_family=17)
    assert m["ejecutable"] is False
    assert m["mde_ic"] > DEFAULT_EFFECT_PLAUSIBLE
    assert m["inejecutable_reason"]  # la razón queda documentada en el dict


def test_effective_T_horizonte_y_newey_west():
    assert effective_T(250, 1, None) == 250.0
    assert effective_T(250, 5, None) == 50.0  # solapamiento: T/h
    # Newey-West con rho_1=0.25: divide por 1.5
    assert effective_T(60, 1, {1: 0.25}) == pytest.approx(40.0)


def test_ic_null_std_formula_ruido_puro():
    assert ic_null_std(50) == pytest.approx(1.0 / math.sqrt(49))
    assert ic_null_std(3) == pytest.approx(1.0 / math.sqrt(2))  # piso n-1=2


# --------------------------------------------- cálculo aplicado (gate dic.)

def test_gate_diciembre_es_matematicamente_casi_imposible():
    """El veredicto que Boris pidió explícitamente: DSR>=0.90 con ~60 días de
    paper y N=17 exige un Sharpe anualizado imposible (~8x). Documentado en
    ANALISIS_MDE_GATE_DICIEMBRE_2026.md."""
    r = gate_diciembre_2026()
    assert r["sr_requerido_diario_autocorr"] > 0.4   # SR diario ~0.53
    assert r["sr_requerido_anual_autocorr"] > 8.0    # anualizado ~8.4
    # un edge plausible (SR diario 0.10, anual 1.59) produce DSR ~0.11, no 0.90
    assert r["dsr_alcanzado_en_plausible"] < 0.20
    # y harían falta ~4-6 años de datos, no 60 días
    assert r["T_necesario_dias_iid"] > 900
    assert r["T_necesario_dias_autocorr"] > r["T_necesario_dias_iid"]
    assert "INEJECUTABLE" in r["veredicto"]


# ------------------------------------ gate del pre-registro (trial_registry)

def test_gate_rechaza_diseno_sub_potente_como_inejecutable(tmp_path):
    """EL test del ticket: un pre-registro con diseño sub-potente queda
    INEJECUTABLE — no consume slot ni cuenta como refutación."""
    path = str(tmp_path / "r.json")
    sub_potente = _res_entry(
        id="trial_b5_sub",
        diseno_mde={"n_symbols": 50, "T_dates": 250, "horizon_days": 20,
                    "n_family": 17},
    )
    register_trial_reservation(sub_potente, preregistro=_preregistro(), path=path)
    entries = all_trials(path=path)
    assert len(entries) == 1
    e = entries[0]
    assert e["status"] == STATUS_INEJECUTABLE
    assert e["n_trials_consumidos"] == 0      # NO consume slot Bonferroni
    assert "veredicto" not in e               # NO cuenta como refutación
    assert "mde" in e and e["mde"]["ejecutable"] is False  # evidencia en ledger
    # el presupuesto de la familia NO cambió (el slot no se gastó)
    assert consumed_budget("motor_signal", path=path) == 0


def test_diseno_bien_dimensionado_se_registra_como_reserva(tmp_path):
    path = str(tmp_path / "r.json")
    ok = _res_entry(
        id="trial_b5_ok",
        diseno_mde={"n_symbols": 50, "T_dates": 250, "horizon_days": 1,
                    "n_family": 17},
    )
    register_trial_reservation(ok, preregistro=_preregistro(), path=path)
    e = all_trials(path=path)[0]
    assert e["status"] == STATUS_RESERVED      # reserva normal, con slot
    # el slot SI se cuenta (la fecha del test es pre-TTL: hoy simulado 08-15)
    assert consumed_budget("motor_signal", path=path,
                           today=date(2026, 8, 15)) == 1


def test_sin_diseno_mde_declarado_no_se_juzga(tmp_path):
    """Backward-compat (patrón B4): lo no declarado no se puede juzgar."""
    path = str(tmp_path / "r.json")
    register_trial_reservation(_res_entry(id="trial_b5_sindiseno"),
                               preregistro=_preregistro(), path=path)
    assert all_trials(path=path)[0]["status"] == STATUS_RESERVED


def test_diseno_mde_malformado_falla_ruidoso(tmp_path):
    entry = _res_entry(id="trial_b5_roto",
                       diseno_mde={"n_symbols": 2, "T_dates": 250})
    with pytest.raises(TrialRegistryError, match="diseno_mde invalido"):
        register_trial_reservation(entry, preregistro=_preregistro(),
                                   path=str(tmp_path / "r.json"))


def test_inejecutable_no_produce_refutacion_para_re_test(tmp_path):
    """Un INEJECUTABLE no produce refutación: no puede anclar un re_test
    (el objetivo de un re_test exige veredicto NO_CUMPLE; el INEJECUTABLE
    no tiene veredicto — nunca corrió)."""
    path = str(tmp_path / "r.json")
    sub = _res_entry(id="trial_b5_sub",
                     diseno_mde={"n_symbols": 50, "T_dates": 250,
                                 "horizon_days": 20, "n_family": 17})
    register_trial_reservation(sub, preregistro=_preregistro(), path=path)
    from app.core.trial_registry import register_trial
    retest = {
        "id": "trial_b5_rt", "fecha": "2026-08-14", "familia": "re_test",
        "re_test_de": "trial_b5_sub", "hipotesis": "re-test",
        "n_trials_consumidos": 0,
        "umbral_aplicado": "DSR>=0.90 (registro previo, sin slot nuevo)",
        "seccion_doc": "§b5", "status": "COMPLETED",
        "veredicto": "NO_CUMPLE", "artefacto": "data/cache/a.txt",
    }
    with pytest.raises(TrialRegistryError, match="NO_CUMPLE"):
        register_trial(retest, path=path)


# ------------------------------------------- el gate también en la ruta post-hoc

def _comp_entry(**overrides):
    """Entrada COMPLETED (registro post-hoc, con veredicto y artefacto)."""
    entry = {
        "id": "trial_b5_posthoc",
        "fecha": "2026-08-14",
        "familia": "motor_signal",
        "hipotesis": "hipotesis registrada despues de correr",
        "n_trials_consumidos": 1,
        "umbral_aplicado": _UMBRAL,
        "seccion_doc": "§b5",
        "status": "COMPLETED",
        "veredicto": "NO_CUMPLE",
        "artefacto": "data/cache/b5.txt",
    }
    entry.update(overrides)
    return entry


def test_registro_post_hoc_de_diseno_sub_potente_se_rechaza(tmp_path):
    """B5 cierra el agujero de la ruta directa: un NO_CUMPLE salido de un
    diseño que NO podía detectar el efecto es refutación-teatro, y no se
    registra. Acá no puede degradarse a INEJECUTABLE (la entrada afirma
    veredicto + artefacto), así que falla ruidoso."""
    from app.core.trial_registry import register_trial
    sub = _comp_entry(diseno_mde={"n_symbols": 50, "T_dates": 250,
                                  "horizon_days": 20, "n_family": 17})
    with pytest.raises(TrialRegistryError, match="sub-potente"):
        register_trial(sub, path=str(tmp_path / "r.json"))
    # no quedó nada escrito (el rechazo es antes de escribir)
    assert all_trials(path=str(tmp_path / "r.json")) == []


def test_registro_post_hoc_de_diseno_bien_dimensionado_pasa(tmp_path):
    """El gate no puede bloquear lo que sí tiene potencia: mismo camino,
    diseño diario de 250 fechas -> se registra con su veredicto."""
    from app.core.trial_registry import register_trial
    ok = _comp_entry(id="trial_b5_posthoc_ok",
                     diseno_mde={"n_symbols": 50, "T_dates": 250,
                                 "horizon_days": 1, "n_family": 17})
    register_trial(ok, path=str(tmp_path / "r.json"))
    e = all_trials(path=str(tmp_path / "r.json"))[0]
    assert e["status"] == "COMPLETED" and e["veredicto"] == "NO_CUMPLE"
