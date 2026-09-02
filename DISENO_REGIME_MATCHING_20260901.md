# Diseño — REGIME-MATCHING: emparejamiento de régimen histórico para predicción per-ticker

**Fecha:** 2026-09-01 · **Autor:** Cline (worktree `fundamentales-automatizado`)
**Estado:** DISEÑO — NO es pre-registro, NO se ejecuta, NO consume ledger, NO integra al motor,
NO toca el piloto de Kilo (worktree `test-kilo-orca`). Este documento especifica la arquitectura
para que Boris decida si se implementa y, en su momento, qué celdas gradúan a pre-registro
(`PRE_REGISTRO_REGIME_MATCHING_<n>.md`, familia `signal_diagnosis`).

**Mandato:** *"NVDA momentum decae GRADUALMENTE (10y continuación → 7y/5y se aplana → 2y se
invierte), no de golpe. En vez de buscar una regla universal o promediar toda la historia,
identificar a qué PERIODO HISTÓRICO se parece más el régimen actual de cada ticker, y usar el
comportamiento medido en ESE periodo análogo — adaptación, no Santo Grial."*

---

## 0. Evidencia que sostiene la propuesta (verificada hoy)

### 0.1 El decaimiento gradual de NVDA momentum es HECHO, no hipótesis

El piloto de Kilo (worktree `test-kilo-orca`, `INGENIERIA_INVERSA_POR_TICKER.md` §5, §8) midió
el comportamiento de `momentum_12_1` para NVDA en 4 ventanas anidadas:

| Ventana | low (tercil inf) | mid | high (tercil sup) | Signo del spread |
|---|---|---|---|---|
| 2y (2024-08→2026-08) | +20.10% | +8.83% | **−3.89%** | **REVERSIÓN** |
| 5y (2021-09→2026-08) | +4.76% | (medido) | **−20.86%** | REVERSIÓN fuerte |
| 7y (2019-09→2026-08) | (medido) | (medido) | (medido) | aplanado |
| 10y (2016-09→2026-08) | +4.09% | +4.11% | **+6.58%** | **CONTINUACIÓN** |

La transición **continuación → aplanado → reversión** en 2-7-10 años no es ni binaria ni
monótona — es gradual y depende del periodo. Promediar las 4 ventanas enmascara el régimen
presente: si hoy NVDA momentum tiene un spread positivo porque está promediado con la era
2020-2021, ese promedio NO informa sobre lo que va a pasar en los próximos 20 días.

### 0.2 El clasificador HMM ya existe — no inventar otro régimen

`backend/app/core/regime_classifier.py:GlobalRegimeClassifier` ya define 4 estados semánticos
alineados (GOLDILOCKS / REFLATION / STAGFLATION / DEFLATION) sobre features cross-asset
(growth SPY/EFA/QQQ, inflation GLD/DBC/TIP, rates TLT/AGG, VIX level). La función
`predict_regime_series_causal` (líneas 138-160) decodifica Viterbi día por día sin leakage,
y `WalkForwardRegimeGate` (`regime_gate.py:61`) ya la envuelve con recalibración cada 63d
hábiles y `min_history=756d`. **No re-entreno HMM, no re-defino estados**: reuso la serie
de régimen causal ya producida por esta infraestructura, que es la misma que ya consume
M3 en producción.

### 0.3 El ATLAS v1 ya tiene el esqueleto de la "ficha por ticker"

`backend/scripts/atlas_ticker.py` (commit `0f2c798`) produce `fichas/<TICKER>.md` con la
curva de respuesta por indicador × horizonte × contexto. La capa 1 ya mide el comportamiento
forward del propio ticker en cada celda. **La pieza que falta es: dado un ticker + fecha
actual, ¿en qué ventana histórica ESE ticker se comportó más parecido al régimen actual?**
Eso es lo que este diseño agrega.

### 0.4 Lección de las refutaciones del repo (no re-caer)

