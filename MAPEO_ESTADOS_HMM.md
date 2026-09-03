# Mapeo de estados HMM — análisis de identificabilidad B6 y fix propuesto

**Fecha:** 2026-09-02 · **Autor:** Cline (worktree `fundamentales-automatizado`)
**Origen:** auditoría externa (GLM) sobre el régimen classifier (`AUDITORIA_GLM_RONDA2.md`
B6 — identificabilidad entre refits trimestrales: GOLDILOCKS/REFLATION pueden voltearse
de nombre entre refits porque el HMM no tiene orden fijo).
**Mandato:** mapear los 4 estados del HMM a variables observables, encontrar una
convención de orden ESTABLE entre refits, e implementarla en `_align_states` si es
posible. **Esto NO toca el ledger ni el motor de señales — es una mejora de
infraestructura del HMM, mismo patrón que T2.2 (HMM walk-forward) y F0.1 (seed Monte
Carlo).**

---

## 0. El problema B6 (re-encuadre)

El `GlobalRegimeClassifier` (`backend/app/core/regime_classifier.py`) entrena un
`hmmlearn.GaussianHMM` con `n_states=4` y `covariance_type="full"`. El HMM produce
**raw states** (0, 1, 2, 3) que son etiquetas arbitrarias — el HMM no tiene orden
intrínseco (es unsupervised). Para hacer los estados interpretables, el código tiene
`_align_states()` (líneas 51-76) que los renombra a semánticos:
- `0 = GOLDILOCKS` (max equity)
- `1 = REFLATION` (max commodity)
- `2 = STAGFLATION` (resto)
- `3 = DEFLATION` (max bonds)

El método actual: `max(metrics, key=lambda s: metrics[s]["equity"])` etc. Esto
**depende del ranking de cada refit**. Si dos refits distintos producen rankings
distintos (porque la muestra cambia), el mismo raw state (e.g. raw 1) puede terminar
mapeado a GOLDILOCKS en un refit y a DEFLATION en otro.

**Consecuencia operativa:** los trials `regime_gating_p`, `kama_hma_supertrend`,
`m3_gate_standalone` (todos en `motor_signal` / `signal_diagnosis` ledger) usan el
clase `WalkForwardRegimeGate` que recalibra cada 63d. **Cada recalibración es un
refit del HMM** — entre recalibraciones, el mismo raw state "1" puede cambiar de
GOLDILOCKS a DEFLATION. Eso es un **mode collapse** del clasificador: el switch de
régimen que el gate observa NO refleja un cambio económico real, refleja un
reordenamiento arbitrario del HMM.

---

## 1. Análisis empírico: ¿son los raw states estables?

**Hipótesis testeada:** los raw states del HMM SÍ tienen perfiles económicos
consistentes entre refits — el problema es solo el reordenamiento, no la
identificación de los clusters.

**Metodología:** 4 refits con muestras distintas (mismos parquets del cache real
del proyecto, 9 tickers macro: SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG + VIX):

| Refit | Rango | N días |
|---|---|---|
| A | 2015-01-02 → 2026-08-31 (todo el cache) | 2923 |
| B | 2020-01-01 → 2026-08-31 (W2-W3 del proyecto) | 1615 |
| C | 2015-01-02 → 2019-12-31 (W1 del proyecto) | 1198 |
| D | 2018-01-01 → 2026-08-31 (sin 2015-2017) | 2158 |

**Resultados de los raw states (sin alinear) — perfil de cada raw state por
refit, ordenado por VIX medio ascendente:**

| Refit | Rank 0 (VIX bajo) | Rank 1 | Rank 2 | Rank 3 (VIX alto) |
|---|---|---|---|---|
| A | raw 2: VIX 16.0, SPY +5.16% | raw 3: VIX 17.6, SPY +6.14% | raw 1: VIX 21.7, SPY +1.53% | raw 0: VIX 22.7, SPY -3.77% |
| B | raw 1: VIX 16.3, SPY +6.56% | raw 2: VIX 22.3, SPY +8.35% | raw 3: VIX 23.1, SPY -1.13% | raw 0: VIX 24.3, SPY -3.12% |
| C | raw 3: VIX 11.5, SPY +4.76% | raw 0: VIX 14.3, SPY +3.04% | raw 1: VIX 15.2, SPY +4.60% | raw 2: VIX 20.0, SPY -2.77% |
| D | raw 0: VIX 17.7, SPY +6.24% | raw 2: VIX 18.1, SPY +5.38% | raw 3: VIX 26.4, SPY -4.99% | raw 1: VIX 30.8, SPY -8.60% |

**Lectura de la tabla:**

1. **Rank 0 (VIX más bajo) SIEMPRE tiene SPY60 positivo** (5.16%, 6.56%, 4.76%,
   6.24% en A/B/C/D). Consistente con un perfil "growth/low-vol" — el **GOLDILOCKS
   canónico** (growth + low VIX).

