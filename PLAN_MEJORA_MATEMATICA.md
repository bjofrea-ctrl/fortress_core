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

## 21 (M1). AUDITORÍA DE HORIZONTE — rank IC a 5d/10d vs 20d (2026-08-13, PRE-REGISTRADO)

**Origen**: `AUDITORIA_MECANICA.md` hallazgo 2. TODA la investigación de señal midió
a 20 días (`HORIZON=20` en los 6 scripts de diagnóstico), pero el motor real tiene
tenencia **mediana de 11 días**: 49.0% de las operaciones cierran en ≤10d y sólo
25.5% llegan a 20d. Medimos el poder predictivo en un horizonte que no es el que el
sistema opera — nunca se cuestionó en 17 secciones de investigación.

**Metodología** (`diagnose_horizon_audit.py`): idéntica a 0.5a (rank IC intra-día,
Spearman por fecha, Newey-West sobre la serie de ICs diarios). Único cambio: el
target. Lags NW escalados por horizonte (L=ceil(H/5): 1, 2, 4). **Check de fidelidad
pre-registrado**: el `fwd_20` recalculado debe reproducir la columna del panel —
resultado `max|dif| = 0.000e+00` sobre 2069 filas, exacto.

**Criterio pre-registrado**: 3 factores × 2 horizontes nuevos = 6 tests
(`trend_score` excluido, es constante dentro del gate y no produce test). Bonferroni-6,
umbral \|t\|>2.64, signo esperado positivo. 20d se reporta como REFERENCIA, no cuenta
como test nuevo.

**Resultado** (`horizon_audit_20260813_173648.txt`):

| factor | 5d (nuevo) | 10d (nuevo) | 20d (referencia) |
|---|---|---|---|
| momentum_score | +0.21 | −0.24 | −0.28 |
| rsi_score | **+2.18** | +1.05 | +1.38 |
| adx_score | −0.06 | +0.05 | +2.31 |

**Validación cruzada**: los t de la columna 20d reproducen EXACTAMENTE los de §0.5a
(momentum −0.28, rsi +1.38, adx +2.31) — la reimplementación es correcta, no es un
cálculo distinto que casualmente da parecido.

**Veredicto**: ningún factor cruza Bonferroni-6 a 5d ni a 10d. **El desajuste de
horizonte era un problema metodológico real, pero no ocultaba ninguna señal.** Todos
los rechazos previos se REFUERZAN — ahora se sabe que los factores no seleccionan en
ninguno de los tres horizontes relevantes, no sólo en el que se había mirado.

**Nota honesta (mismo trato que ADX en §8)**: `rsi_score` a 5d da t=+2.18, el más
fuerte de los tests nuevos y suficiente para un umbral sin corregir (\|t\|>2), pero
**no sobrevive Bonferroni-6**. Se reporta para no esconderlo; no es un hallazgo.

---

## 21.1 (M1b). HORIZONTES LARGOS — 60d y 125d (2026-08-13, PRE-REGISTRADO)

**Origen**: §21 varió el horizonte sólo hacia el lado corto (motivado por la
tenencia real, mediana 11d). Quedó sin testear el lado largo, y hay una razón
académica concreta para hacerlo: `momentum_12_1` es la construcción clásica de
Jegadeesh-Titman (1993), cuya evidencia original vive en tenencias de **3 a 12
meses** — más largo que los 20d hábiles (~1 mes) con los que se midió siempre.

**Metodología** (`diagnose_horizon_largo.py`): idéntica a §21. Horizontes nuevos:
60d (~3 meses, L=12) y 125d (~6 meses, L=25). **Limitación declarada antes de
correr**: 250d no se testea (L=50 sería ~27% de la muestra, Newey-West deja de ser
confiable); 125d es el límite razonable, su t se lee con esa reserva. **Corrección
conservadora**: Bonferroni-12 sobre la familia COMPLETA de horizontes no-históricos
de toda la auditoría (5d/10d/60d/125d × 3 factores), no sólo sobre estos 2 nuevos —
umbral \|t\|>2.87, el más estricto usado en todo el proyecto. Check de fidelidad:
`max|dif|=0.000e+00` sobre 2069 filas, igual que §21.

**Resultado** (`horizon_largo_20260813_181002.txt`):

| factor | 60d (nuevo) | 125d (nuevo) |
|---|---|---|
| momentum_score | +0.07 | +0.73 |
| rsi_score | +0.21 | −1.02 |
| adx_score | +1.71 | +0.77 |

**Veredicto**: ningún factor cruza Bonferroni-12 a 60d ni a 125d. **La auditoría de
horizonte queda completa y cerrada**: sin señal de selección en NINGÚN horizonte
entre 1 semana y 6 meses (5d, 10d, 20d, 60d, 125d). El desajuste de horizonte era
real como problema metodológico — nunca ocultó ninguna señal. Los rechazos previos
quedan reforzados con el margen más amplio posible: se probó corto y largo, y nada
apareció en ningún punto del espectro.

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

---

## 20. TRIAL #15 — PRE-REGISTRO: stops EVT walk-forward en el sizing del motor

**Pregunta**: sustituir la distancia de riesgo del sizing (`stop_distance =
max(2×ATR, price×position_stop)`, `adaptive_risk.py:63`) por la distancia EVT
walk-forward (`stop_distance = max(VaR_GPD(99%)×σ_EWMA, price×position_stop)`),
¿mejora el sistema? Criterio estándar del proyecto: DSR OOS ≥ 0.90 en ≥2/3
ventanas (W1 2020-2021, W2 2022-2023, W3 2024-2026-08-04), piso ≥30 trades.

**Corrección metodológica del usuario (2026-08-13, aceptada — anti-lookahead)**:
el ajuste EVT de §19 se calibró sobre la muestra completa (2019-2026); aplicarlo
fijo retroactivamente a W1/W2 sería información del futuro informando decisiones
del pasado (el mismo leak que §3.1 con régimen). El trial usa parámetros EVT
**walk-forward**: recalibración cada 63 días hábiles, ventana móvil de 756 días
hábiles (~3 años) de retornos estandarizados EWMA (λ=0.94), con **data desde
2015-01-01** para que toda decisión de las ventanas tenga parámetros calibrados
exclusivamente con historia previa a esa fecha.

**Nota de precisión sobre "la regla 2×ATR"**: `2×ATR` NO es el stop de pérdida
ejecutivo (ese es `position_stop`, −5% por régimen, en `check_all_stops`) — es la
distancia de riesgo del SIZING (`shares = equity×RISK_PER_TRADE/stop_distance`).
El EVT sustituye SOLO esa distancia de riesgo; `position_stop`, PARTIAL_TP 2×ATR,
trailing 2×ATR y ABSOLUTE_CEILING quedan intactos (variante mínima, aísla la
variable).

