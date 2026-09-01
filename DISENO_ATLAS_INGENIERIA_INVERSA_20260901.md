# Diseño — ATLAS: sistema de ingeniería inversa precio→indicador por ticker

**Fecha:** 2026-09-01 · **Autor:** Cline (worktree `fundamentales-automatizado`)
**Estado:** DISEÑO — NO es pre-registro, NO se ejecuta, NO consume ledger, NO integra nada,
NO toca el piloto de Kilo (worktree `test-kilo-orca`). Este documento especifica la
arquitectura para que Boris decida si se implementa y, en su momento, qué celdas
gradúan a pre-registro (`PRE_REGISTRO_*.md`, familia `signal_diagnosis`).
**Mandato:** "un SISTEMA sistemático de ingeniería inversa precio-indicador por ticker
(no un análisis puntual, sino la metodología/arquitectura reutilizable para hacer esto
de forma repetible sobre cualquier ticker del universo) — por ticker, por ventana de
tiempo (que capturen CONTEXTOS/regímenes distintos, no potencia estadística), por
horizonte de retorno (corto vs largo plazo): cómo se comporta el indicador
(momentum/RSI/vol) en función de la variación de precio de ESE ticker específico."

---

## 0. Motivación y estado del arte — lo que ya se sabe (verificado hoy)

### 0.1 El hallazgo que dispara esto: F0 del RMT

El análisis RMT de los 8 factores residuales (`ANALISIS_RMT_8FACTORES_20260830.md`,
OpenCode 30/08, verificado) muestra que el eje residual dominante (F0, 15.2% de la
varianza residual, λ=7.589) es **growth/tech vs defensivo**:

```
F0 positivo:  QQQ +0.32 · NVDA +0.24 · SPY +0.22 · AMD +0.20 · AVGO +0.20 · AMZN +0.18
F0 negativo:  KO −0.24 · JNJ −0.23 · PEP −0.21 · PG −0.21 · BRK-B −0.19 · ABBV −0.18
```

Confirmación estructural de lo que Boris venía diciendo: **KO no se comporta como
TSLA/NVDA** — están en extremos opuestos del primer factor residual del universo. Sin
embargo, el motor los puntúa con la MISMA función (`signal_engine.py:110-128`:
`momentum_score = normalize(mom, −50, 100)`, `rsi_score = 0.8 si 45<RSI<70` — umbrales
globales, idénticos para los 50 símbolos).

### 0.2 La evidencia pooled está agotada — y es pooled

