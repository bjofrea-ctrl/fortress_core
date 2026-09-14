# HANDOFF —turno Kilo 2026-09-14 noche (para retomar sin contexto previo)

Fecha: 2026-09-14 ~19:00 ART. Autor estado: Kilo (orquestador). Este documento
permite a cualquiera (otro agente o Boris) retomar cada frente pendiente con
criterios de entrada/salida exactos. Todo lo afirmado acá fue verificado
contra artefactos hoy; donde hay hipótesis sin probar dice HIPÓTESIS.

## 1. Dónde quedó cada cosa (SHAs exactos)

| Qué | Dónde | SHA / estado |
|---|---|---|
| main (repo real) | `/Users/boris/Desktop/fortress_core`, `origin/main` | `a5893fe` pusheado + espejo EMPRESA sync |
| Rama Kilo (SWR sin mergear) | worktree `/Users/boris/orca/workspaces/fortress_core/test-kilo-orca`, rama `bjofrea-ctrl/test-kilo-orca` | `91b367c` (pusheada como `fix/warmup-criterio2-20260911` antes del rebase; el SWR vive SOLO en la rama Kilo, NO en main) |
| Rama fix anterior | `origin/fix/warmup-criterio2-20260911` | `d752464` (histórica; el contenido útil ya está en main vía cherry-pick d19d7e4) |
| Daemon API prod | launchd `com.fortresscore.api`, puerto 8000, código main con fix (reiniciado hoy) | `/health` 200 en ~0.1s verificado |
| Espejo git EMPRESA | `/Volumes/EMPRESA/git-backups/fortress_core.git` | main @ `a5893fe` (sync con bundle+fetch; si el volumen se desmonta, reintentar al remontar) |
| Venv único | `/Users/boris/Desktop/fortress_core/backend/.venv` (py3.9; los worktrees NO tienen venv propio, usan este con `PYTHONPATH=.` y cwd=su `backend/`) | — |

## 2. Frente A — Daemon en fail-loop por throttling Yahoo (ACTIVO, sin resolver)

**Estado**: `/health` OK, pero `advisor_warmup_failed: "Datos insuficientes: 0 días"`
cada ~4-6 min (últimos vistos 18:52/18:56 ART). Causa probable: Yahoo throttlando
descargas masivas tras días de hammering (daemon en rebuilds encadenados + agentes
+ 3 batches de verificación de Kilo esta mañana) — 21.5k líneas de error yfinance
en `scripts/api_server.log`. Probe de 1 ticker responde en 1.3s → throttling por
ráfaga, NO caída dura. El loop reintenta solo (piso 60s); NO detener el daemon
sin orden de Boris (es downtime de producción).
**Reanudar con**: `rg -a "advisor_warmup_(complete|failed)" scripts/api_server.log | tail -5`
y `curl -s --max-time 20 http://127.0.0.1:8000/health`. Si sigue fallando a la
noche: proponer a Boris cooldown con daemon detenido (requiere su OK explícito).
**NO hacer**: más llamadas masivas a yfinance (Kilo ordenó pausa a todos los
agentes vía inbox; sigue vigente hasta que un rebuild salga bien).

## 3. Frente B — Cache de precios contaminado (.Telegram BLOQUEANTE del motor)

**Evidencia** (verificada, ver SESSION_LOG 2026-09-14): 28 grupos / 66 tickers
con colas idénticas al centavo (SPY=AAPL=TSLA=510.37 vs 764.29/332.27/365.44 en
vivo; vols 13x); ACN vs PEP comparten 414 filas (divergen 2025-01-16); vs
espejo Sep-2 difiere el 100% de filas comunes; VIX cache 96 vs 18.02 live;
108 parquets reescritos 08:23-08:32 en tandas de 6-9/min.
**Descartados con evidencia**: hook de integridad (solo memoiza, no escribe);
tests (usan tmp_path o stubs; el único con path absoluto `test_atlas_ticker.py`
solo LEE); updater nocturno (corre 22:00, health limpio hasta Sep-13 23:09);
restart del daemon (PID 85507 corría desde el jueves sin reinicio).
**Hipótesis líder (NO probada)**: misasignación por lote/columna en el path de
descarga/merge — los valores compartidos SÍ existen en historias reales de
otros tickers del espejo (27.72 en BAC/CMCSA/GOOGL/KO/NEM/NVDA; 262.4 en
ADBE/RCL/SPY/V), así que es dato real mal asignado, no sintético. Pista:
comparar el orden del universo en `fetch_universe_data.py` contra los grupos
(ACN/PEP/SPGI, AMZN/HD/ORCL, COST/MSFT/V no son adyacentes alfabéticos —
buscar qué orden los agrupa de a 2-4).
**Recuperación (aprobada por Boris, pendiente de ejecutar)**: (1) frenar churn
(hecho: merge+restart); (2) verificar espejo Sep-2 por muestreo (casi limpio:
2 pares dudosos COST/CRM y NFLX/TMO por spot-check); (3) restaurar espejo como
base + re-descarga limpia completa y verificación ticker-por-ticker contra
live; (4) activar `detect_cross_contamination` (ya existe en
`backend/app/core/cache_integrity.py`) como gate del updater: si detecta
duplicados, no escribe y alerta. **No correr decisiones del motor hasta entonces**
(fila ROADMAP Datos 🔴).

