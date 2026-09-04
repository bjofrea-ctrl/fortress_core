"""
Tests de A8 (PLAN_REMEDIO_BRECHAS_20260903 §A8) — PBO §39 lag-0, docs-only.

A8 es documentación + pre-registro, NO código de producción ni trial que
se ejecute durante el gate. Los tests verifican la ESTRUCTURA de los
artefactos que A8 debe dejar:

  1. `PLAN_MEJORA_MATEMATICA.md` tiene una nueva sección `### 40.1` que
     declara la limitación lag-0 del PBO=0.2358 vigente.
  2. `PRE_REGISTRO_PBO_BASELINE_LAG0_20260903.md` existe y cumple los
     requisitos del plan: naturaleza bugfix, cita la Regla 1 de
     ONBOARDING.md, no se ejecuta durante el gate.
  3. La estructura del pre-registro es coherente con el patrón del
     proyecto (pre-registros previos).

Los tests son herméticos: no tocan red, no escriben en el ledger, no
ejecutan scripts. Son una red de seguridad para que un cambio futuro
que rompa la declaración A8 (borrar el archivo, mover la sección)
rompa ruidoso este test.
"""
import pathlib
import re

# ============================================================ paths


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PLAN_MATH = REPO_ROOT / "PLAN_MEJORA_MATEMATICA.md"
PR_LAG0 = REPO_ROOT / "PRE_REGISTRO_PBO_BASELINE_LAG0_20260903.md"


def _read(path: pathlib.Path) -> str:
    assert path.exists(), f"A8: archivo faltante: {path}"
    return path.read_text(encoding="utf-8")


# ============================================================ §40.1 nota


