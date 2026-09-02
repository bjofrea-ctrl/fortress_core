# PILOTO — Regime matching NVDA con features HMM (solo lectura, sin ledger)

**Fecha piloto:** 2026-09-01 (ejecución en worktree `test-opencode-orca`)  
**Restricción dura:** SOLO LECTURA de `backend/data/cache/*.parquet` y código existente. No se recalculan pesos, no hay backtest nuevo, no se toca `ledger`/`trial_registry`, no hay pre-registro. Evidencia exploratoria, NO reemplaza diseño de Cline.  
**Fuente parquet:** `backend/data/cache/*.parquet` (cache OHLCV hasta 2026-08-14 SPY/QQQ/NVDA, 2026-08-17 EFA/GLD/DBC/TIP/TLT/AGG/^VIX). Ver trazabilidad.  
**Fecha "régimen actual" usada:** **2026-08-14** — último dato común donde SPY/QQQ/NVDA tienen close (SPY max 2026-08-14, VIX 14.25). Alternativa 2026-08-17 descartada porque reutilizaría pct_change 60d de SPY/QQQ stale (ffill), documentado en script.  
**Código HMM leído:** `backend/app/core/regime_classifier.py:1-120` (`GlobalRegimeClassifier`, `n_states=4`, `hmm.GaussianHMM full, 200 iter, random_state 42`, `StandardScaler`, allocations 60/15/15/10 etc.).  
**Estado HMM actual:** **No invocable sin entrenar — `is_fitted=False` retorna default GOLDILOCKS**. No existe modelo cacheado `.pkl` de régimen en repo; `audit_regime_hmm.py` existe pero no persiste modelo. Se reutilizan **solo sus features**, no su inferencia (ver §7).

---

## 1. Features HMM extraídos (verbatim)

`regime_classifier.py:34-55` — `_extract_features(price_data)`:

| Grupo | Tickers | Feature code | Fórmula |
|-------|---------|--------------|---------|
| growth | SPY, EFA, QQQ | `growth_SPY`, `growth_EFA`, `growth_QQQ` | `close.pct_change(60)` |
| inflation | GLD, DBC, TIP | `inflation_GLD`, `inflation_DBC`, `inflation_TIP` | `close.pct_change(60)` |
| rates | TLT, AGG | `rates_TLT`, `rates_AGG` | `close.pct_change(60)` |
| vol | VIX (`VIX` o `^VIX`) | `vix_level` | `close` (nivel, sin pct_change) |

- Ventana: **60 trading days** (~3 meses, `pct_change(60)` aritmético, no log).
- Preproceso HMM: `StandardScaler()` sobre matriz completa (`fit_transform(feats.values)`) → z-score muestral completo (μ/σ de toda la muestra). Sin log, sin rank, sin winsorize. `ffill().dropna()` previo.
- Nº estados HMM: 4 (GOLDILOCKS/REFLATION/STAGFLATION/DEFLATION, remapeados por `_align_states` vía medias de equity/bond/commodity).
- Para este piloto se replica **exacta lista de 9 features, misma ventana 60d, mismo VIX level** y misma estandarización muestral completa (μ/σ abajo).

**Qué se reutiliza:** vector 9-d idéntico al que vería el HMM; **qué no se reutiliza:** matriz de transición/means/covars del HMM (no hay modelo entrenado que cargar).

### Parámetros de estandarización (μ, σ muestrales 2015-03-31→2026-08-14, 2863 filas)

| feature | μ | σ |
|---------|-----|-----|
| growth_SPY | +0.03382 | 0.06754 |
| growth_EFA | +0.02059 | 0.07328 |
| growth_QQQ | +0.04675 | 0.08820 |
| inflation_GLD | +0.02822 | 0.07801 |
| inflation_DBC | +0.01867 | 0.09747 |
| inflation_TIP | +0.00569 | 0.02181 |
| rates_TLT | -0.00041 | 0.06620 |
| rates_AGG | +0.00425 | 0.02442 |
| vix_level | +18.39292 | 7.04154 |

*VIX domina en raw (μ~18) pero tras z-score queda isotrópico.*

---

## 2. Métrica de similitud — declarada A PRIORI (antes de ver rankings)

