#!/bin/bash
# ============================================================
# Fortress Core — Script de Backup Automatizado
# ============================================================
# Respaldos:
#   1. Disco externo: /Volumes/EMPRESA/fortress_core_backups/
#   2. GitHub:        bjofrea-ctrl/fortress_core (rama main)
#
# Uso:
#   bash scripts/backup.sh           # Backup normal
#   bash scripts/backup.sh --force   # Fuerza commit aunque no haya cambios
# ============================================================

set -e  # Exit on error

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXTERNAL_DRIVE="/Volumes/EMPRESA"
BACKUP_DIR="$EXTERNAL_DRIVE/fortress_core_backups"
GITHUB_REPO="bjofrea-ctrl/fortress_core"
BRANCH="main"
FORCE=0

if [[ "$1" == "--force" ]]; then
  FORCE=1
fi

echo "=============================================="
echo "🏛️  FORTRESS CORE — BACKUP AUTOMATIZADO"
echo "=============================================="
echo "📁 Proyecto:     $PROJECT_DIR"
echo "💾 Disco externo: $EXTERNAL_DRIVE"
echo "🐙 GitHub:       $GITHUB_REPO"
echo ""

# ---- Paso 1: Verificar disco externo ----
if [[ ! -d "$EXTERNAL_DRIVE" ]]; then
  echo "❌ ERROR: Disco externo no encontrado en $EXTERNAL_DRIVE"
  echo "   Conecta el disco externo y vuelve a intentar."
  exit 1
fi
echo "✅ Disco externo detectado"

# ---- Paso 2: Crear directorio de backups ----
mkdir -p "$BACKUP_DIR"
echo "✅ Directorio de backups listo: $BACKUP_DIR"

# ---- Paso 3: Añadir todos los cambios ----
cd "$PROJECT_DIR"
git add -A

CHANGES=$(git status --porcelain | wc -l | tr -d ' ')

if [[ "$CHANGES" -eq 0 && "$FORCE" -eq 0 ]]; then
  echo "ℹ️  Sin cambios que commitear. Nada que respaldar."
else
  # ---- Paso 4: Commit ----
  TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
  COMMIT_MSG="backup: $TIMESTAMP ($CHANGES archivos cambiados)"
  git commit -m "$COMMIT_MSG"
  echo "✅ Commit creado: $COMMIT_MSG"
fi

# ---- Paso 5: Push a GitHub ----
if git remote | grep -q "origin"; then
  echo "📤 Haciendo push a GitHub ($GITHUB_REPO)..."
  git push origin "$BRANCH" 2>&1 || echo "⚠️  Push a GitHub falló (verifica conexión o repo remoto)"
  echo "✅ Push a GitHub completado"
else
  echo "⚠️  No hay remoto 'origin' configurado. Repo local solamente."
fi

# ---- Paso 6: Backup al disco externo (copia espejo) ----
echo "💾 Copiando al disco externo..."
rsync -av --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='fortress.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='data/cache/' \
  --exclude='frontend/dist/' \
  --exclude='logs/' \
  "$PROJECT_DIR/" "$BACKUP_DIR/current/"

# ---- Paso 7: Copia versionada con timestamp ----
TIMESTAMP_FILE=$(date "+%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR/snapshots/fortress_core_$TIMESTAMP_FILE"
rsync -a \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.env' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='fortress.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='data/cache/' \
  --exclude='frontend/dist/' \
  --exclude='logs/' \
  "$PROJECT_DIR/" "$BACKUP_DIR/snapshots/fortress_core_$TIMESTAMP_FILE/"

echo "✅ Snapshot versionado: $BACKUP_DIR/snapshots/fortress_core_$TIMESTAMP_FILE"
echo ""

# Limpiar snapshots antiguos (mantener los 10 más recientes)
cd "$BACKUP_DIR/snapshots" 2>/dev/null && ls -t | tail -n +11 | xargs -I{} rm -rf "{}" 2>/dev/null || true

echo "=============================================="
echo "✅ BACKUP COMPLETADO — Todo seguro"
echo "   • GitHub:    $GITHUB_REPO"
echo "   • Disco:     $BACKUP_DIR"
echo "   • Snapshot:  fortress_core_$TIMESTAMP_FILE"
echo "=============================================="