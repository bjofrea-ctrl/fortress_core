# Diagnóstico de performance — GET /api/advisor/universe (102 símbolos)

**Fecha**: 2026-09-02 (mediciones sobre el repo real, universo de 102 símbolos).
**Estado**: diagnóstico cerrado; optimización de bajo riesgo implementada y medida.
**Pendiente (decisión de Boris)**: cuello #1 — replay de calibradores en `_build_calibration_dataset`.

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

### Verificación
- Suite completa: **25/25 passed** (`test_advisor_api.py` 22 + `test_opportunities_api.py` 3).
- Mecanismo de cache verificado en test: 1ra llamada 0.013s (computa) → 2da 0.0002s (cache);
  al recargar el contexto la 3ra recomputa (invalida bien).
- **Medición real con 102 símbolos (repo Desktop, contexto sin replay de calibración
  para no esperar ~20 min)**: 1ra llamada **138.6s** → 2da llamada **1.034s** (~134x),
  payload **idéntico** entre llamadas. Con el loop real fitteado (174.5s medido en el
  perfilado) el efecto es equivalente: de ~3 min a ~1s por request.

