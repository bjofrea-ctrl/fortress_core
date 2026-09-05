"""
Tests de A7 (PLAN_REMEDIO_BRECHAS_20260903 §A7) — el ledger obedece la
Regla 1 de ONBOARDING.md ("Ningún trial de motor sin criterio pre-registrado").

Cobertura:
  - Trial DENTRO de la ventana del gate sin categoria → RECHAZADO con mensaje
    que cita la Regla 1 de ONBOARDING.md (verificada contra el documento real).
  - Trial DENTRO de la ventana del gate con categoria='bugfix' → ACEPTADO.
  - Trial DENTRO de la ventana del gate con categoria='infraestructura' → ACEPTADO.
  - Trial DENTRO de la ventana del gate con categoria inventada → RECHAZADO.
  - Trial FUERA de la ventana del gate (fecha pre-gate) sin categoria → ACEPTADO.
  - Trial DENTRO de la ventana del gate via register_trial_reservation → RECHAZADO.
  - Escape FORTRESS_ALLOW_GATE_TRIAL=1 desactiva la regla (emergencias).
  - El ledger actual (51 entradas, todas pre-gate) carga sin disparar el bloqueo.
  - Constantes públicas del gate son las del plan (start, end, allow-list).

Diseño: el conftest.py del repo setea FORTRESS_ALLOW_GATE_TRIAL=1 a nivel
de sesión para que el resto de los tests sigan probando mecánica sin
verse afectados por el gate que arrancó el 2026-09-02. Los tests de A7
desactivan ese escape explícitamente con monkeypatch.delenv cuando
quieren verificar la regla real.
"""
import datetime as _dt
import os
import pathlib
import re

import pytest
from app.core.gate_window import (
    GATE_CATEGORY_ALLOW_LIST,
    GATE_START_DATE,
    GATE_TRIAL_ESCAPE_ENV,
    MAX_GATE_DAYS,
    assert_allowed_during_gate,
    get_gate_end_date,
    is_allowed_during_gate,
    is_within_gate_window,
)
from app.core.trial_registry import (
    TrialRegistryError,
    all_trials,
    register_trial,
    register_trial_reservation,
)

# ============================================================ fuente de verdad
#
# A7 no inventa una regla: la hace cumplir. La regla que el gate enforcea es la
# Regla 1 de ONBOARDING.md. Estos helpers la leen DEL DOCUMENTO REAL (no de un
# string copiado a mano dentro del test) para que la verificación porte sobre el
# CONTENIDO de la regla y no sobre un literal flotante: si alguien renumera o
# reescribe las reglas de ONBOARDING.md, estos helpers fallan y obligan a
# actualizar la cita del mensaje de error, en vez de dejar un "Regla N"
# mentiroso devuelto a un agente en producción.

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ONBOARDING_PATH = REPO_ROOT / "ONBOARDING.md"


def _regla_de_onboarding(numero: int) -> str:
    """Texto completo (título + cuerpo) de la regla `numero` de ONBOARDING.md,
    colapsado a una sola línea."""
    text = ONBOARDING_PATH.read_text(encoding="utf-8")
    m = re.search(
        rf"^{numero}\.\s+\*\*(.+?)\*\*(.*?)(?=^\d+\.\s+\*\*|\Z)",
        text,
        re.M | re.S,
    )
    assert m, f"ONBOARDING.md no tiene una regla numerada {numero} — cambió el doc"
    cuerpo = re.sub(r"\s+", " ", m.group(2)).strip()
    return f"{m.group(1).strip()} {cuerpo}".strip()


def _titulo_regla_pre_registro() -> str:
    """Título de la regla que A7 enforcea, leído de ONBOARDING.md (sin el punto)."""
    return _regla_de_onboarding(1).split(".")[0].strip()


# ============================================================ constantes


def test_gate_start_date_es_2026_09_02():
    """El arranque del gate está PINNEADO en el plan §0: 2026-09-02."""
    assert GATE_START_DATE == _dt.date(2026, 9, 2)


