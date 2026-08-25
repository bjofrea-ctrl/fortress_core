#!/bin/bash
# Pipeline diario señal→orden papel→ledger (Frente 2).
# Diseño: PLAN_PIPELINE_DIARIO_FRENTE2.md. Patrón idéntico a data_updater.sh:
# set -u SIN set -e (un fallo de fase no saltea el log final), cd backend
# OBLIGATORIO (imports 'app.*' y CACHE_DIR relativo), venv directo, exit 0.
#
# NOTA: este .sh se invoca desde launchd SOLO después de pasar el Checkpoint
# Semana 1 completo (corrida manual verificada: orden ejecutada + registro +
# re-run sin duplicados). Mientras tanto, correr fases a mano con:
#   cd backend && .venv/bin/python -m scripts.pipeline_daily_signal --phase <fase>
set -u

REPO="/Users/boris/Desktop/fortress_core"
VENV="$REPO/backend/.venv/bin/python"
LOG="$REPO/scripts/pipeline_diario.log"

{
echo "====================================================================="
echo "pipeline_daily_signal $(date '+%Y-%m-%d %H:%M:%S') start"
cd "$REPO/backend" || { echo "$(date) FATAL: cd backend falló"; exit 1; }
"$VENV" -m scripts.pipeline_daily_signal --phase auto
rc=$?
echo "pipeline_daily_signal end rc=$rc"
} >> "$LOG" 2>&1

exit 0