- **Trial #22 PBO**: la lección NO es "no escanear muchas celdas" — es "no elegir la celda
  que mejor se ve post-hoc". REGIME-MATCHING hace lo contrario: la métrica de similitud se
  declara ANTES de mirar curvas; el "período análogo" es output de un algoritmo, no de la
  intuición.
- **Asimetría direccional §0.4 (refutados)**: el proyecto ya midió y refutó Δ_f pooled,
  RMT, Hurst signal, vol-regime signal. REGIME-MATCHING no re-propone nada de esa lista —
  usa el régimen HMM como **etiqueta contextual** (cualitativa), no como factor predictivo.
- **Reglas no negociables #1/#2 de ONBOARDING.md**: nada de pre-registro sin pre-registro.
  REGIME-MATCHING v1 (este diseño) es diagnóstico, sin ledger; la graduación a regla es
  pre-registro nuevo con Bonferroni por el conteo real de matches.

### 0.5 Lo que NO se observó pero se asume (declarar para refutar después)

- Se asume que la métrica de similitud entre regímenes (a definir en §4) es estable a lo
  largo del tiempo. Esto es FALSO por construcción (todo en finanzas tiene drift), pero la
  pregunta es **la magnitud del drift** — eso lo medimos en la capa 1, no lo asumimos.
- Se asume que el comportamiento forward del periodo análogo es informativo del futuro. Eso
  es la HIPÓTESIS de la capa 2 (graduación), NO un hecho de la capa 1. La capa 1
  describe; la capa 2 pre-registra; la confirmación es OOS fresca (regla del repo).

---

## 1. Concepto: del promedio histórico al "período análogo"

### 1.1 Lo que el ATLAS v1 hace y por qué es insuficiente

El atlas recorre CADA celda `(ticker, indicador, ventana, horizonte)` de forma
**independiente** y reporta una curva de respuesta. Para un mismo ticker, el "comportamiento
forward" del indicador queda promediado a través de contextos que el ticker realmente vivió.
Si el ticker cambió de régimen y la historia tiene un peso mayor del régimen pasado, el
promedio es sesgado hacia el pasado.

Ejemplo concreto con NVDA momentum h=20: el atlas TOTAL reporta spread Q5−Q1 = +306bp
(continuista). Pero el piloto Kilo para 2y (2024-08→2026-08) reporta spread high−low
= **−2.4pp** (reversionista). Esos dos números describen el mismo par (ticker, indicador,
horizonte) en universos DISTINTOS, no se contradicen — pero el "TOTAL" promedia ambos
y oculta la transición.

### 1.2 La idea: condicionar el comportamiento a la similitud de régimen

En vez de promediar toda la historia, para una fecha `t` y un ticker `i`:

1. **Caracterizar el régimen actual de `i` en `t`** con un vector de features observables
   a `t` (mismo set que el HMM global, + features per-ticker que el HMM no mira).
2. **Comparar ese vector contra TODOS los regímenes históricos** del propio `i`, slide
   por una ventana móvil (default 63d, mismo default que `regime_gate.py:37`).
3. **Recuperar los K períodos más similares** (default K=5, parámetro declarado) — estos
   son los "períodos análogos".
4. **Calcular la curva de respuesta de la celda SOLO sobre los días que caen dentro de los
   períodos análogos identificados.** Eso es la "ficha adaptada al régimen actual".

Lo que cambia respecto al atlas v1: la celda ya no se mide en `W1/W2/W3/TOTAL` (ventanas
calendario fijas), sino en un **slice temporal definido por similitud de régimen**. Sigue
siendo la misma celda `(ticker, indicador, horizonte)` — cambia la ventana de medición.

### 1.3 Lo que NO es este diseño

- **NO es pattern matching de velas** (no busca secuencias de OHLCV) — busca regímenes,
  definidos por features agregadas.