2. **Rank 3 (VIX más alto) SIEMPRE tiene SPY60 negativo o marginal** (-3.77%,
   -3.12%, -2.77%, -8.60%). Consistente con un perfil "risk-off/high-vol" — el
   **DEFLATION canónico** (equity baja + VIX alto).

3. **Rank 1 y Rank 2 son ambiguos entre refits** (a veces tienen SPY fuerte
   positivo, a veces marginal). Eso es esperable: la frontera entre
   GOLDILOCKS/REFLATION y REFLATION/STAGFLATION depende del sample. **No se
   puede fijar con una sola dimensión.**

4. **El raw state ID cambia entre refits** (raw 0 es bear en A y B, raw 0 es
   middle/bull en C, raw 0 es bull en D). **Eso es exactamente el bug B6.**

**Conclusión empírica (1):** los raw states SÍ identifican perfiles económicos
reales, pero sus IDs son arbitrarios entre refits. El bug NO es del HMM — es del
re-etiquetado.

---

## 2. La convención de orden ESTABLE

Tres candidatos de convención:

### 2.1 Candidato A: VIX medio ascendente
- **Regla:** rank 0 = estado con VIX medio más bajo; rank 3 = estado con VIX
  medio más alto.
- **Pro:** VIX es unidimensional, monotónico con riesgo, robusto a cambios en
  sample (VIX tiene un rango natural ~10-30 que no cambia entre refits).
- **Pro:** los rangos 0 y 3 quedan **perfectamente identificados** como bull y
  bear en los 4 refits (verificado arriba).
- **Contra:** los rangos 1 y 2 son ambiguos (no siempre distinguibles entre sí
  por VIX solo).

### 2.2 Candidato B: SPY 60d descendente
- **Regla:** rank 0 = estado con SPY60d más alto; rank 3 = estado con SPY60d más
  bajo.
- **Pro:** monotónico con growth.
- **Contra:** en refit B, el rank 1 (SPY +8.35%) tiene MAYOR growth que el
  rank 0 (SPY +6.56%) — el ranking por SPY puro no separa bien growth de
  inflation (commodities suben junto con equity en REFLATION, no se distinguen
  por SPY solo).

### 2.3 Candidato C: combinación VIX + SPY (criterio del código actual)
- **Regla:** rank 0 = max equity, rank 1 = max commodity, rank 2 = resto, rank 3 =
  max bonds.
- **Pro:** multidimensional, captura los 4 regímenes canónicos.
- **Contra:** **ES LO QUE ESTÁ ROTO.** El método `max(metrics, key=...)` depende
  de los rankings de cada refit, y los rankings pueden rotar.

### 2.4 Decisión: Candidato A (VIX ascendente) con refinamiento

**VIX ascendente como criterio base** porque es la única dimensión que da una
clasificación estable de los **extremos** (rank 0 = bull confirmado, rank 3 =
bear confirmado) en los 4 refits testeados. Los rangos intermedios se asignan
por **SPY 60d descendente como tie-breaker** (rank 1 = segundo mejor SPY, rank 2 =
segundo peor SPY).

**Convención final (4 estados, orden estable):**

| Rank | Etiqueta | Criterio (VIX asc, SPY desc) | Lectura económica |
|---|---|---|---|
| 0 | `GOLDILOCKS` | VIX más bajo (y SPY alto dentro de ese grupo) | Crecimiento + baja vol |
| 1 | `REFLATION` | VIX bajo-medio, SPY alto (commodities ↑) | Crecimiento + inflación |
| 2 | `STAGFLATION` | VIX medio-alto, SPY bajo (commodities ↑ pero equity ↓) | Inflación sin crecimiento |
| 3 | `DEFLATION` | VIX más alto (bonds ↑, flight-to-quality) | Recesión / risk-off |

**Nota crítica:** esta convención NO es perfecta — los rangos 1 y 2 son
**a veces** intercambiables (en refit C, rank 1 y 2 tienen SPY similares). Pero
los **extremos** (0 y 3) son robustos, y eso es lo que importa operativamente:
un gate de régimen que dice "GOLDILOCKS vs DEFLATION" es accionable; un gate
que dice "REFLATION vs STAGFLATION" requiere información más fina que el HMM
proporciona.

---

## 3. Implementación del fix

**Cambio mínimo en `regime_classifier.py:_align_states`:**

Reemplazar el método actual (líneas 51-76) que usa `max(metrics, key=...)` por
uno que ordena los raw states por **VIX medio ascendente** y luego asigna las
etiquetas por **rank** (no por max de una métrica).

**Decisión sobre el cambio:** Boris me dio mandato explícito de implementar si
encontraba una convención estable. La encontré (VIX ascendente, robusto en
4 refits). El fix es chico (cambiar el cuerpo de `_align_states`, agregar
tests), no toca la API pública del clasificador (los nombres `GOLDILOCKS/REFLATION/
STAGFLATION/DEFLATION` se mantienen), y es backward-compatible con todo el código
que consume los `state_name`.

