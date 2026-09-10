"""Feriados NYSE — fix auditoría 2026-09-09.

El updater diario (scripts/data_updater.sh) descargaba los 102 símbolos por
yfinance TODOS los días. En un feriado NYSE (Labor Day 2026-09-07) yfinance
devuelve vacío para todo el universo y el log quedaba con
``PRECIOS: ERROR - 84/102 símbolos fallaron`` — falso positivo: el mercado
estaba cerrado, no roto. La condición (b) del gate (clean_days) lo marcaba
como día sucio.

Este módulo lista los cierres totales NYSE 2025-2027 (fuente: calendario
oficial NYSE; incluye el cierre especial 2025-01-09 (duelo nacional
Carter). data_updater.sh lo consulta ANTES del paso de precios:
si hoy es feriado → ``PRECIOS: SKIP`` (no ERROR) y rc=0.

Sin red, sin dependencias: un frozenset de fechas ISO. Agregar años futuros
extendiendo NYSE_HOLIDAYS (los feriados NYSE se conocen con años de
antelación; Thanksgiving = 4.º jueves de noviembre, etc.).

Uso shell (data_updater.sh):
    .venv/bin/python -m scripts.nyse_holidays --today-quiet >> "$LOG" 2>&1
    # exit 0 + línea "feriado NYSE: <nombre>" si hoy es feriado (mercado cerrado)
    # exit 1 silencioso si hoy hay rueda
Uso manual:
    .venv/bin/python -m scripts.nyse_holidays --date 2026-09-07
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

# Cierres totales NYSE {ISO: nombre} — única fuente canónica. Incluye
# observados (finde → viernes/lunes) y el cierre especial 2026-... no:
# 2025-01-09 (duelo nacional Jimmy Carter, cierre total real).
_HOLIDAYS = {
    # 2025
    "2025-01-01": "Año Nuevo",
    "2025-01-09": "Duelo nacional Carter",
    "2025-01-20": "MLK",
    "2025-02-17": "Presidents",
    "2025-04-18": "Good Friday",
    "2025-05-26": "Memorial Day",
    "2025-06-19": "Juneteenth",
    "2025-07-04": "Independence Day",
    "2025-09-01": "Labor Day",
    "2025-11-27": "Thanksgiving",
    "2025-12-25": "Christmas",
    # 2026
    "2026-01-01": "Año Nuevo",
    "2026-01-19": "MLK",
    "2026-02-16": "Presidents",
    "2026-04-03": "Good Friday",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observado)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving",
    "2026-12-25": "Christmas",
    # 2027
    "2027-01-01": "Año Nuevo",
    "2027-01-18": "MLK",
    "2027-02-15": "Presidents",
    "2027-03-26": "Good Friday",
    "2027-05-31": "Memorial Day",
    "2027-06-18": "Juneteenth (observado)",
    "2027-07-05": "Independence Day (observado)",
    "2027-09-06": "Labor Day",
    "2027-11-25": "Thanksgiving",
    "2027-12-24": "Christmas (observado)",
}
NYSE_HOLIDAYS = frozenset(_HOLIDAYS.keys())


def holiday_name(day: dt.date | str) -> str | None:
    """Nombre del feriado si `day` es cierre NYSE, None si hay rueda."""
    iso = day if isinstance(day, str) else day.isoformat()
    return _HOLIDAYS.get(iso)


def is_nyse_holiday(day: dt.date | str) -> bool:
    """True si `day` es feriado NYSE (mercado cerrado en día de semana)."""
    return holiday_name(day) is not None


def _cli() -> int:
    ap = argparse.ArgumentParser(description="Chequeo de feriados NYSE (cero red).")
    ap.add_argument("--date", default=None,
                    help="Fecha ISO a chequear (default: hoy local).")
    ap.add_argument("--today-quiet", action="store_true",
                    help="Modo data_updater.sh: exit 0 + línea si feriado, exit 1 silencioso si rueda.")
    args = ap.parse_args()
    day = dt.date.today().isoformat() if args.date is None else args.date
    name = holiday_name(day)
    if args.today_quiet:
        if name is not None:
            print(f"feriado NYSE: {name} ({day}) — mercado cerrado")
            return 0
        return 1
    if name is not None:
        print(f"{day}: HOLIDAY — {name} (mercado cerrado)")
    else:
        print(f"{day}: TRADING — hay rueda")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
