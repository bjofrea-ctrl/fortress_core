"""Tests de B4 (PLAN_REMEDIO_BRECHAS_20260903 §B4) — holdout sellado 2025-09-01.

El `trial_registry` rechaza por ESCRITURA cualquier trial cuyo diseño toque
datos posteriores a HOLDOUT_CUTOFF_DATE (2025-09-01), salvo:
  - la excepción explícita: paper trading PROSPECTIVO (el OOS real, no dato
    histórico), declarada como `ventana_datos.modo == "paper_prospectivo"`;
  - el escape declarado FORTRESS_ALLOW_HOLDOUT_TOUCH=1 (emergencias, p.ej.
    la evaluación final C1 de diciembre).

Regla por ESCRITURA: el ledger histórico (51 entradas, varias con datos
post-corte por diseño) carga sin problema — solo los REGISTROS NUEVOS se
validan contra el corte.

Cobertura:
  - constante pinea 2025-09-01;
  - ventana histórica pre-corte (incluso justo en el corte) -> registra;
  - ventana histórica post-corte (estructurada y vía texto del pre-registro)
    -> rechazada con mensaje HOLDOUT_BLOQUEADO + cita al plan y al escape;
  - paper_prospectivo es excepción explícita aun si el texto menciona fechas
    post-corte;
  - entrada sin ventana declarada ni texto -> no bloquea (backward-compat);
  - escape forzado permite tocar el holdout;
  - rangos de años ('2019-2026', '2024-2026-08') también se detectan; citas
    de papel ('2014–2017') o fechas aisladas no generan falsos positivos;
  - la LECTURA de un ledger con ventanas post-corte no bloquea.
"""
import json

import pytest
from app.core.trial_registry import (
    HOLDOUT_CUTOFF_DATE,
    HOLDOUT_ESCAPE_ENV,
    HOLDOUT_PAPER_MODE,
    TrialRegistryError,
    all_trials,
    register_trial,
    register_trial_reservation,
)

_UMBRAL = "DSR>=0.90 2/3 ventanas (n_trials=17)"
_CORTE = "2025-09-01"


def _entry(**overrides):
    entry = {
        "id": "trial_b4_x",
        "fecha": "2026-08-14",  # pre-gate: aísla la prueba del gate A7
        "familia": "motor_signal",
        "hipotesis": "hipotesis de prueba B4",
        "n_trials_consumidos": 1,
        "umbral_aplicado": _UMBRAL,
        "veredicto": "NO_CUMPLE",
        "artefacto": "data/cache/artefacto.txt",
        "seccion_doc": "§b4",
    }
    entry.update(overrides)
    return entry


def _preregistro(contenido: str) -> str:
    """Un pre-registro real declara el umbral (disciplina A7) + el diseño."""
    return (
        "# Pre-registro de prueba B4\n"
        "## Criterio de exito\n"
        f"umbral_aplicado: {_UMBRAL}\n"
        "## Diseno\n"
        + contenido
    )


def _res_entry(**overrides):
    """Entrada RESERVED válida: sin veredicto ni artefacto (contrato Track A)."""
    entry = _entry(status="RESERVED", **overrides)
    entry.pop("veredicto", None)
    entry.pop("artefacto", None)
    return entry


# ------------------------------------------------------------ constante

def test_holdout_cutoff_es_2025_09_01():
    assert HOLDOUT_CUTOFF_DATE.isoformat() == _CORTE


# ------------------------------------ ventana estructurada (ventana_datos)

def test_ventana_historica_pre_corte_registra(tmp_path):
    entry = _entry(id="trial_b4_pre",
                   ventana_datos={"modo": "historico", "hasta": "2025-06-30"})
    register_trial(entry, path=str(tmp_path / "r.json"))
    assert all_trials(path=str(tmp_path / "r.json"))[0]["id"] == "trial_b4_pre"


def test_ventana_historica_justo_en_el_corte_registra(tmp_path):
    """El corte es inclusivo: datos hasta 2025-09-01 no tocan el holdout."""
    entry = _entry(id="trial_b4_corte",
                   ventana_datos={"modo": "historico", "hasta": _CORTE})
    register_trial(entry, path=str(tmp_path / "r.json"))
    assert all_trials(path=str(tmp_path / "r.json"))[0]["id"] == "trial_b4_corte"


def test_ventana_historica_post_corte_es_violacion(tmp_path):
    entry = _entry(id="trial_b4_viol",
                   ventana_datos={"modo": "historico", "hasta": "2026-08-04"})
    with pytest.raises(TrialRegistryError) as exc_info:
        register_trial(entry, path=str(tmp_path / "r.json"))
    msg = str(exc_info.value)
    assert "HOLDOUT_BLOQUEADO" in msg
    assert _CORTE in msg
    assert "2026-08-04" in msg
    assert "B4" in msg               # cita el plan
    assert "paper_prospectivo" in msg  # la excepción explícita visible
    assert HOLDOUT_ESCAPE_ENV in msg   # y el escape para emergencias


