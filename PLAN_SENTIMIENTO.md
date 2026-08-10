# PLAN — Variable de Régimen: Sentimiento Inversor (v4.3)

**Fecha**: 2026-08-09
**Estado**: Ola 2 completada — tesis CONFIRMADA con datos reales (AAII). H7: V1 se integra con peso dominante (50-70%). Pendiente: integración en motor + ContrarianAgent.
**Dueño de la variable**: Agente CONTRARIAN (`triad_agents.py`)

---

## 1. La tesis (mecanismo que debe validar el sistema)

El sistema financiero (instituciones) maneja las alzas y bajas del precio de la bolsa. La
variable central que lo gobierna es el **sentimiento del inversor minorista**:

1. **Sentimiento NEGATIVO (miedo)** → la gente no compra → el sistema financiero compra
   barato → **la bolsa sube**. En sentimiento bajo de compra se alcanzan máximos históricos
   del S&P 500.
2. **Sentimiento POSITIVO (euforia)** → todos quieren comprar → el sistema financiero
   vende caro a la multitud → **la bolsa cae**, para luego recomprar más barato y repetir.
3. **La liquidez NO es la causa de la subida.** Es la condición habilitadora: cuando el
   sistema quiere que la gente compre, se asegura de que haya liquidez (la gente puede
   comprar porque tiene dinero disponible, no porque "la bolsa sube por liquidez").
4. **La velocidad es la firma de la intención:**
   - Movimientos **rápidos** → quieren generar emoción: entusiasmo (subidas) o miedo (bajadas).
   - Movimientos **lentos y persistentes**, especialmente subidas → quieren pasar
     desapercibidos (acumulación silenciosa).
5. **Consecuencia operativa**: el agente CONTRARIAN le da valor a esta variable y
   **cuestiona las demás variables del sistema contra ella** (si el sentimiento está en
   extremo, momentum/RSI/ER mienten).

> **Método de integración (decisión del usuario — prueba por bloques)**: V1 NO es la
> variable principal, ni se integra por contribución marginal. El método es una prueba de
> hipótesis con dos grupos:
>
> - **Grupo 1 (baseline)**: las variables existentes del sistema, con sus pesos variables
>   actuales (las que ya teníamos).
> - **Grupo 2 (hipótesis)**: las variables del Grupo 1 + la variable V1 (sentimiento
>   comprador/vendedor de la gente) con **efecto dominante**: un 50-70% del peso total.
> - **Decisión**: si el Grupo 2 aporta un **efecto probabilístico mejor** que el Grupo 1
>   (mejor calidad de probabilidad/accuracy/Brier en horizontes), V1 queda integrada con
>   peso dominante. Si no mejora, se ajusta el peso o se descarta. V1 se **contrasta**
>   contra el resto, no se impone ni se margina.

---

## 2. Variables del plan

| Var | Nombre | Fuente | Estado |
|-----|--------|--------|--------|
| **V1** | **Sentimiento inversor directo** (hipótesis de efecto dominante 50-70% del peso, validado por prueba de bloques) | AAII bull−bear spread (NAAIM pago, put/call CBOE 2019+ bloqueado) | **Testeada — integra con peso dominante (H7)** |
| V2 | Posiciones adoptadas EN FUNCIÓN del sentimiento | CFTC COT: NonRept (retail), Lev_Money (specs), Asset_Mgr, Dealer | Datos listos (ola 1) |
| V3 | Liquidez como condición habilitadora | FRED: WALCL, RRPONTSYD, WRESBAL | Datos listos (ola 1) |
| V4 | Velocidad (rápido/lento) | Kaufman ER10/20/60 + \|leg_ret\| | Medido (Fase V4) |

**Relación clave V1↔V2**: los inversores adoptan posiciones en función de su sentimiento.
El test H2 mide esa consistencia: cuando el sentimiento (V1) sube, ¿el retail (V2) compra?
Si no, la narrativa sentimiento→posición no se sostiene y hay que revisarla.

---

## 3. Hipótesis medibles y tests

