# Verificación de Premisas I4 — Escenario 102 (GLM) y Heterogeneidad bajo Gates

**Fecha**: 2026-09-02 10:30-12:00
**Régimen**: capa-1 descriptiva, sin ledger, sin slot — mismo que ATLAS. Solo lectura `backend/data/cache/*.parquet`, no diseña shrinkage todavía.
**Origen**: dos premisas baratas antes de diseñar I4 (shrinkage jerárquico).

---

## 1. Premisa del Escenario 102 (GLM): pass-rate constante al pasar de 50 a 102

**Premisa GLM MDE**: el cálculo de MDE asume que el pass-rate de los gates del motor (`trend/adx/vol` de `signal_engine.py:158-170`) se mantiene constante al pasar de 50 a 102 símbolos, de modo que `N_eff` escala 6→12 (doble universo → doble `n` eligible, MDE se reduce ~√2).

**Método**: `SignalEngine.compute_factor_frame` sobre el universo completo (misma implementación del motor, sin BMA ni régimen). `eligible = trend_ok & (adx>=20) & (rsi>40 & rsi<75) & (vol_ratio>=1.0)` donde `trend_ok = close>ema50>ema200`. Cálculo diario 2019-01-01→2026-08-04 (1907 ruedas) y también sobre panel stride 5d (38859 filas 102, 19045 filas 50, horizonte 20d). Dos universos: 50 originales (7 base + 43 NEW_UNIVERSE[:43]) vs 102 ampliado (7+95). `load_universe` desde `2018-01-01` para warmup 200d. Script `/tmp/verif_light.py`.

**Resultado crudo**:

| Universo | Pass-rate diario (eligible/día) | Per-symbol mean | Panel eligible (stride 5d) | N filas eligible (stride) |
|----------|-------------------------------|-----------------|----------------------------|---------------------------|
| **50** | **10.86%** (1907 días) per-sym mean 10.86% median 11.09% | 10.86% | **10.90%** (2076/19045) | 2076 |
| **102** | **10.30%** (1907 días) per-sym mean 10.30% median 10.43% | 10.30% | **10.30%** (4001/38859) | 4001 |
| **Δ** | **-0.55pp** | -0.56pp | -0.60pp | **ratio 1.93×** |

**Lectura**:

- **Pass-rate casi constante**: cae 0.55pp (10.86%→10.30%), diferencia <1pp absoluta, <5% relativa. A fines de MDE es indistinguible de constante. La dispersión por símbolo (mean vs median) también se mantiene (10.86% vs 10.30% mean, 11.09% vs 10.43% median).
- **N_eff escala 1.93×, no 2.00×**: 2076→4001 filas eligible stride. El GLM asumía 6→12 (2.00×). La pérdida de 0.07× (3.5%) es exactamente el drop de pass-rate (10.30/10.86 = 0.948). `N_eff` real ≈ 11.6 en vez de 12. **Error <5%**, irrelevante para MDE (MDE ∝ 1/√N, error en MDE ≈2%). No invalida la estimación.
- **Por qué cae levemente**: los 52 small/mid añadidos tienen pass-rate marginalmente menor (small caps más volátiles → `volume_ratio>=1.0` y `trend` más exigente). No es un quiebre estructural.

**Veredicto premisa 102**: **Se sostiene**. El N_eff GLM 6→12 está bien estimado; corregir a 11.6 no cambia decisión. No hace falta recalibrar MDE.

**Limitaciones**:

- Cálculo con `eligible` de `compute_factor_frame` (gates duros) — no incluye `overall>=0.60` ni `regime_state==3` ni `MIN_RR 1.5` ni `filter_by_regime_exposure` (cap 10% por régimen). El pass-rate operativo real (señales rankeadas y filtradas por exposición) es menor (~1-2 señales/día), pero cae proporcionalmente en ambos universos; la constancia relativa se mantiene.
- Warmup 2018-01-01, no 2015 — los primeros 200 días de 2019 se descartan por `calculate_all_indicators` dropna; el denominador es 1907 días, no 2520. No afecta comparativa 50 vs 102.
- No se midió por régimen (0-3); el pass-rate podría caer más en régimen 3 (donde `regime_state==3` bloquea todo) pero ese bloqueo es independiente del universo.

---

## 2. Premisa de I4: heterogeneidad pooled +0.06 vs mediana -0.074 SIN gates → ¿se mantiene CON gates?

**Hallazgo previo** (ayer, sin gates, raw, 102, horizonte fwd_20d, universo completo, sin filtrar por `eligible`): pooled IC momentum ≈ +0.06, mediana per-ticker ≈ -0.074 (signo invertido, heterogeneidad fuerte). Se midió SIN `eligible` (todos los días).

**Re-medición CON gate**: mismo universo 102, mismo horizonte 20d, mismo `momentum = ((mom_12_1+50)/150).clip(0,1)` de `compute_factor_frame`, mismo stride 5d, pero solo sobre días `eligible==True` (los que el motor realmente opera). Pooled vs mediana per-ticker, `SignalQualityMetrics.compute_ic` (Pearson).

**Resultado 102 (n stride)**:

| Población | n filas | pooled IC (Pearson) | rank IC | mediana per-ticker | mean per-ticker | 10pct | 90pct | Heterogeneidad (pooled - median) |
|-----------|---------|---------------------|---------|-------------------|-----------------|-------|-------|----------------------------------|
| **RAW (sin gate)** | 38859 (100%) | **-0.0286** -0.0228 rank | **-0.0785** | -0.0790 | -0.1795 | +0.0137 | **+0.0499** (mediana más negativa) |
| **GATED (eligible)** | 4001 (10.3%) | **+0.0319** | **-0.0344** | -0.0421 | -0.14 | +0.08 | **+0.0663** |

