"""Tests de M6 — TrialRegistry (ORDENES_MODULOS.md M6).

Cubren el contrato del modulo:
- registrar y releer conserva los datos
- consumed_budget cuenta correctamente por familia
- current_threshold se endurece a medida que sube el consumo
- un registro corrupto o incompleto falla ruidosamente, no en silencio
"""
import json

import pytest
from app.core.trial_registry import (
    BASE_THRESHOLD,
    TrialRegistryError,
    all_trials,
    consumed_budget,
    current_threshold,
    register_trial,
    trials_by_family,
)

FAMILIA = "motor_signal"


def _entry(id_suffix="a", familia=FAMILIA, n=1, veredicto="NO_CUMPLE", path=None):
    return {
        "id": f"trial_{id_suffix}",
        "fecha": "2026-08-14",
        "familia": familia,
        "hipotesis": "hipotesis de prueba",
        "n_trials_consumidos": n,
        "umbral_aplicado": "DSR>=0.90 2/3 ventanas",
        "veredicto": veredicto,
        "artefacto": "data/cache/artefacto.txt",
        "seccion_doc": "§test",
    }


def test_register_and_reload_preserves_data(tmp_path):
    path = tmp_path / "registry.json"
    entry = _entry("x", path=str(path))
    register_trial(entry, path=str(path))
    reloaded = all_trials(path=str(path))
    assert len(reloaded) == 1
    assert reloaded[0] == entry


def test_register_append_multiple(tmp_path):
    path = tmp_path / "registry.json"
    register_trial(_entry("1", path=str(path)), path=str(path))
    register_trial(_entry("2", path=str(path)), path=str(path))
    assert len(all_trials(path=str(path))) == 2


def test_duplicate_id_fails(tmp_path):
    path = tmp_path / "registry.json"
    register_trial(_entry("dup", path=str(path)), path=str(path))
    with pytest.raises(TrialRegistryError, match="duplicado"):
        register_trial(_entry("dup", path=str(path)), path=str(path))


def test_consumed_budget_counts_by_family(tmp_path):
    path = tmp_path / "registry.json"
    register_trial(_entry("1", familia="motor_signal", n=1, path=str(path)), path=str(path))
    register_trial(_entry("2", familia="motor_signal", n=1, path=str(path)), path=str(path))
    register_trial(_entry("3", familia="re_test", n=0, path=str(path)), path=str(path))
    assert consumed_budget("motor_signal", path=str(path)) == 2
    assert consumed_budget("re_test", path=str(path)) == 0
    assert consumed_budget("inexistente", path=str(path)) == 0


def test_consumed_budget_sums_multi_trial_entries(tmp_path):
    path = tmp_path / "registry.json"
    register_trial(_entry("gp", n=30, path=str(path)), path=str(path))
    assert consumed_budget("motor_signal", path=str(path)) == 30


def test_current_threshold_starts_at_base_and_tightens(tmp_path):
    path = tmp_path / "registry.json"
    # Sin consumo: n=1 trial nuevo -> umbral base
    assert current_threshold(FAMILIA, path=str(path)) == pytest.approx(BASE_THRESHOLD)
    register_trial(_entry("1", path=str(path)), path=str(path))
    # 1 consumido + 1 nuevo = 2 -> 1 - 0.10/2 = 0.95
    assert current_threshold(FAMILIA, path=str(path)) == pytest.approx(0.95)
    register_trial(_entry("2", path=str(path)), path=str(path))
    # 2 consumidos + 1 nuevo = 3 -> 1 - 0.10/3 ≈ 0.9667
    assert current_threshold(FAMILIA, path=str(path)) == pytest.approx(1 - 0.10 / 3)


def test_threshold_is_family_scoped(tmp_path):
    path = tmp_path / "registry.json"
    register_trial(_entry("1", familia="motor_signal", path=str(path)), path=str(path))
    assert current_threshold("motor_signal", path=str(path)) == pytest.approx(0.95)
    assert current_threshold("re_test", path=str(path)) == pytest.approx(BASE_THRESHOLD)


def test_corrupt_json_fails_loudly(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{ esto no es json", encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="corrupto"):
        all_trials(path=str(path))


def test_non_list_root_fails_loudly(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"no": "lista"}), encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="corrupto"):
        all_trials(path=str(path))


def test_incomplete_entry_fails_loudly(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([{"id": "incompleto"}]), encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="incompleta"):
        all_trials(path=str(path))


def test_invalid_veredicto_fails_loudly(tmp_path):
    path = tmp_path / "registry.json"
    entry = _entry("mal", path=str(path))
    entry["veredicto"] = "QUIZA"
    path.write_text(json.dumps([entry]), encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="veredicto"):
        all_trials(path=str(path))


def test_zero_consumed_is_valid(tmp_path):
    # Re-tests (Fase 0.6) NO consumen slot nuevo: n_trials_consumidos=0 es valido.
    path = tmp_path / "registry.json"
    register_trial(_entry("retest", n=0, path=str(path)), path=str(path))
    assert len(all_trials(path=str(path))) == 1
    assert consumed_budget(FAMILIA, path=str(path)) == 0


def test_negative_n_trials_fails_loudly(tmp_path):
    path = tmp_path / "registry.json"
    entry = _entry("mal", path=str(path))
    entry["n_trials_consumidos"] = -1
    path.write_text(json.dumps([entry]), encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="n_trials_consumidos"):
        all_trials(path=str(path))


def test_missing_file_returns_empty(tmp_path):
    path = tmp_path / "no_existe.json"
    assert all_trials(path=str(path)) == []
    assert consumed_budget(FAMILIA, path=str(path)) == 0


def test_trials_by_family_groups(tmp_path):
    path = tmp_path / "registry.json"
    register_trial(_entry("a", familia="motor_signal", path=str(path)), path=str(path))
    register_trial(_entry("b", familia="risk", path=str(path)), path=str(path))
    grouped = trials_by_family(path=str(path))
    assert set(grouped.keys()) == {"motor_signal", "risk"}
    assert len(grouped["motor_signal"]) == 1
    assert len(grouped["risk"]) == 1
