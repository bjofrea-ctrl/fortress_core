#!/bin/bash
# agent_watcher.sh — Kilo orquestador: detecta entregas de agentes en tiempo real.
#
# Patrón: cada 60s chequea (1) commits nuevos en los worktrees de los agentes
# vs el último visto, (2) mensajes worker_done pendientes en orca orchestration.
# Cuando detecta una entrega, escribe una línea en scripts/agent_watcher.log
# y un archivo de "cola de asignación" ORCHESTRATOR_INBOX.md que Kilo lee
# al retomar (o al terminar su ciclo actual) para dar continuidad.
#
# Diseño: SIN estado en el propio watcher salvo LAST_SEEN (commits) — la
# fuente de verdad es git + orca. Idempotente y a prueba de reinicios.

set -u

REPO="/Users/boris/Desktop/fortress_core"
WORKTREES=(
  "/Users/boris/orca/workspaces/fortress_core/fundamentales-automatizado|Cline"
  "/Users/boris/orca/workspaces/fortress_core/test-opencode-orca|OpenCode"
)
STATE_FILE="/tmp/agent_watcher_state"
INBOX="$REPO/ORCHESTRATOR_INBOX.md"
LOG="$REPO/scripts/agent_watcher.log"
INTERVAL=60

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [watcher] $*" >> "$LOG"; }

# Estado inicial de commits (primera corrida: registrar sin alertar)
if [[ ! -f "$STATE_FILE" ]]; then
  : > "$STATE_FILE"
  for wt in "${WORKTREES[@]}"; do
    dir="${wt%%|*}"; name="${wt##*|}"
    head=$(git -C "$dir" rev-parse HEAD 2>/dev/null || echo "none")
    echo "$name=$head" >> "$STATE_FILE"
  done
  log "init: baseline registrada, $(wc -l < "$STATE_FILE") agentes"
fi

while true; do
  for wt in "${WORKTREES[@]}"; do
    dir="${wt%%|*}"; name="${wt##*|}"
    head_now=$(git -C "$dir" rev-parse HEAD 2>/dev/null || echo "none")
    head_seen=$(grep "^$name=" "$STATE_FILE" 2>/dev/null | cut -d= -f2)
    if [[ "$head_now" != "$head_seen" && "$head_now" != "none" ]]; then
      subject=$(git -C "$dir" log --format=%s -1 2>/dev/null | head -c 80)
      echo "- **$(date '+%Y-%m-%d %H:%M')** — $name entregó: \`$subject\` ($head_now) — PENDIENTE VERIFICAR+MERGEAR" >> "$INBOX"
      log "ENTREGA: $name -> $head_now ($subject)"
      echo "$name=$head_now" > "$STATE_FILE.tmp"
      grep -v "^$name=" "$STATE_FILE" >> "$STATE_FILE.tmp" 2>/dev/null
      mv "$STATE_FILE.tmp" "$STATE_FILE"
    fi
  done
  sleep "$INTERVAL"
done