def test_ventana_modo_desconocido_falla_ruidoso(tmp_path):
    entry = _entry(id="trial_b4_modo",
                   ventana_datos={"modo": "cuantico", "hasta": "2025-01-01"})
    with pytest.raises(TrialRegistryError, match="modo desconocido"):
        register_trial(entry, path=str(tmp_path / "r.json"))


def test_ventana_historico_sin_hasta_falla_ruidoso(tmp_path):
    entry = _entry(id="trial_b4_sinhasta", ventana_datos={"modo": "historico"})
    with pytest.raises(TrialRegistryError, match="exige 'hasta'"):
        register_trial(entry, path=str(tmp_path / "r.json"))


# --------------------------------------------- excepción paper prospectivo

def test_paper_prospectivo_es_excepcion_explicita(tmp_path):
    """El OOS real (paper trading de hoy hacia adelante) NO es dato histórico:
    puede cruzar el corte por definición, pero debe declararse explícito."""
    entry = _res_entry(id="trial_b4_paper",
                       ventana_datos={"modo": HOLDOUT_PAPER_MODE})
    register_trial_reservation(
        entry,
        preregistro=_preregistro("Ventana de evaluacion: 2026-09-01 a "
                                 "2026-12-01 (paper prospectivo)"),
        path=str(tmp_path / "r.json"),
    )
    assert all_trials(path=str(tmp_path / "r.json"))[0]["id"] == "trial_b4_paper"


# ------------------------------------------- texto del pre-registro (scan)

def test_pre_registro_con_rango_iso_post_corte_bloquea(tmp_path):
    entry = _res_entry(id="trial_b4_txt")
    with pytest.raises(TrialRegistryError) as exc_info:
        register_trial_reservation(
            entry,
            preregistro=_preregistro("Ventana de datos: 2019-01-01 → 2026-08-04"),
            path=str(tmp_path / "r.json"),
        )
    msg = str(exc_info.value)
    assert "HOLDOUT_BLOQUEADO" in msg and "el pre-registro" in msg


def test_pre_registro_con_rango_de_anios_post_corte_bloquea(tmp_path):
    """'2019-2026' también es una ventana de datos que cruza el corte."""
    entry = _res_entry(id="trial_b4_anios")
    with pytest.raises(TrialRegistryError, match="HOLDOUT_BLOQUEADO"):
        register_trial_reservation(
            entry,
            preregistro=_preregistro("Panel de fechas habiles 2019-2026"),
            path=str(tmp_path / "r.json"),
        )
    # '2024-2026-08' (año+mes) también cruza.
    entry = _res_entry(id="trial_b4_anios2")
    with pytest.raises(TrialRegistryError, match="HOLDOUT_BLOQUEADO"):
        register_trial_reservation(
            entry,
            preregistro=_preregistro("Ventanas: W1 2020-2021, W3 2024-2026-08"),
            path=str(tmp_path / "r.json"),
        )


def test_pre_registro_rango_pre_corte_o_cita_de_papel_no_bloquea(tmp_path):
    """Falsos positivos: '2014–2017' (cita de papel) y rangos que terminan
    antes del corte no generan violación."""
    pref = _preregistro(
        "Metodo Prado & Zhu 2014–2017 | Ventana de datos 2019-01-01 → 2025-08-31"
    )
    entry = _res_entry(id="trial_b4_ok1")
    register_trial_reservation(entry, preregistro=pref, path=str(tmp_path / "r.json"))
    assert all_trials(path=str(tmp_path / "r.json"))[0]["id"] == "trial_b4_ok1"


# ------------------------------------------------------- compatibilidad

def test_entrada_sin_ventana_ni_texto_no_bloquea(tmp_path):
    """Backward-compat: las entradas existentes no declaran ventana de datos;
    una registro nuevo sin declaración no se puede juzgar -> no bloquea."""
    entry = _entry(id="trial_b4_simple")
    register_trial(entry, path=str(tmp_path / "r.json"))
    assert all_trials(path=str(tmp_path / "r.json"))[0]["id"] == "trial_b4_simple"


def test_lectura_no_bloquea_ledger_con_ventanas_post_corte(tmp_path):
    """Regla por ESCRITURA: un ledger sembrado con ventanas post-corte (como
    los pre-registros pre-B4) carga sin disparar el holdout check."""
    path = tmp_path / "r.json"
    sembrado = [
        _entry(id="trial_hist_1",
               ventana_datos={"modo": "historico", "hasta": "2026-08-04"}),
        _entry(id="trial_hist_2"),
    ]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sembrado, fh, ensure_ascii=False)
    entries = all_trials(path=str(path))
    assert [e["id"] for e in entries] == ["trial_hist_1", "trial_hist_2"]


def test_escape_forzado_permite_tocar_holdout(monkeypatch, tmp_path):
    monkeypatch.setenv(HOLDOUT_ESCAPE_ENV, "1")
    entry = _entry(id="trial_b4_emerg",
                   ventana_datos={"modo": "historico", "hasta": "2026-08-04"})
    register_trial(entry, path=str(tmp_path / "r.json"))
    assert all_trials(path=str(tmp_path / "r.json"))[0]["id"] == "trial_b4_emerg"
