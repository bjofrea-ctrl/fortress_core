# Feature: limpieza-operativa-fortress

## Objective
Dejar fortress_core limpio y operativo, cubriendo todos los pendientes sin que los agentes se pisen, con lo más sólido (no lo más fácil).

## Problem
- Daemon en fail-loop por throttling Yahoo + cache contaminado bloqueante + tickets agentes con desvíos + gates sin cerrar.
- Riesgo de pisarse: descargas masivas concurrentes, writes al cache real, merges/commits sin orden.

## Why
Gate 90 días (eval 01-12-2026 o +60 días limpios) necesita tubo limpio. Sin tubo no hay activo para decidir.

## Scope
Solo `~/Work/fortress_core`, main `1d4b67d`. No otros repos, no VPS, no disco salvo pedido explícito.

## Constraints / Puertas
- Preservar SIN commitear: `backend/app/api/routes/advisor.py`, `backend/app/core/data_ingestion.py`, `PAUSE_YAHOO_MASS_DOWNLOAD`, `scripts/clean_download/`.
- `git.no_commit_push_sin_indicacion_directa`: no commit/push/merge sin orden directa.
- No detener daemon API sin OK (downtime).
- No descargas masivas yfinance (pausa vigente).
- No writes al cache real desde tests (tmp_path/stubs).
- Slot 29 intocable sin pre-registro nuevo + aprobación.
- No borrar `origin/auto-backup-safety-net` sin OK.

## TDD / Checks
- TDD mode: unresolved (no se invoca sdd-init para ODD). Se usan checks funcionales ordinarios, no TDD estricto.
- Runner observado en docs (no precedente inventado): `PYTHONPATH=. backend/.venv/bin/python -m pytest ...`, `curl /health`, `rg advisor_warmup`.
- Verificación por tarea abajo.

## Delivery
- Estrategia: `ask-on-risk` (default). Forecast <400 líneas por slice; si un slice supera, se pregunta split vs exception antes del siguiente commit.
- Commits: work-unit por tarea en feature branch (si se sale de main, branch primero), Conventional Commits, sin push sin orden.

## Tasks

- [x] T1-pausa-yahoo-sostener — Verificado por fortress-kilo readonly: `data_ingestion.py:228,232`, `advisor.py:409,415,418,422`, `scripts/clean_download/download_ticker_by_ticker.py:4,9`, flag activo. Sin descargas masivas. Route: delegated direct (kilo w2:p2).
- [x] T2-cache-diagnostico-readonly — Kilo readonly: 0 parquets en data/cache y backend/data/cache (solo logs), gate mapeado `cache_integrity.py:326-368,118-122,730-759`, universo `fetch_universe_data.py:12-38`. Restauración espejo + reconcile BLOQUEADA: exige disco fuera de alcance + downloads masivos (viola pausa) + venv ausente. Testigo preservado. Route: delegated direct (kilo w2:p2).
- [x] T3-daemon-estabilidad — Observado por fortress-kilo: API caída (health vacío, sin uvicorn, sin api_server.log). Diverge de HANDOFF 14-09. Requiere tu decisión para levantar. Checks: `curl --max-time 20 /health`, `rg warmup`. Route: delegated direct (kilo w2:p2).
- [ ] T4a-cline-g2g3 — G2 resto + G3 (16 indicadores) solo en `fundamentales-automatizado` / frontend. No tocar motor decisión. Route: delegated direct writer (2+ files no-triviales).
- [ ] T4b-opencode-f3 — Re-correr F3 con diagnóstico, en `verify/opencode-wip`, con pre-registro faltante señalado, sin writes a cache real. Route: delegated direct writer aislado.
- [ ] T4c-kilo-swr-merge — Verificación independiente SWR + merge solo con orden. Route: delegated direct verificador.
- [ ] T5-higiene-gates — `clean_days.json`/`clean_days_counter.py`, reconcile huérfanas, A2-A9/B1 estado, safety-net pendiente OK. Sin mutar criterios estadísticos. Route: inline verificación.

## Aislamiento anti-pisadas
- T1/T3: solo lectura + 1 probe. T2: lectura + tmp. T4a/b/c: worktrees/ramas distintas, file-ownership disjunto (frontend vs estrategia vs SWR). T5: solo contadores/logs. Ningún slice escribe `data/cache/*.parquet` real ni commitea.
- Orden: T1+T3 primero (seguridad), luego T2, luego T4a/b/c en paralelo aislado, T5 al final.

## Progress
- 2026-09-24: árbol verificado `1d4b67d`, `M advisor.py/data_ingestion.py`, `?? PAUSE + clean_download/`. Doc creado.
- 2026-09-24: marcha blanca herdr T1+T3 por fortress-kilo (w2:p2) — pausa verificada con file:línea, API caída hallada. Mirror Engram al día.
- 2026-09-24: ventana limpieza CERRADA con éxito verificado — 102 parquets 2948 filas, gate 0/0/0, snapshot `data/cache_snapshots/full_102_tickers_20260924.json`, pausa reactivada. Cumple pre-registro.

## Verification evidence
- `git status -sb` + `git diff --stat` observados (4 files, 57+/130-).
- Kilo readback: data_ingestion 228/232, advisor 409/415/418/422, clean_download 4/9; health vacío.

## Next step
- Pre-registro T2-mirror recibido de Kilo: NO hay espejo válido (EMPRESA sin montar, git-backups sin parquets, Sep-2 contaminado 38/7/64). Limpieza = descarga completa 102 + gate 0/0/0 + snapshot + re-pausa. BLOQUEADO hasta ventana de limpieza con OK de Boris (a+b+c+d atómicos).

## Locator
- Repo-relative: `odd/tasks/limpieza-operativa-fortress.md`
- Mirror: Engram topic `odd/limpieza-operativa-fortress/tasks`
