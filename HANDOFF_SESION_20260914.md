# HANDOFF — estado y pendientes al 2026-09-14 ~19:00 ART

> Para quien retome (humano o agente) sin conocer el proyecto: este documento
> es la fuente de verdad del estado. Leerlo entero antes de tocar nada.
> Repo real: `/Users/boris/Desktop/fortress_core` (rama `main`, remoto
> `origin` = `bjofrea-ctrl/fortress_core` en GitHub, público).
> Worktrees de agentes en `/Users/boris/orca/workspaces/fortress_core/`:
> `test-kilo-orca` (Kilo), `test-opencode-orca` (OpenCode),
> `fundamentales-automatizado` (Cline). Todos comparten UN repo git.

## 0. Cómo leer este proyecto en 5 minutos

- `AGENTS.md` (raíz): reglas del repo. `ONBOARDING.md`: guía completa.
  `ROADMAP.md`: tabla de trabajos con estado. `SESSION_LOG.md`: bitácora.
- `ORCHESTRATOR_INBOX.md`: cola de coordinación entre agentes (el watcher
  agrega líneas solo; Kilo escribe a mano).
- `PRE_REGISTRO_*.md`: pre-registros obligatorios ANTES de código con
  criterio de aceptación (regla dura del repo para trials y veredictos).
- Backend en `backend/` (venv en `backend/.venv`, Python 3.9.6). Tests:
  `cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/ -q`
  (suite completa ~40 min; excluye `tests/test_a6_n_trials_ledger.py`,
  huérfano con import roto de otro frente).
- Frontend en `frontend/` (`npx tsc --noEmit` para tipos).
- Producción local: daemon API (launchd `com.fortresscore.api`, puerto 8000,
  health REAL en `GET /health` — ojo: `/api/advisor/health` cae en el
  catch-all `/{symbol}` y bloquea; no es bug, es routing).
- Espejo de seguridad: `/Volumes/EMPRESA/git-backups/fortress_core.git`
  (actualizar tras cada push a main con
  `git bundle create /tmp/x.bundle main --not <old> && git -C <espejo> fetch
  /tmp/x.bundle 'refs/heads/*:refs/heads/*'`).
- Premisa vigente de Boris (guardada en memoria del proyecto): ante
  alternativas, proponer SIEMPRE lo más sólido a largo plazo, nunca lo más
  fácil; explicar trade-offs sin jerga (Boris es médico, neófito en sintaxis).

## 1. Estado git exacto (verificado 19:00)

- `main` @ `a5893fe`, pusheado a `origin/main`, espejo EMPRESA sincronizado.
- Rama `bjofrea-ctrl/test-kilo-orca` @ `91b367c`: contiene fix-forward warmup
  (loop anclado a vencimiento + piso 60s + `cache_date` lowercase) y SWR
  (`is_stale` en /universe). **NO mergeada a main** (orden vigente: OpenCode
  verifica independiente antes de cualquier merge; OpenCode no lo hizo).
- Rama `fix/warmup-criterio2-20260911` en origin: mismo fix-forward (para
  referencia; la rama de trabajo real es test-kilo-orca).
- Rama `origin/auto-backup-safety-net`: 31k líneas de datos/artefactos
  (incluye `.CONTAMINATED`) en repo PÚBLICO. **Pendiente decisión Boris:
  respaldar a EMPRESA + borrar rama remota + redirigir auto-backup.**
- Worktree test-kilo-orca limpio (solo untracked ajenos: STOP_FILE,
  test_a6 huérfano, artefactos cache — NO commitear, no son de Kilo).
- Main worktree tiene sin commitear (NO tocar sin orden): `M
  ORCHESTRATOR_INBOX.md` (líneas del watcher), `M
  backend/data/rag_memory.json` (churn de runtime), untracked
  (parquets .bak, earnings txts, PRE_REG_UX doc).

## 2. Incidente ABIERTO y CRÍTICO: cache de precios contaminado

