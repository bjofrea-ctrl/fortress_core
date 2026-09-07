"""Lógica pura del tz_dispatcher (Frente 1 — fix Kilo 07/09).

Stdlib-only, SIN imports de `app.*` para poder correr bajo launchd con el
python del sistema (sin activar el venv). Toda la decisión de disparo vive
acá; el bash `tz_dispatcher.sh` (en scripts/ raíz) sólo computa la hora ET
(con `TZ=America/New_York date`, igual que daily_signal_pipeline.sh) y delega
ventana + state a este módulo.

Responsabilidades:
- select_window(hour, minute) -> "enter" | "exit" | "decide" | None
    Rangos ESPEJO EXACTO de daily_signal_pipeline.sh para que el pipeline
    resuelva la fase correcta y el dispatcher nunca dispare "antes" de la
    ventana (lo que produciría un health en vez de enter/exit/decide).
- state_path / already_fired / mark_fired  -> anti-doble-disparo (una vez
    por ventana por día ET).
- et_from_utc / compute_et_now -> DST-proof vía ZoneInfo. Usadas en tests
    para demostrar que el cálculo ET es correcto en ambos regímenes DST
    (verano EDT = UTC-4 / invierno EST = UTC-5) SIN offset fijo.

Por qué esto arregla el bug: el plist viejo usaba StartCalendarInterval en la
hora LOCAL del sistema (ART, UTC-3), pero el pipeline espera ventanas en ET
(9/15/22). launchd disparaba a 9:35/15:40/22:10 ART => ET real 8:35/14:40/
21:10 (verano) o 7:35/13:40/20:10 (invierno, tras 2/11) => hour_ET nunca era
9/15/22 => siempre caía en health y decide/exit/reconciler NUNCA corrían.
Ahora el dispatcher corre cada 5 min y dispara sobre ET computado en runtime.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo

    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - macOS siempre tiene la tz
    _NY = None

# Ventanas = espejo exacto de daily_signal_pipeline.sh (mismos rangos).
#   enter  : 09:35-09:45 ET  (primer hábil del mes)
#   exit   : 15:35-15:45 ET  (último hábil del mes)
#   decide : 22:05-22:15 ET  (último hábil del mes, tras data_updater)
WINDOWS = {
    "enter": (9, 35, 45),
    "exit": (15, 35, 45),
    "decide": (22, 5, 15),
}


def select_window(hour: int, minute: int):
    """Devuelve el nombre de ventana para (hour, minute) ET, o None fuera."""
    for name, (h, lo, hi) in WINDOWS.items():
        if hour == h and lo <= minute <= hi:
            return name
    return None


def state_path(state_dir: str, window: str) -> str:
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"{window}.last")


def already_fired(state_dir: str, window: str, date_et: str) -> bool:
    """True si la ventana ya disparó para la fecha ET dada (anti-doble)."""
    p = state_path(state_dir, window)
    try:
        with open(p) as fh:
            return fh.read().strip() == date_et
    except OSError:
        return False


def mark_fired(state_dir: str, window: str, date_et: str) -> None:
    p = state_path(state_dir, window)
    with open(p, "w") as fh:
        fh.write(date_et)


def et_from_utc(dt_utc: datetime):
    """(fecha_ET, hora_ET, minuto_ET) desde un instante UTC. DST-proof."""
    if _NY is None:  # pragma: no cover
        raise RuntimeError("zoneinfo America/New_York no disponible")
    dt_et = dt_utc.astimezone(_NY)
    return dt_et.strftime("%Y-%m-%d"), dt_et.hour, dt_et.minute


def compute_et_now():
    return et_from_utc(datetime.now(timezone.utc))


def _default_state_dir() -> str:
    # Este módulo vive en backend/scripts/; el estado va a
    # backend/data/cache/tz_dispatcher (regenerable, ignorado por .gitignore).
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo, "data", "cache", "tz_dispatcher")


def _cli() -> None:
    ap = argparse.ArgumentParser(description="tz_dispatcher logic (pure)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("window", help="imprime la ventana para --hour/--minute")
    w.add_argument("--hour", type=int, required=True)
    w.add_argument("--minute", type=int, required=True)

    f = sub.add_parser("fired", help="¿ya disparó hoy? imprime yes/no")
    f.add_argument("--window", required=True)
    f.add_argument("--date", required=True)
    f.add_argument("--state-dir", default=_default_state_dir())

    m = sub.add_parser("mark", help="marca la ventana como disparada hoy")
    m.add_argument("--window", required=True)
    m.add_argument("--date", required=True)
    m.add_argument("--state-dir", default=_default_state_dir())

    sub.add_parser("et-now", help="imprime la fecha/hora ET actual")

    args = ap.parse_args()
    if args.cmd == "window":
        win = select_window(args.hour, args.minute)
        print(win or "")
    elif args.cmd == "fired":
        print("yes" if already_fired(args.state_dir, args.window, args.date) else "no")
    elif args.cmd == "mark":
        mark_fired(args.state_dir, args.window, args.date)
    elif args.cmd == "et-now":
        d, h, mi = compute_et_now()
        print(f"{d} {h:02d}:{mi:02d}")


if __name__ == "__main__":
    _cli()