**Métrica elegida: distancia euclídea L2 sobre vector estandarizado (z-score muestral completo).**

```
d(t*, t_actual) = || z(t*) - z(t_actual) ||_2
z_i = (x_i - μ_i) / σ_i   ;   i=1..9
μ_i, σ_i = media/desvío de feature i sobre muestra completa feat_df (2863 días)
x = [growth_SPY, growth_EFA, growth_QQQ, inflation_GLD, inflation_DBC,
     inflation_TIP, rates_TLT, rates_AGG, vix_level]
```

**Justificación a priori (no post-hoc):**
- Replica exactamente el preproceso que alimenta al `GaussianHMM` (`StandardScaler`), por lo que la noción de "cercanía" es la que el HMM asume implícitamente (isotropía gaussiana esférica tras standardize).
- Evita que VIX (escala 10-80) domine a retornos 60d (escala -0.15→+0.20) sin normalizar.
- Euclidiana es la distancia natural bajo covarianza diagonal unitaria; Mahalanobis requeriría estimar Σ 9×9 (inestable, introduce grados de libertad y arbitrariedad de shrinkage) y coseno ignora magnitud (dos regímenes con mismo signo pero distinta intensidad colapsarían — justo lo que queremos distinguir).
- Rolling z-score (μ/σ móvil 252d/500d) se descartó a priori: introduce lookahead si se centra en t_actual, y si se estima solo con pasado de t* no es comparable entre candidatos lejanos en el tiempo. Muestral completo es reproducible y coincide con el `fit` del HMM.

**Descartadas y por qué:** coseno (pierde nivel), Mahalanobis full (Σ ruidosa, overfitting a correlaciones históricas), L1/Manhattan (equivalente cualitativo, no cambia ranking materialmente, se deja como sensibilidad futura).

**Congelada antes de computar:** esta métrica no se cambió tras ver resultados (ver script `/tmp/piloto_regime.py` timestamp y `git status` limpio previo).

---

## 3. Matriz histórica

- **Período:** 2015-03-31 (primera fecha con 60d completos desde 2015-01-02) hasta 2026-08-14 inclusive → **2863 filas** (una por día hábil con ventana completa).
- **Construcción:** para cada fecha t, vector 9-d idéntico al HMM (mismos 8 pct_change 60d + VIX level). `ffill().dropna()` replicado.
- **Estandarización:** `StandardScaler().fit(feat_df.values)` global; `scaled_df` para distancias.
- **Exclusión anti-solape:** se excluyen **60 trading days previos a t_actual** (2026-05-20 → 2026-08-13) más el propio t_actual del ranking. Razón: pct_change 60d solapa ventanas — sin exclusión, el "análogo más cercano" sería trivialmente t-1 (dist ~0.05). Exclusión conservadora, documentada, no post-hoc. Candidatos válidos: **2801 fechas** (2015-03-31 → 2026-05-19).
- **Fecha actual:** 2026-08-14 elegida por ser el último close común SPY/QQQ/NVDA; usar 2026-08-17 habría requerido ffill de SPY/QQQ (stale) y sesgaría pct_change.

---

## 4. Régimen actual — snapshot de features

| feature | raw (pct o VIX) | z (standardized) |
|---------|-----------------|------------------|
| growth_SPY | +6.08% | +0.399 |
| growth_EFA | +8.28% | +0.849 |
| growth_QQQ | +4.33% | -0.040 |
| inflation_GLD | -2.44% | -0.674 |
| inflation_DBC | -5.09% | -0.714 |
| inflation_TIP | -0.02% | -0.268 |
| rates_TLT | -0.02% | +0.002 |
| rates_AGG | +0.87% | +0.181 |
| vix_level | 14.25 | -0.588 |

Lectura: equities moderadamente positivos (EFA > SPY > QQQ), commodities/gold en retroceso suave 60d, rates planos, VIX bajo (percentil ~18 en muestra completa, ver DIAGNOSTICO heterogeneidad). Es un régimen de calma con equities al alza — coherente con GOLDILOCKS nominal pero sin inferencia HMM (modelo no fitted).