- **NO es k-Nearest Neighbors en espacio de retornos** — el espacio es el de features del
  HMM + features per-ticker, NO el espacio de retornos (eso sería predictivo y tiene
  overfitting trivial).
- **NO es backtesting con look-ahead** — el régimen actual usa solo datos `≤ t`; los
  períodos análogos históricos se buscan en el pasado de `i`; la curva de respuesta se
  calcula sobre días históricos del propio `i`, no sobre datos futuros.
- **NO es "el período más similar es el futuro"** — es "el comportamiento del propio
  ticker cuando su régimen era más parecido al actual es la mejor evidencia disponible
  sobre lo que podría pasar ahora". Esa evidencia puede ser nula (match bajo) o ruidosa
  (N chica); se reporta con la misma honestidad que el atlas.

---

## 2. Arquitectura de dos capas (mismo patrón que ATLAS v1)

```
┌─────────────────────────────────────────────────────────────────────┐
│  CAPA 1 — REGIME-MATCHING (descriptivo, sin ledger)                 │
│  Input: cache parquet (sin red) + serie régimen HMM (offline).      │
│  Output: ficha adaptada al régimen actual por ticker, + rankings.  │
│  Doctrina: "construir es libre y rápido".                           │
│  Prohibido: afirmar que "va a pasar X porque pasó en análogos".     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ match candidato (Boris elige)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAPA 2 — GRADUACIÓN (confirmatoria)                                │
│  Pre-registro individual con:                                       │
│  - la métrica de similitud declarada (no optimizable)               │
│  - el threshold de similitud (K-ésimo match o distancia)           │
│  - el horizonte de predicción                                       │
│  - el éxito pre-fijado (≥2/3 ventanas, Sharpe > X, o lo que sea)   │
│  - Bonferroni por el conteo REAL de matches evaluados              │
│  Confirmación OOS fresca o walk-forward.                            │
└─────────────────────────────────────────────────────────────────────┘
```

**Por qué dos capas:** REGIME-MATCHING va a probar N_matches × N_tickers × N_indicadores ×
N_horizontes matches. Si el scan es 50 × 3 × 3 × 5 = 2.250 matches potenciales, y Boris
elige "los más similares" a mano, está haciendo exactamente lo que PBO #22 marcó. La
capa 1 describe con honestidad la distribución de similitud Y de curvas de respuesta
adaptadas; la capa 2 es la única vía a regla, con Bonferroni por el conteo real.

---

## 3. Unidad de análisis: el match (con su ficha adaptada)

**Match = (ticker, fecha_objetivo, indicador, horizonte, período_análogo_id).** Es
auto-descripto: `[NVDA, 2026-08-31, rsi14, h=20, análogo_3]` se lee "para NVDA al 2026-08-31,
el comportamiento forward esperado de RSI-14 sobre 20 días, estimado con la curva de
respuesta del período análogo #3 que más se parece al régimen actual".

**Ficha del match = la curva de respuesta adaptada.** Misma estructura que la ficha del
atlas (quintiles del percentil propio → media de retorno forward), pero calculada SOLO
sobre los días del período análogo, no sobre toda la ventana calendario.

**Resumen numérico del match (6+3 números, siempre reportados):**

| Métrica | Definición | Para qué |
|---|---|---|
| IC adaptado | Spearman(quintil, ret_fwd) sobre días del análogo | fuerza y signo en el periodo relevante |
| Spread Q5−Q1 bp | ret_fwd(Q5)−ret_fwd(Q1) | magnitud accionable |
| Monotonicidad | pares adyacentes correctamente ordenados | ¿curva o salto? |
| N bruto | días en el análogo | cobertura |
| N efectivo | N/h | honestidad |
| **Distancia al régimen actual** | la métrica de similitud del §4 | transparencia |
| **N análogos usados** | K declarado | scope |
| **% del total disponible** | N_análogo / N_total | cuánto del pasado "cuenta" |
| Flags | INSUFICIENTE/DEGENERADO/CIRCULAR | validez |