**Evidencia** (verificada contra 3 fuentes: yfinance en vivo ×2, espejo Sep-2,
SESSION_LOG $771.33): 28 grupos / 66 tickers con colas idénticas al centavo
(ej. SPY=AAPL=TSLA=510.37 vs 764.29/332.27/365.44 en vivo; volúmenes 13x);
ACN/PEP comparten 414 filas (divergen 2025-01-16 → contaminación VIEJA para
algunos grupos); vs espejo Sep-2 difiere el 100% de filas comunes; VIX cache
96 vs 18.02 live; 108 parquets reescritos 08:23-08:32 en tandas de 6-9/min.
**Nada que lea `backend/data/cache/*.parquet` es confiable** (motor,
backtests, HMM, screens). Gauges externos (futuros, VIX live, AAII, titulares)
SÍ son confiables.
**Pista principal**: valores compartidos EXISTEN en historias reales de otros
tickers del espejo → misasignación por lote/columna en el path de descarga o
merge, NO fixture sintético. Escritor exacto sin identificar (descartados con
evidencia: hook de integridad solo memoiza, tests usan tmp_path, updater
nocturno corre 22:00, ningún proceso Python de datos vivo al inspeccionar).
**Mitigación aplicada**: merge fix-forward (d19d7e4) + restart daemon
(PID 39745); `/health` 200 en 0.09s durante rebuild.
**Riesgo activo**: daemon en auto-reintento cada ~6-11 min, ciclos fallando
"Datos insuficientes: 0 días" por throttling Yahoo (21.5k errores en log;
probe de 1 ticker OK = por ráfagas, no caída). **Pausa de descargas masivas
vigente para TODOS los agentes** (inbox 11:20) — levantarla solo cuando el
throttle afloje.
**Recuperación pendiente** (en este orden): (1) que afloje el throttle;
(2) verificar espejo Sep-2 por muestreo (tiene 2 pares dudosos: COST/CRM,
TMO); (3) restaurar + re-descarga limpia completa y verificada ticker por
ticker; (4) activar `detect_cross_contamination` (ya existe en
`backend/app/core/cache_integrity.py`) como gate del updater: si detecta
duplicados, no escribe y alerta.

## 3. Tareas pendientes por dueño

- **Kilo (orquestador, no implementa salvo rescate)**: (a) vigilar recuperación
  del daemon (si sigue fallando a la tarde, proponer cooldown con daemon
  detenido — requiere orden, es downtime); (b) verificar entregas vía inbox +
  watcher; (c) suite completa ya verde en main post-merge (1055 passed, 0
  failed, 41 min, log en /tmp/suite_main_postmerge.log — ese /tmp expira,
  el resultado quedó en SESSION_LOG).
- **OpenCode** (análisis estrategia; ticket vigente
  `TASK_KILO_A_OPENCODE_FASE3_20260913.md` + orden 21:28): implementar Fase 3
  (AssetFavourability TASK-009/010, Gate 3 >0.5% anualizado) con pre-registro
  ANTES de código; rama nueva desde main; entregas sin merge. Estado:
  código F3/F4 escrito sin commitear (282+542+236 líneas), suite propia
  colgada 48 min con 1 FAIL (Kilo la terminó al inspeccionar — re-correr con
  diagnóstico). Sin pre-registro F3 todavía.
- **Cline** (dashboard/front/back; ticket `TASK_KILO_A_CLINE_20260912.md`):
  G1 mergeado, G2 parcial (solo RiskPanel mergeado 2ff1997), resto G2
  (widget TV, muertos, solapamientos) + propuesta G3 pendientes. Quieto 3h+.
  Su auto-backup pusheó datos a origin (ver decisión pendiente arriba).
- **Claude Code**: SIN CRÉDITOS — no delegarle nada (Kilo único verificador).

## 4. Monitor y coordinación (operativos)

- `agent_watcher.sh` v2 corriendo (launchd `com.fortresscore.agentwatcher`):
  heartbeat `/tmp/agent_watcher_heartbeat`, estado
  `/tmp/agent_watcher_state`, entregas/ramas/quietud>15min→`POSIBLE FIN` en
  inbox + snapshot `scripts/agent_wip_<agente>.txt`. OJO: `/tmp` NO sobrevive
  reboot — el script re-inicializa baseline en silencio al arrancar.
- `PROTOCOLO_COORDINACION_AGENTES.md`: R1 worktrees exclusivos, R2 prohibido
  `git stash` (stack compartido del repo), R3 push solo ramas propias, R4
  inbox solo watcher+Kilo, R5 suites completas solo Kilo escalonadas, R6 ramas
  con prefijo. Stashes kilo eliminados tras verificar absorción.
- Reglas duras vigentes: ningún merge a main sin aviso de Boris; ningún trial
  sin pre-registro; falsación (tests nuevos deben fallar con código viejo);
  ruff limpio en archivos tocados; suite completa tras merges.

## 5. Comandos de verificación rápida (copiar/pegar)

```bash
cd /Users/boris/Desktop/fortress_core
git log --oneline -3 && git status -sb | head -5   # estado main
curl -s --max-time 20 http://127.0.0.1:8000/health  # 200 en ~0.1s esperado
tail -2 backend/../scripts/api_server.log 2>/dev/null || tail -2 scripts/api_server.log | cut -c1-160  # último ciclo warmup
cat /tmp/agent_watcher_heartbeat  # epoch reciente = watcher vivo
PYTHONPATH=. .venv/bin/python -m pytest tests/test_advisor_warmup.py tests/test_advisor_api.py -q  # 29 tests, ~30s (desde backend/)
```
