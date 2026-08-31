#!/bin/bash
# Respaldo de las bóvedas de claves cifradas (~/Desktop/BOVEDA-CLAVES-*.md.enc)
# hacia el disco externo /Volumes/EMPRESA. NUNCA descifra nada -- copia el
# blob cifrado tal cual, mismo principio que backup_db() en auto_backup.sh
# (sqlite3 .backup: nunca toca el contenido, solo lo copia de forma segura).
#
# Corre via launchd (com.fortresscore.bovedabackup.plist). Si el disco externo
# no esta montado, no falla -- loggea y sale limpio (se reintenta en el
# proximo ciclo).
set -u
LOG="$HOME/Desktop/fortress_core/scripts/boveda_backup.log"
SRC_DIR="$HOME/Desktop"
DEST_DIR="/Volumes/EMPRESA"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] boveda_backup: inicio" >> "$LOG"

if [ ! -d "$DEST_DIR" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] boveda_backup: /Volumes/EMPRESA no montado, se reintenta despues" >> "$LOG"
  exit 0
fi

copiados=0
sin_cambios=0
for f in "$SRC_DIR"/BOVEDA-CLAVES-*.md.enc; do
  [ -e "$f" ] || continue
  nombre=$(basename "$f")
  dest="$DEST_DIR/$nombre"
  if [ -f "$dest" ] && cmp -s "$f" "$dest"; then
    sin_cambios=$((sin_cambios + 1))
  else
    cp -p "$f" "$dest"
    copiados=$((copiados + 1))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] boveda_backup: $nombre actualizado en disco externo" >> "$LOG"
  fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] boveda_backup: fin ($copiados actualizados, $sin_cambios sin cambios)" >> "$LOG"
