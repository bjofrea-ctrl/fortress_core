# PRE-REGISTRO — Warmup advisor + paralelización load_universe (TASK_WARMUP_PARALELO_20260909)

Rama: `bjofrea-ctrl/test-kilo-orca` (NO la del doc — orden explícita de Boris).
Categoría: infra/perf. No trial, no gate-legal. Sin merge a main.
Fecha: 2026-09-10. Estado: pre-registro ANTES de tocar código.

## Qué se mide (instrumentación existente, sin agregar nueva)

- `process_time_ms` del middleware `add_request_id` (`backend/app/main.py:62-82`,
  header `X-Process-Time` + log `request_completed`). Es la única métrica de
  cierre frío-vs-caliente.
- Log `advisor_warmup_complete` (nuevo, exigido por el ticket: duración,
  n_tickets, fecha de cache). Sin log, no verificable.

## Criterios de éxito medibles (falsan el ticket si no se cumplen)

1. **Warmup no bloquea startup** — TestClient con `_load_context_sync`
   monkeypatched a sleep(30): `GET /health` responde 200 en < 5s mientras el
   warmup sigue corriendo en background. Si /health tarda ≥ warmup → FAIL.
2. **TTL nunca se alcanza en caliente** — TTL=2s, re-warmup=1.5s (inyectados
   por parámetro, sin tocar la constante de 300s): tras 3 ciclos, un request
   posterior NO dispara rebuild (`_load_context_sync` mock cuenta llamadas;
   el conteo no aumenta). Si aumenta → FAIL.
3. **Paralelo == secuencial** — `load_universe` con `download_data` stubbeado
   (dfs deterministas por ticker): el dict paralelo tiene mismos tickers,
   mismo orden de claves y mismos valores que corrida secuencial de
   referencia. Cualquier diferencia → FAIL.
4. **Fallo aislado** — stub que raisea en 1 ticker de 5: el lote termina, el
   dict trae los 4 exitosos, el fallo queda en el log de lote. Si el lote
   muere o el dict trae al fallido → FAIL.
5. **Números reales de cierre** — una request fría y una caliente a
   `/api/advisor/universe` (TestClient, cache real del worktree),
   reportando `process_time_ms` de ambas en SESSION_LOG. Caliente debe ser
   < 5% del frío. Si no hay mejora de orden de magnitud → FAIL.

## Decisiones pre-declaradas (no determinismo documentado)

- **Orden de escrituras no determinístico**: cada worker escribe su propio
  parquet (un archivo por ticker, sin colisión); el orden entre archivos no
  se garantiza. El dict resultado SÍ preserva el orden de `tickers`
  (`executor.map` lo garantiza).
- **Workers = 10** (rango del ticket 8-12; punto medio). yfinance tolera
  10 concurrentes; los retries existentes en `download_data` absorben 429.
- **Warmup calienta contexto + tickets** (no solo contexto): el costo frío
  real (~174s) está en el loop de tickets; calentar solo contexto dejaría el
  primer render esperando igual. El re-warmup reconstruye ambos.
- **Intervalo re-warmup = 280s** (TTL 300s). Caveat conocido: si un rebuild
  tardara > 280s, los ciclos se solapan por diseño (el lock serializa, sin
  stampede); documentado, no manejado (fuera de alcance).
- **Horario IV / TTL / semántica de cache**: intactos (fuera de alcance).

## Reversión

- Frente 1: borrar `warmup_advisor_loop()` + la línea `create_task` en
  `startup()` (2 puntos de edición). Sin el task, el comportamiento es el
  previo bit-a-bit.
- Frente 2: `max_workers=1` restaura ejecución secuencial sin cambiar código
  (`executor.map` con 1 worker == loop). Reversión sin deploy: variable de
  entorno o parámetro.
- Cualquiera de los 5 criterios en FAIL → revertir el frente correspondiente
  antes de reportar.