---

## 4. Definiciones operacionales (fijas a priori, anti-fishing)

### 4.1 Features del régimen (POR TICKER, no cross-asset)

A diferencia del HMM global (que mira SPY/QQQ/GLD/TLT/VIX), REGIME-MATCHING mira el
propio ticker — porque el mandato es "el comportamiento de ESE ticker", no del mercado.
Para el ticker `i` en fecha `t`, el vector de features es:

```
F(i, t) = [
    ret_63d(i, t-1)         # tendencia del propio ticker (63d, §4.1 ATLAS)
    vol20_pctil(i, t-1)     # posición del ticker en su propia historia de vol
    rsi14(i, t-1)           # estado RSI propio
    momentum_12_1_pctil(i, t-1)  # posición del momentum propio
    hmm_regime_id(i, t-1)   # etiqueta HMM global vigente (4 valores: 0..3)
    spy_ret_63d(t-1)        # beta con el mercado de los últimos 63d (una sola feature)
]
```

**Por qué estas 5+1 y no otras:** las 4 primeras son EL estado del propio ticker, y la 5
trae el contexto macro del HMM sin reentrenarlo. `spy_ret_63d` es la única feature exógena
— un proxy mínimo de "qué está haciendo el mercado". **Prohibido en v1:** añadir features
dentro del loop (cualquier nueva = pre-registro aparte).

**Crítico:** todas las features usan `t-1` (`shift(1)`), igual que el atlas. Cero look-ahead.

### 4.2 Ventana del régimen actual

El "régimen actual" del ticker `i` en `t` se caracteriza por el vector de features
calculado sobre los últimos `W_reg` días (default 63d hábiles, parámetro declarado). Es
el mismo default que el HMM global usa para extraer features. W_reg ≠ H es lo que permite
caracterizar el régimen sin confundirlo con el outcome.

### 4.3 Métrica de similitud entre dos regímenes

Para dos vectores `F_a` y `F_b` del ticker `i`, la similitud es:

```
sim(F_a, F_b) = w_t · |ret63_a − ret63_b|/σ_ret63(i)
              + w_v · |volpct_a − volpct_b|/σ_volpct(i)
              + w_r · |rsi_a − rsi_b|/σ_rsi(i)
              + w_m · |mompct_a − mompct_b|/σ_mompct(i)
              + w_h · 1{hmm_a ≠ hmm_b}                    # Hamming si régimen HMM difiere
              + w_s · |spy_a − spy_b|/σ_spy(i)
```

Donde `σ_x(i)` es la std histórica del ticker `i` para la feature `x` (normalización
per-ticker; misma lógica que "percentil propio" del atlas — hace comparables tickers
con escalas distintas).

**Pesos `w_*` (default, declarados):** w_t=0.25, w_v=0.15, w_r=0.15, w_m=0.25, w_h=0.15,
w_s=0.05. Suman 1.0. Pesos son declarados a priori — un cambio de pesos es un
pre-registro aparte. La elección "0.25/0.25 en momentum y tendencia" refleja la intuición
mínima de que la dirección del precio (momentum + tendencia) domina; el resto modula.

**Distancia final = similitud** (menor = más similar). El "período análogo" es el de
menor distancia, dentro de la ventana de búsqueda.

### 4.4 Ventana de búsqueda (de períodos históricos)

Para el ticker `i` y la fecha objetivo `t`, la búsqueda de análogos recorre la historia
del propio `i` desde la primera fecha con datos suficientes (`max(W_reg, 252d)`) hasta
`t - 1` (excluyendo `t` para no leakage — el "hoy" no se cuenta como análogo de sí mismo).

**Stride:** el set de candidatos es la secuencia de fechas `t - 63d, t - 126d, t - 189d, ...`
hacia atrás (paso 63d = `W_reg`). Eso da ~N_history / 63 candidatos por ticker. Para NVDA
2015→2026 son ~28 candidatos. Suficiente para ranking top-K, no para cobertura estadística
— eso es honesto, se reporta en la ficha.

