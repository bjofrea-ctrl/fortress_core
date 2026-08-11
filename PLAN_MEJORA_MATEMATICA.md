# Plan de mejora matemática — arquitectura, no variables

Este documento consolida: el inventario de técnicas propuesto por OpenCode (§1), la
evaluación crítica de Claude Code (§2), la auditoría académica independiente que encontró
3 bugs de flujo + confirmó 1 de ejecución (§3), y el plan de fases consolidado con
cronograma (§4). Sigue la misma disciplina del proyecto: diagnóstico antes que trial,
nada quema `n_trials` hasta demostrar valor OOS, y ningún bug de flujo se ignora aunque
el hallazgo que produjo sea "interesante".

Ver también: `RESUMEN_VALIDACION_VARIABLES.md`, `SESSION_LOG.md` (historial completo).

---

## 1. Antecedentes — inventario de OpenCode (2026-08-11)

**Ya cubierto en el proyecto**: Platt/Isotonic · Kelly fraccional · IC/RankIC/ICIR +
n_eff Newey-West · Beta-Bernoulli online (BMA) · t-Student MC + Cornish-Fisher · cópulas
Clayton/Gumbel por pares · walk-forward · HMM de régimen (`hmmlearn`) · PBO/CSCV · DSR
con n_trials · Diebold-Mariano · purged CV · ridge (combinación de señales).

**Brecha propuesta — Tier A:**

| # | Técnica | Aporte | Esfuerzo |
|---|---|---|---|
| A1 | Random Matrix Theory (Marchenko-Pastur) | Matriz de correlación del universo 50 limpia de ruido | Bajo |
| A2 | Extreme Value Theory (GPD, POT) | VaR/ES de cola estimado de datos reales, no `dof` fijo | Bajo |
| A3 | Bayesian Optimization (GP + EI) | Elegir próxima configuración por información esperada | Medio |
| A4 | Kalman Filter / DLM | Detectar decaimiento de IC en vivo | Medio-bajo |

**Tier B (deprioritizada)**: bootstrap estacionario, transfer entropy, vine copulas, HMM
t-Student, White's Reality Check/Hansen SPA — PBO/CSCV + DSR ya cubren esa clase de error.

---

## 2. Evaluación crítica (Claude Code, primera pasada)

De acuerdo con A1/A2 sin reservas. **Reparo en A3**: con ~16 trials heterogéneos
(hipótesis estructuralmente distintas, no puntos de un mismo espacio continuo), un GP no
tiene datos suficientes para elegir entre categorías — se reencuadra como herramienta de
tuning fino *dentro* de un enfoque ya validado, no de selección de dirección de
investigación. A4 se secuencia después de que cross-sectional/RMT definan "la señal" a
monitorear.

---

## 3. Auditoría académica independiente — 3 bugs de flujo + 1 de ejecución confirmado

Una segunda revisión completa de archivos encontró problemas que invalidan parcialmente
resultados ya reportados como positivos. Se documentan íntegros porque cambian qué se
puede confiar del inventario de §1 hecho hasta ahora.

### 3.1 — Lookahead en el régimen del panel (`build_factor_panel.py:101`) — CRÍTICO

```python
regime_state = int(regime_clf.predict_current_regime(market_data)["state"])
```

`market_data` se pasa completo (hasta 2026-08-04), no cortado en `date`. Como
`predict_current_regime` lee `aligned[-1]`, **cada fila del panel recibe el régimen del
último día de toda la serie**, no el de su propia fecha. Evidencia: runs de régimen de
~63 días exactos (la cadencia de refit), no de duración de régimen real.

**Invalida**: el hallazgo "macro es contra-régimen" (+0.198 GOLDILOCKS / −0.173
DEFLATION) y "score del motor estable en los 4 regímenes" — ambos basados en etiquetas
mal asignadas. **No afecta**: el backtest/DSR/trades reales, que sí cortan bien en
`backtest_engine.py` líneas 381-383.

### 3.2 — IC macro +0.13 es in-sample por diseño

Los pesos del macro compuesto (0.2588/0.4543/0.2869) se calibraron proporcional a \|IC\|
**en la misma ventana** (2019-2024, 7 símbolos) donde después se reportó ese +0.13 como
evidencia. Medido en el panel amplio (2019-2026, 50 símbolos, con gate): **IC pooled =
−0.0247** — cambia de signo. Es sesgo de selección clásico: pesos elegidos y performance
reportada sobre el mismo dato.

### 3.3 — El blend de comparación del trial de ridge tiene IC pooled negativo

Con macro al 57.5% del peso normalizado y su IC pooled negativo, el blend usado como
línea de base en el trial de ridge da IC −0.0129. **Momentum+RSI solos (sin macro) dan
+0.0502 — mejor que el blend "completo".** El ridge (+0.0156) le gana a un punto de
comparación roto, no necesariamente tiene edge en términos absolutos. El gate de ese
trial no es confiable tal como corrió.

### 3.4 — Bug de ejecución PARTIAL_TP: confirmado con timestamps exactos

Independientemente identificado por Claude Code (sección de confusores arquitectónicos,
`RESUMEN_VALIDACION_VARIABLES.md` §6.1) y ahora confirmado con archivos: trial #8 (AAII,
huella `091011`, 10-ago 09:10) y trial #9 (fundamentales, huella `120906`, 12:09) corrieron
**antes** del fix (commit `0e934cc`, 13:42). Sus métricas de P&L están contaminadas; el
IC/Brier de señal sobrevive.