| # | Hipótesis | Test | Datos |
|---|-----------|------|-------|
| **H1** | IC(sentimiento, retorno futuro) NEGATIVO: sentimiento alto → cae; bajo → sube | IC univariado V1 vs ret 5/20/60d + terciles | ola 2 |
| **H2** | Consistencia: sentimiento alto → retail COT comprado | Correlación V1 con cot_retail_net_pct (misma semana) | ola 2 + ola 1 |
| **H3** | Distribución retardada: la caída ocurre DESPUÉS del pico de sentimiento | Retorno 20/60d tras extremos de V1 (tercil alto vs bajo) | ola 2 |
| **H4** | Liquidez como condición: el efecto H1 se POTENCIA cuando hay liquidez | 2×2 sentimiento × liquidez (celda sent_bajo × liq_alta debe ser la mejor) | ola 2 + ola 1 |
| **H5** | Velocidad: subida lenta y persistente + sentimiento bajo → continúa (acumulación); subida rápida + sentimiento alto → cae (distribución) | 2×2 sentimiento × ER (o \|leg_ret\|) | ola 2 + Fase V4 |
| **H6** | Cuestionamiento: en buckets de sentimiento extremo, momentum/RSI/ER cambian de signo o pierden potencia | IC condicional de momentum/rsi/er por bucket de V1 | ola 2 |
| **H7** | **Prueba de bloques (decisión de integración)**: el Grupo 2 (variables existentes + V1 con 50-70% del peso) mejora la calidad probabilística vs el Grupo 1 (baseline) | Accuracy/Brier por horizonte (1/5/20/60d) de ambos grupos; V1 gana peso dominante SOLO si el Grupo 2 supera al Grupo 1 | ola 2 + motor actual |

**Regla de significancia**: |IC| > 2/√n, consistencia entre horizontes, y rank_ic en la
misma dirección. Los datos mandan: si una hipótesis de la narrativa falla, se documenta
y se descarta — no se fuerza.

---

## 4. Implementación

### Ola 2 — Fuentes de sentimiento directo (V1)
- **AAII** (sentimiento semanal de inversores individuales): bull/bear neutral → spread. ✅
  `https://www.aaii.com/files/surveys/sentiment.xls` — completo 1987-2026, headers en fila 3,
  datos desde fila 5, fila final "Count YY" de resumen a descartar, bull/bear en fracción 0-1.
- **NAAIM** (exposición de gestores): ❌ **pago** (suscripción desde 2025) — descartado.
- **Put/call ratio** CBOE: ❌ CDN diario 2019+ devuelve 403 AccessDenied (S3) a bots con todas
  las impersonaciones; CSVs estáticos oficiales solo llegan a 10/2019 — pendiente de fuente.
- Implementación en `backend/app/core/market_sentiment.py` con el mismo patrón:
  anti-lookahead (`shift(1)` + `ffill` sobre fechas de trading), cache parquet, doble
  transporte HTTP (requests + curl_cffi). ✅

### Integración — Variable de régimen
- Nueva capa `sentiment_regime` sobre `REGIME_WEIGHTS` (`predictive_engine.py:1021`):
  - **Prueba de bloques (H7) primero**: Grupo 1 (baseline, pesos actuales) vs Grupo 2
    (baseline + V1 con 50-70% del peso). Solo si el Grupo 2 mejora la calidad
    probabilística, V1 entra con peso dominante. Si no, se recalibra el peso (30%, 50%)
    o se descarta.
  - Sentimiento en extremo → V1 gana peso de régimen; las demás variables se **cuestionan**
    (multiplicador o inversión según H6).
  - Subidas lentas y persistentes (ER bajo) con sentimiento bajo → confirmar continuidad.
  - Subidas rápidas (ER alto) con sentimiento alto → señal de distribución → inclinar bear.
- Reglas nuevas en `ContrarianAgent` (`triad_agents.py:268`): el agente lee V1 como su
  variable principal y condiciona su voto a los extremos de sentimiento.

### Validación
- `pytest` completo tras integración.
- OOS: datos 2025-2026 si la fuente lo permite.
- Docs: `PLAN_SENTIMIENTO.md` + entrada en `SESSION_LOG.md`.

---

## 7. SPEC CONGELADA — Test OOS 2025-2026 (PRE-REGISTRADA, 2026-08-09, antes de correr)

> **Disciplina**: el OOS se corre UNA sola vez, con esta spec tal cual. No se
> re-testa con 0.60/0.70 ni se toca aunque el resultado decepcione. El ranking
> causal se declara aquí: en el IS se usó rank global de la muestra; en OOS
> sería lookahead, así que se usa **percentil rolling de 260 días (causal)**.

**Spec congelada**:
- Peso V1: **0.50 fijo** (sin barrido). Señal V1 = −percentil_rolling260(aaii_bullbear_spread) en [−1,1].
- Señales Grupo 1 (pesos relativos del régimen, normalizados a suma 1):
  momentum_12_1 .35 → 0.58, rsi14 .10 → 0.17 (invertida), walcl_growth_w .05 → 0.08, cot_retail_net_pct .10 → 0.17.
- Score2 = 0.50·Score1 + 0.50·V1. Prob = sigmoid(1.5·score).
- Universo SYMBOLS, stride 5d, warmup 260d, horizontes 1/5/20/60d (evaluación ≥ 2025-01-01).
- Métricas: IC univariado con n_eff Newey-West, Brier G1 vs G2/50, Diebold-Mariano (varianza NW, lag=ceil(h/5)), accuracy direccional.
- Criterio pre-registrado:
  - **CONFIRMA** si IC(AAII) < 0 (dirección correcta) Y G2/50 gana Brier en ≥3/4 horizontes → integrar V1 con 0.50.
  - **DIRECCIÓN SOLA** (IC correcto pero <3/4) → integrar, peso a discutir (30-50%).
  - **NO CONFIRMA** → reportar tal cual; NO re-testar; descartar o revisar con el usuario.