---

## 4. Riesgos del fix (declarados)

1. **Los rangos 1 y 2 son ambiguos.** En refit C, rank 1 (VIX 14.3, SPY +3.04%) y
   rank 2 (VIX 15.2, SPY +4.60%) son indistinguibles. El tie-breaker por SPY
   los separa, pero el resultado es sensible al ordenamiento secundario. **Riesgo
   aceptable:** esos rangos no son críticos para gates operacionales.

2. **Si VIX tiene datos faltantes en el refit**, `vix_level.mean()` puede ser
   NaN. Mitigante: el código original ya exige `_extract_features` con
   `dropna()`, así que VIX está presente donde hay features.

3. **El fix cambia el orden de las etiquetas semánticas** respecto al código
   actual. Si algún test externo asume que raw state `0` = GOLDILOCKS (en lugar
   de "el raw state con VIX más bajo"), va a romperse. Mitigante: solo el código
   interno del repo usa las etiquetas, y los tests del regime_classifier se
   actualizan en este mismo cambio.

4. **El HMM sigue siendo estocástico** (`random_state=42` pero el `covariance_type="full"`
   puede tener variabilidad si la librería cambia de versión). El fix no
   elimina esa estocasticidad; solo asegura que la convención de ordenamiento
   sea estable DADO un HMM entrenado. El bug B6 queda cerrado pero la
   variabilidad de los clusters persiste.

---

## 5. Tests propuestos (en `test_regime_classifier.py`)

1. `test_align_states_orden_por_vix_ascendente` — 4 refits (A, B, C, D), cada
   uno verifica que el raw state con VIX medio más bajo quede mapeado a
   `GOLDILOCKS` (rank 0) y el de VIX más alto a `DEFLATION` (rank 3).
2. `test_align_states_estabilidad_entre_refits` — verifica que el mismo raw
   state tiene el mismo perfil económico (VIX/SPY/bonds) en distintos refits.
3. `test_align_states_extremos_estables` — verifica específicamente que rank 0
   SIEMPRE tiene SPY60 > 0 y rank 3 SIEMPRE tiene VIX > percentil 75.

---

## 6. Resumen del estado de la auditoría

| Hallazgo B6 | Estado |
|---|---|
| B6 identificado (GLM ronda 2) | Cerrado (este doc) |
| Convención estable encontrada | VIX ascendente, robusto en 4 refits |
| Fix implementado | Sí (en este commit) |
| Tests agregados | Sí (test_regime_classifier.py) |
| Compatibilidad con código existente | API pública intacta (mismas etiquetas) |
| Riesgos documentados | §4 de este doc |
| No toca el ledger | Confirmado (solo `regime_classifier.py` + tests) |
| No toca el motor de señales | Confirmado (el HMM es upstream del motor) |

---

## 7. Regresión conocida y resolución (2026-09-02) — NO reintroducir

**Contexto**: el commit del fix B6 (`dd1d6c1`) rompió 3 tests de lag en
`test_backtest_engine.py` (`test_entrada_con_lag_1...`, `test_entrada_con_lag_0...`,
`test_salida_con_lag_1...`): el backtest pasó de 1 trade a 0 trades.

**Causa raíz (verificada contra el refit real)**: `_market_data()` en esos tests
arma el MISMO dataframe sintético para los 9 tickers macro
(SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG/^VIX). Con features de retorno idénticas,
`_align_states_legacy` colapsaba: los 3 `max(metrics, key=...)` devolvían el mismo
raw state y el dict literal `{g:0, r:1, st:2, d:3}` quedaba con keys duplicadas
(gestionadas por el intérprete a favor de la última) → el raw state del día de
señal quedaba FUERA del remap y mantenía su id → 2 (STAGFLATION, no bloqueante)
**por accidente del bug**. Con VIX ascendente ese mismo día cae en 3 (DEFLATION)
y el gate `regime_state == 3` de `signal_engine.generate_signal` lo bloquea —
comportamiento CORRECTO del motor ante un régimen distinto.

**Decisión**: el alineamiento por VIX es correcto (fix B6 se mantiene). Los tests
de lag verifican la MECÁNICA de ejecución (T0.2), no el régimen: sobre un panel
degenerado el régimen es arbitrario. La resolución fue fijar la ENTRADA de régimen
del motor a GOLDILOCKS (0) en `_run()` de `test_backtest_engine.py` (parcheando
`predict_current_regime`), dejando intactos `signal_engine`, la elegibilidad y el
fit HMM real. Ver commit `2ab6658`.

**Lección para agentes futuros**: si un test que NO prueba régimen empieza a
fallar por el mapeo de `_align_states`, verificar primero si el panel del test es
degenerado (tickers idénticos). NO debilitar el gate (`regime_state == 3`) ni
reintroducir el orden legacy — aislar la entrada de régimen en el test.

