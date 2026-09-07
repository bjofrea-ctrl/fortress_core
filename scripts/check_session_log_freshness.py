#!/usr/bin/env python3
"""M3: avisa si SESSION_LOG.md no tiene entrada en las últimas 48h.

El ritual de cierre de sesión (ONBOARDING) exige dejar rastro en
SESSION_LOG.md; si la última entrada tiene más de 48h, se imprime un
WARNING visible (pensado para correr en el latido / cron diario). Sale 0
si está al día, 1 si está desactualizado.

CORRECCIÓN de auditoría (2026-09-07):
  - Solo se parsean los headers de sección ('## ...' a nivel h2). Una fecha
    que aparezca en el *cuerpo* del texto NO se considera. Dentro de cada
    header se toma la PRIMER fecha 'YYYY-MM-DD' de la línea, así cubre ambos
    formatos usados en el log real: '## 2026-09-06 — título' y
    '## B8 — ... (2026-09-06, Cline)'.
  - Una fecha futura no puede hacer que el check pase: se ignora para el
    cálculo de frescura y se emite un WARNING de fecha futura (rc=1).
"""
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_AGE_HOURS = 48
LOG_PATH = Path(__file__).resolve().parents[1] / "SESSION_LOG.md"

# Lineas de header de sección (h2). No matchea h3+ (### ...) ni cuerpo.
HEADER_RE = re.compile(r"^##\s.*$", re.MULTILINE)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def section_dates(path: Path):
    """Fechas (datetime) de los headers de sección '## ...'.

    De cada línea-header se toma la primera 'YYYY-MM-DD'.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    fechas = []
    for m in HEADER_RE.finditer(text):
        dm = DATE_RE.search(m.group(0))
        if not dm:
            continue
        try:
            fechas.append(datetime.strptime(dm.group(1), "%Y-%m-%d"))
        except ValueError:
            continue
    return fechas


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else LOG_PATH
    ahora = datetime.now()

    fechas = section_dates(path)
    if not fechas:
        print(
            f"[SESSION-LOG] WARNING: {path} sin headers de sección '## ...' "
            f"— ritual de cierre roto",
            file=sys.stderr,
        )
        return 1

    futuras = [d for d in fechas if d > ahora]
    pasadas = [d for d in fechas if d <= ahora]

    avisos = []
    if futuras:
        fs = ", ".join(sorted({d.date().isoformat() for d in futuras}))
        avisos.append(f"fecha(s) futura(s): {fs}")

    if not pasadas:
        avisos.append("sin entradas válidas (todas las secciones en el futuro)")
        print(f"[SESSION-LOG] WARNING: {path}: " + "; ".join(avisos), file=sys.stderr)
        return 1

    ultima = max(pasadas)
    edad_h = (ahora - ultima).total_seconds() / 3600.0
    if edad_h > MAX_AGE_HOURS:
        avisos.append(f"última entrada hace {edad_h:.0f}h (> {MAX_AGE_HOURS}h)")
        print(f"[SESSION-LOG] WARNING: {path}: " + "; ".join(avisos), file=sys.stderr)
        return 1

    print(f"[SESSION-LOG] OK: última entrada {ultima.date()} (hace {edad_h:.0f}h)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