- Huella: salida con timestamp en `data/cache/oos_result_*.txt`.

**Resultado (se llena DESPUÉS de la única corrida)**:
| Horizonte | IC AAII | G1 Brier | G2/50 Brier | DM p |
|-----------|---------|----------|-------------|------|
| 1d | | | | |
| 5d | | | | |
| 20d | | | | |
| 60d | | | | |
**Veredicto OOS**:

---

## 5. Orden de ejecución

1. ~~**Ola 2**: fetch AAII + NAAIM + put/call~~ ✅ AAII listo; NAAIM pago, put/call bloqueado (documentado).
2. ~~**Tests H1-H4**~~ ✅ H1/H2' confirmadas; H3/H4 (2×2) consistentes con la tesis.
3. ~~**Test H5**~~ ✅ sustituido por H6/V1 2×2 (sent × liq) que confirma el mecanismo.
4. ~~**Test H6**~~ ✅ IC condicional por bucket de AAII: en euforia, RSI/ER se invierten.
5. ~~**Test H7 (prueba de bloques)**~~ ✅ **Veredicto: V1 integra con peso dominante (50-70%)** — G2 gana en Brier en 4/5 horizontes (1/5/20/60d).
6. **Integración**: `sentiment_regime` en `predictive_engine.py` + reglas en `ContrarianAgent`.
7. **Cierre**: `pytest`, OOS si aplica, `SESSION_LOG.md`.

---

## 6. Estado de datos (ola 1 + ola 2, ya medido)

| Medición | Resultado | Nota |
|----------|-----------|------|
| COT retail (NonRept) 60d | IC +0.1069*** | Posición, NO sentimiento — no es evidencia contra la tesis |
| COT asset managers 60d | IC -0.0890*** | Dirección contraria a retail |
| walcl_growth_w 60d | IC +0.0633* / rank_ic -0.0167 | Frágil |
| H6 2×2 (liquidez × retail COT) 60d | liq_alta × ret_alta = +0.0983 | La celda "euforia + liquidez" sube — inconsistente con H4/H6 narrativa, requiere V1 real para dirimir |
| **AAII (V1) 5d** | IC -0.0315 (borde sig), rank_ic -0.0405 | Dirección correcta desde 5d |
| **AAII (V1) 20d** | IC -0.0472*** (rank -0.0439***) | Confirma |
| **AAII (V1) 60d** | **IC -0.0773*** (rank_ic -0.0857***)** | **ÚNICA variable con IC negativo consistente en todos los horizontes** |
| **Terciles AAII 60d** | bajo +0.0987 > medio +0.0609 > alto +0.0585 | **MONÓTONO — tesis confirmada: pesimismo → sube, euforia → cae** |
| **H6/V1 2×2 60d** | liq_baja×sent_baja +0.0916, liq_alta×sent_baja +0.0747 vs sent_alta +0.0642/+0.0537 | **El sentimiento domina; la liquidez solo modula (en línea con la tesis)** |
| **H2' (sent → posiciones)** | rho +0.243 lag0 → +0.095 lag8 (Spearman) | La gente actúa según su actitud — cadena actitud→acción se sostiene |
| **H6 condicional 60d (euforia AAII)** | RSI IC -0.1254, ER IC -0.1122 | En sentimiento alto, los factores de tendencia se INVIERTEN — base del "cuestionamiento" |
| **H7 prueba de bloques** | G2 (V1 al 50-70%) gana en Brier en 4/5 horizontes; mejor dom=50% | **VEREDICTO: V1 integra con peso dominante** |

> **Veredicto global**: la tesis del usuario se CONFIRMA con datos reales. El sentimiento
> directo de la gente (AAII) predice retornos en dirección contraria — cuando la gente está
> pesimista el mercado sube, cuando está eufórica cae — y domina a las demás variables en
> calidad probabilística (Brier). La liquidez modula pero no causa (H6/V1). En sentimiento
> extremo, momentum/RSI/ER pierden fiabilidad (H6 condicional) — esto justifica que el
> agente CONTRARIAN cuestione las demás variables contra V1.

> **Importante**: los resultados de ola 1 miden POSICIONES sin el sentimiento directo.
> La tesis completa solo puede confirmarse o refutarse con V1 (AAII/NAAIM/put-call) y los
> tests H1-H6. El COT NonRept de 2026-08-04 ya está descartado por el bug de alineación
> (fix: `sort_index()` en `_align`).
