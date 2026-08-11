# Plan de mejora matemática — arquitectura, no variables

Consolida: inventario de OpenCode (§1), evaluación crítica de Claude Code (§2),
auditoría académica independiente #1 con 3 bugs de flujo + 1 confirmado de ejecución
(§3), correcciones de auditoría académica independiente #2 (§4), y plan de fases
consolidado con cronograma (§5).

Ver también: `RESUMEN_VALIDACION_VARIABLES.md`, `SESSION_LOG.md`.

---

## 1. Antecedentes — inventario de OpenCode

**Ya cubierto**: Platt/Isotonic · Kelly fraccional · IC/RankIC/ICIR + n_eff Newey-West ·
Beta-Bernoulli online (BMA) · t-Student MC + Cornish-Fisher · cópulas Clayton/Gumbel por
pares · walk-forward · HMM de régimen · PBO/CSCV · DSR con n_trials · Diebold-Mariano ·
purged CV · ridge.

**Brecha — Tier A**: A1 Random Matrix Theory · A2 Extreme Value Theory · A3 Bayesian
Optimization · A4 Kalman Filter/DLM. **Tier B deprioritizada**: bootstrap estacionario,
transfer entropy, vine copulas, HMM t-Student, White's Reality Check/Hansen SPA.

---

## 2. Evaluación crítica (primera pasada)

De acuerdo con A1/A2. A3 reencuadrado como tuning fino dentro de un enfoque ya validado
(con ~16 trials heterogéneos, un GP no puede elegir entre categorías estructuralmente
distintas). A4 depende del veredicto de señal, no de EVT (ver ajuste 2.1 más abajo).

---

## 3. Auditoría académica independiente #1 — 3 bugs de flujo + 1 de ejecución

**3.1 Lookahead en régimen del panel** (`build_factor_panel.py:101`, CRÍTICO): pasa
`market_data` completo en vez de cortado en `date` → cada fila recibe el régimen del
último día de toda la serie. Invalida "macro contra-régimen" y "score estable en 4
regímenes". No afecta el backtest real.

**3.2 IC macro +0.13 in-sample**: pesos calibrados y evaluados en la misma ventana. En
panel amplio: IC pooled = −0.0247, cambia de signo.

**3.3 Blend de comparación del ridge, roto**: macro al 57.5% con IC negativo → blend de
referencia da IC −0.0129. Momentum+RSI solos: +0.0502. Gate del ridge no confiable.

**3.4 PARTIAL_TP confirmado con timestamps**: trials #8/#9 corrieron antes del fix
(commit `0e934cc`, 13:42). PF 1.46 vs 2.35 sin reconciliar contra artefacto.

**3.5 Rank IC de momentum ~0**: hipótesis fuerte de que momentum es timing, no selección
— pero corregido en §4.1, el test pooled no es el correcto para esta pregunta.

**3.6 Los demás rechazos sostienen**: ER, pares, stops, Bollinger, Fama-French,
score+macro, dirección de sentimiento — verificados, correctos.

---

## 4. Auditoría académica independiente #2 — 3 correcciones + 1 implicación estratégica

### 4.1 — rr2 estaba mal especificado (la corrección más importante)

El rank_ic **pooled** del panel (concatenando 2069 filas de 50 símbolos) mezcla la
dimensión temporal con la transversal: si momentum sube para *todos* los símbolos el
mismo día (rally de mercado), infla el Spearman pooled sin que exista jerarquía
intra-día real. **El test correcto es rank IC intra-día**: por cada fecha elegible,
rankear los símbolos disponibles por momentum, correlacionar con retorno 20d adelante,
promediar sobre fechas con error Newey-West. Redefine rr2 completo — el pooled no
decide nada sobre W2 vs W3.

### 4.2 — RMT sube de Fase 1 a Fase 0.5, como sonda conjunta con rr2