**Exclusión:** NO se considera análogo un período que solape con `t..t+h` (no se mide
forward return sobre datos futuros al target). Esa es la línea de leakage del atlas,
idéntica.

### 4.5 K (top-K análogos)

Default: K=5. Parametro declarado. Variantes (K=3, K=10): pre-registro aparte.

La curva de respuesta adaptada se calcula sobre la **unión** de los K análogos, no sobre
cada uno por separado. Eso da N más robusto y evita el overfitting de tomar el "análogo
perfecto" (que es ruido de cola).

**Disclaimer que va en cada ficha:** el K=5 análogos NO son una muestra i.i.d. — están
seleccionados por similitud. La N efectiva es aún menor que N/h; se reporta y se trata
como una cota pesimista.

### 4.6 Indicadores y horizontes (mismo set que ATLAS v1)

Sin variantes. `momentum_12_1`, `rsi14`, `vol20`, h ∈ {5, 20, 60}. Razón: la ingeniería
inversa debe hablar el mismo idioma que el atlas. Una nueva variante rompe la
comparabilidad entre la celda cruda y la celda adaptada.

---

## 5. Medición por match (§5.4 del atlas aplica igual)

### 5.1 Cálculo del match (procedimiento determinístico)

Para el match `(i, t_obj, ind, h)`:

1. Calcular `F(i, t_obj)` con features `≤ t_obj`.
2. Calcular `F(i, t)` para todos los `t` en la ventana de búsqueda, respetando la
   exclusión §4.4.
3. Ordenar por `sim(F(i, t_obj), F(i, t))` ascendente.
4. Tomar los K mejores = `T_top = {t_1, ..., t_K}`.
5. Construir el set de días del análogo: `D_análogo = ⋃_{k=1..K} [t_k, t_k + W_reg)`.
6. Para cada `d ∈ D_análogo`, calcular `x_d = percentil propio del ind en d-1` y
   `y_d = close[d+h]/close[d] - 1` (misma convención que atlas §4.4).
7. Quintiles sobre `x_d` dentro de `D_análogo` → curva de respuesta adaptada.

### 5.2 Estadística (la lección de la asimetría §0.5a)

- IC diario sobre la serie adaptada con Newey-West L=h (mismo estimador que el repo).
- **Reporte obligatorio**: N bruto, N efectivo = N/h, y además la **fracción de la historia
  usada** (N_análogo / N_total). El t NO se reporta solo — siempre con su N.
- Si K=5 da N_análogo muy chico (e.g. < 30), el flag INSUFICIENTE se activa y la celda
  se reporta como tal, jamás "cuenta como cero".

### 5.3 Gates de validez (mismos que atlas §5.3, copiados literal)

1. **Cobertura:** N_análogo < 30 → INSUFICIENTE.
2. **Degeneración:** std del indicador ≈ 0 dentro del análogo.
3. **Datos:** si la ventana de búsqueda del ticker es < 252d hábiles, no se corre match
   para ese ticker.
4. **Match trivial:** si el mejor match es el propio `t_obj - W_reg` (trivialidad de
   vecindad), se reporta pero con flag `TRIVIAL_MATCH` — no se filtra porque a veces
   el match trivial es el régimen actual extendiéndose.

### 5.4 Factibilidad a priori (declarada antes de medir)

Con ~2.500 días de historia por ticker y stride 63d, hay ~40 candidatos por ticker.
Top-K=5 → ~10-15% de la historia disponible, ~250-500 días calendario, ~5-10 días hábiles
por análogo (5 análogos × 63d cada uno) → N_análogo típico ~250-500 días hábiles.

