# TASK — Precalentado del contexto advisor + paralelización de descargas (de OpenCode, autorizado por Boris 2026-09-09)

Tu worktree: `fundamentales-automatizado`. Trabaja SOLO aquí, no en main.
Categoría: infraestructura/perf (no trial, no gate-legal).
NO pushear ni mergear — Kilo verifica y mergea.

## Contexto verificado (no inferido — líneas reales)

- `backend/app/main.py:85-88` — `startup()` solo hace `init_db()` + log: **no hay
  warmup del contexto advisor**. La primera request del dashboard (o la primera
  tras 300s) paga el build frío completo.
- `backend/app/api/routes/advisor.py:214` (docstring del propio código): el loop
  de tickets costaba **~174s por request** antes del cache. En frío, ese costo lo
  paga el usuario esperando el primer render.
- `backend/app/core/data_ingestion.py:252-255` — `load_universe` es **secuencial**
  (`for t in tickers: download_data(t, ...)`) — la descarga del universo no
  paraleliza.
- TTL 300s: `advisor.py:169` — `_CONTEXT_CACHE_TTL_SECONDS = 300`.

## TU TICKET — dos frentes, un solo objetivo: que el primer render no espere ~174s

### Frente 1 — Precalentado en startup (prioritario)

**Archivo**: `backend/app/main.py` (y/o `advisor.py` si el warmup vive mejor ahí).

**Fix exigido** (mínero, sin tocar nada más):
1. En `startup()`, disparar el warmup del contexto advisor SIN bloquear el
   arranque del server (task en background: `asyncio.create_task` o equivalente
   FastAPI lifespan). El server levanta igual; el contexto se calienta en
   background, listo cuando llegue el primer visitante.
2. Re-warmup preventivo ANTES de que expire el TTL (p.ej. a los ~280s de un
   contexto recién generado): el contexto nunca llega a expirar en caliente, así
   ningún visitante paga frío por segunda vez.
   Requisito observable: medido desde el último warmup, ningún request real
   alcanza un contexto expirado.
3. Log explícito de warmup completo (duración, fecha de cache). Sin log, no es
   verificable.

### Frente 2 — Paralelización de `load_universe` (mismo ticket, independiente)

**Archivo**: `backend/app/core/data_ingestion.py`.

**Fix exigido** (mínimo, sin re-diseñar el módulo):
1. `load_universe` deja de ser secuencial: paraleliza `download_data` por ticker
   con ThreadPoolExecutor (I/O-bound; threads, no procesos). Workers acotados
   (8-12) — no unbounded. Ojo con rate-limits de la fuente (yfinance/SEC):
   workers moderados; los retries ya existen en `download_data`.
   El dict resultado preserva el orden de `tickers` (misma API de salida).
2. `_integrity_hook` corre DENTRO de `download_data` — se ejecuta en el worker
   de cada ticker. Cada worker escribe su propio parquet (un parquet por ticker,
   sin colisión). El orden de escrituras queda no determinístico (por design):
   registrar esta decisión en el pre-registro.
3. Logs de progreso: inicio/fin por lote (no por ticker, no spamear), con
   duración del lote y contador de fallos.

### Regla de la casa para TODO el ticket

- **Pre-registro obligatorio**: `PRE_REGISTRO_WARMUP.md` en la raíz del worktree
  con criterios de éxito medibles ANTES de tocar código (qué mides, qué umbral
  define éxito, cómo se revierte). Sin pre-registro commiteado primero, Kilo no
  verifica.
- **Tests** (pytest): 
  (a) warmup no bloquea startup: TestClient con `_load_context_sync`
  monkeypatched lento (sleep) → `/health` responde mientras el warmup sigue
  corriendo.
  (b) TTL nunca se alcanza en caliente: con TTL corto (p.ej. 2s) y re-warmup a
  1.5s, tras varias iteraciones ningún request paga frío.
  (c) `load_universe` paralelizado: mismo resultado y orden del dict que la
  versión secuencial (mismos tickers, misma data), con descargas stubbeadas.
  (d) fallo de un ticker no mata el lote: el lote sigue, el fallo queda logueado
  y el dict trae los exitosos.
- **Instrumentación**: el middleware de timing ya existe en `main.py` (request_id,
  process_time_ms) — usá los logs existentes, no agregues instrumentación nueva.
- **Cierre**: en SESSION_LOG reportá duración de warmup medida en dev y el
  tiempo de `/api/advisor/universe` frío vs caliente (una request de cada una,
  leyendo process_time_ms del middleware).
- **Sin credenciales, sin secrets, sin push/merge propio.** Kilo verifica y
  mergea.

## Fuera de alcance (explícito)

- No tocar el frontend ni la rama `frontend-tabs-cache-fix`.
- No cambiar el TTL de 300s ni la semántica del cache de contexto/tickets.
- No re-diseñar `data_ingestion.py` (solo paralelizar `load_universe`).
- No tocar `cache_integrity.py` ni los retries existentes.
