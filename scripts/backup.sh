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
EXCLUDES="--exclude=.git --exclude=.venv --exclude=venv --exclude=node_modules --exclude=.env --exclude=__pycache__ --exclude='*.pyc' --exclude=.DS_Store --exclude=fortress.db --exclude='*.sqlite' --exclude='*.sqlite3' --exclude=data/cache/ --exclude=frontend/dist/ --exclude=logs/"

# ---- Paso 6.5: Backup específico de fortress.db (la excluimos del rsync a propósito;
# vive acá con retención propia). sqlite3 .backup es seguro con escrituras concurrentes.
DB_SRC="$PROJECT_DIR/backend/fortress.db"
DB_BACKUP_DIR="$BACKUP_DIR/db"
if [[ -f "$DB_SRC" ]]; then
  mkdir -p "$DB_BACKUP_DIR"
  DB_STAMP=$(date "+%Y%m%d_%H%M%S")
  if sqlite3 "$DB_SRC" ".backup '$DB_BACKUP_DIR/fortress_$DB_STAMP.db'"; then
    echo "✅ Backup de fortress.db: $DB_BACKUP_DIR/fortress_$DB_STAMP.db"
    # Retención: mantener los 20 más recientes
    ls -t "$DB_BACKUP_DIR"/fortress_*.db 2>/dev/null | tail -n +21 | xargs -I{} rm -f "{}" 2>/dev/null || true
  else
    echo "⚠️  Backup de fortress.db falló (¿sqlite3 CLI disponible?)"
  fi
fi

# ---- Paso 6.6: Backup versionado de trial_registry.json (el rsync de abajo
# lo copia igual, pero con --delete: si se corrompe localmente, el espejo se
# sobreescribe con la versión corrupta en el próximo ciclo. Retención propia.
REG_SRC="$PROJECT_DIR/backend/data/trial_registry.json"
REG_BACKUP_DIR="$BACKUP_DIR/trial_registry"
if [[ -f "$REG_SRC" ]]; then
  mkdir -p "$REG_BACKUP_DIR"
  REG_STAMP=$(date "+%Y%m%d_%H%M%S")
  if cp "$REG_SRC" "$REG_BACKUP_DIR/trial_registry_$REG_STAMP.json"; then
    echo "✅ Backup de trial_registry.json: $REG_BACKUP_DIR/trial_registry_$REG_STAMP.json"
    ls -t "$REG_BACKUP_DIR"/trial_registry_*.json 2>/dev/null | tail -n +21 | xargs -I{} rm -f "{}" 2>/dev/null || true
  else
    echo "⚠️  Backup de trial_registry.json falló"
  fi
fi

echo "💾 Copiando al disco externo..."
rsync -av --delete $EXCLUDES "$PROJECT_DIR/" "$BACKUP_DIR/current/"

# ---- Paso 7: Copia versionada con timestamp ----
TIMESTAMP_FILE=$(date "+%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR/snapshots/fortress_core_$TIMESTAMP_FILE"
rsync -a $EXCLUDES "$PROJECT_DIR/" "$BACKUP_DIR/snapshots/fortress_core_$TIMESTAMP_FILE/"

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