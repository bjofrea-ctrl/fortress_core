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
    _validate_cross_entries,
    _validate_entry,
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


def _retest(id_suffix="rt", target="trial_orig", **overrides):
    """Entrada re_test valida por defecto: exencion Fase 0.6 anclada a un objetivo."""
    entry = {
        "id": f"trial_{id_suffix}",
        "fecha": "2026-08-14",
        "familia": "re_test",
        "re_test_de": target,
        "hipotesis": "re-test de hipotesis ya refutada",
        "n_trials_consumidos": 0,
        "umbral_aplicado": "DSR>=0.90 (registro previo, sin slot nuevo)",
        "veredicto": "NO_CUMPLE",
        "artefacto": "data/cache/artefacto.txt",
        "seccion_doc": "§test",
    }
    entry.update(overrides)
    return entry


def _seed_target(path_str, id_suffix="orig"):
    """Siembra el objetivo legitimo: motor_signal, NO_CUMPLE, n=1."""
    register_trial(_entry(id_suffix), path=str(path_str))


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
    register_trial(_retest("3", target="trial_1", path=str(path)), path=str(path))
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


def test_zero_consumed_is_valid_only_in_re_test(tmp_path):
    # Re-tests (Fase 0.6) NO consumen slot nuevo: n_trials_consumidos=0 es valido
    # SOLO en familia re_test y SOLO con objetivo anclado (garantia H3.1).
    path = tmp_path / "registry.json"
    register_trial(_entry("orig", veredicto="NO_CUMPLE", path=str(path)), path=str(path))
    register_trial(_retest("retest", target="trial_orig", path=str(path)), path=str(path))
    assert len(all_trials(path=str(path))) == 2
    assert consumed_budget(FAMILIA, path=str(path)) == 1  # el re_test no suma slot


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


# ============================================================================
# Garantias anti-evasion Bonferroni de la familia re_test (H3.1, aprobadas por
# Boris 2026-08-26). 8 rutas: obligatoriedad, existencia, veredicto, cadenas,
# tope, camino feliz, cero fuera de re_test, backfill sigue validando.
# ============================================================================

def test_ruta1_re_test_sin_re_test_de_falla(tmp_path):
    """Ruta 1 — obligatoriedad: re_test sin 're_test_de' no se registra ni se carga."""
    path = tmp_path / "registry.json"
    _seed_target(str(path))
    invalida = _retest("rt")
    del invalida["re_test_de"]
    with pytest.raises(TrialRegistryError, match="re_test_de"):
        register_trial(invalida, path=str(path))
    # Tambien falla la CARGA si el JSON fue editado a mano (invariante en _load_raw)
    path.write_text(json.dumps([_entry("orig"), invalida]), encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="re_test_de"):
        all_trials(path=str(path))


def test_ruta2_re_test_objetivo_inexistente_o_posterior_falla(tmp_path):
    """Ruta 2 — existencia: el objetivo debe existir y ser ANTERIOR en el registro."""
    path = tmp_path / "registry.json"
    _seed_target(str(path))
    with pytest.raises(TrialRegistryError, match="inexistente o posterior"):
        register_trial(_retest("rt", target="trial_fantasma"), path=str(path))
    # Referencia hacia adelante (objetivo aparece DESPUES): tambien rechazada al cargar
    adelante = [_retest("adelantado", target="trial_tarde"), _entry("tarde")]
    path.write_text(json.dumps(adelante), encoding="utf-8")
    with pytest.raises(TrialRegistryError, match="inexistente o posterior"):
        all_trials(path=str(path))


def test_ruta3_re_test_solo_sobre_no_cumple(tmp_path):
    """Ruta 3 — veredicto: solo se permite re-test de hallazgos NO_CUMPLE."""
    path = tmp_path / "registry.json"
    register_trial(_entry("cumple", veredicto="CUMPLE"), path=str(path))
    with pytest.raises(TrialRegistryError, match="NO_CUMPLE"):
        register_trial(_retest("rt", target="trial_cumple"), path=str(path))


