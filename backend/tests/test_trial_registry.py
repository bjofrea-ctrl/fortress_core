"""Tests de M6 — TrialRegistry (ORDENES_MODULOS.md M6).

Cubren el contrato del modulo:
- registrar y releer conserva los datos
- consumed_budget cuenta correctamente por familia
- current_threshold se endurece a medida que sube el consumo
- un registro corrupto o incompleto falla ruidosamente, no en silencio
"""
import json
import subprocess
from datetime import date, timedelta

import pytest
from app.core.trial_registry import (
    BASE_THRESHOLD,
    RESERVATION_TTL_DAYS,
    STATUS_COMPLETED,
    STATUS_EXPIRED,
    STATUS_RESERVED,
    TrialRegistryError,
    _validate_cross_entries,
    _validate_entry,
    all_trials,
    complete_trial,
    consumed_budget,
    current_threshold,
    effective_status,
    expire_stale_reservations,
    extract_umbral_aplicado,
    register_trial,
    register_trial_reservation,
    trials_by_family,
    validate_umbral_aplicado,
)

FAMILIA = "motor_signal"


@pytest.fixture(autouse=True)
def _no_cache_snapshot(monkeypatch):
    """Estos tests validan las garantías del LEDGER (JSON), no el cache.
    A0 agrega el attach automático del snapshot de cache en
    register_trial/register_trial_reservation; acá se aísla para que las
    entradas de prueba queden exactamente como las declara _entry()
    (y sin pagar los 25s del manifiesto de 102 parquets por registro).
    El contrato del snapshot tiene sus tests en test_cache_integrity.py."""
    import app.core.trial_registry as tr

    monkeypatch.setattr(tr, "_attach_cache_snapshot_if_absent", lambda entry: entry)


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
    # Track A: al releer, la entrada trae status explicito (registro post-hoc
    # sin status declarado -> COMPLETED).
    esperado = dict(entry)
    esperado["status"] = "COMPLETED"
    assert reloaded[0] == esperado


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


# ==================== Track A: estados de reserva ====================

HOY = date.today()


def _reservation(id_suffix="res", familia=FAMILIA, fecha=None, n=1, **overrides):
    entry = {
        "id": f"trial_{id_suffix}",
        "fecha": fecha or HOY.isoformat(),
        "familia": familia,
        "hipotesis": "hipotesis aprobada por Boris, trial sin correr",
        "n_trials_consumidos": n,
        "umbral_aplicado": "DSR>=0.90 2/3 ventanas",
        "seccion_doc": "§track-a-test",
    }
    entry.update(overrides)
    return entry


def test_reserva_cuenta_presupuesto(tmp_path):
    """El slot se ocupa AL RESERVAR: consumed_budget sube con la reserva sola."""
    path = str(tmp_path / "registry.json")
    antes = consumed_budget(FAMILIA, path=path)
    register_trial_reservation(_reservation("r1"), path=path)
    assert consumed_budget(FAMILIA, path=path) == antes + 1
    # y el umbral se endurece igual que con un trial ya corrido
    assert current_threshold(FAMILIA, path=path) < BASE_THRESHOLD + 0.0999


def test_completar_no_duplica_presupuesto(tmp_path):
    """RESERVED -> COMPLETED deja el conteo en 1 (mismo slot, no dos)."""
    path = str(tmp_path / "registry.json")
    register_trial_reservation(_reservation("c1"), path=path)
    assert consumed_budget(FAMILIA, path=path) == 1
    complete_trial("trial_c1", veredicto="NO_CUMPLE",
                   artefacto="data/cache/art.txt", path=path)
    assert consumed_budget(FAMILIA, path=path) == 1
    entrada = all_trials(path=path)[0]
    assert entrada["status"] == STATUS_COMPLETED
    assert entrada["veredicto"] == "NO_CUMPLE"


def test_expirar_libera_presupuesto(tmp_path):
    """Reserva vencida (> TTL dias) deja de contar; se materializa EXPIRED."""
    path = str(tmp_path / "registry.json")
    vieja = HOY - timedelta(days=RESERVATION_TTL_DAYS + 1)
    register_trial_reservation(
        _reservation("vieja", fecha=vieja.isoformat()), path=path)
    register_trial_reservation(_reservation("fresca"), path=path)
    # la vencida NO cuenta aunque el campo fisico diga RESERVED
    entradas = {e["id"]: e for e in all_trials(path=path)}
    assert effective_status(entradas["trial_vieja"]) == STATUS_EXPIRED
    vivas = [e for e in entradas.values() if effective_status(e) == STATUS_RESERVED]
    assert len(vivas) == 1  # solo la fresca
    n_expiradas = expire_stale_reservations(path=path)
    assert n_expiradas == 1
    estados = {e["id"]: e["status"] for e in all_trials(path=path)}
    assert estados["trial_vieja"] == STATUS_EXPIRED


