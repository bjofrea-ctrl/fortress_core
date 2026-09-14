# PROTOCOLO DE COORDINACIÓN ENTRE AGENTES — fortress_core

Fecha: 2026-09-14 · Autor: Kilo (orquestador) · Origen: incidentes reales
(Cline y OpenCode percibieron pisadas mutuas el 2026-09-13/14).

## Reglas (vinculantes para Kilo, Cline, OpenCode, Claude Code)

**R1 — Un agente, un worktree.** Cada agente trabaja SOLO en su worktree
asignado. Prohibido `git -C` al worktree ajeno, editar sus archivos, cambiar
sus ramas o crearle stashes/branches. Lectura cruzada: solo vía `origin/*`
después de `fetch` (el código del otro se lee pusheado, nunca en su disco).
*Incidente que la motiva: Kilo creó ramas y stashes dentro de los worktrees
de Cline y OpenCode mientras sus sesiones estaban activas.*

**R2 — Prohibido `git stash` en este repo.** El stack de stash es GLOBAL
del repo compartido (no por worktree): un `pop` agarra lo que esté arriba,
sea de quien sea. WIP sin terminar → commit WIP en rama propia, nunca stash.
*Incidente: 5 stashes mezclados de 3 agentes + Kilo en una sola pila.*

**R3 — Push solo de ramas propias; ramas backup/data, NUNCA a origin.**
Los backups de datos y artefactos van al espejo EMPRESA, no a GitHub
(repositorio público). *Incidente: rama auto-backup-safety-net con 31k líneas
(incluye `.CONTAMINATED` y snapshots) pusheada a origin — pendiente decisión
de Boris: conservar como red de seguridad o borrar.*

**R4 — ORCHESTRATOR_INBOX.md: escriben solo el watcher (automático) y Kilo
(manual).** Los agentes anuncian entregas commiteando en su rama; el watcher
las publica. Nadie edita a mano las líneas de otro.

**R5 — Suites completas: solo Kilo-verificación, escalonadas.** Los agentes
corren tests focalizados durante el desarrollo (la RAM/CPU y el venv son
compartidos; el patrón de crash por RAM viene de suites paralelas).

**R6 — Ramas con prefijo del dueño para experimentos** (`cline/...`,
`opencode/...`, `tmp-...`, `verify/...`): el watcher reporta toda rama nueva
y los nombres genéricos confunden la atribución.

## Monitor (agent_watcher.sh v2, launchd com.fortresscore.agentwatcher)

- Detecta: commits en HEAD (ENTREGA→inbox), commits en otras ramas (log),
  ramas nuevas (inbox, una vez), actividad WIP (dirty+mtimes).
- Señal de fin: quietud >15min tras actividad → `POSIBLE FIN` en inbox +
  snapshot de archivos sin commitear en `scripts/agent_wip_<agente>.txt`.
- Heartbeat: `/tmp/agent_watcher_heartbeat` (epoch por ciclo; staleness =
  watcher muerto). Estado: `/tmp/agent_watcher_state`.
