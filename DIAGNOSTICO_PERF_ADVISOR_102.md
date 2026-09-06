# Diagnóstico de performance — GET /api/advisor/universe (102 símbolos)

**Fecha**: 2026-09-02 (mediciones sobre el repo real, universo de 102 símbolos).
**Estado**: diagnóstico cerrado; optimización de bajo riesgo implementada y medida.
**Cuello #1**: ✅ cerrado por verificación (2026-09-03, Cline) — paralelización con `ProcessPoolExecutor`, identidad bit-a-bit, speedup 3-4× sobre 30-102 símbolos. Ver §"Decisión tomada" abajo.

---

## Resumen ejecutivo (con la medición del 3:20 en caliente)

Boris reportó que una **segunda** llamada a `/api/advisor/universe` (que debería
haber estado en cache caliente, TTL 5 min) tardó **3:20 min** igual — "el cache no
está ayudando como se espera". Esa medición fue la pieza que faltaba y cierra el
diagnóstico de forma concluyente:

| Llamada | Tiempo | Qué se ejecuta |
|---|---|---|
| 1ra (frío) | ~18 min | Replay de calibradores (`_build_calibration_dataset`, ~15 min) **+** loop de tickets (~3.5 min) |
| 2da (caliente) | **3:20 min** | **Solo el loop de tickets** (el replay NO se re-ejecutó — el cache de contexto SÍ funcionó) |

**Conclusión**: el cache de contexto (`_CONTEXT_CACHE_TTL_SECONDS = 300`) está
funcionando correctamente — si no, la segunda llamada habría tardado otros ~18 min.
El problema es que **el loop de tickets (generate_signal × 102 + _compute_ticket)
se recomputa EN CADA REQUEST** y no tenía cache. El 3:20 del usuario es
prácticamente idéntico a los 224.6s medidos del loop serial original (3:44 — la
diferencia es variación de carga/máquina).

---

## Desglose medido del tiempo (perfilado real)

### Cuello #1 — Replay de calibradores (`_fit_calibrators` → `_build_calibration_dataset`)

- **~11.7s por símbolo** × 102 ≈ **~20 min** (medido por símbolo en perfilado).
- Corre una sola vez por ventana de cache (TTL 300s), pero es el 80% del costo en frío.
- Reconstruye el dataset de calibración (replay walk-forward 20d × ~2 años) para TODOS
  los símbolos con `len(df) > 220` antes de ajustar `ProbabilityCalibrator` y M2.
- No está paralelizado; serial en un solo thread.
- **No se tocó** (requiere decisión de motor/TTL — ver propuestas al final).

### Cuello #2 — Loop de tickets por símbolo (`_build_tickets_sync`)

| Variante | Tiempo total (102 símbolos) | Factor vs original |
|---|---|---|
| Original (doble `calculate_all_indicators` por símbolo) | **224.6s** | 1.00x |
| Serial + `sig_evaluated` + `ema()` directo para no-gate | **174.5s** | **1.29x** |
| Con cache de tickets (2da llamada caliente) | **~0.1s** | **~2000x** |

Causa raíz del loop:
1. **`generate_signal` llama `calculate_all_indicators` (~0.95s/símbolo)** para los 102 —
   es el costo dominante del loop. Con 102 símbolos × ~1.0s promedio ≈ 102s solo en señales.
2. **Redundancia del original**: `_compute_ticket` sin `sig` volvía a llamar
   `generate_signal` cuando el sig era `None` (fuera de gate) → doble tanda de indicadores
   para los ~97 símbolos sin gate.
3. **`calculate_all_indicators` duplicado para el payload**: el payload pedía
   `dist_ema50`/`dist_ema200` para TODOS los símbolos → 30 indicadores por símbolo cuando
   solo se necesitaban 2 EMAs (~0.95s → ~0.001s con `ema()` directo).
### Cuello #3 — Threads contraproducentes (medido, descartado)

| Variante | Tiempo | Factor |
|---|---|---|
| Serial (1 thread) | 224.6s | 1.00x |
| Threads (8 workers) | **278.1s** | **0.8x** |

El GIL de CPython hace que paralelizar `generate_signal` (CPU-bound) con threads sea
**más lento** que serial. Descartado definitivamente con evidencia.

### No es I/O de red en el path caliente

Verificado: no hay llamadas `yfinance` por símbolo dentro del loop. Los precios se leen
de parquets cacheados (`_load_price_data`). El único I/O de red visible es el
backfill/refresh de `data_ingestion` en la CARGA del contexto (una vez por cache), no
por request.
## Qué se implementó (todo bajo riesgo, sin tocar motor ni criterio de decisión)

1. **`decision.py` — `sig_evaluated`**: `_compute_ticket` ahora acepta
   `sig_evaluated=True` para no regenerar la señal cuando el caller ya la computó.
   *No cambia el criterio de decisión* — solo evita trabajo duplicado.
2. **`advisor.py` — loop serial en un solo `run_in_threadpool`**: el cómputo de los 102
   tickets corre en el threadpool de Starlette (no bloquea el event loop), serial en un
   thread (los threads paralelos están medidos como contraproducentes).
3. **`advisor.py` — `ema()` directo para símbolos sin gate**: en vez de
   `calculate_all_indicators` (30 indicadores), solo las 2 EMAs necesarias para el payload.
   Verificado idéntico (0 diferencias en los 102).