def test_no_se_puede_completar_lo_que_no_esta_reserved(tmp_path):
    """complete_trial falla para inexistentes, completadas y expiradas."""
    path = str(tmp_path / "registry.json")
    register_trial(_entry("ya"), path=str(path))
    with pytest.raises(TrialRegistryError, match="inexistente"):
        complete_trial("trial_fantasma", "CUMPLE", "a.txt", path=path)
    # doble completion
    register_trial_reservation(_reservation("doble"), path=path)
    complete_trial("trial_doble", "CUMPLE", "a.txt", path=path)
    with pytest.raises(TrialRegistryError, match="ya fue completado"):
        complete_trial("trial_doble", "NO_CUMPLE", "b.txt", path=path)
    # expirada: libero su slot; completarla atras es doble uso del mismo intento
    vieja_date = HOY - timedelta(days=RESERVATION_TTL_DAYS + 5)
    register_trial_reservation(
        _reservation("old", fecha=vieja_date.isoformat()), path=path)
    expire_stale_reservations(path=path)
    with pytest.raises(TrialRegistryError, match="expiro"):
        complete_trial("trial_old", "CUMPLE", "c.txt", path=path)


def test_veredicto_invalido_en_complete(tmp_path):
    path = str(tmp_path / "registry.json")
    register_trial_reservation(_reservation("v"), path=path)
    with pytest.raises(TrialRegistryError, match="veredicto invalido"):
        complete_trial("trial_v", "ZONA_GRIS", "a.txt", path=path)
    with pytest.raises(TrialRegistryError, match="artefacto"):
        complete_trial("trial_v", "CUMPLE", "   ", path=path)


def test_reserva_no_lleva_veredicto_ni_artefacto():
    with pytest.raises(TrialRegistryError, match="no puede llevar"):
        _validate_entry(
            _reservation("conV", status=STATUS_RESERVED, veredicto="CUMPLE"))
    with pytest.raises(TrialRegistryError, match="no puede llevar"):
        _validate_entry(
            _reservation("conA", status=STATUS_RESERVED, artefacto="x.txt"))


def test_reserva_requiere_slot_y_no_aplica_a_re_test():
    # n=0 se rechaza (una reserva ES un slot): el chequeo general de "cero solo
    # legal en re_test" o el especifico de reserva pueden disparar primero.
    with pytest.raises(TrialRegistryError, match="solo es legal en familia|n>=1"):
        _validate_entry(_reservation("cero", status=STATUS_RESERVED, n=0))
    reserva_retest = {
        "id": "trial_rt_res", "fecha": HOY.isoformat(), "familia": "re_test",
        "re_test_de": "trial_x", "hipotesis": "h", "n_trials_consumidos": 1,
        "umbral_aplicado": "u", "seccion_doc": "s", "status": STATUS_RESERVED,
    }
    with pytest.raises(TrialRegistryError, match="re_test"):
        _validate_entry(reserva_retest)


def test_register_trial_post_hoc_default_completed(tmp_path):
    """register_trial sigue aceptando el formato viejo: default COMPLETED."""
    path = str(tmp_path / "registry.json")
    register_trial_reservation(_reservation("mix"), path=path)
    register_trial(_entry("post"), path=str(path))  # formato legacy completo
    statuses = {e["id"]: e["status"] for e in all_trials(path=path)}
    assert statuses["trial_mix"] == STATUS_RESERVED
    assert statuses["trial_post"] == STATUS_COMPLETED


def test_current_threshold_con_reserva_y_expiracion(tmp_path):
    """Umbral Bonferroni responde a reservas vivas y se libera con expiracion."""
    path = str(tmp_path / "registry.json")
    vigente = 1.0 - (1 - BASE_THRESHOLD) / 1
    assert current_threshold(FAMILIA, path=path) == pytest.approx(vigente)
    register_trial_reservation(_reservation("t1"), path=path)
    con_un_slot = 1.0 - (1 - BASE_THRESHOLD) / 2  # consumo 1 -> n=2
    assert current_threshold(FAMILIA, path=path) == pytest.approx(con_un_slot)
    expire_stale_reservations(path=path, today=HOY + timedelta(days=99))
    assert consumed_budget(FAMILIA, path=path) == 0
    assert current_threshold(FAMILIA, path=path) == pytest.approx(vigente)