| Match | N_tipico | N_ef (h=20) | Veredicto factibilidad |
|---|---|---|---|
| `NVDA momentum h=20` | 250-500 | 12-25 | ✅ |
| `KO rsi14 h=5` | 250-500 | 50-100 | ✅ |
| `EPAM vol20 h=60` | 100-200 (historia corta) | 2-3 | ⚠️ INSUFICIENTE probable |

**Regla derivada:** matches con `N_min_history` insuficiente (EPAM, QLYS, tickers < 5 años
de historia en cache) se reportan con flag `INSUFICIENTE_HISTORY` y se excluyen de la
capa 2 por defecto. Si Boris quiere incluirlos, pre-registro aparte.

### 5.5 Escala del scan (declarada, alimenta deflactación §7)

```
50 tickers × 3 indicadores × 3 horizontes × 1 fecha_objetivo
= 450 matches por fecha_objetivo

(la fecha_objetivo se elige: la última fecha con datos del cache — para
  v1, UN solo punto. Walk-forward multi-fecha es pre-registro aparte.)
```

Con K=5 análogos por match, cada match abre 5 ventanas de W_reg=63d → 5×63d = 315d
útiles. La deflactación Bonferroni de §7 usa 450 como multiplicador base (más las
variaciones de W_reg y K que Boris pueda pedir después).

---

## 6. Taxonomía de "calidad del match" (lo que convierte matches en mapa legible)

Para CADA match se reporta un score de **cobertura del match**, no un veredicto
predictivo. Es análogo a los arquetipos del atlas pero NO sobre el resultado forward
(eso sería el veredicto que la capa 2 emite con pre-registro).

| Calidad | Regla (pre-especificada) | Lectura |
|---|---|---|
| **FUERTE** | K=5 análogos, N_análogo ≥ 250, sim_top ≤ p25 de la distribución histórica de similitud | el régimen actual tiene análogos bien definidos y muestra pasada suficiente |
| **DÉBIL** | 1 ≤ K efectivo < 5 (varios análogos solapan o son muy cercanos), N_análogo entre 100 y 250 | el régimen actual es raro en la propia historia, análogos disponibles pero menos robustos |
| **INSUFICIENTE** | N_análogo < 100 o N_min_history insuficiente o match trivial | el ticker no tiene historia comparable — la ficha adaptada NO se reporta, se reporta el INSUFICIENTE |

**Métrica de similitud explícita:** la distancia euclidiana ponderada normalizada
del §4.3, en unidades de σ. La ficha del match muestra, además, la distribución de
similitud histórica del propio ticker (percentiles 25/50/75 de la distancia) para que
el "FUERTE" sea interpretable — un match "FUERTE" con sim_top=p10 es mucho más fuerte
que uno con sim_top=p24.

**Prohibido en v1:** hacer optimización sobre los pesos `w_*` para maximizar cobertura.
Si una elección de pesos da más matches "FUERTE" para el set actual, no es evidencia de
nada — es ajuste post-hoc. La cobertura se reporta, no se optimiza.

---

## 7. Capa 2 — Graduación: cómo un match se vuelve regla (y solo así)

1. **Disparador:** Boris (o el agente con su aprobación) elige matches candidatos desde
   el ranking de calidad. REGIME-MATCHING NO auto-gradúa nada.
2. **Pre-registro individual** (`PRE_REGISTRO_REGIME_MATCHING_<n>.md`): antes de re-testear,
   declara el match exacto, los pesos `w_*` (fijos por diseño, pero hay que citarlos), el
   K (5 por defecto), la definición de "FUERTE/DÉBIL" (la del §6), el **threshold de éxito
   (≥2/3 ventanas OOS, estándar del repo)** y la **deflactación Bonferroni por el conteo
   real de matches evaluados** (~450 por fecha_objetivo).
3. **Test de confirmación:** OOS fresca sobre fechas POSTERIORES a la fecha_objetivo
   declarada (no se re-testea sobre los mismos días del match — eso sería leer dos veces
   lo mismo, igual que el atlas §7).