class TestSeccion401:
    """A8 deja una nota §40.1 declarando la limitación lag-0 del PBO=0.2358."""

    def test_seccion_40_1_existe_en_plan(self):
        """`### 40.1` aparece en PLAN_MEJORA_MATEMATICA.md."""
        content = _read(PLAN_MATH)
        assert re.search(r"^### 40\.1\b", content, re.MULTILINE), (
            "A8: falta la sección `### 40.1` en PLAN_MEJORA_MATEMATICA.md"
        )

    def test_seccion_40_1_esta_entre_40_y_41(self):
        """`### 40.1` aparece DESPUÉS de `## 40.` y ANTES de `## 41.`."""
        content = _read(PLAN_MATH)
        m40 = list(re.finditer(r"^## 40\.", content, re.MULTILINE))
        m401 = list(re.finditer(r"^### 40\.1\b", content, re.MULTILINE))
        m41 = list(re.finditer(r"^## 41\.", content, re.MULTILINE))
        assert len(m40) == 1, "A8: falta la sección `## 40.`"
        assert len(m401) == 1, "A8: falta la sección `### 40.1`"
        assert len(m41) == 1, "A8: falta la sección `## 41.`"
        assert m40[0].start() < m401[0].start() < m41[0].start(), (
            "A8: la sección `### 40.1` debe estar entre `## 40.` y `## 41.`"
        )

    def test_seccion_40_1_declara_limitacion_lag(self):
        """§40.1 menciona lag-0 / open(m)→close(m) / PBO=0.2358."""
        content = _read(PLAN_MATH)
        # extraer el bloque §40.1
        m = re.search(
            r"^### 40\.1.*?(?=^## |\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert m, "A8: no se pudo extraer la sección §40.1"
        block = m.group(0)
        assert "0.2358" in block, "A8: §40.1 debe mencionar el PBO=0.2358 vigente"
        assert "lag" in block.lower(), "A8: §40.1 debe hablar del lag de ejecución"
        assert "open(m)" in block and "close(m)" in block, (
            "A8: §40.1 debe explicitar las dos convenciones open(m)→close(m) vs close[m-1]→close[m]"
        )

    def test_seccion_40_1_cita_plan_remedio(self):
        """§40.1 referencia el ticket A8 y el archivo de pre-registro."""
        content = _read(PLAN_MATH)
        m = re.search(
            r"^### 40\.1.*?(?=^## |\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        block = m.group(0)
        assert "A8" in block, "A8: §40.1 debe referenciar el ticket A8"
        assert "PRE_REGISTRO_PBO_BASELINE_LAG0_20260903.md" in block, (
            "A8: §40.1 debe apuntar al archivo de pre-registro"
        )

    def test_seccion_40_1_prohibe_durante_el_gate(self):
        """§40.1 es taxativo: NO se ejecuta durante el gate."""
        content = _read(PLAN_MATH)
        m = re.search(
            r"^### 40\.1.*?(?=^## |\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        block = m.group(0).lower()
        assert "no" in block and "gate" in block, (
            "A8: §40.1 debe declarar la prohibición de ejecutar durante el gate"
        )
        # chequeo más fuerte: la frase "no se ejecuta durante el gate"
        # debería aparecer textual o equivalente
        assert (
            "no se ejecuta durante el gate" in block
            or "no se corre durante el gate" in block
            or "prohibido durante el gate" in block
            or "prohibición de ejecutar" in block
        ), "A8: §40.1 debe ser explícito sobre la prohibición de ejecutar durante el gate"


# ============================================================ pre-registro


class TestPreRegistroLag0:
    """A8 deja el pre-registro del re-run con lag-0."""

    def test_pre_registro_lag0_existe(self):
        assert PR_LAG0.exists(), (
            f"A8: falta el archivo de pre-registro {PR_LAG0.name}"
        )

    def test_pre_registro_cita_a8_y_regla_1_de_onboarding(self):
        """El pre-registro referencia A8 del PLAN_REMEDIO_BRECHAS y la Regla 1
        de ONBOARDING.md (la del criterio pre-registrado), con su contenido."""
        content = _read(PR_LAG0)
        assert "A8" in content, "A8: el pre-registro debe referenciar el ticket A8"
        assert "ONBOARDING" in content, (
            "A8: el pre-registro debe citar ONBOARDING.md como fuente de la regla"
        )
        # El número correcto: la regla 1 (no existe una "Regla 0" en el repo).
        assert re.search(r"[Rr]eglas?\s*#?\s*1", content), (
            "A8: el pre-registro debe apuntar a la Regla 1 de ONBOARDING.md"
        )
        assert "Regla 0" not in content, (
            "A8: el pre-registro cita 'Regla 0', una regla que no existe en el repo"
        )
        # Y el contenido real de esa regla: se escribe ANTES, no se edita después.
        assert "ANTES" in content, (
            "A8: el pre-registro debe declarar que se escribe ANTES de correr"
        )
        assert "no se edita" in content.lower(), (
            "A8: el pre-registro debe prohibir editarlo tras ver el resultado"
        )

    def test_pre_registro_categoria_bugfix(self):
        """El pre-registro declara categoría=bugfix (per A8)."""
        content = _read(PR_LAG0)
        # Acepta mayúscula/minúscula, con o sin tilde, y con backticks o quotes
        assert re.search(
            r"[Cc]ategor[íi]a\s*[:=]\s*[`'\"]?bugfix[`'\"]?",
            content,
        ), "A8: el pre-registro debe declarar categoría=bugfix"

    def test_pre_registro_prohibe_durante_el_gate(self):
        """El pre-registro es taxativo sobre no ejecutarse durante el gate."""
        content = _read(PR_LAG0).lower()
        assert "no se ejecuta durante el gate" in content, (
            "A8: el pre-registro debe declarar explícitamente que NO se ejecuta durante el gate"
        )

    def test_pre_registro_declara_overrides_lag(self):
        """El pre-registro documenta que el override es LAG_DAYS=0 y la convención target open(m)→close(m)."""
        content = _read(PR_LAG0)
        assert "LAG_DAYS=0" in content or "EXECUTION_LAG_DAYS=0" in content or "lag=0" in content.lower(), (
            "A8: el pre-registro debe declarar el override LAG_DAYS=0"
        )
        assert "open(m)→close(m)" in content or "open(m) -> close(m)" in content, (
            "A8: el pre-registro debe mencionar la convención target open(m)→close(m)"
        )

    def test_pre_registro_tiene_umbral_y_criterio_pre_registrados(self):
        """Como todo pre-registro del proyecto, debe llevar umbral + criterio
        mecánicos declarados ANTES de ejecutarse (Regla 1 de ONBOARDING.md)."""
        content = _read(PR_LAG0)
        assert "umbral" in content.lower(), (
            "A8: el pre-registro debe mencionar el umbral pre-registrado"
        )
        # Criterio PBO bucket
        assert "0.20" in content and "0.50" in content, (
            "A8: el pre-registro debe llevar los cortes 0.20 y 0.50 del criterio"
        )

    def test_pre_registro_tiene_check_de_fidelidad(self):
        """Como los otros pre-registros, debe tener checks de fidelidad explícitos."""
        content = _read(PR_LAG0)
        assert "check" in content.lower() and "fidelidad" in content.lower(), (
            "A8: el pre-registro debe llevar checks de fidelidad"
        )

    def test_pre_registro_referencia_pre_registro_previo_seccion_39(self):
        """El re-run referencia §39 (PBO=0.2358 vigente) como baseline a re-medir."""
        content = _read(PR_LAG0)
        assert "§39" in content or "0.2358" in content, (
            "A8: el pre-registro debe referenciar §39 / PBO=0.2358 como baseline a re-medir"
        )

    def test_pre_registro_es_coherente_con_otros_pre_registros(self):
        """Estructura básica del proyecto: tiene 'Hipótesis', 'Método',
        'Criterio pre-registrado', 'Artefacto' (o equivalentes)."""
        content = _read(PR_LAG0)
        for seccion in ("Hipótesis", "Método", "Criterio", "Artefacto"):
            assert seccion in content, (
                f"A8: el pre-registro debe tener la sección `{seccion}` "
                f"(consistente con el patrón del proyecto)"
            )


# ============================================================ invariante


class TestA8EsSoloDocumentacion:
    """A8 es pura documentación — no toca código de producción."""

    def test_a8_no_toco_codigo_de_produccion(self):
        """Ningún archivo .py de `app/` debe haber sido modificado para A8.

        A8 es 100% documentación. Si alguien futuro intenta hacer un fix
        de código con la etiqueta A8, este test rompe ruidoso."""
        # El conftest del repo más los tests de A8 sí pueden haber sido
        # creados — ese es el cambio legítimo. Lo que NO debe haber es
        # cambios en `app/`.
        # (Este test se evalúa contra `git diff --name-only HEAD`.)
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        changed = [p for p in r.stdout.splitlines() if p]
        prod_python = [p for p in changed if p.startswith("app/") and p.endswith(".py")]
        assert not prod_python, (
            "A8 es documentación pura — los siguientes archivos de producción "
            "no deberían haber sido modificados:\n  " + "\n  ".join(prod_python)
        )
