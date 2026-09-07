#!/usr/bin/env python3
"""M3: avisa si SESSION_LOG.md no tiene entrada en las últimas 48h.

El ritual de cierre de sesión (ONBOARDING) exige dejar rastro en
SESSION_LOG.md; si la última entrada tiene más de 48h, se imprime un
WARNING visible (pensado para correr en el latido / cron diario). Sale 0
si está al día, 1 si está desactualizado — así un orquestador o cron puede
fallar ruidosamente antes de que el rastro se pierda.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_AGE_HOURS = 48
LOG_PATH = Path(__file__).resolve().parents[1] / "SESSION_LOG.md"


def latest_entry_date(path: Path) -> "datetime | None":
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    fechas = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if not fechas:
        return None
    return max(datetime.strptime(f, "%Y-%m-%d") for f in fechas)


def main() -> int:
    ultima = latest_entry_date(LOG_PATH)
    ahora = datetime.now()
    if ultima is None:
        print(
            f"[SESSION-LOG] WARNING: {LOG_PATH} sin fechas — ritual de cierre roto",
            file=sys.stderr,
        )
        return 1
    edad_h = (ahora - ultima).total_seconds() / 3600.0
    if edad_h > MAX_AGE_HOURS:
        print(
            f"[SESSION-LOG] WARNING: última entrada en {ultima.date()} "
            f"hace {edad_h:.0f}h (> {MAX_AGE_HOURS}h) — actualizar SESSION_LOG.md",
            file=sys.stderr,
        )
        return 1
    print(f"[SESSION-LOG] OK: última entrada {ultima.date()} (hace {edad_h:.0f}h)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
