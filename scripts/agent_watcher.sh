#!/bin/bash
# agent_watcher.sh — Kilo orquestador: detecta entregas Y estado de agentes.
#
# v2 (2026-09-14): el v1 solo veía HEAD de la rama checkouteada → ciego a
# commits en otras ramas (auto-backup), a WIP sin commitear (RiskPanel 9h
# invisible) y sin señal de "terminó". Este v2 agrega, sin quitar nada:
#  (1) tracking GLOBAL de ramas (los 3 worktrees comparten UN repo: el
#      listado es idéntico; se trackea una vez, sin atribución por agente),
#  (2) actividad WIP por worktree (conteo dirty + mtime más reciente),
#  (3) heartbeat por ciclo (staleness del heartbeat = watcher muerto),
#  (4) transición a quietud → línea POSIBLE FIN en inbox + snapshot de WIP
#      (continuidad: qué quedó sin commitear al terminar),
#  (5) ramas nuevas → aviso UNA vez (seed silencioso en init, sin inundar).
#
# Diseño: SIN estado salvo el STATE_FILE (clave=valor) — fuente de verdad
# git + filesystem. Idempotente y a prueba de reinicios. Ciclo 60s.
# Inbox = solo eventos (ENTREGA / POSIBLE FIN / RAMA NUEVA); el resto al log.

set -u

REPO="/Users/boris/Desktop/fortress_core"
WORKTREES=(
  "/Users/boris/orca/workspaces/fortress_core/fundamentales-automatizado|Cline"
  "/Users/boris/orca/workspaces/fortress_core/test-opencode-orca|OpenCode"
)
STATE_FILE="/tmp/agent_watcher_state"
HEARTBEAT_FILE="/tmp/agent_watcher_heartbeat"
INBOX="$REPO/ORCHESTRATOR_INBOX.md"
LOG="$REPO/scripts/agent_watcher.log"
INTERVAL=60
QUIET_MINUTES=15
# Permitir override en tests/dry-run sin editar el archivo.
STATE_FILE="${AGENT_WATCHER_STATE:-$STATE_FILE}"
HEARTBEAT_FILE="${AGENT_WATCHER_HEARTBEAT:-$HEARTBEAT_FILE}"
INBOX="${AGENT_WATCHER_INBOX:-$INBOX}"
LOG="${AGENT_WATCHER_LOG:-$LOG}"

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [watcher] $*" >> "$LOG"; }
now_epoch() { date +%s; }

get_state() { # $1=clave → valor o ""
  grep "^$1=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- | tail -1
}
set_state() { # $1=clave $2=valor (reescritura atómica)
  local key="$1" val="$2" tmp="$STATE_FILE.tmp.$$"
  grep -v "^$key=" "$STATE_FILE" 2>/dev/null > "$tmp" || true
  echo "$key=$val" >> "$tmp"
  mv "$tmp" "$STATE_FILE"
}

# mtime más reciente (epoch) de archivos del worktree, excluyendo ruido.
newest_mtime() { # $1=dir
  find "$1" -type f \
    -not -path "*/.git/*" \
    -not -path "*/node_modules/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/backend/data/cache/*" \
    -not -path "*/.pytest_cache/*" \
    -not -path "*/.venv/*" \
    -printf "%T@\n" 2>/dev/null | sort -n | tail -1 | cut -d. -f1
}

# Huella del conjunto de ramas locales (repo compartido: una sola vez).
branches_fingerprint() {
  git -C "$REPO" for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads/ 2>/dev/null | sort | md5 | cut -d' ' -f1
}

if [[ ! -f "$STATE_FILE" ]]; then
  : > "$STATE_FILE"
  for wt in "${WORKTREES[@]}"; do
    dir="${wt%%|*}"; name="${wt##*|}"
    head=$(git -C "$dir" rev-parse HEAD 2>/dev/null || echo "none")
    echo "$name=$head" >> "$STATE_FILE"
  done
  echo "branches=$(branches_fingerprint)" >> "$STATE_FILE"
  log "init: baseline registrada (HEADs + ramas, sin alertar)"
fi

