"""Tests del tz_dispatcher (Frente 1 — fix Kilo 07/09).

Cubren la lógica pura de scripts/tz_dispatcher_lib.py:
- select_window: mapea (hour, minute) ET -> enter/exit/decide, y None fuera.
- anti-doble-disparo: una vez por ventana por día ET (state file).
- DST-proof: el cálculo ET es correcto en ambos regímenes (invierno EST
  UTC-5 / verano EDT UTC-4) sin offset fijo.

No toca launchd ni la red: se prueba la librería directamente.
"""
from datetime import datetime, timezone

import pytest

from scripts import tz_dispatcher_lib as lib


# ---------------------------------------------------------------------------
# Ventanas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hour,minute,expected", [
    (9, 34, None), (9, 35, "enter"), (9, 40, "enter"), (9, 45, "enter"), (9, 46, None),
    (15, 34, None), (15, 35, "exit"), (15, 40, "exit"), (15, 45, "exit"), (15, 46, None),
    (22, 4, None), (22, 5, "decide"), (22, 10, "decide"), (22, 15, "decide"), (22, 16, None),
    (8, 35, None), (10, 0, None), (16, 40, None), (23, 10, None),
])
def test_select_window(hour, minute, expected):
    assert lib.select_window(hour, minute) == expected


def test_window_ranges_match_pipeline_contract():
    """Las ventanas del dispatcher deben coincidir EXACTAMENTE con las que
    daily_signal_pipeline.sh resuelve internamente (9:35-45 / 15:35-45 /
    22:5-15), para no disparar 'antes' y producir un health en vez de la fase."""
    # enter
    assert lib.select_window(9, 35) == "enter" and lib.select_window(9, 45) == "enter"
    assert lib.select_window(9, 34) is None and lib.select_window(9, 46) is None
    # exit
    assert lib.select_window(15, 35) == "exit" and lib.select_window(15, 45) == "exit"
    # decide
    assert lib.select_window(22, 5) == "decide" and lib.select_window(22, 15) == "decide"


# ---------------------------------------------------------------------------
# Anti-doble-disparo (state file)
# ---------------------------------------------------------------------------

def test_no_double_fire_same_window_same_day(tmp_path):
    sd = str(tmp_path)
    assert lib.already_fired(sd, "enter", "2026-09-07") is False
    lib.mark_fired(sd, "enter", "2026-09-07")
    assert lib.already_fired(sd, "enter", "2026-09-07") is True


def test_fire_state_is_per_window_and_per_day(tmp_path):
    sd = str(tmp_path)
    lib.mark_fired(sd, "enter", "2026-09-07")
    # otra ventana del mismo día: libre
    assert lib.already_fired(sd, "exit", "2026-09-07") is False
    # misma ventana otro día: libre (se debe volver a disparar)
    assert lib.already_fired(sd, "enter", "2026-09-08") is False


def test_dispatcher_fires_once_per_window_per_day(tmp_path):
    """Simula el bucle del dispatcher: el primer tick de la ventana dispara;
    los ticks siguientes del mismo día (hasta 5 min después) NO re-disparan."""
    sd = str(tmp_path)
    date_et = "2026-09-07"

    def would_fire(hour, minute):
        w = lib.select_window(hour, minute)
        if w is None:
            return "skip_outside_window"
        if lib.already_fired(sd, w, date_et):
            return "skip_already_fired"
        lib.mark_fired(sd, w, date_et)
        return f"FIRE:{w}"

    # Tres ticks dentro de la ventana enter (9:35, 9:40, 9:45)
    assert would_fire(9, 35) == "FIRE:enter"
    assert would_fire(9, 40) == "skip_already_fired"
    assert would_fire(9, 45) == "skip_already_fired"
    # La ventana decide del mismo día es independiente y sí dispara una vez
    assert would_fire(22, 10) == "FIRE:decide"
    assert would_fire(22, 12) == "skip_already_fired"


# ---------------------------------------------------------------------------
# DST-proof (cálculo ET sin offset fijo)
# ---------------------------------------------------------------------------

def test_et_winter_est():
    """Invierno 2026: 2026-01-15 14:00 UTC = 09:00 EST (UTC-5)."""
    d, h, m = lib.et_from_utc(datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc))
    assert d == "2026-01-15"
    assert h == 9 and m == 0


def test_et_summer_edt():
    """Verano 2026: 2026-07-15 13:00 UTC = 09:00 EDT (UTC-4)."""
    d, h, m = lib.et_from_utc(datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc))
    assert d == "2026-07-15"
    assert h == 9 and m == 0


def test_et_has_no_fixed_offset():
    """La misma hora LOCAL ET (09:00) cae en dos instantes UTC distintos según
    la estación (14:00 UTC en invierno vs 13:00 UTC en verano). Esto demuestra
    que el cálculo NO usa un offset fijo (el bug original: launchd en ART
    hardcodeaba -3h y el 2/11 el desfase crecía a -2h)."""
    winter = lib.et_from_utc(datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc))
    summer = lib.et_from_utc(datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc))
    # Ambos resuelven 09:00 ET...
    assert winter[1] == 9 and summer[1] == 9
    # ...pero provienen de instantes UTC distintos (offset 5h vs 4h).
    assert winter[0] == "2026-01-15"
    assert summer[0] == "2026-07-15"