RMT no es sólo "riesgo" — es la sonda directa de si hay estructura cross-sectional real.
Matriz 50×50 de retornos estandarizados, `λ₊ = σ²(1+√q)²` con `q=N/T≈0.026` → autovalores
sobre el umbral son factores reales, el resto es ruido. Si salen 3-6 factores con uno
dominante (mercado), el plano de selección es chico independientemente del rank IC.

**Caveat de diseño**: estandarizar por ventanas rodantes; sacar el factor de mercado
(PCA) antes de aplicar Marchenko-Pastur sobre la matriz residual — si no, el autovalor
del mercado (siempre enorme) contamina el conteo de factores idiosincráticos.

rr2 (rank IC intra-día) + RMT (conteo de factores) corren en paralelo en Fase 0.5, con
veredicto conjunto como gate formal antes de Fase 1.

### 4.3 — §3.2 se resuelve mejor con macro crudo al ridge, no re-ponderación

Re-derivar sólo los 3 pesos del composite deja intactos los umbrales internos de cada
regla (también tuneados in-sample) — de-biasing a medias. **Mejor**: alimentar al ridge
las 3 componentes macro crudas como features separadas. El ridge pondera por datos, no
por \|IC\| in-sample, y mata §3.3 de raíz (macro ya no puede dominar el blend por diseño
manual). El composite walk-forward-ponderado queda como fallback sólo para el motor de
producción (si se quiere un único `macro_score` interpretable en el dashboard), no para
el diagnóstico.

### 4.4 — Ajustes menores aceptados

1. **A4 (Kalman) no depende de EVT** — depende del veredicto de señal (gate de Fase
   0.5): necesita saber *qué* IC monitorear antes de monitorearlo. Se mueve a
   inmediatamente después del gate de Fase 0.5, no después de EVT.
2. **GP-BO: cada evaluación cuenta como trial** para el DSR — 30 iteraciones = +30 a
   `n_trials`. La config final se valida en una ventana fresca no usada por el BO, o el
   DSR queda inflado por el propio proceso de búsqueda.
3. **EVT sobre retornos de activos** (idealmente residuales GARCH-filtrados, McNeil-Frey
   — no GPD directo sobre retornos crudos), **no sobre P&L de estrategia**: con 100-500
   trades el umbral POT deja sólo 10-20 excesos, insuficiente para un ajuste GPD
   confiable.
4. **Reconciliar UN baseline post-fix limpio para toda la serie de trials**, no sólo el
   par 1.46/2.35 — distintos trials compararon contra baselines de distintos estados
   pre/post-fix.
5. **Producto**: se puede construir la UI en paralelo, pero **no cablear señales en vivo
   hasta pasar el gate de Fase 0.5** — el blend actual tiene IC negativo; mostrarlo como
   sugerencia real sería activamente engañoso.

### 4.5 — La implicación estratégica que el plan no nombraba

Si rr2 + RMT confirman conjuntamente **W2 (timing, no selección)** — el resultado más
probable dado lo ya medido —, entonces rankear 50 símbolos con rank IC ~0 es selección
sin sustancia: un overlay de momentum/RSI sobre un solo basket/ETF lograría un P&L
similar con menos fricción, menos costos, menos superficie de error. Esto no es "cambiar
el motor ahora" — es que el plan necesita un **gate explícito** en Fase 0.5: si sale W2,
el siguiente paso no es continuar con RMT-para-riesgo/EVT/Kalman sobre la arquitectura
actual, es **re-evaluar si el producto debe ser selección de 50 símbolos o timing sobre
un basket** — una pregunta de producto, no de matemática adicional. Si sale W3, Fase
1/2 tal como estaban planificadas es lo correcto.

---

## 5. Plan de fases consolidado, con cronograma

