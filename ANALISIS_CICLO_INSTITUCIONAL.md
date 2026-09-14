# Termómetro de sentimiento + Ciclo institucional — diagnóstico, herramienta y hipótesis evaluada

**Fecha**: 2026-09-11 · **Worktree**: `test-opencode-orca`
**Alcance**: (1) diagnóstico de fuentes día a día, (2) termómetro implementado (solo lectura),
(3) hipótesis del ciclo institucional (piso → alza lenta → retest → markup) medida sobre
5 años y ~130 activos, con SPY como caso de referencia.

---

## 1. Diagnóstico de fuentes — qué responde HOY, gratis y sin key

| Fuente | Acceso | Estado | Frecuencia |
|---|---|---|---|
| **CNN Fear & Greed** | `production.dataviz.cnn.io/index/fearandgreed/graphdata` — JSON 200 | ✅ **Desbloqueo clave**: trae put/call diario (0.65 hoy) que CBOE bloqueaba, VIX, breadth, junk bonds, + 1 año de histórico (252 pts) y score actual | Diario |
| **GDELT tone** | `api.gdeltproject.org` timelinevolinfo | ✅ 200 (con 429 por rate limit — necesita backoff) | Diario (15d por llamada, acumulable) |
| FRED (RRP, T10Y2Y, WALCL) | fredgraph.csv | Timeout desde este host hoy, pero `fetch_fred()` del repo ya funciona (ola 1) | Diario |
| AAII | ya integrado (V1, blend 0.50) | ✅ Cache al 2026-08-27 | Semanal |
| COT CFTC | ya integrado (ola 1) | ✅ 2019-2026 en parquets | Semanal (lag 3d) |
| ICI flujos | 403 a bots | ❌ Descartado | — |
| CBOE directo | 200 HTML pero data via JS; CSVs 2019+ 403 | ❌ (resuelto vía CNN) | — |

**Valores de HOY (2026-09-11, smoke real del termómetro)**: F&G **32.2 "fear"** ·
put/call **0.74 (extreme fear)** · VIX 17.8 · GDELT tone +0.17 — día de miedo medido,
contexto perfecto para la hipótesis que sigue.

## 2. Termómetro — implementado (solo lectura, sin tocar motor)

- **`backend/app/core/thermometer.py`**: `fetch_fear_greed()` (CNN: fg_score, put_call_ratio,
  vix — cache parquet, TTL 6h, acumulación de historia por append+dedup),
  `fetch_gdelt_tone()` (backoff 2s/8s/30s, 429 = falla blanda), `build_thermometer_frame()`
  (alineación anti-lookahead shift(1)+ffill, mismo contrato que `build_sentiment_frame`).
- **`GET /api/advisor/thermometer`**: current + history 180d + meta con staleness_warnings.
  Falla blanda total — nunca 500 por fuente caída.
- **Tests**: 15 nuevos (test_thermometer.py) + 25 advisor + 6 market_sentiment = **46 passed**, ruff limpio.
- Descubrimiento: GDELT timelinevolinfo trae "Volume Intensity", no tone puro — la serie
  usada queda auditada en `series_used` (no mezcla escalas si cambia).

## 3. Hipótesis del ciclo institucional — EVALUADA (pre-registro, medición en cache de producción)

**Tu hipótesis operacionalizada**: (A) caída ≥15% a piso → (B) alza LENTA 8-13% en ≥20
ruedas con vol menor que la caída → (C) retest ≥5% sin romper piso → (D) markup.
**Pregunta**: ¿después del ambiente de venta, con pesimismo persistente, viene el alza
lenta institucional? **Universo**: ~130 activos (cache producción), 2021-09 → 2026-09, **392 eventos limpios**
(filtro de contaminación |fwd|<100%).

### 3.1 El patrón EXISTE y la narrativa se confirma como descripción

El algoritmo detecta eventos donde la recuperación (Fase B) es **más tranquila que la caída** (vol B < vol A).
Con datos de producción (split-ajustados, dividendo-reinvertidos), el SPY 2022 **no califica** porque
su rally oct-nov 2022 fue MÁS volátil que la caída previa (vol_b > vol_a). El único evento SPY que
cumple el patrón completo en 2021-2026 es **2026-02-23** (reciente, sin fwd60 completo).

Sin embargo, el patrón SÍ aparece en otros activos y regímenes. Ejemplo destacado **SCHW 2022-09-02**
(STAGFLATION):
- Piso 66.49 (−25.8%), Fase B +8.4% en 21d, retest confirmado sin romper piso
- AAII en piso −14.7, en retest −40.9 (pesimismo extremo persistente)
- COT: asset managers +213k, leverage −295k, retail −83k
- fwd60 desde retest: **+19.2%**, fwd180 +9.4%, pendiente fase D 4.5 bp/d, Sharpe 0.37

Agregado (128 retests): en el retest, asset managers netos **+682k** vs leverage **−291k**
— la firma institucional (compran en pesimismo) se mantiene.

### 3.2 Como SEÑAL de timing — el retest NO agrega valor en general, PERO depende del régimen