4. **Ledger:** familia `signal_diagnosis`, slot secuencial al momento de registrar.
5. **Si CUMPLE:** existe una hipótesis per-ticker del tipo "cuando el régimen de KO se
   parece al actual, su momentum_12_1 h=20 sigue con spread +Xbp". Integrar al motor
   requiere SU PROPIO trial `motor_signal` con DSR ≥ 0.90 — dos puertas, no una.

**Anti-conflictos con otras piezas del repo:**
- `predict_regime_series_causal` ya está validado como anti-leakage. REGIME-MATCHING lo
  consume sin modificarlo.
- `WalkForwardRegimeGate` recalibra HMM cada 63d. REGIME-MATCHING no recalibra nada
  (lee la serie vigente, no la produce).
- ATLAS v1 describe curvas por ventana calendario fija. REGIME-MATCHING describe curvas
  por ventana de régimen-similar. **No compiten**: la ficha del match es complementaria
  a la ficha del atlas, no la reemplaza.

---

## 8. Entregables concretos del pipeline (implementación futura, tras aprobación)

| Artefacto | Contenido |
|---|---|
| `backend/scripts/regime_matching.py` | Motor: lee cache parquet + serie HMM offline, no toca el motor. Salida: los 4 artefactos. Runtime estimado: minutos sobre 50 tickers. |
| `backend/data/cache/regime_match_<ts>/matches.csv` | Tabla: ticker × indicador × horizonte × match_id × distancia × N × IC adaptado × spread bp × flags × calidad. |
| `backend/data/cache/regime_match_<ts>/matches/<TICKER>_<ts>.md` | Ficha humana del match: top-5 análogos listados con sus fechas, la curva de respuesta adaptada, y el disclaimer. |
| `backend/data/cache/regime_match_<ts>/resumen_calidad.md` | Mapa cross-ticker: cuántos matches FUERTE / DÉBIL / INSUFICIENTE hay por ticker × indicador. |
| `backend/tests/test_regime_matching.py` | Tests: (1) sin look-ahead — el match en t usa solo datos ≤ t; (2) gates de cobertura marcando INSUFICIENTE; (3) métrica de similitud es simétrica y normalizada per-ticker; (4) idempotencia; (5) K=5 declarado se respeta (no se "elige" otro K post-hoc). |

**Alcance v1 explícito:** universo 50 canónico, 3 indicadores, 3 horizontes, **una sola
fecha_objetivo** (la última del cache, ~2026-08-31), K=5, W_reg=63d, pesos w_* fijos del
§4.3. Walk-forward multi-fecha y variación de K/w_* son pre-registros aparte. Sin
interfaces al motor, sin endpoints, sin frontend. Es una herramienta de diagnóstico
para Boris y los agentes — mismo patrón que el atlas v1.

---

## 9. Relación con lo existente (fronteras claras)

- **Con el HMM global (`regime_classifier.py`):** reuso la serie de régimen causal
  (`predict_regime_series_causal`) y la asignación de 4 estados. NO reentreno. NO
  redefino estados. NO compito con M3 (`regime_gate.py`); M3 decide si OPERAR; este
  diseño decide QUÉ LEER del pasado cuando se está operando.
- **Con `WalkForwardRegimeGate`:** el gate es infraestructura de la operación (abstenerse
  en régimen desfavorable); REGIME-MATCHING es diagnóstico del pasado. La salida de M3
  podría usarse como FILTRO opcional sobre las fechas de los análogos (excluir
  análogos en régimen desfavorable si Boris quiere), pero por defecto v1 los incluye
  todos.
- **Con ATLAS v1 (`atlas_ticker.py`):** complementarios, no redundantes. El atlas mide
  curvas por ventana calendario fija; REGIME-MATCHING mide curvas por ventana de
  similitud de régimen. **Comparación futura útil:** ficha del atlas "TOTAL" vs ficha
  del match "FUERTE" para el mismo ticker — la diferencia entre ambas es el "premio
  por condicionar al régimen actual". Si el premio es pequeño, el atlas TOTAL ya
  alcanzaba; si es grande, REGIME-MATCHING agrega valor.
