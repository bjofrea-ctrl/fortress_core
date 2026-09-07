"""Tests de check_session_log_freshness.py (M3-fix, auditoría 2026-09-07).

Cubre las dos brechas de la auditoría:
  - fecha futura en header -> WARNING, rc=1 (nunca OK)
  - sin secciones recientes (>48h) -> rc=1
  - regresión: una fecha futura en el *cuerpo* NO engana el check
"""
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check_session_log_freshness.py"


def _run(content: str, tmp_path):
    p = tmp_path / "SESSION_LOG.md"
    p.write_text(content, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(p)],
        capture_output=True, text=True,
    )


def test_future_date_header_is_warning(tmp_path):
    content = "## 2099-12-01 — entrada del futuro\n\nalgo de texto\n"
    r = _run(content, tmp_path)
    assert r.returncode == 1
    out = (r.stderr + r.stdout).lower()
    assert "warning" in out
    assert "futura" in out


def test_no_recent_section_is_rc1(tmp_path):
    content = "## 2026-01-01 — entrada vieja\n\nalgo\n"
    r = _run(content, tmp_path)
    assert r.returncode == 1
    assert "warning" in (r.stderr + r.stdout).lower()


def test_recent_section_is_ok(tmp_path):
    hoy = date.today().isoformat()
    content = f"## {hoy} — entrada de hoy\n\nalgo\n"
    r = _run(content, tmp_path)
    assert r.returncode == 0
    assert "ok" in (r.stdout + r.stderr).lower()


def test_body_date_not_counted(tmp_path):
    # La fecha futura esta en el CUERPO, no en header -> no engana el check.
    hoy = date.today().isoformat()
    content = (
        f"## {hoy} — entrada de hoy\n\n"
        "nota: el gate de diciembre es 2026-12-01, no afecta este check\n"
    )
    r = _run(content, tmp_path)
    assert r.returncode == 0
    assert "ok" in (r.stdout + r.stderr).lower()