| Evidencia previa | Resultado | Fuente |
|---|---|---|
| momentum_score intra-día | IC −0.0100, t −0.28 | `rr2_intraday_20260811_150741.txt` |
| rsi_score intra-día | IC +0.0404, t +1.38 — no sig | idem |
| adx_score intra-día | IC +0.0679, t +2.31 — muere Bonferroni-4 | idem |
| ADX walk-forward (§25, #15) | 0/3 ventanas | `trial_adx_walkforward_20260817_103916.txt` |
| Indicadores semanales (§26, #16) | 0/3, máx \|t\|=0.44 | `weekly_indicators_20260817_105918.txt` |
| MACD/dirección (§36, #19) | 0/3 | `trial_macd_bollinger_20260820_174735.txt` |
| PBO/CSCV mom+RSI (#22) | PBO 0.4688 → overfitting de proceso | `pbo_cscv_mom_rsi_20260822_093300.txt` |
| Rank IC vs SPY (§28) | 0/3 todos — IC relativos ≈ absolutos | RESUMEN_VALIDACION_VARIABLES §5 |
| Ridge_3f como score (#13) | DSR 0/3 — IC mejor no se tradujo en PnL | idem §2 |

**Lectura honesta:** cada uno de esos tests promedió A TRAVÉS de tickers. Si cada ticker
es un universo propio (F0 lo confirma), el pooling puede estar promediando señales con
signos OPUESTOS entre sí hasta anularlas — o señales que solo existen en ciertos
contextos. Esto NO reabre ningún veredicto: el ranking pooled sigue muerto, el PBO
sigue NO_CUMPLE. Es la motivación de medir UNA cosa distinta que nadie midió: el
comportamiento INDIVIDUAL de cada ticker.

### 0.3 Confusores documentados que este diseño respeta

- **§6.2 del RESUMEN:** todas las IC midieron dirección absoluta, mezclando alpha con
  beta de mercado. El análisis por ticker es la extensión natural de esa crítica: mide
  al ticker contra sí mismo.
- **§6.3 del RESUMEN:** el gate duro nunca se testeó variable por variable fuera de la
  población que el gate selecciona. El atlas mide en TODOS los días del ticker, sin
  filtrar por el gate — es ortogonal a ese confusor por construcción.
- **Lección PBO (#22):** minar in-sample y reportar lo mejor es fabricar hallazgos.
  Toda la arquitectura de este diseño (§2) existe para que el minado sea DEScriptivo
  y la confirmación sea SIEMPRE pre-registrada.

### 0.4 Lo que este diseño NO re-propone (refutado con rigor, tabla §2 del RESUMEN)

Sentimiento AAII, fundamentales EDGAR, ER/Kaufman, piso de stop por régimen, ADX como
peso, pares/cointegración, ridge como score, rank IC cross-sectional. El atlas no valida
factores (línea cerrada pooled): **mapea comportamiento individual**.

---

## 1. Objetivo en una línea

> Construir el **ATLAS**: un pipeline reutilizable y repetible que, para cualquier
> ticker del universo, en cualquier contexto (ventana o régimen), en cualquier horizonte
> (corto/medio/largo), produce la **curva de respuesta** del retorno futuro del ticker
> en función del nivel propio de cada indicador — más una taxonomía de arquetipos que
> convierte miles de mediciones en un vocabulario estable — y una capa de graduación
> que es el ÚNICO camino por el que una celda del atlas puede volverse regla accionable.

Lo que NO es: no es un análisis puntual (es infraestructura), no valida el ranking
pooled (muerto), no modifica el motor, no consume slots para correr (solo para
graduar), y no autoriza trades por sí solo.

---

## 2. Arquitectura de dos capas (la decisión estructural del diseño)

```
┌─────────────────────────────────────────────────────────────────────┐
│  CAPA 1 — ATLAS (descriptivo)                                       │
│  Corre libre, sin ledger, sin trial, sin veredicto.                 │
│  Entrada: cache parquet (sin red). Salida: fichas + taxonomía.      │
│  Doctrina: "construir es libre y rápido".                           │
│  Prohibido: afirmar que una celda "funciona" o accionar nada.       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ celda candidata (a elección de Boris)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CAPA 2 — GRADUACIÓN (confirmatoria)                                │
│  Pre-registro individual ANTES de re-testear (umbral, corrección,   │
│  criterio de éxito escritos de antemano — regla no negociable #2).  │
│  Deflactación Bonferroni por el CONTEO REAL de celdas escaneadas.   │
│  Confirmación OOS fresca o walk-forward ≥2/3 ventanas (estándar).   │
│  Familia signal_diagnosis, slot secuencial al momento de graduarse. │
└─────────────────────────────────────────────────────────────────────┘
```

**Por qué dos capas:** el atlas v1 escaneará ~7.000 celdas (§5.5). Con ese número,
aplicar umbrales de significancia a cada celda sería el error exacto que el PBO #22
atrapó (minar primero, contar después). La solución del diseño: la capa 1 describe con
honestidad estadística (N, N efectivo, signos, flags — sin veredictos), y la capa 2
convierte CUALQUIER celda en hipótesis formal pre-registrada con deflactación por el
conteo real del scan. El atlas jamás retro-valida un hallazgo in-sample.

---

## 3. La unidad de análisis: la celda y su ficha

**Celda = (ticker, indicador, contexto, horizonte).** Es atómica y auto-descripta:
`[NVDA, rsi14, W2, h20]` se lee "NVDA, RSI-14, contexto 2022-23, horizonte 20 días".

**Ficha de la celda = la curva de respuesta.** El indicador propio del ticker se
parte en quintiles (percentil propio, §4.1) y para cada quintil se mide el retorno
forward medio del MISMO ticker. Resumen numérico (6 números, siempre reportados):

| Métrica | Definición | Para qué |
|---|---|---|
| **IC de celda** | Spearman(quintil indicador, ret_fwd) | fuerza y signo |
| **Spread Q5−Q1** | ret_fwd(Q5) − ret_fwd(Q1), en bp | magnitud accionable (lección ADX: t sin magnitud no integra) |
| **Monotonicidad** | fracción de pares adyacentes de quintiles correctamente ordenados | ¿es una curva o un salto de un solo quintil? |
| **N bruto** | días observados en la celda | cobertura |
| **N efectivo** | N/h (deflactación por solape) | honestidad estadística |
| **Flags** | degenerado / circular / INSUFICIENTE | validez (§5.3) |

La ficha HUMANA (`fichas/<TICKER>.md`) agrupa las celdas del ticker: una tabla por
indicador × horizonte, filas = contextos. Es el producto de "ingeniería inversa" que
Boris lee: *qué hace este ticker cuando su RSI propio está en el quintil alto, en cada
contexto, a cada horizonte*.

---

## 4. Definiciones operacionales (fijas a priori, anti-fishing)

### 4.1 Indicadores — EXACTAMENTE los del motor, sin variantes

| Indicador | Definición (fuente en el motor) | Nota |
|---|---|---|
| **momentum_12_1** | retorno 12m excluyendo el último mes (col. `momentum_12_1`) | ventana t−252..t−22: no solapa con fwd ret ≤60d |
| **rsi14** | RSI Wilder 14d (col. `rsi14`) — RAW + score del motor (gate 45-70) | el score degenera a 0.4 fuera de 45-70: reportar fracción degenerada (sub-hipótesis mecánica de la asimetría §1) |
| **vol20** | std de retornos diarios 20d, anualizada √252 | flag de circularidad con h<20 (§10) |

**Escala primaria: percentil propio del ticker** — rank rodante 252d, min_periods 60
(mismos parámetros de `_rolling_rank01`, `signal_engine.py:269`, maquinaria ya del
repo). Hace que "RSI 65" signifique lo mismo en KO que en NVDA: cada uno contra SU
propia historia. Escala secundaria: valor crudo (reportado, no usado en arquetipos).

**Prohibido en v1:** variantes de parámetros (RSI-7, mom 6-1, vol 60...). Si una ficha
motiva una variante, es un pre-registro aparte (§7). El atlas mide los indicadores que
el motor YA usa — la ingeniería inversa es del motor real, no de un laboratorio.

### 4.2 Contextos — dos familias complementarias

**Filosofía del mandato: las ventanas capturan CONTEXTOS, no potencia estadística.**
El atlas nunca promete significancia por celda: reporta cada celda con su N y su
contexto; el pooling solo aparece como vista agregada EXPLÍCITAMENTE etiquetada.

**(a) Ventanas calendario** — las del proyecto, comparabilidad directa con los trials:

- W1: 2020-01-01 → 2021-12-31 · W2: 2022-01-01 → 2023-12-31
- W3: 2024-01-01 → 2026-08-04 (fin de datos del cache)
- TOTAL: 2016 → 2026-08 (solo descriptivo, nunca head de nada)

**(b) Celdas de régimen del PROPIO ticker** — 9 celdas, reusando la maquinaria de
etiquetado de la asimetría direccional (su §2.1):

```
tendencia_propia(i,t):  UP si ret_63d(i, t−1) ≥ +10% · DOWN si ≤ −10% · NEUTRO si no
                        (etiqueta usa SOLO datos ≤ t−1: cero look-ahead, cero solape
                         con el outcome t→t+h — idéntico a asimetría §2.1)
vol_propia(i,t):        tercil del percentil propio de vol20 en t−1
celda_régimen = {UP,DOWN,NEUTRO} × {VOL_BAJA,MEDIA,ALTA} = 9 celdas
```

Capturan el "régimen" sin calendarios arbitrarios: un mismo año puede contener tres
regímenes del ticker. Responde "¿el RSI de NVDA significa otra cosa cuando NVDA viene
cayendo 10%+ que cuando viene subiendo?"

### 4.3 Horizontes

| h | Nombre | Rol |
|---|---|---|
| 5 | corto | primario para celdas de régimen (factibilidad §5.4) |
| 20 | medio | **primario del sistema** (estándar del proyecto) |
| 60 | largo | solo ventanas calendario + total — descriptivo |

### 4.4 Alineación temporal (convención del repo, sin excepciones)

`indicador(i, t−1) medido con cierre de t−1 → ret_fwd(i, t→t+h)`. El outcome es
SIEMPRE estrictamente futuro respecto de t−1. En celdas de régimen, además, la
etiqueta tampoco solapa el outcome (asimetría §2.1 verbatim).

---

## 5. Medición por celda

### 5.1 Curva de respuesta (el corazón del sistema)

Para la celda `(i, f, c, h)`: quintiles del percentil propio de f dentro del contexto c
→ 5 retornos forward medios del MISMO ticker i → spread Q5−Q1 + IC + monotonicidad.

### 5.2 Estadística — comparabilidad directa con los artefactos del repo

- IC diario sobre la serie solapada (t−1 → t+h para cada t) con **Newey-West L=h**
  (mismo estimador que §0.5a/§25 — los números son directamente comparables con los
  t existentes de momentum −0.28, rsi +1.38, adx +2.31).
- **Reporte obligatorio junto a cada t:** N bruto y **N efectivo = N/h**. El t solapado
  crudo JAMÁS se reporta solo: la ficha lo muestra siempre acompañado del N efectivo,
  para que nadie lea un t=2.1 con N efectivo 25 como si fuera 500 observaciones.
- La estabilidad de arquetipos (§6) usa SIGNOS (no t), robusta al solape.

### 5.3 Gates de validez (corren ANTES de calcular cualquier IC — lección trial #17)

1. **Gate de cobertura:** N de la celda < N_min → celda **INSUFICIENTE** (se reporta
   como tal, jamás "cuenta como cero"). N_min pre-especificado: **75 días** en ventanas
   calendario, **40 días** en celdas de régimen (h≤20).
2. **Gate de degeneración:** fracción de días con varianza del indicador ≈ 0 dentro de
   la celda (ej. rsi_score colapsado a 0.4 en DOWN). Si supera 1/3 de los días, la
   celda se marca **DEGENERADA** y su IC se reporta como no-interpretable.
3. **Gate de datos:** el script verifica cobertura real por ticker ANTES de correr
   (parquets 2016→2026-08, profundidad variable por ticker — verificado hoy: 60
   parquets, AAPL 2016-01-04→2026-08-11, 2666 filas OHLCV).

### 5.4 Matriz de factibilidad a priori (declarada ANTES de medir, como asimetría §2.4)

Con ~2.600 días hábiles por ticker (2016→2026-08):

| Horizonte | Ventanas calendario (W1/W2/W3) | Celdas de régimen (9/ticker) |
|---|---|---|
| h=5 | ✅ viable (N≈100-84 por ventana) | ✅ viable (N≈30-60 por celda sobre TOTAL; por ventana, muchas celdas INSUFICIENTES — así se reportan) |
| h=20 | ✅ viable (N≈95-80 efectivos ~4-5) | ⚠️ solo sobre TOTAL (no por ventana): celdas de régimen con h=20 se computan sobre la serie completa |
| h=60 | ✅ solo TOTAL y ventanas (N efectivo ~7-8 por ventana) | ❌ **INSUFICIENTE por diseño** (≈4-5 obs no solapadas por celda) — no se disfraza con solapamiento |

**Regla derivada:** las celdas de régimen × h=60 no existen en el atlas v1. La ficha
declara esta restricción en su header para que nadie la pida "porque faltan celdas".

### 5.5 Escala del scan (declarada, alimenta la deflactación de §7)

```
50 tickers × 3 indicadores
× (3 ventanas + 1 total) × 3 horizontes            = 1.800 celdas calendario
× 9 celdas de régimen × 2 horizontes (h5, h20)      = 2.700 celdas de régimen
+ celdas de régimen h20 sobre TOTAL (50×3×9)        =   1.350 celdas
───────────────────────────────────────────────── ≈ 5.850 celdas (redondeo ~6.000)
```

El conteo EXACTO se emite en el output del atlas (`n_celdas_escaneadas`) y es el
multiplicador de la deflactación Bonferroni de la capa 2.

---

## 6. Taxonomía de arquetipos (lo que convierte mediciones en SISTEMA)

Para cada trío (ticker, indicador, horizonte), el atlas observa el conjunto de sus
celdas (contextos) y asigna UN arquetipo con un score de estabilidad:

| Arquetipo | Regla (pre-especificada) | Lectura |
|---|---|---|
| **CONTINUISTA** | IC > 0 en ≥70% de las celdas interpretables | indicador alto → el ticker SIGUE subiendo (en su propio espacio) |
| **REVERSIONISTA** | IC < 0 en ≥70% de las celdas interpretables | indicador alto → el ticker corrige |
| **CAMALEÓN** | ningún signo alcanza 70%; al menos 60% de celdas con \|IC\| ≥ 0.05 de magnitud | el indicador significa cosas OPUESTAS según el contexto — exactamente lo que el pooling destruye |
| **INERTE** | el resto, con celdas suficientes | sin relación estable |
| **INSUFICIENTE** | <50% de celdas interpretables | el ticker/horizonte no da para hablar |

- **Score de estabilidad** = fracción de celdas interpretables con el signo modal,
  ponderada por N efectivo de cada celda. Se reporta siempre junto al arquetipo.
- El umbral 70/60/50 está fijado AQUÍ, antes de correr, para que la taxonomía no se
  ajuste a los resultados.
- **El arquetipo es descriptivo, no confirmatorio.** "NVDA es CONTINUISTA en momentum
  h=60" es un hecho del atlas, no un hallazgo de trial. Solo la capa 2 (§7) convierte
  un arquetipo en hipótesis formal.

El output del sistema es entonces un **mapa** legible y repetible: para cualquier
ticker nuevo del universo, correr el atlas y obtener su ficha con arquetipos. Esa es
la "metodología reutilizable" del mandato: mismo pipeline, mismas definiciones, mismos
gates, sobre cualquier ticker — incluyendo tickers NUEVOS que entren al universo.

---

## 7. Capa 2 — Graduación: cómo una celda se vuelve regla (y solo así)

1. **Disparador:** Boris (o el agente con su aprobación) elige celdas candidatas desde
   el resumen de arquetipos. El atlas NO auto-gradúa nada.
2. **Pre-registro individual** (`PRE_REGISTRO_ATLAS_GRAD_<n>.md`): antes de re-testear,
   declara la celda exacta, el signo esperado, el umbral de magnitud (spread mínimo en
   bp e |IC| mínimo), el criterio de éxito (≥2/3 ventanas, estándar del repo) y la
   **deflactación Bonferroni por el conteo real de celdas escaneadas** emitido por el
   atlas (con ~6.000 celdas, un hallazgo por azar puro a α=0.05 sería ~300 — el umbral
   graduado debe ser órdenes de magnitud más estricto que un t=2 nominal).
3. **Test de confirmación:** la celda pre-registrada se re-testea OOS (datos posteriores
   a la corrida del atlas) o walk-forward ≥2/3 ventanas. Re-testear sobre LOS MISMOS
   datos del atlas NO es confirmación (es leer dos veces lo mismo).
4. **Ledger:** familia `signal_diagnosis`, slot secuencial al momento de registrar.
   El atlas v1 mismo NO consume slot (es infraestructura de diagnóstico, como
   `diagnose_factor_ic` — no hay veredicto CUMPLE/NO_CUMPLE sobre el motor).
5. **Si la graduación CUMPLE:** recién ahí existe una regla per-ticker candidata, y su
   integración al motor (siempre que Boris la quiera) requiere SU PROPIO trial
   `motor_signal` con DSR ≥ 0.90 en W1/W2/W3 — el estándar vigente. Dos puertas, no una.

---

## 8. Entregables concretos del pipeline (implementación futura, tras aprobación)

| Artefacto | Contenido |
|---|---|
| `backend/scripts/atlas_ticker.py` | Motor del atlas: offline, cache-only (parquet), sin red, sin tocar el motor. Entrada: configuración del grid (§4-§5). Salida: los 3 artefactos de abajo. Runtime estimado: minutos. |
| `backend/data/cache/atlas_<ts>/atlas_celdas.csv` | El grid completo: una fila por celda con los 6 números + flags + `n_celdas_escaneadas`. |
| `backend/data/cache/atlas_<ts>/fichas/<TICKER>.md` | La ficha humana por ticker (curvas de respuesta + arquetipos). |
| `backend/data/cache/atlas_<ts>/resumen_arquetipos.md` | Mapa cross-ticker (vista agregada etiquetada como tal) + candidatos visibles + conteo de scan. |
| `backend/tests/test_atlas_ticker.py` | Tests: (1) sin look-ahead — correr con datos desplazados +h debe cambiar el resultado de forma verificable; (2) gates de cobertura marcando INSUFICIENTE; (3) convención t−1→t+h; (4) idempotencia de la corrida; (5) el conteo de celdas emitido = conteo real. |

**Alcance v1 explícito:** universo 50 canónico, 3 indicadores, 3 horizontes, ventanas
W1/W2/W3/TOTAL + 9 celdas de régimen (con la restricción §5.4). Sin interfaces al
motor, sin endpoints, sin frontend. Es una herramienta de escritorio para Boris y los
agentes.

---

## 9. Relación con lo existente (fronteras claras)

- **Con el motor:** mide LOS MISMOS indicadores con las mismas definiciones
  (`momentum_12_1`, `rsi14` + su score, `vol20` ↔ la familia de vol del motor). No lo
  modifica. La ficha explica el motor, no lo reemplaza.
- **Con la asimetría direccional (diseño 30/08, slot 23 si corre):** complementarias,
  NO redundantes. La asimetría pregunta "¿los FACTORES del motor condicionan distinto
  bajo impulso de alza vs baja?" (panel cross-sectional, IC por lado, test Δ_f formal).
  El atlas pregunta "¿cómo se comporta CADA TICKER individual frente a sus propios
  indicadores?" (series de tiempo por ticker, curvas de respuesta, descriptivo). Sus
  celdas de régimen UP/DOWN usan la misma etiqueta pero NO re-testean Δ_f — son
  descriptivas y así se etiquetan en la ficha.
- **Con el piloto de Kilo (worktree `test-kilo-orca`):** corre en paralelo y NO se toca.
  Interfaz natural: el piloto concreto de Kilo puede servir de caso de validación del
  pipeline del atlas (si su análisis puntual y el atlas discrepan en un ticker, hay un
  bug en alguno de los dos). Ningún archivo compartido se modifica.
- **Con los refutados (§0.4):** el atlas no re-propone nada de esa tabla. No busca
  "salvar" factores pooled; mide individuos.

---

## 10. Riesgos específicos de este diseño y cómo se neutralizan

1. **El atlas como máquina de p-hacking per-ticker** (el riesgo mayor, es el PBO #22
   amplificado ×50 tickers): minar 6.000 celdas y quedarse con las lindas es fabricar
   hallazgos con pasos extra. Neutralización: arquitectura de dos capas (§2), la capa 1
   sin veredictos ni consumo, la graduación con deflactación por conteo real (§7.2) y
   confirmación solo OOS/walk-forward (§7.3). El arquetipo es descripción, nunca
   autorización (§6).
2. **Solape inflando t:** con h=60, las observaciones solapadas inflan N ×60.
   Neutralización: NW L=h (estándar repo), N efectivo OBLIGATORIO junto a cada t (§5.2),
   estabilidad de arquetipos por signos (robusta al solape), y h=60 excluido de celdas
   de régimen (§5.4).
3. **Look-ahead en etiquetas de régimen:** una etiqueta calculada con datos futuros
   contaminaría todo el atlas. Neutralización: etiquetas usan datos ≤ t−1 (asimetría
   §2.1 verbatim) + test automatizado de desplazamiento (§8, test 1).
4. **Fishing de parámetros:** "¿y con RSI-7? ¿y con vol 60?" Neutralización: grid FIJO
   declarado en §4; variantes = pre-registro aparte. El atlas mide el motor real.
5. **La ficha como excusa para tradear sin validación:** "KO es REVERSIONISTA, vendo".
   Neutralización: la ficha lleva un header fijo que dice que NO autoriza nada; el único
   camino a regla es §7; y aun graduada, integrar al motor exige trial `motor_signal`
   DSR ≥ 0.90 (§7.5). Dos puertas explícitas.
6. **Circularidad vol20 con h=5:** vol20 (t−21..t−1) solapa el outcome t→t+5. El IC de
   esa celda mezcla persistencia de vol con predicción. Neutralización: flag
   `circular=true` en las celdas vol20×h5, reportado en la ficha; interpretación
   acotada declarada aquí.
7. **Doble contabilidad con la asimetría (#23):** si ambos corren, podrían "descubrir"
   lo mismo dos veces. Neutralización: §9 fija la frontera (panel cross-sectional vs
   series individuales; test formal vs descriptivo) y las celdas UP/DOWN del atlas
   llevan etiqueta `descriptivo-no-re-testea-Δf`.
8. **Profundidad de datos desigual por ticker:** no todos los parquets cubren 2016→.
   Neutralización: gate de cobertura por ticker ANTES de correr (§5.3.3), reportado en
   la ficha; un ticker con 2019→ simplemente tiene menos celdas interpretables.

---

## 11. Qué decide Boris sobre este diseño

1. **Aprobar la arquitectura de dos capas** (atlas descriptivo libre + graduación
   pre-registrada como único camino a regla).
2. **Aprobar el grid v1:** 3 indicadores del motor, 3 horizontes {5,20,60}, ventanas
   W1/W2/W3/TOTAL + 9 celdas de régimen (con restricción h=60 de §5.4), percentil
   propio 252/60 como escala primaria.
3. **Aprobar que el atlas corra SIN slot de ledger** (infraestructura de diagnóstico,
   no trial). Las graduaciones futuras sí consumen slots individuales.
4. **Aprobar el arquetipo-vocabulario** (CONTINUISTA / REVERSIONISTA / CAMALEÓN /
   INERTE / INSUFICIENTE con umbrales 70/60/50) como el output estándar del sistema.

Si aprueba: siguiente paso es implementar `atlas_ticker.py` + tests (tarea separada,
sin ledger), correr atlas v1, y leer fichas. Ninguna corrida de esto toca el motor ni
el ledger ni el trabajo de Kilo.

---

## 12. Criterios de éxito del atlas v1 (verificables al implementar)

- Corre completa en <10 min sobre el cache, sin red.
- Gates de cobertura operativos: celdas INSUFICIENTES reportadas como tales (esperamos
  que sean una fracción minoritaria pero NO cero — si sale 0% INSUFICIENTE, sospechar
  bug en el gate, no celebrar).
- Test de look-ahead en verde (datos desplazados cambian el resultado de forma
  verificable).
- ≥80% de los tríos (ticker, indicador, horizonte) reciben arquetipo no-INSUFICIENTE.
- Fichas legibles: Boris puede abrir `fichas/KO.md` y entender en 2 minutos cómo se
  comporta KO frente a sus propios indicadores.

---

*Documento de diseño. Sin ejecución, sin ledger, sin cambios al motor. Mismo estatus
que `DISENO_ASIMETRIA_DIRECCIONAL_20260830.md` hasta que Boris diga lo contrario.*
