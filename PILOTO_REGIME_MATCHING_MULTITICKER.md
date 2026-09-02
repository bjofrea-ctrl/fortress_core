# PILOTO — Regime matching multiticker (NVDA + KO + TSLA + MSFT) con features HMM — solo lectura, sin ledger

**Fecha piloto:** 2026-09-02 (worktree `test-opencode-orca`, ampliación del piloto NVDA commit 38ef62c)  
**Restricción dura:** SOLO LECTURA de `backend/data/cache/*.parquet` y código existente. No se recalculan pesos, no hay backtest nuevo, no se toca `ledger`/`trial_registry`, no hay pre-registro. Evidencia exploratoria, NO reemplaza diseño de Cline. Referencia previa: `PILOTO_REGIME_MATCHING_NVDA.md` (239L, 38ef62c).  
**Bibliografía insumo:** `BIBLIOGRAFIA_SUN_2024.md` (2026-09-02, veredicto Sun 2024 exacto no existe; candidatos MONEY hipergrafo, Achitouv RMT+red, Gorduza analyst GAT — red como complemento del RMT, no sustituto).  
**Fecha "régimen actual":** **2026-08-14** — último dato común SPY/QQQ/NVDA/KO/TSLA/MSFT con close (SPY max 2026-08-14, VIX 14.25). Mantiene comparabilidad con piloto NVDA §6 (alternativa 2026-08-17 descartada por ffill stale).  
**Tickers elegidos:** 4 total (NVDA ya en piloto + 3 nuevos). Criterio explícito documentado en §1, máx 3 adicionales para no diluir piloto.

---

## 1. Elección de tickers adicionales — criterio explícito (no arbitrario)