NVDA en t_actual: close 225.16, `momentum_12_1 = +24.2%` (pct_change 252d), `momentum_score = 0.494` (clip((24.2+50)/150)), rsi14 ~ no usado aquí. Score por debajo de mediana histórica (0.894).

---

## 5. Ranking de análogos — top-5 y top-10

Distancias euclídeas sobre z-space (9-d). Distribución global: min 0.7405, p5 1.391, p25 2.038, mediana 2.655, p95 6.044, max 12.95, mean 3.02 ±1.50.

**Top-5 más cercanos (k=5 fijo, no elegido post-hoc):**

| rank | fecha análogo | dist L2 | VIX | growth_SPY | growth_QQQ | inflation_GLD | inflation_DBC | rates_TLT | rates_AGG | notas |
|------|---------------|---------|-----|------------|------------|---------------|---------------|-----------|-----------|-------|
| 1 | 2015-04-13 | 0.7405 | 13.94 | +4.56% | +6.70% | -2.40% | -0.57% | -1.68% | +0.47% | Más cercano absoluto (0.04th pctil) |
| 2 | 2015-04-02 | 0.8006 | 14.67 | +3.77% | +5.29% | -1.57% | -2.87% | -0.10% | +0.95% | Cluster abr-2015 |
| 3 | 2017-07-06 | 0.8056 | 12.54 | +2.71% | +3.52% | -2.50% | -7.34% | +2.45% | +0.97% | Verano 2017 calma |
| 4 | 2017-07-17 | 0.8416 | 9.82 | +4.84% | +7.53% | -3.83% | -4.30% | +0.73% | +0.74% | VIX <10 |
| 5 | 2017-07-18 | 0.8610 | 9.89 | +5.23% | +8.28% | -3.43% | -2.94% | +1.61% | +0.94% | Consecutivo |

**Top-10 (k=10 fijo):**

| rank | fecha | dist | VIX | growth_SPY | growth_EFA | growth_QQQ | inflation_GLD | inflation_DBC | rates_TLT |
|------|-------|------|-----|------------|------------|------------|---------------|---------------|-----------|
| 6 | 2017-07-05 | 0.8766 | 11.07 | +3.72% | +7.04% | +4.50% | -2.46% | -6.68% | +3.78% |
| 7 | 2017-05-05 | 0.8861 | 10.57 | +5.02% | +9.77% | +8.95% | -1.00% | -8.48% | -0.17% |
| 8 | 2019-12-10 | 0.8978 | 15.68 | +4.94% | +4.61% | +6.59% | -2.37% | -0.38% | +0.80% |
| 9 | 2015-04-09 | 0.8980 | 13.09 | +3.54% | +11.14% | +5.92% | -3.28% | -0.46% | -1.22% |
| 10 | 2019-12-03 | 0.9010 | 15.96 | +4.29% | +4.42% | +5.56% | -1.61% | +0.26% | -0.87% |

*Features completas en tabla; rates_TIP/AGG omitidos por brevedad pero incluidos en distancia. Todas las distancias <0.91 (~0.3th percentil) — "más cercano" es realmente cercano relativo a distribución (p5=1.39).*

Histograma conceptual: distancias concentradas 1.5–4.0; top-10 cola izquierda extrema. No hay análogos a distancia 0.1–0.3 (no hay gemelo perfecto), pero 0.74 es outlier izquierdo genuino.

---

## 6. Outcome de NVDA en análogos

Definiciones: `momentum_score = clip((momentum_12_1+50)/150, 0,1)` con `momentum_12_1 = pct_change(252)*100` (`indicators.py:381`, `signal_engine.py:137`). `fwd_ret_20d = close.shift(-20)/close -1`, `fwd_ret_60d = close.shift(-60)/close -1` (misma convención que heterogeneidad). Precios split-ajustados en parquet (NVDA split 4:1 2021).

**Base rate incondicional NVDA (toda la muestra con fwd disponible):**
- fwd20: n=2901, **mean +5.12%**, median +4.84%, sd 13.19%, hit>0 66.5%, hit>+5% 49.5%
- fwd60: n=2861, **mean +16.25%**, median +13.97%, sd 25.05%, hit>0 73.8%, hit>+10% 57.7%