def test_gate_end_default_es_90_dias_post_start():
    """Si nadie setea FORTRESS_GATE_END, el cap es GATE_START + MAX_GATE_DAYS."""
    assert MAX_GATE_DAYS == 90
    end_default = get_gate_end_date()
    assert end_default == GATE_START_DATE + _dt.timedelta(days=MAX_GATE_DAYS)


def test_allow_list_es_cerrada_y_exacta():
    """El allow-list es un frozenset cerrado: SOLO 'bugfix' y 'infraestructura'."""
    assert GATE_CATEGORY_ALLOW_LIST == frozenset({"bugfix", "infraestructura"})


def test_escape_env_var_name_coincide_con_documentacion():
    """El nombre del escape es estable (documentado en el mensaje de error)."""
    assert GATE_TRIAL_ESCAPE_ENV == "FORTRESS_ALLOW_GATE_TRIAL"


# ============================================================ ventana


def test_is_within_gate_window_inclusive_en_extremos():
    """La ventana es inclusiva en ambos extremos."""
    assert is_within_gate_window(GATE_START_DATE) is True
    assert is_within_gate_window(get_gate_end_date()) is True
    assert is_within_gate_window(GATE_START_DATE - _dt.timedelta(days=1)) is False
    assert is_within_gate_window(get_gate_end_date() + _dt.timedelta(days=1)) is False


def test_is_within_gate_window_dia_random_del_gate():
    assert is_within_gate_window(_dt.date(2026, 9, 15)) is True
    assert is_within_gate_window(_dt.date(2026, 11, 30)) is True


def test_is_within_gate_window_override_env_var(monkeypatch):
    """FORTRESS_GATE_END con formato YYYY-MM-DD acorta la ventana."""
    override = (GATE_START_DATE + _dt.timedelta(days=10)).isoformat()
    monkeypatch.setenv("FORTRESS_GATE_END", override)
    new_end = get_gate_end_date()
    assert new_end == _dt.date.fromisoformat(override)
    assert is_within_gate_window(new_end + _dt.timedelta(days=1)) is False


def test_is_within_gate_window_override_invalido_o_anterior_falla_gracioso(monkeypatch):
    """Override con formato inválido o fecha anterior al start → fallback al cap."""
    monkeypatch.setenv("FORTRESS_GATE_END", "no-es-fecha")
    assert get_gate_end_date() == GATE_START_DATE + _dt.timedelta(days=MAX_GATE_DAYS)
    monkeypatch.setenv("FORTRESS_GATE_END", (GATE_START_DATE - _dt.timedelta(days=1)).isoformat())
    assert get_gate_end_date() == GATE_START_DATE + _dt.timedelta(days=MAX_GATE_DAYS)


# ============================================================ allow-list


def test_is_allowed_during_gate_exactos():
    assert is_allowed_during_gate("bugfix") is True
    assert is_allowed_during_gate("infraestructura") is True
    assert is_allowed_during_gate("BUGFIX") is True  # case-insensitive
    assert is_allowed_during_gate("Infraestructura") is True
    assert is_allowed_during_gate(" marketing ") is False
    assert is_allowed_during_gate(None) is False
    assert is_allowed_during_gate("") is False
    assert is_allowed_during_gate("re_test") is False
    assert is_allowed_during_gate("producto") is False


# ============================================================ gate enforcement


def _entry_in_gate(id_suffix="x", categoria=None, fecha=None, status=None):
    """Helper: entrada con fecha dentro del gate (default: 2026-09-15).

    Si `status="RESERVED"`, NO incluye veredicto/artefacto (Track A exige
    que las reservas lleguen sin ellos). Si `status=None` o "COMPLETED",
    sí los incluye."""
    is_reserved = status == "RESERVED"
    base = {
        "id": f"trial_a7_{id_suffix}",
        "fecha": (fecha or _dt.date(2026, 9, 15)).isoformat(),
        "familia": "motor_signal",
        "hipotesis": "trial de hipotesis nueva",
        "n_trials_consumidos": 1,
        "umbral_aplicado": "DSR>=0.90 2/3 ventanas",
        "seccion_doc": "§a7-test",
    }
    if not is_reserved:
        base["veredicto"] = "NO_CUMPLE"
        base["artefacto"] = "data/cache/artefacto.txt"
    if status is not None:
        base["status"] = status
    if categoria is not None:
        base["categoria"] = categoria
    return base


