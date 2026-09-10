"""Tests de scripts.nyse_holidays (fix auditoría 2026-09-09).

El updater diario descargaba por yfinance incluso en feriados NYSE:
Labor Day 2026-09-07 dio "PRECIOS: ERROR - 84/102" falso (mercado cerrado,
no roto) y rompió la condición (b) del gate. El módulo es un calendario
estático (cero red) — estos tests fijan fechas reales conocidas.
"""
import datetime as dt
import subprocess
import sys

import pytest

from scripts import nyse_holidays as nh


@pytest.mark.parametrize("iso,name_frag", [
    ("2026-09-07", "Labor"),
    ("2026-11-26", "Thanksgiving"),
    ("2026-12-25", "Christmas"),
    ("2026-07-03", "Independence"),
    ("2026-01-01", "Año Nuevo"),
    ("2026-04-03", "Good Friday"),
    ("2025-01-09", "Carter"),
    ("2025-09-01", "Labor"),
    ("2027-11-25", "Thanksgiving"),
    ("2027-12-24", "Christmas"),
])
def test_feriados_conocidos(iso, name_frag):
    assert nh.is_nyse_holiday(iso) is True
    assert nh.is_nyse_holiday(dt.date.fromisoformat(iso)) is True
    assert name_frag in (nh.holiday_name(iso) or "")


@pytest.mark.parametrize("iso", [
    "2026-09-08",  # mar: día después de Labor Day hay rueda
    "2026-09-09",  # mié
    "2026-09-04",  # vie antes de Labor Day hay rueda
    "2026-11-27",  # vie después de Thanksgiving (Black Friday: hay rueda)
    "2026-09-05",  # sáb (fin de semana ≠ feriado: el módulo solo lista cierres)
    "2026-09-06",  # dom
])
def test_dias_con_rueda(iso):
    assert nh.is_nyse_holiday(iso) is False
    assert nh.holiday_name(iso) is None


def test_cli_today_quiet_exit_codes():
    """--today-quiet: exit 0 + línea si feriado, exit 1 silencioso si rueda."""
    r = subprocess.run(
        [sys.executable, "-m", "scripts.nyse_holidays",
         "--date", "2026-09-07", "--today-quiet"],
        capture_output=True, text=True, cwd=".",
    )
    assert r.returncode == 0
    assert "feriado NYSE" in r.stdout and "Labor" in r.stdout

    r = subprocess.run(
        [sys.executable, "-m", "scripts.nyse_holidays",
         "--date", "2026-09-08", "--today-quiet"],
        capture_output=True, text=True, cwd=".",
    )
    assert r.returncode == 1
    assert r.stdout.strip() == ""


def test_skip_no_dispara_condicion_b():
    """La línea PRECIOS: SKIP del updater en feriado NO debe matchear el
    chequeo de condición (b) (busca el substring 'PRECIOS: ERROR')."""
    from scripts import clean_days_counter as cc

    skip_block = "\n".join([
        "[2026-09-07 22:00:01] data_updater: inicio",
        "feriado NYSE: Labor Day (2026-09-07) — mercado cerrado",
        "PRECIOS: SKIP - feriado NYSE, mercado cerrado (no es error)",
        "precios: SKIP feriado NYSE 0/0",
        "[2026-09-07 22:00:02] data_updater: fin (acumulacion rc=0)",
    ])
    days = cc.parse_updater_days(skip_block)
    ev = cc.evaluar_condicion_b(days, "2026-09-07")
    assert ev["corrida"] is True
    assert ev["ok"] is True
