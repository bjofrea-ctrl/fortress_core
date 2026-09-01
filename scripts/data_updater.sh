#!/bin/bash
# Actualización diaria de datos — fortress_core (launchd: com.fortresscore.dataupdater)
#
# Cierra la brecha de "datos manuales": antes el refresh de precios y la
# acumulación FinBERT dependían de que alguien los corriera a mano (el cache
# llegó a estar 5 ruedas desactualizado). Ahora corre solo al cierre del
# mercado US (22:00 local, ~16:00 ET en verano / ~17:00 ET en invierno).
#
# Orden: primero precios OHLCV (yfinance, incremental por fecha), después
# acumulación de sentimiento earnings (SEC EDGAR, incremental por accession).
# Cada paso loggea su resultado; un fallo de un paso NO saltea el siguiente.
#
# Notas de diseño:
#   - NO toca credenciales: yfinance y EDGAR (User-Agent declarativo) no
#     requieren claves. Las credenciales de Alpaca NO se usan acá.
#   - Logs con rotación manual mínima: se append a scripts/data_updater.log.
#   - El auto-backup git (otro job launchd) captura los datos a los 10 min.
set -u
REPO="/Users/boris/Desktop/fortress_core"
VENV="$REPO/backend/.venv/bin/python"
LOG="$REPO/scripts/data_updater.log"

echo "=====================================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] data_updater: inicio" >> "$LOG"

# 1) Precios OHLCV del universo dinámico (7 base + NEW_UNIVERSE desde fetch_universe_data.py, 102 símbolos actuales)
# cwd=backend es OBLIGATORIO acá: `scripts.fetch_universe_data` y el CACHE_DIR relativo
# ("data/cache" en app/core/data_ingestion.py) resuelven contra backend/. Sin este cd,
# launchd (cwd fuera del repo) rompe el import con ModuleNotFoundError — bug que dejó
# el cache de precios estancado entre 2026-08-15 y 2026-08-22 (detectado y fixeado).
# Resiliencia 2026-09-01: el paso de precios NUNCA queda silencioso — cualquier fallo
# (cd, import, red, yfinance) deja "PRECIOS: ERROR" explícito en el log.
if ! cd "$REPO/backend"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] PRECIOS: ERROR - cd $REPO/backend falló" >> "$LOG"
  RC_PRECIOS=1
else
  "$VENV" -c "
from scripts.fetch_universe_data import NEW_UNIVERSE
from app.core.data_ingestion import download_data
universe = ['SPY','QQQ','AAPL','MSFT','GOOGL','AMZN','NVDA'] + list(NEW_UNIVERSE)
import datetime, sys
fails = 0
for t in universe:
    try:
        df = download_data(t, '2015-01-01')
        print(f'  {t:6s} hasta {df.index[-1].date()}')
    except Exception as e:
        fails += 1
        print(f'  {t:6s} ERROR: {e}')
if fails:
    print(f'PRECIOS: ERROR - {fails}/{len(universe)} símbolos fallaron (ver líneas ERROR arriba)')
    sys.exit(1)
print(f'precios: {len(universe)-fails}/{len(universe)} OK')
" >> "$LOG" 2>&1
  RC_PRECIOS=$?
  if [ $RC_PRECIOS -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] PRECIOS: ERROR - paso precios rc=$RC_PRECIOS" >> "$LOG"
  fi
fi

# 2) Sentimiento de earnings — acumulación incremental (dedup por accession en SQLite)
cd "$REPO/backend" && "$VENV" -m scripts.accumulate_earnings_sentiment >> "$LOG" 2>&1
RC=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] data_updater: fin (acumulacion rc=$RC)" >> "$LOG"
exit 0