def test_trial_dentro_del_gate_sin_categoria_rechazado(tmp_path, monkeypatch):
    """A7: el chokepoint se activa. Sin categoria y fecha adentro → TrialRegistryError
    con mensaje que cita la Regla 1 de ONBOARDING.md con su contenido real."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    with pytest.raises(TrialRegistryError) as exc_info:
        register_trial(_entry_in_gate("no_cat"), path=path)
    msg = str(exc_info.value)
    assert "GATE_BLOQUEADO" in msg
    # Cita al documento y número CORRECTOS (ONBOARDING.md regla 1, no "Regla 0").
    assert "Regla 1" in msg, f"el mensaje no cita la Regla 1: {msg}"
    assert "ONBOARDING.md" in msg
    assert "Regla 0" not in msg, (
        "regresión: el mensaje cita 'Regla 0', una regla que NO existe en el repo"
    )
    # Y no un número vacío: cita el CONTENIDO real de la regla, leído del doc.
    assert _titulo_regla_pre_registro() in msg, (
        "el mensaje debe reproducir el título real de la regla de ONBOARDING.md"
    )
    assert "categoria=<ausente>" in msg
    # El archivo NO se escribió
    assert not os.path.exists(path)


def test_trial_dentro_del_gate_categoria_bugfix_aceptado(tmp_path, monkeypatch):
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    register_trial(_entry_in_gate("bf", categoria="bugfix"), path=path)
    assert len(all_trials(path=path)) == 1
    saved = all_trials(path=path)[0]
    assert saved["categoria"] == "bugfix"


def test_trial_dentro_del_gate_categoria_infraestructura_aceptado(tmp_path, monkeypatch):
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    register_trial(_entry_in_gate("infra", categoria="infraestructura"), path=path)
    assert len(all_trials(path=path)) == 1


def test_trial_dentro_del_gate_categoria_inventada_rechazado(tmp_path, monkeypatch):
    """Una categoria que no está en el allow-list también es rechazada."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    with pytest.raises(TrialRegistryError) as exc_info:
        register_trial(_entry_in_gate("inventada", categoria="marketing"), path=path)
    assert "categoria='marketing'" in str(exc_info.value)


def test_trial_fuera_del_gate_sin_categoria_aceptado(tmp_path, monkeypatch):
    """Fecha pre-gate (2026-08-30) sin categoria → ACEPTADO. La regla no aplica."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    entry = _entry_in_gate("pre", fecha=_dt.date(2026, 8, 30))
    register_trial(entry, path=path)
    assert len(all_trials(path=path)) == 1


def test_reserva_dentro_del_gate_tambien_bloqueada(tmp_path, monkeypatch):
    """register_trial_reservation también respeta la regla A7 (la fecha
    del trial cae dentro de la ventana, no la fecha de la reserva)."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    with pytest.raises(TrialRegistryError) as exc_info:
        register_trial_reservation(
            _entry_in_gate("res_no_cat", status="RESERVED"),
            path=path,
        )
    assert "GATE_BLOQUEADO" in str(exc_info.value)
    assert not os.path.exists(path)


def test_reserva_dentro_del_gate_con_bugfix_pasa(tmp_path, monkeypatch):
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    path = str(tmp_path / "registry.json")
    register_trial_reservation(
        _entry_in_gate("res_bf", categoria="bugfix", status="RESERVED"),
        path=path,
    )
    assert len(all_trials(path=path)) == 1
    assert all_trials(path=path)[0]["status"] == "RESERVED"


def test_env_var_escape_desbloquea_trial(tmp_path, monkeypatch):
    """El escape documentado (FORTRESS_ALLOW_GATE_TRIAL=1) desactiva la
    regla para emergencias declaradas. Sin categoria, fecha adentro,
    pero el operador sabe lo que hace."""
    monkeypatch.setenv("FORTRESS_ALLOW_GATE_TRIAL", "1")
    path = str(tmp_path / "registry.json")
    # No rompe
    register_trial(_entry_in_gate("emergencia"), path=path)
    assert len(all_trials(path=path)) == 1


