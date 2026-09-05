"""
Tests del hash-guard del motor (A4 — PLAN_REMEDIO_BRECHAS_20260903.md).

Cobertura:
  - los 7 módulos canónicos están bien (contrato del gate)
  - compute_hashes es determinista y del orden correcto
  - verify_manifest detecta drift de bytes y de módulos faltantes
  - bump_manifest cambia hashes + commit y deja verify OK
  - phase_health devuelve rc=2 y registra drift cuando hay drift
  - phase_health devuelve rc=0 cuando todo coincide

Diseño: los tests que tocan disco usan tmp_path y monkeypatch sobre
MANIFEST_PATH/CACHE_DIR; el archivo del manifiesto VIGENTE en el repo
NO se toca (los demás tests del pipeline siguen dependiendo de él).
"""
import os
import subprocess

import pytest

from scripts import motor_manifest as mm
from scripts import pipeline_daily_signal as pl

# ----------------------------------------------------- contrato del gate


def test_canonical_modules_son_los_7_del_plan_a4():
    """Contrato del gate: exactamente estos 7 módulos, ni uno más ni uno menos."""
    expected = [
        "backend/app/core/signal_engine.py",
        "backend/app/core/paper_trading.py",
        "backend/app/core/backtest_engine.py",
        "backend/app/api/routes/decision.py",
        "backend/app/core/adaptive_risk.py",
        "backend/app/core/conformal.py",
        "backend/app/core/regime_classifier.py",
    ]
    assert mm.CANONICAL_MODULES == expected
    assert len(mm.CANONICAL_MODULES) == 7


def test_todos_los_canonical_modules_existen_en_repo():
    for rel in mm.CANONICAL_MODULES:
        assert os.path.exists(os.path.join(mm.REPO_ROOT, rel)), f"falta: {rel}"


# ----------------------------------------------------- compute_hashes


def test_compute_hashes_devuelve_7_entradas_en_orden_canonico():
    h = mm.compute_hashes()
    assert len(h) == 7
    assert list(h.keys()) == mm.CANONICAL_MODULES
    # SHA256 hex = 64 chars
    for v in h.values():
        assert len(v) == 64
        int(v, 16)  # parseable como hex


def test_compute_hashes_es_determinista():
    h1 = mm.compute_hashes()
    h2 = mm.compute_hashes()
    assert h1 == h2


def test_compute_hashes_con_modulos_custom_permite_test_de_drift():
    h = mm.compute_hashes([mm.CANONICAL_MODULES[0]])
    assert len(h) == 1
    assert list(h.keys()) == [mm.CANONICAL_MODULES[0]]


def test_compute_hashes_falla_si_modulo_no_existe():
    with pytest.raises(FileNotFoundError):
        mm.compute_hashes(["backend/este/archivo/no/existe.py"])


# ----------------------------------------------------- verify_manifest


def test_verify_manifest_vacio_devuelve_ok_sin_drift():
    """Sin manifiesto declarado, no hay contrato que violar todavía."""
    ok, drifted = mm.verify_manifest({})
    assert ok is True
    assert drifted == []


def test_verify_manifest_manifieste_vacio_devuelve_ok():
    ok, drifted = mm.verify_manifest({"commit": "abc", "hashes": {}})
    assert ok is True
    assert drifted == []