**Resultado 50 para referencia**:

| Población 50 | n | pooled | median | 
|--------------|---|--------|--------|
| RAW | 19045 | -0.0183 | -0.0830 |
| GATED | 2076 (10.9%) | +0.0319 | -0.0483 |

**Lectura**:

- **RAW 102 NO replica el +0.06 previo**: pooled RAW es **-0.0286** (negativo), no +0.06. La discrepancia se debe a diferencias metodológicas: el +0.06 previo se midió sobre universo y ventana ligeramente distintos (posiblemente 2019-2024, 50 símbolos, momentum sin normalizar, o con `expected_sign` invertido), o sobre `fcf_yield`-like. Nuestra re-medición RAW con `compute_factor_frame` 2019-2026-08-04 stride 5d da pooled levemente negativo. **No se puede afirmar que el +0.06 se sostiene** con la definición actual del motor. La heterogeneidad, sin embargo, **sí se sostiene**: pooled (-0.0286) vs median (-0.0785) diff +0.0499, mediana más negativa que pooled, 10pct -0.179 vs 90pct +0.013 (dispersión amplia).
- **GATED SÍ muestra signo invertido** (pooled +0.0319 >0, mediana -0.0344 <0) con diff +0.0663 — más heterogéneo que RAW. El pooled pasa de -0.0286 (RAW) a +0.0319 (GATED) al filtrar por `eligible`, mientras la mediana pasa de -0.0785 a -0.0344 (menos negativa pero sigue negativa). El gate **no elimina la heterogeneidad; la idea de I4 (shrinkage jerárquico) se mantiene** — pooled no representa a la mediana.
- **¿Se mantiene el "signo invertido" bajo gates?** En nuestra métrica, **SÍ bajo gates** (pooled positivo, mediana negativa), pero **NO en RAW** (ambos negativos). Si la premisa original era "signo invertido sin gates", no se replica con esta definición; si la premisa es "heterogeneidad y signo invertido pueden aparecer", se confirma bajo gates. La variación es que el gate cambia el signo del pooled.
- **50 vs 102**: la heterogeneidad es similar en ambos universos (50 RAW pooled -0.0183 median -0.0830 diff +0.0647; 102 RAW diff +0.0499). No es artefacto de los 52 nuevos.

**¿Por qué el gate invierte el pooled?**

El gate `eligible` selecciona días con tendencia alcista (`close>ema50>ema200`), `adx>=20`, `rsi 40-75` y `volume_ratio>=1.0`. Esos días están sesgados a momentum moderado-alto (q33/q66 momentum 48/140 en 10y). Filtrar por tendencia elimina colas de momentum muy bajo donde el IC es más negativo, elevando el pooled. La mediana per-ticker sigue negativa porque muchos small caps (EPAM, QLYS) tienen IC negativo incluso en días eligible.

**Implicancia para I4**:

- **Sí, hay heterogeneidad bajo gates**: mediana per-ticker sigue desplazada -6 a -7pp respecto al pooled, incluso cuando pooled se vuelve positivo. Un modelo pooled (shrinkage total) sesgaría a los tickers medianos. Shrinkage jerárquico (parcial pooling por ticker) sigue justificado.
- **El signo del pooled no es robusto**: cambia de -0.028 (RAW) a +0.032 (GATED) solo por filtrar 10% de días. Cualquier shrinkage que use pooled como prior es frágil al gate. Hay que shrinkar hacia **mediana per-ticker o hacia prior 0**, no hacia pooled.
- **No es solo "mediana = -0.074"**: nuestra mediana RAW es -0.0785 (coincide con -0.074 previo), pero pooled difiere. El hallazgo de mediana negativa se replica; el de pooled +0.06 no.

**Limitaciones honestas**:

- **Definición de momentum**: usamos `momentum = ((mom_12_1+50)/150).clip(0,1)` de `compute_factor_frame`, no `mom_12_1` crudo. Si el hallazgo previo usó crudo, el signo puede diferir. No se probó rsi ni trend como placebo.
- **Horizonte y stride**: solo 20d y stride 5d (igual que `build_factor_panel`). 60d o stride diario darían otra heterogeneidad (ayer se vio que 60d anticipa reversión). No se exploró.
- **n efectivo**: GATED n=4001 (102) y 2076 (50) → IC con ~4000 puntos, no 38859. El `n_eff` real con solapamiento 20d/stride 5 es menor (≈ 4001 * 5/20 ≈ 1000). El IC +0.0319 no es significativo con `thresh = 2/√n_eff ≈ 0.06`. Tanto pooled como mediana están **dentro del ruido** (|IC|<0.08). La heterogeneidad es descriptiva, no confirmatoria.
- **Solo momentum**: no se midió rsi, adx, volume_shock bajo gates; la heterogeneidad podría ser distinta por factor.
- **No se midió por régimen**: el gate `eligible` ya depende de régimen implícito (trend/adx), pero no se estratificó por `regime_state` 0-3. La heterogeneidad podría concentrarse en régimen 1 vs 2.

---

## 3. Qué sigue y qué no

- **No diseñar shrinkage todavía** — este es solo el chequeo previo pedido.
- Si se decide I4, **pre-registrar** con: universo 102, gate `eligible` (definición `signal_engine.py:170`), horizonte 20d, stride 5d, métrica IC pooled vs mediana per-ticker, y prior de shrinkage hacia mediana o 0 (no hacia pooled). El MDE del escenario 102 puede usar N_eff 11.6 sin corrección.
- **Artefactos**: `/tmp/verif_light.py`, `/tmp/verif_light_raw.txt` (logs con `load_universe` 102/50), este archivo. Solo lectura parquet, sin escritura de ledger ni slot.

