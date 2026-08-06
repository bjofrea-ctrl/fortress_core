#!/bin/bash
# =============================================
# FORTRESS CORE — AUTO-BACKUP AUTOMATIZADO
# =============================================
# Ejecuta commit + push a GitHub cada 10 minutos
# para no perder trabajo por cortes de energía,
# internet, créditos, o cualquier problema.
# =============================================

PROJECT_DIR="/Users/boris/Desktop/fortress_core"
LOG_FILE="$PROJECT_DIR/scripts/auto_backup.log"
LOCK_FILE="/tmp/fortress_auto_backup.lock"

# Evitar ejecución concurrente
if [ -f "$LOCK_FILE" ]; then
    exit 0
fi
touch "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

cd "$PROJECT_DIR" || exit 1

# Verificar si hay cambios
CHANGES=$(git status --porcelain)
if [ -z "$CHANGES" ]; then
    # Sin cambios, solo verificar si hay commits locales sin pushear
    UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
    if [ "$UNPUSHED" -gt 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pushando $UNPUSHED commits pendientes..." >> "$LOG_FILE"
        git push origin main >> "$LOG_FILE" 2>&1
    fi
    exit 0
fi

# Hay cambios — hacer commit y push
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
COMMIT_MSG="auto-backup: $TIMESTAMP"

echo "[$TIMESTAMP] Detectados cambios, respaldando..." >> "$LOG_FILE"
git add -A >> "$LOG_FILE" 2>&1
git commit -m "$COMMIT_MSG" >> "$LOG_FILE" 2>&1

# Push a GitHub
if git push origin main >> "$LOG_FILE" 2>&1; then
    echo "[$TIMESTAMP] OK Push a GitHub exitoso" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] WARN Push falló (sin internet?) - commit local guardado" >> "$LOG_FILE"
fi

# Backup al disco externo si está montado
if [ -d "/Volumes/EMPRESA" ]; then
    BACKUP_DIR="/Volumes/EMPRESA/fortress_core_backups/current"
    mkdir -p "$BACKUP_DIR"
    rsync -a --delete \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='venv' \
        --exclude='node_modules' \
        --exclude='.env' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.db' \
        --exclude='*.sqlite' \
        --exclude='data/cache' \
        "$PROJECT_DIR/" "$BACKUP_DIR/" >> "$LOG_FILE" 2>&1
    echo "[$TIMESTAMP] OK Backup a disco externo completado" >> "$LOG_FILE"
fi

# Mantener log acotado (últimas 200 líneas)
tail -200 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"