| Régimen | Retests (n) | fwd60 retest | win% | Control (n) | fwd60 control | win% | ¿Retest mejora? |
|---|---|---|---|---|---|---|---|
| **GOLDILOCKS** | 48 | **+3.7%** | 48% | 66 | **+6.8%** | 67% | **NO** (peor) |
| **STAGFLATION** | 80 | **+7.3%** | 60% | 196 | **+2.6%** | 58% | **SÍ** (mejor) |

En **STAGFLATION** (entorno de estanflación, el régimen más común en 2022), el retest **SÍ agrega valor**:
fwd60 +7.3% vs +2.6% control. En **GOLDILOCKS** (crecimiento + desinflación), el retest es peor que el simple
piso+bote. REFLATION y DEFLATION tienen muy pocos retests en la muestra.

**Conclusión**: la narrativa "piso → alza lenta → retest → markup" **describe un fenómeno real** (confirmado por COT
y AAII), pero como **disparador de timing** solo tiene edge en régimen STAGFLATION. Fuera de ese régimen,
el piso+bote ya contiene la información.

### 3.3 Lo que SÍ quedó como señal viva

- **AAII en el piso** (mean −8.3 en retests, 65% eventos pesimistas): el "ambiente de venta"
  coincide con pesimismo medido — el termómetro puede marcar "piso con miedo" como
  contexto del advisor (etiqueta, no señal de motor).
- **COT asset managers acumulando en el piso**: la firma institucional es medible
  semanalmente y ya está en el panel de datos.
- **Calidad de fase D**: pendiente media 16-40 bp/día (alza lenta real), recuperación
  del pre-piso en mediana 74-82 días — números útiles para EXPECTATIVAS cuando el
  patrón se detecta en régimen STAGFLATION, no para disparar entradas.
- **Régimen como filtro**: solo en STAGFLATION el retest mejora el fwd60 vs control.

## 4. Correcciones vs versión anterior (2026-09-11 primera corrida)

| Qué | Versión anterior (sandbox cache) | Versión corregida (cache producción) | Causa |
|---|---|---|---|
| **Fuente de precios** | `/tmp/opencode/sandbox/data/cache/` (copia con convención distinta) | `/Users/boris/Desktop/fortress_core/backend/data/cache/` (cache real del motor) | El sandbox tenía precios pre-split/ajuste-dividendos diferente → returns diarios no idénticos (corr 0.925, ratio variable 0.57-0.63) |
| **Eventos SPY 2022** | Detectado piso 188.46 (nov-09), DD −17% | **No califica** — rally oct-nov 2022 tuvo vol_b > vol_a (falla condición "alza lenta") | La condición `vol_b < vol_a` rechaza rallies volátiles; 2022 SPY fue bear market rally ruidoso |
| **Eventos totales** | 421 | **392** | Diferente universo + diferente condición de vol sobre mismos datos |
| **STAGFLATION retest vs control** | Retest +1.4% vs Control +2.8% (retest PEOR) | **Retest +7.3% vs Control +2.6% (retest MEJOR)** | La fuente de precios cambió qué eventos califican y sus regímenes asignados |
| **SPY caso canónico** | 2022-11-09 (piso 188.46) | **No hay caso canónico 2022**; ejemplo representativo: SCHW 2022-09-02 | El algoritmo busca recuperaciones TRANQUILAS, no cualquier rally |

**Lección**: los % de drawdown/rally/retest **solo son comparables dentro de la misma convención de precios**.
El cache de producción es el único válido para decisiones que alimenten al motor.

## 5. Reglas respetadas

- Mediciones descriptivas pre-registradas (protocolo al inicio del script) — NO son
  validación de señal de motor: no entran al motor ni consumen N_TRIALS sin fase de
  IC walk-forward + pre-registro (doctrina §§21-28: AAII-timing y rank-IC ya murieron
  en ese camino).
- Sin tocar código de producción del motor: thermometer.py + endpoint + tests son solo
  lectura. Scripts de medición en `/tmp/opencode/` (ahora contra cache de producción).
- Evento contaminado de AKAM (+504% falso) filtrado por el sanity |fwd|<100%.

## 6. Archivos

| Archivo | Qué es |
|---|---|
| `backend/app/core/thermometer.py` | Fetchers CNN+GDELT con cache/TTL/falla blanda (NUEVO) |
| `backend/app/api/routes/advisor.py` | +endpoint `/thermometer` (solo lectura) |
| `backend/tests/test_thermometer.py` | 15 tests (NUEVO) |
| `/tmp/opencode/ciclo_boris_v2.py`, `ciclo_deep_v2.py` | Scripts de medición v2 (contra cache producción) |
| `/tmp/opencode/ciclo_result_v2.json`, `ciclo_deep_v2.json` | Eventos + agregados v2 |
| `data/cache/thermometer_cnn.parquet`, `thermometer_gdelt.parquet` | Cache del termómetro (gitignored) |

**Sin commit** — Kilo verifica y decide. Próximo paso natural: el panel del
termómetro en el frontend (mesa advisor) con el badge de "piso con miedo" cuando
AAII<−15 y precio a >15% del máx 252d, **condicionado a régimen STAGFLATION** si se quiere edge de timing.