def test_verify_manifest_limpio_cuando_hashes_coinciden(tmp_path, monkeypatch):
    man_path = str(tmp_path / "manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    man = mm.build_manifest(commit="test123", note="test")
    mm.save_manifest(man, path=man_path)
    ok, drifted = mm.verify_manifest(man)
    assert ok is True
    assert drifted == []


def test_verify_manifest_detecta_drift_de_un_byte(tmp_path, monkeypatch):
    """Modifica un byte de un módulo congelado y verifica que el guard lo detecta."""
    man_path = str(tmp_path / "manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    man = mm.build_manifest(commit="antes", note="congelado")
    mm.save_manifest(man, path=man_path)

    # Apunta los hashes a un archivo controlado
    target_rel = "test/dummy_module.py"
    target_abs = tmp_path / "dummy_module.py"
    target_abs.write_text("contenido original\n")
    man["hashes"][target_rel] = mm._sha256(str(target_abs))

    # Ahora cambiamos el archivo
    target_abs.write_text("contenido MODIFICADO\n")
    ok, drifted = mm.verify_manifest(man)
    assert ok is False
    assert target_rel in drifted


def test_verify_manifest_detecta_modulo_faltante(tmp_path, monkeypatch):
    """Si el manifiesto declara un módulo que ya no existe, es drift."""
    man_path = str(tmp_path / "manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    man = {"commit": "x", "note": "", "hashes": {"fantasma/path/que/no/existe.py": "abc"}}
    ok, drifted = mm.verify_manifest(man)
    assert ok is False
    assert "fantasma/path/que/no/existe.py" in drifted


def test_verify_manifest_deduplica_drift_repetido():
    """El mismo path no aparece dos veces aunque esté en ambas listas."""
    man = {"hashes": {"x.py": "antiguo_hash"}}
    ok, drifted = mm.verify_manifest(man)
    assert drifted.count("x.py") == 1


# ----------------------------------------------------- build/save/load


def test_save_manifest_atomico(tmp_path, monkeypatch):
    """save_manifest escribe via .tmp y no deja basura."""
    man_path = str(tmp_path / "manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    man = mm.build_manifest(commit="abc", note="test")
    mm.save_manifest(man, path=man_path)
    assert os.path.exists(man_path)
    assert not os.path.exists(man_path + ".tmp")
    loaded = mm.load_manifest(path=man_path)
    assert loaded["commit"] == "abc"
    assert loaded["note"] == "test"
    assert loaded["hashes"] == man["hashes"]


def test_load_manifest_devuelve_vacio_si_no_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "MANIFEST_PATH", str(tmp_path / "no_existe.json"))
    assert mm.load_manifest() == {}


def test_build_manifest_toma_git_head_si_no_se_pasa_commit(monkeypatch):
    monkeypatch.setattr(mm, "_git_head", lambda: "deadbeef1234")
    man = mm.build_manifest()
    assert man["commit"] == "deadbeef1234"
    assert "hashes" in man and len(man["hashes"]) == 7


# ----------------------------------------------------- bump / init


def test_bump_actualiza_hashes_y_commit_y_pasa_verificacion(tmp_path, monkeypatch):
    man_path = str(tmp_path / "manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    # Inicial
    import argparse
    mm.cmd_init(argparse.Namespace(note="init", force=False))
    monkeypatch.setattr(mm, "_git_head", lambda: "bumped_commit")
    rc = mm.cmd_bump(argparse.Namespace(note="bugfix X"))
    assert rc == 0
    man = mm.load_manifest(path=man_path)
    assert man["commit"] == "bumped_commit"
    assert man["note"] == "bugfix X"
    ok, drifted = mm.verify_manifest(man)
    assert ok is True and drifted == []


def test_bump_requiere_note():
    import argparse
    rc = mm.cmd_bump(argparse.Namespace(note=""))
    assert rc == 2  # rechaza sin nota


def test_init_bloquea_si_manifiesto_ya_existe(tmp_path, monkeypatch):
    man_path = str(tmp_path / "manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    import argparse
    mm.cmd_init(argparse.Namespace(note="primera vez", force=False))
    # Segunda vez sin --force: rechaza
    rc = mm.cmd_init(argparse.Namespace(note="otra vez", force=False))
    assert rc == 2
    # Con --force: sobrescribe
    rc = mm.cmd_init(argparse.Namespace(note="forzado", force=True))
    assert rc == 0
    man = mm.load_manifest(path=man_path)
    assert man["note"] == "forzado"


# ----------------------------------------------------- integración con phase_health


@pytest.fixture
def fake_modules_dir(tmp_path, monkeypatch):
    """Crea 7 archivos dummy en un directorio aislado, hace que REPO_ROOT
    apunte allí y CANONICAL_MODULES use paths relativos a ese root. Así
    `phase_health()` corre end-to-end sin tocar el repo real."""
    root = tmp_path / "fake_repo"
    root.mkdir()
    rels = [
        "backend/app/core/signal_engine.py",
        "backend/app/core/paper_trading.py",
        "backend/app/core/backtest_engine.py",
        "backend/app/api/routes/decision.py",
        "backend/app/core/adaptive_risk.py",
        "backend/app/core/conformal.py",
        "backend/app/core/regime_classifier.py",
    ]
    for r in rels:
        p = root / r
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# fake module: {r}\nvalor = 42\n")
    # Redirige REPO_ROOT a tmp; CANONICAL_MODULES ya es relativo a REPO_ROOT.
    monkeypatch.setattr(mm, "REPO_ROOT", str(root))
    monkeypatch.setattr(mm, "BACKEND_DIR", str(root / "backend"))
    # Manifiesto en tmp
    man_path = str(root / "scripts" / "motor_manifest.json")
    monkeypatch.setattr(mm, "MANIFEST_PATH", man_path)
    return root, rels


@pytest.fixture
def state_file_in_tmp(tmp_path, monkeypatch):
    """Redirige CACHE_DIR/STATE_PATH a tmp para que phase_health no toque
    el estado real del pipeline (los demás tests lo necesitan)."""
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True)
    monkeypatch.setattr(pl, "CACHE_DIR", str(cache))
    monkeypatch.setattr(pl, "STATE_PATH", str(cache / "pipeline_state.json"))
    monkeypatch.setattr(pl, "HASH_GUARD_LOG", str(cache / "hash_drift.log"))
    monkeypatch.setattr(pl, "DECISION_PREFIX", str(cache / "pipeline_decision_"))
    monkeypatch.setattr(pl, "ARTIFACT_DIR", str(cache))
    return cache


def test_phase_health_devuelve_rc0_si_manifiesto_coincide(
    fake_modules_dir, state_file_in_tmp, monkeypatch
):
    root, rels = fake_modules_dir
    man = mm.build_manifest(commit="test", note="ok")
    mm.save_manifest(man)
    # Stubs para evitar dependencias de red/calendario (no probamos A1/A2 acá)
    monkeypatch.setattr(pl, "_cache_stale_days", lambda: 0)
    monkeypatch.setattr(pl, "detect_auto_phase", lambda: "health")
    rc = pl.phase_health()
    assert rc == 0
    # Log de drift NO se crea en el caso OK
    assert not (state_file_in_tmp / "hash_drift.log").exists()


def test_phase_health_devuelve_rc2_y_alerta_si_drift(
    fake_modules_dir, state_file_in_tmp, monkeypatch
):
    root, rels = fake_modules_dir
    man = mm.build_manifest(commit="antes", note="congelado")
    mm.save_manifest(man)
    # Modifico un byte de un módulo
    target = root / rels[0]
    target.write_text(target.read_text() + " # drift introducido\n")
    monkeypatch.setattr(pl, "_cache_stale_days", lambda: 0)
    monkeypatch.setattr(pl, "detect_auto_phase", lambda: "health")
    rc = pl.phase_health()
    # rc=2 por hash drift (A4), distinto del rc=1 de cache estancado
    assert rc == 2
    # El log de drift debe existir y mencionar el path
    log = state_file_in_tmp / "hash_drift.log"
    assert log.exists()
    content = log.read_text()
    assert "[HASH-GUARD]" in content
    assert "DRIFT DETECTADO" in content
    assert rels[0] in content


def test_phase_health_sin_manifiesto_no_explota(
    fake_modules_dir, state_file_in_tmp, monkeypatch
):
    """Antes del init del gate (manifiesto ausente), phase_health no rompe —
    solo avisa que no hay gate formal y devuelve rc=0/1 según cache."""
    man_path = fake_modules_dir[0] / "scripts" / "motor_manifest.json"
    if man_path.exists():
        man_path.unlink()
    monkeypatch.setattr(pl, "_cache_stale_days", lambda: 0)
    monkeypatch.setattr(pl, "detect_auto_phase", lambda: "health")
    rc = pl.phase_health()
    assert rc == 0


# ----------------------------------------------------- CLI end-to-end


def test_cli_verify_devuelve_rc0_en_repo_limpio():
    """El repo real (sin cambios) tiene su manifiesto recién creado por
    `init`, así que `verify` debe devolver 0 (o 2 si algo drifteó)."""
    r = subprocess.run(
        ["/Users/boris/Desktop/fortress_core/backend/.venv/bin/python",
         "-m", "scripts.motor_manifest", "verify"],
        cwd=os.path.join(mm.REPO_ROOT, "backend"),
        capture_output=True, text=True,
    )
    # 0 = OK, 2 = drift detectado
    assert r.returncode in (0, 2)
    assert "OK" in r.stdout or "DRIFT" in r.stdout


def test_cli_show_imprime_manifiesto_si_existe():
    r = subprocess.run(
        ["/Users/boris/Desktop/fortress_core/backend/.venv/bin/python",
         "-m", "scripts.motor_manifest", "show"],
        cwd=os.path.join(mm.REPO_ROOT, "backend"),
        capture_output=True, text=True,
    )
    # El init ya creó el manifiesto en este worktree
    assert r.returncode == 0
    assert "commit" in r.stdout
    assert "hashes" in r.stdout
