#!/usr/bin/env bash
# keep_awake_market_hours.sh — M5: Mac despierto en horario de mercado (09:25–16:05 ET, weekdays)
#
# Uso: ./scripts/keep_awake_market_hours.sh [--check]
#   --check: solo verifica si estamos en horario de mercado (exit 0=sí, 1=no), no ejecuta caffeinate
#
# Requiere: macOS (caffeinate, date, pmset). El script se auto-gestiona:
# - Si ya hay un caffeinate -i -s nuestro corriendo, no lanza otro.
# - Si salió del horario, mata nuestro caffeinate (si lo lanzamos nosotros).
# - Limpieza con trap en SIGTERM/SIGINT.

set -euo pipefail

SCRIPT_NAME="keep_awake_market_hours"
PID_FILE="/tmp/${SCRIPT_NAME}.pid"
CAFFEINATE_ARGS="-i -s"   # -i: prevent idle sleep; -s: prevent system sleep (AC power)

# --- Helpers ---
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SCRIPT_NAME] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$SCRIPT_NAME] ERROR: $*" >&2; }

# Hora actual en ET (America/New_York). macOS date respeta TZ.
now_et() { TZ=America/New_York date "$@"; }

# ¿Estamos en horario de mercado? Weekday (Mon-Fri) 09:25–16:05 ET.
in_market_hours() {
    local dow hour minute
    dow=$(now_et '+%u')        # 1=Mon .. 7=Sun
    hour=$(now_et '+%H')
    minute=$(now_et '+%M')
    # 10# fuerza base decimal (evita octal con leading zero)
    local hm=$((10#${hour} * 60 + 10#${minute}))
    [[ $dow -ge 1 && $dow -le 5 ]] && [[ $hm -ge 565 && $hm -le 965 ]]  # 09:25=565, 16:05=965
}

# PID del caffeinate que NOSOTROS lanzamos (guardado en PID_FILE)
our_caffeinate_pid() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null) || return 1
    # Verificar que el proceso sigue vivo Y es caffeinate
    kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o comm= | grep -q '^caffeinate$'
}

# Matar nuestro caffeinate si existe
kill_our_caffeinate() {
    if our_caffeinate_pid; then
        local pid
        pid=$(cat "$PID_FILE")
        log "Saliendo de horario de mercado — matando caffeinate (PID $pid)"
        kill "$pid" 2>/dev/null && rm -f "$PID_FILE"
        # Esperar un momento a que muera
        for _ in {1..10}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.2
        done
    fi
}

# Lanzar caffeinate -i -s en background, guardar PID
launch_caffeinate() {
    if our_caffeinate_pid; then
        log "caffeinate ya corriendo (PID $(cat "$PID_FILE")) — no se lanza otro"
        return 0
    fi
    log "Entrando en horario de mercado — lanzando caffeinate $CAFFEINATE_ARGS"
    caffeinate $CAFFEINATE_ARGS &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    log "caffeinate lanzado (PID $pid)"
}

# Limpieza al recibir señal
cleanup() {
    log "Señal recibida — limpiando"
    kill_our_caffeinate
    exit 0
}
trap cleanup SIGTERM SIGINT

# --- Main ---
if [[ "${1:-}" == "--check" ]]; then
    if in_market_hours; then
        log "CHECK: DENTRO de horario de mercado"
        exit 0
    else
        log "CHECK: FUERA de horario de mercado"
        exit 1
    fi
fi

log "Iniciado (PID $$). Horario mercado: 09:25–16:05 ET, Lun-Vie."

# Bucle principal: cada 30s chequea horario y gestiona caffeinate
while true; do
    if in_market_hours; then
        launch_caffeinate
    else
        kill_our_caffeinate
    fi
    sleep 30
done