**Discrepancia sin resolver**: "PF 1.46→2.35" fue relayado sin verificar contra archivo.
`SESSION_LOG.md` (sesión 8i) registra 1.30→1.46 sobre 7 símbolos; el 2.35 pudo
corresponder a la corrida de universo 50 (sesión 8j), pero no se confirmó la ruta exacta
del artefacto para cada número. **Pendiente de reconciliar antes de usar cualquiera de
los dos.**

### 3.5 — Hallazgo académico: rank IC de momentum ~0 (posible timing, no selección)

| Factor | IC pooled (Pearson) | rank_ic pooled (Spearman) |
|---|---|---|
| momentum_score | +0.0325 | **−0.0081** |
| rsi_score | +0.0454 | +0.0380 |
| score motor | +0.0502 | +0.0291 |
| macro_composite | −0.0247 | −0.0226 |

Si se confirma, el momentum funciona como señal de timing (long/flat según condición de
mercado), no como ranking cross-sectional entre activos — explicaría W3 (bull, momentum
como timing) vs W2 (mixto, sin ranking que ayude). **Esto viene del mismo panel con el
bug §3.1 confirmado en otra columna — se acepta como hipótesis fuerte, no como hecho,
hasta reproducirlo en un panel limpio.**

### 3.6 — Validación cruzada de los demás rechazos: sostienen

ER, pares/cointegración, stops, Bollinger, Fama-French, score+macro, dirección de
sentimiento — revisados contra artefactos, veredictos correctos y reproducibles. El
problema es específico a régimen/macro/ridge, no generalizado a toda la sesión.

---

## 4. Plan de fases consolidado, con cronograma

**Cambio de orden respecto a la versión anterior**: nada de RMT/EVT ni cross-sectional
corre sobre el panel actual hasta que §3.1-§3.3 estén arreglados — construir sobre un
panel con lookahead confirmado invalidaría cualquier resultado nuevo antes de empezar.

```mermaid
gantt
    title Plan de mejora matemática — fortress_core (consolidado post-auditoría)
    dateFormat X
    axisFormat Sesión %d

    section Fase -1 — Bugs de flujo (bloquea todo lo demás)
    Fix lookahead regimen panel (3.1)       :crit, f1, 0, 1d
    Re-derivar pesos macro walk-forward (3.2) :crit, f2, after f1, 1d
    Reconciliar PF 1.46 vs 2.35 (3.4)       :f3, 0, 1d
    Gate: panel limpio                       :milestone, gate0, after f2, 0d

    section Fase 0 — Re-correr sobre panel limpio
    Re-correr trial ridge vs blend arreglado :rr1, after gate0, 1d
    Reproducir rank_ic momentum (3.5)        :rr2, after gate0, 1d
    Gate: veredicto ridge confiable          :milestone, gate1, after rr1, 0d

    section Fase 0.5 — Re-test variables (arquitectura corregida)
    Re-test sentimiento (motor+universo50)   :rt1, after gate0, 1d
    Re-test fundamentales (motor+universo50) :rt2, after rt1, 1d

    section Fase 1 — Señal y riesgo (Tier A1/A2)
    A1 RMT Marchenko-Pastur                  :a1, after gate1, 1d
    A2 EVT/GPD cola                          :a2, after a1, 1d
    Gate: integrar si mejora VaR/ES real     :milestone, gate2, after a2, 0d

    section Fase 2 — Monitoreo y tuning (Tier A4/A3)
    A4 Kalman/DLM IC en vivo                 :a4, after gate2, 1d
    A3 GP-BO re-especificado (tuning fino)   :a3, after a4, 1d

    section Producto (paralelo, no bloquea investigación)
    Endpoint + dashboard oportunidades       :done, p1, 0, 1d
    Telegram + correo                        :p2, after p1, 1d
```

### Detalle por fase

**Fase -1 — Bugs de flujo** (nueva, máxima prioridad, bloquea todo lo de investigación)
1. Fix `build_factor_panel.py`: cortar `market_data` en `date` antes de pasarlo a
   `predict_current_regime`, igual que ya hace `backtest_engine.py`.
2. Re-derivar pesos del macro compuesto con calibración walk-forward/OOS, no in-sample.
3. Reconciliar el PF 1.46 vs 2.35 con ruta exacta de artefacto para cada número.

**Fase 0 — Re-correr sobre panel limpio**
El trial de ridge se re-ejecuta contra un blend de comparación arreglado (macro
re-ponderado). Sólo con esto el gate es confiable. Se reproduce el rank_ic de momentum
en el panel ya corregido, sin el bug de régimen contaminando otras columnas.

**Fase 0.5 — Re-test de variables refutadas** (sin cambios respecto al plan anterior)
Sentimiento y fundamentales se refutaron con ejecución rota y 7 símbolos. Re-correr
contra el motor actual antes de cerrarlas para siempre.

**Fase 1 — RMT + EVT** (Tier A1, A2)
Sin cambios de alcance, pero ahora corre sobre un panel ya validado por Fase -1/0.

**Fase 2 — Kalman + GP-BO re-especificado** (Tier A4, A3)
Sin cambios respecto al plan anterior.

**Producto** (paralelo, no bloqueado por nada de lo de arriba)
Endpoint, dashboard, Telegram + correo — sigue su camino independiente.

---

## 5. Disciplina que se mantiene sin excepción

- Ningún resultado de un panel con bug de flujo conocido se usa para decidir nada hasta
  que el bug esté arreglado y el resultado reproducido.
- Todo diagnóstico corre antes que cualquier trial de motor.
- Ningún trial se dispara sin criterio pre-registrado (mismo DSR≥0.90, mismas ventanas).
- `n_trials` se actualiza con cada trial real, no con diagnósticos.
- Ningún número se relaya sin verificar contra su artefacto — la discrepancia del PF fue
  exactamente el costo de no hacerlo una vez.