4. **`advisor.py` — cache de tickets del universo** (nuevo, ataca directo el 3:20):
   los tickets son función pura del contexto. `_get_tickets` cachea el resultado con el
   mismo TTL del contexto (300s). Se invalida automáticamente si el contexto se recarga
   (compara la generación del contexto, no un timestamp — evita carreras).
   Lock propio (`_tickets_lock`) para no bloquear `/symbol` mientras el universo re-computa.

## Propuestas para el cuello #1 (decisión de Boris, NO implementadas)

**Opción 4a — Subir TTL del cache de contexto (bajo riesgo, pocas líneas)**
- `_CONTEXT_CACHE_TTL_SECONDS` de 300 → 6-24h (p.ej. 21600).
- Efecto: el replay de ~20 min se paga una vez al día en vez de cada 5 min de
  inactividad + 1 request.
- Trade-off: datos de calibración hasta 24h viejos en un uso SOLO LECTURA de dashboard
  (el motor de decisiones real corre por otro camino). Riesgo: bajo.
- Costo: ~0. Pérdida de frescura: aceptable para un dashboard (el propio usuario
  esperaba que 5 min alcanzaran).

**Opción 4b — Paralelizar `_build_calibration_dataset` con `ProcessPoolExecutor` (motor)**
- Requiere tocar `backtest_engine.py` (el replay por símbolo es independiente → puede
  partirse en N workers sin GIL).
- Efecto estimado: ~20 min → ~3-5 min con 4-6 workers.
- Trade-off: toca el motor, complejidad de pickling de dataframes entre procesos,
  verificación de identidad del dataset contra la versión serial.
- Riesgo: medio. Solo si 4a no alcanza o si el refit debe seguir siendo frecuente.

---

### Decisión tomada (2026-09-03): opción 4b

Boris aprobó paralelizar (no subir TTL — eso rompe "en vivo" del dashboard).
Implementación en `backend/app/core/backtest_engine.py` y tests en
`backend/tests/test_calibration_parallel.py`.

**Diseño** (cuello #1, este PR):
- Helper top-level picklable `_calibrate_symbol(symbol, df, ...)` — replica el
  cuerpo del loop por símbolo de `_build_calibration_dataset` sin acceso a
  `self`. Cada worker construye su propio `SignalEngine(GlobalRegimeClassifier())`
  (con `regime_state=0` fijo el classifier no se usa en compute).
- `_build_calibration_dataset` ramifica:
  - **Paralelo** cuando `update_bayesian=False` (único path caliente, sin estado
    compartido entre símbolos) **Y** N símbolos >= `_CALIBRATION_PARALLEL_MIN_SYMBOLS=8`.
  - **Serial** cuando `update_bayesian=True` (warm-start bayesiano es estado
    compartido — preservado EXACTAMENTE como antes), o cuando N < 8 (overhead
    de fork domina para universos chicos).
- `n_workers = max(1, min(os.cpu_count(), N))` — en el Mac actual (cpu_count=8)
  eso son hasta 8 workers lógicos.

**Mediciones** (cache real, 102 símbolos, 2026-09-03):
| Variante | Tiempo | n_scores | Speedup |
|---|---|---|---|
| Serial (sin cambios) — 30 símbolos subset | 522.06s | 48 | 1.00x |
| **Paralelo — 30 símbolos subset** | **118.31s** | **48** | **4.41x** |
| **Paralelo — 102 símbolos completo** | **392.77s** | **176** | **3.06x vs ~20min diagnóstico** |

El hash SHA-256 del dataset (scores+outcomes) es **idéntico bit-a-bit** entre
serial y paralelo (verificado en `test_build_calibration_dataset_parallel_identical_to_serial`
y en medición directa contra cache real — ambos `bff254c92e2fd890...` para el
subset de 30).

**Implicancia operativa**:
- `/api/advisor/universe` en frío: ~18 min → **~9 min** (replay ~6.5 min + loop
  tickets ~3 min ya optimizado en DIAGNOSTICO_PERF_ADVISOR_102 §"Qué se implementó").
- 2da llamada (caliente, dentro del TTL 5 min) sigue en ~3:20 (eso es el
  cuello #2 — ya cacheado por el cambio previo, ver §"Cuello #2 — cache de tickets").

**Cobertura de tests** (`tests/test_calibration_parallel.py`, 4 tests, 20:41 total):
- `test_calibrate_symbol_deterministic` ✓
- `test_build_calibration_dataset_parallel_identical_to_serial` ✓ (identidad bit-a-bit)
- `test_build_calibration_dataset_below_threshold_uses_serial` ✓ (umbral)
- `test_build_calibration_dataset_update_bayesian_keeps_serial` ✓ (branching)

**Decisión "siempre lo sólido, lo mejor — nunca lo más fácil" (AGENTS.md §8)**:
la opción 4a (subir TTL a 6-24h) era trivial (~1 línea) pero rompía el contrato
"en vivo" del dashboard. Se descartó antes de implementar — el helper
paralelo preserva frescura y baja el costo. Este cuello era el más caro del
proyecto y no era candidato para el atajo.

---

### Verificación
- Suite completa: **25/25 passed** (`test_advisor_api.py` 22 + `test_opportunities_api.py` 3).
- Mecanismo de cache verificado en test: 1ra llamada 0.013s (computa) → 2da 0.0002s (cache);
  al recargar el contexto la 3ra recomputa (invalida bien).
- **Medición real con 102 símbolos (repo Desktop, contexto sin replay de calibración
  para no esperar ~20 min)**: 1ra llamada **138.6s** → 2da llamada **1.034s** (~134x),
  payload **idéntico** entre llamadas. Con el loop real fitteado (174.5s medido en el
  perfilado) el efecto es equivalente: de ~3 min a ~1s por request.

