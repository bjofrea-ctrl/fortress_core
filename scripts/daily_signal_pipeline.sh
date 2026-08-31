#!/bin/bash
# Pipeline diario señal→orden papel→ledger (Frente 2).
# Diseño: PLAN_PIPELINE_DIARIO_FRENTE2.md. Patrón idéntico a data_updater.sh:
# set -u SIN set -e (un fallo de fase no saltea el log final), cd backend
# OBLIGATORIO (imports 'app.*' y CACHE_DIR relativo), venv directo, exit 0.
#
# Fases (cadencia MENSUAL fiel al backtest):
#   decide  ~22:10 ET tras data_updater, último hábil del mes
#   enter   ~09:35 ET primer hábil del mes
#   exit    ~15:40 ET último hábil del mes
#   health  cualquier día (chequeo de frescura)
#
# launchd corre este script 3 veces al día; la lógica de abajo decide qué fase
# ejecutar según la hora y el calendario de hábiles del mercado (parquet SPY).
set -u

REPO="/Users/boris/Desktop/fortress_core"
VENV="$REPO/backend/.venv/bin/python"
LOG="$REPO/scripts/pipeline_diario.log"

# Hora actual en ET (UTC-4 o UTC-5 según DST)
HOUR_ET=$(TZ="America/New_York" date +%H)
MIN_ET=$(TZ="America/New_York" date +%M)

# Función para detectar si hoy es el último hábil del mes (usa el calendario del parquet SPY)
is_last_business_day() {
    "$VENV" -c "
import datetime as dt, sys
sys.path.insert(0, '.')
from scripts.pipeline_daily_signal import trading_days, month_bounds
days = trading_days()
first, last = month_bounds(days, dt.date.today())
sys.exit(0 if (last and dt.date.today() == last) else 1)
" 2>/dev/null
}

# Función para detectar si hoy es el primer hábil del mes
is_first_business_day() {
    "$VENV" -c "
import datetime as dt, sys
sys.path.insert(0, '.')
from scripts.pipeline_daily_signal import trading_days, month_bounds
days = trading_days()
first, last = month_bounds(days, dt.date.today())
sys.exit(0 if (first and dt.date.today() == first) else 1)
" 2>/dev/null
}

{
echo "====================================================================="
echo "pipeline_daily_signal $(date '+%Y-%m-%d %H:%M:%S') start (hour_ET=$HOUR_ET)"
cd "$REPO/backend" || { echo "$(date) FATAL: cd backend falló"; exit 1; }

PHASE=""
if [ "$HOUR_ET" -eq 9 ] && [ "$MIN_ET" -ge 35 ] && [ "$MIN_ET" -le 45 ]; then
    # ~09:35 ET: ENTER si es primer hábil del mes, health si no
    if is_first_business_day; then
        PHASE="enter"
    else
        PHASE="health"
    fi
elif [ "$HOUR_ET" -eq 15 ] && [ "$MIN_ET" -ge 35 ] && [ "$MIN_ET" -le 45 ]; then
    # ~15:40 ET: EXIT si es último hábil del mes, health si no
    if is_last_business_day; then
        PHASE="exit"
    else
        PHASE="health"
    fi
elif [ "$HOUR_ET" -eq 22 ] && [ "$MIN_ET" -ge 5 ] && [ "$MIN_ET" -le 15 ]; then
    # ~22:10 ET: DECIDE si es último hábil del mes, health si no
    if is_last_business_day; then
        PHASE="decide"
    else
        PHASE="health"
    fi
else
    # Fuera de ventanas programadas: health (chequeo de rutina)
    PHASE="health"
fi

echo "Fase detectada: $PHASE"
"$VENV" -m scripts.pipeline_daily_signal --phase "$PHASE"
rc=$?
echo "pipeline_daily_signal end rc=$rc"
} >> "$LOG" 2>&1

exit 0
