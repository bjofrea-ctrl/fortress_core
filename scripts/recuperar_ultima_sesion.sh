#!/bin/bash
# FORTRESS CORE — Recuperador de sesión Kilo
# Uso:
#   ./scripts/recuperar_ultima_sesion.sh          → abre TUI retomando la última sesión
#   ./scripts/recuperar_ultima_sesion.sh --listar → lista sesiones disponibles
#   ./scripts/recuperar_ultima_sesion.sh --nueva  → abre TUI sin retomar
REPO="/Users/boris/Desktop/fortress_core"
DB="$HOME/.local/share/kilo/kilo.db"

# Resolver binario kilo (puede cambiar de versión cuando se actualiza la extensión)
KILO="$HOME/.local/bin/kilo"
if [ ! -x "$KILO" ]; then
  KILO=$(ls -t "$HOME"/.vscode/extensions/kilocode.kilo-code-*-darwin-*/bin/kilo 2>/dev/null | head -1)
  [ -n "$KILO" ] && ln -sf "$KILO" "$HOME/.local/bin/kilo"
fi
if [ ! -x "$KILO" ]; then
  echo "No se encontró la extensión Kilo Code. Abrí VS Code una vez para repararla y volvé a intentar."
  read -n 1 -s -r -p "Enter para cerrar..."
  exit 1
fi

cd "$REPO" || exit 1

if [ "$1" = "--listar" ]; then
  echo "Sesiones Kilo — fortress_core:"
  sqlite3 -header -column "$DB" \
    "SELECT id AS sesion, title AS titulo, datetime(time_updated/1000,'unixepoch','localtime') AS actualizada FROM session WHERE directory='$REPO' ORDER BY time_updated DESC LIMIT 15;"
  exit 0
fi

if [ "$1" = "--nueva" ]; then
  exec "$KILO" "$REPO"
fi

LAST=$(sqlite3 "$DB" "SELECT id FROM session WHERE directory='$REPO' ORDER BY time_updated DESC LIMIT 1;")
if [ -z "$LAST" ]; then
  echo "No hay sesiones previas. Abriendo sesión nueva..."
  exec "$KILO" "$REPO"
fi
echo "Retomando última sesión: $LAST"
exec "$KILO" "$REPO" -s "$LAST"
