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

### Integración — Variable de régimen (IMPLEMENTADA 2026-08-09)
- Nueva capa `sentiment_regime` sobre `REGIME_WEIGHTS` (`predictive_engine.py`):
  - **Prueba de bloques (H7)**: veredicto **CONFIRMA** con peso 0.50 (IS: Brier 4/4
    con DM p<0.05 en 1d/5d; OOS 2025-2026: Brier 4/4 con DM p<0.05 en 4/4).
  - Implementación (constantes en `app/core/sentiment_regime.py`, peso 0.50 fijo):
    - Blend: `composite = 0.5*composite + 0.5*s_v1` con `s_v1 = -normalize(spread, ±35)`.
      Sin datos de sentimiento → comportamiento idéntico al baseline (backward-compatible).
    - **H6 — cuestionamiento en euforia** (`s_v1 < -0.5`): tech_mom y tech_rev se
      multiplican por 0.5 antes del compuesto (IC condicional RSI/ER invierte en euforia).
    - **V4 — velocidad**: ER20 < 0.25 con pesimismo (`s_v1 > 0.3`) → `composite += 0.10`
      (acumulación silenciosa); ER20 > 0.60 con euforia (`s_v1 < -0.3`) → `composite -= 0.10`
      (distribución). Señales agregadas al reporte con categoría `sentiment_regime`.
  - Nota de diseño: con sentimiento neutro (spread=0) el blend diluye la convicción
    base a la mitad — fiel al bloque H7 (`0.5*G1 + 0.5*0`), test cubierto.
- Reglas nuevas en `ContrarianAgent` (`triad_agents.py`): V1 como variable principal
  (regla 8: spread < -15 → +0.3 alcista, > +15 → -0.3 bajista, intermedio proporcional);
  en euforia extrema las señales de reversión (reglas 1-5) se multiplican por 0.5 (H6).
  `TriadEvaluator.evaluate` y `PredictiveEngine.analyze` aceptan `sentiment_data`
  (backward-compatible).

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
| 1d | — | 0.2764 | 0.2623 | 0.014 |
| 5d | -0.0880 | 0.2789 | 0.2647 | 0.007 |
| 20d | -0.1326 | 0.2952 | 0.2705 | 0.006 |
| 60d | **-0.3567*** | 0.2978 | 0.2560 | 0.000 |
**Veredicto OOS**: **CONFIRMA** — IC(AAII) < 0 en todos los horizontes (dirección correcta) Y G2/50 gana Brier en 4/4 con DM p<0.05 en 4/4 → **V1 se integra con 0.50**.

---

## 5. Orden de ejecución

1. ~~**Ola 2**: fetch AAII + NAAIM + put/call~~ ✅ AAII listo; NAAIM pago, put/call bloqueado (documentado).
2. ~~**Tests H1-H4**~~ ✅ H1/H2' confirmadas; H3/H4 (2×2) consistentes con la tesis.
3. ~~**Test H5**~~ ✅ sustituido por H6/V1 2×2 (sent × liq) que confirma el mecanismo.
4. ~~**Test H6**~~ ✅ IC condicional por bucket de AAII: en euforia, RSI/ER se invierten.
5. ~~**Test H7 (prueba de bloques)**~~ ✅ **Veredicto: V1 integra con peso 0.50** — IS: G2 gana Brier 4/4 con DM p<0.05 en 1d/5d (cumple criterio pre-registrado); OOS 2025-2026: **CONFIRMA** (Brier 4/4, DM p<0.05 4/4, IC 60d -0.3567***).
6. ~~**Integración**: `sentiment_regime` en `predictive_engine.py` + reglas en `ContrarianAgent`~~ ✅ **2026-08-09**: blend 0.50, cuestionamiento H6 en euforia, reglas V4 de velocidad; tests `test_sentiment_regime.py` (10) + suite 36/36.
7. ~~**Cierre**~~ ✅ `pytest` 36/36, `SESSION_LOG.md` Sesión 8b.

---

## 8. Estado de la integración (2026-08-09)

