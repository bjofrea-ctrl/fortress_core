#!/bin/bash
# ============================================================
# FORTRESS CORE — RECUPERADOR DE SESIÓN Kilo
# ============================================================
# Abre la ÚLTIMA sesión de Kilo del proyecto fortress_core en
# modo terminal (TUI). Funciona aunque el nombre o versión de
# la extensión cambie.
#
# Uso:
#   ./scripts/recuperar_ultima_sesion.sh            → última sesión
#   ./scripts/recuperar_ultima_sesion.sh --listar   → ver todas
#   ./scripts/recuperar_ultima_sesion.sh --nueva    → sesión nueva
# ============================================================

REPO="/Users/boris/Desktop/fortress_core"
DB="$HOME/.local/share/kilo/kilo.db"

# --- 1. Resolver binario kilo (symlink estable, si no glob) ---
KILO="$HOME/.local/bin/kilo"
if [ ! -x "$KILO" ]; then
  KILO=$(ls -t "$HOME"/.vscode/extensions/kilocode.kilo-code-*-darwin-*/bin/kilo 2>/dev/null | head -1)
  if [ -n "$KILO" ]; then
    ln -sf "$KILO" "$HOME/.local/bin/kilo"
  fi
fi
if [ ! -x "$KILO" ]; then
  echo "ERROR: no se encontró el binario de Kilo Code (extensión VS Code)."
  read -n 1 -s -r -p "Enter para cerrar..."
  exit 1
fi

cd "$REPO" || exit 1

# --- 2. Descubrir sesiones ---
if [ "$1" = "--listar" ]; then
  echo "Sesiones Kilo de fortress_core:"
  sqlite3 -header -column "$DB" \
    "SELECT id AS sesion, title AS titulo,
            datetime(time_updated/1000,'unixepoch','localtime') AS actualizada
     FROM session WHERE directory='$REPO'
     ORDER BY time_updated DESC LIMIT 20;"
  echo ""
  read -n 1 -s -r -p "Enter para cerrar..."
  exit 0
fi

if [ "$1" = "--nueva" ]; then
  exec "$KILO" .
fi

LAST=$(sqlite3 "$DB" \
  "SELECT id FROM session WHERE directory='$REPO' ORDER BY time_updated DESC LIMIT 1;")

if [ -z "$LAST" ]; then
  echo "No hay sesiones previas de fortress_core. Abriendo sesión nueva..."
  exec "$KILO" .
fi

TITLE=$(sqlite3 "$DB" "SELECT title FROM session WHERE id='$LAST';")
DATE=$(sqlite3 "$DB" "SELECT datetime(time_updated/1000,'unixepoch','localtime') FROM session WHERE id='$LAST';")

echo "Recuperando última sesión de fortress_core:"
echo "  Título: $TITLE"
echo "  Última actividad: $DATE"
echo "  ID: $LAST"
echo ""
exec "$KILO" -s "$LAST"
