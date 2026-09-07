#!/bin/bash
# tz_dispatcher.sh — Frente 1 (fix Kilo 07/09).
#
# launchd lo corre cada 5 min (StartInterval=300, ver com.fortresscore.pipeline.plist).
# Computa la hora en America/New_York (ET) EN RUNTIME (DST-proof, sin offset
# fijo) y dispara daily_signal_pipeline.sh UNA vez por ventana
# (enter/exit/decide) usando un state-file anti-doble-disparo.
#
# POR QUÉ EXISTE (raíz del bug de auditoría):
#   El plist viejo usaba StartCalendarInterval en la hora LOCAL del sistema
#   (ART, UTC-3), pero daily_signal_pipeline.sh espera ventanas en ET (9/15/22).
#   launchd disparaba a 9:35/15:40/22:10 ART => ET real 8:35/14:40/21:10
#   (verano, -1h) o 7:35/13:40/20:10 (invierno tras 2/11, -2h) => hour_ET
#   nunca era 9/15/22 => siempre caía en `health` y decide/exit/reconciler
#   NUNCA corrían (0 líneas reconcile en producción).
#
# DST-proof: la hora ET se calcula siempre con `TZ=America/New_York date`
# (misma fuente que el pipeline). No hay offset hardcodeado, así que el
# "fall back" del 2/11 no rompe nada: el dispatcher simplemente ve la hora
# ET correcta en cada tick de 5 min.
#
# Anti-doble-disparo: por cada ventana se guarda la fecha ET del último
# disparo; si ya corrió hoy para esa ventana, se salta. Cubre el caso de que
# el pipeline tarde >5 min (el siguiente tick no lo re-dispara).
set -u

REPO="/Users/boris/Desktop/fortress_core"
DIR="$REPO/scripts"
# tz_dispatcher_lib.py vive en backend/scripts/ (package `scripts` importable por
# los tests); se invoca por path absoluto con el python del sistema (stdlib-only).
LIB="$REPO/backend/scripts/tz_dispatcher_lib.py"
PIPELINE="$DIR/daily_signal_pipeline.sh"
LOG="$REPO/scripts/tz_dispatcher.log"
STATE_DIR="${TZ_DISPATCHER_STATE_DIR:-$REPO/backend/data/cache/tz_dispatcher}"

mkdir -p "$STATE_DIR"

# Hora en ET (DST-proof: `date` usa la base de datos de zonas del sistema).
ET_H=$(TZ="America/New_York" date +%H)
ET_M=$(TZ="America/New_York" date +%M)
ET_D=$(TZ="America/New_York" date +%Y-%m-%d)
TS=$(date '+%Y-%m-%d %H:%M:%S')

# ¿En qué ventana estamos? (lógica espejo de daily_signal_pipeline.sh)
WINDOW=$(/usr/bin/python3 "$LIB" window --hour "$ET_H" --minute "$ET_M" 2>/dev/null)
if [ -z "$WINDOW" ]; then
  # Fuera de las ventanas objetivo: no spam de health. Salimos limpio.
  exit 0
fi

# Anti-doble-disparo: si ya corrimos esta ventana hoy (fecha ET), salir.
ALREADY=$(/usr/bin/python3 "$LIB" fired --window "$WINDOW" --date "$ET_D" --state-dir "$STATE_DIR" 2>/dev/null)
if [ "$ALREADY" = "yes" ]; then
  echo "$TS tz_dispatcher: ventana=$WINDOW fecha=$ET_D YA disparada hoy -> skip" >> "$LOG"
  exit 0
fi

# Marcamos ANTES de invocar para evitar re-entrada si el pipeline tarda >5min.
/usr/bin/python3 "$LIB" mark --window "$WINDOW" --date "$ET_D" --state-dir "$STATE_DIR" >/dev/null 2>&1

echo "$TS tz_dispatcher: disparando pipeline (ventana=$WINDOW, ET=${ET_H}:${ET_M}, fecha=$ET_D)" >> "$LOG"
exec "$PIPELINE"