NVDA es alcista incondicionalmente en este período (2015-2026).

**Tabla outcome por análogo (top-10):**

| fecha análogo | mom_score en t* | mom_12_1 | close | fwd20 | fwd60 | vs base fwd20 | vs base fwd60 |
|---------------|-----------------|----------|-------|-------|-------|---------------|---------------|
| 2015-04-13 | NaN* | NaN | 0.54 | **-8.51%** | **-12.46%** | -13.6pp | -28.7pp |
| 2015-04-02 | NaN | NaN | 0.51 | +8.02% | -4.02% | +2.9pp | -20.3pp |
| 2017-07-06 | 1.000 | +202.8% | 3.54 | +16.03% | +24.71% | +10.9pp | +8.5pp |
| 2017-07-17 | 1.000 | +213.4% | 4.05 | +2.53% | +15.13% | -2.6pp | -1.1pp |
| 2017-07-18 | 1.000 | +215.1% | 4.09 | +0.61% | +15.15% | -4.5pp | -1.1pp |
| 2017-07-05 | 1.000 | +203.8% | 3.53 | +14.92% | +22.92% | +9.8pp | +6.7pp |
| 2017-05-05 | 1.000 | +199.1% | 2.56 | **+42.66%** | **+58.54%** | +37.5pp | +42.3pp |
| 2019-12-10 | 0.610 | +41.5% | 5.32 | +13.57% | +14.77% | +8.5pp | -1.5pp |
| 2015-04-09 | NaN | NaN | 0.54 | -0.18% | -10.06% | -5.3pp | -26.3pp |
| 2019-12-03 | 0.517 | +27.6% | 5.16 | +15.53% | +33.20% | +10.4pp | +16.9pp |

\*NaN 2015: ventana 252d insuficiente (primeros ~15 meses desde 2015-01-02, mom_12_1 no disponible). No es error de datos; es warmup.

**Agregado:**

| k | n_analogs con mom válido | mean fwd20 | median fwd20 | hit>0 fwd20 | mean fwd60 | median fwd60 | hit>0 fwd60 | vs base mean |
|---|--------------------------|------------|--------------|-------------|------------|--------------|-------------|--------------|
| 5 | 3/5 (2017 only) | **+3.74%** | +2.53% | 4/5=80% | +7.70% | +15.13% | 3/5=60% | fwd20 -1.4pp, fwd60 -8.5pp **peor que base** |
| 10 | 7/10 | **+10.52%** | +10.80% | 8/10=80% | +15.79% | +15.14% | 7/10=70% | fwd20 +5.4pp, fwd60 -0.5pp ≈ base |

**Lectura honesta:** k=5 no predice mejor que azar (peor que base en ambas ventanas); k=10 levemente mejor en 20d (+5.4pp) pero indistinguible de base en 60d y con **n=10 la incertidumbre es enorme** (permutación rápida: p(random 10 >= obs mean 10.5%) ≈0.10 bajo muestreo iid, ignorando autocorrelación — no significativo). El hit rate 80% vs 66.5% base suena mejor pero con n=10 el IC 95% Wilson es 49-94% (cubre base). Ver limitaciones.

**Momentum en análogos vs actual:** análogos 2017 con mom_score 1.0 (saturado alcista, +200% 12-1) muy por encima del actual 0.494; análogos 2019 con 0.52-0.61 similares al actual; 2015 sin dato. Promedio válidos k=10: **0.875** vs actual 0.494 — régimen actual tiene momentum NVDA más moderado que sus "análogos de régimen macro". Esto subraya que **régimen macro similar ≠ momentum idio NVDA similar**.

---

## 7. Qué dice el HMM existente

**`GlobalRegimeClassifier.predict_current_regime` sin estar fitted retorna `{"state":0, "state_name":"GOLDILOCKS", "confidence":0.5, "allocation":{...}}` — default.** (`regime_classifier.py:118-133`).