```mermaid
gantt
    title Plan de mejora matemática — fortress_core (v3, post 2 auditorías)
    dateFormat X
    axisFormat Sesión %d

    section Fase -1 — Bugs de flujo (bloquea todo)
    Fix lookahead regimen panel (3.1)         :crit, f1, 0, 1d
    Macro crudo al ridge, no re-peso (4.3)    :crit, f2, after f1, 1d
    Reconciliar UN baseline limpio (4.4.4)    :f3, 0, 1d
    Gate: panel limpio                         :milestone, gate0, after f2, 0d

    section Fase 0.5 — Sonda conjunta W2 vs W3
    rr2 rank IC intra-día + Newey-West (4.1)  :rr2, after gate0, 1d
    RMT Marchenko-Pastur, market-mode fuera (4.2) :rmt, after gate0, 1d
    Re-correr ridge (macro crudo)              :rr1, after gate0, 1d
    Gate: veredicto W2 vs W3                   :milestone, gatew, after rr2, 0d

    section Rama W2 (si timing, no selección)
    Re-evaluar arquitectura: selección vs basket :branch, after gatew, 1d

    section Fase 0.6 — Re-test variables (paralelo)
    Re-test sentimiento (motor+universo50)     :rt1, after gate0, 1d
    Re-test fundamentales (motor+universo50)   :rt2, after rt1, 1d

    section Fase 1 — Riesgo (si W3, o en paralelo a la rama W2)
    A2 EVT/GPD sobre activos, no P&L (4.4.3)  :a2, after gatew, 1d
    Gate: integrar si mejora VaR/ES real       :milestone, gate2, after a2, 0d

    section Fase 2 — Monitoreo y tuning
    A4 Kalman/DLM (depende del veredicto de señal) :a4, after gatew, 1d
    A3 GP-BO (cada iter = trial, val. en ventana fresca) :a3, after a4, 1d

    section Producto
    UI/dashboard (sin datos en vivo)           :done, p1, 0, 1d
    Cablear señal en vivo                      :p2, after gatew, 1d
    Telegram + correo                          :p3, after p2, 1d
```

### Detalle por fase

**Fase -1 — Bugs de flujo** (bloquea todo lo de investigación)
1. Cortar `market_data` en `date` en `build_factor_panel.py`.
2. Alimentar al ridge las 3 componentes macro crudas, no el composite re-ponderado.
3. Un baseline post-fix único, documentado, para toda comparación de trials futura.

**Fase 0.5 — Sonda conjunta W2 vs W3** (reemplaza la vieja "Fase 0" y absorbe RMT)
rr2 (rank IC intra-día, correctamente especificado) + RMT (conteo de factores reales,
con el mercado removido) corren en paralelo, junto con el re-run del ridge sobre macro
crudo. El gate de esta fase **decide la rama siguiente**, no sólo si "pasa o no pasa".

**Rama W2** (nueva, condicional): si el veredicto es timing-no-selección, el siguiente
trabajo es de producto/arquitectura, no más matemática sobre el diseño actual.

**Fase 0.6 — Re-test de variables refutadas** (sin cambios): sentimiento y fundamentales
contra el motor actual + universo 50, en paralelo a Fase 0.5.

**Fase 1 — EVT** (RMT ya no está acá, se movió a 0.5): sobre retornos de activos
(idealmente residuales GARCH), nunca sobre la serie de P&L del motor.

**Fase 2 — Kalman + GP-BO**: Kalman depende del veredicto de señal, no de EVT. GP-BO
cuenta cada iteración como trial y valida la config ganadora en ventana no vista por la
búsqueda.

**Producto**: la UI se construye en paralelo desde ya, pero el cableado de señal en vivo
espera al gate de Fase 0.5 — no se muestra como sugerencia real un blend con IC negativo.

---

## 6. Disciplina sin excepción

- Ningún resultado de un panel con bug de flujo conocido decide nada hasta reproducirse
  arreglado.
- El test de cross-sectional es intra-día con Newey-West, no pooled — un pooled no
  responde la pregunta de selección vs timing.
- Todo diagnóstico corre antes que cualquier trial de motor.
- Ningún trial sin criterio pre-registrado (DSR≥0.90, mismas ventanas).
- `n_trials` cuenta cada trial real, incluidas las iteraciones de búsqueda automática
  (GP-BO).
- Ningún número se relaya sin verificar contra su artefacto.
- Ninguna señal en vivo se muestra al usuario antes de pasar el gate de señal (Fase 0.5).