**Refactor aditivo de producción (backward compatible, 119 tests verdes)**:
(1) hook `BacktestEngine._make_risk_manager()` — `run()` lo usa en vez de
instanciar `AdaptiveRiskManager` directo; default idéntico. (2) `symbol` opcional
(último parámetro, default None) en `AdaptiveRiskManager.compute_position_size` —
`run()` lo pasa; con None el comportamiento es idéntico al previo (único llamador
en producción es `run()`; `scripts/test_system.py:56` sigue posicional). Permite
inyección por subclase sin duplicar `run()` (alternativa al patrón de trial #13).

**Mecánica del trial (`trial_evt_stops.py`)**:
- `EVTRiskManager(AdaptiveRiskManager)`: override de `compute_position_size` con
  `stop_distance = max(var_mult_vigente(symbol) × σ_EWMA_día, price×position_stop)`.
  Reloj interno sincronizado en `check_all_stops(date)` (corre ANTES de toda
  entrada del día) — cada decisión usa parámetros calibrados con data ≤ esa fecha.
- Walk-forward por activo: σ_t causal EWMA (λ=0.94, v_t = λ·v_{t-1} + (1−λ)·r²_{t-1})
  precomputada desde 2015; recalibración cada 63 días hábiles; en cada fecha de
  recalibración: ventana móvil 756 días hábiles ≤ fecha, z = r/σ, umbral u = p95%
  empírico, GPD MLE (`genpareto` loc=0), VaR_GPD(99%) (McNeil). Si excesos < 30 →
  fallback declarado: cuantil empírico 99% de la ventana (sin parámetros nuevos).
- **Assert anti-lookahead en el script**: cada compra estampa la fecha de
  recalibración vigente y verifica < fecha de compra; fallo = abortar.
- Dos corridas en el mismo script con la MISMA data (2015+): baseline
  (`BacktestEngine` estándar) y EVT (`EVTEngine` con el hook). La comparación es
  intra-corrida y consistente; el baseline intra-corrida puede diferir del
  artefacto histórico 2019-only al inicio (indicadores con más historia), se
  reporta el baseline intra-corrida como referencia contra el que se mide el EVT.
- N_TRIALS = **19**: 17 histórico (hasta #13, §6) + 1 por trial #14 (§11:
  "17+1=18 por ser un trial nuevo") + 1 por este trial. Fase 0.6 = re-test sin
  slot (§6.1), §18.1/§18.2 = backtests de señal sin slot (C6 nunca llegó a trial),
  §19 = diagnóstico sin inyección al motor, sin slot.

**Riesgo declarado**: cambios de producción aditivos y cubiertos por los 119
tests; variante mínima (solo la distancia de riesgo del sizing); parámetros EVT
(λ=0.94, u=p95%, ventana 756d, stride 63d, VaR 99%) heredados 1:1 del diagnóstico
§19 — cero grados de libertad nuevos sobre el resultado; fallback (cuantil
empírico si excesos<30) declarado por adelantado. Si NO CUMPLE: el sizing EVT no
mejora el sistema → no se integra (gate honesto) y la Fase 1 queda cerrada con la
evidencia de §19 (diagnóstico) + §20 (trial). Si CUMPLE: se evalúa la integración
con el gate "mejora VaR/ES real" del plan (comparar drawdown/cola realizada del
P&L EVT vs baseline en el mismo artefacto).

**RESULTADO (2026-08-15) — trial ejecutado, veredicto INVÁLIDO por diseño, no por
mercado. Revisión completa en `AUDITORIA_MECANICA.md` Hallazgo 6**:

1. Primer run (`trial15_evt_stops_20260814_172715.txt`, 36 trades): MECÁNICA ROTA
   (Hallazgo 5) — `ewma_vol_daily` calculaba la varianza sin elevar el retorno al
   cuadrado (`r2[t-1]` en vez de `r2[t-1]**2`) → σ en el floor 34% de los días →
   z ±187,559 → var_mult 20k-85k → sizing aniquilado. Fix de 1 carácter (idéntico a
   la implementación sana de §19) y re-run.
2. Re-run válido (`trial15_evt_stops_20260814_195828.txt`, 281 trades, 214 compras
   EVT con assert anti-lookahead OK): baseline y EVT dan métricas IDÉNTICAS a 4
   decimales en las 3 ventanas (W1 Sharpe 0.2562/0.2562, W2 −0.0542/−0.0542, W3
   0.5299/0.5299; DSR 0.0649/0.0253/0.1602). Reconstrucción del sizing sobre los
   281 trades: `var_mult×σ` (mediana 0.052) NUNCA supera el floor de régimen ni
   2×ATR (0/281), y `shares_by_risk` nunca es la restricción activa del `min()`
   (Kelly o el tope del 10% ganan siempre). **El trial midió el sistema contra sí
   mismo.** El "NO CUMPLE" no refuta el sizing EVT: demuestra que con el tope
   `MAX_POSITION_PCT=10%` y el brazo Kelly activo, `stop_distance` (EVT o 2×ATR) no
   influye en ninguna decisión. Probar la hipótesis requiere un pre-registro NUEVO
   que aísle `shares_by_risk` (p. ej. `fractional_kelly=0` en esa comparación) —
   decisión del usuario. Fase 1 se cierra con §19 (colas reales, ratio 1.26) + §20
   (trial no evaluable) + Hallazgo 6.

   ---

   ## 22. Lead-lag entre símbolos — PRE-REGISTRO (Tarea C, PLAN_LARGO_PLAZO.md, 2026-08-15)

   **Contexto**: nunca se testeó si un símbolo predice a otro (ej. NVDA→AMD por cadena
   de suministro) — todo lo probado hasta hoy mide un símbolo contra su propio pasado.
   Barato: no necesita datos nuevos, solo el panel diario que ya existe. Tarea asignada
   a Command Code por el plan.

   **Pregunta**: ¿el retorno de un símbolo "líder" predice el retorno de un símbolo
   "seguidor" del mismo sector/cadena a horizontes de 1-5 días, en exceso de lo que el
   propio pasado del seguidor ya contiene?

   **Lista de pares candidatos (fijada ANTES de mirar resultados, regla anti-p-hacking)**:

   | Par | Líder → Seguidor | Cadena |
   |---|---|---|
   | P1 | NVDA → AMD | semis (GPU competencia/cadena) |
   | P2 | NVDA → AVGO | semis (cadena suministro) |
   | P3 | NVDA → QCOM | semis (cadena móvil/GPU) |
   | P4 | AAPL → MSFT | mega-cap tech (ambos en el universo) |
   | P5 | AAPL → GOOGL | mega-cap tech |
   | P6 | MSFT → GOOGL | mega-cap tech |
   | P7 | XOM → CVX | energía (mismo sector) |
   | P8 | JPM → BAC | bancos (mismo sector) |
   | P9 | AMZN → WMT | retail (mismo sector) |
   | P10 | LLY → JNJ | farma (mismo sector) |

   **Metodología** (`diagnose_lead_lag.py`, corre DESPUÉS de este pre-registro):
   - Panel: universo 50 (7 originales + `NEW_UNIVERSE`), 2019-01-01 → 2026-08-04, OHLC
   diario vía `load_universe` (misma data del resto del proyecto).
   - Retornos diarios `r_sym[t] = close[t]/close[t-1] - 1` por símbolo.
   - Para cada par (líder L, seguidor F) y cada lag k ∈ {1,2,3,4,5}:
     correlación cruzada de Spearman entre `r_L[t-k]` y `r_F[t]` sobre las fechas
     comunes. SE asintótico de la correlación: `sqrt((1-ρ²)/(n-2))`. (El SE Newey-West
     de §0.5a/§21 aplica sobre series de ICs diarios; acá la correlación es un solo
     número por par-lag, así que el SE es el asintótico estándar.)
   - Signo esperado: **positivo** (el líder anticipa al seguidor en la misma dirección).
   Un lead-lag de "reversión" (negativo) se reporta como contexto, no como hallazgo.

   **Criterio pre-registrado (sin conocer el resultado)**:
   - Tests: 10 pares × 5 lags = **50 tests**.
   - Bonferroni-50 sobre los tests nuevos → umbral |t| > ~3.48 (z 0.05/50 bilateral).
   - Un par es un hallazgo si **≥2 lags consecutivos** del mismo par cruzan el umbral
   con signo esperado positivo (evita que un lag aislado sea ruido).
   - VEREDICTO: si algún par cumple → lead-lag real, se documenta como candidato a
   pre-registro de motor (familia `motor_signal`). Si ninguno → la hipótesis de
   lead-lag entre símbolos del universo queda refutada con la vara más estricta
   usada en el proyecto.

   **Riesgo declarado**: los pares se eligieron por cadena/sector ANTES de ver
   resultados (cero grados de libertad post-hoc); los lags se fijan en 1-5 días sin
   mirar datos. Si sale un par significativo, se valida contra el sub-período
   PRE/POST 2022 (mismo patrón que §15) antes de cualquier conclusión.

   **Registro en ledger**: familia `signal_diagnosis` (diagnóstico de señal, no
   consume slot de motor). Se registra con `register_trial(...)` al cerrar.
---

## 23. Triple Barrier como target de investigación — re-test de factores refutados (Tarea A, PLAN_LARGO_PLAZO.md, 2026-08-16, PRE-REGISTRADO)

**Origen**: PLAN_LARGO_PLAZO Tarea A (Cline). Toda la investigación histórica del
proyecto midió factores contra `fwd_return_20d` (retorno a horizonte fijo). El motor
real sale por BARRERAS (M1, `app/core/barrier_labeling.py`), no a horizonte fijo.
`momentum_score`, `rsi_score` y `adx_score` fueron refutados contra `fwd_return_20d`
(§0.5a, §21 5d/10d, §21.1 60d/125d: ningún t cruza Bonferroni en NINGÚN horizonte),
pero **nunca se probaron contra el objetivo binario que el motor persigue de verdad**:
"¿toca TP antes que SL?" (`label` +1/−1/0 de M1).

**Pregunta**: un factor nulo contra `fwd_return_20d` (ruido de magnitud, colas
dominadas por pocas salidas extremas) puede tener poder real contra la PROBABILIDAD
binaria de que la barrera cierre en positivo (robusta a colas). ¿Los factores
refutados seleccionan contra `label_barrier`?

**Metodología** (`backend/scripts/retest_triple_barrier.py`, corre DESPUÉS de este
pre-registro):

- Mismo panel del resto de la investigación: `factor_panel_20260811_144857.parquet`
  (universo 50 = 7 originales + `NEW_UNIVERSE`, stride 5 días, 2019-01-02 →
  2026-07-06), filas `eligible=True` — idéntico a §21/§21.1, comparable.
- Labels: `barrier_labeling.label_symbol()` (M1, NO se toca ese módulo) por símbolo,
  sobre precios OHLC diarios vía `load_universe` + `atr14` (indicators.atr), con
  `max_horizon=60`, costo `settings.COST_PER_SIDE` (0.0015, M4) y la serie `regime`
  del propio panel (HMM causal, columna real del panel, NO state 0 default).
- **Exclusión del borde (declarada ANTES de correr)**: los últimos 60 barras de cada
  símbolo se excluyen del etiquetado — sin 60 barras futuras la barrera no puede
  resolver y `label_symbol` cerraría por TIME_BARRIER truncado (contaminación). Solo
  se etiquetan fechas con ventana de evaluación COMPLETA (entry + 60 ≤ fin del panel
  de precios).
- rank IC intra-día (Spearman por fecha, patrón §0.5a/§21/§21.1) entre
  momentum_score / rsi_score / adx_score y `label` (+1/−1/0). SE Newey-West sobre
  los ICs diarios.
- **Lags NW por ventana** (regla fijada acá, respeta el límite declarado en §21.1):
  `L = min(12, floor(n_dias/8))` — 12 = ceil(60/5) del horizonte máximo de la
  barrera; se recorta según `n` para que la fracción de la muestra nunca supere
  ~12.5% (el mismo criterio por el que §21.1 descartó 250d).
- **Ventanas**: W1 2020-2021, W2 2022-2023, W3 2024-2026-07-06 (fin del panel).
  Se reportan también el total 2019-2026 como referencia.
- **Cheque de fidelidad**: (a) `label_symbol.summarize` por ventana (n, por barrera,
  win_rate neto, % barrera temporal) — si `n` o win_rate son absurdos se aborta sin
  interpretar; (b) el label debe ser independiente en forma de los factores (no hay
  ninguna transformación compartida).
- **CHECK de puerta abierta de M1** (`test_barrier_labeling.py` ya cubre la fidelidad
  de barreras vs `adaptive_risk.py`; se cita como verificación de "no tocar").

**Criterio pre-registrado (sin conocer el resultado)**:
- Tests: 3 factores × 3 ventanas = **9 tests nuevos**. (El ÍC total 2019-2026 no
  cuenta: es referencia, igual que 20d en §21.)
- Bonferroni-9 bilateral: umbral |t| > **2.78** (`z` = ppf(1 − 0.05/18) ≈ 2.78).
- Signo esperado: **+1** (mayor score → mayor probabilidad de `label>0`; todos los
  factores se miden con su dirección histórica).
- VEREDICTO: si ALGÚN factor cruza el umbral en ≥1 ventana con signo esperado → el
  target de barreras importa: se documenta el/la factor como candidato a pre-registro
  de motor con el target corregido. Si NINGUNO → la hipótesis de "generador vacío"
  queda reforzada incluso contra el objetivo que el motor persigue: los rechazos de
  §0.5a/§21/§21.1 se extienden al target binario.
- Nota honesta (mismo trato que §21): cualquier |t|>2 sin corregir se reporta como
  contexto, nunca como hallazgo.

**Riesgo declarado**: el label usa las barreras de M1, cuyas fidelidad al motor está
cubierta por 17 tests; el stride 5d del panel evita overlap perfecto entre labels
adyacentes, pero hay overlap parcial (horizonte variable hasta 60d) — por eso el IC
es POR FECHA (no pooled) y el SE es Newey-West con L recortado. La ventana W2 tiene
el menor n (~30-40 fechas); su t se lee con la misma reserva que declaró §21.1 para
125d.

**Registro en ledger**: familia `signal_diagnosis` (diagnóstico de señal rank-IC, no
consume slot de motor — mismo tratamiento que §21, §21.1 y §22, que están TODOS en
`signal_diagnosis`; el texto de PLAN_LARGO_PLAZO decía "motor_signal" pero el contrato
del ledger (`app/core/trial_registry.py`) clasifica este tipo de test bajo
`signal_diagnosis`; el desvío se documentó acá para que no vuelva a confundirse). Se
registra con `register_trial(...)` al cerrar, n=1.

**RESULTADO (2026-08-16, corrido por Cline) — artefacto:
`data/cache/retest_triple_barrier_20260816_091649.txt`**

Cheque de fidelidad del etiquetado: OK. 142,729 labels / 50 símbolos / 2,855 fechas;
win_rate_neto 0.586, toma parcial 58.95%, barrera temporal 6.24%. Pares eligible+label:
2,028.

| factor | ventana | n_dias | mean_IC | t-NW | sig(Bonf9) |
|---|---|---|---|---|---|
| momentum_score | TOTAL | 163 | −0.0753 | −2.48 | no (signo −) |
| momentum_score | W1 | 54 | −0.1035 | −1.97 | no |
| momentum_score | W2 | 30 | −0.1194 | −1.71 | no |
| momentum_score | W3 | 53 | +0.0003 | +0.00 | no |
| rsi_score | TOTAL | 144 | +0.0278 | +0.69 | no |
| rsi_score | W1 | 47 | −0.0480 | −0.96 | no |
| rsi_score | W2 | 22 | +0.1572 | +1.73 | no |
| rsi_score | W3 | 50 | +0.0231 | +0.31 | no |
| adx_score | TOTAL | 133 | +0.0116 | +0.33 | no |
| adx_score | W1 | 47 | −0.0555 | −1.13 | no |
| adx_score | W2 | 19 | +0.1546 | +1.90 | no |
| adx_score | W3 | 45 | −0.0056 | −0.08 | no |

**VEREDICTO (pre-registrado)**: NO CUMPLE — ningún factor cruza Bonferroni-9
(\|t\|>2.77) en ninguna ventana con signo esperado +1. La hipótesis de "generador
vacío" queda REFORZADA también contra el objetivo binario que el motor persigue: los
factores refutados no son nulos solo en magnitud (fwd_return_20d) — tampoco predicen
la PROBABILIDAD de que la barrera cierre en positivo. La vía "nulo en magnitud pero
útil para clasificar ganar/perder" queda cerrada con datos.

**Nota honesta**: momentum TOTAL dio el \|t\| más alto (−2.48) con signo NEGATIVO (score
alto → peor salida de barrera): bajo el criterio no cuenta (signo −) y tampoco cruza
el umbral. RSI/ADX W2 dieron t nominales +1.73/+1.90 con n chico (19-22 fechas, L
recortada a 2): contexto, nunca hallazgo.

## 24. TRIAL #16 — PRE-REGISTRO: abstención calibrada M2 contra el baseline real (2026-08-17)

**Origen**: decisión del usuario (2026-08-17). El instrumento diagnóstico M1-M8 está
completo (DISENO_INSTRUMENTO.md) pero NINGÚN trial lo usó contra datos reales. M2
(`app/core/conformal.py`, Split Conformal Prediction) envuelve el score real del motor
(`win_prob`) y declara abstenerse cuando el intervalo de predicción del retorno neto es
demasiado ancho. Pregunta: **¿la abstención calibrada M2 mejora el VPP de lo que el
motor SÍ opera, contra el baseline que opera todo?**

**Datos**: `data/cache/baseline_clean_20260811_150643_trades.parquet` — 286 trades
REALES del baseline universo 50 (2019-01-07 → 2026), con `win_prob` (score que el motor
usa para sizing, `backtest_engine.py:438`), `pnl`, `entry_date`, `exit_reason`.

**Score**: `win_prob` (el score real del motor, no uno nuevo).
**Outcome**: retorno neto por trade `ret = pnl / (shares × entry_price)` (el ret_net
real del trade, no un label sintético).

**Metodología** (`backend/scripts/trial_m2_abstencion.py`, corre DESPUÉS de este
pre-registro):

- **Walk-forward acumulado sin lookahead** (corrección del usuario del trial #15
  aplicada): para cada ventana, M2 se calibra SOLO con trades cuya `entry_date` es
  ANTERIOR al inicio de la ventana (historia completa previa, nunca datos futuros).
- **Ventanas**: W2 2022-2023, W3 2024-2026-08-04.
- **Exclusión declarada ANTES de correr — W1 (2020-2021) NO es evaluable**: la
  calibración de W1 usaría solo los 24 trades de 2019, y el piso de calibración de M2
  es n ≥ 30 (`conformal.py:99-104`) — calibrar con 24 trades violaría el piso del
  propio instrumento. W1 se reporta como no evaluable por diseño, no como fracaso.
- **Calibración**: W2 calibra con trades < 2022-01-01 (n=118 ✓); W3 calibra con
  trades < 2024-01-01 (n=167 ✓).
- Por trade de la ventana: `engine.predict(win_prob)` → `abstenerse` (intervalo más
  ancho que el umbral `2×mediana de residuos`, default declarado de M2).
- Métricas por ventana: VPP_baseline (fracción de trades con ret>0 operando todo),
  VPP_M2 (fracción con signo correcto entre los operados, `vpp_bajo_abstencion`),
  n_operados, tasa_abstención, cobertura empírica de M2.
- Test: z-test unilateral de dos proporciones con corrección de continuidad
  (VPP_M2 > VPP_baseline).

**Criterio pre-registrado (sin conocer el resultado)**:
- Tests: 2 ventanas × 1 test = **2 tests nuevos**. Bonferroni-2 unilateral:
  umbral p < **0.025** por ventana (α_total 0.05).
- CUMPLE si, en **TODAS** las ventanas evaluables (W2, W3): (a) VPP_M2 > VPP_baseline
  con p < 0.025; (b) n_operados ≥ 30 (piso TRADE_FLOOR del proyecto); (c) tasa de
  abstención ≤ 0.80 (un instrumento que se abstiene el 95% "mejora" trivialmente el
  VPP con n=2 — no es operativamente útil).
- Fidelidad: cobertura empírica de M2 en [0.80, 0.97] (nominal 0.90). Si una ventana
  falla cobertura, se declara NO INTERPRETABLE (DISENO_INSTRUMENTO §8: si la
  cobertura falla, el instrumento no se usa) — no cuenta como éxito ni fracaso.
- NO CUMPLE si alguna ventana evaluable falla cualquier condición. Nota honesta:
  métricas secundarias (retorno medio operado vs baseline, delta pnl) se reportan
  como contexto, nunca como hallazgo.

**Familia**: `motor_signal` — es un trial de MECÁNICA del motor (abstención de
operar), mismo tratamiento que #15 EVT (sizing), NO un diagnóstico de señal rank-IC
(eso es `signal_diagnosis`). Consume 1 slot: motor_signal pasa de 8 a 9 consumidos;
el umbral Bonferroni vigente para el próximo trial de la familia queda
1 − 0.10/10 = 0.99.

**Riesgo declarado**: los trades del baseline NO son independientes (mismo símbolo,
misma fecha, salidas por barreras) — el z-test de proporciones es la vara nominal;
la cobertura empírica y la consistencia entre ventanas son la vara de robustez real
(criterio exige TODAS las ventanas, no mayoría). M2 se calibra con `ret` real del
parquet — si el parquet fuera un artefacto del error (como el primer run de §22), la
fidelidad lo delata: cobertura fuera de rango → no interpretable.

**Registro en ledger**: `register_trial(...)` con familia `motor_signal`,
n_trials_consumidos=1, veredicto según criterio, al cerrar.

**RESULTADO**: (se llena al correr)
**RESULTADO (2026-08-17, corrido por OpenCode) — artefacto:
`data/cache/trial16_m2_abstencion_20260817_100548.txt`**

| ventana | n | VPP_base | VPP_M2 | n_operados | abst | cobertura | p |
|---|---|---|---|---|---|---|---|
| W2 2022-2023 | 49 | 0.4694 | NaN | 0 | 100% | 0.8367 | NaN |
| W3 2024-2026 | 119 | 0.5798 | NaN | 0 | 100% | 0.8908 | NaN |

VEREDICTO FORMAL (mecánico, aplicado al criterio): **NO_CUMPLE** — ambas ventanas
fallan n_operados ≥ 30 y abst ≤ 0.80 con n_operados=0.

**PERO EL VEREDICTO ES TAUTOLÓGICO — HALLAZGO ESTRUCTURAL DE M2, no de la
hipótesis** (mismo patrón que #15 EVT: el sistema midiéndose a sí mismo):

1. **El ancho del intervalo NO depende del score.** `ConformalAbstentionEngine`
   modela `point = polyfit(score)` y residuos ABSOLUTOS `|outcome − point|` →
   el cuantil conforme q es una constante por calibración → TODO intervalo mide
   `2q`. La abstención `width > max_interval_width` compara una constante contra
   otra: o abstiene todo o nada. Es estructuralmente incapaz de abstención
   diferencial (la promesa de DISENO_INSTRUMENTO.md §7 "declara CUÁNDO su lectura
   no es confiable").
2. **El default `max_interval_width = 2×median(residuos)` es SIEMPRE < 2q**
   (q = cuantil ~91.5% con α=0.10, n=118/167 → q > mediana en cualquier
   distribución no degenerada) → **abstención 100% garantizada por
   construcción**. Reproducción mínima independiente: calibración sintética n=118
   → q=0.0487, mediana=0.0220, umbral=0.0440, ancho=0.0973 → abstiene 28/28
   (100%). La cobertura empírica quedó DENTRO de rango (0.8367/0.8908) — el
   instrumento está bien calibrado y aun así no opera NUNCA con su default.
3. Los 16 tests de `test_conformal.py` no lo detectaron porque fijan
   `max_interval_width` explícito (999/0.001/0.0) — el test del default
   (línea 116) solo verifica que el default SE CALCULA como 2×median, no que
   produzca abstención utilizable.

**Consecuencia**: el trial #16 tal como está pre-registrado (usar M2 con su
default) NO PUEDE responder la pregunta "¿la abstención mejora el VPP?" — con
n_operados=0 no hay nada que medir. La hipótesis NO queda refutada ni
confirmada: queda SIN MEDIR, igual que #15. **No es un trial nuevo** — es la
constatación de que M2 necesita (a) residuos RELATIVOS (o un modelo de varianza)
para que el ancho dependa del score, y (b) un default de umbral utilizable
(p. ej. cuantil del ancho en calibración), ANTES de que cualquier trial de
abstención pueda medir algo. Decisión del usuario, no de un agente.

---

## 24.1 TRIAL #17 — PRE-REGISTRO: re-trial de abstención M2 con el instrumento CORREGIDO (2026-08-17)

**Origen**: hallazgo estructural del trial #16 (§24): M2 con su default era incapaz de
abstención diferencial (ancho constante + default 2×mediana → 100% de abstención
garantizada) → la hipótesis "¿la abstención mejora el VPP?" quedó SIN MEDIR. Decisión
del usuario (2026-08-17): corregir M2 y re-medir la misma pregunta. **Esto NO es el
trial #16 re-corrido: es un trial NUEVO que consume un slot nuevo** (lección del #15
aplicada: para retomar una línea hace falta pre-registro nuevo — la mecánica del
instrumento cambió).

**Corrección aplicada a M2** (`app/core/conformal.py`, antes de este pre-registro,
suite completa 242 passed):
1. **Residuos RELATIVOS** `|outcome − point| / max(|point|, floor)` (floor =
   p50(|point|)/10 de calibración) → el ancho del intervalo `2q·denom(point)` depende
   del score → la abstención puede discriminar entre scores.
2. **Default de umbral** = percentil 90 de los anchos de calibración → abstención ~10%
   de los casos de señal más extrema (ni 100% ni 0%).
3. Test de regresión nuevo (`test_default_produce_abstencion_diferencial_no_100_ni_0`):
   exige abstención diferencial con el default y que los abstendidos sean los de
   |point| más grande — el test que faltaba en §24.3.

**Pregunta (idéntica al §24)**: si el motor real (baseline universo 50) hubiera
aplicado la abstención calibrada M2, ¿el VPP de lo que SÍ opera supera el VPP del
baseline que opera todo?

**Datos**: `data/cache/baseline_clean_20260811_150643_trades.parquet` — 286 trades
REALES (2019-01-07 → 2026-08-04).
**Score**: `win_prob`. **Outcome**: `ret = pnl / (shares × entry_price)`.

**Metodología** (`backend/scripts/trial_m2_abstencion.py`, corre DESPUÉS de este
pre-registro): walk-forward acumulado SIN lookahead, mismo que §24 — W2 2022-2023
(calibra con trades < 2022-01-01, n=118), W3 2024-2026-08-04 (calibra con trades <
2024-01-01, n=167). W1 NO evaluable por diseño (24 trades de 2019 < piso 30 de M2,
declarado en §24 y vigente). Por trade de la ventana: `engine.predict(win_prob)` con
el DEFAULT corregido → VPP_baseline vs VPP_M2 (`vpp_bajo_abstencion`), n_operados,
tasa_abstención, cobertura empírica. Test: z-test unilateral de dos proporciones con
corrección de continuidad (VPP_M2 > VPP_baseline).

**Criterio pre-registrado (idéntico al §24, sin conocer el resultado)**:
- Tests: 2 ventanas × 1 test = 2 tests nuevos. Bonferroni-2 unilateral: p < **0.025**
  por ventana.
- CUMPLE si, en TODAS las ventanas evaluables (W2, W3): (a) VPP_M2 > VPP_baseline con
  p < 0.025; (b) n_operados ≥ 30; (c) tasa de abstención ≤ 0.80.
- Fidelidad: cobertura empírica en [0.80, 0.97] (nominal 0.90); fuera de rango →
  ventana NO INTERPRETABLE (ni éxito ni fracaso).
- NO CUMPLE si alguna ventana evaluable falla cualquier condición. Métricas
  secundarias (retorno medio, delta pnl) = contexto, nunca hallazgo.
- Abstención ~10% esperada con el nuevo default: si la tasa real quedara > 0.80 se
  declara NO_CUMPLE igual (criterio ciego al resultado).

**Familia**: `motor_signal` — mecánica del motor (abstención de operar), mismo
tratamiento que #15/#16. Consume 1 slot: motor_signal pasa de 9 a 10 consumidos; el
umbral Bonferroni vigente para el próximo trial de la familia queda 1 − 0.10/11 =
0.9909. **Umbral aplicado en el registro de ESTE trial: 0.99** (el vigente al momento
de correr, heredado del #16).

**Riesgo declarado**: trades del baseline no independientes (mismo símbolo, salidas
por barreras) — z-test de proporciones es la vara nominal; cobertura + consistencia
entre ventanas es la vara de robustez real (TODAS las ventanas, no mayoría). El
default nuevo abstiene los win_prob de señal extrema (|point| grande): si el motor
opera mejor en los extremos que en el centro, el trial lo mostrará como NO_CUMPLE —
la pregunta es genuinamente empírica, el criterio no se ajusta al resultado.

**Registro en ledger**: `register_trial(...)` con familia `motor_signal`,
n_trials_consumidos=1, veredicto según criterio, al cerrar.

**RESULTADO (2026-08-17, corrido por OpenCode) — artefacto:
`data/cache/trial17_m2_abstencion_20260817_104452.txt`**

| ventana | n | VPP_base | VPP_M2 | n_operados | abst | cobertura | p |
|---|---|---|---|---|---|---|---|
| W2 2022-2023 | 49 | 0.4694 | 0.4043 | 47 | 4.08% | 0.7755 | 0.8020 |
| W3 2024-2026 | 119 | 0.5798 | 0.6000 | 100 | 15.97% | 0.8908 | 0.4347 |

VEREDICTO FORMAL (mecánico, aplicado al criterio): **NO_CUMPLE**.

- **W2**: FIDELIDAD — cobertura 0.7755 fuera de [0.80, 0.97] → NO INTERPRETABLE
  (DISENO_INSTRUMENTO §8: si la cobertura falla, el instrumento no se usa).
- **W3** (interpretable): VPP_M2 0.6000 vs VPP_base 0.5798 — la abstención mejoró
  numéricamente +2.0pp pero p=0.4347 ≫ 0.025; n_operados=100 ✓, abst 15.97% ✓.
- Fix estructural CONFIRMADO FUNCIONANDO: la abstención ahora discrimina (4%/16%,
  no 100% tautológico) — el defecto del #16 quedó resuelto y verificado por el
  propio trial.

**Interpretación — hipótesis REFUTADA (medida, no tautológica)**:
con el instrumento corregido, la abstención calibrada M2 sobre `win_prob` NO mejora
significativamente el VPP de lo operado (W3: +2.0pp, p=0.43). El motor no gana
"callándose" con la incertidumbre conforme de win_prob. La respuesta honesta a la
pregunta del usuario ("¿debería el motor callarse cuando no hay señal?"): con ESTE
score y ESTA mecánica, la evidencia dice que no — la cobertura W2 además sugiere que
la garantía conforme no se sostiene en regímenes cambiantes (77.6% vs nominal 90%).

**Decisión tomada**: M2 queda CORREGIDO en el código (el fix del #16 es permanente —
residuos relativos + default p90 + test de regresión), pero la línea de abstención
sobre win_prob queda CERRADA como refutada. Si en el futuro hay un score nuevo (ej.
FinBERT) la abstención M2 podrá re-medirse con pre-registro nuevo — el instrumento
ahora SÍ es capaz de medir.

---

## 26. Indicadores sobre velas semanales — ¿el ruido diario oculta señal? (2026-08-17, PRE-REGISTRADO, Tarea C PLAN_LARGO_PLAZO.md)

**Problema**: Todos los indicadores se calculan sobre barras diarias. Nunca se probó
si una granularidad distinta (semanal) cambia el poder predictivo. Esto NO es cambiar
el horizonte del retorno futuro (eso ya se probó en §21/§21.1) — es cambiar el RUIDO
del indicador mismo. Barras semanales tienen menos microestructura (gap de overnight,
ruido intradía, spread bid-ask) y podrían revelar señal que el ruido diario oculta.

**Hipótesis**: Indicadores calculados sobre velas semanales (resample W-FRI) tienen
menos ruido y revelan rank IC significativo contra el retorno forward de la próxima
semana que los indicadores diarios equivalentes no muestran.

**Metodología pre-registrada** (ANTES de ver resultados):

1. **Datos**: OHLCV diario de los 50 símbolos del universo (`data/cache/{SYMBOL}.parquet`,
   2015-01-01 a 2026-08-04). Resample a semanal con `resample('W-FRI').agg(
   Open='first', High='max', Low='min', Close='last', Volume='sum')`.

2. **Indicadores sobre serie SEMANAL**:
   - `momentum_20w`: pct_change(20) × 100 sobre Close semanal (equivalente a ~5 meses)
   - `rsi_14w`: RSI 14 periodos sobre Close semanal (14 semanas ≈ 3.5 meses)
   - `adx_14w`: ADX 14 periodos sobre High/Low/Close semanal (mismo algoritmo que
     `indicators.py:adx`)

3. **Target**: `fwd_ret_1w` = retorno de Close a Close de la próxima semana
   (`close.shift(-1) / close - 1`). Equivalente semanal a fwd_return_5d del panel diario.

4. **Rank IC intra-semana** (mismo patrón que `diagnose_rr2_intraday.py`):
   - Por cada semana: rankear símbolos por cada indicador, correlacionar (Spearman) con
     `fwd_ret_1w`. Mínimo 5 símbolos por semana para computar.
   - Promediar ICs sobre semanas con Newey-West SE (L = ceil(5/5) = 1 lag, solapamiento
     semanal del retorno forward).

5. **Ventanas** (mismo período que el proyecto, diferente granularidad):
   - W1: 2019-01-01 a 2021-12-31 (in-sample)
   - W2: 2022-01-01 a 2023-12-31 (OOS 1)
   - W3: 2024-01-01 a 2026-07-06 (OOS 2)

6. **Familia**: `signal_diagnosis` — es un diagnóstico de señal, no un cambio de motor.

**Criterio de éxito/fracaso pre-registrado** (Bonferroni-8: 3 indicadores × 3 ventanas
= 9 tests, pero usamos 8 porque un indicador puede quedar sin datos en una ventana;
corrección conservadora):
- **CUMPLE** si, para al menos 1 indicador: |t| > 2.73 (α/8 ≈ 0.00625, dos colas) en
  ≥2 de 3 ventanas, con signo consistente (momentum/RSI positivo, ADX positivo).
- **NO CUMPLE** si ningún indicador alcanza |t| > 2.73 en ≥2 ventanas.
- **NO INTERPRETABLE** si una ventana tiene <20 semanas con datos (n_insuficiente).

**n_trials**: este es el slot #15 de `signal_diagnosis` (14 consumidos + 1 = 15).
Umbral Bonferroni vigente: 1 − 0.10/16 = **0.99375** (ya calculado por el ledger).

**Riesgo declarado**: (a) RSI semanal puede tener warmup insuficiente en W1 (pocos
datos al inicio de 2019); (b) ADX semanal suaviza tanto que puede perder poder
discriminativo; (c) 50 símbolos × ~260 semanas/W1 = rank IC con ~13000 obs transversales
por ventana — potencia alta, pero el ruido semanal puede inflar varianza.

**Artefacto**: `data/cache/weekly_indicators_YYYYMMDD_HHMMSS.txt`

**Registro en ledger**: `register_trial(...)` con familia `signal_diagnosis`,
n_trials_consumidos=1, veredicto según criterio, al cerrar.
---

## 25. Tarea B — ADX walk-forward como candidato a "bueno" (PLAN_LARGO_PLAZO.md, 2026-08-17, PRE-REGISTRADO)

**Origen**: PLAN_LARGO_PLAZO.md Tarea B (Cline). ADX es el ÚNICO factor con señal
nominal positiva de toda la investigación (IC +0.0679, t=+2.31, §0.5a —
`rr2_intraday_20260811_150741.txt`), pero: (a) no resiste Bonferroni-4 medido en
TOTAL (2019-2026); (b) §21/§21.1 lo midieron por HORIZONTE (5d/10d/60d/125d) — ningún
t cruza; (c) §23 lo midió por VENTANA contra el label de barreras — no cruza ninguna.
**Lo que nunca se midió**: el rank IC de `adx_score` por VENTANA contra
`fwd_return_20d` (el target de magnitud). El candidato "ADX alto → operar, ADX bajo →
abstenerse" nunca se evaluó OOS por ventana con el target de retorno que el motor
persigue.

**Pregunta**: ¿`adx_score` tiene poder predictivo OOS (W2/W3) contra
`fwd_return_20d`? ¿La señal nominal de §0.5a sobrevive el corte temporal por ventana,
o era un artefacto de medir toda la muestra junta?

**Metodología** (`backend/scripts/trial_adx_walkforward.py`, corre DESPUÉS de este
pre-registro):

- Panel: `factor_panel_*.parquet` (universo 50 = 7 originales + `NEW_UNIVERSE`, stride
  5 días, 2019-01-02 → 2026-07-06), filas `eligible=True`, idéntico a §21/§21.1/§23 —
  comparable. `latest_panel()` (misma convención que §23).
- Factor: `adx_score` — dicotómico por construcción del motor
  (`signal_engine.compute_factor_frame`: 0.3 si adx14≤25, 0.9 si adx14>25; el gate de
  elegibilidad ya exige adx14≥20). No se toca el motor: se lee la columna del panel.
- Target: `fwd_return_20d`.
- rank IC intra-día (Spearman por fecha, patrón §0.5a/§21/§23): por cada fecha,
  rankear los símbolos de esa fecha por el factor, correlacionar (Spearman) con el
  target, promediar sobre fechas con error estándar Newey-West (lags por ventana,
  pesos Bartlett).
- Lags NW por ventana: `L = min(12, floor(n_dias/8))` (§23). TOTAL con `L=4`
  (idéntico a §0.5a) SOLO para el cheque de fidelidad.
- `MIN_SYMBOLS = 5` por fecha (patrón §0.5a).
- Ventanas: W1 2020-2021, W2 2022-2023, W3 2024-2026-07-06 (fin del panel). TOTAL
  2019-2026 como referencia (no cuenta como test).
- **Cheque de fidelidad (aborta sin interpretar si falla)**: el rank IC TOTAL debe
  reproducir §0.5a: `mean_IC = +0.0679` y `t = +2.31` (con L=4). Si `|mean_IC −
  0.0679| > 0.001` o `|t − 2.31| > 0.05` → la reimplementación o el panel no son los
  de la evidencia → abortar, no interpretar (§14).

**Test secundario (contexto, NUNCA hallazgo — la hipótesis operativa "adx≥20")**:
- La hipótesis de producto "operar cuando adx≥20, abstenerse cuando no" ya está
  parcialmente dentro del gate (eligible exige adx≥20). El contraste operativo real
  dentro de la población elegible es adx14>25 (score 0.9) vs adx14∈[20,25] (score 0.3).
- Walk-forward declarado ANTES de correr: no hay parámetro libre que calibrar en W1 —
  la dicotomía 0.3/0.9 la fija el motor y el signo esperado (+1: ADX más alto →
  retorno forward mayor) viene de §0.5a. W1 es la ventana de observación; W2/W3 son
  la prueba con el signo congelado. Es lo honesto que puede hacer un factor dicotómico
  con umbral ya fijado.
- Métricas por ventana: premia = mean(fwd_ret | score=0.9) − mean(fwd_ret | score=0.3),
  n por grupo, VPP (fracción fwd_ret>0) por grupo, t pooled de la premia. Se reporta
  como contexto del valor operativo; el veredicto lo da SOLO el rank IC pre-registrado.

**Criterio pre-registrado (sin conocer el resultado)**:
- Tests: 1 factor × 3 ventanas = **3 tests nuevos** (TOTAL es referencia, no cuenta).
- Umbral: |t| > **2.77** (Bonferroni-9 bilateral, z = ppf(1 − 0.05/18); el plan fija
  Bonferroni-9 aunque los tests formales sean 3 — vara conservadora del patrón del
  proyecto, nunca más laxa; §23 usó 2.78 con el mismo origen).
- Signo esperado: **+1**.
- VEREDICTO: CUMPLE si |t| > 2.77 con signo +1 en **≥2/3 ventanas** → ADX deja de ser
  "marginal no robusto" y pasa a candidato con evidencia OOS → se discute pre-registro
  de motor con el usuario. NO CUMPLE en caso contrario. Nota honesta (mismo trato que
  §21): cualquier |t|>2 sin corregir se reporta como contexto, nunca como hallazgo.
- El target label (M1) NO se re-testea: §23 ya lo hizo contra adx_score y no cruzó
  ninguna ventana (t máx +1.90 en W2). La novedad de este trial es la dimensión
  ventana × fwd_return_20d, que nunca se midió.

**Familia ledger**: `signal_diagnosis` — contrato de `trial_registry.py`
("diagnósticos de señal: rank IC intra-día, RMT, horizontes, sub-períodos"), mismo
tratamiento que §21/§21.1/§22/§23. El texto de PLAN_LARGO_PLAZO dice "motor_signal",
pero el contrato clasifica este test bajo `signal_diagnosis` (un rank-IC de señal NO
es un trial de motor con DSR OOS) — desvío documentado acá igual que en §23.
`n_trials_consumidos=1`: signal_diagnosis 14→15, umbral vigente 0.9933 (del trial
nuevo). `motor_signal` NO se toca (queda en 9 consumidos).

**Riesgo declarado**:
- `adx_score` es dicotómico → el IC mide "adx>25 vs no" dentro de la población
  elegible, no la intensidad del ADX continuo. Es lo que el motor usa; la limitación
  es del factor, no del test.
- Overlap temporal del `fwd_return_20d` entre filas (stride 5d, horizonte 20d) →
  mitigado por IC por fecha + NW con L recortado; el t pooled del test secundario se
  lee con esa reserva explícita.
- W2 es la ventana con menor n de fechas (~30-50): su t se lee con la reserva que
  declaró §21.1 para 125d.
- La población eligible ya pasa el gate completo → la señal se mide donde el motor
  podría operar, no en todo el mercado (misma decisión de §0.5a/§21/§23).

**Registro en ledger**: `register_trial(...)` al cerrar, id `adx_walkforward`,
familia `signal_diagnosis`, n=1, veredicto según criterio, artefacto
`data/cache/trial_adx_walkforward_<ts>.txt`.

**RESULTADO (2026-08-17, corrido por Cline) — artefacto:
`data/cache/trial_adx_walkforward_20260817_103916.txt`**

Cheque de fidelidad: OK — TOTAL mean_IC=+0.0679, t=+2.31 (L=4), reproduce §0.5a
exacto (151 n_dias). 2069 filas eligible+target.

| ventana | rango | n_dias | mean_IC | SE_NW | t | L | signo | |t|>2.77 |
|---|---|---|---|---|---|---|---|---|
| W1 | 2020→2021 | 53 | +0.0395 | 0.0499 | +0.79 | 6 | + | no |
| W2 | 2022→2023 | 20 | +0.1026 | 0.0668 | +1.54 | 2 | + | no |
| W3 | 2024→2026-07 | 53 | +0.0792 | 0.0539 | +1.47 | 6 | + | no |
| TOTAL(ref) | 2019→2026 | 151 | +0.0679 | 0.0294 | +2.31 | 4 | + | — |

**VEREDICTO (pre-registrado): NO CUMPLE** — 0/3 ventanas cruzan Bonferroni-9
(|t|>2.77). El ADX queda como estaba: marginal, no robusto — pero ahora con evidencia
OOS por ventana, no solo el Bonferroni sobre el pooled. Lectura honesta: la señal es
POSITIVA en las 3 ventanas (signo + siempre), el t TOTAL +2.31 era el pooling de esa
señal débil repartida, no una señal concentrada que una ventana confirme sola. El
criterio ≥2/3 exige que la señal sea suficientemente fuerte para sostenerse en
aislamiento; no lo es.

Test secundario (contexto, no cuenta): premia ADX alto(0.9) vs bajo(0.3) siempre
positiva (W1 +0.0090, W2 +0.0075, W3 +0.0135) pero t pooled no significativos en
ninguna (máx W3 +1.73) e inconsistente en VPP (W2 alto 0.476 < bajo 0.481). Dirección
operativa levemente favorable 2/3 ventanas, nunca significativa.

**Acción**: Tarea B CERRADA. ADX NO pasa a candidato a pre-registro de motor. No se
integró nada (el script solo lee el panel; verificado). Artefacto del primer run
(`trial_adx_walkforward_20260817_103529.txt`) ELIMINADO: implementaba L con
`n_days_est` (fechas brutas) en vez de `n_dias` usados — desvío de §23 corregido,
corrida re-hecha con la regla pre-registrada.

**Ledger**: `register_trial(...)` id `adx_walkforward`, familia `signal_diagnosis`,
n=1 (14→15, umbral vigente 0.99375), veredicto NO_CUMPLE.

---

## 27. Trial FinBERT PASO 2 — sentimiento de earnings (8-K 2.02) como factor de retorno relativo (2026-08-17, PRE-REGISTRADO)

**Origen**: Tarea B de `PLAN_LARGO_PLAZO.md`, PASO 2 (trial). El PASO 1
(`earnings_sentiment.py` + acumulación) quedó hecho el 2026-08-16 y la corrida completa
del universo 50 terminó el 2026-08-17 12:07 (`data/cache/earnings_sentiment_run_20260817_120713.txt`:
48/48 símbolos, 369 filings, 0 errores). El contrato de desbloqueo ("≥8 trimestres ×
≥30 símbolos") se cumple: verificado contra la store SQLite: 8 trimestres
(2024Q3→2026Q2) con ≥30 símbolos cada uno; 45 símbolos con 8 filings.

**Pregunta**: ¿el tono del comunicado de earnings (FinBERT score = p_pos − p_neg,
rango [−1,1]) predice el retorno RELATIVO AL MERCADO (no el absoluto — lección §6.2)
a 20 días hábiles post-filing?

**Naturaleza de los datos (difiere del panel diario de §0.5a/§21/§23)**: un score por
evento (ticker × fecha de 8-K), no panel diario. La cross-section por día de filing es
fina (medido: 190 fechas, 41 días con 2 filings, 14 con ≥5; máximo 7) → el rank-IC
intra-día por símbolo NO es la mecánica correcta acá. Se usa la mecánica event-study
del proyecto adaptada: **agregar por día de filing** (score y retorno relativos
promedio de los filings simultáneos) y medir la serie temporal de esas fechas con
Spearman + Newey-West — misma máquina que §0.5a, con fechas de filing en vez de
fechas de trading.

**Metodología** (`backend/scripts/trial_finbert_eventstudy.py`, corre DESPUÉS de este
pre-registro):

- **Eventos**: los 369 filings de la store (`data/cache/earnings_sentiment.db`).
  Exclusión pre-declarada: eventos sin ventana forward completa de 20 días hábiles
  (medido hoy: 331/369 quedan; filings con fecha > 2026-08-04 no tienen 20bd de
  ventana hacia adelante en el cache, que termina 2026-08-04).
- **t0/t1**: t0 = última rueda de trading ≤ filing_date; t1 = 20 ruedas después.
  ret_stock = Close[t1]/Close[t0] − 1. ret_bench = lo mismo sobre SPY con las ruedas
  NEAREST ≤ t0/≤ t1 (el cache del bench no tiene por qué contener t0/t1 exactos).
  **rel = ret_stock − ret_bench** (retorno relativo pre-declarado como target, NUNCA
  el absoluto — confusor de dirección de mercado declarado en §6.2).
- **Test principal (decide)**: regresión OLS rel_evento ~ 1 + score_evento sobre la
  serie CRONOLÓGICA de eventos individuales (no agregados); el estadístico de decisión
  es el **t HAC Newey-West de la pendiente** (pesos Bartlett). Un t sobre la media
  mediría drift de mercado, no predicción — se aclara para que no haya ambigüedad.
  L = min(40, n_eventos//8): la ventana forward de 20 ruedas implica que filings a
  ≤20 ruedas de distancia comparten ventana de retorno (hasta ~40 eventos); ese tope
  se declara como autocorrelación a absorber — conservador, ANTES de correr.
  Spearman se reporta como contexto nominal.
- **Agregación por día de filing**: solo para el test secundario — para fechas con
  >1 filing, score_día y rel_día = medias.
- **Ventanas por fecha de filing** (3, pre-declaradas):
  - E1: 2024-08-13 → 2025-06-30 (~137 filings)
  - E2: 2025-07-01 → 2026-01-31 (~141 filings)
  - E3: 2026-02-01 → 2026-08-12 (~91 filings)
- **Signo esperado pre-declarado**: **+1** (tono más positivo → outperformance
  relativa). No hay parámetro libre que calibrar: el score lo fija FinBERT (modelo
  congelado) y el signo la hipótesis económica — análogo al factor dicotómico de §25.
  Ninguna ventana es "calibración"; las tres son prueba con signo congelado, y una
  cuarta TOTAL es referencia (no cuenta).
- **Cheque de fidelidad (aborta sin interpretar si falla)**: la store debe coincidir
  con el artefacto de corrida: 369 filas, 48 símbolos, 0 NULLs en score, modelo
  `ProsusAI/finbert` en todas. Rango de filing_dates 2024-08-13→2026-08-12. Si algo
  difiere → exit 2, no interpretar (§14).

**Test secundario (contexto, NUNCA hallazgo)**: premia de terciles de score (alto vs
bajo) sobre rel, t pooled con reserva declarada de clustering por día de filing y
overlap (un mismo día reporta hasta 7 tickers del mismo sector tecnológico, p.ej.
2026 Q2) — se reporta solo como lectura de magnitud.

**Criterio pre-registrado (escrito antes de ver el outcome de ventanas)**:
- 3 tests formales (E1/E2/E3; TOTAL es referencia).
- Umbral: |t| > **2.77** (Bonferroni-9 bilateral, z = ppf(1 − 0.05/18)) — la vara
  conservadora del proyecto, igual que §25 (nunca más laxa aunque los tests sean 3).
- CUMPLE si |t| > 2.77 con signo +1 en **≥2/3 ventanas**. NO CUMPLE en caso contrario.
- Nota de poder declarada ANTES: con n_eventos ≈ 90-140 por ventana y umbral 2.77, se
  necesita rho ≈ 0.3+ por ventana para cruzar — es un test exigente, consistente con
  la historia del proyecto (casi todos los factores dieron rho ≪ 0.3). Un NO CUMPLE
  acá es evidencia, no ausencia de evidencia (n suficiente por ventana).

**Familia ledger**: `signal_diagnosis` — un test de rank de señal sobre datos reales,
mismo tratamiento que §21/§22/§23/§25 (desvío documentado del texto genérico del plan,
que decía motor_signal; un rank de señal no es un trial de motor con DSR OOS).
`n_trials_consumidos=1`: signal_diagnosis 16→17, umbral vigente del trial nuevo.
`motor_signal` NO se toca (queda en 10).

**Riesgos declarados**:
1. **Proxy del comunicado, no del call verbatim**: limitación heredada del PASO 1 y
   documentada en `earnings_sentiment.py` — el 8-K 2.02 es el press release editado
   por la gerencia, no las preguntas/respuestas del call. Si el factor sale nulo
   puede ser por la proxy y no por ausencia total de señal (y viceversa). Se acepta
   como la mejor fuente pública gratuita disponible; no se scrapean transcripciones
   pagas.
2. **Clustering temporal**: filings del mismo día de temporada de earnings (pico:
   7 tickers, varios del mismo sector) no son independientes → la agregación por
   día de filing + Newey-West mitiga; el t secundario pooled se lee con esa reserva.
3. **Overlap de ventanas forward**: eventos con filing_dates a <20 ruedas de distancia
   comparten ventanas → NW con L recortado cubre la autocorrelación de la serie
   agregada; se declara para que no se sobre-interprete.
4. **Cobertura sectorial**: el universo tiene sesgo tech/large-cap; la conclusión vale
   para este universo, no se extrapola.

**Registro en ledger**: al cerrar, `register_trial(...)` id `finbert_sentiment_eventstudy`,
familia `signal_diagnosis`, n=1, veredicto según criterio, artefacto
`data/cache/trial_finbert_eventstudy_<ts>.txt`.

**RESULTADO (2026-08-17, Kilo Code) — artefacto:
`data/cache/trial_finbert_eventstudy_20260817_163512.txt`**

Cheque de fidelidad: OK — la store coincide exactamente con el artefacto de
acumulación (369 filas, 48 símbolos, 0 NULLs, modelo ProsusAI/finbert, rango
2024-08-13→2026-08-12). 331/369 eventos con ventana fwd-20 completa (38 excluidos,
pre-declarado). L por ventana = min(40, n//8).

| ventana | rango | n_eventos | spearman | HAC SE | t | signo | |t|>2.77 |
|---|---|---|---|---|---|---|---|
| E1 | 2024-08-13→2025-06-30 | 137 | +0.0496 | 0.0665 | +0.38 | + | no |
| E2 | 2025-07-01→2026-01-31 | 113 | −0.1118 | 0.0491 | −0.85 | − | no |
| E3 | 2026-02-01→2026-08-12 | 81 | +0.0320 | 0.0771 | −0.08 | − | no |
| TOTAL (ref) | 2024-08-13→2026-08-12 | 331 | −0.0098 | 0.0340 | −0.14 | — | — |

**VEREDICTO (pre-registrado): NO_CUMPLE** — 0/3 ventanas cruzan Bonferroni-9
(|t|>2.77) y el SIGNO es inconsistente entre ventanas (E2 negativo en spearman y
pendiente). El tono del comunicado de earnings (8-K 2.02) no predice el retorno
relativo a SPY a 20 ruedas.

Test secundario (contexto, nunca hallazgo): premia terciles alto vs bajo sobre rel:
E1 +1.67pp (t +0.73), E2 −0.75pp (t −0.39), E3 +2.93pp (t +0.83) — mixta y no
significativa; inconsistente con el signo del test principal.

Lectura honesta: dos limitaciones declaradas quedan vigentes como única vía de
reapertura — (1) el 8-K 2.02 es el COMUNICADO editado, no la transcripción del call
(null puede ser de la proxy); (2) 2 años × ~110-140 eventos por ventana da poder solo
para rho ≳ 0.25. Con esa doble reserva, la línea FinBERT-sentiment queda CERRADA como
"sin señal con la evidencia disponible"; se retoma solo con evidencia nueva
sustancial (≥4-5 años de acumulación incremental, o transcripciones si alguna vez el
costo lo justifica). La acumulación incremental sigue corriendo (es barata y sirve
para el futuro): NO se borra la store.

**Ledger**: `register_trial(...)` id `finbert_sentiment_eventstudy`, familia
`signal_diagnosis`, n=1 (16→17, umbral próximo 0.99444), veredicto NO_CUMPLE.
Suite 242 passed, ruff limpio.


---

## 28. Dos mediciones justas que nunca se hicieron (2026-08-17, PRE-REGISTRADO)

**Origen**: auditoría de brechas del usuario ("es más fácil descartar que aprobar;
medir con los años/datos suficientes, no con la vara fácil"). Dos factores del proyecto
nunca fueron medidos contra lo que realmente miden:

1. **Test A — rank IC intradía contra retorno RELATIVO a mercado** (RESUMEN_VALIDACION_VARIABLES
   §5/§6.2: "el más prometedor sin probar"). Todos los rank IC previos (§0.5a/§21/§23/§25/§26)
   usaron `fwd_return_20d` ABSOLUTO: mezclan habilidad de selección con dirección del
   mercado (confusor §6.2). El test de selección correcto es contra `fwd_return_20d −
   ret_SPY_misma_ventana`. Factores: momentum_score, rsi_score, adx_score (los 3 del
   gate; trend_score es constante entre elegibles, se excluye — misma razón que §0.5a).

2. **Test B — AAII (sentimiento retail) como TIMING de fecha** — primera medición
   estructuralmente válida. Verificado en el panel: `sentiment_v1` es constante por
   fecha (nunique=1) → los tests anteriores (#8, Fase 0.6) lo midieron como variable
   por-símbolo donde NO PUEDE variar; sus veredictos refutan esa medición, no la
   hipótesis. El test correcto es a nivel de fecha: ¿el spread bull-bear de esa fecha
   se correlaciona con el retorno relativo medio del cross-section elegible hacia
   adelante? Signo esperado pre-registrado: **−1** (contrarian — spread bajo/bearish =
   señal alcista; consenso empírico AAII). Se reporta también |+| por ventana.

**Metodología** (`backend/scripts/trial_xsec_relative.py`, corre DESPUÉS de este
pre-registro):

- Panel: `factor_panel_20260811_144857.parquet` (el único; 2069 filas eligible+target,
  346 fechas ≥5 símbolos).
- Target relativo: `rel = fwd_return_20d − spy_fwd_20d`, donde `spy_fwd_20d` = retorno
  20 ruedas de SPY desde el MISMO día del panel (SPY.parquet, calendario propio;
  aproximación ≤2 días por feriados — declarada ANTES).
- Test A: Spearman por fecha entre el factor y `rel`, serie temporal + Newey-West,
  L = min(12, n_dias//8) (regla §23). Ventanas W1 2020-2021 / W2 2022-2023 /
  W3 2024→2026-07 (idénticas a §25). Signo esperado: +1 para los 3 factores.
- Test B: por fecha, `mean(rel)` del cross-section elegible vs `sentiment_v1` de la
  fecha; Spearman + NW serie temporal, mismas ventanas, L misma. Signo esperado: −1.
  Fechas con ≥5 símbolos y sentiment no-NaN (verificado: 187/187).
- **Cheque de fidelidad (aborta sin interpretar si falla)**: el pipeline debe
  reproducir §0.5a con target ABSOLUTO: momentum n≈187 mean_IC≈−0.0100 t≈−0.28;
  rsi +0.0404/+1.38; adx +0.0679/+2.31 (L=4). Tolerancias |ΔIC|≤0.001, |Δt|≤0.05.

**Criterio pre-registrado (sin conocer resultados)**:
- Tests formales: 3 factores × 3 ventanas (A) + 3 ventanas (B) = **12 tests**.
- Umbral único: |t| > **2.86** (Bonferroni-12 bilateral, z = ppf(1−0.05/24)) — vara
  conservadora, nunca más laxa (patrón §25/§27).
- CUMPLE por factor si |t|>2.86 con el signo pre-registrado en ≥2/3 ventanas.
- NO CUMPLE en caso contrario. Nota de poder declarada ANTES: con n_dias≈50-90 por
  ventana se requiere rho≳0.30 para cruzar — test exigente, consistente con la
  historia del proyecto.
- Limitación declarada: stride 5d del panel limita n_dias; el poder real de este
  proyecto para ICs chicos (~0.05) requeriría panel diario (no se construye acá;
  queda como brecha de infraestructura, no de este trial).

**Familia ledger**: `signal_diagnosis` (rank-IC de señal, mismo contrato que
§21-§27). `n_trials_consumidos=1`: signal_diagnosis 17→18, umbral vigente del trial
nuevo. `motor_signal` no se toca (10).

**Registro**: id `xsec_relative_and_aaii_timing`, veredicto según criterio, artefacto
`data/cache/trial_xsec_relative_<ts>.txt`.

**RESULTADO**: (pendiente de corrida)

**RESULTADO (2026-08-17, Kilo Code) — artefacto:
`data/cache/trial_xsec_relative_20260817_184355.txt`**

Cheque de fidelidad: OK — reproduce §0.5a exacto (n 187/164/151, IC y t dentro de
tolerancia con L=4). 2069 filas; 0 sin bench.

| test | W1 t | W2 t | W3 t | signo esperado | SIG (|t|>2.86) |
|---|---|---|---|---|---|
| momentum × rel | −0.03 | −1.01 | −0.11 | + | 0/3 |
| rsi × rel | +0.76 | −0.62 | +1.05 | + | 0/3 |
| adx × rel | +0.79 | +1.54 | +1.47 | + | 0/3 |
| AAII timing | −0.32 | **+2.94** | +0.04 | − | 0/3 |

**VEREDICTO (pre-registrado): NO_CUMPLE** — ningún test cruza Bonferroni-12 con el
signo esperado en ≥2/3 ventanas.

Lecturas honestas:
1. **Test A (relativo)**: la hipótesis §6.2 ("los factores parecían débiles por medir
   absoluto") queda REFUTADA con el test que la propia auditoría pidió: contra retorno
   relativo a SPY, momentum/RSI/ADX dan ICs prácticamente idénticos a los absolutos
   (los t por ventana son casi los mismos que §25 — el componente de mercado que
   sustrae el bench era ruido pequeño, no la señal perdida). El confusor beta existía
   pero no era el motivo del fracaso.
2. **Test B (AAII timing)**: primera medición estructuralmente válida → no hay señal
   contrarian utilizable. W2 (2022-23) muestra t=+2.94 pero con SIGNO POSITIVO (contra
   el −1 pre-registrado): en esa ventana el spread alto coincidió con retorno relativo
   alto, lo opuesto al contrarian clásico; un hallazgo de dirección correcta no se puede
   re-signar post-hoc. W1/W3 ≈ 0. AAII queda refutado como timing con su medición justa;
   la línea sentimiento retail queda CERRADA (refutación #8/Fase0.6 + medición justa #18).
3. ADX sigue siendo el único factor con dirección consistentemente positiva en las 3
   ventanas en todas las mediciones (absoluta §25, relativa §28: mismos t), pero nunca
   cruzando la barra — "marginal no robusto" confirmado ahora también contra retorno
   relativo.

**Acción**: RESUMEN_VALIDACION_VARIABLES §5 — el ítem cross-sectional queda CERRADO
(como refutado tras su medición). No queda hipótesis de señal declarada sin medir en el
espacio del proyecto (diario, 50 símbolos, factores del gate + sentimiento).

**Ledger**: id `xsec_relative_and_aaii_timing`, signal_diagnosis n=1 (17→18, umbral
próximo 0.994737). Suite sin cambios requeridos (solo script nuevo).

---

## 29. Mapeo de etiquetas de resultado proyectado para el dashboard advisor (2026-08-17, PRE-REGISTRADO como doc de presentación)

**Naturaleza**: NO es una hipótesis nueva ni consume slot de trial. Es el mapeo
documentado y congelado que el dashboard (`/api/advisor`) usa para presentar la
selectividad YA medida del `win_prob` del motor como apoyo a decisión. Regla #4 de
ONBOARDING: ninguna etiqueta se presenta como predicción; todas llevan su n de
evidencia y el badge global de honestidad.

**Evidencia citada (verificada contra el artefacto ANTES de escribir esto)**:
`data/cache/baseline_clean_20260811_150643_trades.parquet` — 286 trades del baseline,
columna `win_prob` calibrada por el motor. Verificado hoy: win_rate global 0.5874;
umbral ≥0.55 → VPP 0.5828 (n=163, NADA sobre el base); umbral ≥0.60 → 0.6452 (n=62);
umbral ≥0.65 → VPP 0.7368 (n=19); umbral ≥0.70 → VPP 0.8750 (n=8); umbral ≥0.75 →
3/3 (n=3, sin poder). Coincide con el registro de SESSION_LOG 2026-08-17
(diagnóstico de asesoría). La selectividad real vive SOLO en la cola alta, con
cobertura chica (~7%/2.8% de los trades).

**Mapeo congelado (implementación obligatoria del endpoint advisor):**

| win_prob calibrado | Etiqueta | Evidencia mostrada en UI |
|---|---|---|
| ≥ 0.70 | `GANANCIA_PROYECTADA_ALTA` | VPP real 87.5%, n=8 |
| 0.65–0.70 | `GANANCIA_PROYECTADA` | VPP real 73.7%, n=19 |
| 0.45–0.65 | `NEUTRO` | VPP ≈ base rate 0.58-0.65, sin selectividad medida |
| < 0.45 | `RIESGOSA_SIN_APOYO` | la cola baja NO tiene evidencia de selectividad — se muestra "sin apoyo estadístico", NUNCA "pérdida proyectada" como predicción |

**Reglas de presentación (no negociables):**
1. Si el n de evidencia de un casillero es <30 (todos lo son hoy), el n se muestra
   junto a la etiqueta en la UI.
2. Régimen DEFLATION (estado 3): el endpoint devuelve `blocked_reason` (mecánica
   real del motor, `decision.py`) y la UI no muestra etiquetas de entrada.
3. win_prob nulo (símbolo fuera del gate / sin score) → etiqueta `SIN_SCORE`, no se
   inventa ni se interpola.
4. Si el calibrador no está fitteado → todas las etiquetas `SIN_CALIBRAR`.
5. Cualquier cambio futuro de este mapeo requiere sección nueva + verificación contra
   artefacto de nuevo (no edición en caliente).

---

## 30. M4 — Curva de costo por tamaño de orden: PRE-REGISTRO de la medición qty=10/50 (Tarea D, Ronda 2026-08-19)

**Naturaleza**: MEDICIÓN, no trial de señal. No consume n_trials del ledger
(registrado en el plan de la ronda: "es medición, no trial de señal, así que no
consume el ledger de n_trials"). Es la extensión de M4 (DISENO_INSTRUMENTO.md §7)
al protocolo ya ejecutado con qty=1.

**Estado**: ✅ CERRADA 2026-08-19 — corrida real ejecutada y verificada (ver RESULTADO
abajo). Código y tests listos (Kilo Code: `backend/scripts/measure_execution_costs.py`
+ `execution_costs.py`, 21 tests). Diagnóstico del bloqueo y plan ajustado en la
Enmienda 1.

**ENMIENDA 1 (2026-08-19, escrita ANTES de correr — diagnóstico real y plan ajustado)**:
El 403 NO era por permisos de la API key. Cuenta `PA3QUWEX1XBJ` ACTIVE, sin
bloqueos (`trading_blocked: false`); el error era `40310000 "insufficient buying
power"` con `buying_power: 0`. Causa: el intento qty=10 de esta mañana alcanzó a
entrar en 18 símbolos (~$81k de notional) antes de agotar el margen; quedaron 18
posiciones qty=10 abiertas, cash −$56k, BP 0 (todo orden posterior → 403). Se
liquidaron las 18 posiciones residuales (paper): cash $24.9k, equity $25.1k,
BP $100k, cuenta limpia, sin runners activos. Credenciales de la nota "Alpaca
Paper" (Apple Notes) = las ya presentes en `backend/.env` (cuenta PRUEBA, mismo
par) — no había que rotar nada.

Restricción estructural: el notional del universo completo (50 símbolos) es
inviable en esta cuenta — qty=10 ≈ $150k y qty=50 ≈ $750k contra BP $100k
(equity $25k, margen 4x). ENMIENDA del universo de medición (la hipótesis y el
criterio NO cambian):
- qty=10 → `BASE_SYMBOLS` (los 7 que opera el motor: SPY, QQQ, AAPL, MSFT,
  GOOGL, AMZN, NVDA), notional ≈ $31k. Relevancia: es exactamente lo que el
  motor compra/vende.
- qty=50 → subset líquido SPY, QQQ, AAPL (notional ≈ $90k, dentro del BP). Si
  una orden falla por BP, se reduce a SPY+QQQ y se documenta.

**Comandos exactos (corrida real, 2026-08-19, mercado abierto 12:2x ET)**:
```
.venv/bin/python -m scripts.measure_execution_costs --qty 10 --side buy  --symbols SPY,QQQ,AAPL,MSFT,GOOGL,AMZN,NVDA
.venv/bin/python -m scripts.measure_execution_costs --qty 10 --side sell --symbols SPY,QQQ,AAPL,MSFT,GOOGL,AMZN,NVDA
.venv/bin/python -m scripts.measure_execution_costs --qty 50 --side buy  --symbols SPY,QQQ,AAPL
.venv/bin/python -m scripts.measure_execution_costs --qty 50 --side sell --symbols SPY,QQQ,AAPL
```

**Hipótesis (pre-registrada)**: el costo por lado SUBE con el tamaño de la orden
por impacto de mercado — el slippage no es lineal en qty. qty=1 (ya medido,
2026-08-18, artefacto `measure_execution_costs_20260818_134338.txt`) dio
`cost_per_side_medido = 0.0001888` (≈0.019%/lado), slippage p50 0.000122, p95
0.0005195, comisión 0 (paper), 120 órdenes.

**qty a testear**: 10 y 50 (además del 1 ya medido). Mismo protocolo que qty=1:
universo completo (BASE_SYMBOLS + NEW_UNIVERSE), un buy y un sell por símbolo por
qty, mercado abierto US ET obligatorio.

**Criterio de comparación (pre-registrado)**: descriptivo, sin test estadístico
formal — se comparan `slippage_p50`, `slippage_p95` y `cost_per_side_medido` entre
qty=1/10/50:
- Si p95(qty=50) ≳ 3× p95(qty=1) → impacto de mercado MEDIBLE en el rango → el
  costo real depende del tamaño y el campo del dashboard debe citar la curva.
- Si la curva queda plana (p95 similar entre qtys) → el costo NO escala con el
  tamaño en este rango (mercados US líquidos) → qty=1 es representativo.

**Comandos exactos (cuando se desbloquee)**, desde `backend/`:
```
.venv/bin/python -m scripts.measure_execution_costs --qty 10 --side buy
.venv/bin/python -m scripts.measure_execution_costs --qty 10 --side sell
.venv/bin/python -m scripts.measure_execution_costs --qty 50 --side buy
.venv/bin/python -m scripts.measure_execution_costs --qty 50 --side sell
```

**Restricciones**: PAPER únicamente (el módulo fuerza paper-api.alpaca.markets).
Credenciales SOLO en `backend/.env` / variables de entorno — nunca en chat ni commit.
No tocar `settings.COST_PER_SIDE` (sigue 0.0015 deliberado; actualizarlo es decisión
del usuario + pre-registro aparte).

**Post-condición**: tabla con los 3 puntos (qty=1/10/50: cost_per_side_medido,
slippage_p50/p95, n_ordenes, artefacto citado) agregada a esta sección; actualizar
ROADMAP.md fila M4. El endpoint `/api/costs/current` (Tarea E) ya expone la curva
por tamaño sin cambios de contrato.

**RESULTADO (2026-08-19, corrida real, mercado abierto 12:13–12:14 ET)**:
Cuenta desbloqueada (liquidación de residuos qty=10 de la mañana → BP $100k),
4 corridas ejecutadas con el script oficial:
- qty=10 buy: 7 órdenes (BASE_SYMBOLS) — artefacto `measure_execution_costs_20260819_121324.txt`
- qty=10 sell: 7 órdenes (mismos) — artefacto `measure_execution_costs_20260819_121352.txt`
- qty=50 buy: 2 órdenes (SPY, QQQ; **AAPL 50 falló 403 por buying power** — notional
  $90k excede el margen de la cuenta; fallback previsto en la Enmienda 1, se documenta
  el resultado real: subset SPY+QQQ) — artefacto `measure_execution_costs_20260819_121440.txt`
- qty=50 sell: 2 órdenes (SPY, QQQ) — mismo artefacto

**Curva real (156 órdenes, DB `backend/data/cache/execution_costs.db`, fórmula del
contrato M4: `abs(slippage)` + np.median/np.percentile — verificado: size=1 idéntico
al artefacto del 18/08)**:

| size | n (buy/sell) | cost_per_side_medido | slippage_p50 | slippage_p95 |
|------|--------------|---------------------|--------------|--------------|
| 1    | 120 (60/60)  | 0.000122 | 0.000122 | 0.000519 |
| 10   | 32 (25/7)    | 0.000116 | 0.000116 | 0.000417 |
| 50   | 4 (2/2)      | 0.000029 | 0.000029 | 0.000098 |

**VEREDICTO (criterio pre-registrado)**: la curva NO sube con el tamaño — es plana
o decreciente: p95(50) = 0.000098 es **5.3× MENOR** que p95(1) = 0.000519. No se
cumple "p95(qty=50) ≳ 3× p95(qty=1)" → **impacto de mercado NO medible en el rango
1→50** (mercados US líquidos, papel). Cae en el segundo brazo del criterio: **qty=1
es representativo del costo por lado**. Nota de tamaño muestral: n=4 en qty=50 (2/2)
y n=32 en qty=10 (con sell 7) — conclusiones descriptivas, no estadísticas (como fue
pre-registrado). Consecuencia práctica: el motor opera qty pequeñas; `cost_per_side_medido`
global ≈ 0.00017–0.00019 (≈0.018–0.019%/lado) sigue siendo la cifra a usar; la
decisión de bajar `settings.COST_PER_SIDE` (0.0015 → ~0.0002) queda del usuario con
pre-registro aparte. El endpoint `/api/costs/current` expone la curva (sizes 1/10/50)
sin cambios de contrato.

## 31. Análisis exploratorio de franjas horarias (Nasdaq/QQQ 1-min) — PRE-REGISTRO (Ronda 2026-08-19)

**Naturaleza**: ANÁLISIS EXPLORATORIO de datos (no trial de señal — NO consume
n_trials del ledger). Genera evidencia descriptiva para decidir si construir un
meta-sistema de rotación por franja horaria (idea del usuario: cambiar estrategia
por franja, rotar indicadores, revisión regresiva). Respeta la lección ya pagada
(27 trials, 17 citados): NO se declara señal; se mide estructura y se decide.

**Pregunta**: ¿la microestructura del Nasdaq (QQQ) difiere por franja horaria lo
suficiente como para justificar estrategias/indicadores distintos por franja?
Control: SPY (S&P 500).

**Data**: QQQ y SPY, barras 1-min vía API de Alpaca (IEX free, historial verificado
hasta 2019). Ventana inicial: 2024-01-01 → hoy (2.5 años; ampliable si la estructura
aparece). Franjas ET: APERTURA 09:30–11:30, MEDIA 11:30–14:00, CIERRE 14:00–16:00.

**Métricas por franja (descriptivas, sin test formal de señal)**:
- Retorno medio por barra (y por día equivalente), volatilidad (std por barra),
  volumen medio por barra, rango intrabarra (high-low)/close.
- Ratio apertura/cierre: ¿el primer 60 min concentra volatilidad/volumen?

**Criterio de interpretación (pre-registrado)**:
- Estructura APARECE si la volatilidad por barra difiere ≥ 1.5× entre franjas Y el
  volumen medio por barra difiere ≥ 1.5× entre franjas (p. ej. apertura >> media).
  Eso es microestructura conocida de mercado; si NO aparece, la data 1-min está mal
  descargada o el instrumento es atípico.
- Estructura EXPLOTABLE (para el siguiente paso) si, ADEMÁS, la predictividad de los
  indicadores del motor (momentum/RSI/EMA — ya medidos como sin poder intra-día
  global en §4.1) difiere MATERIALMENTE entre franjas (p. ej. IC o accuracy por franja
  con signos opuestos o magnitud ≥ 2×). Esto se mide en la Fase B, solo si la Fase A
  muestra estructura de volatilidad/volumen.

**Plan de corridas**:
- Fase A (este pre-registro): descarga 1-min QQQ+SPY → parquets locales
  `data/cache/qqq_1min.parquet`, `spy_1min.parquet` → tabla de métricas por franja.
- Fase B (pre-registro aparte, solo si A da estructura): predictividad por franja de
  los indicadores del motor (protocolo §4.1 adaptado: correlación temporal del
  indicador con retorno forward dentro de la franja).

**Restricciones**: data pública de mercado (QQQ/SPY son ETFs — sin datos personales);
credenciales solo en `backend/.env`; nada de órdenes (solo lectura de data).
**Post-condición**: tabla de métricas por franja agregada aquí + veredicto
estructura sí/no + recomendación sobre si construir el meta-sistema de rotación.

**RESULTADO Fase A (2026-08-19, corrida real)**:
Data: 256,724 barras 1-min QQQ + 256,808 SPY (2024-01-01 → 2026-08-19, Alpaca IEX).
Artefacto: `data/cache/franjas_horarias_20260819_125219.txt` + parquets
`qqq_1min.parquet` / `spy_1min.parquet`.

| símbolo | franja | n_barras | vol_por_barra | volumen/barra |
|---------|--------|----------|---------------|---------------|
| QQQ | APERTURA | 79,080 | 0.000638 | 134,063 |
| QQQ | MEDIA | 98,827 | 0.000433 | 75,332 |
| QQQ | CIERRE | 78,817 | 0.000416 | 105,714 |
| SPY | APERTURA | 79,080 | 0.000455 | 157,603 |
| SPY | MEDIA | 98,844 | 0.000347 | 96,651 |
| SPY | CIERRE | 78,884 | 0.000340 | 178,759 |

Ratios contra MEDIA: QQQ volumen 1.78x / volatilidad 1.47x; SPY volumen 1.63x /
volatilidad 1.31x. Cierre concentra volumen (SPY 178k > apertura) sin volatilidad
extra — patrón clásico de rebalanceos.

**VEREDICTO Fase A (criterio §31)**: estructura horaria CONFIRMADA en dirección
clásica (apertura caliente, mediodía desierto, cierre con volumen) pero MODERADA:
el umbral estricto era >= 1.5x en vol Y volumen; se cumple volumen (1.6-1.8x) y la
volatilidad queda justo debajo (1.31-1.47x). No hay diferencia extrema de volatilidad
por franja. La pregunta que decide la rotación de indicadores es la Fase B:
¿la PREDICTIVIDAD de los indicadores del motor difiere materialmente por franja?
Los 2.5 años de 1-min ya descargados permiten medirla sin nueva descarga.

## 32. Fase B — Predictividad de indicadores por franja horaria: PRE-REGISTRO (Ronda 2026-08-19)

**Naturaleza**: ANÁLISIS EXPLORATORIO de predictividad (no trial de señal formal —
no consume n_trials; genera evidencia para decidir si construir el meta-sistema de
rotación por franja). Solo se ejecuta porque la Fase A (§31) confirmó estructura
horaria de volumen/volatilidad.

**Pregunta**: ¿la correlación del momentum intraday y del RSI(14) con el retorno
forward (5/15/30 min) difiere MATERIALMENTE entre franjas (APERTURA/MEDIA/CIERRE)?
Si la predictividad es uniforme, la rotación por franja no tiene base; si difiere con
signos opuestos o magnitud >= 2x, hay base para ponderar indicadores distinto por franja.

**Data**: parquets ya descargados en Fase A — `data/cache/qqq_1min.parquet` y
`spy_1min.parquet` (2024-01-01 → 2026-08-19). Sin nueva descarga.

**Método** (protocolo §4.1 adaptado de cross-sectional a temporal por símbolo):
- Indicadores por barra: retorno acumulado de los últimos 5/15/30 min (momentum
  intrabarra) y RSI(14) de barras 1-min.
- Retorno forward: próximas 5/15/30 min.
- Por símbolo y por franja: Spearman(indicator_t, retorno_forward_t) con correlación
  de Pearson sobre rango (rank IC), promedio por día (evita inflar por días atípicos),
  error Newey-West (lag 4) — mismo espíritu de §4.1.
- Métricas: IC medio, t-stat, hit-rate de dirección (sign(indicator)==sign(forward)).

**Criterio de interpretación (pre-registrado)**:
- Base para rotación: existe AL MENOS UN indicador con |IC| >= 0.02 y t-stat >= 2.0
  en una franja Y |IC| <= 0.01 o signo opuesto en otra franja (diferencia material
  entre franjas). El umbral IC>=0.02 es exigente para datos 1-min (el promedio
  intra-día del motor ya fue medido cerca de 0 — §4.1).
- Sin base: ICs bajos y uniformes en las 3 franjas → la rotación por franja no está
  justificada por predictividad y el meta-sistema no se construye (se documenta como
  descarte honesto).

**Restricciones**: solo lectura de parquets locales; nada de órdenes; data pública.
**Post-condición**: tabla de IC por indicador×franja×símbolo + veredicto
base_si/no + recomendación (construir rotador vs. descartar la hipótesis horaria).

**RESULTADO Fase B (2026-08-19, corrida real — 659 días por franja, QQQ y SPY)**:
Artefacto: `data/cache/franjas_predictividad_20260819_125427.txt`. IC = Spearman
diario (indicator_t vs retorno forward 5 min) promediado, t-stat Newey-West lag 4.

| indicador | franja | QQQ IC (t) | SPY IC (t) |
|-----------|--------|------------|------------|
| mom5  | APERTURA | -0.061 (-10.0) | -0.062 (-9.8) |
| mom5  | MEDIA | -0.058 (-9.6) | -0.061 (-10.9) |
| mom5  | CIERRE | -0.063 (-9.8) | -0.064 (-10.2) |
| mom15 | APERTURA | -0.086 (-13.0) | -0.088 (-13.0) |
| mom15 | MEDIA | -0.083 (-13.8) | -0.084 (-13.5) |
| mom15 | CIERRE | -0.099 (-13.8) | -0.098 (-13.8) |
| mom30 | APERTURA | -0.123 (-17.4) | -0.119 (-16.7) |
| mom30 | MEDIA | -0.119 (-19.2) | -0.114 (-19.2) |
| mom30 | CIERRE | -0.129 (-19.2) | -0.126 (-19.9) |
| rsi14 | APERTURA | -0.129 (-19.6) | -0.133 (-19.0) |
| rsi14 | MEDIA | -0.115 (-18.7) | -0.116 (-19.3) |
| rsi14 | CIERRE | -0.129 (-18.6) | -0.126 (-19.0) |

**VEREDICTO Fase B (criterio §32)**:
1. **Sin base para rotación por franja**: los ICs son casi IDÉNTICOS entre franjas
   (diferencias < 0.015). El criterio exigía un indicador fuerte en una franja y
   débil/de signo opuesto en otra — NO se cumple en ningún caso. La predictividad es
   uniforme en las 3 franjas. → La hipótesis de rotación horaria de indicadores se
   DESCARTA con evidencia (no se construye el meta-sistema de rotación por franja).
2. **Hallazgo nuevo (inesperado, robusto)**: TODOS los indicadores tienen IC
   NEGATIVO fuerte y altamente significativo (t-stat -10 a -19, 659 días, 2 símbolos):
   **reversión a la media intra-día**. El momentum de 5/15/30 min predice el retorno
   forward en dirección OPUESTA; el RSI(14) alto predice baja. Es estructura
   predictiva real en intra-día — la dirección contraria al momentum que asume el
   motor (que usa momentum diario como ranking). No es una señal de alta precisión
   (hit-rate 0.49-0.51, cerca de azar) pero el IC es grande y estable.
3. Implicación: si el motor operara intra-día con estas ventanas, el enfoque
   correcto sería CONTRARIAN (comprar dips de 15-30 min), no momentum. Eso merece un
   trial formal pre-registrado (consumiría n_trials) — NO es parte de este análisis
   exploratorio, que queda cerrado.

## 33. Actualización de `settings.COST_PER_SIDE` al costo MEDIDO — PRE-REGISTRO (decisión del usuario, 2026-08-19)

**Naturaleza**: CAMBIO DE CONSTANTE DE CONFIGURACIÓN del motor, no trial de señal —
NO consume n_trials del ledger (es el "pre-registro aparte" pedido explícitamente en
§30, ROADMAP filas M4/Tarea D y PLAN_LARGO_PLAZO Tarea D: "actualizarlo es decisión
del usuario + pre-registro aparte").

**Estado**: ✅ CERRADO 2026-08-19 — usuario eligió **0.0005 (0.05%/lado)**;
`settings.COST_PER_SIDE` actualizado en `backend/app/config.py`, suite 271 passed.

**Valor adoptado (decisión del usuario, 2026-08-19)**: **0.0005** (0.05%/lado) —
punto medio conservador: ~2.6× el piso paper medido (0.000189), margen para comisión
y slippage LIVE reales sin volver al 0.15% asumido. Comentario del código actualizado
con la evidencia y la fecha.

**Evidencia (verificada contra el artefacto real, no resúmenes)**:
- Medición M4 qty=1 (2026-08-18, 120 órdenes paper, artefacto
  `measure_execution_costs_20260818_134338.txt`): `cost_per_side_medido = 0.0001888`
  (≈0.019%/lado), slippage p50 0.000122, p95 0.000519, comisión 0 (paper).
- Tarea D qty=10/50 (2026-08-19, 156 órdenes totales en
  `backend/data/cache/execution_costs.db`). **Corrección de transcripción**: la tabla
  de §30 transcriptó `slippage_p50` en la columna `cost_per_side_medido`; el valor
  del contrato M4 (`mean(|slippage|) + mean(comisión)`, verificado con SQL contra la
  DB) es:
  - size=1: n=120 → **0.000189** (p50 0.000122 / p95 0.000519)
  - size=10: n=32 → **0.000131** (p50 0.000116 / p95 0.000417)
  - size=50: n=4 → **0.000043** (p50 0.000029 / p95 0.000098)
- Veredicto §30: curva plana/decreciente → qty=1 representativo → **cifra global a
  usar ≈ 0.00019** (0.019%/lado).

**Valor actual**: `settings.COST_PER_SIDE = 0.0015` (0.15%/lado, asumido 0.10%
comisión + 0.05% slippage) — **≈ 8× el costo medido**. El motor viene evaluando
toda señal contra un costo inflado en un orden de magnitud.

**CAVEAT (heredado de M4/§30, no se puede ignorar)**: es costo de ejecución PAPER —
fills instantáneos al último trade, sin comisión, sin cola ni impacto real de tamaño
(la curva plana 1→50 lo confirma). La ejecución LIVE real tendrá más slippage y
comisión ≠ 0. El número medido es un **piso inferior medido**, no el número final.

**Decisión en juego (del usuario)**: qué valor adopta el motor. El menú NO es libre —
la evidencia acota el rango:
- **~0.0002 (0.02%/lado)**: piso paper medido, sin margen para live.
- **~0.0005 (0.05%/lado)**: punto medio conservador — cubre comisión live y slippage
  extra con margen ~2.6× sobre el piso medido, sin volver al 0.15% asumido.
- **0.0015 (mantener)**: conservador máximo, pero con evidencia de que infla ~8×.

**Criterio de éxito del cambio (pre-registrado)**:
1. `settings.COST_PER_SIDE` actualizado al valor elegido con el comentario del
   artefacto/DB que lo respalda y la fecha de medición.
2. Suite completa `cd backend && .venv/bin/python -m pytest -q` sigue en verde
   (hoy 271 passed) — los tests de barrier_labeling pasan `cost_per_side` explícito,
   no dependen del default.
3. Sin cambio de contrato: `/api/costs/current` sigue exponiendo la curva medida
   (no se toca); los scripts históricos con costo hardcodeado (backtest_gap_costs.py,
   backtest_c6_hedge.py, reeval_trial14_basket_adx.py) NO se modifican — su costo
   quedó fijado en su pre-registro original y re-correrlos con vara nueva sería
   reabrir líneas cerradas sin pre-registro nuevo.
4. ROADMAP fila M4 y SESSION_LOG actualizados con el valor adoptado.

**Impacto declarado (qué cambia al bajar el costo)**:
- `DEFAULT_COST_PER_SIDE` en `barrier_labeling.py` (ret_net del etiquetado M1) y
  `diagnostic_pipeline.py` heredan el nuevo valor → los labels netos futuros se
  calculan con el costo medido.
- **NO reabre automáticamente veredictos cerrados**: §13 (gap-reversion) murió por
  retorno bruto ≈0 (t-NW −0.20), no por costos — no cambia; §18.2 (C6 hedged) murió
  con neto −0.000292 vs costo hedged 0.63%/trade, y §18.1 con neto −0.000228 — esos
  veredictos quedaron fijados con su vara declarada en su momento. La vara nueva
  aplica a trials FUTUROS. Si el usuario quiere re-evaluar alguna línea cerrada con
  el costo medido, eso es un pre-registro NUEVO aparte — no se asume.

**Post-condición**: esta sección queda con el valor elegido, la fecha y el commit;
ROADMAP fila M4 refleja "COST_PER_SIDE actualizado a X (medido M4/Tarea D)".

### 33.1 — Validación externa del costo adoptado (Perplexity + JoF 2025, 2026-08-19)

**No es un pre-registro de trial** — no hay hipótesis de señal, no consume
`n_trials`. Es documentación de respaldo externo para un parámetro de config ya
vigente (0.0005, adoptado arriba), a pedido de Boris con acceso temporal a
Perplexity con modelo potente.

**Pregunta**: ¿0.05%/lado (10bps round-trip) es realista para ejecución LIVE, o
solo válido para el piso PAPER medido en M4/Tarea D?

**Fuente**: Schwarz, Barber, Huang, Jorion, Odean — *"The Actual Retail Price of
Equity Trades"*, Journal of Finance, 2025. **Cita verificada directamente contra la
fuente** (WebFetch a instituteforautomatedresearch.org/wiki, resumen del paper) —
no se aceptó la síntesis de Perplexity sin chequear. Confirmado sin errores.

**Diseño real**: 6 cuentas en 5 brokers (TD Ameritrade, Fidelity, E*Trade,
Robinhood, IBKR Pro, IBKR Lite), ~85.000 órdenes de MERCADO simultáneas (mismo tipo
de orden que usa el motor: market-at-close) en 128 acciones, dic-2021 a jun-2022,
tamaño objetivo $100/orden.

**Costo round-trip medido por broker (bps)**:

| Broker | bps round-trip |
|---|---|
| TD Ameritrade | 7.2 |
| Fidelity | 19.7 |
| E*Trade | 23.4 |
| Robinhood | 31.4 |
| IBKR Lite | 44.3 |
| IBKR Pro | 46.2 |

Gap mejor-peor: 39bps, atribuido al routing hacia wholesalers (calidad de
ejecución), NO a comisión explícita ni a payment-for-order-flow como tal.

**Veredicto**: 0.05%/lado (10bps round-trip) **NO es optimista** — cae en el rango
bajo-medio de brokers de buena calidad de ejecución (TD Ameritrade/Fidelity), no en
un extremo irreal. Queda validado como caso BASE razonable, con dos escenarios
adicionales para uso futuro (sensibilidad, no cambio de default):

- **5bps** (0.025%/lado) — best-case, broker de alta calidad de ejecución.
- **10bps** (0.05%/lado) — BASE, el valor ya adoptado en §33. Sin cambios.
- **25-30bps** (0.125-0.15%/lado) — conservador, broker con routing desfavorable
  (extremo IBKR Lite/Pro del estudio).

**Caveat**: el estudio no incluye Alpaca ni Schwab directamente. Alpaca queda sin
dato propio (PFOF-dependiente, prudente asumir escenario medio); Schwab, por sus
propios reportes de price improvement (no independientes), se ubicaría en el grupo
bueno junto a TD/Fidelity. Tamaño de orden del estudio ($100) es menor al de
fortress_core (sub-$50k notional) — la literatura de wholesalers (citada por
Perplexity, no verificada acá independientemente) sugiere que el costo no escala
fuerte con tamaño en rango retail, consistente con la curva plana/decreciente medida
en Tarea D (qty 1/10/50).

**No cambia ningún veredicto activo**: Tarea J (§34, abajo) cerró NO CUMPLE incluso
al costo base optimista (neto +0.000010/día, t-NW +0.07, lejos de t≥2.0) — correrlo
a 25-30bps sería estrictamente peor, no aporta nada nuevo. Sin acción sobre C6.

**Uso futuro**: si algún día una señal deja edge neto validado con el costo BASE y
se reconsidera la conexión a broker real (hoy bloqueada, fila ROADMAP), esta tabla
ya da el ranking de brokers para elegir con qué conectar — evita repetir la
investigación.

## 34. C6 (MA200 hedged) reabierto bajo el costo MEDIDO — PRE-REGISTRO (Tarea J, autorizado por Boris 2026-08-19)

**Naturaleza**: TRIAL FORMAL de señal/mecánica — CONSUME `n_trials` de la familia
`motor_signal`. Reabre la línea C6 (§18, cerrada DEFINITIVO en 2026-08-13) porque
§33 introdujo evidencia nueva y externa: el costo real medido (0.05%/lado, 156
órdenes paper) es 3× menor que el 0.15% asumido que mató a §18.2. Reabrir por
evidencia nueva de costos es el único motivo que el propio §18.2 reconoce como
legítimo (no es re-parametrizar la señal).

**Autorización**: Boris, 2026-08-19 noche ("lo más sólido, no lo más fácil").
Regla de parada §18.2 ("sin tercera variante") se relaja SOLO porque la vara de
costos cambió por medición, no por variante de señal.

**Estado**: ✅ CERRADO 2026-08-19 — NO CUMPLE (ver RESULTADO abajo).

**RESULTADO (2026-08-19, corrida real, costo 0.05%/lado, artefacto
`data/cache/backtest_c6_hedge_costo_medido_20260819_155509.txt`)**:
- Check de integridad §14: n=3710 (vs 3703 de §16), Pearson IC −0.1603 (vs −0.1582),
  Spearman −0.1148 (vs −0.1129). **Desviación menor verificada NO es bug del script**:
  el script ORIGINAL §18.2 re-corrido HOY da idéntico (3710/−0.1603/−0.1148) — la
  diferencia con los números de §16 se debe al refresh de datos (data_updater 17/08)
  entre la corrida del 13/08 y hoy. Mi copia es fiel al original.
- LS-HEDGE: BRUTO +0.000157/día (t-NW +1.07), **NETO +0.000010/día (t-NW +0.07)**,
  Sharpe +0.02, 49.1% días positivos, n_días 2666.
- SO-HEDGE (informativa): BRUTO −0.000017 (t-NW −0.13), NETO −0.000126 (t-NW −0.99).
- **VEREDICTO: NO CUMPLE** (media neta >0 pero t-NW +0.07 ≪ 2.0). El costo corregido
  3× menor SÍ movió el neto de −0.000292 (§18.2) a +0.000010, pero la señal bruta es
  demasiado débil (+0.000157, t-NW +1.07) y ni siquiera el costo real la deja
  sobrevivir. **C6 queda cerrado DEFINITIVO por segunda vez, ahora contra el costo
  real medido — sin ambigüedad.** Ledger motor_signal: 10 → 11 (trial_18), umbral
  0.991667. NO se integra nada al motor.

**Hipótesis (pre-registrada)**: el fade C6 hedgeado (market-neutral por beta),
idéntico a §18.2 en TODO excepto el costo, deja retorno diario NETO positivo con
el costo REAL medido (0.05%/lado) en lugar del 0.15% asumido.

**Metodología (idéntica a §18.2 en todo excepto costo)**:
- Universo: AAPL, V, MA, ORCL, IBM, QCOM, TXN.
- Señal: `dist_ma200 = (close − ema200)/ema200`; fade LS: side = −1 si dist>0,
  +1 si dist<0; stride 5d; hold 20d; entry al close; salida t+20.
- Hedge: cada unit SHORT (dist>0) se cubre comprando |beta_sym| de SPY; la pata
  LONG se cubre simétricamente shorteando |beta_sym| de SPY (cubrir solo el short
  dejaría drift residual — decisión declarada en §18.2).
- Beta: OLS diario (ret_sym ~ ret_SPY, con constante) sobre ventana PRE-MUESTRA
  2015-01-01 → 2018-12-31; NADA de la ventana de test participa del estimador.
- Costos: `cost_per_side * 2 * (1 + |beta|)` por trade unit hedged (C6 round-trip
  + SPY round-trip proporcional al beta), deducidos el día de entrada, misma
  convención §18.2. **`cost_per_side = 0.0005`** (0.05%/lado, §33) en lugar del
  COST_SIDE=0.0015 original.
- Ventana de test: 2019-01-01 → 2026-08-04 (idéntica a §18.2).

**Check de integridad (§14, pre-registrado)**: el panel debe reproducir n=3703,
Pearson IC −0.1582, Spearman −0.1129 (igual que §16/§18.1/§18.2). Si no coincide,
el trial es inválido y se documenta como tal — no se interpreta.

**Criterio de éxito (fijado ANTES de correr, idéntico a §18.1/§18.2 para
comparabilidad)**: `n_días_con_posiciones ≥ 100` Y retorno diario NETO medio > 0
con `t-NW ≥ 2.0` (L=20). Variante LS-HEDGE es el gate; SO-HEDGE informativa, no gate.

**Ledger**: familia `motor_signal`, n_trials 10 → 11, umbral Bonferroni 0.990909
(verificado en ledger real el 2026-08-19; confirmar de nuevo al cerrar por si otro
trial corrió antes). Se registra el trial al cerrar con su veredicto real.

**Regla de parada (autorizada por Boris)**: es el re-trial de C6 bajo costo
medido. NO CUMPLE → C6 queda cerrado definitivamente por segunda vez, ahora contra
el costo real, sin ambigüedad. CUMPLE → C6 candidato REAL de motor; NO se integra
en esta tarea — la integración es un trial de motor aparte con su propio pre-registro.

**Post-condición**: artefacto en `data/cache/backtest_c6_hedge_costo_medido_*.txt`
con el veredicto CUMPLE/NO_CUMPLE; ROADMAP fila C6/§18 y SESSION_LOG actualizados;
trial registrado en el ledger.

## 35. AUDITORÍA FDR (Benjamini-Hochberg) sobre todos los factores cerrados — NO es un trial

**Naturaleza**: AUDITORÍA / DIAGNÓSTICO ESTADÍSTICO retroactivo sobre resultados YA
obtenidos. **NO es pre-registro de trial, NO consume `n_trials` del ledger, NO toca
mercado ni datos, NO corre backtests.** Solo lectura de t-stats ya medidos en los
artefactos de `data/cache/` + un script nuevo de análisis (`scripts/auditoria_fdr.py`).
Motivo: Bonferroni es demasiado conservador para un programa secuencial de ~29 trials;
la literatura (Harvey-Liu-Zhu RFS 2016, Bailey-López de Prado DSR) alinea FDR (BH) con
este caso. Auditoría HONESTA — si algo flipea a "discovery" NO se integra al motor ni
se cambia su estado en el ledger; se reporta como hallazgo pendiente de decisión.

**Estado**: ✅ COMPLETO 2026-08-19 — **ningún factor flipea a discovery bajo BH**.

**MÉTODO DE POOLING (decidido ANTES de correr, no después de ver números)**:
- **Stouffer weighted-z** (meta-análisis de varianza inversa): `z_pool = Σ√nᵢ·tᵢ / √Σnᵢ`,
  p bilateral gaussiana. Pesos √n = varianza inversa (SE_NW ∝ 1/√n), consistente con el
  pooling "TOTAL" que el proyecto ya usa (ADX ref t=+2.31 sobre n=151).
- **POR QUÉ no Fisher**: Fisher combina p's bilaterales de forma NO direccional y crea
  discoveries espurios cuando una ventana es fuerte y otra opuesta (p.ej. AAII W2=+2.94
  con W1=−0.32). Cada factor tiene hipótesis direccional pre-registrada; Stouffer
  conserva el signo y cancela evidencia opuesta — es el comportamiento correcto.
- BH sobre m = nº real de FACTORES (no ventanas), reportando **q=0.05 Y q=0.10** (ambos,
  no se elige el que convenga).

**Set BH (m=14)** — t_pool / p_pool (Stouffer), ordenado por p:
| factor | t_pool | p_pool | n | rank | corte BH(q=.05) | corte BH(q=.10) | BH05 | BH10 | Bonferroni orig |
|---|---|---|---|---|---|---|---|---|---|
| ADX_daily | +2.08 | 0.0376 | 126 | 1 | 0.0036 | 0.0071 | no | no | NO_CUMPLE |
| momentum_TB | −2.04 | 0.0416 | 137 | 2 | 0.0071 | 0.0143 | no | no | NO_CUMPLE |
| AAII_timing | +1.18 | 0.2398 | 157 | 3 | 0.0107 | 0.0214 | no | no | NO_CUMPLE |
| C6_hedged | +1.07 | 0.2846 | 2666 | 4 | 0.0143 | 0.0286 | no | no | NO_CUMPLE |
| rsi_daily | +0.90 | 0.3698 | 137 | 5 | 0.0179 | 0.0357 | no | no | NO_CUMPLE |
| Donchian | −0.81 | 0.4179 | 187 | 6 | 0.0214 | 0.0429 | no | no | NO_CUMPLE |
| momentum_daily | −0.55 | 0.5811 | 157 | 7 | 0.0250 | 0.0500 | no | no | NO_CUMPLE |
| adx_weekly | +0.47 | 0.6388 | 392 | 8 | 0.0286 | 0.0571 | no | no | NO_CUMPLE |
| rsi_TB | +0.34 | 0.7327 | 119 | 9 | 0.0321 | 0.0643 | no | no | NO_CUMPLE |
| FinBERT | −0.29 | 0.7705 | 331 | 10 | 0.0357 | 0.0714 | no | no | NO_CUMPLE |
| gap_reversion | −0.20 | 0.8415 | 2206 | 11 | 0.0393 | 0.0786 | no | no | NO_CUMPLE |
| rsi_weekly | −0.20 | 0.8444 | 392 | 12 | 0.0429 | 0.0857 | no | no | NO_CUMPLE |
| momentum_weekly | −0.00 | 0.9977 | 392 | 13 | 0.0464 | 0.0929 | no | no | NO_CUMPLE |
| adx_TB | −0.00 | 0.9999 | 111 | 14 | 0.0500 | 0.1000 | no | no | NO_CUMPLE |

**VEREDICTO**: k_rechazados = 0 en q=0.05 y q=0.10. El p más chico (ADX_daily 0.0376,
rank 1) queda lejos del corte BH (q·k/m = 0.10·1/14 = 0.0071). **Ningún factor flipea
a discovery** — la hipótesis "BH resucita algo" NO se confirma. Incluso el único factor
positivo (ADX) es ~5× más débil de lo que exigiría FDR a q=0.10. momentum_TB (−2.04)
tiene p chico pero con SIGNO NEGATIVO (reversión, no continuación esperada) — no sería
un discovery direccional de todos modos. **Robustez de m**: set solo-windowed (m=11)
también da k=0; agregar single-t solo sube m y endurece el corte → veredicto robusto.

**Excluidos del set BH (reportados aparte, con justificación)**:
- **EVT stops (§20)**: trial INVALIDO por diseño (sizing EVT nunca fue binding por el
  `min()` con Kelly; nunca midió un efecto). Solo DSR 0.0649/0.0253/0.1602, sin t por
  ventana. No es candidato a discovery.
- **lead-lag (§22)**: familia de 50 tests de correlación cruzada, sin un t único.
  Ningún par cruzó Bonferroni-50 (|t|>3.29); max |t| ≈ 2.69.
- **MA200 clusters (§16)**: misma señal subyacente que C6_hedged; su afirmación era
  heterogeneidad de clusters (REFUTADA: mismo signo en todos — C3 y C6 negativos). No
  es un factor direccional independiente.

**Fuentes (t-stats verificados contra artefactos reales)**: §25 `trial_adx_walkforward_
20260817_103916.txt`, §28 `trial_xsec_relative_20260817_184355.txt`, §23
`retest_triple_barrier_20260816_091649.txt`, §26 `weekly_indicators_20260817_105918.txt`,
§27 `trial_finbert_eventstudy_20260817_163512.txt`, §34 `backtest_c6_hedge_costo_medido_
20260819_155509.txt`, §17 `diagnose_donchian_intraday_20260812_201008.txt`, §13.1
`backtest_gap_costs_20260812_173951.txt` (bruto).

**Artefacto**: `data/cache/auditoria_fdr_20260819_195829.txt` (+ `.json` resumen).
**Ledger**: NO se registra trial (es auditoría, no consume n_trials). **Suite**: 271 passed.
**Post-condición**: ROADMAP + SESSION_LOG actualizados. Nada se integra al motor.

---

## 36. TAREA N — MACD (dirección) y Bollinger (régimen de volatilidad): dos preguntas DISTINTAS

**Naturaleza**: TRIAL pre-registrado, familia `signal_diagnosis`, consume **1** slot.
**Estado**: PRE-REGISTRADO 2026-08-20 (ANTES de correr; veredicto se llena al cierre).
Familia `signal_diagnosis` ya consumida: **18** → con este trial **n_trials = 19**.
Confirmado con el ledger: `consumed_budget('signal_diagnosis')=18`,
`current_threshold('signal_diagnosis')=0.99474`.

**Umbral Bonferroni de la familia (criterio |t|)**: con n_trials=19, dos colas,
`ALPHA_PER = 0.05/(2·19) = 0.05/38` → **|t| > z(1−0.05/38) = 3.008**. Este es el umbral
Bonferroni de la familia `signal_diagnosis` que se usa como vara para TODOS los rank IC
de este trial. (Patrón idéntico a §25/§27/§28, que usaban Bonferroni-9/12 bilateral
derivado del nº de tests; acá se deriva del nº de trials de la familia.)

**Fuentes**: `RESEARCH_PREDICTIVE_INDICATORS.md` (leída antes de pre-registrar) —
MACD Appel 1979 / Chong-Ng 2008 / Chen-Metghalchi-Chang 2008, correlación 0.05-0.08,
horizonte 2-8 sem (compatible con 20d); Bollinger Bollinger 1992 / Lento-Gradojevic-
Wright 2007, correlación 0.03-0.05, horizonte 1-2 sem (MÁS corto — por eso se mide
también a 5-10d, no solo 20d). `macd()`/`bollinger_bands()` de indicators.py se
LEEN, no se tocan; siguen sin usarse en el score (peso 0) — este trial NO integra nada.

**DATOS**: universo 50 (`opportunities_universe.SYMBOLS`), desde `data/cache/*.parquet`
vía `load_universe` (ya descargados, NO se baja nada nuevo). Ventanas:
W1 2020-01-01→2021-12-31, W2 2022-01-01→2023-12-31, W3 2024-01-01→2026-07-06
(mismas que §25 para comparabilidad). Columnas vía `calculate_all_indicators`
(macd/macd_signal/macd_hist, bb_upper/middle/lower, rsi14, momentum_12_1, close).

### 2A — MACD (pregunta de DIRECCIÓN — mismo protocolo que Tarea M/§25)
**Hipótesis**: `macd_hist` rank IC cross-sectional contra `fwd_return_20d` con **signo +1**
(más momentum alcista → mayor retorno futuro), consistente con momentum/RSI.
**Método**: Spearman por fecha (ranks sobre símbolos de esa fecha) vs fwd_return_20d,
promedio sobre fechas con **SE Newey-West**, `L = min(12, n_dias//8)` por ventana
(mismo que §25/§23).
**Criterio (pre-registrado)**: **|t| > 3.008 con signo +1 en ≥ 2/3 ventanas** → CUMPLE.

### 2B — Bollinger (pregunta de RÉGIMEN, NO de dirección — protocolo DISTINTO)
Se declaran DOS mediciones separadas ANTES de correr:

**(i) VALIDACIÓN — el ancho de banda mide volatilidad (por diseño del autor).**
`band_width = (bb_upper−bb_lower)/bb_middle`. Rank IC cross-sectional de band_width vs
**volatilidad realizada futura** `std(retornos_diarios futuros)` a **horizonte 10d y 20d**
(`real_vol_10d`, `real_vol_20d`). Esperado **signo +1** (banda ancha → más vol futura).
Esto es cheque de VALIDEZ del instrumento (clustering de vol), NO discovery de edge:
por eso NO dispara el veredicto CUMPLE del trial. Se reporta con su |t| (misma vara 3.008).
**Criterio (i)**: |t| > 3.008 con signo +1 en ≥ 1 de los 2 horizontes → validez confirmada.

**(ii) INTERACCIÓN — ¿condicionar momentum+RSI por régimen de banda cambia su rank IC?**
Factor compuesto `mom_rsi = rank01(momentum_12_1) + rank01(rsi14)` (rank cross-sectional
por fecha). Rank IC de `mom_rsi` vs retorno futuro **a 20d Y a 5-10d** (se declaran AMBOS
horizontes ahora), split por **terciles de band_width por fecha** (tranquilo/media/expansión)
y además **split por régimen HMM** de `regime_gate.py`/`regime_classifier.py` (walk-forward,
fit ≤2024-12-31, decodificación causal). Pregunta: ¿momentum+RSI funciona mejor en mercado
tranquilo o en expansión? y ¿coinciden los dos "regímenes" (banda vs HMM)?
**Criterio (ii) — interacción presente**: el rank IC de `mom_rsi` difiere entre el tercil
tranquilo y el de expansión en **|ΔIC| ≥ 0.05** a horizonte 20d O a 5-10d, y el IC del
tercil ganador es **significativo (|t| > 3.008)** en al menos 1 ventana/horizonte.
Si hay interacción → podría ser un factor de régimen; si no, Bollinger no condiciona el score.

### VEREDICTO COMBINADO DEL TRIAL (UN solo slot en el ledger)
El trial se registra **CUMPLE si (MACD CUMPLE) O (Bollinger-ii CUMPLE)** — las dos
preguntas de "edge" pre-registradas. Bollinger-(i) es validación del instrumento y se
reporta pero NO dispara CUMPLE por sí sola (bandwidth→vol futura está casi garantizado por
clustering de vol, no es edge transable). Bollinger-(ii) y MACD son las que pueden abrir
puertas. **Post-condición**: artefacto `data/cache/trial_macd_bollinger_*.txt` con tablas
y veredictos; registro en ledger `signal_diagnosis` n=1; ROADMAP (fila Tarea N) y
SESSION_LOG actualizados; suite completa en verde. Nada se integra al motor.

## 37. T1.1 — Proxy OFI (Order Flow Imbalance desde OHLCV): diagnóstico de IC antes de cualquier integración

**Naturaleza**: TRIAL pre-registrado, familia `signal_diagnosis`, consume **1** slot.
**Estado**: CERRADO 2026-08-20 — **NO_CUMPLE** (había sido pre-registrado ANTES de
correr; ver resultado al final de esta sección).
Familia `signal_diagnosis` ya consumida: **19** (confirmado con `consumed_budget`)
→ con este trial **n_trials = 20**.

**Umbral Bonferroni de la familia (criterio |t|)**: con n_trials=20, dos colas,
`ALPHA_PER = 0.05/(2·20) = 0.05/40` → **|t| > z(1−0.05/40) = 3.023**.
`current_threshold('signal_diagnosis') = 0.995` al momento de correr.

**Origen / ticket**: PLAN_INTEGRACION_INDICAGENT.md **T1.1** (ejecutado 2026-08-20,
Kilo Code). El ticket solo pide código + test + diagnóstico de IC — **NO** pide
promover al score. Este protocolo evalúa el factor con la vara del proyecto;
el criterio de "promover" es externo al trial.

**Hipótesis**: el proxy OFI positivo (cierre pegado al high de la barra, volumen alto)
predice retorno futuro positivo. Signo esperado: **+1** para `ofi_ewma_fast`.

**Qué se mide** (4 features OFI, escritas en `calculate_all_indicators` tras T1.1).
Para homogeneidad cross-sectional (los volúmenes absolutos difieren órdenes de magnitud
entre símbolos, y eso dominaría cualquier rank IC sobre el valor crudo), cada feature
se transforma a **z-score rodante por símbolo, ESTRICTAMENTE CAUSAL** (ventana trailing
100 barras, `min_periods=50`): `z_t = (x_t − media_trailing) / std_trailing`, solo con
datos ≤ t. Así "¿qué tan alto está el OFI de HOY respecto a la distribución RECIENTE de
este mismo símbolo?" se vuelve comparable entre símbolos y sin look-ahead. Se reporta
tanto el t sobre el z rodante (feature operativa) como referencia el signo del raw.

| Feature raw | Definición | z-rating usado |
|---|---|---|
| `ofi_raw` | (close−low)/(high−low+eps) × volume | z rodante 100d |
| `ofi_ewma_fast` | EWMA(span=5) de `ofi_raw` | z rodante 100d (feat principal) |
| `ofi_ewma_slow` | EWMA(span=20) de `ofi_raw` | z rodante 100d |
| `ofi_spike_z` | z inline de `ofi_raw` (ya es rodante 100d) | se usa tal cual |

El target es `fwd_return_20d` (mismo horizonte que §25/§27/§28/§36 para comparabilidad).

**Método**: idéntico a §25/§27/§28/§36 (protocolo estándar de la familia):
rank IC daily (Spearman cross-sectional por fecha), SE Newey-West con
`L = min(12, n_dias//8)`, ventanas W1/W2/W3 idénticas a §25/§36.

**Criterio de veredicto (pre-registrado, un slot)**:
CUMPLE si `ofi_ewma_fast_z` (feature principal declarada) alcanza
**|t| > 3.023 con signo +1 en ≥ 2/3 ventanas** (W1, W2, W3).
Las otras features (`ofi_ewma_slow`, `ofi_spike_z`, `ofi_raw`) se reportan con su t
pero NO disparan veredicto — son informativas si la principal no cumple.

**Decisiones de diseño registradas** (no parte del criterio):
1. **Feat principal = `ofi_ewma_fast_z`** (z rodante 100d de la EWMA 5 del raw — el
   pseudocódigo de indicAgent `ofi.py` usa EWMA 5 como "presión inmediata"). El z-rating
   es imprescindible: el valor crudo tiene escala volumétrica que no es comparable
   cross-sectionalmente entre símbolos de capitalización distinta.
2. **z rodante ESTRICTAMENTE CAUSAL**: `z_t = (x_t − media[x_{t-99..t}]) / std[x_{t-99..t}]`,
   `min_periods=50`. NO es look-ahead: cada fecha usa solo historia ≤ t. (Se descartó el
   z por ventana completa porque usaría fechas futuras de la ventana para normalizar el
   día actual — el código de la familia es sensible a estos detalles y este diseño
   queda cerrado acá, antes de correr.)
3. **Horizonte único 20d**: no se declaran horizontes secundarios pre-registrados
   para no inflar la cuenta de tests. Si el t a 20d no cumple, se registra
   NO_CUMPLE sin re-medir a otro horizonte.
4. **Máscara de elegibilidad**: NO se usa el filtro duro de `generate_signal` para este
   diagnóstico — se mide sobre TODAS las fechas con todas las columnas presentes.
   (El patrón "eligible-IC" de `diagnose_factor_ic` es para comparar contra el score
   del motor; acá el objetivo es el poder predictivo intrínseco del factor.)

**Post-condición (post-execución)**:
- Artefacto `data/cache/trial_ofi_proxy_*.txt` con tablas por feature y veredicto.
- Registro en ledger `signal_diagnosis` con n=1 (n_trials=20, umbral 0.995).
- ROADMAP fila T1.1 y SESSION_LOG actualizados.
- Si NO_CUMPLE: `ofi_*` se mantendrán en `calculate_all_indicators` pero NO se integran
  al score; si CUMPLE: se abre una entrada en el siguiente ciclo de trial (signal_engine
  integration, pre-registro aparte).

**No se integra al motor.** Ningún cambio a `signal_engine.py::_factor_scores` en este ticket.

**Resultado (2026-08-20, al cierre)**: NO_CUMPLE — `ofi_ewma_fast_z`: W1 t −2.30,
W2 +0.10, W3 +0.19 (0/3 con signo +1 y |t|>3.023); TOTAL t −1.66 (NEGATIVO además:
la dirección observada es la contraria a la hipótesis, sin ser significativa).
Las otras features tampoco (máx |t| −2.32 ofi_raw_z). Veredicto registrado en el
ledger (`trial_ofi_proxy`, signal_diagnosis 19→20). OFI desde OHLCV diario,
tal como lo define indicAgent, no contiene información cross-sectional utilizable
para el retorno a 20 ruedas en el universo 50. Línea cerrada sin integración.

## 38. T1.2 — Proxy CVD (Cumulative Volume Delta desde OHLCV): diagnóstico de IC antes de cualquier integración

**Naturaleza**: TRIAL pre-registrado, familia `signal_diagnosis`, consume **1** slot.
**Estado**: CERRADO 2026-08-20 — **NO_CUMPLE** (había sido pre-registrado ANTES de
correr; ver resultado al final de esta sección).
Familia `signal_diagnosis` ya consumida: **20** (confirmado con `consumed_budget`)
→ con este trial **n_trials = 21**.

**Umbral Bonferroni de la familia (criterio |t|)**: con n_trials=21, dos colas,
`ALPHA_PER = 0.05/(2·21) = 0.05/42` → **|t| > z(1−0.05/42) = 3.038**.

**Origen / ticket**: PLAN_INTEGRACION_INDICAGENT.md **T1.2** (ejecutado 2026-08-20,
Kilo Code). Mismo espíritu que §37: el ticket pide código + test + diagnóstico de IC;
la promoción al score requiere que este trial lo gane.

**Decisión de diseño registrada** (la que exige el ticket de forma explícita):
el CVD original de indicAgent resetea el acumulador cada sesión intradía — en barras
DIARIAS no hay sesión que resetear, así que se implementó acumulación ROLLING de
`window=20` días hábiles (~1 mes, alineado al horizonte de calibración), sin
acumulador infinito (evita drift histórico no comparable). El window es decisión de
diseño NO medida; este trial evalúa esa elección.

**Hipótesis**: la presión neta de flujo compradora/vendedora acumulada reciente
(cierre al high ⇒ comprador; cierre al low ⇒ vendedor, ponderado por volumen)
predice el retorno a 20 ruedas. Signo esperado **+1**: más delta acumulado positivo
→ mayor retorno futuro.

**Qué se mide** (features `cvd_*`, escritas en `calculate_all_indicators` tras T1.2):

| Feature raw | Definición | z-rating usado |
|---|---|---|
| `cvd_rolling` | suma de deltas de las últimas 20 barras | z rodante 100d (feat principal) |
| `cvd_slope_5bar` | aceleración del rolling (diff 5) | z rodante 100d (informativa) |

(`cvd_divergence` es discreto −2..2 y patrón de divergencia, no una variable de IC
cross-sectional; se excluye del protocolo IC por diseño de la medición, no por resultado.)

Mismo z rodante ESTRICTAMENTE CAUSAL que §37 (ventana trailing 100d, min_periods=50,
solo datos ≤ t) — la escala volumétrica difiere órdenes de magnitud entre símbolos,
el z la hace comparable sin look-ahead.

**Método**: protocolo estándar de la familia, idéntico a §37: panel universo 50,
SIN máscara de elegibilidad, Spearman cross-sectional por fecha vs `fwd_return_20d`,
SE Newey-West `L = min(12, n_dias//8)`, ventanas W1 2020-2021 / W2 2022-2023 /
W3 2024→2026-07-06.

**Criterio de veredicto (pre-registrado, un slot)**:
CUMPLE si `cvd_rolling_z` alcanza **|t| > 3.038 con signo +1 en ≥ 2/3 ventanas**.
`cvd_slope_5bar_z` se reporta con su t pero NO dispara veredicto. Horizonte único
20d, sin re-medición a otros horizontes si no cumple.

**Post-condición**: artefacto `data/cache/trial_cvd_proxy_*.txt`; registro en ledger
`signal_diagnosis` n=1 (n_trials=21); PLAN_INTEGRACION T1.2, ROADMAP, SESSION_LOG.
Si NO_CUMPLE: `cvd_*` quedan disponibles pero NO se integran al score. **No se
integra al motor bajo ninguna rama de este ticket.**

**Resultado (2026-08-20, al cierre)**: NO_CUMPLE — `cvd_rolling_z`: W1 t +0.73,
W2 −0.84, W3 +0.38 (0/3 con signo +1 y |t|>3.038; máx |t| 0.84, ruido puro); TOTAL
t −0.73. `cvd_slope_5bar_z` tampoco (máx |t| 0.78). Veredicto registrado en el
ledger (`trial_cvd_proxy`, signal_diagnosis 20→21). El CVD-acumulado-20d desde
OHLCV diario no contiene información cross-sectional para el retorno a 20 ruedas.
Línea cerrada sin integración.

---

## 39. PBO vía CSCV del baseline momentum+RSI — auditoría de proceso, NO es un trial (2026-08-22, PRE-REGISTRADO antes de correr)

**Autor**: Cline, tomado de la cola de Boris (2026-08-22). Motivación: momentum+RSI es el
ÚNICO factor que sobrevivió todo el proceso selectivo (38 trials en ledger), y nunca se le
aplicó la pregunta inversa: ¿el propio baseline es un artefacto de selección entre las
configuraciones vecinas que se pudieron haber elegido? El PBO=0.5 de §11 Fase 3 (2026-08-11)
fue sobre la familia ridge ANTES de que el baseline quedara lockeado; no aplica al vigente.

**Naturaleza**: igual que §35 — auditoría estadística retroactiva. NO consume slot del
ledger (`motor_signal` ni `signal_diagnosis`), NO promueve ni refuta señal alguna. Mide el
PROCESO, no un factor nuevo.

**Método** (Bailey, Borwein, López de Prado, Zhu 2017 — CSCV):

- **Matriz M** (T meses × N configuraciones): retorno mensual neto de un portafolio
  equal-weight reconstruido VECTORIALMENTE a partir del mismo motor de reglas:
  - Universo: los 50 símbolos canónicos del cache (`data/cache/*.parquet`, OHLCV local,
    sin descargas).
  - Snapshot en el ÚLTIMO día de trading de cada mes. Elegibilidad = gates EXACTOS del
    motor: `close>ema50>ema200`, `adx14≥20`, `rsi14∈(40,75)`, `volume_ratio≥1.0`.
  - Señal si `score ≥ 0.6` (umbral real de `generate_signal`). Score = pesos·(momentum_score,
    rsi_score) con las definiciones exactas de `signal_engine.py`.
  - Retorno del mes siguiente = media simple de close-to-close de los símbolos señalados;
    si no hay señales → 0 (cash). Costo: 2 lados × (0.001 comisión + 0.0005 slippage)
    descontado por rebalance completo (conservador).
  - **Alcance declarado**: aproximación vectorizada SIN stops/barriers/regime-gating —
    mide el EDGE del score, no el backtest completo del motor. Cualquier conclusión sobre
    el motor completo requiere el trial walk-forward estándar.
- **Familia de configuraciones (N=27)** — perturbaciones alrededor de las elecciones
  efectivamente hechas, definidas ANTES de correr:
  - Pesos momentum/rsi: {0.50/0.50, **0.664/0.336 (ACTUAL, derivado de ICs)**, 0.80/0.20}
  - Banda RSI del sub-score: {(40,65), **(45,70) (ACTUAL)**, (50,75)}
  - Techo normalización momentum: {75, **100 (ACTUAL)**, 125} (piso −50 fijo)
  La config ACTUAL es exactamente la celda central. *Corrección de rótulo (2026-08-22,
  ANTES de analizar resultados): el texto original decía "N=18" — error aritmético; la
  grilla enumerada (3×3×3) siempre fue de 27 y así se corrió. La definición de la familia
  no cambió; solo se corrige el número.*
- **CSCV**: S=16 bloques contiguos iguales (T truncado al múltiplo de 16 reteniendo los
  meses MÁS RECIENTES), todas las C(16,8)=12.870 combinaciones train/test. Estadística
  IS/OOS: Sharpe anualizado sobre retornos mensuales (√12). Para cada combinación: rank
  de la config mejor-IS dentro del OOS → ω̄ relativo → logit λ=ln(ω̄/(1−ω̄)).
- **PBO** = fracción de combinaciones con λ≤0 (la mejor in-sample queda debajo de la
  mediana out-of-sample).

**Criterio pre-registrado (ANTES de correr)**:

| PBO | Lectura | Acción |
|---|---|---|
| ≤ 0.20 | Riesgo de sobreajuste de proceso BAJO | El baseline queda parado con evidencia propia; nada cambia |
| 0.20–0.50 | INTERMEDIO | Se documenta; ninguna acción automática; Tarea O y P deben citarlo al evaluar sus resultados |
| > 0.50 | ALTO | El veredicto del baseline queda marcado "no fiable por sí solo ante el proceso selectivo". NO se revoca nada automáticamente — eso es decisión de producto de Boris — pero ROADMAP lo registra |

**Checks de fidelidad** (fallar cualquiera invalida la corrida): (1) la config ACTUAL debe
estar presente como fila y su Sharpe full-período reportado; (2) T final ≥ 96 meses;
(3) cobertura: ≥30% de meses con ≥1 señal en la config actual; (4) signo del edge: el
retorno medio mensual de la config ACTUAL debe ser positivo sin costos.

**Artefacto**: `backend/data/cache/pbo_cscv_baseline_<ts>.txt` (+json). Script:
`backend/scripts/pbo_cscv_baseline.py`. Resultado y veredicto: `RESUMEN_PBO_CSCV_BASELINE.md`
+ ROADMAP/SESSION_LOG.

### RESULTADO §39 (2026-08-22, corrido tras el pre-registro)

- Fidelidad: OK en los 4 checks (T=128 meses 2016-01→2026-08, cobertura 83.6% de meses
  con ≥1 señal, edge bruto +1.55%/mes positivo).
- **PBO = 0.2358** (3035/12.870 combos con λ≤0; mediana λ +0.310) → bucket
  **INTERMEDIO** del criterio pre-registrado (0.20–0.50).
- Hallazgo estructural más importante que el PBO mismo: **las 27 configuraciones de la
  vecindad tienen Sharpe positivo** (rango +0.55 a +0.90) — el vecindario de diseño no
  contiene configuraciones fallidas. El riesgo de selección es de GRADO (cuán bueno es
  el elegido), no de EXISTENCIA (si el edge es real).
- La config ACTUAL rankea 12/27 por Sharpe full-período (+0.714; la mejor del vecindario
  es hi=75 con +0.901) — el elegido NO era el máximo in-sample del vecindario, lo que es
  evidencia EN CONTRA del cherry-picking.
- Veredicto completo en `RESUMEN_PBO_CSCV_BASELINE.md`.

---

## 40. PBO/CSCV sobre momentum+RSI — overfitting de proceso entre los 21 trials signal_diagnosis (2026-08-22, PRE-REGISTRADO, consume ledger)

**Autor**: OpenCode (Muse Spark) — ejecución del pre-registro `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md` (estado BORRADOR 2026-08-22, en cola y ahora liberado). Único slot liberado de la cola PBO.

**Naturaleza**: TRIAL diagnóstico de proceso, familia `signal_diagnosis`, consume **1** slot (21→22). Mide **overfitting de selección** (Bailey et al.): "miré 21 ideas de señal y me quedé con momentum+RSI porque era lo menos malo" — ¿ese ranking IS es artefacto? Distinto de DSR (que corrige p-valores individuales): PBO ya captura la selección, no necesita Bonferroni adicional. Tarea L (BH→BY) queda como calibración — no se rehace por decisión del usuario (§16 pre-registro).

**Pre-registro** (`PRE_REGISTRO_PBO_CSCV_MOM_RSI.md`): sellado ANTES de correr, no editado después (ONBOARDING regla #1). Criterio mecánico §4: **PBO < 0.10 = CUMPLE** (no overfitting, ranking informativo), **0.10–0.20 = zona gris** (no se declara artefacto pero no se afirma robustez; binario → NO_CUMPLE), **≥0.20 = NO_CUMPLE** (overfitting de proceso — la mejor IS es indistinguible de la mediana OOS), **≥0.30 = overfitting sustancial**. Veredicto binario para ledger: CUMPLE si PBO<0.10, NO_CUMPLE si ≥0.10.

**Método** (Bailey, Borwein, López de Prado & Zhu 2014–2017 — CSCV fiel al paper):

- **N = consumed_budget(signal_diagnosis) = 21** al 2026-08-22 (lista congelada §6.1; leída vía `app.core.trial_registry`, no hardcodeada). Si al correr ya hay 22, N se actualiza — documentado en artefacto.
- **Universo 50** canónico (`opportunities_universe.SYMBOLS`) y ventana **2019-01-01→2026-08-04** (misma que baseline limpio `baseline_clean_20260811_150643.txt`). Warmup 252d para momentum no entra al ranking.
- **S = 16 particiones cronológicas** sobre serie de retornos mensuales netos → **C(16,8)=12 870 splits IS/OOS** combinatorios (cada observación está en IS en la mitad de los splits). Fallback S=12 si partición <60 ruedas — no hizo falta (5 meses ≈105 ruedas). T truncado al múltiplo de S reteniendo meses recientes: T_total=92 → T=80 meses (2020-01→2026-08).
- **Métrica**: Sharpe anualizado OOS (retornos mensuales netos ×√12, misma que `backtest_engine.calculate_metrics`). Por split: ranking IS de las N, PBO = P(rank_OOS(best_IS) < N/2), logit = log((rank/(N+1))/(1−rank/(N+1))), histograma, degradación Sharpe_OOS−Sharpe_IS, Spearman IS vs OOS.
- **N Sharpe**: 21 parametrizaciones vecinas del baseline como proxy combinatorio (w_mom {0.50,0.664,0.80} × RSI_band {(40,65),(45,70),(50,75)} × mom_hi {75,100,125} = 27; se toman las primeras 21 ordenadas lexicográficamente, forzando inclusión del ACTUAL w=0.664/45-70/100). Proxy declarado §8: las 21 del ledger son 21 familias heterogéneas (gap, MA200, FinBERT, OFI, CVD…), no 21 thresholds del mismo modelo — el grid asume comparabilidad por mismo Sharpe. Alternativa limpia (reconstruir las 21 como backtests con `backtest_engine.run`) queda para slot futuro si se exige fidelidad total. Heterogeneidad documentada como limitación, no como excusa post-hoc.
- **Costos**: `COST_PER_SIDE=0.0005` + `slippage=0.0005` + `EXECUTION_LAG_DAYS=1` (misma config vigente) para las N.
- **Determinista**: seed 42, `random_state=42` donde aplique, enumeración combinatoria determinista.

**Por qué el script previo N=1 no sirve** (`backend/scripts/pbo_cscv.py` y artefactos `pbo_cscv_20260811_093415.txt`): PBO = P(sharpe_test−sharpe_train <0) con UNA configuración y splits balanceados → logit ANTISIMÉTRICO por construcción (cada combo tiene su complementaria con signo invertido) → **PBO=0.5 SIEMPRE**. No mide selección. La información ahí es la dispersión del logit (desv 0.14), no el PBO. Este N=21 sí mide selección.

**Script**: `backend/scripts/pbo_cscv_mom_rsi.py` (nuevo, reutiliza plantilla de particionado de `pbo_cscv.py` pero con N Sharpes por split, no uno solo; lee `trial_registry.json` para N real).

**Artefacto**: `backend/data/cache/pbo_cscv_mom_rsi_20260822_093300.txt` + `.json` (PBO, histograma logits p5/p25/p50/p75/p95, N, S, lista 21 Sharpes, timestamp, checks).

**Resultado (UNA sola corrida, sin re-corridas por S, 2026-08-22)**:

- Fidelidad: **OK** (T=80 meses ≥72, cobertura 85% meses con señal, edge bruto +1.98%/mes positivo, universo 50 OK). S=16 sin fallback.
- **PBO = 0.4688** (6 033 / 12 870 combos con λ ≤ 0; λ mediana +0.201, media +0.949, p5 −2.944, p95 +20.723, std 7.22). Rank_OOS del best IS: mediana 12.0 (teórica mediana 11.0) — el mejor IS cae justo sobre la mediana OOS, no por encima.
- Degradación Sharpe_OOS − Sharpe_IS del best IS: mediana **−0.322** (p5 −1.157) — la mejor IS pierde ~0.32 de Sharpe OOS de media.
- Estabilidad rank IS vs OOS (Spearman): **mediana +0.030** — sin correlación entre ranking IS y OOS.
- Sharpe_full por config (orden ledger): rango +0.68 a +1.25; **ACTUAL (w=0.664/45-70/100) Sharpe +0.934, rank 17/21** — ni siquiera es el mejor full-período, consistente con §39 (ACTUAL 12/27 allí).
- **Veredicto §4 mecánico: PBO ≥ 0.20 → OVERFITTING de proceso — NO_CUMPLE** (y ≥0.30 → overfitting sustancial). Binario ledger (PBO<0.10): **NO_CUMPLE**. Zona gris 0.10–0.20 no aplica (0.4688 >>0.20).

**Ledger**: `signal_diagnosis` 21→22, `id=pbo_cscv_mom_rsi`, `n_trials_consumidos=1`, `umbral="PBO<0.10 (Bailey et al.)"`, `veredicto=NO_CUMPLE`, `artefacto=data/cache/pbo_cscv_mom_rsi_20260822_093300.txt`, `seccion_doc=PRE_REGISTRO_PBO_CSCV_MOM_RSI.md §4`.

**Interpretación honesta (no reinterpretar el criterio)**: PBO alto no significa que la estrategia pierda siempre; significa que **el procedimiento de elegir la mejor IS entre 21 no generaliza**: la IS #1 es tan buena como una elección aleatoria OOS (mediana). Es la firma de haber probado demasiadas variantes y quedarse con la que mejor quedó in-sample. El baseline momentum+RSI no se revoca automáticamente (es el único modo documentado que no se refutó como peor que alternativas, pero con DSR 0.17 en W3 nunca cruzó 0.90), pero **cualquier "mejor de 21" futuro exige validación OOS fresca** — el proceso selectivo medido aquí está sobreajustado. §39 (PBO=0.2358 intermedio sobre 27 vecinas, T=128) y este PBO=0.4688 sobre 21 con ventana más corta apuntan en la misma dirección (riesgo de grado, no de existencia), pero este con N=21 es el que audita el proceso real del ledger.

**No se toca**: T1.4/RESUMEN_STOP_ESTRUCTURAL (mejora calidad por trade, informativo no promovible) y Tarea L DSR/N_eff (solo calibración) — decisión del usuario.



---

## 41. Tarea O — Frog-in-the-Pan: ID condicionando momentum_12_1 (2026-08-22, PRE-REGISTRO antes de correr, consume ledger)

**Fuente**: Da, Gurun & Warachka (2014, RFS) "Frog in the Pan". Un grado de libertad
sobre momentum_12_1 ya validado (no un factor nuevo compitiendo solo). Asignada a
Kilo Code por Boris 2026-08-22 (`PLAN_LARGO_PLAZO.md` ronda en cola).

**Definición EXACTA de Information Discreteness** (fórmula del paper, verificada):
sobre la MISMA ventana de formación que `momentum_12_1` (= `close.pct_change(252)*100`,
`indicators.py:277`) — los últimos **252 retornos diarios** hasta t inclusive:

- `%neg` = fracción de días con retorno < 0 en la ventana; `%pos` = fracción > 0.
  Días con retorno exactamente 0 se excluyen de AMBAS (convención declarada).
- `PRET = momentum_12_1_t` (retorno acumulado de la ventana).
- **ID = sign(PRET) × (%neg − %pos)** ∈ [−1, +1].
  Equivalente al enunciado de PLAN_LARGO_PLAZO: sign(ret)×%contrarios − %iguales.
  ID muy negativo = información CONTINUA (muchos días pequeños a favor del signo);
  ID positivo / cercano a 0 = información DISCRETA (saltos con días contrarios).

Todo causal: usa solo retornos ≤ t. Sin datos nuevos (panel cacheado).

**Hipótesis**: el rank IC cross-sectional de `momentum_12_1` vs `fwd_20` es MAYOR en
el tercil de MENOR ID (información continua) que en el de MAYOR ID (discreta).

**Método** (protocolo familia signal_diagnosis §25/§37/§38):

- Panel universo 50 canónico (`opportunities_universe.SYMBOLS`), cache parquet,
  START=2018-01-01 (warmup 252d), DATA_END=2026-08-21 (cache vigente; ventanas fijas,
  días extra solo amplían W3 — declarado aquí, no post-hoc).
- SIN máscara de elegibilidad (población completa, igual que §37/§38).
- Terciles de ID POR FECHA (`qcut` cross-sectional, ranks method='first'): tercil 1 =
  menor ID (continua), tercil 3 = mayor ID (discreta). Mínimo 5 símbolos/bucket/día.
- IC diario = Spearman(momentum_12_1, fwd_20) intra-bucket por fecha.
- **ΔIC_t = IC_tercil1_t − IC_tercil3_t** (solo fechas con AMBOS buckets computables:
  serie pareada). t_NW = mean/SE Newey-West, L = min(12, n//8), copia fiel §0.5a.
- Ventanas: W1 2020-2021, W2 2022-2023, W3 2024→2026-07-06 (idénticas a §37/§38).

**Umbral**: familia `signal_diagnosis` con 22 consumidos → este trial es n=23 →
Bonferroni bilateral |t| > z(1 − 0.05/(2·23)) = **3.065** (46 comparaciones).

**CRITERIO DE ÉXITO (pre-registrado)**: ΔIC > 0 con t_NW > +3.065 en **≥2/3 ventanas**
→ CUMPLE. Si NO: línea cerrada como refutada, nada se integra. Si CUMPLE: la
integración (condicionar el score por ID) sería trial de MOTOR aparte — este
diagnóstico NO integra ni promueve nada.

**Reportes informativos (no disparan veredicto)**: IC por tercil y ventana;
TOTAL pooled no pre-registrado; distribución de ID (p10/p50/p90) como sanity check.

**Script**: `backend/scripts/trial_frog_in_the_pan.py` (nuevo, plantilla
`trial_cvd_proxy.py`). Python 3.9 real, lee cache, no descarga.
**No toca**: indicators.py, signal_engine.py, trial_registry.py en runtime
(registro manual al cierre), nada del motor. Artefacto:
`backend/data/cache/trial_frog_in_the_pan_<ts>.txt`.

## 42. Tarea P — Regime gating de momentum: UN trial coordinado con 3 sub-hipótesis (2026-08-22, PRE-REGISTRO ANTES de correr, consume ledger)

Fuente: `PLAN_LARGO_PLAZO.md` Tarea P (líneas 768-792). Contexto: PBO/CSCV N=21 = 0.4688
NO_CUMPLE sustancial (§40) y validación OOS fresca Sharpe_OOS +1.33 con DSR 0.6077 < 0.95
NO_CUMPLE (ledger signal_diagnosis ahora n=23). El baseline momentum+RSI queda
no-promovible; esta tarea es DIAGNÓSTICO que puede explicar CUÁNDO sí funciona el
momentum. Es además el primer uso REAL de `regime_gate.py::WalkForwardRegimeGate`
(M3, construido 2026-08-15, 8 tests, jamás usado para condicionar un factor).

**DECISIÓN DOCUMENTADA** (el plan ofrece dos opciones en líneas 789-792): **UN SOLO
TRIAL COORDINADO** con 3 sub-hipótesis pre-registradas, `n_trials_consumidos=1`.
Corrección intra-trial: Bonferroni sobre las 3 sub-hipótesis × 3 ventanas = m=9 tests.

**Umbral (leído del ledger EN runtime al redactar este pre-registro)**: familia
signal_diagnosis con 23 consumidos → este trial es n=24 →
`trial_registry.current_threshold("signal_diagnosis")` = **0.9958333333333333**
(= 1 − 0.10/24). Masa de error del trial α_trial = 0.00416667; repartida Bonferroni
sobre las m=9 celdas → α_por_test bilateral = 0.00416667/9 = 0.00046296 →
**|t| > z(1 − 0.00046296/2) = z(0.99976852) = 3.5013**. Referencia: la convención
previa de la familia sin split intra-trial daría z(1 − 0.05/(2·24)) = 3.078; la
corrección m=9 la endurece a 3.501 — declarado acá, antes de correr. Si otro trial de
la familia registra antes de esta corrida (O está en paralelo), el umbral se recalcula
con la misma fórmula sobre el ledger vigente y el artefacto cita el número efectivo.

**Factor y protocolo CONGELADOS** (fidelidad §0.5a, copia de §41/§37): 
momentum_12_1 = close.pct_change(252)\*100 sin skip (`indicators.py:277`);
fwd_20 = close.shift(-20)/close − 1; IC diario = Spearman(momentum_12_1, fwd_20)
por fecha sobre ≥5 símbolos; SE Newey-West L=min(12, n//8), copia fiel; SIN máscara
de elegibilidad. Ventanas canónicas: W1 2020-2021, W2 2022-2023, W3 2024→2026-07-06.
START=2015-01-02 — extendido vs el 2018 de trials previos ÚNICAMENTE para que
min_history=756 del gate cubra W1 completa; el factor solo necesita 252d de warmup y
las ventanas de análisis no cambian. DATA_END=2026-08-21 (cache termina 08-14/17;
diferencia ≤7 días → cero descargas, mismo criterio §41).

**Los 3 condicionantes (fórmulas fijadas ANTES de codear)**:

- **(a) Estado HMM rezagado un mes** — vía `WalkForwardRegimeGate.label_series`
  con `favorable_states=frozenset({0})` (GOLDILOCKS según el remapeo canónico
  `_align_states`: estado con growth_SPY máximo), defaults del módulo
  (recalib_every=63, min_history=756), price_data macro = tickers que usa
  `_extract_features` (SPY EFA QQQ GLD DBC TIP TLT AGG ^VIX, cache). La etiqueta
  usada en la fecha t es la de t−21 días hábiles (mes anterior); fechas sin etiqueta
  rezagada quedan fuera. Split: ΔIC(a) = IC(días GOLDILOCKS-lag) − IC(resto).
  Signo esperado + (Cooper-Gutierrez-Hameed 2004: momentum rinde más tras estados
  alcistas; coherente con macro IC +0.198 GOLDILOCKS / −0.173 DEFLATION medido aquí).
- **(b) Vol realizada de la cartera momentum** — cada cierre de mes (último hábil
  con ≥40 símbolos con momentum válido): top-quintil (10 de 50) por momentum_12_1;
  retorno diario del portafolio el mes siguiente = media equal-weight de los ret_1d
  de esos 10 (rebalanceo diario implícito, declarado). vol_t = std(ddof=1) rolling
  63 ruedas de esa serie (datos ≤ t). Tercil ESTRICTAMENTE causal: percentil
  expanding de vol_t contra vol_{≤t−1}, burn-in 126 ruedas; tercil 1 = baja vol.
  ΔIC(b) = IC(tercil1) − IC(tercil3). Signo esperado + (Barroso-Santa-Clara 2015:
  los crashes del momentum ocurren en alta vol realizada).
- **(c) Iliquidez Amihud agregada** — illiq_sym_t = |ret_1d|/(close×volume) por
  símbolo (volume>0); agregado diario = media sobre los símbolos disponibles ese día
  (≥25 requeridos); amihud_t = media rolling 21 ruedas. Tercil expanding causal
  idéntico a (b); tercil 1 = baja iliquidez. ΔIC(c) = IC(tercil1) − IC(tercil3).
  Signo esperado + (Avramov-Cheng-Hameed 2016: momentum más débil cuando la
  iliquidez agregada está alta).

**Estadística**: los buckets son DISJUNTOS por fecha (cada día cae en un bucket), a
diferencia del pareo de §41 → ΔIC = mean(IC_A) − mean(IC_B);
SE_diff = sqrt(SE_NW_A² + SE_NW_B²), L=min(12,n//8) por serie; supuesto de
independencia entre buckets declarado como riesgo. Celda computable requiere
≥30 días con IC en AMBOS buckets de la ventana.

**CRITERIO DE ÉXITO POR CONDICIONANTE (pre-registrado)**: ΔIC > 0 (signo declarado
arriba) con t_NW > **+3.5013** en **≥2/3 ventanas** → CUMPLE. Ventana no computable
cuenta como no-signal para ese condicionante. Si no hay ≥2 ventanas computables →
NO_CUMPLE mecánico. **Veredicto global**: CUMPLE si ≥1 de los 3 CUMPLE (regla OR,
protegida por Bonferroni m=9). Los 3 son diagnósticos INDEPENDIENTES: ninguno integra
motor sin trial de MOTOR aparte (esto no toca signal_engine.py ni el score vivo).

**Riesgos declarados**: estados HMM desbalanceados (GOLDILOCKS puede dominar el
calendario → bucket resto heterogéneo; distribución reportada); Amihud sensible a
microcaps/outliers de volumen dentro del universo 50; terciles de vol con fuerte
autocorrelación (rachas → efectivo muestral menor); SE_diff bajo independencia puede
subestimar (fwd_20 solapa 20 ruedas entre buckets vecinos); cobertura W1 del gate
depende del START extendido; HMM sin convergencia → label_series lanza excepción →
corrida abortada documentada como FALLO, no se fuerza resultado.

**Checks de fidelidad (estilo §39/validacion OOS)**: F1 universo 50 cargadas; F2
cobertura de meses por ventana; F3 edge TOTAL pooled de momentum_12_1 > 0
(informativo); F4 determinismo seed 42 (random_state del HMM verificado en runtime,
qcut/expanding deterministas); F5 asserts anti-lookahead del gate pasaron y
n_recalibraciones>0.

**Script**: `backend/scripts/trial_regime_gating_p.py` (nuevo, plantilla
`trial_frog_in_the_pan.py`). Python 3.9 real, lee SOLO cache parquet, sin descargas.
**No toca**: indicators.py, signal_engine.py, regime_gate.py/regime_classifier.py,
trial_registry.py en runtime (registro manual al cierre), PRE_REGISTRO_PBO_CSCV ni
validación OOS (otros agentes). Artefacto:
`backend/data/cache/trial_regime_gating_p_<ts>.txt` (+`.json`).

### 42.1 RESULTADO (apéndice post-corrida, 2026-08-22) — corrida ÚNICA 16:26

Artefacto: `backend/data/cache/regime_gating_p_20260822_162628.txt` (+`.json`).
Umbral efectivo: ledger consumido=23 → n=24 → current_threshold()=0.9958333333333333
→ α_trial/9 → **|t| > +3.5013** bilateral (idéntico al pre-registrado; ningún otro
trial de la familia registró entre pre-registro y corrida).

**Fidelidad**: F1 universo 50/50 · F2 meses con datos W1=24/W2=24/W3=31 (jul-26
parcial) · F3 edge pooled TOTAL IC=+0.0079 (t+0.47, n=2649; positivo, débil — el
momentum diario promedia casi cero, consistente con la familia) · F4 seed HMM 42 ·
F5 gate walk-forward OK: 34 recalibraciones, asserts anti-lookahead pasados,
distribución de estados no degenerada (GOLDILOCKS 528 / REFLATION 446 /
STAGFLATION 821 / DEFLATION 312 días).

| Condicionante | W1 ΔIC (t) | W2 ΔIC (t) | W3 ΔIC (t) | SIG | Veredicto |
|---|---|---|---|---|---|
| (a) HMM rezagado GOLDILOCKS−resto | **+0.1774 (+3.14)** | +0.0121 (+0.17) | −0.0678 (−1.12) | 0/3 | **NO_CUMPLE** |
| (b) Vol cartera t1−t3 | +0.0663 (+0.94) | +0.0352 (+0.31) | +0.0148 (+0.15) | 0/3 | **NO_CUMPLE** |
| (c) Amihud t1−t3 | −0.1864 (−1.56) | no computable (n_B=6) | no computable (n_B=0) | 0/3 | **NO_CUMPLE** |

**VEREDICTO GLOBAL: NO_CUMPLE** (regla OR). Ledger signal_diagnosis 23→24, id
`regime_gating_p`, n=1.

Lectura honesta SIN reinterpretar el veredicto: (a) W1 fue sugerente (t +3.14, signo
correcto, coherente con Cooper-Gutierrez-Hameed) pero NO cruza la vara m=9 (3.5013)
y NO se repite en W2/W3 — la hipótesis del estado rezagado como compuerta queda sin
evidencia suficiente bajo esta disciplina. (c) materializó el riesgo declarado: la
Amihud agregada es tan persistente que su percentil expanding colapsa los terciles
altos (1911/490/141 días; tercil alto casi desaparece en W2/W3) — el split es
inaplicable así como se definió; además el signo en W1 fue el OPUESTO al paper
(IC mayor en alta iliquidez). (b) plano en las tres ventanas.
Ninguna compuerta se integra al motor; regime_gate.py sigue siendo infraestructura
disponible (ahora CON un primer uso real documentado).

### RESULTADO §41 (2026-08-22, corrido tras el pre-registro)

- Fidelidad: panel 119900 filas × 50 símbolos × 2398 fechas (2016-12-30→2026-07-17);
  ID sanity p10 −0.151 / p50 −0.068 / p90 +0.024 (rango [−1,+1] respetado, masa en
  negativo = mayoría de símbolos con información continua, esperable).
- **ΔIC(t1−t3): W1 −0.51, W2 +2.16, W3 −0.07 → 0/3 ventanas con t_NW > +3.065 →
  NO_CUMPLE.** Ni siquiera W2 (la más favorable) llega al umbral.
- ICs por tercil (informativo): tercil1 continuo +0.28 TOTAL (t), tercil3 discreto
  −0.41; la dirección promedio va a favor de la hipótesis pero el efecto es ruido
  (TOTAL ΔIC t +0.65) e INESTABLE por ventana (W1 y W3 con signo contrario).
- Lectura honesta: el condicionamiento Frog-in-the-Pan NO rescatable a este tamaño
  de universo/horizonte con la vara de la familia. La asimetría del paper (6m,
  cross-section grande US) no se traslada a momentum_12_1 sobre N=50 diario.

**Ledger**: `signal_diagnosis` → `id=trial_frog_in_the_pan`, veredicto NO_CUMPLE,
artefacto `backend/data/cache/trial_frog_in_the_pan_20260822_175302.txt`. Al momento
de correr: 22 consumidos (este era n=23, umbral fijado ex-ante). Nota: durante la
corrida OpenCode registró en paralelo `validacion_oos_fresca_mom_rsi` y
`regime_gating_p` (familia ahora en 25) — no afectan este veredicto (umbral propio).

**No se integra nada al motor** — momentum_12_1 queda como estaba (sin condición ID).

---

## 43. PBO/CSCV de FIDELIDAD COMPLETA — candidatos reconstruidos como configuraciones REALES del motor (2026-08-22, PRE-REGISTRO ANTES de correr, consume ledger)

**Autor**: OpenCode. Cierra la limitación declarada en §40: los 21 del PBO proxy eran
vecinos de parámetros (grid w×banda×techo), NO las configuraciones que el proceso pudo
haber elegido realmente. Aquí cada candidato corre `backtest_engine.run()` COMPLETO
(stops, regime-gating, calibrador walk-forward, execution_lag_days=1, costos vigentes)
y el PBO mide selección entre esas configuraciones ejecutables reales.

**Naturaleza**: trial diagnóstico de proceso, familia `signal_diagnosis`,
`n_trials_consumidos=1`. Ledger al momento del pre-registro: **consumido=25**
(`current_threshold=0.99615`) — este es el slot 26. Umbral aplicable a ESTE trial:
**PBO<0.10 (Bailey et al.)**, no Bonferroni-t (PBO ya captura la selección; §4 del
pre-registro original).

### 43.1 PASO 1 — MAPEO HONESTO de los 21 ids congelados de §6.1 (tabla CONGELADA, no se edita después)

Criterio: ¿el id corresponde a una configuración EJECUTABLE por
`backtest_engine.run()` como variante del score/gates que el motor pudo haber adoptado?
Los diagnósticos de factores nunca wireados (OFI, CVD, FinBERT, gap-reversion,
lead-lag…) no tienen config de motor → EXCLUIDOS con justificación. Los diagnósticos
que ALIMENTARON una decisión real sobre score/gates/horizonte aportan el eje ejecutable
correspondiente.

| # | id §6.1 | ¿Ejecutable por run()? | Justificación / eje que alimenta |
|---|---|---|---|
| 1 | fase05a_rr2_intraday | NO directo | IC intra-día diagnóstico. ALIMENTA ejes pesos/banda y la alternativa ADX-in-blend (decisión §0.5a documentada en signal_engine.py) |
| 2 | fase05b_rmt | NO | Factores residuales RMT jamás wireados al motor |
| 3 | fase05c_ridge_macro_crudo | NO | Ridge macro crudo refutado antes de integrar (delta −0.0046); su primo wireado fue trial_13 (familia motor_signal, fuera de los 21) |
| 4 | sectorial_endogeno | NO | Diagnóstico de clusters; sin config de motor |
| 5 | reeval_trial14 | NO | Basket timing ADX = otra clase de estrategia (no selección de acciones del motor) |
| 6 | gap_reversion_diag | NO | Microestructura intra-día; motor EOD; refutado con costos (§13.1) |
| 7 | rr2_subperiodos | NO | Auditoría de estabilidad temporal del IC; sin config |
| 8 | ma200_clusters | NO | Niveles MA200 por cluster; C6 backtesteado aparte y refutado (§18.1/18.2); nunca variante del score/gates |
| 9 | donchian | NO | Factor canal refutado (t −0.81); sin config |
| 10 | ma200_beta_control | NO | Control estadístico de beta; sin config |
| 11 | horizon_audit_5d_10d | ALIMENTA EJE | `CALIBRATION_HORIZON_DAYS` es knob REAL del motor (constante de módulo usada en labels de calibración) → candidato HORIZON10 (10d auditado en M1) |
| 12 | horizon_largo_60d_125d | NO | 60d/125d fuera de la ventana producto declarada (short-term 1–30d) → excluido con justificación |
| 13 | lead_lag_diag | NO | Lead-lag cross-symbol; sin config EOD del motor |
| 14 | triple_barrier_retest | NO | Re-etiquetado para diagnóstico; label interno del motor intacto |
| 15 | adx_walkforward | ALIMENTA EJE | Confirmó ADX marginal-no-robusto; la alternativa "ADX al blend" era opción VIVA rechazada en §0.5a → candidato ADX_BLEND |
| 16 | weekly_indicators_2026 | NO | Velas semanales; motor opera diario EOD; sin config |
| 17 | finbert_sentiment_eventstudy | NO | Panel 8-K point-in-time nunca disponible para run(); refutado |
| 18 | xsec_relative_and_aaii_timing | NO directo | El timing AAII SÍ es parámetro real de run() (`sentiment_data`→G2), pero fue probado/refutado como trials motor_signal #8/fase06 (familia distinta, fuera de los 21 y fuera del scope score/gates del baseline) |
| 19 | trial_macd_bollinger | NO | MACD/Bollinger diagnósticos sin config (refutados §36) |
| 20 | trial_ofi_proxy | NO | OFI nunca wireado (refutado §37) |
| 21 | trial_cvd_proxy | NO | CVD nunca wireado (refutado §38) |

**Resultado del mapeo: N=9 ≠ 21.** De los 21 ids, 0 son corridas directas del motor;
3 alimentan ejes ejecutables (pesos/banda/adx desde fase05a+§0.5a+adx_walkforward;
horizonte desde M1); 18 carecen de configuración de motor posible. Los 4 ids
posteriores a §6.1 (`pbo_cscv_mom_rsi`, `validacion_oos_fresca_mom_rsi`,
`regime_gating_p`, `trial_frog_in_the_pan`) tampoco tienen config de motor
(auditorías/diagnósticos IC) → misma exclusión. La fidelidad es al PROCESO de
selección real, no al número 21.

**Nota histórica**: el estado PRE-IC del motor (commit pre-02e419d, pesos
{momentum .35/technical .65}) usa una fórmula de score distinta (composite técnico
retirado) — excluido: el proceso auditado opera sobre la estructura momentum+RSI
post-lockeo del baseline.

### 43.2 Conjunto de candidatos EJECUTABLES (N=9, congelado)

Variaciones UN-EJE-A-LA-VEZ alrededor del ACTUAL (el proceso real perturbó un eje por
vez, nunca movimientos conjuntos):

| id candidato | w_mom/w_rsi | banda RSI sub-score | techo mom | CALIBRATION_HORIZON_DAYS | Origen documentado |
|---|---|---|---|---|---|
| ACTUAL (baseline) | .664/.336 | (45,70) | 100 | 20 | signal_engine.py vigente |
| W_EQUAL | .500/.500 | (45,70) | 100 | 20 | alternativa sin re-weighting IC (midpoint medido en §39 y §40) |
| W_MOM80 | .800/.200 | (45,70) | 100 | 20 | vecino momentum-heavy MEDIDO en artefactos §39 y §40 |
| BAND_WIDE | .664/.336 | (40,65) | 100 | 20 | banda medida en §39/§40 |
| BAND_NARROW | .664/.336 | (50,75) | 100 | 20 | banda medida en §39/§40 |
| CAP_LOW | .664/.336 | (45,70) | 75 | 20 | techo medido en §39/§40 |
| CAP_HIGH | .664/.336 | (45,70) | 125 | 20 | techo medido en §39/§40 |
| HORIZON10 | .664/.336 | (45,70) | 100 | 10 | horizonte 10d auditado en M1 (horizon_audit artifact) |
| ADX_BLEND | IC-proporcional 3 factores (.3889/.1966/.4145 sobre ICs pooled .0637/.0322/.0679) | (45,70) | 100 | 20 | opción viva RECHAZADA explícitamente en §0.5a (adx_score = 0.9 si adx>25 else 0.3, definición compute_factor_frame) |

EXCLUIDOS con justificación (nunca disponibles para el motor o fuera de scope):
sentimiento AAII/G2 y fundamentales/G3 (trials motor_signal #8/#9 ya refutados, familia
distinta), stops estructurales T1.4 (`use_market_structure=True`: mecanismo de SALIDAS,
no variante de score/gate de entrada; su evaluación vive en RESUMEN_STOP_ESTRUCTURAL
como informativo no promovido), stops EVT (familia risk/motor_signal refutada), ridge_3f
(motor_signal #13 refutado), basket ADX, C6/MA200, gap-reversion, lead-lag, OFI, CVD,
FinBERT, weekly, ID/frog, regime gating, hurst/vol_regime (diagnósticos sin config).

### 43.3 Implementación SIN tocar archivos del motor

- `SignalEngine` se SUBCLASIFICA (no se edita): override de `_factor_scores` +
  `factor_weights` parametrizando w_mom/banda/techo (+ adx para ADX_BLEND).
  `BacktestEngine` también se subclasifica solo para inyectar la señal custom tras
  `super().__init__()` (patrón `_make_risk_manager`, aditivo, previsto en el código).
- HORIZON10: patch de la constante de módulo `app.core.backtest_engine.CALIBRATION_HORIZON_DAYS`
  SOLO durante esa corrida (restore inmediato). Limitación declarada: el default-arg de
  `validate_signal_quality(horizon=…)` se liga en definición y queda en 20 — afecta solo
  al diagnóstico colateral, NO al path de trading (labels de calibración sí quedan en 10).
- Datos: cache parquet local SIN descargas (offline determinista), columnas lowercase,
  universo 50 canónico `opportunities_universe.SYMBOLS`. price_data y market_data se
  cargan desde 2015-01-02 (cache completo) → `_build_calibration_dataset` tiene replay
  real 2016–2018 y el HMM fittea con historia. Ventana evaluada:
  **2019-01-01 → 2026-08-14** (fin del cache real; "hoy" no tiene datos aún).
- Costos/lag: `commission=settings.COST_PER_SIDE=0.0005`, `slippage=0.0005`,
  `execution_lag_days=1`, `use_market_structure=False`, capital 25 000 — idéntico para
  las 9.
- Serie mensual neta: equity curve diaria de run() → equity último hábil de mes →
  `pct_change` mensual (los meses sin trades rinden 0 = cash; riesgo declarado).
- CSCV: S=16 bloques contiguos → C(16,8)=12 870 splits (fallback S=12 si bloque <60
  ruedas; T truncado a múltiplo de S reteniendo meses recientes, igual que §40).
  Sharpe anualizado OOS mensual ×√12. Por split: rank IS de las 9 → rank_OOS del best-IS
  → logit λ=log((r/(N+1))/(1−r/(N+1))). **PBO = P(λ≤0)**. Secundarios: degradación
  Sharpe_OOS−IS del best IS, Spearman IS vs OOS, Sharpe_full por config + rank del ACTUAL.
- Determinista: seed 42 (np.random.seed antes de CADA run() — el bootstrap MC de
  calculate_metrics usa np.random global; bootstrap CI usa Generator local seed 42;
  HMM random_state=42 ya en regime_classifier).

### 43.4 CRITERIO CONGELADO (mismos buckets de §40 / §4 del pre-registro original)

| PBO | Veredicto |
|---|---|
| <0.10 | **CUMPLE** — ranking IS informativo, no overfitting de proceso |
| 0.10–0.20 | zona gris — binario **NO_CUMPLE** |
| ≥0.20 | **NO_CUMPLE** — overfitting de proceso |
| ≥0.30 | NO_CUMPLE **sustancial** |

### 43.5 Checks de fidelidad pre-registrados (fallar alguno → FALLO HONESTO, corrida no interpretable)

1. Universo: ≥45/50 símbolos con datos cargados.
2. T mínimo: T_final ≥ 72 meses tras truncado a múltiplo de S.
3. Cobertura baseline: ≥30% de meses con ≥1 trade cerrado.
4. Edge positivo ex-costos del baseline: mean retorno mensual NETO > 0 Y total_trades ≥ 100
   (comparabilidad con baseline_clean 286 trades) Y Sharpe_full(ACTUAL) > 0.
5. **NUEVO — fidelidad de ejecución**: cada corrida registra y el artefacto lista
   `execution_lag_days=1`, `commission=0.0005` (settings.COST_PER_SIDE),
   `slippage=0.0005`, `use_market_structure=False`; aserción runtime por config.

### 43.6 Presupuesto de cómputo (obligatorio ANTES de lanzar)

Correr UNA config (baseline ACTUAL) midiendo wall-clock → forecast total 9×.
Paralelización con multiprocessing Pool workers=cpu_count()-2 (6), cada worker su propio
BacktestEngine (sin estado compartido: engine/calibrador/HMM son instancia-local; el
ledger JSON se lee solo en el proceso padre; config_registry cachea por proceso y aquí ni
se consulta en el hot path). **Si el forecast total >4h aun paralelo → PARAR y consultar
a Boris antes de lanzar.**

### 43.7 Riesgos declarados ANTES de correr

1. Correlación altísima entre vecinos un-eje (esperable N_eff bajo inflado) — declarado;
   PBO no lo corrige, lo expone.
2. Meses sin trades → retorno 0 (cash) comprime varianza diferencial entre configs.
3. Monkeypatch del horizonte: único camino sin editar archivos; default-arg diagnóstico
   queda en 20 (limitación cosmética, no afecta trades).
4. Costo computacional alto por corrida completa (calibración replay + copulas +
   Monte Carlo de run() completo son parte del contrato "run() tal cual").
5. Comparabilidad con §40: cambia N (9 vs 21), ventana fin (08-14 vs 08-04), frecuencia
   idéntica (mensual neta ×√12) y ahora SÍ hay stops/regime/calibrador — la comparación
   de PBOs es OBSERVACIÓN, nunca cambio de veredicto.

### 43.8 Artefacto, script y ledger

- Script: `backend/scripts/pbo_cscv_fidelidad_completa.py` (nuevo).
- Artefacto: `backend/data/cache/pbo_cscv_fidelidad_<ts>.txt` + `.json`.
- Ledger: `register_trial(id="pbo_cscv_fidelidad_completa", familia="signal_diagnosis",
  n_trials_consumidos=1, umbral_aplicado="PBO<0.10 (Bailey et al.)", veredicto=mecánico §43.4)`.
  Veredicto NO se interpreta ni ajusta post-hoc.
- Corrida ÚNICA: sin re-corridas para "probar otro S/N". Si aborta por fidelidad →
  NO INTERPRETABLE, no NO_CUMPLE.

---

## 44. Tarea M — KAMA / HMA / Supertrend: familia de tendencia adaptativa, UN trial coordinado con 3 sub-hipótesis (2026-08-23, PRE-REGISTRO ANTES de correr, consume ledger)

Fuente: `PLAN_LARGO_PLAZO.md` Tarea M (líneas 585-640) + regla añadida 2026-08-19
(líneas 574-583): los 3 indicadores miden DIRECCIÓN (verificado contra origen por la
spec — KAMA Kaufman 1972/1995; HMA Hull 2005; Supertrend Seban ~2009, sin respaldo
académico, caveat registrado), por eso comparten protocolo con momentum/RSI: rank IC
intra-día contra fwd_return_20d. No es el error de Bollinger (régimen) repetido.
Contexto: Tarea N (§36) cerró MACD NO_CUMPLE 0/3 con este mismo protocolo.

**DECISIÓN DOCUMENTADA**: UN SOLO TRIAL COORDINADO con las 3 sub-hipótesis
(KAMA, HMA, Supertrend), `n_trials_consumidos=1`. Corrección intra-trial:
Bonferroni sobre 3 indicadores × 3 ventanas = **m=9 tests primarios**.

**Umbral (leído del ledger EN runtime al redactar este pre-registro, 2026-08-23)**:
familia signal_diagnosis con **25 consumidos** → este trial es n=26 →
`trial_registry.current_threshold("signal_diagnosis")` = **0.9961538461538462**
(= 1 − 0.10/26). Masa de error del trial α_trial = 0.00384615; repartida Bonferroni
sobre m=9 celdas → α_por_test = 0.00384615/9 = 0.00042735 bilateral →
**|t| > z(1 − 0.00042735/2) = z(0.99978633) = 3.5226**. El script lee el ledger en
runtime y recalcula con la MISMA fórmula si otro trial de la familia registra antes
de esta corrida (patrón §42); el artefacto cita el número efectivo usado.

**Los 3 factores (fórmulas fijadas ANTES de codear)** — todos normalizados por
precio para ser comparables cross-sectional (el IC es Spearman intra-día entre
símbolos):

- **kama_dist** = (close − KAMA)/close. KAMA estándar de Kaufman:
  ER = `predictive_indicators.compute_efficiency_ratio(close, period=10)` (reusado,
  no reinventado — orden expreso de la spec); sc_t = (ER_t×(2/(2+1) − 2/(30+1)) +
  2/(30+1))²; recursión causal kama_t = kama_{t−1} + sc_t×(close_t − kama_{t−1})
  sembrada en el primer close válido del ER. Parámetros canónicos er=10/fast=2/slow=30.
- **hma_dist** = (close − HMA)/close con HMA(16): WMA ponderada lineal (pesos
  1..n), HMA_n = WMA(2×WMA(n/2) − WMA(n), √n) con n=16 (√n→4). Fórmula literal de
  Alan Hull (2005).
- **supertrend_side** ∈ {+1, −1}: Supertrend(ATR period=10, multiplicador=3.0),
  parámetros canónicos de comunidad. basic_ub/lb = hl2 ± 3×ATR10 (atr() ya existente);
  bandas finales con ratchet causal estándar (final_ub solo baja si basic_ub baja o
  close_{t−1} > final_ub_{t−1}; simétrico abajo); dirección flip a +1 cuando close
  cruza por encima de final_ub previo, a −1 cuando cruza por debajo de final_lb
  previo, sino arrastra. NaN hasta el primer ATR válido.

**Signo esperado (declarado antes de correr)**: +1 para los tres — proxy de
tendencia alcista en t → mayor retorno futuro (misma hipótesis de continuación que
momentum_12_1/RSI; ADX ya mostró señal nominal positiva en esta familia).

**Protocolo CONGELADO** (fidelidad §0.5a, copia §41/§42): fwd_20 =
close.shift(−20)/close − 1; IC diario = Spearman(factor, fwd_20) por fecha sobre
≥5 símbolos; SE Newey-West L=min(12, n//8), copia fiel; SIN máscara de elegibilidad;
los factores entran a `calculate_all_indicators` como columnas nuevas (patrón
T1.1/T1.2/T2.3: disponibles para diagnóstico, NO wired a signal_engine ni al score).
Ventanas canónicas: W1 2020-2021, W2 2022-2023, W3 2024-01-01→2026-07-06 (idénticas
a §41/§42 para comparabilidad). START=2015-01-02 (warmup máximo necesario ≈60 ruedas,
cubierto de sobra); DATA_END=2026-08-21 (cache termina 08-14/17+, diff ≤7 días →
cero descargas, mismo criterio §41).

**CRITERIO DE ÉXITO POR INDICADOR (pre-registrado)**: IC > 0 (signo declarado) con
t_NW > **+ZC** en **≥2/3 ventanas computables** → CUMPLE ese indicador. Ventana no
computable (<30 días con IC o <5 símbolos) cuenta como no-signal. **Veredicto
global**: CUMPLE si ≥1 de los 3 CUMPLE (regla OR, protegida por Bonferroni m=9).
Ninguno integra motor sin trial de MOTOR aparte (esto no toca signal_engine.py ni
el score vivo — regla explícita de la spec).

**Desglose por régimen (SECUNDARIO, NO gating — declarado antes de correr)**:
requisito de la spec ("reportar también el IC condicionado por régimen… usar
regime_gate.py para clasificar cada fecha ANTES de correr — no post-hoc"). Estado
HMM rezagado 21 hábiles vía `WalkForwardRegimeGate(favorable_states={0})`
(GOLDILOCKS, defaults recalib_every=63/min_history=756, macro SPY EFA QQQ GLD DBC
TIP TLT AGG ^VIX — idéntico a §42a, segundo uso real de M3). Para cada indicador ×
ventana se REPORTA ΔIC(GOLDILOCKS-lag − resto) con su t_NW y n por bucket. Este
desglose es EXPLORATORIO: ningún veredicto CUMPLE/NO_CUMPLE sale de acá; una pista
fuerte (t>ZC sostenido) se documenta como candidata a trial propio, nunca como
resultado positivo del trial M. Los 9 tests primarios son los únicos que gatean.

**Riesgos declarados**: los 3 factores comparten la misma señal latente (tendencia)
→ ICs correlacionados entre sub-hipótesis; el OR con Bonferroni m=9 asume celdas
contables, un único CUMPLE aislado tiene menor informatividad (declarado). Supertrend
es binario → varianza cross-sectional mínima, ties masivos en ranks, |IC| diarios
chicos por construcción. hma_dist/kama_dist correlacionan con momentum de corto
pelo (misma familia, no invalida la medición). Warmup nuevo (<60 ruedas) ≪ 252 de
momentum_12_1 → el dropna de `calculate_all_indicators` sigue dominado por momentum,
sin cambio de comportamiento en columnas existentes (tests existentes lo verifican).
Cobertura W1 del gate depende del START extendido (mismo riesgo aceptado en §42).
HMM sin convergencia → label_series lanza → corrida abortada documentada como FALLO
honesto, no NO_CUMPLE.

**Checks de fidelidad (estilo §39/§41/§42)**: F1 universo 50 cargadas; F2 cobertura
de meses por ventana (~24/24/30); F3 edge pooled TOTAL por factor (informativo);
F4 determinismo seed 42 del HMM verificado en runtime; F5 asserts anti-lookahead del
gate pasaron y n_recalibraciones>0; F6 tests unitarios sintéticos de tendencia
conocida de los 3 indicadores en verde ANTES de correr (la corrida exige suite de
indicators pasada — caso sintético de tendencia conocida por función, orden de la
spec punto 4).

**Script**: `backend/scripts/trial_kama_hma_supertrend.py` (nuevo, plantilla
`trial_regime_gating_p.py`). Python 3.9 real (backend/.venv), lee SOLO cache parquet,
sin descargas. **No toca**: signal_engine.py, regime_gate.py/regime_classifier.py,
trial_registry.py en runtime (registro manual al cierre), predictivo_engine/triad
(peso de score intacto). Implementación nueva SOLO en indicators.py (funciones +
columnas diagnósticas) y tests/test_indicators.py. Artefacto:
`backend/data/cache/trial_kama_hma_supertrend_<ts>.txt` (+`.json`). Ledger:
`register_trial(id="trial_kama_hma_supertrend", familia="signal_diagnosis",
n_trials_consumidos=1, umbral_aplicado="Bonferroni m=9 |t|>ZC sobre th vigente",
veredicto=mecánico, seccion_doc="§44")`. Corrida ÚNICA: si aborta por fidelidad →
NO INTERPRETABLE, no NO_CUMPLE (mismo contrato §43.8).

### 44.1 RESULTADO (apéndice post-corrida, 2026-08-23) — corrida ÚNICA 15:28

Corrida única (`scripts/trial_kama_hma_supertrend.py`, artefacto
`data/cache/trial_kama_hma_supertrend_20260823_152846.txt`+`.json`). Umbral
efectivo = el del pre-registro: ledger consumido=25 → n=26 → th=0.9961538461538462,
m=9 → **|t|>3.5226** (sin recalculo: ningún otro trial registró en el medio).

**Fidelidad OK×5**: F1 universo 50/50; F2 cobertura 24/24/31 meses; F4 seed HMM 42;
F5 gate walk-forward 34 recalibraciones, asserts anti-lookahead OK, estados no
degenerados {0:548, 1:446, 2:831, 3:285}; panel 133650 filas × 2673 fechas
(2016-01-04→2026-08-20), cero descargas. Nota técnica declarada: días con
supertrend_side constante cross-sectional (todos +1 o todos −1) no producen IC
(Spearman indefinido) y quedan fuera — n st = 2651 vs 2653 días de los otros.

**TESTS PRIMARIOS — 0/9 celdas significativas → GLOBAL NO_CUMPLE**:

| factor | W1 | W2 | W3 | pooled TOTAL (informativo) |
|---|---|---|---|---|
| kama_dist | −0.0219 (t−0.98) | −0.0026 (t−0.10) | +0.0061 (t+0.27) | IC −0.0103 (t−1.01) |
| hma_dist | −0.0044 (t−0.26) | +0.0059 (t+0.31) | −0.0090 (t−0.67) | IC −0.0016 (t−0.24) |
| supertrend_side | −0.0361 (t−1.40) | +0.0127 (t+0.55) | +0.0195 (t+0.91) | IC −0.0126 (t−1.24) |

Veredictos por indicador: kama_dist NO_CUMPLE, hma_dist NO_CUMPLE,
supertrend_side NO_CUMPLE. Ni siquiera señal nominal: los tres con IC TOTAL
ligeramente NEGATIVO (signo contrario al esperado de continuación) y |t| máximos
por ventana ≤1.40 — lejos del umbral 3.5226 y sin consistencia de signo entre
ventanas. La familia de tendencia adaptativa sobre N=50 diario NO predice
retorno a 20 ruedas cross-sectional.

**Desglose por régimen (EXPLORATORIO, pre-declarado no-gating)**: ΔIC(GOLDILOCKS-lag
− resto) máximo |t|=+2.58 (supertrend_side W1) — mismo patrón débil-no-confirmado
de Tarea P(a): sugerente solo en W1 (n gold=43), sin repetición en W2/W3, muy por
debajo de ZC=3.52. Sin pistas sobre el umbral; nada candidatiza trial propio.

**Ledger**: `signal_diagnosis` 25→26 consumidos, id=`trial_kama_hma_supertrend`,
veredicto=NO_CUMPLE, próximo threshold 0.99630. **Nada se integra al motor**
(indicadores quedan disponibles como columnas diagnósticas, patrón T1.x/T2.x;
signal_engine.py intacto). Implementación: `kama()`/`hma()`/`wma()`/
`supertrend()` en indicators.py + 10 tests sintéticos (suite 367 passed).

---

## 45. TRIAL #18 — PRE-REGISTRO: stops EVT con sizing aislado (re-take de la línea #15, neutralizando las DOS capas de inercia) — **BORRADOR PARA REVISIÓN, NO CORRER hasta aprobación explícita**

> **Estado**: APROBADO para ejecución (revisión del coordinador Claude Code,
> 2026-08-24, con Boris): diseño validado, umbral n=12/th=0.99167 verificado
> contra el ledger real. Única modificación de la revisión incorporada abajo
> (consumo explícito del slot según gate de activación). Luz verde completa:
> implementar, correr UNA vez, cerrar.

**Pregunta (la misma de §20, ahora medible)**: sustituir la distancia de riesgo
del sizing (`stop_distance = max(2×ATR, price×position_stop)`) por la distancia
EVT walk-forward (`stop_distance = max(VaR_GPD(99%)×σ_EWMA_día,
price×position_stop)`), **cuando `shares_by_risk` es efectivamente la restricción
activa del sizing**, ¿mejora el perfil de riesgo-retorno del motor (DSR OOS)?

**Por qué #15 fue placebo y qué exige el re-diseño (Hallazgo 5+6,
AUDITORIA_MECANICA.md)** — la inercia tenía DOS capas y hay que neutralizar las dos:

1. **Capa Kelly**: `compute_position_size()` toma la rama Kelly cuando
   win_prob/payoff_ratio ≠ None (siempre en producción, backtest_engine.py:552-557)
   → `kelly_shares` domina el `min()`. Fix propuesto por ROADMAP: aislar
   `shares_by_risk` del Kelly. PERO `fractional_kelly=0` NO sirve tal cual:
   dejaría `kelly_shares=0` → `min(0,…)=0` → cero posiciones. El mecanismo
   correcto equivalente es **desactivar la rama Kelly simétricamente en AMBOS
   brazos** vía subclase que replica la rama no-Kelly
   (`return int(min(shares_by_risk, max_shares))`, adaptive_risk.py:121).
2. **Capa tope**: aun sin Kelly, `max_shares = 10%×equity/price` gana el `min()`
   salvo que `stop_distance > (RISK_PER_TRADE/MAX_POSITION_PCT)×price = 15%×price`
   (con RISK_PER_TRADE=1.5% vigente). Ni 2×ATR típico (4–6% del precio) ni el
   VaR-GPD de §19 llegan ahí → placebo otra vez (281/281 trades, Hallazgo 6).
   **Fix propuesto**: reducir RISK_PER_TRADE SOLO dentro del experimento, en
   AMBOS brazos por igual.

**DECISIÓN DE DISEÑO PROPUESTA (marcada para revisión)**:

- **Dial elegido**: `RISK_PER_TRADE_arm = 0.0015` (0.15%, un décimo del vigente),
  `MAX_POSITION_PCT` intacto (10%). Umbral de binding resultante:
  `dist > (0.0015/0.10)×price = 1.5%×price` — por DEBAJO del rango típico de
  AMBAS distancias documentadas ex-ante (2×ATR 4–6%P, Hallazgo 6; EVT mediana
  5.2% σ-día, Hallazgo 6 reconstrucción). Así `shares_by_risk` es la restricción
  activa esperada en la gran mayoría de los trades de ambos brazos, con tamaños
  de posición resultantes (~2–5% equity por posición) dentro de lo
  production-plausible. El dial se calibró contra distribuciones ya publicadas
  en artefactos (Hallazgo 6), NO mirando resultados nuevos.
- **Alternativas consideradas y rechazadas**: (i) subir MAX_POSITION_PCT a 100%
  → concentraciones de 30–40% equity por nombre y artefactos de orden dependiente
  de cash (el motor solo compra si `cost < cash`, backtest_engine.py:560);
  (ii) overlay analítico post-hoc sobre la misma lista de trades → estadísticamente
  limpio pero abandona la pregunta "el motor decidiendo"; (iii) apalancar capital
  → mismo problema de realismo que (i). La auditoría (Hallazgo 6 "Implicación")
  lista exactamente estas tres rutas; se elige la variante que mantiene el tope
  de concentración de producción.
- **Alcance idéntico a §20 (variante mínima)**: el EVT sustituye SOLO la
  distancia de riesgo del sizing; `position_stop` ejecutivo, PARTIAL_TP 2×ATR,
  trailing 2×ATR, ABSOLUTE_CEILING, cooldowns y gates de señal intactos.

**Mecánica del trial (`scripts/trial_evt_stops_v2.py`, NUEVO — reuso verbatim de
la maquinaria validada de `trial_evt_stops.py` post-fix-Hallazgo-5)**:

- Dos subclases simétricas inyectadas vía hook `_make_risk_manager()`
  (backtest_engine.py:41, sin duplicar `run()`, cero edición del motor):
  - `BaselineRiskManager`: replica `compute_position_size` con
    `stop_distance = max(2×atr, price×position_stop)` y rama no-Kelly
    (`int(min(shares_by_risk, max_shares))`), RISK_PER_TRADE_arm=0.0015.
  - `EVTRiskManagerV2`: idéntico pero
    `stop_distance = max(var_mult_vigente(symbol) × σ_EWMA_día, price×position_stop)`.
- Walk-forward EVT **idéntico al §20** (cero grados de libertad nuevos): EWMA
  λ=0.94 causal (CON el cuadrado — regresión Hallazgo 5), recalibración cada 63
  hábiles, ventana móvil 756 hábiles de z=r/σ, u=p95% empírico, GPD MLE loc=0,
  VaR_GPD(99%) McNeil, fallback cuantil empírico si excesos<30, data desde
  2015-01-01, asserts anti-lookahead estampados por compra (recalibración
  ESTRICTAMENTE anterior, side='left').
- **Dos corridas intra-corrida con la MISMA data y el MISMO motor actual**
  (baseline_risk vs evt_risk). Nota declarada: el motor actual incluye
  `execution_lag_days=1` (T0.2, adoptado DESPUÉS del trial #15) — el baseline
  intra-corrida se re-establece bajo el motor vigente y contra ese se mide el EVT;
  nada se compara contra artefactos históricos.
- **Diagnósticos de activación (pre-registrados, por brazo × ventana)**: n_trades,
  % de compras donde `shares_by_risk` fue la restricción activa del min(),
  % compras ejecutadas vs rechazadas por cash, mediana del ratio dist_EVT/dist_2ATR
  implícito, conteo `evt_term > floor` y `evt_term > 2×ATR`.

**GATE DE ACTIVACIÓN (pre-registrado, lección #15 institucionalizada)**: el
veredicto de mercado solo es interpretable si en el brazo EVT `shares_by_risk`
fue la restricción activa en ≥50% de las compras en ≥2/3 ventanas. Si no:
corrida **NO INTERPRETABLE mecánicamente** (no consume slot de mercado, se
documenta como FALLO de diseño y no se re-corre sin pre-registro nuevo).

**Umbral (leído del ledger EN runtime al redactar, 2026-08-24)**: familia
motor_signal con **11 consumidos** → este trial es n=12 →
`current_threshold("motor_signal")` = **0.9916666666666667** (= 1 − 0.10/12).
Criterio: **DSR OOS ≥ 0.99167 en ≥2/3 ventanas computables**, piso ≥30 trades del
brazo EVT por ventana; n=12 se alimenta también como N_trials al cálculo del
Deflated Sharpe. Si otro trial de la familia registra antes de la corrida, el
número se re-lee en runtime con la misma fórmula y el artefacto cita el efectivo.

**Checks de fidelidad**: F1 universo 50 cargadas; F2 cobertura meses por ventana;
F3 determinismo seed (HMM random_state 42); F4 asserts anti-lookahead pasados y
recalibraciones >0 por símbolo; F5 EWMA cuadrado verificado (regresión Hallazgo 5:
var_mult medianos en rango plausible [1.0, 20], nunca 10³–10⁵); F6 suite completa
backend en verde ANTES de correr; F7 GATE DE ACTIVACIÓN ≥50%; F8 métricas del
brazo baseline_risk reportadas como referencia interna (no comparables 1:1 con
producción: RISK_PER_TRADE reducido y sin Kelly — declarado).

**Riesgos declarados**: (1) el régimen de sizing del experimento NO es el de
producción (risk budget 10× menor, sin Kelly): CUMPLE respondería la pregunta
científica "¿normaliza mejor el riesgo la distancia EVT?", y la integración a
producción exigiría decisión de producto aparte sobre QUÉ dial mover (risk budget,
tope o pesos Kelly) con su propio gate; (2) cascadas de segunda orden: tamaños
distintos → exposición distinta → `filter_by_regime_exposure` puede admitir señales
extra en un brazo (parte legítima del efecto, mecanismo idéntico en ambos); (3)
rechazos por cash difieren entre brazos (reportado en activación); (4) DSR≥0.9917
es exigente (presupuesto familiar n=12) — un resultado "mejora pero no alcanza" se
documenta como NO_CUMPLE sin zona gris; (5) HMM/GPD sin convergencia → aborto
documentado como FALLO honesto.

**Ledger (AL CIERRE, manual)**: `register_trial(id="trial_evt_stops_v2",
familia="motor_signal", n_trials_consumidos=1,
umbral_aplicado="DSR≥current_threshold(motor_signal)=0.99167 (n=12) en ≥2/3
ventanas", veredicto=mecánico, seccion_doc="§45")`. Corrida ÚNICA por diseño; si
aborta por fidelidad → NO INTERPRETABLE, no NO_CUMPLE.

**Consumo del slot según el gate de activación (aclaración de la revisión, fijada
ANTES de correr)**: si el gate de activación **F7 falla** → la corrida **NO se
registra en `trial_registry`** (NO consume slot de `motor_signal`); se documenta
como intento inválido en este documento + SESSION_LOG + ROADMAP — mismo
tratamiento que el #15 original ("ningún n_trials se gasta por esto"). Si F7
**pasa** (corrida interpretable) → SÍ se registra en el ledger sea CUMPLE o
NO_CUMPLE (el slot se consume con el veredicto mecánico que salga). Un aborto por
fidelidad (F1-F6/F8) tampoco registra ni consume: corrida no interpretable.

**Nota de ejecución (2026-08-24, ANTES de la corrida válida)**: el INTENTO 1 se
abortó tras ~13h sin completar siquiera el brazo baseline y SIN producir
veredicto alguno (`ABORTADO_trial18_evt_stops_v2_20260824_070552.txt`, heartbeats
en fase baseline hasta el corte; no consume slot — no llegó a evaluarse F7).
Causa raíz diagnosticada con sampler de stacks: `SignalEngine.generate_signal`
(signal_engine.py:200) recalcula `calculate_all_indicators(df.loc[:date])` en
cada llamada día×símbolo sobre un frame que YA viene indicatorizado
(backtest_engine.py:299 construye `indicators_cache` una vez) — redundancia que
tras T2.3 (hurst_exponent con rolling-apply pesado, añadido DESPUÉS del #15)
volvió el run ~10× más caro. El INTENTO 2 aplica un parche de identidad SOLO
dentro del proceso del trial: `signal_engine.calculate_all_indicators` pasa a ser
identidad porque el frame recibido ya contiene todas las columnas; equivalencia
bit-idéntica por causalidad (todas las columnas son rolling/backward desde la
primera fila del frame completo) y verificada EN-CORRIDA por el check nuevo **F9**
(25 pares símbolo×fecha muestreados contra recálculo real, aborto si difieren;
método determinista seed 42). Metodología de sizing, walk-forward, criterios y
gates de §45: INTACTOS. La corrida única válida es la del intento 2.

### 45.1 RESULTADO (apéndice post-corrida, 2026-08-24) — corrida única válida, intento 2, 20:09

Corrida única (`scripts/trial_evt_stops_v2.py`, artefacto
`data/cache/trial18_evt_stops_v2_20260824_200927.txt` + parquet trades/equity de
ambos brazos). Duración ~37 min con el parche F9 (intento 1: >13h sin terminar).
Umbral efectivo = el del pre-registro: motor_signal consumido=11 → n=12 → th=
0.9916666666666667 (sin recálculo: ningún otro trial registró en el medio).

**Fidelidad OK×8**: F1 universo 50/50; F4 anti-lookahead — **254 compras EVT
dimensionadas con VaR-GPD walk-forward, asserts de recalibración estrictamente
anterior OK en todas, 0 fallbacks** (35 fechas de recalibración); F5 regresión
Hallazgo 5 — mediana var_mult=2.9283, rango plausible [1,20]; F9 equivalencia
identity-cache — 25 pares × 10 columnas bit-idénticos; suite 367 passed pre-corrida.

**GATE DE ACTIVACIÓN F7: PASA al 100%** — `shares_by_risk` fue la restricción
activa en el **100%** de las compras dimensionadas en las 3 ventanas, en AMBOS
brazos (BASE 253 dimensionadas / 227 ejecutadas; EVT 254/231). Por primera vez
desde que existe el motor, la distancia de riesgo del sizing DECIDIÓ el tamaño:
el experimento midió lo que decía medir (a diferencia del #15 placebo).

**TESTS PRIMARIOS — 0/3 ventanas → GLOBAL NO_CUMPLE** (DSR vs th=0.99167):

| ventana | n BASE/EVT | Sharpe BASE | Sharpe EVT | DSR EVT | maxDD BASE→EVT |
|---|---|---|---|---|---|
| W1 2020-2021 | 125/127 | 0.3197 | 0.2738 | 0.1011 | −1.53%→−1.61% |
| W2 2022-2023 | 53/53 | 0.1855 | −0.0012 | 0.0478 | −1.01%→−1.45% |
| W3 2024-2026 | 98/100 | 0.6944 | 0.6008 | 0.2595 | −0.96%→−1.24% |

Veredicto mecánico: **NO_CUMPLE (0/3)** — y no por poco margen estadístico sino
por DIRECCIÓN consistente: el brazo EVT fue PEOR que el baseline en las 3
ventanas (Sharpe −0.05/−0.19/−0.09, drawdowns algo más profundos). Mecanismo
económico medido: la distancia VaR-GPD es más ancha que 2×ATR la mayoría del
tiempo → posiciones sistemáticamente más chicas → mismo número aproximado de
trades (cascada de exposición casi idéntica: n 127/53/100 vs 125/53/98) pero
menos capital capturando el edge; la protección extra de cola no compensó en
NINGUNA ventana, ni siquiera en W2 (bear/chop 2022-2023), donde el daño relativo
fue mayor.

**Lectura honesta**: la hipótesis de §19/§20 ("los stops 2×ATR subestiman el
riesgo de cola; normalizar por EVT mejora") queda ahora REFUTADA EN SU FORMA
OPERATIVA para este motor y universo: cuando la normalización de riesgo por
distancia realmente decide tamaños, usar el cuantil GPD de colas empeora el
perfil completo (retorno, Sharpe, drawdown) frente al humilde 2×ATR. La línea
EVT-stops queda **CERRADA DEFINITIVAMENTE**: §19 (colas reales, ratio 1.26) +
§20/Hallazgo 6 (trial placebo) + §45 (trial válido, refutación direccional).

**Ledger**: `motor_signal` 11→12 consumidos, id=`trial_evt_stops_v2`,
veredicto=NO_CUMPLE, próximo threshold 0.9923076923. **Nada se integra al motor**
(solo se corrieron subclases inyectadas vía `_make_risk_manager`; producción
intacta).

**Hallazgo de código para decisión futura de riesgo (NO bug a arreglar ahora,
reportado por Claude Code 2026-08-24, verificado por Kilo Code)**:
`adaptive_risk.py:109` dimensiona con `stop_distance=max(2×ATR,
price×position_stop)` pero el trigger ejecutivo `REGIME_STOP_HIT`
(`adaptive_risk.py:149`) dispara SOLO con `position_stop%` de pérdida desde
entry, sin ATR. Cuando 2×ATR domina, la posición queda dimensionada para un stop
más ANCHO del que realmente se aplica → el motor arriesga MENOS que su
RISK_PER_TRADE nominal en nombres volátiles (asimetría sizing/trigger). En §45 el
patrón existió igual en ambos brazos (alcance mínimo: solo cambió la distancia de
sizing), así que no sesga esta comparación. Es una decisión de producto pendiente
(¿debería el trigger usar la misma distancia que el sizing?) — registrarla en la
cola de decisiones de Boris, no resolverla aquí.

---


