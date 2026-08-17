# Resumen de validación de variables — fortress_core

Documento de síntesis pedido por el usuario (2026-08-11), consolidando todo lo probado
en las sesiones 8a-8k+ del `SESSION_LOG.md`. Ver ese archivo para el detalle completo
de cada trial; acá sólo el veredicto y la evaluación de confusores arquitectónicos.

## 1. Nominales positivos — ACTUALIZADO 2026-08-17 (antes: "Válido por sí solo")

| Factor | IC medido | Estado real (tras §21/§21.1/§25/§26) |
|---|---|---|
| Momentum (12m-1m) | +0.064 (pooled) | Walk-forward por ventana y horizontes 5d-125d: **0 cruces** Bonferroni en todos los tests (§21/§21.1). Nominal pooled, no robusto OOS. Sigue en producción como parte del gate/blend |
| RSI (zona 45-70) | +0.032 (pooled) | Ídem; semanal §26: máx |t| 0.44, sin señal alguna |
| Macro compuesto (DXY/oro, petróleo, SPY invertido) | +0.13 (pooled); contra-régimen (+0.198 GOLDILOCKS) | Como score de motor: trial #13 DSR 0/3; como compuerta: probada dos veces, cerrada. IC más alto medido pero nunca tradujo en DSR |

Lectura honesta (corrección del 2026-08-17): estos ICs sobrevivieron Newey-West **pooled**
(toda la muestra junta), pero los re-tests por ventana OOS (§21/§21.1: horizontes; §25:
ADX como patrón de ventana) muestran que la significancia pooled era señal débil
repartida, no una señal que se sostenga en aislamiento. Ninguno es "válido por sí solo"
bajo la vara actual del proyecto; siguen en producción porque el baseline (que los
incluye) es el único modo de operación documentado, no porque cada uno esté validado
aisladamente. Ninguno solo, ni el blend original, cruzó DSR≥0.90.

## 2. Refutado con rigor — no aporta (tal como se probó)

| Idea | Trial | Resultado |
|---|---|---|
| Sentimiento AAII (V1, ranking H7) | #8 | OOS Sharpe -0.60→-0.72 (empeora), DSR p=0.164 |
| Fundamentales EDGAR (15 ratios point-in-time) | #9 | OOS DSR 0.034, sin edge neto |
| Efficiency Ratio / velocidad (V4, Kaufman) | #12 | IC≈0 en subidas; signo invertido en bajadas |
| Piso de stop de régimen | #11 | Empeoró el sistema (W3 DSR 0.234→0.058) |
| Gate técnico suelto | (pre-trial) | Momentum fuera del gate = ruido puro (IC 0.004) |
| Pares/cointegración (universo 50) | Fase 4 | 1225 pares, mejor 47%, media 18.1% — no cointegran |
| ADX, trend como factor ponderado | auditoría original + §25 (2026-08-17) | ADX IC **POSITIVO** +0.0679 (t+2.31, §0.5a) pero marginal-no-robusto: §25 walk-forward OOS 0/3 ventanas (t +0.79/+1.54/+1.47, Bonf-9 2.77). Trend constante entre elegibles (no discrimina). Ambos siguen como gates duros, no como peso |
| BULL rsi, BEAR trend/momentum | auditoría triad | Invertidos, corregido el signo |
| **ridge_3f como score del motor** (momentum+RSI+macro vía ridge) | #13 | DSR 0/3 ventanas (0.054/0.001/0.180 vs baseline 0.071/0.028/0.173) — IC mejor no se tradujo en PnL; revert aplicado, motor sigue en #10/V1 |

## 3. Mejora en combinación, no probado solo

- **Ridge purgado (momentum+RSI+macro)**: IC OOS +0.0156, ICIR 0.78, +0.0285 sobre el blend
  simple por \|IC\|. Factores poco correlacionados (\|ρ\|<0.3). **Trial #13 (2026-08-11) lo
  probó como score real del motor y lo refutó** (0/3 ventanas DSR, ver tabla arriba) — el IC
  mejor no sobrevivió gates/sizing/costos/salidas. No re-intentar hasta que el gate de Fase
  0.5 del `PLAN_MEJORA_MATEMATICA.md` resuelva W2 vs W3, y sólo si sale W3 (el ridge de este
  trial se entrenó con macro composite + IC pooled, ambos corregidos en esa fase).
- **BMA (BayesianOnlineUpdater)**: no es un factor, es el método que pondera los existentes
  con evidencia online en vez de un número fijo.

