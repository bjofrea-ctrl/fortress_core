# Plan de mejora matemática — arquitectura, no variables

Consolida: inventario de OpenCode (§1), evaluación crítica de Claude Code (§2),
auditoría académica independiente #1 con 3 bugs de flujo + 1 confirmado de ejecución
(§3), correcciones de auditoría académica independiente #2 (§4), plan de fases
consolidado con cronograma (§5), evidencia post-plan de trial #13 (§6), resultado de
las Fases -1 y 0.5 con gate W2/W3 (§8), rama resultante (§9) y disciplina (§10).

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

---

## 10. Disciplina sin excepción

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