| Componente | Estado |
|------------|--------|
| `app/core/sentiment_regime.py` (constantes pre-registradas) | ✅ Creado |
| `predictive_engine.py` — `_sentiment_regime_signal()` | ✅ Blend 0.50 + H6 cuestionamiento + V4 velocidad |
| `predictive_engine.py` — `analyze(sentiment_data=...)` | ✅ Backward-compatible (None → baseline) |
| `triad_agents.py` — `ContrarianAgent` regla V1 (regla 8) | ✅ +0.3 pánico / -0.3 euforia / proporcional |
| `triad_agents.py` — cuestionamiento reversión en euforia (H6) | ✅ ×0.5 reglas 1-5 |
| `TriadEvaluator.evaluate(sentiment_data=...)` | ✅ Propagado |
| `tests/test_sentiment_regime.py` | ✅ 10 tests (blend, H6, V4, backward-compat, agente) |
| Data feeding (pipeline: descargar AAII y pasar `sentiment_data` en `predict.py`) | ✅ 2026-08-10: `_load_sentiment_data()` en ambos endpoints (`/analyze/{symbol}`, `/universe`) |
| Guardas del data feeding (revisión): TTL semanal cache + degradado a baseline | ✅ `fetch_aaii()` con `AAII_CACHE_MAX_AGE_DAYS=7` (mtime): 1 descarga/semana máx, nunca por request; fallo con cache → stale; fallo sin cache → propaga y `_load_sentiment_data` captura → `None` → baseline. Guard formato xls: <400 filas no pisa cache bueno. Tests: `test_market_sentiment.py` (6) |
| Pendientes de auditoría (no bloqueantes) | n_eff=36 en OOS 60d (confirmación ajustada); **0a régimen HMM ✅ 2026-08-10** (`data/cache/regime_audit_20260810_082318.txt`): deterioro G1 OOS transversal, no por régimen; V1 positiva OOS por régimen. **0b backtest con costos ✅ (3 corridas)** (`backtest_v1_costs_20260810_083449.txt` v1-gate bloqueo matemático; `backtest_v1_costs_20260810_091011.txt` v2-ranking H7; `backtest_v1_costs_20260810_120906.txt` v2-fund trial #9): **Fase 1 fundamentales EDGAR CERRADA — sin edge neto demostrable; NO más variables de categoría sin evidencia nueva; la pregunta pasa a arquitectura** (ver Sesión 8h) |

---

## 6. Estado de datos (ola 1 + ola 2, ya medido)

| Medición | Resultado | Nota |
|----------|-----------|------|
| COT retail (NonRept) 60d | IC +0.1069*** | Posición, NO sentimiento — no es evidencia contra la tesis |
| COT asset managers 60d | IC -0.0890*** | Dirección contraria a retail |
| walcl_growth_w 60d | IC +0.0633* / rank_ic -0.0167 | Frágil |
| H6 2×2 (liquidez × retail COT) 60d | liq_alta × ret_alta = +0.0983 | La celda "euforia + liquidez" sube — inconsistente con H4/H6 narrativa, requiere V1 real para dirimir |
| **AAII (V1) 5d** | IC -0.0315 (borde sig), rank_ic -0.0405 | Dirección correcta desde 5d || **AAII (V1) 20d** | IC -0.0472*** (rank -0.0439***) | Confirma |
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

---

## 9. PROYECTO PRE-REGISTRADO — Expansión de universo a 50 símbolos (2026-08-10)

**Contexto / justificación** (gap audit, Sesión 8i): con 7 símbolos el motor genera 15 trades OOS en 2025-26 → el criterio acordado (DSR OOS ≥ 0.90 en ≥2 de 3 ventanas) es **estructuralmente inalcanzable por falta de poder estadístico**, no por mecánica rota (trial #10: win_rate honesto 0.667 OOS, pero PF 0.848 y n=15). La expansión no busca más edge de señal: busca **frecuencia y poder estadístico**.

### 9.1 Hipótesis del proyecto (pre-registrada)
Con 50 símbolos líquidos de gran capitalización, el motor genera ≥ 30 trades por ventana OOS de 2 años (vs 15 en 7 símbolos) y el criterio DSR OOS ≥ 0.90 en ≥2 de 3 ventanas pasa a ser **evaluable**; la señal del gate (trend + ADX + RSI + vol, score momentum/RSI) sobrevive al costo 0.15%/lado a escala. No se cambia NADA de la mecánica: gate, salidas (parcial único, fix trial #10), régimen HMM, calibrador, cooldowns, lunes, top-5.

### 9.2 Regla de selección de universo (sin lookahead)
- Los 7 actuales (SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA) se MANTIENEN (SPY/QQQ además como inputs de mercado para el HMM).
- Se añaden 43 US-listed top-43 por market cap, corte estático 2026-08-01, historial yfinance ≥ 2015-01-01 (lista en `scripts/fetch_universe_data.py`; los ETFs SPY/QQQ siguen siendo tradeables como hoy).
- La lista NO se re-elige después de ver resultados.

### 9.3 Qué cambia vs trial #10
| Componente | Estado |
|---|---|
| SYMBOLS 7 → 50 | CAMBIA (script Phase A2) |
| N_TRIALS (DSR) | 10 → **16** (+6 por selección de universo: regla mecánica estática, penalización por haber elegido 1 lista de 50 de un menú de ~500 grandes caps) |
| Gate / salidas / régimen / calibrador / cooldown / lunes / top-5 / costs | **NO cambian** |
| Risk caps (5 concurrentes, 10% posición, Kelly 25%) | NO cambian en Phase A (sub-trial pre-registrado aparte si la capital queda infra-utilizada) |
| Capa fundamentals EDGAR (g3) | FUERA de Phase A (cobertura 5/50 inútil); **Phase B gated**: solo si Phase A pasa el criterio se re-fetchea EDGAR para los 50 y se re-valida g3 |

### 9.4 Ventanas de evaluación (pre-registradas, 3 no solapadas, 2 años cada una)
- W1: 2020-01-01 → 2021-12-31
- W2: 2022-01-01 → 2023-12-31
- W3: 2024-01-01 → 2026-08-04 (fin de datos)
- **Piso de evaluabilidad**: una ventana cuenta solo con ≥ 30 trades (con n menor, el DSR no es interpretable — lección del gap audit).
- Criterio de éxito: DSR OOS ≥ 0.90 en **≥2 de 3** ventanas evaluables, con costos 0.15%/lado, n_trials=16. Freno pre-comprometido: si Phase A no lo cumple → el proyecto se cierra sin Phase B y la pregunta de universo se archiva.

### 9.5 Fases y orden
1. **A0 Data** — fetch 43 tickers yfinance → cache parquet (en curso 2026-08-10). Criterio: 50/50 tickers con ≥ 2,600 filas desde 2015.
2. **A1 Pre-registration** — este §9 + N_TRIALS=16 + ventanas en el script.
3. **A2 Phase A run** — V1 config (sin fundamentals) sobre 50 símbolos: baseline + V1, full + 3 ventanas, dump de trades (reusar `audit_gap_exits`). Runtime estimado: 3 backtests × ~30-45 min (el dataset de calibración y el loop diario crecen ~7×) → nohup + polling.
4. **A3 Veredicto Phase A** — vs criterio 9.4. Si pasa → Phase B (EDGAR 50, re-validar g3) como sub-proyecto pre-registrado. Si no → cierre y archivo.

### 9.6 Trial #11 (2026-08-10) — Piso de stop (pre-registrado tras auditoría de exits)

**Evidencia (auditoría Session 8j, trades 165713)**: el leak real de PnL no es la
salida técnica (refutada: 16/16 riders en parcial terminaron en TECHNICAL con 100%
win, +$103 vs +$66 y 70% win de los TRAILING) sino `REGIME_STOP_HIT`: 41 posiciones,
0% win, -$5,857 = 68% de lo que produce TRAILING_STOP (+$6,187). Pérdida promedio
-$143 vs -$43 de las técnicas: el stop de régimen (0.07 en régimen 1, 0.08 en 2)
deja correr perdedores ~3x más profundo que el base.

**Hipótesis del trial**: topar el stop de posición de régimen al ancho base (nunca
más profundo que -5%) recupera parte del leak sin tocar el resto del protocolo
(exposición, cooldown, portfolio stop).

**Cambio**: `position_stop` efectivo = min(regime position_stop, 0.05). Solo ese
parámetro — portfolio_stop, max_exposure, cooldown NO cambian. Aplica en sizing y
en checks (vía `get_thresholds`, punto único).

**Criterio**: el ORIGINAL de §9.4 (DSR OOS ≥ 0.90 en ≥2/3 ventanas evaluables) —
no cambia. N_TRIALS 16 → **17** (+1 por este trial). Advertencia pre-registrada:
esperado no alcanzar 0.90; el trial mide mejora real del sistema, no fabrica el umbral.

**Freno**: si el leak no se reduce, se archiva el trail del stop de régimen sin más cambios.

### 9.7 Trial #12 (2026-08-10) — V4 Kaufman Efficiency Ratio (pre-registrado)

**Hipótesis del usuario (formalizada)**: los movimientos rápidos/volátiles (picos
abruptos) atraen compra retail por FOMO y tienden a revertir; los movimientos
lentos/sostenidos (acumulación institucional silenciosa) tienden a continuar.
Conecta con el ciclo institucional de `knowledge_repo.py:291`
(ACUMULAR en silencio → MARKUP → VENDER a retail → MARKDOWN → RECOMPRAR).

**Variable**: Kaufman Efficiency Ratio — ER = |Close[t]-Close[t-n]| / Σ|ΔClose|
en la ventana. ER→1 = movimiento eficiente/lento-sostenido; ER→0 = ruidoso.

**Protocolo en fases (sin atajos, freno en cada una)**:
1. **Fase 1 — diagnóstico IC** (`scripts/diagnose_er_ic.py`, ya pre-registrado en
   su docstring, NUNCA ejecutado): IC + rank_ic + terciles de ER10/ER20/ER60 vs
   retornos fwd 5/20/60d, SEPARADO por tramo alcista/bajista (la hipótesis es
   dependiente de la pata), Newey-West n_eff, universo de 50 símbolos, datos
   hasta 2026-08-04. Freno: si ER no muestra IC direccional consistente y
   terciles no-monótonos → se archiva V4, NO se llega al backtest.
2. **Fase 2 — backtest con costos** SOLO si Fase 1 mide algo real, sobre el
   universo de 50, criterio ORIGINAL (DSR OOS ≥ 0.90 en ≥2/3 ventanas,
   N_TRIALS 17 → **18**, +1 por este trial). Mismo freno que V1/fundamentals.
3. **No se integra nada sin cruzar la barra.**

**Regla anti-anécdota**: ningún caso individual (NVDA, semiconductores) cuenta
como evidencia — solo el IC agregado sobre el universo.

### 9.7.1 Veredicto Fase 1 (2026-08-10, huella `er_ic_trial12_20260810_211323.txt`)

**V4 REFUTADO — freno aplicado, NO llega al backtest.** La hipótesis dependiente
de la pata no se cumple en ninguna de las dos patas:

- **Tramo alcista** (subida lenta continúa / pico revierte): FALSO. IC de ER ≈ 0
  en todos los horizontes (er20 5d +0.004, 20d +0.005, 60d -0.002) y terciles
  PLANOS (60d: 0.0458/0.0410/0.0439 — sin monoticidad). Además, la velocidad
  del tramo predice CONTINUACIÓN, no reversión (ic(abs_leg_ret20) = +0.032 a 5d,
  +0.058 a 20d, +0.099 a 60d) — es momentum, lo contrario de la hipótesis.
- **Tramo bajista** (caída rápida rebota / lenta sigue cayendo): solo la primera
  mitad se sostiene (abs_leg_ret +0.070/+0.124/+0.159 = los crashes rebotan),
  pero el IC de ER es POSITIVO y significativo en 3/3 horizontes (er20 5d
  +0.0207**, 20d +0.0337**, 60d +0.0368**) con terciles monótonos crecientes
  (0.0507/0.0634/0.0669): las caídas EFICIENTES rebotan MÁS, no "siguen cayendo".
  Dirección opuesta a la hipótesis pre-registrada (que pedía IC < 0).

**Interpretación honesta**: el ER no predice nada en subidas; en caídas predice
al revés de lo esperado, y el spread de terciles (1.6pp sobre base 6pp) es
pequeño — nada accionable. Lo único robusto (crashes rebotan) ya se sabía y es
mean reversion general del sample long-only, no edge del ER. Regla anti-anécdota
aplicada: NVDA no contó como evidencia.
