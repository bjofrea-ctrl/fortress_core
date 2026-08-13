# Plan de mejora matemática — arquitectura, no variables

Consolida: inventario de OpenCode (§1), evaluación crítica de Claude Code (§2),
auditoría académica independiente #1 con 3 bugs de flujo + 1 confirmado de ejecución
(§3), correcciones de auditoría académica independiente #2 (§4), plan de fases
consolidado con cronograma (§5), evidencia post-plan de trial #13 (§6), resultado de
las Fases -1 y 0.5 con gate W2/W3 (§8), rama resultante (§9), pre-registro del
trial de basket (a) (§11), pivot a gestión de riesgo — régimen vs volatilidad (§12)
y gap reversion intra-día (§13), y disciplina (§14).

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

#### 0.6.1 PRE-REGISTRO — re-test V1 (AAII) y fundamentales (EDGAR) sobre universo 50 (Tanda D, 2026-08-12)

**Contexto (RESUMEN §6.1)**: los trials #8 (sentimiento) y #9 (fundamentales) corrieron
ANTES del fix de `PARTIAL_TP` (trial #10) y sobre universo de 7 símbolos; el panel tenía
52% de filas `shares=0/pnl=0` que contaminaban win_rate y total_trades. No sabemos si
las variables fallaron por mérito o por la vara rota. Este re-test los repite sin cambios
de hipótesis: misma pregunta, misma variable, misma construcción (G2 = 0.5*rank(técnico)
+ 0.5*(-rank(AAII)); G3 = 0.5*rank(técnico) + 0.5*rank(fundamental EDGAR)), contra el
motor ACTUAL post-fix + universo 50. Diferencias explícitas vs #8/#9: motor con
`partial_done` (trial #10), piso de stop 0.05 (trial #11), universo 50 (trial #11),
métricas con filas `shares<=0` excluidas.

**Pregunta**: con la ejecución arreglada y el universo ampliado, ¿V1 y/o fundamentales
mejoran el DSR OOS del motor por sobre el baseline post-fix documentado?

**Metodología** (`backtest_fase06_retest.py`, corre DESPUÉS de este pre-registro):
- Universo 50 (7 originales + 43 de `NEW_UNIVERSE`), 2019-01-01 → 2026-08-04,
  costos 0.10% comisión + 0.05% slippage por lado (idéntico a trial #10/#11).
- 3 corridas: baseline (sin variables) / V1-ranking (sentiment_data) /
  fundamentales (fundamentals_by_symbol, sin AAII — categoría aislada, igual que #9).
- Ventanas OOS: W1 2020-2021, W2 2022-2023, W3 2024-2026-08-04, piso ≥30 trades/ventana
  (mismas del trial #11/#13).

**Criterio (fijado ANTES de correr)**: una variante re-ingresa a consideración si DSR
OOS ≥ 0.90 (n_trials=17, registro previo — re-test barato, no consume slot nuevo, §6.1
RESUMEN) en ≥2/3 ventanas evaluables. Si no cumple: se mantiene el veredicto de refutación
de #8/#9, ahora con la vara arreglada (refutación robusta, no contaminada).

**Revert automático**: variante NO adoptada si no pasa (ningún cambio de código existe —
las variantes viven solo en el script; el motor en producción sigue en baseline).

**Riesgo declarado**: las 3 corridas comparten el mismo baseline post-fix; el valor
informativo es la comparación π(V1) − π(baseline) y π(FUND) − π(baseline) dentro del
mismo motor — no hay grados de libertad de búsqueda nuevos.

**Limitación de cobertura (declarada ANTES de leer el resultado)**: el panel EDGAR
cubre 5/50 símbolos del universo (AAPL, AMZN, GOOGL, MSFT, NVDA — los mismos 5 del
trial #9, que operaba sobre 7: allí 71% de cobertura; acá 10%). La variante FUND es
la MISMA construcción, pero con poder muy reducido: el ranking G3 solo difiere del
técnico puro en esos 5 símbolos. El criterio mecánico se aplica igual (sin alterar
umbrales), y la interpretación debe declarar este sesgo: un "NO CUMPLE" de FUND en
este re-test refuta "fundamentales con cobertura del 10% del universo", no una
refutación tan fuerte como la de V1 (que sí tiene cobertura del 100%: AAII en
2913/2913 días).

**Resultado** (`fase06_retest_20260812_175055.txt`, universo 50, motor post-fix
partial_done + piso de stop 0.05, costos 0.15%/lado; TODAS las ventanas evaluables,
n≥30 en las 9 celdas):

| ventana | DSR baseline | DSR V1 (AAII) | DSR FUND (EDGAR) |
|---|---|---|---|
| W1 2020-2021 (n 103/99/97) | 0.0714 | 0.0410 | 0.1205 |
| W2 2022-2023 (n 47/49/49) | 0.0284 | 0.0020 | 0.0043 |
| W3 2024-2026 (n 113/119/134) | 0.1727 | 0.2253 | 0.3302 |

V1: 0/3 ventanas → **NO CUMPLE**. FUND: 0/3 ventanas → **NO CUMPLE** (con la
limitación de cobertura 5/50 declarada arriba).

**Verificado contra el artefacto**: DSRs idénticos a "deflated_sharpe" del log;
win_rate V1 0.616/0.469/0.580 (vs 0.660/0.553/0.549 baseline); FUND 0.711/0.633/0.567;
Monte Carlo prob_loss: base 0.011, V1 0.040, FUND 0.004.

**Interrogatorio antes de aceptar**:
- La única variable con cobertura COMPLETA (V1/AAII 2913/2913 días) es más débil que
  el baseline en W1 y W2 — el "rescatador" de la sesión 8d no sobrevive el universo 50
  con la ejecución arreglada; con la vara arreglada, la refutación de #8 es robusta.
- FUND gana a baseline en W1/W3 (win_rate, PF, DSR, prob_loss 0.004) pero con 5/50
  símbolos el efecto no es atribuible a la categoría; y pierde en W2 (sharpe −0.54 vs
  −0.05). Sin consistencia entre ventanas → no hay señal estable, y el criterio
  pre-registrado es DSR≥0.90 en ≥2/3 (0/3 acá).
- El patrón del trial #11 histórico (universo 50 con ~0 trades post-2023) NO se repitió:
  este run sí operó W3 (n=113-134) — el re-test actual es autocontenido, pre-registrado
  y con las 9 celdas evaluables, así que el veredicto no depende de ventanas descartadas.

**Veredicto honesto**: Fase 0.6 **NO CUMPLE para ambas variantes** → la refutación de
sentimiento y fundamentales (#8/#9) queda CONFIRMADA con ejecución arreglada y universo
ampliado. Ninguna variable externa re-ingresa al motor. El baseline post-fix de
universo 50 queda como único modo de operación documentado.

**Fase 1 — EVT** (RMT ya no está acá, se movió a 0.5): sobre retornos de activos
(idealmente residuales GARCH), nunca sobre la serie de P&L del motor.

**Fase 2 — Kalman + GP-BO**: Kalman depende del veredicto de señal, no de EVT. GP-BO
cuenta cada iteración como trial y valida la config ganadora en ventana no vista por la
búsqueda.

**Producto**: la UI se construye en paralelo desde ya, pero el cableado de señal en vivo
espera al gate de Fase 0.5 — no se muestra como sugerencia real un blend con IC negativo.

---

## 6. Trial #13 — evidencia post-plan (ridge_3f como score del motor, REFUTADO)

Corrido en OpenCode el 2026-08-11, **antes** de que existieran las correcciones de §4 (rr2
intra-día, RMT a Fase 0.5, macro crudo al ridge). Huella `trial13_ridge_motor_20260811_120029.txt`,
commit `cf63e12`, verificado contra el archivo.

**Resultado**: ridge_3f (Fase 1b: momentum+RSI+macro_composite vía ridge, IC OOS +0.0156, ICIR
0.78) inyectado como score real del motor. DSR OOS, n_trials=17, criterio ≥0.90 en ≥2/3 ventanas:

| Ventana | baseline | V1 (AAII) | ridge_3f | trades ridge | ¿pasa? |
|---|---|---|---|---|---|
| W1 2020-2021 | 0.0714 | 0.0410 | 0.0538 | 118 | no |
| W2 2022-2023 | 0.0284 | 0.0020 | 0.0010 | 77 | no |
| W3 2024-2026 | 0.1727 | 0.2253 | 0.1803 | 163 | no |

0/3 → **NO CUMPLE**. Más trades (118/77/163 vs 103/47/113), win_rate similar, pero Sharpe W2
−0.820 y W3 0.554, por debajo de baseline y V1. El IC mejor no se tradujo en plata al pasar por
gates/sizing/costos/salidas. Revert pre-registrado aplicado (script borrado, producción nunca
tocada — inyección era por subclase); motor queda en trial #10/V1.

**Por qué no cierra el gate de Fase 0.5, y qué sí aporta**:
- El ridge_3f de este trial se entrenó con el macro **composite** (pesos in-sample, §3.2/§3.3) y
  su IC de referencia fue **pooled**, no intra-día (§4.1) — exactamente los dos sesgos que Fase -1
  y Fase 0.5 existen para corregir. No es la prueba limpia de W2 vs W3.
- Pero es una segunda señal independiente en la misma dirección que rr2 pooled≈0: mejorar la
  *función de combinación* (blend simple → ridge) no mejoró el resultado del motor. Eso es
  consistente con W2 (timing, no selección) — el problema no parece estar en cómo se combinan
  los factores, sino en si hay algo cross-sectional real para combinar.
- Valida el protocolo: criterio congelado antes de correr, veredicto binario, revert automático
  sin tocar producción. Mantenerlo así para Fase 0.5 y en adelante.

**Regla explícita que agrega**: no re-intentar un trial de "ridge/combinación como score del
motor" hasta que el gate de Fase 0.5 (§4.5) resuelva W2 vs W3, y sólo si el veredicto es W3. Si
sale W2, insistir con variantes de scoring/combinación sobre la arquitectura de 50 símbolos es
gastar trials en la misma pregunta que trial #13 ya sugirió que no es donde está el problema.

---

## 8. Resultado Fase -1 + Fase 0.5 — gate W2/W3 (2026-08-11)

### Fase -1 — bugs de flujo corregidos (todo verificado contra artefacto)

1. **§3.1 lookahead régimen** — corregido en `build_factor_panel.py`: `predict_current_regime`
   ahora recibe `{s: df[df.index <= date] ...}`. Impacto medido: **260/378 fechas cambiaron
   de régimen** (el bug era masivo). Panel limpio: `factor_panel_20260811_144857.parquet`.
2. **§4.3 macro crudo** — hallazgo extra de auditoría: `MARKET_TICKERS` no incluye
   DXY/gold/oil, así que el composite (y el motor) SOLO usaba SPY+TLT desde siempre.
   Corregido cargando los 3 tickers faltantes. El panel ahora expone las 4 columnas crudas
   (dxy_ret_20d, gold_ret_20d, spy_ret_50d, oil_ret_20d, 0 NaN) + composite con las 3 reglas.
3. **§4.4.4 baseline único** — `baseline_clean_20260811_150643.txt`: reproduce **1:1**
   (trades 103/47/113 baseline, 99/49/119 V1; PF 1.3785/1.0882/1.4878; DSR
   0.0714/0.0284/0.1727) la huella post-fix `universe50_phaseA_20260810_165713.txt`
   → el motor es DETERMINISTA. **Los PF 1.46 y 2.35 citados en §3.4 NO tienen artefacto
   verificable en cache** → se descartan como referencias; toda comparación futura usa
   este baseline. El 2.35 del trial #10 probablemente sea un estado pre-fix de PARTIAL_TP.

**Gate 0: panel limpio — PASADO.** (Parquets: `factor_panel_20260811_144857`,
`baseline_clean_20260811_150643` + trades/events/equity.)

### Fase 0.5 — sonda conjunta W2 vs W3 (3 sondas independientes)

**0.5a rr2 intra-día con Newey-West** (`rr2_intraday_20260811_150741.txt`, §4.1):
por fecha, Spearman entre factor y fwd 20d entre los símbolos disponibles; promedio
sobre fechas con SE Newey-West (L=4). Fechas elegibles: 346, promedio **6.0 símbolos/fecha**
(el cross-section operable real es ~6, no 50).

| factor | n_días | mean_IC | SE_NW | t | pooled | veredicto |
|---|---|---|---|---|---|---|
| momentum_score | 187 | −0.0100 | 0.0359 | −0.28 | −0.0081 | no sig |
| rsi_score | 164 | +0.0404 | 0.0294 | +1.38 | +0.0380 | no sig |
| trend_score | 0 | — | — | — | — | constante (=1.0, gate) |
| adx_score | 151 | +0.0679 | 0.0294 | +2.31 | +0.0219 | sig (nominal) |

Nota honesta: momentum (el ÚNICO ranking continuo del motor) NO selecciona intra-día.
Los demás son gates binarios (rsi 0.4/0.8, adx 0.3/0.9 — `signal_engine.py`). ADX pasa el
umbral nominal |t|>2 pero **NO resiste corrección de multiple testing** (4 factores →
Bonferroni ≈2.5) → "marginal, no robusto".

**0.5b RMT / Marchenko-Pastur** (`rmt_mp_20260811_150849.txt`, §4.2): N=50, T=1599,
q=0.0313, λ₊=1.385. Mercado (PC1) explica 30.8% de la varianza; espectro residual
(mercado removido): 8 autovalores sobre el umbral, primero = 15.2% de la varianza
residual. El propio script lo tagea "consistente con W3" — es la lectura correcta de
RMT aislado: 8 factores reales sobre 49 dimensiones residuales posibles, ninguno
dominante, es estructura *difusa/sectorial real*, no ausencia de estructura. **Corrección
sobre una primera redacción de este párrafo**: RMT NO apoya "no hay nada que seleccionar"
— apoya "hay estructura sectorial sin explotar por los factores actuales". Ver matiz en
el veredicto conjunto.

**0.5c ridge macro crudo** (`ridge_comb_20260811_150859.txt`, §4.3): sobre panel limpio,
con features macro crudas (4 columnas) en vez del composite.

| modelo | IC OOS pooled | delta vs blend | ICIR | folds+ |
|---|---|---|---|---|
| blend_actual | −0.0016 | — | — | — |
| ridge_3f (ref. histórica) | +0.0112 | +0.0128 | 0.996 | 4/5 |
| ridge_3f+sent | −0.0175 | −0.0159 | 0.297 | 3/5 |
| ridge_macro_crudo | −0.0062 | −0.0046 | 0.174 | 3/5 |
| ridge_macro_crudo+sent | −0.0172 | −0.0156 | 0.073 | 2/5 |

→ **El ridge con macro crudo NO mejora nada** (delta −0.0046, ICIR 0.174). Corrobora
trial #13: el problema NO está en cómo se combinan los factores (§6: no re-intentar).

### VEREDICTO DEL GATE (conjunto): W2 con matices — corregido tras revisión

- **Sólido (W2 fuerte)**: los rankings de selección del motor a nivel símbolo
  individual (momentum, RSI) **no tienen poder intra-día**; ADX (único con señal) no
  resiste multiple testing; mejorar la función de combinación no rescata nada
  (trial #13 + 0.5c). El ranking de 50 símbolos con los factores actuales está muerto,
  con evidencia sólida — esto no necesita más análisis.
- **No es lo mismo que "no hay estructura"**: RMT encuentra 8 factores residuales
  reales (de 49 dimensiones posibles), ninguno dominante (15.2%) — estructura
  sectorial/difusa real, sin explotar por los factores actuales. El script la tagea
  "consistente con W3" y es la lectura correcta de RMT aislado. Una primera redacción
  de este veredicto reescribió esto como "sectorial débil" apoyando W2 — es una
  sobre-simplificación que no sostiene el propio artefacto.
- **Lectura corregida**: no es "timing puro, no hay nada más que seleccionar" — es
  "el ranking individual de 50 símbolos con estos factores está muerto, y lo que
  queda sin explotar (si algo) es estructura sectorial, no símbolo-por-símbolo".
  El siguiente paso no es más matemática sobre momentum/RSI a nivel símbolo — pero
  la RAMA W2 (§9) debería evaluar tres opciones, no dos: (a) timing sobre un basket
  único, (b) selección de 50 símbolos (descartada, sin evidencia a favor), (c)
  rotación/asignación a nivel sector o cluster — la única opción con evidencia
  positiva (RMT) detrás.

*Nota: esta sección se escribió ANTES de confirmar la rama con el usuario — la rama
resultante se registra en §9.*

---

## 9. Rama W2 — re-evaluación de producto: CONFIRMADA (2026-08-11, usuario)

Re-evaluación confirmada: no hace falta más matemática sobre momentum/RSI a nivel
símbolo — la muerte del ranking individual tiene evidencia sólida de tres fuentes
independientes (0.5a rr2 intra-día, trial #13, 0.5c ridge macro crudo).

**Alcance corregido: la re-evaluación compara TRES opciones, no dos** (corrección del
usuario sobre un alcance inicial de 2): cerrar prematuramente sobre "basket único"
ignoraría la única evidencia positiva del gate:

| Opción | Evidencia | Estado |
|---|---|---|
| (a) Timing sobre un basket único (ETF) | rr2: momentum/RSI no seleccionan intra-día; DSR baseline/basket ya mide el timing | candidata |
| (b) Selección de 50 símbolos (arquitectura actual) | momentum/RSI/r ridge muertos a nivel símbolo (rr2, trial #13, 0.5c); cross-section operable ~6 símbolos/fecha | **descartada** con evidencia sólida |
| (c) Rotación/asignación sectorial o por cluster | RMT: 8 factores residuales reales (de 49 dims), ninguno dominante (15.2%) = estructura sectorial difusa **sin explotar** por los factores actuales | candidata con la única evidencia **positiva** del gate |

Criterio de la re-evaluación: no decidir (a) vs (c) por pre-registro de trial hasta que
se defina qué activo subyacente y qué score sectorial — la estructura que RMT detecta
no está tocada por momentum/RSI, así que cualquier trial de motor sobre sectores
requiere su propio diagnóstico sectorial primero (mismo protocolo: intra-día, Newey-West,
pre-registrado).

### Diagnóstico sectorial endógeno — EJECUTADO (2026-08-11, `sector_clusters_20260811_170235.txt`)

Pre-registrado con las restricciones del usuario: clusters ENDÓGENOS (autovectores
residuales de RMT y jerárquico Ward sobre la misma matriz residual; **prohibido GICS**
— fuente externa con riesgo de lookahead de membership point-in-time), Bonferroni
sobre 8 clusters → umbral |t| > 2.73.

**Resultado: (c) NO pasa el diagnóstico sectorial previo.** Dos definiciones de
cluster, ninguna significativa (protocolo 0.5a, rank IC intra-día de momentum medio
del cluster vs retorno fwd 20d):

| clusters (k=8) | n_días | mean_IC | SE_NW | t | veredicto |
|---|---|---|---|---|---|
| autovectores residuales | 378 | +0.0339 | 0.0330 | +1.03 | no sig (2.73) |
| jerárquico Ward | 378 | +0.0230 | 0.0401 | +0.57 | no sig (2.73) |

Lectura precisa de este resultado:
- La **estructura** que RMT detecta sigue existiendo (8 factores reales, grupos
  coherentes: Farma LLY/JNJ/ABBV/MRK, Energía XOM/CVX, Pagos V/MA, Retail WMT/COST),
  pero es estructura de **co-movimiento (riesgo compartido)**, no de **predictibilidad**:
  el momentum medio del cluster NO predice el retorno futuro del cluster intra-día.
  §4.2 advertía exactamente este matiz: factores de co-movimiento ≠ alfa explotable.
- Esto NO prueba que todo score sectorial sea imparable (solo momentum medio), pero el
  factor que el motor ya usa era el único con hipótesis previa.
- **Opción (a) basket único queda como candidata por defecto** — con la salvedad de que
  un trial de basket requerirá su propio pre-registro (score de timing, mismas ventanas,
  DSR ≥ 0.90, N_TRIALS=17).

Nota de rigor: la primera corrida de este diagnóstico usó por error los autovectores de
la matriz COMPLETA (con mercado → 5 factores, no 8); detectado y corregido a la matriz
residual (8 factores, consistente con `rmt_mp_20260811_150849.txt`). La huella final es
`170235`; la intermedia `170216` queda como artefacto del error, no como resultado.

### CIERRE DE LA RAMA W2 (2026-08-11) — las tres opciones quedan descartadas

| Opción | Evidencia | Estado final |
|---|---|---|
| (b) Selección de 50 símbolos | rr2 intra-día, trial #13, ridge macro crudo (3 fuentes) | **descartada** |
| (c) Rotación sectorial/cluster | diagnóstico sectorial endógeno: t=+1.03/+0.57 vs 2.73 | **descartada** |
| (a) Timing sobre basket único (ADX) | trial #14 (DSR 0/3, mal especificado para 1 activo) + re-evaluación §11.1 (t-NW 1/3, delta vs buy&hold negativo en 3/3) | **descartada** |

El veredicto de (a) se sostiene por el estadístico CORRECTO para timing de un activo
(serie diaria con Newey-West), no por el DSR sobre conteo de trades: ni la media diaria
es significativa en ≥2/3 ventanas (solo W3, t=+2.24), ni el timing supera a mantener el
basket (delta negativo en las 3, t=−3.06/−0.53/−1.33). Con la rama W2 cerrada con tres
descartes verificados de punta a punta, el motor queda sin señal comercial en vivo
verificada (§4.5): lo que sigue es una decisión de PRODUCTO sobre esta arquitectura,
no más matemática (§5 no se agenda hasta que se defina).

---

---

## 11. Trial #14 (PRE-REGISTRADO 2026-08-11, pendiente de corrida) — (a) basket único con score de timing ADX + régimen

**Contexto**: rama W2 confirmada (§9); opción (b) descartada (3 fuentes independientes),
opción (c) descartada por diagnóstico sectorial endógeno (§9.c: t=+1.03/+0.57 vs 2.73)
→ queda (a) como candidata por defecto. Este trial la somete al criterio estándar.

**Score de timing DEFINIDO (fijado aquí, no implícito)**: NO momentum/RSI — ambos
refutados a nivel símbolo (0.5a) y cluster (§9.c). El score de timing del basket es:

1. **ADX del basket** — la única señal con evidencia real en todo el gate
   (0.5a: t=+2.31 nominal a nivel símbolo, artefacto `rr2_intraday_150741.txt`;
   a nivel UN activo no hay Bonferroni, el umbral vuelve a |t|>2). Regla:
   long del basket cuando `adx_score ≥ 0.9`; flat en caso contrario. MISMOS
   parámetros que el motor, sin inventar umbrales nuevos: ADX(14) con
   `adx_score = 0.9 si ADX>25 / 0.3 si ADX∈[20,25]` (`signal_engine.py:102-103`)
   y gate de entrada `ADX<20 → no compra` (réplica exacta del motor). El score
   NO es el momentum del basket.
   **Chequeo de distribución previo (pre-registrado)**: antes de correr el
   trial se audita la distribución empírica del ADX del basket (qué % de días
   cae en cada tramo >25 / 20-25 / <20). Si sale degenerada (el ADX de un
   basket diversificado suele ser más suave que el de una acción individual
   por cancelación de ruido idiosincrático), los umbrales absolutos del motor
   podrían no discriminar nada → se recalibran por percentil expansivo causal
   en vez de valor fijo. Esta recalibración se decide con datos ANTES de la
   corrida y queda documentada en el pre-registro — no post-hoc.
2. **Régimen SÓLO como identificador (sin magnitud de ajuste por ahora)** — el
   HMM global existente (`regime_classifier.py`) se reusa tal cual únicamente
   para IDENTIFICAR el régimen. El ajuste de exposición por régimen
   (+0.198 GOLDILOCKS / −0.173 DEFLATION, "macro contra-régimen") NO entra
   todavía en este pre-registro: esa medición quedó invalidada por el lookahead
   §3.1 y sigue sin re-medirse sobre la especificación correcta (serie del
   basket, no panel de 50). Se corre esa re-medición de la serie del basket en
   paralelo; si sobrevive con la spec limpia, entra al pre-registro ANTES de la
   corrida (no después). Si no se re-mide a tiempo, (a) corre solo con el ADX
   del basket (sin condicionamiento de régimen) y el régimen se mantiene como
   diagnóstico sin tocar exposición.
   **RESULTADO RE-MEDICIÓN (2026-08-11, artefacto `regime_basket_20260811_213437.txt`)**:
   el condicionamiento de régimen NO sobrevive con la spec limpia sobre la serie
   del basket y POR LO TANTO el ajuste de exposición por régimen QUEDA FUERA del
   pre-registro. Sobre el basket (target = retorno fwd 20d del basket equal-weight,
   régimen HMM walk-forward sin lookahead, `remeasure_regime_basket.py`): IC por
   régimen GOLDILOCKS +0.112 (n=59), REFLATION +0.106 (n=160), STAGFLATION +0.121
   (n=268, único con n>=200), DEFLATION +0.249 (n=68). Ningún |t|>2; STAGFLATION
   invierte el signo esperado (−1) y DEFLATION es +0.249 frente al −0.173 de la
   medición original. Patrón contrarégimen NO conservado → (a) corre SOLO con
   ADX; el régimen se mantiene como diagnóstico, sin tocar exposición.
3. **Revert si NO CUMPLE**: script borrado, producción nunca tocada (inyección
   por subclase dentro del script, mismo patrón que trial #13). Baseline de
   comparación: BASELINE ÚNICO post-fix `baseline_clean_20260811_150643.txt`
   (referencia oficial §8), no baselines históricos.

**Activo**: basket equal-weight de los MISMOS 50 símbolos del universo, NO un
ETF externo (SPY/QQQ). Justificación: el gate dejó pendiente "selección murió,
¿alcanza con timing solo?" — para contestarlo limpio hay que cambiar UNA sola
variable (seleccionar vs no seleccionar) y mantener todo lo demás igual (mismo
universo, misma ventana, mismos costos). Si el subyacente fuera SPY/QQQ se mete
una segunda variable no controlada: una racha buena/mala del ETF en la ventana
podría decidir a favor o en contra sin que el timing sea mejor que la selección.
El basket equal-weight de los 50 aísla exactamente el efecto del timing. Contras
anotados: agrega su propio costo de rebalanceo (a diferencia de un ETF ya
armado) y es un instrumento sintético, no directamente tradeable hoy — para la
fase de investigación es lo correcto; si (a) gana, la implementación de producto
evalúa después si conviene un ETF real como proxy. **Chequeo de sanity
secundario**: SPY como referencia OBSERVACIONAL para ver si el basket sintético
se comporta razonablemente parecido al mercado amplio — NO es el trial que
decide el gate y no consume un trial extra ni cambia el criterio.

**Criterio (congelado, mismo de siempre)**: DSR OOS ≥ 0.90 en ≥ 2/3 ventanas
(W1 2020-2021, W2 2022-2023, W3 2024-2026), piso ≥ 30 trades/ventana,
N_TRIALS=17+1=18 por ser un trial nuevo. Si el basket con ADX (el
condicionamiento de régimen queda FUERA: no sobrevivió la re-medición sobre la
serie del basket, regla 2) supera el baseline oficial en DSR en 2/3 ventanas →
(a) gana y el producto pasa a timing sobre basket; si no → (a) queda descartada
como (b) y (c), y el motor queda como está (sin señal en vivo, §4.5).

**Pre-registrado ANTES de correr — este documento es el registro.** Huella
timestamp en data/cache al correr. Sin cambios al criterio después de la
corrida (lección 0.5a en §10).

**RESULTADO TRIAL #14 (a) — CORRIDO 2026-08-11, artefacto
`trial14_basket_adx_20260811_215113.txt`: (a) DESCARTADA.** Verificado contra
artefacto (§3.4). Chequeo de distribución ADX previo (`basket_adx_dist_20260811_214847.txt`):
NO degenerada (long>25 62.6%, flat<20 21.2%) → se mantuvieron umbrales absolutos
del motor, sin recalibración. Timing LONG/FLAT (ADX>25 long / <20 flat / 20-25
mantiene) sobre basket equal-weight de 50, costos 0.15%/lado, 51 trades totales.
DSR por ventana: W1 n=11 DSR=0.0346, W2 n=10 DSR=0.0665, W3 n=12 DSR=0.0290 —
NINGUNA llega al piso de 30 trades (no evaluables) y las 3 quedan muy bajo 0.90.
**0/3 ventanas → NO CUMPLE → (a) queda descartada**, igual que (b) y (c). Script
del trial borrado (patrón #13): producción nunca tocada. El motor queda como
está, sin señal en vivo (§4.5). Con (a) descartada, el gate W2/W3 (veredicto §8)
no deja candidata: el timing agregado no reemplaza la selección, y la selección
murió (0.5a) — el sistema se mantiene como motor puro sin señal comercial live.

### 11.1 RE-EVALUACIÓN del veredicto de (a) — métrica apropiada para timing de UN activo (PRE-REGISTRADO 2026-08-11, ANTES de correr)

**Motivo**: el veredicto "0/3 → DESCARTADA" del trial #14 usó el criterio congelado
(DSR OOS ≥ 0.90, piso 30 trades) que fue diseñado para el motor de 50 símbolos.
Para un gate binario LONG/FLAT sobre UN solo activo, n=10-12 trades/ventana es
**estructural** (un activo con histéresis cruza sus umbrales pocas veces al año:
51 trades en 2915 días), y el DSR con n~10 colapsa a ~0 por la incertidumbre de
la estimación, no por falta de edge. El propio artefacto reporta PF 2.07/1.18/4.69
y win_rate 73%/60%/67% — direccionalmente positivos pero no evaluados con el
estadístico correcto. Mismo patrón que `RESUMEN_VALIDACION_VARIABLES.md §6.1`
(sentimiento/fundamentales): el criterio es estructuralmente inalcanzable con
esa frecuencia de señal; ahí se marcó para re-test, no se cerró. Corrección: el
piso de trades aplica a estrategias que generan entradas/salidas por símbolo;
para timing de un activo la muestra es la SERIE DIARIA de retornos, no el conteo.

**Metodología (fijada aquí, no implícita)** — replica EXACTA del trial #14:
- Misma construcción de serie: basket equal-weight 50 (rebalanceo diario,
  `MIN_BASKET_MEMBERS=40`), ADX(14) de Wilder sobre el cierre del basket
  (high=low=close), regla LONG si ADX>25 / FLAT si ADX<20 / 20-25 mantiene
  (histéresis), costos 0.15%/lado en transiciones, ventana 2019-01-01 →
  2026-08-04, W1/W2/W3 iguales al trial.
- **Verificación de fidelidad ANTES de evaluar**: la reconstrucción debe
  reproducir el ADX mediana 28.1 y los 51 trades del artefacto del trial. Si no
  coincide, la serie NO es la del trial y la re-evaluación no procede.
- Métricas por ventana sobre la SERIE DIARIA de retornos de la estrategia:
  media diaria, Sharpe anualizado (×√252), Sortino anualizado (desviación
  downside ×√252), t de Newey-West sobre la media diaria (H0: μ=0, HAC con
  lags L = floor(4·(n/100)^(2/9)), kernel Bartlett).
- Contexto de producto (no es el criterio): delta diario estrategia − buy&hold
  del basket en cada ventana, con su t-NW. Informa si el timing agrega valor
  sobre simplemente MANTENER el basket — dato de producto, no de supervivencia.

**Criterio pre-registrado (sin conocer el resultado)**: (a) sobrevive si
t-NW(media diaria) > 2 en ≥ 2/3 ventanas. Si no, (a) queda DESCARTADA por el
estadístico correcto — el veredicto pasa de "mal especificado" a "probado".
El veredicto DSR 0/3 original NO se borra: queda documentado como
mal especificado para 1 activo (auditoría informa; la re-evaluación decide).

**RESULTADO RE-EVALUACIÓN — CORRIDO 2026-08-11, artefacto
`reeval_trial14_basket_adx_20260811_220640.txt`**: verificación de fidelidad
ANTES de evaluar: OK (ADX mediana 28.1 = trial, 51 trades = trial — la serie
reconstruida es la del trial). Métricas por ventana sobre la serie diaria:

    ventana    n_dias  media_d  sharpe  sortino  t_NW  sig>2  delta_vs_H  t_NW_delta
    W1 2020-21   505   +0.00033   0.354   0.272  +0.63  False  -0.00094      -3.06
    W2 2022-23   501   +0.00019   0.291   0.251  +0.47  False  -0.00017      -0.53
    W3 2024-26   649   +0.00052   1.305   1.075  +2.24  True   -0.00028      -1.33

**Veredicto pre-registrado: 1/3 ventanas con t-NW > 2 → (a) DESCARTADA por el
estadístico correcto.** La media diaria del timing ADX del basket NO es
significativamente > 0 en ≥2/3 ventanas (solo W3 la supera). El contexto es
aún más claro: el delta vs buy&hold del basket es NEGATIVO en las 3 ventanas
(t=−3.06/−0.53/−1.33) — el timing ADX del basket nunca supera a simplemente
MANTENER el basket, y en W1 es significativamente PEOR. El veredicto del
trial #14 (descartada) se CONFIRMA en dirección, ahora con la métrica
correcta: no hay edge de timing ADX sobre el basket, y lo que hubiera de
señal en W3 no alcanza ni para superar al hold. Script de la re-evaluación
`reeval_trial14_basket_adx.py` CONSERVADO (a diferencia del trial #14, no hay
código en producción que replicar — el re-eval es el registro del veredicto).
El veredicto DSR 0/3 original queda como está: documentado como mal
especificado para 1 activo, ahora sustituido por la métrica apropiada.

---

## 12. Diagnóstico régimen vs VOLATILIDAD realizada (2026-08-12, PRE-REGISTRADO)

**Contexto**: régimen+macro se refutó DOS veces como predictor de RETORNO (Fase 2
original con lookahead §3.1; §11.1 sobre basket limpio). Pregunta distinta, nunca
testeada: ¿régimen predice MAGNITUD (volatilidad realizada), no dirección? Motivación
de producto: `TARGET_VOLATILITY` existe en `config.py` sin conectar
(`RESUMEN_VALIDACION_VARIABLES.md §5`).

**Metodología** (`diagnose_regime_volatility.py`, fijada antes de correr): misma
serie de basket y mismo régimen HMM walk-forward que §11.1; target = volatilidad
realizada forward 20d del basket (std retornos diarios en (t,t+20] × √252),
estrided 5d; por régimen, t-NW de (vol_régimen − vol_media_global) contra 0.
Criterio pre-registrado: algún régimen con n≥200 con \|t-NW\|>2.

**Resultado** (`diagnose_regime_vol_20260812_064914.txt`): 555 registros, vol media
global 0.1499.

| régimen | n | vol media | delta vs global | t-NW | n≥200 |
|---|---|---|---|---|---|
| GOLDILOCKS | 59 | 0.1744 | +0.0245 | +1.43 | no |
| REFLATION | 160 | 0.1473 | −0.0025 | −0.19 | no |
| STAGFLATION | 268 | 0.1322 | −0.0177 | **−2.18** | sí |
| DEFLATION | 68 | 0.2042 | +0.0544 | +1.47 | no |

**Corrección aplicada (misma vara que ADX en §8, no menos exigente porque el
resultado conviene)**: el criterio pre-registrado no incluyó Bonferroni pese a
testear 4 régimenes simultáneos — mismo error que se cometió y corrigió con ADX.
Bonferroni-4 sube el umbral a ≈2.50. STAGFLATION (t=−2.18) **NO lo cruza**. El
régimen con el efecto más grande e intuitivo (DEFLATION, vol +36% sobre la media)
es el que NO llega al piso de muestra (n=68) — es la lectura más prometedora y la
menos confirmable con los datos actuales.

**Veredicto honesto**: NO es una confirmación limpia. Es una pista (STAGFLATION
nominal sin sobrevivir corrección; DEFLATION direccionalmente grande pero
subpotenciado), no una señal de riesgo establecida. No se conecta `TARGET_VOLATILITY`
sobre esta base. Para resolverlo de verdad hace falta más historia (más años de
datos para que los 4 regímenes lleguen a n≥200) o reducir la granularidad del HMM
(menos estados, más muestra por estado) — ninguna de las dos es gratis ni inmediata.

**Cierre (2026-08-12, decisión del usuario)**: §12 se cierra COMO PISTA SIN ACCIÓN.
No se conecta `TARGET_VOLATILITY` (el desvío de volatilidad por régimen no superó la
corrección de múltiples comparaciones y la pista DEFLATION no tiene poder). No se
reducen los estados del HMM (tocaría el modelo de régimen que usa el motor en
producción sin una hipótesis nueva que lo justifique) ni se espera más historia
(pasivo, sin consumir trabajo). Si el proyecto vuelve a esto, es con un pre-registro
nuevo y una razón nueva.

## 13. Diagnóstico GAP REVERSION intra-día (2026-08-12, PRE-REGISTRADO)

**Origen**: un informe de Cline citaba "overnight gap reversion" como el signal #1
del Medallion Fund (19.4% feature importance), atribuido a `gurmansaran/medallion-pub`.
**Verificado y descartado como fuente**: ese repo es la réplica de un desconocido
(0 estrellas, 1 push, backtest propio con 12x de apalancamiento etiquetado literal
"12x Medallion", datos yfinance hasta los años 70) — no son datos reales de
Renaissance Technologies, que jamás publicó sus señales internas. Se prueba la idea
por mérito propio (hay literatura académica independiente sobre retornos
overnight/intraday), sin ninguna autoridad prestada.

**Metodología** (`diagnose_gap_reversion.py`, mismo aparato que 0.5a — rank IC
intra-día, Newey-West, NO pooled): señal = gap_pct = (open[t]−close[t-1])/close[t-1],
universo 50+7 símbolos, 2019-2026. 3 targets a horizontes CORTOS (el fade se espera
y decae rápido, no se testea a 20d): mismo día (close−open)/open, +1d close, +5d
close. Signo esperado: negativo (reversión).

**Resultado** (`diagnose_gap_reversion_20260812_082809.txt`, 145729 filas, 2915
fechas):

| horizonte | n_días | mean IC | t-NW | veredicto |
|---|---|---|---|---|
| mismo día (open→close) | 2915 | −0.0525 | **−11.29** | reversión real (nominal) |
| +1 día close | 2914 | −0.0021 | −0.46 | no sig |
| +5 días close | 2910 | −0.0029 | −0.65 | no sig |

**Interrogatorio antes de aceptar** (t=−11.29 es, por lejos, el número más fuerte
de toda la investigación — eso exige más escrutinio, no menos): el efecto se
evapora por completo de un día para el otro (t pasa de −11.29 a −0.46). Esa firma
es característica de ruido de microestructura del precio de apertura (auction de
apertura menos estable que el cierre), no de reversión económica genuina — si fuera
información real corrigiéndose, algo debería persistir al día siguiente, no
desaparecer a cero de golpe.

**Veredicto honesto**: estadísticamente el hallazgo es real y el más robusto de
todo el proyecto, pero **no es capturable con la arquitectura actual**: es
intradía puro (entrar cerca de la apertura, salir al cierre, mismo día) — este
sistema no tiene motor de ejecución, no tiene datos en tiempo real, y `yfinance`
no da un precio de apertura operable en vivo. Es exactamente la infraestructura
("escalar en serio") que se descartó como no realista dado Mac + VPS chica + 3TB.
Queda documentado como hallazgo académico válido, no como próximo paso de producto.
Si en el futuro se invierte en ejecución intradía real, es el primer candidato a
re-testear con costos reales (dos operaciones por día por posición) antes de
construir nada.

### 13.1 PRE-REGISTRO — backtest gap-reversion con costos reales (Tanda D, 2026-08-12)

**Pregunta**: después de pagar costos de ejecución reales (0.15%/lado, 2 lados por
trade completo), ¿el fade intradía del gap de apertura deja retorno NETO positivo?
El diagnóstico §13 probó el IC (t=−11.29 mismo día) pero el efecto se evaporó a +1d;
ese backtest no pagó costos. Este paso decide si algún día tiene sentido evaluar
ejecución intradía de verdad — es la cuenta económica que falta, no un trial de motor.

**Metodología** (`backtest_gap_costs.py`, corre DESPUÉS de este pre-registro):
- Universo 50+7 símbolos, 2019-01-01 → 2026-08-04, datos OHLC reales (`load_universe`).
- Estrategia: cada día de trading con ≥3 símbolos con |gap| ≥ 1.0% → fade en cada
  uno (short si gap>0, long si gap<0), equally weighted, entrada al open del día,
  salida al close del mismo día (el horizonte ÚNICO donde §13 mostró señal).
- Costos: 0.15% por lado × 2 lados = 0.30% del tamaño por posición completa
  (retorno diario neto del portafolio = bruto − 0.003, aplicado solo en días operados).
- Serie principal: retorno diario (bruto y neto) del portafolio EW de fades activos;
  inferencia sobre la serie con Newey-West Bartlett L=3 (mismo aparato que §13/0.5a).

**Criterio de éxito (fijado ANTES de correr, sin conocer el resultado)**:
`n_días_operados ≥ 100` Y media del retorno diario NETO > 0 con `t-NW ≥ 2.0`.
Secundario (informativo, no gate): Sharpe neto anualizado, % de días positivos,
delta bruto→neto (cuánto se come el costo), tamaño medio del portafolio (nº fades/día).

**Veredicto posible**: si cumple → el fade sobrevive costos y queda justificado
revisar el diseño de motor intradía (con pre-registro propio, infraestructura
apart); si no cumple → §13 se cierra: gap-reversion queda como hallazgo académico,
no traducible a PnL neto con esta infraestructura.

**Riesgo declarado**: este ejercicio es cross-sectional diario con el aparato ya
validado — sin nuevos grados de libertad de búsqueda; el umbral 1.0% es literatura
clásica de gap-fade y se fija acá sin mirar resultados.

**Resultado** (`backtest_gap_costs_20260812_173951.txt`, 145729 filas, 2206 días
operados = 75.7% de los 2915 días; media 11.3 fades/día):

| métrica | valor |
|---|---|
| retorno bruto medio diario | −0.00005 (t-NW = −0.20) |
| retorno neto medio diario (0.30%/trade) | −0.00305 (**t-NW = −11.53**) |
| Sharpe neto anualizado | −3.90 |
| % días positivos (neto) | 39.3% |

**Verificado contra el artefacto**: n_días 2206 ≥ 100 pero media neta < 0 con
t-NW = −11.53 → criterio pre-registrado NO se cumple.

**Interrogatorio antes de aceptar** (el IC de §13 era t=−11.29 — ¿por qué el
fade EW no gana?): el rank-IC mide consistencia de ordenamiento, no retorno
promedio; el fade equally-weighted diluye los gaps grandes (donde vive la
reversión) contra los abundantes gaps de 1-2% (donde el retorno esperado es
despreciable). No hay bug: mismo panel (145729 filas), misma dirección de trade
(short si gap>0), datos verificados. El retorno BRUTO ya es indistinguible de
cero (t=−0.20) — la significancia del IC no se tradujo en PnL promedio ni antes
de pagar costos. Explorar umbrales/top-N post-hoc violaría el pre-registro (§14);
si algún día se quiere, es un pre-registro nuevo.

**Veredicto honesto**: §13.1 NO CUMPLE → se cierra. Gap-reversion queda como
hallazgo académico estadísticamente real pero no capturable: sin costos ya no
produce retorno EW, con costos destruye cualquier residuo. Confirma el veredicto
de §13: la ejecución intradía no se persigue con esta infraestructura.

---

## 15. rank IC intra-día por SUB-PERÍODO — ¿quiebre de régimen? (2026-08-12, PRE-REGISTRADO)

**Origen**: motivado por evidencia externa verificada (§13, NY Fed "The Overnight
Drift" / "The Disappearing Overnight Drift") — una anomalía real y académicamente
documentada se desvaneció desde 2021 por compresión de la dispersión de
desequilibrios de cierre. Pregunta: ¿algo similar les pasó a momentum/RSI/ADX en
nuestros propios datos? Nunca se testeó — todo §0.5a corrió sobre 2019-2026 pooled.

**Metodología** (`diagnose_rr2_subperiodos.py`, mismo protocolo que 0.5a — rank IC
intra-día, Newey-West, NO pooled): panel limpio partido en PRE (<2022-01-01,
fijado por la literatura externa, no elegido mirando nuestros datos) y POST
(≥2022-01-01). Bonferroni-8 (4 factores × 2 sub-períodos), umbral |t|>2.73.

**Resultado** (`rr2_subperiodos_20260812_194031.txt`): PRE 139 fechas / POST 207
fechas.

| factor | PRE t | POST t | sig (Bonf-8) |
|---|---|---|---|
| momentum_score | +0.36 | −0.61 | ninguno |
| rsi_score | +1.54 | +0.45 | ninguno |
| trend_score | nan (constante) | nan (constante) | — |
| adx_score | +1.22 | +2.03 | ninguno (POST cerca pero no cruza) |

**Veredicto**: ningún factor es significativo en NINGÚN sub-período. No hay
evidencia de quiebre de régimen — no porque el efecto haya desaparecido, sino
porque nunca hubo un efecto Bonferroni-robusto que quebrar, ni antes ni después de
2021. Responde con precisión la hipótesis del usuario: no es que "los indicadores
que funcionaban antes de 2021 dejaron de funcionar" — es que, con este universo y
este protocolo, no funcionaron de forma robusta en ningún momento de la muestra.

---

## 16. MA200 soporte/resistencia por CLUSTER RMT — ¿heterogéneo? (2026-08-12, PRE-REGISTRADO)

**Origen**: hipótesis del usuario — algunos activos respetan MA200 como resistencia
(reversión), otros la usan como confirmación de tendencia (momentum/continuación).
Un test pooled con un signo esperado único cancelaría ambos efectos. Nunca se
testeó heterogeneidad por activo en este proyecto.

**Metodología** (`diagnose_ma200_clusters.py`): señal = (close−ema200)/ema200,
target = fwd_return_20d, estride 5d. Pooled DENTRO de cada uno de los 8 clusters
RMT ya calculados (§9.b/§9.c, no inventados de nuevo). Newey-West con n_eff por
símbolo. Bonferroni-8, umbral \|t\|>2.73. Criterio: heterogeneidad real si ≥2
clusters significativos con signos OPUESTOS.

**Resultado** (`diagnose_ma200_clusters_20260812_200228.txt`, 26450 filas):

| cluster | n | IC | rank_IC | t-NW | sig (Bonf-8) |
|---|---|---|---|---|---|
| C0 (SPY/QQQ/NVDA/TSLA/...) | 6348 | +0.0398 | −0.0143 | +1.42 | no |
| C1 (JPM/BAC/ADBE/GE/...) | 3174 | +0.0134 | +0.0329 | +0.34 | no |
| C2 (CRM/ACN/AMGN) | 1587 | −0.0999 | −0.0955 | −1.78 | no |
| **C3 (WMT/UNH/ABBV/TMO/MCD/PFE)** | 3174 | **−0.1294** | −0.1008 | **−3.26** | **sí** |
| C4 (META/LLY/COST/MRK/CSCO) | 2645 | −0.0371 | −0.0410 | −0.85 | no |
| C5 (GOOGL/AMZN/XOM/NFLX/...) | 3703 | −0.0606 | −0.0501 | −1.65 | no |
| **C6 (AAPL/V/MA/ORCL/IBM/QCOM/TXN)** | 3703 | **−0.1582** | −0.1129 | **−4.31** | **sí** |
| C7 (MSFT/HD/CMCSA/DIS) | 2116 | −0.0663 | −0.0220 | −1.36 | no |

**Veredicto sobre la hipótesis original**: NO CONFIRMADA — no hay clusters con
signos opuestos entre los significativos. La hipótesis de "resistencia para unos,
continuación para otros" no se sostiene: ningún cluster mostró el signo momentum
(positivo).

**Pero apareció algo distinto y más fuerte que cualquier otra cosa en esta
investigación**: C3 y C6 dan Bonferroni-significativos con margen real (no al
límite como ADX o STAGFLATION antes) — mientras más lejos por ARRIBA de su MA200
está el precio, PEOR el retorno de los próximos 20 días. Reversión por
sobre-extensión, no ruptura alcista.

**Reserva explícita antes de tratarlo como hallazgo**: el test es pooled dentro de
cluster (correcto para esta pregunta específica, ver metodología), pero eso lo
hace vulnerable a un confusor distinto — que sea simplemente beta de mercado
(rallies extendidos del mercado general preceden correcciones, y estos dos
clusters se movieron con el mercado) en vez de comportamiento idiosincrático del
activo. **Falta controlar contra el retorno del mercado en la misma ventana**
antes de aceptarlo como señal real, específica de C3/C6. Candidato más
prometedor de selección de toda la investigación — pendiente de ese control, no
cerrado como validado todavía.

---

## 17. Canal de Donchian — rank IC intra-día (2026-08-12, PRE-REGISTRADO)

**Origen**: hipótesis del usuario — cerca de máximos/mínimos recientes se acumulan
stop-loss y márgenes de otros traders; romperlos puede disparar cascadas. No se
puede ver el libro de órdenes real (privado de cada broker); el proxy público más
cercano ya implementado en el proyecto es el Canal de Donchian (20d high/low,
"sistema Turtle", citado con Donchian 1970 y Shumway & Wu 2006 en
`RESEARCH_PREDICTIVE_INDICATORS.md`, IC esperado documentado 0.05-0.08) — nunca
se le corrió el mismo test riguroso que al resto de los factores.

**Metodología** (`diagnose_donchian_intraday.py`, mismo protocolo exacto que
0.5a — rank IC intra-día, Newey-West, NO pooled): señal = posición continua
dentro del canal, (close−mid)/(upper−lower), sobre el panel limpio ya construido.
Signo esperado +1 (breakout alcista = continuación). Umbral |t|>2.0 (un solo
factor, sin corrección de múltiples comparaciones).

**Resultado** (`diagnose_donchian_intraday_20260812_201008.txt`, 2069/2069 filas
con Donchian calculado): 187 fechas, mean_IC=−0.0249, t-NW=**−0.81**.

**Veredicto**: NO SIGNIFICATIVO, y con signo contrario al esperado (negativo, no
positivo). Mismo destino que momentum/RSI/trend/ADX en §0.5a: el "sistema Turtle"
está implementado y documentado con una cita académica, pero no muestra poder de
selección real en este universo con este protocolo. Descartado — no confirma la
hipótesis de cascadas de stops como señal explotable vía este proxy.

---

## 18. Control de beta de mercado sobre MA200 C3/C6 (2026-08-12, PRE-REGISTRADO)

**Origen**: §16 dejó una reserva explícita — el hallazgo de C3/C6 (MA200 como
reversión) es pooled dentro de cluster y podía ser sólo beta de mercado (rallies
generales preceden correcciones) en vez de comportamiento idiosincrático.

**Metodología** (`diagnose_ma200_beta_control.py`): mismo panel/señal que §16,
pero el target pasa a ser retorno EN EXCESO de SPY (mismo horizonte). Sólo C3 y
C6 deciden (los únicos significativos en §16, fijado antes de correr — los otros
6 clusters se reportan como contexto, sin peso en el veredicto, para no inflar
potencia filtrando "ganadores" después de mirar). Bonferroni-2, umbral \|t\|>2.24.

**Resultado** (`diagnose_ma200_beta_control_20260812_202125.txt`):

| cluster | t crudo (§16) | t exceso-mercado | veredicto |
|---|---|---|---|
| C3 | −3.26 | −1.02 | NO SOBREVIVE — era beta de mercado |
| C6 | −4.31 | **−2.87** | **SOBREVIVE** — idiosincrático |

**Veredicto**: C3 queda refutado como beta disfrazada. **C6 (AAPL, V, MA, ORCL,
IBM, QCOM, TXN) sobrevive el control** — sobre-extensión por encima de MA200
predice retorno peor que el del mercado, no sólo peor en general. Primer
hallazgo de toda la investigación que sostiene este nivel de escrutinio.

**Nota de disciplina, no perseguida ahora**: C0 (SPY/QQQ/NVDA/TSLA/...) mostró
t=+3.28 en exceso-de-mercado pese a no ser significativo en crudo (§16) — no
estaba pre-registrado como cluster que decide, así que NO se actúa sobre esto
acá (sería exactamente el post-hoc cherry-picking que este protocolo existe para
evitar). Queda anotado como posible pregunta futura, con su propio pre-registro
si se retoma.

**Próximo paso, no hecho todavía**: backtest con costos reales del hallazgo de
C6 (mismo patrón que mató a gap-reversion en §13.1 — una cosa es el IC, otra es
que sobreviva costos y mecánica real).

### 18.1 PRE-REGISTRO — backtest C6 con costos reales (Tanda D, 2026-08-12)

**Pregunta**: el fade del IC pooled de C6 (dist_ma200 vs fwd_20d, t=−2.87 en exceso
de mercado) ¿deja retorno NETO positivo después de costos reales (0.15%/lado) y
mecánica de hold 20d? Es el mismo gate que mató a gap-reversion en §13.1.

**Metodología** (`backtest_c6_costs.py`, corre DESPUÉS de este pre-registro):
- Universo C6 (AAPL, V, MA, ORCL, IBM, QCOM, TXN — exactamente el cluster de
  §16/§18), 2019-01-01 → 2026-08-04, OHLC real vía `load_universe`.
- Señal idéntica a §16: `dist_ma200 = (close − ema200)/ema200` con
  `calculate_all_indicators` (no se reinventa el cálculo); fechas de señal con
  stride 5d POR SÍMBOLO (mismo `iloc[::5]` que §16).
- Estrategia principal (variante **LS**): fade completo del IC pooled del cluster
  — LONG en los símbolos con dist_ma200 < 0, SHORT en los con dist_ma200 > 0,
  trade units equally-weighted, entrada al close de la fecha de señal, salida al
  close de t+20 (el target exacto de §16, sin stops ni salidas anticipadas — no
  se inventan parámetros).
- Variante informativa (NO gate, reportada aparte): **SO** = short-only de los
  símbolos con dist_ma200 > 0 (la sobre-extensión destacada en §16), mismos hold/
  costos.
- Costos: 0.15%/lado × 2 = 0.30% del tamaño por trade unit completo, deducidos el
  día de entrada del trade unit (costeo conservador, adelanta el costo — mismo
  criterio que §13.1).
- Serie principal: retorno diario del portafolio (promedio EW de los trade units
  activos ese día), bruto y neto; inferencia Newey-West Bartlett L=20 (el
  horizonte, misma convención que los ICs de 20d).

**Criterio de éxito (fijado ANTES de correr, sin conocer el resultado)**: para la
variante LS: `n_días_con_posiciones ≥ 100` Y media del retorno diario NETO > 0 con
`t-NW ≥ 2.0`. Secundario (informativo): Sharpe neto anualizado, % días positivos,
delta bruto→neto, nº medio de trade units activos/día, y el mismo juego de métricas
para SO.

**Veredicto posible**: si LS cumple → C6 queda como candidato REAL de motor: se
diseña un trial de motor pre-registrado (integración del fade en el motor, no una
estrategia paralela) con su propio slot de n_trials. Si no cumple → §18 se cierra:
C6 queda como hallazgo académico que no sobrevive costos (mismo destino que
gap-reversion), y el proyecto queda con el baseline universo 50 como único modo de
operación documentado.

**Riesgo declarado**: cero grados de libertad de búsqueda nuevos — la señal, el
horizonte y el stride son literalmente los de §16; el umbral de signo es el signo
del IC validado; los costos son los estándar del proyecto. La variante SO no
participa del gate (el IC pooled del cluster es el hallazgo validado, no solo su
mitad short).

**RESULTADO (2026-08-13, artefacto `data/cache/backtest_c6_costs_20260813_135830.txt`)**
— NO CUMPLE, §18 se cierra.

- Verificación de integridad del panel (obligatoria §14): el script reproduce
  EXACTAMENTE §16 — 3703 filas pooled, Pearson IC −0.1582, Spearman −0.1129
  (mismos valores del artefacto de §16). La señal y el target son fieles.
- LS (gate): 3703 trade units, 2661 días con posición (≥100 ✓). Bruto −0.000019/día
  (t-NW −0.07), NETO −0.000228/día (t-NW −0.88, no >0 ✓/✗), Sharpe neto −0.27,
  45.5% días positivos, 20 trade units activos/día promedio. Costos 0.30%/unit =
  0.000209/día → consumen todo el bruto y más.
- SO (informativa): bruto −0.000603/día (t-NW −2.33), neto −0.000758 (t-NW −2.92),
  44.0% días positivos.
- Diagnóstico (por qué el IC −0.1582 no se traduce): `E[sign(dist)×fwd] = +0.00017`
  en el panel — el fade LS crudo pierde el drift. En 7 años alcistas el precio pasa
  la mayor parte del tiempo POR ENCIMA del MA200 (P(dist>0) ≫ 0.5), el portafolio
  está short la mayoría del tiempo y el short paga el drift completo del mercado.
  El hallazgo de §16/§18 es real pero VIVE EN EXCESO DE MERCADO (t=−2.87 en §18),
  no en nivel: la mecánica LS cruda no lo capitaliza porque mezcla señal con
  desbalance de signo.
- Lección §13.1 repetida con más claridad: un IC pooled significativo sobre retornos
  crudos NO implica PnL del fade EW con hold 20d, ni siquiera en bruto. El gate de
  costos (0.15%/lado) elimina cualquier resto. Veredicto: C6 queda como hallazgo
  académico — la señal existe en exceso de mercado, pero ninguna mecánica con costos
  reales la convierte en PnL neto sin una estrategia neutral al mercado explícita
  (que sería UN NUEVO pre-registro, no un ajuste de este).
- Estado del proyecto: baseline universo 50 = único modo de operación documentado.
  Tanda D completa; siguiente frente: Fase 1 EVT o Fase 2 Kalman+GP-BO (decisión del
  usuario).

### 18.2 PRE-REGISTRO — backtest C6 HEDGEADO (market-neutral por beta) con costos
### — INTENTO FINAL (§18), 2026-08-13

**Pregunta**: el fade LS crudo de §18.1 falló porque la pata short paga el drift
completo del mercado (E[sign×fwd] = +0.00017, P(dist>0) ≫ 0.5 en 7 años alcistas).
El hallazgo de §18 predice retorno RELATIVO al mercado (t=−2.87 en exceso), no
dirección absoluta. Una versión del fade neutralizada por beta de mercado, con los
mismos costos, ¿deja retorno NETO diario positivo con t-NW ≥ 2.0?

**Metodología** (`backtest_c6_hedge.py`, corre DESPUÉS de este pre-registro):
- Mismas unidades, señal, ventana y mecánica que §18.1 (dist_ma200, stride 5d,
  hold 20d, entry al close, salida t+20, costos 0.15%/lado por pata). Panel debe
  reproducir n=3703, Pearson IC −0.1582, Spearman −0.1129 (check de integridad §14
  en el header del artefacto).
- **Pata hedge (la que pidió el usuario, "corto C6 extendido + largo del mercado
  en proporción")**: cada trade unit SHORT (dist>0) se cubre comprando |β_sym|
  unidades de SPY; decisión de diseño declarada ANTES de correr: la pata LONG del
  fade (dist<0) se cubre simétricamente shorteando β_sym de SPY — cubrir solo el
  short deja exposición de drift residual y repetiría el defecto de §18.1 a media
  escala. El portafolio resultante es market-neutral por construcción.
- **Beta**: regresión OLS diaria (ret_sym ~ ret_SPY, con constante) sobre la
  ventana PRE-MUESTRA 2015-01-01 → 2018-12-31 — ningún dato de la ventana de test
  (2019+) participa de la estimación del beta. Sin rolling, sin parámetros nuevos.
- Costos: cada unit hedged paga 0.15%/lado en C6 + 0.15%/lado × |β| en SPY
  (round-trip completo = 0.003 × (1+|β|)), deducidos el día de entrada, misma
  convención que §18.1/§13.1.
- Serie principal: retorno diario del portafolio hedged (promedio EW de units
  activos, cada unit = pata C6 + pata SPY), bruto y neto; Newey-West Bartlett
  L=20. Variante SO-hedged (short-only cubierto): informativa, NO gate.

**Criterio de éxito (fijado ANTES de correr, idéntico a §18.1 para comparabilidad)**:
`n_días_con_posiciones ≥ 100` Y media del retorno diario NETO > 0 con `t-NW ≥ 2.0`.
Secundario informativo: Sharpe neto, % días positivos, delta bruto→neto, betas
estimados, P(dist>0).

**Regla de parada (compromiso del usuario, 2026-08-13)**: este es el INTENTO FINAL
de la línea C6. Si NO CUMPLE → §18 se cierra DEFINITIVO: C6 queda como hallazgo
académico en exceso de mercado, sin tercera variante, sin re-parametrización, sin
"market-neutral v2". Se sigue con el frente Fase 1 EVT o Fase 2 Kalman+GP-BO
(decisión del usuario). Si CUMPLE → C6 es candidato REAL de motor: trial de motor
pre-registrado con slot de n_trials propio.

**RESULTADO (2026-08-13, artefacto `data/cache/backtest_c6_hedge_20260813_154313.txt`)**
— NO CUMPLE (INTENTO FINAL). **§18 se cierra DEFINITIVO.**

- Check de integridad §14 en el artefacto: n=3703, Pearson IC −0.1582, Spearman
  −0.1129 — idénticos a §16/§18.1; P(dist>0)=0.744 (confirma el diagnóstico de
  §18.1: el fade está short el 74% del tiempo).
- Betas pre-muestra (2015-2018, sin datos de test): AAPL 1.195, V 1.005, MA 1.105,
  ORCL 1.062, IBM 0.833, QCOM 1.352, TXN 1.217 — |β| medio 1.110.
- LS-HEDGE (gate): BRUTO **+0.000149/día** (t-NW +1.01, Sharpe +0.31, 50.2% días
  positivos) — el hedge neutralizó el drift: el bruto pasó de −0.000019 (crudo
  §18.1) a +0.000149, la magnitud exacta de E[sign×fwd]=+0.000172. NETO −0.000292/día
  (t-NW **−1.97**, Sharpe −0.61). Costos 0.0063/unit (0.30%×(1+|β|)) consumen el
  doble del bruto.
- SO-HEDGE (info): bruto −0.000022 (t-NW −0.17), neto −0.000349 (t-NW −2.72).
- Veredicto final: la señal existe en exceso de mercado (confirmada al neutralizar
  el drift) pero su tamaño es del orden de los costos reales: +0.30% bruto por
  trade hedged ≈ costo de UNA pata, y MENOR al round-trip hedged (0.63%). La señal
  es real, no tradeable. Sin tercera variante (regla de parada del usuario).
- Estado definitivo: C6 = hallazgo académico en exceso de mercado. Baseline
  universo 50 = único modo de operación documentado. La línea de investigación
  C6/MA200 queda CERRADA en el proyecto.

---

## 14. Disciplina sin excepción

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
- La corrección de múltiples comparaciones (p.ej. Bonferroni) se declara en el PRE-REGISTRO
  del script, antes de correr — agregarla post-hoc en la interpretación viola este mismo
  principio. Lección 0.5a (2026-08-11, auditado por el usuario): ADX pasó |t|>2 nominal
  (t=+2.31) pero no Bonferroni-4; la conclusión W2 se sostiene por las otras 2 fuentes
  (trial #13, 0.5c), pero el criterio final no estaba en el script. Próximo script:
  umbrales corregidos por múltiples comparaciones van en el código desde el inicio.

---

## 19. Fase 1 — EVT: PRE-REGISTRO del diagnóstico de colas (universo 50)

**Contexto (2026-08-13, decisión del usuario)**: con la línea de señal cerrada (rama W2
con tres descartes verificados, §9), se arranca la Fase 1 EVT como la pieza de gestión
de riesgo del motor baseline (trial #10/V1) — no depende de ningún hallazgo de señal
nuevo. El plan (4.4.3 + Fase 1) fija: EVT/GPD sobre retornos de ACTIVOS (nunca sobre
P&L de estrategia — POT sobre 100-500 trades deja 10-20 excesos, insuficiente).

**Pregunta**: ¿los retornos diarios de los activos del universo 50 (2019-2026) tienen
colas de PÉRDIDA más pesadas que la normal estándar que la regla ATR del motor asume
de facto (stop 2×ATR, `adaptive_risk.py`)? ¿Cuánto subestima el supuesto gaussiano el
VaR/ES de cola, y en qué proporción del universo?

**Limitación declarada ANTES de correr**: `arch` (GARCH) NO está instalado en el venv.
El filtro de estandarización es EWMA de volatilidad (λ=0.94, RiskMetrics — el arquetipo
de McNeil-Frey sin GARCH): colas sobre residuos estandarizados z_t = r_t/σ_t, NUNCA
sobre retornos crudos. Si Ljung-Box(10) sobre z² muestra autocorrelación de vol
residual en ≥30% de los activos, se anota como limitación y se decide con el usuario
si `pip install arch` (GARCH) antes del trial de stops.

**Metodología** (`diagnose_evt_tails.py`, corre DESPUÉS de este pre-registro):
- Universo 50 = 7 originales (SPY/QQQ/AAPL/MSFT/GOOGL/AMZN/NVDA) + NEW_UNIVERSE (43),
  ventana 2019-01-01 → 2026-08-04, close diario vía `load_universe` (misma data del
  resto del proyecto).
- Por símbolo: σ_t² = 0.94·σ_{t-1}² + 0.06·r_{t-1}², arranque = varianza muestral de
  los primeros 60 retornos; z_t = r_t/σ_t.
- GPD por MLE (scipy `genpareto`, loc=0) sobre los excesos de pérdida: L = −z,
  umbral u = percentil 95% empírico de L (~5% excesos, n≈95 con ~1900 días — muy por
  encima del mínimo de la regla 4.4.3).
- Por activo: ξ̂ (shape) con SE ≈ (1+ξ̂)/√N_u; VaR_GPD(99%) y ES_GPD(99%) en unidades
  de z (fórmulas estándar McNeil); cuantil empírico 99%; VaR normal = 2.326; ratio
  VaR_GPD/VaR_normal. Cola derecha (ganancias): ξ̂ informativa, NO gate.
- Backtest de la cola (muestra completa): proporción de días con r_t < −2.326·σ_t
  (esperado 1% si normal; >1% si cola pesada) y con r_t < −VaR_GPD·σ_t (esperado ~1%
  si el GPD calibra bien). Ljung-Box(10) sobre z².
- Agregado: distribución de ξ̂ sobre el universo, nº de activos con ξ̂>0 significativo
  (t>1.64 unilateral), promedio de ratios VaR_GPD/VaR_normal.

**Criterio del gate diagnóstico (fijado ANTES de correr)**: el diagnóstico PASA (→ se
pre-registra el trial de stops EVT del motor) si se cumplen AMBAS:
1. ≥30% de los activos (≥15/50) con ξ̂ significativamente > 0 (t > 1.64); Y
2. ≥30% de los activos con excesos empíricos bajo el VaR normal ≥ 1.5% (la regla
   gaussiana subestima el riesgo de cola de forma material y generalizada).

Si NO pasa: las colas son compatibles con normalidad → la regla ATR no está
sistemáticamente subdimensionada → NO se justifica el trial de stops EVT, y la Fase 1
se cierra con este diagnóstico como evidencia (gate honesto, mismo espíritu que
§13/§18). La decisión de integración al motor NO se toma sin este diagnóstico a favor
y sin un trial pre-registrado posterior (el plan exige el gate "integrar si mejora
VaR/ES real").

**RESULTADO (2026-08-13, artefacto `data/cache/evt_tails_20260813_155237.txt`) — PASA
el gate diagnóstico. Se pre-registra el trial de stops EVT del motor en el siguiente
paso.**

- 50/50 activos evaluados, 146 excesos por activo (~5% de ~2915 días, umbral p95%
  sobre z estandarizado EWMA λ=0.94).
- **gate1 ✓**: ξ>0 significativo (t>1.64) en **28/50 (56%)**; ξ medio +0.187, mediana
  +0.171, p25/p75 +0.108/+0.260. Colas más pesadas que la normal, de forma
  generalizada; ninguna cola degenerada (ξ<0.5 en todo el universo; único negativo:
  XOM −0.009, no significativo).
- **gate2 ✓**: excesos empíricos bajo el VaR normal (2.326σ) **≥1.5% en 47/50 (94%)**;
  promedio 1.95% vs 1% esperado — el supuesto gaussiano falla a ~2× la tasa nominal.
- El GPD calibra bien: excesos reales bajo el VaR-GPD(99%) medio **0.98%** ≈ 1%,
  consistente en todo el universo — el modelo EVT describe la cola que la normal pierde.
- VaR99-GPD medio ≈ 3.0 z vs 2.326 normal → **ratio medio 1.26** (la regla gaussiana
  subestima el VaR 99% en ~26% en unidades de vol). Extremos: IBM +0.501 (t 4.03),
  CSCO +0.459 (t 3.80), WMT +0.422 (t 3.58) — los defensivos de baja vol con shocks
  discretos tienen las colas relativas más pesadas.
- Limitación verificada: Ljung-Box(10) sobre z² significativo en solo 8/50 (16%) — el
  filtro EWMA captura la mayor parte de la estructura de vol; la limitación GARCH
  declarada en el pre-registro queda acotada a ese 16%.
- **Interpretación para el motor**: la regla de stop 2×ATR (que equivale a un
  múltiplo fijo de la desviación empírica) está sistemáticamente subdimensionada
  contra el riesgo de cola en ~una cuarta parte de la distancia al VaR 99%; el trial
  de stops EVT (VaR/ES-GPD por activo, mismas ventanas, DSR) es el gate de
  integración que el plan exige — se pre-registra por separado. Nota de script: la
  primera corrida tuvo un bug de signo en el VaR normal (−ppf(0.99) anidado) que
  produjo excesos del 98% — imposible por construcción para un VaR 99%; detectado por
  el interrogatorio de verosimilitud antes de interpretar, corregido y re-corrido
  (artefacto 155217 descartado como artefacto del error, igual que en §9).