- **Con la asimetría direccional (diseño 30/08):** complementaria. La asimetría pregunta
  "¿los FACTORES del motor condicionan distinto bajo impulso de alza vs baja?". REGIME-
  MATCHING pregunta "¿el COMPORTAMIENTO per-ticker es invariante al régimen?". Las
  dos usan features distintas y atienden preguntas distintas.
- **Con el piloto de Kilo:** si el piloto midió "NVDA momentum 2y reversionista",
  REGIME-MATCHING en fecha_objetivo=2026-08-31 debería encontrar como análogo
  precisamente esa ventana 2y. **Esa es la validación cruzada natural**: que el match
  top-1 (o top-K) para NVDA momentum h=20 al 2026-08-31 sea la ventana 2024-08→2026-08.
  Si NO es así, hay un bug en alguno de los dos. Si SÍ es así, evidencia independiente
  de que la métrica de similitud captura lo que el piloto midió manualmente.
- **Con los refutados (PBO #22, RMT, Hurst signal, etc.):** REGIME-MATCHING no re-propone
  nada de esa tabla. NO busca "el match perfecto" — busca "el match más similar según
  la métrica declarada".

---

## 10. Riesgos específicos (declarados, no son "fallas esperadas" — son a vigilar)

1. **Selección espuria del K=5.** Si el K óptimo fuera 1 o 20, el top-5 declarado
   enmascara la sensibilidad. Mitigante: la ficha del match muestra el top-K con su
   similitud explícita, y el resumen_calidad reporta la cobertura por calidad — Boris
   puede pedir "top-3" o "top-10" como variante pre-registrada.
2. **Sobre-ingeniería de features.** El set §4.1 tiene 5+1 features, pero cada una
   puede tener drift. Mitigante: la distribución de similitud histórica por ticker
   reporta la std — un ticker con std 5× la mediana indica features que cambian mucho.
3. **HMM y per-ticker se contradicen.** El HMM global etiqueta el régimen macro; el
   régimen per-ticker (vía features §4.1) puede ser distinto — un KO en REFLATION
   puede tener features de tendencia neutral. Mitigante: se reportan AMBOS; la
   similitud usa los dos (HMM y per-ticker) explícitamente.
4. **El "período análogo" es trivialmente el más reciente.** Si la similitud está
   dominada por features de drift lento, todos los matches serán los últimos 252d.
   Mitigante: la métrica incluye `hmm_regime_id` (cambia rápido) y pesos en features
   per-ticker (no en tiempo).
5. **N_análogo demasiado chico para conclusión.** Si los 5 análogos están concentrados
   en un periodo corto (e.g. todo el COVID), el N_análogo se infla pero la
   independencia se rompe. Mitigante: la ficha del match muestra las fechas de los K
   análogos para inspección visual; el flag `ANÁLOGOS_CONCENTRADOS` se activa si la
   std de las fechas < 252d.

---

## 11. Decisión solicitada a Boris (la única pregunta)

¿Aprobás la implementación de la **CAPA 1** (descriptiva, sin ledger, sin veredicto) del
sistema REGIME-MATCHING según el §8, con el alcance v1 explícito?

Si aprobás → tarea separada: implementar `regime_matching.py` + 5 tests + corrida de
referencia. La CAPA 2 (graduación) queda en pausa hasta que el scan descriptivo produzca
candidatos concretos y Boris elija uno(s) para pre-registrar.

Si rechazás → alternativa: ¿qué pieza del diseño querés cambiar? Los pesos `w_*` del
§4.3, el K del §4.5, el set de features del §4.1, la fecha_objetivo única, o algo más
estructural. Ningún componente de la propuesta está casado con su implementación —
todo es paramétrico y reemplazable, igual que ATLAS v1.