## 4. El hallazgo de mayor impacto no fue estadístico — fue un bug

`PARTIAL_TP` se re-disparaba todos los días mientras `price-entry ≥ 2×ATR` (sin flag),
vendiendo 50%→25%→12.5%... y generando filas fantasma (shares=0, pnl=0) que contaminaban
win_rate (0.36 reportado vs 0.65 real) y conteo de trades (340 reportado vs 91 posiciones
reales). Arreglarlo (trial #10) subió PF de 1.30 a 1.46 sólo con el fix de reporting honesto.
Ninguna variable nueva tuvo ese impacto.

## 5. Pendiente de probar

| Idea | Estado |
|---|---|
| **Cross-sectional / rank IC** (alpha relativo vs beta) | Propuesta, no corrida — la más prometedora sin probar |
| Cálculo de límite de capacidad (frecuencia vs eficiencia) | Propuesto, chico, no corrido |
| Volatility targeting a nivel portafolio | `TARGET_VOLATILITY` existe en `.env`, sin conectar |
| Matriz de covarianza completa (extensión de cópulas) | Propuesto |
| Long-short / market-neutral | Decisión de producto pendiente (riesgo distinto: shorts reales) |
| Shrinkage Ledoit-Wolf en el blend | Redundante parcial con ridge — esperar backtest de motor primero |
| IC condicional por régimen del motor completo | Corrido (Fase 2): score estable en los 4 regímenes, pero **macro es contra-régimen** (+0.198 GOLDILOCKS, -0.173 DEFLATION) — hallazgo capturado implícitamente por ridge |

## 6. Confusores arquitectónicos identificados (evaluación pedida por el usuario)

### 6.1 — CONFIRMADO por cronología: sentimiento y fundamentales se probaron sobre una ejecución rota y un universo chico

Reconstruyendo el orden real de sesiones en `SESSION_LOG.md`:

- **Trial #8** (sentimiento, sesión 8g) y **Trial #9** (fundamentales, sesión 8h) corrieron
  **ANTES** del fix de `PARTIAL_TP` (sesión 8i, trial #10) y **ANTES** de la expansión de
  universo a 50 símbolos (sesión 8j).
- Eso significa que sus métricas de Sharpe/DSR se calcularon sobre una lista de trades
  contaminada por filas fantasma (52% de las filas eran `shares=0, pnl=0` en el dataset
  de fundamentales) y sobre sólo 7 símbolos (9-15 trades OOS — la propia auditoría 8i
  concluyó que con esa frecuencia el criterio DSR≥0.90 es "estructuralmente inalcanzable").
- **Conclusión honesta**: no sabemos si sentimiento o fundamentales fallaron por ser
  variables sin valor, o porque se midieron con una vara rota y sin poder estadístico
  suficiente. **Ninguna de las dos se volvió a probar contra el motor actual (trial #10
  + universo 50).** Es un re-test legítimo y barato (no consume una hipótesis nueva,
  es corregir la misma pregunta con la ejecución ya arreglada) antes de darlas por
  cerradas para siempre.

### 6.2 — Todas las IC midieron dirección absoluta, no habilidad relativa

Cada IC de este documento (momentum, RSI, macro, sentimiento, ER, fundamentales) responde
"¿esto sube en términos absolutos?" — mezcla habilidad de selección (alpha) con dirección
del mercado (beta). Con base_rate de "sube" colapsando a 0.375 en OOS 2025-26, cualquier
variable con habilidad de selección real pudo mostrar IC débil o negativo simplemente
porque el mercado no acompañó. La propuesta de IC cross-sectional (rank relativo al
universo, sección 5) ataca esto directamente y podría cambiar la lectura de #2 y #3.

### 6.3 — El gate duro nunca se testeó variable por variable

Se confirmó que el gate CONCENTRA señal en agregado (IC momentum dentro del gate muy
superior a fuera). Pero cada variable individual (sentimiento, fundamentales, ER) se
testeó siempre YA condicionada al gate — nunca se midió si alguna de ellas tiene valor
específicamente fuera de la población que el gate selecciona (por ejemplo, para detectar
salidas o para un contexto de mercado que el gate excluye por diseño).

## Recomendación

Antes de sumar variables nuevas: re-testear sentimiento y fundamentales contra el motor
actual (trial #10, universo 50) es más barato y más honesto que descartarlas
permanentemente sobre una medición que ahora sabemos que estaba distorsionada.
