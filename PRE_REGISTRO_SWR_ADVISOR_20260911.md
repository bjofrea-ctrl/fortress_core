# PRE-REGISTRO — Stale-while-revalidate en /api/advisor/universe (TASK_SWR_ADVISOR_20260911)

Rama: `bjofrea-ctrl/test-kilo-orca` (NO mergear a main sin aviso — orden Boris).
Categoría: infra/perf. No trial, no gate-legal. Sin merge a main.
Fecha: 2026-09-11. Estado: pre-registro ANTES de tocar código.

## Contexto (verificado por Claude Code con curl real en la VPS Oracle)

El warmup+paralelo mergeado funciona en caliente (0.49s), pero un request a
`/api/advisor/universe` que cae DURANTE un rebuild (cada ~5-7min, 100-135s en
la VPS por ancho de banda limitado) espera el rebuild COMPLETO: el endpoint
toma `_context_lock`/`_tickets_lock` y se bloquea. Se sintió como "dashboard
lento/no funcional".

## Qué se mide (instrumentación existente, sin agregar nueva salvo el flag)

- `process_time_ms` del middleware `add_request_id` (`backend/app/main.py`).
- Asserts de tests nuevos contra `advisor_universe()` directo (sin HTTP).
- `is_stale` (nuevo, top-level en la respuesta de `/universe`): True si el
  par servido superó el TTL al momento de servirlo.

## Criterios de éxito medibles (falsan la tarea si no se cumplen)

1. **Request durante rebuild activo NO bloquea**: con ambos locks tomados
   (rebuild en curso simulado) y un par completo previo en cache,
   `advisor_universe()` responde en <1.0s sirviendo el par anterior, con
   `is_stale=True` (el par superó el TTL). Si tarda ≥1s o bloquea → FAIL.
2. **Cold start real sigue bloqueando**: con caches en None y sin par previo,
   el request espera al rebuild (tarda ≥ lo que tarda el loader stubbeado),
   devuelve payload fresco con `is_stale=False`. Si retorna vacío/instantáneo
   sin payload, o marca stale un payload fresco → FAIL.
3. **Flag explícito**: `is_stale` existe top-level en `/universe`; True solo
   cuando el par servido superó el TTL; el camino bloqueante-fresco lo
   devuelve False. Si falta la key o miente en algún camino → FAIL.
4. **Nunca mezcla de generaciones**: el par servido cumple siempre
   `tickets.ctx_time == context gen` (el request durante la fase de tickets
   del rebuild NO recibe contexto nuevo + tickets viejos: recibe el par viejo
   completo). Si un test observa mezcla → FAIL.
5. **Tests existentes verdes**: suite warmup + advisor_api intacta
   (`_get_context` default sigue bloqueante para `/symbol`, `/theses` y el
   propio warmup — cero cambios de comportamiento fuera de `/universe`).

## Decisiones pre-declaradas

- **TTL 300s y cadencia intactos** (orden explícita): no se toca
  `_CONTEXT_CACHE_TTL_SECONDS` ni la semántica del loop (ancla a gen+TTL,
  piso 60s). El fix es solo comportamiento de LECTURA bajo contención.
- **Snapshot atómico, un solo writer**: un único global
  `_last_complete_pair = (ctx_tuple, tickets, gen, gen_time) | None`,
  escrito solo por `warmup_advisor_once()` al completar un ciclo con
  generaciones coherentes (verifica `_context_cache_time == ctx_gen` y
  `_tickets_cache_ctx_time == ctx_gen` antes de publicar; si un rebuild
  concurrente se metió en el medio, no publica). Una sola asignación =
  snapshot atómico: ningún lector ve un par mezclado.
- **Solo `/universe` usa SWR** (`/symbol`, `/theses`, warmup: intactos).
- **Staleness máxima acotada por el ciclo**: el par servido puede superar el
  TTL hasta ~lo que reste del rebuild (~180s tickets en el peor caso); el
  flag `is_stale=True` lo declara siempre. El ticket pide "unos segundos"
  pero el criterio medible es <1s de respuesta + flag honesto: la fase de
  tickets del rebuild es larga y servir mezcla sería peor (criterio 4).
- **`_cache_date()` (scan de ~110 parquets, ~1s medido en este repo) NO se
  llama en el camino SWR**: rompería el presupuesto <1s del criterio 1. El
  `staleness` del camino SWR se computa del tuple servido en memoria
  (misma fuente: los parquets de los que se cargó).
- **is_stale por edad, no por camino**: `True ⟺ (now - gen_servido) ≥ TTL`,
  en ambos caminos. Un lock tomado con cache aún fresco sirve fresco
  (flag False): el dato manda, no el camino.

## Reversión

- Quitar el branch SWR en `advisor_universe` + el helper de render + el
  snapshot-write en `warmup_advisor_once` → comportamiento previo bit-a-bit
  (`_last_complete_pair` sin lectores es inerte; getters intactos).
- Cualquiera de los 5 criterios en FAIL → no se pushea la rama.