## 4. Frente C — Colas de agentes (tickets en main, vigentes)

- **Cline** (dashboard/frontend/backend; worktree `fundamentales-automatizado`,
  rama `ux/dashboard-control-panel`): G2 resto (widget TV externo, componentes
  muertos/solapados; RiskPanel ya mergeado) + propuesta G3 (subconjunto de 16
  indicadores con justificación). Último commit propio `ed9bd2c` (PRE_REG
  restaurado + claims pytest10/tsc0/vitest22). Quieto 3h+ al cierre.
- **OpenCode** (estrategia; worktree `test-opencode-orca`, rama
  `verify/opencode-wip` behind 14): F3 implementada en código (282+542+236 L)
  pero con 3 desvíos notificados en `TASK_KILO_A_OPENCODE_FASE3_20260913.md`:
  (1) sin pre-registro F3, (2) rama vieja pre-SWR, (3) su suite colgada 48 min
  con 1 FAIL (Kilo la terminó al inspeccionar — avisado en ticket). Su test
  NO escribe al cache real (verificado: `tempfile`/`mkdtemp`). Requiere
  re-correr con diagnóstico.
- **Claude Code**: sin créditos (verificación delegada a Kilo hasta aviso).
- **SWR propio de Kilo** (rama test-kilo-orca, commits 373e3e1+b279cb4+3a19d85):
  verificado 33/33 + falsación + ruff; pendiente merge a main con verificación
  independiente (era de OpenCode; reasignar si sigue sin créditos).

## 5. Puertas que NO se cruzan sin orden explícita de Boris

`git.no_commit_push_sin_indicacion_directa`: no commitear/pushear salvo orden
directa. No mergear a main sin aviso (salvo merges ya ordenados). No detener
el daemon API (downtime). No borrar `origin/auto-backup-safety-net` (31k
líneas de datos en repo público — respaldo a EMPRESA + delete + redirigir
mecanismo, todo pendiente de OK). No reabrir temporada de descargas masivas
(pausa vigente). `trial.slot29_preregistro_required`: slot 29 intocable sin
pre-registro nuevo + aprobación explícita.

## 6. Comandos de verificación rápida (copiar/pegar)

```bash
cd /Users/boris/Desktop/fortress_core
git log --oneline -3 && git status -sb | head -3   # estado main
ls -t backend/data/cache/pipeline_run_health_*.txt 2>/dev/null | head -2  # última corrida del updater
curl -s --max-time 20 http://127.0.0.1:8000/health   # 200 en ~0.1s = daemon vivo
rg -a "advisor_warmup_(complete|failed)" scripts/api_server.log | tail -3 | cut -c1-160  # racha del loop
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/test_advisor_warmup.py tests/test_advisor_api.py -q  # 29-38 tests, ~30s
cat /tmp/agent_watcher_heartbeat 2>/dev/null  # epoch del último ciclo del watcher (si >120 = muerto)
/tmp/suite_main_postmerge.log  # última suite completa: 1055 passed (tail -3)
```

## 7. Sesiones y memoria

- Memoria proyecto Kilo (`kilo_memory_save`, proyecto actual): premisa
  `doctrina.premisa-solido-sobre-facil` (Boris 2026-09-14, siempre proponer lo
  sólido con trade-off explicado).
- Engram proyecto `boris`: decisiones `latest_session_digest` y siguientes
  (warmup fix, SWR, orquestación, análisis miedo, incidente cache).
- Ritual de cierre estándar del repo (ONBOARDING.md): estado → commit →
  `git push origin main` → espejo EMPRESA (`git bundle` + fetch al bare) →
  memoria. Espejo git: `git -C /Volumes/EMPRESA/git-backups/fortress_core.git
  fetch <repo> 'refs/heads/main:refs/heads/main'` (solo si montado).