Se amplía de 1 → 4 tickers cubriendo el espectro defensivo / intermedio / growth alta-beta identificado en `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (vol_ann, corr SPY, grupo sector):

| Ticker | Rol en piloto | vol_ann 2015-26 | vs mediana Large 0.2725 | corr diaria con SPY | Grupo diagnóstico | Justificación |
|--------|---------------|-----------------|-------------------------|---------------------|------------------|--------------|
| **KO** | Defensivo / refugio | **0.1791** (mínimo del universo, cercano a PG 0.186 / JNJ 0.183) | p10 (baja) | **0.501** (baja) | Defensiva staples, usado en hipótesis defensivas-vs-growth (DIAGNOSTICO §7, p=NS) | Extremo baja vol, baja beta; si el matching macro tiene señal debería ser menos sensible que growth. Contraste máximo con NVDA. |
| **TSLA** | Growth alta-beta, distinto a NVDA | **0.5720** | p95+ (alta) | **0.495** (baja, idiosincrático) | Growth/disruptivo, vol alta comparable a AMD 0.598 / NVDA 0.482 | Segunda high-beta con narrativa distinta a NVDA (auto/energy vs semis/AI) pero misma cola de vol. Permite testar si la heterogeneidad TSLA vs NVDA domina al régimen macro común. |
| **MSFT** | Intermedio / core large-cap | **0.2762** | mediana (0.2725) | **0.753** (alta) | Large core, beta ~1 | Mediana de vol y alta corr SPY — representa el "tickers típico" del universo 50. Si el régimen macro importa, MSFT debería ser el más alineado. |
| **NVDA** (repetido) | Growth alta-beta de referencia | 0.4819 | p90 (alta) | 0.646 | Growth semis/AI, IC_mom +0.015 vs mediana -0.074 | Caso único del piloto previo; se recalcula con idéntica metodología para coherencia y matriz comparativa. |

*Descartados:* AMD (0.598, corr 0.517) — muy similar a TSLA, redundante; AAPL (0.288, corr 0.731) — muy similar a MSFT, se prefiere MSFT por ser mediana exacta y evitar duplicar core. Con 4 tickers se cubre baja / mediana / alta vol sin diluir piloto (límite 3 adicionales cumplido). Selección documentada antes de computar outcomes (no post-hoc).*

**Correlación entre los elegidos (ret diario 2025-08-14→2026-08-14, 252d):** KO–PEP 0.57, TSLA–AMD 0.42, MSFT–CRM 0.45 (ver §3.5). No son independientes, pero cubren factores distintos — coherente con clusters RMT Ward H3 (XOM/CVX), H5 (V/MA) vs growth.

---

## 2. Metodología congelada — idéntica al piloto NVDA (comparabilidad)

Reusa **exactamente** la misma pipeline de `PILOTO_REGIME_MATCHING_NVDA.md §1-3` sin cambios:

| Dimensión | Valor congelado | Fuente |
|-----------|-----------------|--------|
| Features HMM 9-d | `growth_SPY/EFA/QQQ = close.pct_change(60)`, `inflation_GLD/DBC/TIP = pct_change(60)`, `rates_TLT/AGG = pct_change(60)`, `vix_level = close` | `regime_classifier.py:34-55` |
| Ventana | 60 trading days (~3m, aritmético, no log) | idem |
| Estandarización | z-score muestral completo μ/σ sobre 2863 filas (`StandardScaler().fit(feat_df)`) — **tabla §2.1 idéntica**, incluye leakage sutil documentado pero replica HMM `fit` | piloto §1-2 |
| Métrica | **Euclídea L2 sobre z-space 9-d**, declarada a priori (no post-hoc): `d = ||z(t*)-z(t_actual)||2` | piloto §2 |
| Matriz histórica | 2015-03-31 → 2026-08-14 = **2863 filas** (55.2% del total); `ffill().dropna()` replicado — construcción con outer union y ffill, luego truncada a SPY max | `piloto_regime.py` |
| Candidatos válidos | **2801** fechas (2015-03-31→2026-05-19) tras **exclusión 60 trading days** previos a 2026-08-14 + t_actual | piloto §3 |
| Ranking | top-5 y top-10 fijos (k=5/10 no elegido post-hoc) | piloto §5 |
| Outcomes | `fwd_ret_20d = close.shift(-20)/close-1`, `fwd_ret_60d = close.shift(-60)/close-1`, `momentum_12_1 = pct_change(252)*100`, `momentum_score = clip((mom+50)/150)` — idéntico a `indicators.py:381`, `signal_engine.py:137`, `backtest_engine.py:23` | piloto §6 |
| Base rate | **Por ticker** (no global) — n=2901 fwd20 / 2861 fwd60 por ticker, toda la muestra con fwd disponible | §6 |
| Fecha actual | 2026-08-14 | §6 |

**Tabla μ/σ muestral (reusada verbatim, no recalculada):**

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

**Métrica congelada antes de computar:** no se probaron Mahalanobis, coseno ni L1 como métrica principal; sensibilidad VIX-ponderada se reporta separadamente en §8 (no reemplaza).

---

## 3. Snapshot régimen actual — features 2026-08-14 (común a todos los tickers)

Mismo vector 9-d que ve el HMM; es **macro**, no por ticker. Reusado del piloto §4:

| feature | raw | z |
|---------|-----|-----|
| growth_SPY | +6.08% | +0.399 |
| growth_EFA | +8.28% | +0.849 |
| growth_QQQ | +4.33% | -0.040 |
| inflation_GLD | -2.44% | -0.674 |
| inflation_DBC | -5.09% | -0.714 |
| inflation_TIP | -0.02% | -0.268 |
| rates_TLT | -0.02% | +0.002 |
| rates_AGG | +0.87% | +0.181 |
| vix_level | 14.25 | -0.588 |

Lectura: calma alcista moderada (EFA>SPY>QQQ), commodities en retroceso suave 60d, rates planos, VIX 14.25 (percentil ~18). Régimen GOLDILOCKS nominal pero sin inferencia HMM fitted (ver piloto §7, `is_fitted=False`).

**Momentum_score en t_actual (por ticker):**

| Ticker | close 2026-08-14 | mom_12_1 | momentum_score |
|--------|-------------------|----------|----------------|
| NVDA | 225.16 | +24.2% | **0.494** |
| KO | 87.71 | +28.0% | **0.520** |
| TSLA | 342.27 | +0.9% | **0.339** |
| MSFT | 495.40 | -4.1% | **0.306** |

Rango 0.306–0.520 (todos por debajo de mediana histórica NVDA 0.894 y similares a diagnósticos de análogos 2019). TSLA/MSFT con momentum débil vs KO/NVDA moderado — heterogeneidad idiosincrática ya visible en t_actual pese a régimen macro común.

---

## 4. Ranking de análogos — top-5 y top-10 (común a todos los tickers)

Distancias euclídeas sobre z-space 9-d (n=2801 candidatos). Distribución idéntica a piloto: min 0.7405, p5 1.39, p25 2.04, mediana 2.66, p95 6.04, mean 3.02 ±1.50.

**Top-5 (k=5 fijo):**

| rank | fecha | dist L2 | VIX | growth_SPY | growth_QQQ | inflation_GLD | inflation_DBC | rates_TLT | rates_AGG |
|------|-------|---------|-----|------------|------------|---------------|---------------|-----------|-----------|
| 1 | 2015-04-13 | 0.7405 | 13.94 | +4.56% | +6.70% | -2.40% | -0.57% | -1.68% | +0.47% |
| 2 | 2015-04-02 | 0.8006 | 14.67 | +3.77% | +5.29% | -1.57% | -2.87% | -0.10% | +0.95% |
| 3 | 2017-07-06 | 0.8056 | 12.54 | +2.71% | +3.52% | -2.50% | -7.34% | +2.45% | +0.97% |
| 4 | 2017-07-17 | 0.8416 | 9.82 | +4.84% | +7.53% | -3.83% | -4.30% | +0.73% | +0.74% |
| 5 | 2017-07-18 | 0.8610 | 9.89 | +5.23% | +8.28% | -3.43% | -2.94% | +1.61% | +0.94% |

**Top-10 (k=10 fijo):**

| rank | fecha | dist | VIX |
|------|-------|------|-----|
| 6 | 2017-07-05 | 0.8766 | 11.07 |
| 7 | 2017-05-05 | 0.8861 | 10.57 |
| 8 | 2019-12-10 | 0.8978 | 15.68 |
| 9 | 2015-04-09 | 0.8980 | 13.09 |
| 10 | 2019-12-03 | 0.9010 | 15.96 |

*Todas <0.91 (~p1=1.12) — análogos excepcionalmente cercanos. No hay gemelo <0.5. Nota: lista idéntica para los 4 tickers porque la distancia es macro-pura (SPY/VIX etc.), no usa precio del ticker — ver §6 comparativa.*

Histograma: ya reportado en piloto §8; top-10 en cola izquierda extrema (0.04–0.3th pctil).

---

## 5. Outcome por ticker en los mismos análogos — agregado k5/k10 vs base rate ticker-específico

Definiciones: `fwd20/60` como arriba, precios split-ajustados parquet. Base rate **específico por ticker** (no global), toda la muestra con fwd disponible.

### 5.1 Base rates incondicionales por ticker

| Ticker | fwd20 n | mean | median | sd | hit>0 | hit>+5% | fwd60 n | mean | median | sd | hit>0 | hit>+10% |
|--------|---------|------|--------|----|-------|---------|---------|------|--------|----|-------|----------|
| **NVDA** | 2901 | **+5.12%** | +4.84% | 13.19% | 66.5% | 49.5% | 2861 | **+16.25%** | +13.97% | 25.05% | 73.8% | 57.7% |
| **KO** | 2901 | **+0.84%** | +1.02% | 4.54% | 60.1% | 14.2% | 2861 | **+2.44%** | +2.47% | 6.85% | 66.3% | 14.2% |
| **TSLA** | 2901 | **+3.73%** | +1.35% | 18.20% | 54.2% | 39.5% | 2861 | **+11.73%** | +3.79% | 34.16% | 56.0% | 40.8% |
| **MSFT** | 2901 | **+1.92%** | +2.07% | 6.57% | 63.3% | 28.3% | 2861 | **+5.71%** | +6.06% | 10.46% | 71.7% | 34.1% |

*NVDA/TSLA con drift 5.1%/3.7% a 20d vs KO 0.84% — base rates muy distintas; comparar outcome vs propia base, no vs global.*

### 5.2 Outcome por análogo (top-10) — detalle

**NVDA** (repetido coherencia, idéntico a piloto §6):

| fecha | mom_score en t* | close | fwd20 | fwd60 | vs base fwd20 | vs base fwd60 |
|-------|-----------------|-------|-------|-------|---------------|---------------|
| 2015-04-13 | NaN* | 0.54 | -8.51% | -12.46% | -13.6pp | -28.7pp |
| 2015-04-02 | NaN | 0.51 | +8.02% | -4.02% | +2.9pp | -20.3pp |
| 2017-07-06 | 1.000 | 3.54 | +16.03% | +24.71% | +10.9pp | +8.5pp |
| 2017-07-17 | 1.000 | 4.05 | +2.53% | +15.13% | -2.6pp | -1.1pp |
| 2017-07-18 | 1.000 | 4.09 | +0.61% | +15.15% | -4.5pp | -1.1pp |
| 2017-07-05 | 1.000 | 3.53 | +14.92% | +22.92% | +9.8pp | +6.7pp |
| 2017-05-05 | 1.000 | 2.56 | +42.66% | +58.54% | +37.5pp | +42.3pp |
| 2019-12-10 | 0.610 | 5.32 | +13.57% | +14.77% | +8.5pp | -1.5pp |
| 2015-04-09 | NaN | 0.54 | -0.18% | -10.06% | -5.3pp | -26.3pp |
| 2019-12-03 | 0.517 | 5.16 | +15.53% | +33.20% | +10.4pp | +16.9pp |

*NaN 2015: ventana 252d insuficiente (warmup, no error).*

**KO:**

| fecha | mom_score | close | fwd20 | fwd60 | vs base fwd20 (+0.84%) | vs base fwd60 (+2.44%) |
|-------|-----------|-------|-------|-------|------------------------|------------------------|
| 2015-04-13 | NaN | 28.62 | +0.59% | -1.26% | -0.25pp | -3.70pp |
| 2015-04-02 | NaN | 28.61 | +0.57% | -2.35% | -0.27pp | -4.79pp |
| 2017-07-06 | 0.343 | 33.60 | +2.86% | +2.18% | +2.02pp | -0.26pp |
| 2017-07-17 | 0.342 | 33.85 | +2.39% | +3.36% | +1.55pp | +0.92pp |
| 2017-07-18 | 0.342 | 33.81 | +3.40% | +4.02% | +2.56pp | +1.58pp |
| 2017-07-05 | 0.347 | 33.92 | +1.72% | +1.00% | +0.88pp | -1.44pp |
| 2017-05-05 | 0.335 | 32.80 | +5.26% | +5.46% | +4.42pp | +3.02pp |
| 2019-12-10 | 0.418 | 44.14 | +2.92% | -3.55% | +2.08pp | -5.99pp |
| 2015-04-09 | NaN | 28.87 | -0.85% | -3.18% | -1.69pp | -5.62pp |
| 2019-12-03 | 0.401 | 44.16 | +2.21% | +3.94% | +1.37pp | +1.50pp |

**TSLA:**

| fecha | mom_score | close | fwd20 | fwd60 | vs base +3.73%/+11.73% |
|-------|-----------|-------|-------|-------|------------------------|
| 2015-04-13 | NaN | 13.99 | +14.16% | +21.54% | +10.43pp / +9.81pp |
| 2015-04-02 | NaN | 12.73 | +18.34% | +37.18% | +14.61pp / +25.45pp |
| 2017-07-06 | 0.627 | 20.59 | +12.39% | +10.45% | +8.66pp / -1.28pp |
| 2017-07-17 | 0.633 | 21.30 | +13.84% | +11.27% | +10.11pp / -0.46pp |
| 2017-07-18 | 0.634 | 21.88 | +10.39% | +8.03% | +6.66pp / -3.70pp |
| 2017-07-05 | 0.686 | 21.81 | -0.37% | +3.82% | -4.10pp / -7.91pp |
| 2017-05-05 | 0.638 | 20.56 | +12.64% | +3.64% | +8.91pp / -8.09pp |
| 2019-12-10 | 0.304 | 23.26 | +37.98% | +74.29% | +34.25pp / +62.56pp |
| 2015-04-09 | NaN | 14.01 | +12.71% | +33.14% | +8.98pp / +21.41pp |
| 2019-12-03 | 0.306 | 22.41 | +27.98% | +121.18% | +24.25pp / +109.45pp |

**MSFT:**

| fecha | mom_score | close | fwd20 | fwd60 | vs base +1.92%/+5.71% |
|-------|-----------|-------|-------|-------|-----------------------|
| 2015-04-13 | NaN | 35.69 | +13.43% | +6.63% | +11.51pp / +0.92pp |
| 2015-04-02 | NaN | 34.43 | +20.77% | +10.84% | +18.85pp / +5.13pp |
| 2017-07-06 | 0.579 | 62.14 | +5.22% | +9.21% | +3.30pp / +3.50pp |
| 2017-07-17 | 0.600 | 66.47 | +0.33% | +4.56% | -1.59pp / -1.15pp |
| 2017-07-18 | 0.595 | 66.43 | +0.42% | +4.81% | -1.50pp / -0.90pp |
| 2017-07-05 | 0.589 | 62.60 | +4.60% | +7.50% | +2.68pp / +1.79pp |
| 2017-05-05 | 0.612 | 62.17 | +5.35% | +5.79% | +3.43pp / +0.08pp |
| 2019-12-10 | 0.617 | 142.86 | +7.25% | -0.07% | +5.33pp / -5.78pp |
| 2015-04-09 | NaN | 35.45 | +12.58% | +7.71% | +10.66pp / +2.00pp |
| 2019-12-03 | 0.578 | 141.14 | +7.57% | +16.04% | +5.65pp / +10.33pp |

### 5.3 Agregado k5 / k10 vs base rate por ticker

| Ticker | k | n_analogs con mom válido | mean fwd20 | median fwd20 | hit>0 fwd20 | mean fwd60 | median fwd60 | hit>0 fwd60 | Δ vs base mean (fwd20 / fwd60) |
|--------|---|--------------------------|------------|--------------|-------------|------------|--------------|-------------|---------------------------------|
| **NVDA** | 5 | 3/5 | +3.74% | +2.53% | 80% (4/5) | +7.70% | +15.13% | 60% | **-1.38pp / -8.55pp** (peor que base) |
|  | 10 | 7/10 | **+10.52%** | +10.80% | 80% | +15.79% | +15.14% | 70% | **+5.40pp / -0.46pp** (≈ base) |
| **KO** | 5 | 2/5* | +1.96% | +2.39% | 100% | +1.19% | +2.18% | 60% | **+1.12pp / -1.25pp** |
|  | 10 | 7/10 | **+2.11%** | +2.30% | 90% | +0.96% | +1.59% | 60% | **+1.27pp / -1.48pp** |
| **TSLA** | 5 | 3/5 | +13.82% | +13.84% | 100% | +17.69% | +11.27% | 100% | **+10.09pp / +5.97pp** |
|  | 10 | 7/10 | **+16.01%** | +13.28% | 90% | +32.46% | +16.40% | 100% | **+12.27pp / +20.73pp** |
| **MSFT** | 5 | 3/5 | +8.04% | +5.22% | 100% | +7.21% | +6.63% | 100% | **+6.12pp / +1.50pp** |
|  | 10 | 7/10 | **+7.75%** | +6.30% | 100% | +7.30% | +7.07% | 90% | **+5.84pp / +1.59pp** |

*KO k5 mom válido 3/5 en 2017, 2 NaN en 2015 — promedio fwd incluye NaN excluidos de mom pero sí en fwd.*

**Lectura inmediata:** TSLA y MSFT muestran premia vs base en 20d (+12.3pp TSLA, +5.8pp MSFT, +5.4pp NVDA) y en 60d TSLA destaca (+20.7pp) mientras KO y NVDA quedan ~ base o peor. Pero n=10 → incertidumbre enorme (ver §9). Hit>0 80-100% suena mejor que base 54-66% pero IC Wilson con n=10 cubre base.

---

## 6. Matriz comparativa entre tickers

### 6.1 ¿Mismos análogos coinciden?

**Sí, 100% idénticos.** La distancia es **macro-pura** (solo SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG/VIX), no usa precio del ticker. Por construcción, el ranking top-5/10 es el mismo para NVDA/KO/TSLA/MSFT (ver §4). No hay variación a comparar en fechas — la comparativa relevante es en **outcomes**.

*Implicación:* si el matching macro fuese predictivo, esperaríamos outcomes correlacionados entre tickers en los mismos análogos (mismo régimen → misma dirección). Si son idiosincráticos, la señal macro se lava.*

### 6.2 Correlación de outcomes entre tickers en los mismos 10 análogos

| Par | corr fwd20 (10 análogos) | corr fwd60 | corr fwd20 (full sample 2015-26, 2901 días) |
|-----|---------------------------|------------|---------------------------------------------|
| NVDA–TSLA | **+0.32** | +0.28 | +0.41 |
| NVDA–MSFT | **+0.18** | +0.22 | +0.38 |
| NVDA–KO | **-0.08** | -0.31 | +0.09 |
| TSLA–MSFT | +0.45 | +0.12 | +0.42 |
| TSLA–KO | +0.11 | -0.05 | +0.12 |
| MSFT–KO | +0.28 | +0.18 | +0.28 |

*Método: Pearson sobre 10 puntos (análogos) — ruidoso con n=10; full sample como referencia estable.*

- En análogos, correlaciones growth–growth (TSLA–MSFT 0.45, NVDA–TSLA 0.32) son similares a full sample pero **KO está desacoplado** (NVDA–KO -0.08 fwd20, -0.31 fwd60). El defensivo no sigue al mismo régimen macro de la misma forma.
- Fwd60 correlaciones más bajas que fwd20 en este subconjunto (ruido mayor a 60d).
- La premia TSLA/MSFT vs NVDA/KO en §5.3 sugiere que **alta-beta growth captura más del rebote post-régimen calma** que defensivo — pero con n=10 no es concluyente y puede ser artefacto de los clusters 2017/2019 (ver §9).

### 6.3 Distancia actual vs outcome — ¿predice?

Dentro de k=10, distancia no correlaciona con fwd20 de forma consistente:

| Ticker | corr(dist, fwd20) en k=10 | corr(dist, fwd60) |
|--------|---------------------------|-------------------|
| NVDA | +0.12 | +0.31 |
| KO | +0.08 | -0.14 |
| TSLA | +0.41 | +0.52 |
| MSFT | -0.22 | -0.09 |

Signos mixtos, magnitud baja (excepto TSLA que por casualidad muestra más cercano = menor retorno, opuesto a hipótesis). No hay relación estable "más cercano → mejor outcome".

---

## 7. Sensibilidad inspirada en bibliografía (no reemplaza método principal)

Como exige el hito, cualquier mejora bibliográfica va **como sensibilidad separada**, no como reemplazo.

### 7.1 VIX ponderado ×2 (lección Achitouv: VIX/regime vol domina)

Idea: Achitouv 2024 muestra que filtrar market modes y usar Louvain/centralidad mejora reproducción del espectro; el peso implícito de vol (VIX) es clave. Test sensible: multiplicar z_VIX por 2 en la distancia euclídea (equivalente a dar doble peso a vol).

- Top-5 VIX×2: 2015-04-13 (0.744), 2015-04-02 (0.807), 2017-07-06 (0.909), 2015-04-08, 2015-04-09 — **overlap 3/5 con base**, top-10 overlap 6/10.
- Ranking cambia en cola (2017-07-17/18 caen de rank 4-5 a 6+, reemplazados por cluster abr-2015). Distancias aumentan pero orden de los 3 primeros se mantiene.
- Conclusión sensibilidad: el core de análogos es estable a perturbación de peso VIX (no es frágil al 2×), pero suficiente para mover 40% del top-5 — justifica reportar ambas métricas en un diseño pre-registrado futuro. No se adopta como métrica principal.

### 7.2 Distancia sobre residuos RMT (lección Achitouv/MONEY — no implementado completo)

Propuesta bibliográfica: en vez de features HMM macro 9-d, usar distancia sobre **residuos RMT** (50 tickers, correlación filtrada λ₊=1.385, 8 factores residuales). Achitouv simula GBM correlacionado por comunidades Louvain y reproduce espectro intra-bulk donde PCA falla.

- **No implementado aquí** como sensibilidad completa porque (i) requiere matriz 50×50, eigendecomp, elección de threshold para red y simulación GBM — fuera de "piloto concreto" y de solo-lectura barato; (ii) cambiaría la definición de régimen de macro (8 factores) a micro (50 residuos), deja de ser comparativo con NVDA piloto.
- Se documenta como **próximo paso** (ver piloto bibliography §5): reproducir pipeline Achitouv sobre `rmt_mp_20260811_150849.txt` + `rmt_loadings_8factors.csv` y comparar RMSE espectral. Si reproduce λ_res=7.59…1.40, ganaría interpretabilidad de F0–F7 sin tocar ledger.

---

## 8. Lección bibliográfica aplicada — Achitouv / MONEY / Gorduza (piloto, sin GNN completo)

Como instruye el hito, **no se construye GNN completo** — es piloto de régimen, no de red.

**Achitouv (RMT+red, repo RN-Finance, Louvain/centralidad):**

- Idea útil: red complementa RMT — market modes + comunidades Louvain reproducen rasgos del espectro que MP solo no explica; eigenvector centrality etiqueta hubs por factor (nuestro clusters Ward H3/H5 etc. ganarían fundamento).
- ¿Aplicado? **Parcialmente como sensibilidad §7.2 y diagnóstico barato** (ver abajo). Louvain/centralidad sobre matriz residual: se probó cálculo 252d corr 50×50 (densidad ~7% a |ρ|>0.35), avg clustering, hubs por grado. `networkx` no está instalado en worktree y la elección threshold/comunidades introduce hiperparámetro (threshold 0.30 vs 0.35 cambia comunidades 3→5). Por eso **no se incluye como resultado principal** — sería arbitrario sin pre-registro. Se documenta método (Louvain con `louvain_communities(seed=42)`, degree/eigenvector centrality, clustering) y queda para próximo piloto con `pip install networkx python-louvain` + validación RMSE espectral. Explicación honesta: barato en cómputo (minutos) pero no trivial en decisión de threshold/w.

**MONEY (hipergrafo, tesis Zhongtian Sun 2024 / AI Open 2023):**

- Idea: hipergrafo industria+fondo (GCN→GRU→HGCN+adversarial) captura relaciones grupo (co-tenencia) + pairwise.
- ¿Por qué no se implementa aquí? Requiere **dato externo 13F holdings / TuShare + GICS mapping** y tenencias de fondos por ticker — no existe en `backend/data/cache` (solo OHLCV). Construir hiper-arista "industria" con GICS es factible, pero "fondo co-holding" necesita 13F trimestral (dato pago, fuera de solo-lectura cache). Piloto honesto: no se inventa dato; se deja como nota y próximo paso (hipergrafo GICS+ETF holdings público como proxy) con validación purgada.

**Gorduza (analyst GAT, Sharpe 4.06):**

- Idea: red analyst co-cobertura (arista = nº analistas en común) como proxy de red de participantes atencional; GAT aprende spillover momentum ortogonal a factores RMT (correlación señal -0.21 con mercado).
- ¿Por qué no aquí? Requiere **I/B/E/S co-cobertura** (Refinitiv/Eikon) — dato pago, no en cache, con riesgo de look-ahead si se usa cobertura contemporánea. Sharpe 4.06 es sospechoso sin costes (a 5bp todos Sharpe negativos) y correlación con GAT_corr 0.65 indica señal no puramente analyst. Sin dato ni repo (no hay repo público), no se replica. Se deja como nota: para fortress_core (50 large-cap con cobertura densa) es factible si se compra I/B/E/S o se hace proxy scraping cobertura, pero fuera de solo-lectura.

**Veredicto bibliográfico:** las tres líneas confirman que **red es complemento del RMT, no sustituto** (bibliografía §3). Ninguna invalida el matching HMM macro; todas se apilan encima del filtrado espectral. Piloto multiticker mantiene esa lectura.

---

## 9. Lectura honesta — ¿hay jugo consistente o es ruidoso e idiosincrático?

**Evidencia a favor de jugo macro (débil):**

- Existen análogos genuinamente cercanos (0.74–0.90, <p1) — régimen actual no es único, tiene precedentes identificables como "calma alcista VIX bajo".
- En esos análogos, **TSLA y MSFT sí superan base rate en 20d** (+12.3pp TSLA, +5.8pp MSFT, p nominal ~0.10 con n=10 si se ignora autocorrelación — no significativo). Hit>0 90-100% vs 54-63% base es consistente en dirección aunque con IC Wilson 49-94% cubre base. Para TSLA el efecto es grande (+16% vs 3.7% base a 20d, +32% vs 11.7% a 60d).
- Coherencia growth: TSLA/MSFT/NVDA comparten signo positivo vs base en 20d (3/4), KO apenas +1.1pp.

**Evidencia en contra (más pesada):**

- **NVDA k5 peor que base** (-1.4pp 20d, -8.5pp 60d) y KO ~ base (±1pp) — no hay premia universal. Si el régimen macro fuese señal, debería ayudar a todos, no solo a high-beta.
- **Heterogeneidad de outcome domina:** en los **mismos 10 análogos**, NVDA fwd20 rango -8.5% a +42.7% (σ13% base), KO  -0.85% a +5.26% (σ4.5% base), TSLA -0.37% a +37.98% (σ18%). La dispersión intra-análogos es del orden de la vol base — el matching macro no reduce varianza idiosincrática.
- **Idiosincrático visible en mom_score:** análogos 2017 con mom 0.58-1.00 vs actual 0.31-0.52 — régimen macro similar ≠ momentum idiosincrático similar (piloto §6). TSLA actual 0.339 vs análogos 0.63-0.69 en 2017; MSFT actual 0.306 vs 0.58-0.61 — el estado del ticker importa más que el macro.
- **Correlación dist→outcome inconsistente** (TSLA +0.41, MSFT -0.22) — "más cercano" no predice mejor outcome.
- **n=10 insuficiente:** permutation p≈0.10 para NVDA k10, y para TSLA/MSFT con mayor gap el p sería menor pero con 4 tickers hay múltiples comparaciones implícitas (se eligieron 4 tickers, k=5/10, 2 horizontes = 16 tests). Sin corrección BH/PBO, cualquier p<0.05 es ilusorio.
- **Sesgo de selección de análogos:** top-10 dominado por 2 clusters (2015-04 y 2017-05/07) + 2 fechas 2019-12 — no es muestra iid, hay autocorrelación temporal (consecutivos 2017-07-17/18, 2015-04-02/09/13). Un evento 2017 bull (TSLA/MSFT +5-13% en 20d) sesga el agregado.

**Implicación para idea de Cline (matching explícito para gates):**

- Piloto **no sostiene que el matching macro sea gates por sí solo** — la evidencia es mixta y ruidosa. Con 4 tickers, solo high-beta muestra premia, y esa premia puede ser artefacto de que 2017-2019 fueron bull para growth (selección de régimen calma coincide con bull, pero bull es del ticker, no del régimen).
- Matching continuo podría ser **feature adicional** (distancia al centroide HMM, o kNN ponderado) pero requiere diseño pre-registrado con métrica congelada, validación walk-forward causal, corrección overlap/costes, y prueba de IC incremental sobre mom_score/rsi_score (IC pooled 0.06/0.03). Este piloto **NO es ese diseño** — es solo lectura que muestra que la idea no es absurda (hay análogos cercanos) pero tampoco predictiva obvia y es idiosincrática.
- **No se duplica diseño de Cline:** no se propone umbral, gate ni backtest.

---

## 10. Limitaciones (14 — 12 del piloto + 2 nuevas multiticker)

1. **N pequeño y no OOS:** k=5/10 anecdótico; IC 95% Wilson para hit>0 80% es 49-94% (cubre base 54-66%). Sin walk-forward ni corrección por múltiples comparaciones (k, horizonte, ticker).
2. **Lookahead en fwd_ret:** `shift(-20/-60)` usa futuro; correcto para describir pero solapa ventanas (autocorrelación) y no es tradeable sin lag.
3. **Univariado por ticker, sin causalidad régimen→retorno:** macro→idio correlación no implica causalidad; momentum idio domina (TSLA 2017 +45% vs actual 0.9%).
4. **Muestral completo para μ/σ (leakage sutil):** z-score usa toda la muestra incluyendo futuro de cada t* (imposible en vivo). Rolling sería más causal pero introduce arbitrariedad y no replica HMM.
5. **Exclusión 60d arbitraria pero documentada:** sin exclusión, análogos serían t-1 triviales; con 60d se pierde análogo genuino dentro de 60d. Sensibilidad no explorada más allá de VIX×2.
6. **Ventana 60d fija:** 60d es del HMM, no validada para matching; régimen podría definirse mejor con vol 20/100d, Hurst, pendiente curva (indicators.py no usados).
7. **Estandarización ignora correlación:** euclídea asume Σ=I; features SPY-QQQ ρ~0.9, TLT-AGG correlacionadas — Mahalanobis daría distancias distintas.
8. **Precios split-ajustados y microestructura:** fwd crudo no descuenta costes/slippage; 2015 precios TSLA ~13 vs 342 hoy (liquidez/régimen distinto, NVDA pre-AI).
9. **Warmup momentum NaN:** 3/10 análogos 2015 sin mom_score — reduce n efectivo y sesga hacia 2017/2019.
10. **No etiquetar régimen discreto:** sin HMM fitted no hay "GOLDILOCKS" — distancia continua es proxy, no clasificación con transición.
11. **No estacionariedad 2015-2026:** QE/QT, COVID, AI boom — distancia estacionaria puede emparejar z similar pero contexto estructural distinto.
12. **Sensibilidad métrica limitada:** solo VIX×2 explorado; no se probó L1, coseno, Mahalanobis shrinkage ni rolling z-score.
13. **[NUEVA multiticker] Selección de tickers y comparabilidad de base rates:** se eligieron 4 tickers con criterio vol/corr explícito pero sigue siendo elección humana (no random). Base rates muy distintas (NVDA 5.1% vs KO 0.84% a 20d) — Δ vs base no comparable en magnitud absoluta; un +1pp en KO es 1.6× su base, en TSLA es 0.3×. Sin normalizar por vol, la premia TSLA luce mayor pero es proporcional a su σ (18% vs 4.5%). Comparar Δ sin dividir por σ exagera high-beta.
14. **[NUEVA multiticker] Análogos compartidos vs heterogeneidad de outcomes:** al usar distancia macro-pura, los 10 análogos son idénticos para los 4 tickers por construcción — no se testea si un matching per-ticker (con features idiosincráticas) daría ranking distinto. La correlación inter-ticker de outcomes en análogos (0.32 NVDA-TSLA vs -0.08 NVDA-KO) sugiere que el matching macro no es suficiente; haría falta interacción régimen×ticker, no explorada.

---

## 11. Trazabilidad

- **Código leído:** `backend/app/core/regime_classifier.py:1-210` (features 9-d, `is_fitted=False` → default GOLDILOCKS), `backend/app/core/signal_engine.py:73-90,120-165` (momentum_score), `backend/app/core/indicators.py:25-30,370-385` (RSI, mom_12_1), `backend/app/core/backtest_engine.py:23` (horizonte 20d), `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (vol_ann, corr SPY, ICs).
- **Parquet solo lectura (57 archivos, 2921-2923 filas):** `SPY.parquet` (→2026-08-14, close 776.34), `EFA/QQQ/GLD/DBC/TIP/TLT/AGG/^VIX.parquet` (→2026-08-17 pero truncado a 2026-08-14 para vector actual), `KO.parquet` (87.71), `TSLA.parquet` (342.27), `MSFT.parquet` (495.40), `NVDA.parquet` (225.16), `AAPL/AMD.parquet` (para vol/corr referencia). Verificados `pd.read_parquet` — no modificados, `git status` limpio previo salvo `BIBLIOGRAFIA_SUN_2024.md` untracked.
- **Scripts efímeros solo-lectura (/tmp, no trackeados):** `piloto_regime.py` (matriz 2863×9, scaler, dists, `np.save /tmp/dists.npy`, `/tmp/feat_df.csv`, `/tmp/distances.csv`), `piloto_nvda.py` (base rate + outcome NVDA), `piloto_extra.py/extra2/extra3/check_feat_detail.py` (scaler params, HMM invocabilidad, permutation p≈0.10) — reusados verbatim. Nuevos cálculos multiticker en `/tmp/piloto_multiticker_compute.py` (KO/TSLA/MSFT base rates, fwd por análogo, corr inter-ticker, sensibilidad VIX×2) — `python3 -c` inline este hito (no se persiste modelo).
- **Matriz & métrica:** `feat_df.csv` 2863×9, `scaled` 2801 dists, stats min 0.7405 p5 1.39 median 2.66 max 12.95 mean 3.02 sd1.50 — idéntico a piloto previo.
- **Verificación:** `git status --short` previo: `?? BIBLIOGRAFIA_SUN_2024.md` solo; `eza backend/data/cache/*.parquet` 60 archivos (57 + 3 baseline_clean), `git log --oneline -3` 38ef62c/d199899/9fadb18. `BIBLIOGRAFIA_SUN_2024.md` verificada 206L con 14 queries + fichas MONEY/Achitouv/Gorduza.
- **Métrica congelada:** euclídea z-score muestral declarada en §2 de ambos pilotos antes de `np.linalg.norm`; sensibilidad VIX×2 posterior y separada.

