#!/bin/bash
# Respaldo diario al disco externo de todo lo VALIOSO que git NO versiona.
#
# Por qué existe: el código viaja a GitHub, pero `.gitignore` excluye datos que
# sólo existen en esta Mac y que no se regeneran gratis:
#   - backend/fortress.db          (base de datos del sistema)
#   - backend/data/*.json          (knowledge_repo, memorias, backtest_results)
#   - *.parquet                    (precios históricos y trades de cada corrida)
#   - data/                        (cache raíz)
# Si el disco de la Mac muere, todo eso se pierde y GitHub no ayuda.
#
# Precedente concreto: el 28/08 se perdió el fixture Excel de la prueba de
# paridad por vivir sólo en ~/Downloads. Este script existe para que ningún
# dato crítico dependa de una sola copia.
#
# NUNCA borra nada: rsync va sin --delete a propósito. Si un archivo se borra
# del origen por accidente, el respaldo lo conserva.
#
# Corre via launchd (com.fortresscore.backupdatos.plist), diario 23:00.
set -u

LOG="$HOME/Desktop/fortress_core/scripts/backup_datos.log"
DEST="/Volumes/EMPRESA/FortressCore_Fuentes"
REPO="$HOME/Desktop/fortress_core"
KILO="$HOME/orca/workspaces/fortress_core/test-kilo-orca"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] backup_datos: inicio" >> "$LOG"

# El disco externo puede no estar conectado: no es un error, se salta y listo.
if [ ! -d "$DEST" ]; then
  echo "[$(ts)] backup_datos: disco externo NO montado ($DEST) — se omite esta corrida" >> "$LOG"
  exit 0
fi

copiados=0

# --- Repo principal: datos no versionados ---
if [ -d "$REPO" ]; then
  mkdir -p "$DEST/datos_no_versionados"
  cd "$REPO" || exit 0
  for item in backend/fortress.db backend/data/ data/; do
    [ -e "$item" ] || continue
    if rsync -a --relative "$item" "$DEST/datos_no_versionados/" 2>>"$LOG"; then
      copiados=$((copiados + 1))
    else
      echo "[$(ts)] backup_datos: AVISO fallo al copiar $item" >> "$LOG"
    fi
  done
fi

# --- Worktree de investigación: artefactos de corridas largas (horas de cómputo) ---
if [ -d "$KILO/backend/data/cache" ]; then
  mkdir -p "$DEST/artefactos_cientificos"
  rsync -a --include="*/" \
        --include="baseline_clean_*" --include="screening_palas_*" \
        --include="*.parquet" --exclude="*" \
        "$KILO/backend/data/cache/" "$DEST/artefactos_cientificos/" 2>>"$LOG" \
    && copiados=$((copiados + 1))
fi

total=$(du -sh "$DEST" 2>/dev/null | awk '{print $1}')
echo "[$(ts)] backup_datos: fin ($copiados grupos copiados, respaldo total: ${total:-?})" >> "$LOG"