- `is_fitted=False` al instanciar sin `fit()`; no hay `*.pkl`/`joblib` con `model`+`scaler` persistido en repo (búsqueda `*.pkl`, `*hmm*` solo `audit_regime_hmm.py` de diagnóstico).
- Intentar `predict_current_regime(price_data)` con datos reales pero sin fit devuelve igualmente default (no entrena on-the-fly). Para inferencia real habría que `fit(price_data)` y luego `predict`, pero eso sería **re-entrenar**, fuera del alcance solo-lectura y cambiaría el modelo (no se hace aquí).
- Conclusión documentada: **"HMM no entrenado/cacheado — se usan solo sus features, no su inferencia"**. El piloto no etiqueta t_actual con régimen 0-3; usa distancia continua.

Si se entrenara el HMM (fuera de este piloto), `predict_regime_series_causal` sería la vía sin leakage (vs `predict_regime_series` con leakage de Viterbi).

---

## 8. Stats de distancia global (¿"más cercano" es realmente cercano?)

```
n_candidatos = 2801 (excluidos 60d)
dist    min   p1    p5    p25   median  p75   p90   p95   max    mean  sd
L2     0.740 1.12  1.39  2.04   2.66   3.56  4.60  6.04 12.95  3.02  1.50
```

- Top-1 (0.74) está en **percentil 0.04** — genuinamente cola izquierda, no ruido de muestreo.
- p5=1.39 → top-10 (≤0.90) están todos por debajo de p1 (~1.12), muy por debajo de p5. Son análogos excepcionalmente cercanos en z-space 9-d.
- Aun así, distancia absoluta 0.74 en 9-d con vars=1 equivale a ~0.25σ por dimensión promedio (0.74/√9≈0.25) — no es gemelo idéntico, es "similar".
- No hay cluster a distancia <0.5 ni gap bimodal; distribución unimodal con cola derecha larga (regímenes de stress VIX alto distantes).

---

## 9. Limitaciones honestas (mínimo 8, sin ocultar)

1. **N pequeño y no OOS:** k=5/10 es anecdótico; intervalos de confianza abarcan base rate. No hay validación out-of-sample, walk-forward ni corrección por múltiples comparaciones implícitas (se eligió distancia euclídea a priori, pero k=5/10 y horizonte 20/60d son grados de libertad).
2. **Lookahead en fwd_ret:** `shift(-20/-60)` usa futuro; correcto para describir "qué pasó después" pero solapa ventanas y no es tradeable sin lag de ejecución. No se corrige por overlap (autocorrelación de fwd).
3. **Univariado NVDA, sin causalidad régimen→retorno:** correlación macro→idio no implica causalidad; momentum NVDA en análogos está dominado por ciclo propio (2017 bull run) no por régimen SPY/VIX. Confusión con factor común (e.g., tasa).
4. **Muestral completo para μ/σ (leakage sutil):** estandarización usa toda la muestra incluyendo futuro de cada t* (imposible en vivo). Rolling μ/σ sería más causal pero introduce arbitrariedad de ventana y no replica el HMM. Sesgo pequeño pero real.
5. **Exclusión 60d conservadora pero arbitraria:** sin exclusión, análogos serían t-1..t-60 triviales; con 60d se pierde potencial análogo genuino dentro de 60d (e.g., evento de 30d atrás). Sensibilidad no explorada.
6. **Ventana 60d pct_change fija:** 60d es la del HMM, no validada para matching; régimen podría definirse mejor con vol 20d/100d, Hurst, pendiente de curva, etc. (indicators.py tiene hurst_exponent/realized_vol_regime no usados aquí).
7. **Estandarización ignora correlación:** Euclidiana en z-space asume Σ=I; features están correlacionadas (SPY-QQQ ρ~0.9, TLT-AGG, etc.) — Mahalanobis daría distancias distintas. No se explora.
8. **NVDA precios split-ajustados y microestructura:** fwd_ret crudo no descuenta dividendos/splits futuros (parquet ya ajustado, correcto), pero no considera costos, slippage, ni que 2015 precios ~0.5 (liquidez distinta, régimen de NVDA pre-AI).
9. **Warmup momentum_score NaN:** 3/10 análogos sin score (2015) — se excluyen del promedio, reduciendo n efectivo y sesgando hacia 2017/2019 (supervivencia de muestra larga).
10. **No replicar HMM completo = no etiquetar régimen:** sin inferencia HMM no se puede afirmar "t_actual es GOLDILOCKS"; distancia continua es proxy, no clasificación discreta con incertidumbre de transición.
11. **Estacionariedad dudosa:** 2015-2026 incluye cambios estructurales (QE/QT, COVID, AI boom); distancia euclídea asume métrica estacionaria — análogo de 2015 puede ser "cerca" en z pero lejos en contexto estructural.