def test_regla_1_de_onboarding_es_la_de_criterio_pre_registrado():
    """Guarda anti-renumeración: la regla que A7 enforcea debe seguir siendo la
    número 1 de ONBOARDING.md y debe hablar de criterio pre-registrado. Si alguien
    reordena las reglas del doc, este test falla ANTES de que el mensaje de error
    de producción cite un número equivocado."""
    regla = _regla_de_onboarding(1)
    assert "criterio pre-registrado" in regla.lower(), (
        f"la Regla 1 de ONBOARDING.md dejó de ser la del criterio pre-registrado: {regla[:120]}"
    )
    # El cuerpo de la regla es lo que el gate protege: se decide ANTES de correr.
    assert "ANTES" in regla, "la Regla 1 debe exigir pre-registro antes de ejecutar"


def test_mensaje_de_error_cita_la_regla_1_real_de_onboarding(monkeypatch):
    """El TrialRegistryError que dispara el gate contiene la cita correcta
    (Regla 1 de ONBOARDING.md) con el CONTENIDO real de la regla, más un hint
    operativo (allow-list + escape). No se conforma con matchear un literal."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    with pytest.raises(TrialRegistryError) as exc_info:
        assert_allowed_during_gate(
            _dt.date(2026, 9, 15), None, trial_id="trial_smoke"
        )
    msg = str(exc_info.value)
    # Cita verificada contra el documento real, no contra un string del test.
    assert "Regla 1" in msg
    assert "ONBOARDING.md" in msg
    assert "Regla 0" not in msg
    assert _titulo_regla_pre_registro() in msg
    # Conceptos sustantivos de la regla (los que el gate hace cumplir).
    assert "criterio pre-registrado" in msg
    assert "ANTES" in msg
    # Hint operativo para el agente que choca contra el bloqueo.
    assert "bugfix" in msg
    assert "infraestructura" in msg
    assert "FORTRESS_ALLOW_GATE_TRIAL" in msg
    assert "trial_smoke" in msg  # trial_id aparece para identificar el bloqueo


def test_ledger_actual_de_prod_carga_sin_error_despues_del_cambio(monkeypatch):
    """Las 51 entradas existentes del ledger de prod están todas en rango
    pre-gate (2026-08-10 a 2026-08-30). Cargar y validar el archivo
    entero NO debe disparar el gate check — la regla es por ESCRITURA,
    no por lectura."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    # El ledger de prod vive en backend/data/trial_registry.json
    prod_ledger = pathlib.Path(__file__).parent.parent / "data" / "trial_registry.json"
    if not prod_ledger.exists():
        pytest.skip("ledger de prod no disponible en este entorno")
    entries = all_trials(path=str(prod_ledger))
    assert len(entries) >= 50  # 51 al cierre del plan, >=50 tolerante a delta
    # Las 51 están pre-gate (ninguna con fecha >= 2026-09-02)
    for e in entries:
        fecha = _dt.date.fromisoformat(e["fecha"])
        assert fecha < GATE_START_DATE, (
            f"el ledger de prod tiene una entrada con fecha {fecha} dentro del gate — "
            f"revisar si fue pre-registrada durante el gate (A7)."
        )


def test_assert_allowed_during_gate_no_falla_fuera_de_ventana(monkeypatch):
    """El helper no rompe ni siquiera con categoria=None si la fecha está afuera."""
    monkeypatch.delenv("FORTRESS_ALLOW_GATE_TRIAL", raising=False)
    # No raise
    assert_allowed_during_gate(_dt.date(2026, 1, 1), None)
    assert_allowed_during_gate(_dt.date(2027, 1, 1), None)


def test_assert_allowed_during_gate_escape_no_rompe(monkeypatch):
    """Con el escape activo, ni siquiera una categoria inválida rompe."""
    monkeypatch.setenv("FORTRESS_ALLOW_GATE_TRIAL", "1")
    # No raise
    assert_allowed_during_gate(_dt.date(2026, 9, 15), "marketing", trial_id="t")
    assert_allowed_during_gate(_dt.date(2026, 9, 15), None, trial_id="t")