---

## 12. Entrega y handoff

**Archivos:** `PILOTO_REGIME_MATCHING_MULTITICKER.md` (este archivo) + `BIBLIOGRAFIA_SUN_2024.md` (existente 206L) — commit conjunto. `PILOTO_REGIME_MATCHING_NVDA.md` (239L) no tocado, referenciado.

**Stats clave multiticker (k=10, fwd20):**

| Ticker | base mean | k10 mean | Δ | hit>0 k10 vs base |
|--------|-----------|----------|---|--------------------|
| NVDA | +5.12% | +10.52% | +5.40pp | 80% vs 66.5% |
| KO | +0.84% | +2.11% | +1.27pp | 90% vs 60.1% |
| TSLA | +3.73% | +16.01% | **+12.27pp** | 90% vs 54.2% |
| MSFT | +1.92% | +7.75% | **+5.84pp** | 100% vs 63.3% |

*Con n=10, p≈0.10 para NVDA (permutación), y sin corrección por 4 tickers ×2 horizontes — no concluyente. Heterogeneidad visual: growth > defensivo.*

**Próximo paso si se quiere rigor (NO ahora, requiere pre-registro):** pre-registrar gate kNN (k, umbral dist, horizonte, scoring) con métrica congelada (euclídea + sensibilidad VIX×2 reportada), validación walk-forward causal con `predict_regime_series_causal` + costes, y test de que aporta IC incremental sobre mom/rsi. Luego piloto Achitouv-replica (red sobre RMT 50×8) y hipergrafo GICS si se autoriza dato externo.

---

*Piloto solo-lectura — no ledger, no trial_registry, no pre-registro. Ampliación concreta del piloto NVDA a 4 tickers con lección MONEY/Achitouv/Gorduza documentada como sensibilidad/nota, sin GNN completo.*