# ==================== Track A: disciplina ejecutable minima ====================
PREREGISTRO_MD = """
## 4. Criterio de éxito / fracaso

| Resultado | Veredicto |
|---|---|
| PALA > RESTO ... | CUMPLE |

### 4.4 Binario
- umbral_aplicado: `DSR_PALA>0.50 Y Sharpe_PALA>Sharpe_RESTO en >=2/3 ventanas`
"""


def test_extract_umbral_linea_clave_valor():
    assert extract_umbral_aplicado(PREREGISTRO_MD).startswith("DSR_PALA>0.50")


def test_extract_umbral_fila_tabla_markdown():
    md = "| umbral aplicado (registro) | `\"DSR>=0.90 en 2 de 3 ventanas\"` |"
    assert extract_umbral_aplicado(md) == "DSR>=0.90 en 2 de 3 ventanas"


def test_validate_umbral_coincidente_pasa_y_mismatch_falla_ruidoso():
    devuelto = validate_umbral_aplicado(
        PREREGISTRO_MD, "dsr_pala>0.50 y sharpe_pala>sharpe_resto EN >=2/3 ventanas"
    )
    assert devuelto.startswith("DSR_PALA")  # normalizacion case-insensitive pasa
    with pytest.raises(TrialRegistryError, match="DISCIPLINA EJECUTABLE VIOLADA"):
        validate_umbral_aplicado(PREREGISTRO_MD, "DSR>=0.95 despues lo afloje")


def test_pre_registro_sin_umbral_no_se_puede_validar():
    with pytest.raises(TrialRegistryError, match="extrai"):
        validate_umbral_aplicado("# documento sin criterio\nnada aqui", "x")


def test_reserva_con_preregistro_mismatch_no_registra(tmp_path):
    path = str(tmp_path / "registry.json")
    reserva = _reservation("disc", umbral_aplicado="DSR>=0.50 distinto al doc")
    with pytest.raises(TrialRegistryError, match="DISCIPLINA EJECUTABLE VIOLADA"):
        register_trial_reservation(reserva, path=path, preregistro=PREREGISTRO_MD)
    assert all_trials(path=path) == []  # nada quedo escrito


# ==================== Track A: reconciliacion git contra origin/main ====================


def _git_local(args, cwd):
    r = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git error: " + " ".join(args))
    return r


def test_reconciliacion_git_detecta_desync_origin_main(tmp_path):
    """El guard de reconciliacion compara contra origin/main (NO @{u}) y falla
    ruidoso cuando origin/main avanzo el ledger sin que el local lo tenga.

    Regresion del bug que el revisor detecto: usar @{u} (upstream del branch)
    fallaba en silencio en worktrees sin tracking, dejando el drift 25-vs-26
    sin detectar. Este test levanta un mini-repo con remote origin y un
    segundo clon que avanza main — el primer repo debe bloquear registrar.
    """
    try:
        _git_local(["--version"], tmp_path)
    except Exception:
        pytest.skip("git no disponible")
    bare = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    (repo / "backend" / "data").mkdir(parents=True)
    _git_local(["init", "--bare", "-q", str(bare)], tmp_path)
    _git_local(["init", "-q"], repo)
    _git_local(["config", "user.email", "t@t"], repo)
    _git_local(["config", "user.name", "t"], repo)
    _git_local(["checkout", "-q", "-b", "main"], repo)
    ledger = repo / "backend/data/trial_registry.json"
    ledger.write_text(json.dumps([_entry("seed")]), encoding="utf-8")
    _git_local(["add", "-A"], repo)
    _git_local(["commit", "-q", "-m", "seed"], repo)
    _git_local(["remote", "add", "origin", str(bare)], repo)
    _git_local(["push", "-q", "origin", "main"], repo)

    # otro agente avanza origin/main con una entrada nueva (el drift 25-vs-26)
    other = tmp_path / "other"
    _git_local(["clone", "-q", str(bare), str(other)], tmp_path)
    other_file = other / "backend/data/trial_registry.json"
    _git_local(["config", "user.email", "t@t"], other)
    _git_local(["config", "user.name", "t"], other)
    otros = json.loads(other_file.read_text(encoding="utf-8"))
    otros.append(_entry("b", veredicto="CUMPLE"))
    other_file.write_text(json.dumps(otros), encoding="utf-8")
    _git_local(["add", "-A"], other)
    _git_local(["commit", "-q", "-m", "otro"], other)
    _git_local(["push", "-q", "origin", "main"], other)

    # el repo local no trae esa entrada; registrar debe fallar ruidoso
    with pytest.raises(TrialRegistryError, match="LEDGER DESINCRONIZADO"):
        register_trial(_entry("z"), path=str(ledger))