while true; do
  echo "$(now_epoch)" > "$HEARTBEAT_FILE"
  now=$(now_epoch)

  # --- 0. Ramas del repo compartido: detectar ramas nuevas o movidas ---
  # Migración v1→v2: si el state predataba el tracking de ramas (sin clave
  # `branches`), sembrar TODO en silencio una vez — si no, cada rama
  # preexistente dispararía una falsa "RAMA NUEVA" (inundación del inbox).
  fp_now=$(branches_fingerprint)
  fp_seen=$(get_state "branches")
  fp_had="$fp_seen"  # vacío solo en primera corrida o migración
  if [[ -z "$fp_seen" ]]; then
    while IFS= read -r line; do
      br="${line%% *}"; sha="${line##* }"
      set_state "branch.$br" "$sha"
    done < <(git -C "$REPO" for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads/ 2>/dev/null | sort)
    set_state "branches" "$fp_now"
    log "migración: baseline de ramas registrada sin alertar"
  fi
  if [[ -n "$fp_had" && -n "$fp_now" && "$fp_now" != "$fp_seen" ]]; then
    while IFS= read -r line; do
      br="${line%% *}"; sha="${line##* }"
      seen=$(get_state "branch.$br")
      if [[ -z "$seen" ]]; then
        subject=$(git -C "$REPO" log --format=%s -1 "$sha" 2>/dev/null | head -c 80)
        echo "- **$(date '+%Y-%m-%d %H:%M')** — RAMA NUEVA en repo compartido: \`$br\` ($sha): \`$subject\`" >> "$INBOX"
        log "RAMA NUEVA: $br -> $sha ($subject)"
      elif [[ "$sha" != "$seen" ]]; then
        subject=$(git -C "$REPO" log --format=%s -1 "$sha" 2>/dev/null | head -c 80)
        log "RAMA: $br -> $sha ($subject)"
      fi
      set_state "branch.$br" "$sha"
    done < <(git -C "$REPO" for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads/ 2>/dev/null | sort)
    set_state "branches" "$fp_now"
  fi

  for wt in "${WORKTREES[@]}"; do
    dir="${wt%%|*}"; name="${wt##*|}"

    # --- 1. HEAD de la rama checkouteada (comportamiento v1 intacto) ---
    head_now=$(git -C "$dir" rev-parse HEAD 2>/dev/null || echo "none")
    branch_now=$(git -C "$dir" branch --show-current 2>/dev/null || echo "?")
    head_seen=$(get_state "$name")
    if [[ "$head_now" != "$head_seen" && "$head_now" != "none" ]]; then
      subject=$(git -C "$dir" log --format=%s -1 2>/dev/null | head -c 80)
      echo "- **$(date '+%Y-%m-%d %H:%M')** — $name entregó [$branch_now]: \`$subject\` ($head_now) — PENDIENTE VERIFICAR+MERGEAR" >> "$INBOX"
      log "ENTREGA: $name [$branch_now] -> $head_now ($subject)"
      set_state "$name" "$head_now"
    fi

    # --- 2. Actividad WIP: archivos dirty + mtime más reciente ---
    dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    mtime=$(newest_mtime "$dir")
    [[ -z "$mtime" ]] && mtime=0
    prev_dirty=$(get_state "$name.dirty"); [[ -z "$prev_dirty" ]] && prev_dirty=0
    prev_mtime=$(get_state "$name.mtime"); [[ -z "$prev_mtime" ]] && prev_mtime=0
    last_active=$(get_state "$name.active"); [[ -z "$last_active" ]] && last_active=0

    if [[ "$dirty" != "$prev_dirty" || "$mtime" != "$prev_mtime" ]]; then
      last_active=$now
      set_state "$name.active" "$now"
    fi
    set_state "$name.dirty" "$dirty"
    set_state "$name.mtime" "$mtime"

    # --- 3. Transición a quietud = POSIBLE FIN (una vez por transición) ---
    quiet_reported=$(get_state "$name.quiet"); [[ -z "$quiet_reported" ]] && quiet_reported=0
    idle_secs=$(( now - last_active ))
    if [[ "$last_active" -gt 0 && "$idle_secs" -ge $(( QUIET_MINUTES * 60 )) && "$quiet_reported" != "$last_active" ]]; then
      idle_min=$(( idle_secs / 60 ))
      wip_list="$REPO/scripts/agent_wip_${name}.txt"
      git -C "$dir" status --porcelain 2>/dev/null | head -30 > "$wip_list"
      echo "- **$(date '+%Y-%m-%d %H:%M')** — POSIBLE FIN: $name quieto ${idle_min}min (HEAD=$head_now [$branch_now], WIP=${dirty} archivos, lista en scripts/agent_wip_${name}.txt) — revisar entrega" >> "$INBOX"
      log "POSIBLE FIN: $name quieto ${idle_min}min, HEAD=$head_now, dirty=$dirty"
      set_state "$name.quiet" "$last_active"
    fi
    if [[ "$idle_secs" -lt $(( QUIET_MINUTES * 60 )) && "$quiet_reported" != "0" ]]; then
      set_state "$name.quiet" "0"
    fi
  done
  sleep "$INTERVAL"
done