@pytest.mark.parametrize("familia_objetivo", ["producto", "re_test"])
def test_ruta4_re_test_sin_cadenas_ni_producto(tmp_path, familia_objetivo):
    """Ruta 4 — cadenas: objetivo debe ser familia de investigación.

    Ni decisiones de producto, ni otro re_test (prohibida la segunda derivación
    sin presupuesto).
    """
    path = tmp_path / f"registry_{familia_objetivo}.json"
    if familia_objetivo == "producto":
        base = _entry("prod", familia="producto", n=1)
        register_trial(base, path=str(path))
    else:
        # Cadena: re_test apuntando a otro re_test
        _seed_target(str(path), "base0")  # soporte legal para el PRIMER re_test
        base = _retest("cad1", target="trial_base0")
        register_trial(base, path=str(path))
    with pytest.raises(TrialRegistryError, match="investigación|de familia"):
        register_trial(_retest("cad2", target=base["id"]), path=str(path))


def test_ruta5_tope_retests_por_objetivo(tmp_path):
    """Ruta 5 — tope: MAX_RETESTS_PER_TARGET re-tests por objetivo; el (N+1)ésimo falla."""
    from app.core.trial_registry import MAX_RETESTS_PER_TARGET
    path = tmp_path / "registry.json"
    _seed_target(str(path))
    for i in range(MAX_RETESTS_PER_TARGET):
        register_trial(_retest(f"rt{i}", target="trial_orig"), path=str(path))
    assert consumed_budget("re_test", path=str(path)) == 0
    with pytest.raises(TrialRegistryError, match="MAX_RETESTS_PER_TARGET"):
        register_trial(_retest("rt_excedente", target="trial_orig"), path=str(path))


def test_ruta6_camino_feliz_par_completo(tmp_path):
    """Ruta 6 — camino feliz: par objetivo NO_CUMPLE + re_test anclado, ciclo completo."""
    path = tmp_path / "registry.json"
    _seed_target(str(path))
    register_trial(_retest("rt", target="trial_orig"), path=str(path))
    reloaded = all_trials(path=str(path))
    assert len(reloaded) == 2
    rt = [e for e in reloaded if e["familia"] == "re_test"][0]
    assert rt["re_test_de"] == "trial_orig"
    assert rt["n_trials_consumidos"] == 0
    # El umbral de motor_signal NO cambia por la exencion del re-test
    assert current_threshold(FAMILIA, path=str(path)) == pytest.approx(0.95)


def test_ruta7_cero_fuera_de_re_test_falla(tmp_path):
    """Ruta 7 — invariante inversa: n_trials_consumidos=0 SOLO legal en re_test."""
    for familia in ("motor_signal", "signal_diagnosis", "risk", "backtest_costos", "producto"):
        path = tmp_path / f"registry_{familia}.json"
        entry = _entry("cero", familia=familia, n=0)
        with pytest.raises(TrialRegistryError, match="solo es legal en familia 're_test'"):
            register_trial(entry, path=str(path))
        # Tambien al cargar un JSON editado a mano con el truco del cero
        path.write_text(json.dumps([entry]), encoding="utf-8")
        with pytest.raises(TrialRegistryError, match="solo es legal en familia 're_test'"):
            all_trials(path=str(path))


def test_ruta8_backfill_trials_pasan_validacion():
    """Ruta 8 — regresión: el TRIALS completo del backfill sigue validando entero.

    Incluye que las entradas re_test del backfill citen objetivos reales y
    anteriores (trial_08_sentimiento / trial_09_fundamentales verificados contra
    el ledger antes de escribir el backfill).
    """
    from scripts.backfill_trial_registry import TRIALS
    ids_vistos = set()
    for entry in TRIALS:
        _validate_entry(entry)
        if entry["familia"] == "re_test":
            assert entry["re_test_de"] in ids_vistos, (
                f"{entry['id']} cita objetivo '{entry.get('re_test_de')}' que no "
                f"aparece antes en TRIALS"
            )
        ids_vistos.add(entry["id"])
    _validate_cross_entries(TRIALS)