---

## 10. Veredicto — ¿tiene jugo "emparejamiento de régimen"?

**Evidencia mixta, débil, no concluyente — no justifica por sí sola reemplazar/complementar el gate de régimen actual sin trabajo adicional.**

- A favor: existen análogos macro a distancia genuinamente pequeña (0.74-0.90, <p1), no todos los días son equidistantes; régimen actual es identificable como "calma alcista con VIX bajo" y tiene precedentes con outcomes NVDA dispares pero en promedio no peores que base en 60d.
- En contra: outcome NVDA en análogos es **heterogéneo y no mejor que base rate** (k=5 peor, k=10 ~ base; p≈0.10). Momentum NVDA en análogos (0.875) ≠ actual (0.494) — el matching macro no captura estado idio. N=10 insuficiente; sin OOS ni test formal (e.g., permutation con bloques, BH).

**Implicación práctica:** matching de régimen continuo podría ser feature adicional (e.g., distancia al centroide de cada estado HMM, o kNN ponderado) pero requiere diseño pre-registrado con métrica congelada, validación walk-forward causal, corrección por overlap y costos, y prueba de que aporta IC incremental sobre momentum_score/rsi_score (que ya tienen IC pooled 0.06/0.03). Este piloto **NO** es ese diseño — es solo lectura exploratoria que muestra que la idea no es absurda (hay análogos cercanos) pero tampoco es predictiva obvia.

**No se duplica diseño de Cline:** Cline propone matching explicito para gates; este piloto solo describe similitud y outcome histórico, sin proponer umbral, gate ni backtest.

---

## 11. Trazabilidad

- **Código leído:** `backend/app/core/regime_classifier.py:1-210` (bat, completo), `backend/app/core/signal_engine.py:120-165` (momentum_score), `backend/app/core/indicators.py:370-385` (momentum_12_1), `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (definiciones fwd_ret).
- **Parquet fuente (solo lectura):** `backend/data/cache/SPY.parquet` (2921, 2015-01-02→2026-08-14), `EFA.parquet` (2922→2026-08-17), `QQQ.parquet` (2921), `GLD.parquet`, `DBC.parquet`, `TIP.parquet`, `TLT.parquet`, `AGG.parquet`, `^VIX.parquet` (2923, close 14.25 en 2026-08-14), `NVDA.parquet` (2921, close 225.16). Verificados con `python3 -c pd.read_parquet` (no modificados, `git status` clean).
- **Scripts efímeros (no trackeados, en /tmp):** `/tmp/piloto_regime.py` (matriz, scaler, distancias), `/tmp/piloto_nvda.py` (fwd_ret, base rate), `/tmp/piloto_extra.py` (scaler params, HMM invocabilidad), `/tmp/piloto_extra2.py`, `/tmp/piloto_extra3.py`, `/tmp/check_feat_detail.py` (estandarizados). Todos solo-lectura, salidas en `/tmp/distances.csv`, `/tmp/feat_df.csv`, `/tmp/dists.npy` (no en repo).
- **Verificación:** `git status --short` limpio antes y después de cálculos (solo nuevo `.md` untracked), `git log --oneline -3` registra diagnósticos previos d199899/9fadb18, `eza backend/data/cache/*.parquet` confirma no escritura. `rg "momentum_score"` y `rg "fwd_ret"` en diagnósticos para definiciones.
- **Métrica congelada:** euclídea estandarizada declarada en §2 antes de `np.linalg.norm` — no se probaron alternativas post-hoc.

---

*Piloto solo-lectura — no ledger, no trial_registry, no pre-registro. Próximo paso si se quiere rigor: pre-registrar gate kNN (k, umbral dist, horizonte, scoring) y validar OOS walk-forward con `predict_regime_series_causal` + costos.*

