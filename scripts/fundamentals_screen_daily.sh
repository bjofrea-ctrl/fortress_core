#!/bin/bash
# Screening automatizado de fundamentales — fortress_core
# (launchd: com.fortresscore.fundamentals_screen)
#
# Cierra la brecha del screening manual: antes el motor corría con un
# export manual de InvestingPro (cada corrida requería que el operador
# bajara el xlsx). Ahora corre solo al cierre del mercado US (22:30 local,
# ~16:30 ET en verano / ~17:30 ET en invierno), después de dataupdater.
#
# Qué produce este job (todo en data/cache_fundamentals_screen/):
#   - screen_<fecha>.json          → endpoint /api/fundamentals/screen
#   - dashboard_<fecha>.html       → endpoint /screen/dashboard.html
#   - Screening_AAI_<fecha>.xlsx   → endpoint /screen/export.xlsx
#   - state.json                    → estado del job (resume / cuota)
# El Excel y el HTML los genera el motor canónico real (vendorizado en
# app/core/motor_canonico/) vía run_fundamentals_screen.py → render_artifacts.
#
# Política de cuota FMP (free tier, 250/día, 5 endpoints/ticker):
#   - El job corre una vez por día a las 22:30. Si falla a mitad, NO
#     se reintenta el mismo día (eso quemaría la cuota del día siguiente
#     y los datos no van a aparecer hoy de todos modos).
#   - Al día siguiente, con --resume, retoma desde el último símbolo
#     exitoso leyendo state.json. Idempotente.
#   - Ver: scripts/run_fundamentals_screen.py para los detalles del loop.
#
# Orden del orquestador (cron decide; este script sólo invoca):
#   1. dataupdater (22:00) — refresca precios del universo 50
#   2. fundamentals_screen (22:30) — ingesta FMP + screening + render
#      El gap de 30min deja que yfinance termine primero y no compitan
#      por CPU/red.
#
# Notas de diseño:
#   - NO toca credenciales: las claves viven en .env (FMP_API_KEY) — el
#     python las lee via Settings; este bash no las ve.
#   - Logs append a scripts/fundamentals_screen_daily.log. launchd además
#     captura stdout/stderr en fundamentals_screen_launchd.log.
#   - El auto-backup git (otro job launchd) captura el state.json a los 10min.
set -u
REPO="/Users/boris/Desktop/fortress_core"
VENV="$REPO/backend/.venv/bin/python"
LOG="$REPO/scripts/fundamentals_screen_daily.log"
LAUNCHD_LOG="$REPO/scripts/fundamentals_screen_launchd.log"

echo "=====================================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] fundamentals_screen_daily: inicio" >> "$LOG"

# cwd=backend es OBLIGATORIO: igual que data_updater.sh, los imports
# relativos y CACHE_DIR resuelven contra backend/. Sin este cd, launchd
# (cwd fuera del repo) rompe el import con ModuleNotFoundError.
cd "$REPO/backend" || { echo "FATAL: no se pudo cd a $REPO/backend" >> "$LOG"; exit 1; }

# Lanzar el job. --resume permite retomar al día siguiente si el anterior
# quedó a mitad. Sin --resume, el primer job del día arranca limpio
# PERO hereda state.json (calls_used, completed_symbols, failed_symbols).
# Por eso el script de Python distingue entre --resume y arranque limpio.
"$VENV" -m scripts.run_fundamentals_screen --resume >> "$LAUNCHD_LOG" 2>&1
RC=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] fundamentals_screen_daily: fin (rc=$RC)" >> "$LOG"
exit $RC