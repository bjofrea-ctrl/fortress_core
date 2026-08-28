#!/bin/bash
# Chequeo de salud de disco -- detecta temprano si algun agente (Cline,
# Kilo, OpenCode, Claude Code) esta acumulando datos sin limpiar, ANTES
# de que el disco se quede sin espacio (lo que paso el 2026-08-27/28 con
# ~/.cline/data/db/hub-events-hub-production.db, 95GB de log interno de
# Cline nunca podado -- eso tiro abajo una corrida de Kilo a mitad de
# noche). Este script NUNCA borra nada solo -- solo avisa en el log.
#
# Corre via launchd (com.fortresscore.diskhealth.plist), cada 4 horas.
set -u
LOG="$HOME/Desktop/fortress_core/scripts/disk_health.log"

# Umbrales -- Cline/Kilo/OpenCode/Claude normalmente pesan cientos de MB,
# no GB. 5GB es generoso pero atrapa el problema mucho antes de llegar a
# los 95GB que rompieron todo la ultima vez.
UMBRAL_AGENTE_GB=5
UMBRAL_DISCO_LIBRE_GB=15

echo "[$(date '+%Y-%m-%d %H:%M:%S')] disk_health: inicio" >> "$LOG"

avisos=0

# --- Espacio libre general ---
libre_kb=$(df -k / | tail -1 | awk '{print $4}')
libre_gb=$((libre_kb / 1024 / 1024))
if [ "$libre_gb" -lt "$UMBRAL_DISCO_LIBRE_GB" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] disk_health: AVISO disco libre bajo: ${libre_gb}GB (umbral ${UMBRAL_DISCO_LIBRE_GB}GB)" >> "$LOG"
  avisos=$((avisos + 1))
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] disk_health: disco libre OK (${libre_gb}GB)" >> "$LOG"
fi

# --- Tamano de las carpetas de datos de cada agente ---
for dir in ".cline" ".kilo" ".opencode" ".claude"; do
  ruta="$HOME/$dir"
  [ -d "$ruta" ] || continue
  tam_kb=$(du -sk "$ruta" 2>/dev/null | awk '{print $1}')
  tam_gb=$((tam_kb / 1024 / 1024))
  if [ "$tam_gb" -ge "$UMBRAL_AGENTE_GB" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] disk_health: AVISO ~/$dir pesa ${tam_gb}GB (umbral ${UMBRAL_AGENTE_GB}GB) -- revisar $dir/data/db/*.db o equivalente" >> "$LOG"
    avisos=$((avisos + 1))
  fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] disk_health: fin ($avisos avisos)" >> "$LOG"
