# PILOTO — Regime matching growth ampliación (AMD + META + AVGO) sobre matriz HMM congelada — solo lectura, sin ledger

**Fecha piloto:** 2026-09-02 (worktree `test-opencode-orca`, segunda extensión sobre multiticker b41c1a1, amplía 4→7 tickers)  
**Restricción dura:** SOLO LECTURA de `backend/data/cache/*.parquet` y código existente. No se modifican `ledger`/`trial_registry`, no hay pre-registro, no se reentrena HMM, no se recalcula ranking macro. Evidencia exploratoria, NO reemplaza diseño pre-registrado. Referencias previas: `PILOTO_REGIME_MATCHING_NVDA.md` (239L, 38ef62c, N=1) y `PILOTO_REGIME_MATCHING_MULTITICKER.md` (380L, b41c1a1, N=4 KO/TSLA/MSFT/NVDA).  
**Tickers elegidos (3 nuevos):** **AMD** (vol_ann 0.5983, p99, semis), **META** (0.3785, social/growth), **AVGO** (0.3953, semis diversificado) — motivo documentado abajo, test de replicación del hallazgo TSLA. Total evaluado en este documento: 7 tickers (4 previos reutilizados como comparativa + 3 nuevos calculados).  
**Insumo diagnóstico:** `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (vol_ann, corr SPY, ICs; criterio vol en § vol_ann tabla: mediana Large 0.2725, AMD 0.598 p99, META 0.379 > mediana, AVGO 0.395 High-vol grupo).  
**Fecha "régimen actual":** **2026-08-14** — último dato común SPY/QQQ/AMD/META/AVGO con close (SPY max 2026-08-14, VIX 14.25). Mantiene comparabilidad con pilotos previos §6 (alternativa 2026-08-17 descartada por ffill stale).  
**Métrica y matriz congeladas:** ver §2 verbatim.

---

## 1. Elección de 3 tickers growth/high-beta — criterio explícito (no arbitrario, pre-especificado antes de computar outcomes)

TSLA fue **único con ventaja real** en el multiticker k10: Δ fwd20 **+12.27pp** (16.01% vs 3.73% base), Δ fwd60 **+20.73pp** (32.46% vs 11.73% base), hit>0 90%/100% vs 54%/56% base (§5.3 multiticker). NVDA +5.40pp, MSFT +5.84pp, KO +1.27pp — magnitudes menores y/o diluidas por σ. Boris pregunta si es **efecto sistemático growth/high-beta** o **idiosincrático TSLA**.

Se amplía con 3 nombres growth/high-beta adicionales con la misma lógica de heterogeneidad que guió KO/TSLA/MSFT, usando el diagnóstico vol ya publicado:

| Ticker | Rol en extensión | vol_ann 2015-26 (DIAGNOSTICO tabla) | vs mediana Large 0.2725 | corr diaria SPY (ref piloto) | Grupo sector | Justificación vs TSLA |
|--------|------------------|--------------------------------------|--------------------------|------------------------------|--------------|------------------------|
| **AMD** | High-beta extremo, semis puro | **0.5983** (máximo del universo, p99, > NVDA 0.482 / TSLA 0.572) | p99 (alta) | 0.52 aprox (TSLA 0.49, baja idiosincrática) | Semis/AI, IC_mom -0.037 | Extremo alta-vol del diagnóstico (rango 0.176-0.598, p90 0.387). Si ventaja TSLA fuese por high-beta, AMD debería replicarla o excederla — es el test más exigente por vol. |
| **META** | Growth large-cap, social/ads | **0.3785** | > mediana (+0.106, p~75) | ~0.55 (no reportada pero Large típica) | Big tech / growth, IC_mom +0.044 (cola superior positiva) | High-vol moderada pero distinta narrativa (plataforma vs hardware semis/auto). Pertenece a cola positiva de IC_mom (solo 3 tickers >+0.05: ADBE/GE/META). Testa si narrativa growth distinta converge en mismo régimen macro. |
| **AVGO** | Growth semis diversificado, M&A | **0.3953** | high-vol (+0.123) | ~0.50 | Semis diversificado (infrasw/Broadcom), vol 0.395 > p75 | Semis como NVDA/AMD pero modelo diversificado (no puro AI), vol alta coherente con grupo High-vol del diagnóstico. Permite separar semis puro vs diversificado. |

*Descartados para esta extensión:* AAPL (0.288) y NFLX (0.426) — AAPL muy similar a MSFT (core), NFLX similar vol a AVGO/META pero con heterogeneidad de censura distinta; con 3 plazas se prioriza el triángulo AMD extremo / META plataforma / AVGO semis diversificado para máxima varianza sectorial dentro de high-beta. Selección documentada **antes** de computar outcomes (ver este §, no post-hoc).*

**Vol y grupo:** DIAGNOSTICO § vol_ann: media 0.290, mediana 0.273, p90 0.387, p99 0.598 (AMD es max). META 0.378 y AVGO 0.395 caen en **High-vol** (>p75≈0.31 / >p90 borde), TSLA 0.572 p95+, NVDA 0.482 p90. Los 3 nuevos superan mediana y rebasan p75 — son high-beta por definición del diagnóstico.

---

## 2. Metodología congelada — idéntica a pilotos previos (comparabilidad, sin reinventar)

Reusa **exactamente** la misma pipeline de `PILOTO_REGIME_MATCHING_NVDA.md §1-3` y `MULTITICKER.md §2`, sin cambios:

| Dimensión | Valor congelado | Fuente |
|-----------|-----------------|--------|
| Features HMM 9-d | `growth_SPY/EFA/QQQ = close.pct_change(60)`, `inflation_GLD/DBC/TIP = pct_change(60)`, `rates_TLT/AGG = pct_change(60)`, `vix_level = close` | `regime_classifier.py:34-55` |
| Ventana | 60 trading days (~3m, aritmético, no log) | idem |
| Estandarización | z-score muestral completo μ/σ sobre 2863 filas (`StandardScaler().fit(feat_df)`) — **tabla §2.1 idéntica verbatim**, incluye leakage sutil documentado pero replica HMM `fit` | multiticker §2 |
| Métrica | **Euclídea L2 sobre z-space 9-d**, declarada a priori: `d = \|\|z(t*)-z(t_actual)\|\|₂` — **congelada, no probar Mahalanobis como principal** (solo nota §8 si se desea) | piloto §2 |
| Matriz histórica | 2015-03-31 → 2026-08-14 = **2863 filas** (55.2% del total); `ffill().dropna()` replicado — outer union + ffill, truncada a SPY max | `piloto_regime.py` |
| Candidatos válidos | **2801** fechas (2015-03-31→2026-05-19) tras **exclusión 60 trading days** previos a 2026-08-14 + t_actual | piloto §3 |
| Ranking | top-5 y top-10 **fijos (k=5/10)** idénticos multiticker — **no recalcular ranking macro** (es común, ya está en multiticker §4) | multiticker §4 |
| Outcomes | `fwd_ret_20d = close.shift(-20)/close-1`, `fwd_ret_60d = close.shift(-60)/close-1`, `momentum_12_1 = pct_change(252)*100`, `momentum_score = clip((mom+50)/150)` | `indicators.py:381`, `signal_engine.py:137`, `backtest_engine.py:23` |
| Base rate | **Por ticker** (no global) — n=2901 fwd20 / 2861 fwd60 por ticker, toda la muestra con fwd disponible | multiticker §5 |
| Fecha actual | 2026-08-14 | §6 multiticker |

**Tabla μ/σ muestral (reusada verbatim, no recalculada — verifica `/tmp/piloto_growth3.py`):**

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

**Métrica congelada antes de computar:** no se probó Mahalanobis, coseno ni L1 como métrica principal; sensibilidad VIX-ponderada ya reportada en multiticker §7-8 (no reemplaza, no se repite aquí).

---

## 3. Snapshot régimen actual — features 2026-08-14 (común, macro-puro)

Mismo vector 9-d que ve el HMM; es **macro**, no por ticker. Reusado de multiticker §3 (verificado idéntico en `/tmp/feat_df.csv`):

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

Lectura: calma alcista moderada (EFA>SPY>QQQ), commodities en retroceso suave 60d, rates planos, VIX 14.25 (p~18). Mismo régimen GOLDILOCKS nominal pero sin HMM fitted (`is_fitted=False`).

**Momentum_score en t_actual (por ticker — 3 nuevos calculados + 4 previos reutilizados para comparativa):**

| Ticker | close 2026-08-14 | mom_12_1 | momentum_score | Nota |
|--------|-------------------|----------|----------------|------|
| **AMD** | 514.39 | **+178.9%** | **1.000** | Máximo posible (clip 1.0) — momentum extremo, outlier incluso dentro de high-beta. Supera 2017 análogos (1.00) y distorsiona base vs régimen. |
| **META** | 589.85 | **-24.1%** | **0.172** | Por debajo de todos los análogos 2017/2019 (0.517-0.611) y de base NVDA mediana 0.894 — momentum muy débil pese a régimen macro común. |
| **AVGO** | 392.99 | **+28.1%** | **0.521** | Casi idéntico a KO 0.520 y NVDA 0.494, homogéneo con régimen actual. |
| NVDA (ref) | 225.16 | +24.2% | **0.494** | multiticker §3 |
| KO (ref) | 87.71 | +28.0% | **0.520** | |
| TSLA (ref) | 342.27 | +0.9% | **0.339** | |
| MSFT (ref) | 495.40 | -4.1% | **0.306** | |

Rango 0.172 (META) – 1.000 (AMD) — heterogeneidad idiosincrática extrema **en t_actual** pese a régimen macro idéntico. AMD en euforia momentum, META/MSFT/TSLA en debilidad. El estado del ticker importa más que el macro, como ya advirtió multiticker §5.3/§9.

---

## 4. Ranking de análogos — top-5 y top-10 (común a los 7 tickers, no recalculado)

Distancias euclídeas sobre z-space 9-d (n=2801 candidatos). Distribución idéntica a pilotos previos: min 0.7405, p5 1.39, p25 2.04, mediana 2.66, p95 6.04, mean 3.02 ±1.50.

| rank | fecha | dist L2 | VIX | Lectura macro |
|------|-------|---------|-----|---------------|
| 1 | 2015-04-13 | 0.7405 | 13.94 | Calma 60d, SPY +4.56% |
| 2 | 2015-04-02 | 0.8006 | 14.67 | |
| 3 | 2017-07-06 | 0.8056 | 12.54 | |
| 4 | 2017-07-17 | 0.8416 | 9.82 | VIX 9.8 — calma extrema |
| 5 | 2017-07-18 | 0.8610 | 9.89 | |
| 6 | 2017-07-05 | 0.8766 | 11.07 | |
| 7 | 2017-05-05 | 0.8861 | 10.57 | |
| 8 | 2019-12-10 | 0.8978 | 15.68 | |
| 9 | 2015-04-09 | 0.8980 | 13.09 | |
| 10 | 2019-12-03 | 0.9010 | 15.96 | |

*Todas <0.91 (~p1=1.12) — análogos excepcionalmente cercanos. Top-10 en cola 0.04–0.3th pctil. Lista **idéntica** para los 7 tickers porque la distancia es macro-pura; cualquier diferencia entre tickers en §5 es outcome idiosincrático, no ranking.*

---

## 5. Outcome por ticker en los mismos análogos — base rate ticker-específica + detalle 10 análogos + agregado k5/k10

Definiciones: `fwd20/60` split-ajustados, base rate **específica por ticker** (n≈2901 fwd20 / 2861 fwd60).

### 5.1 Base rates incondicionales (3 nuevos + 4 previos de referencia — recalculado idéntico, verifica multiticker §5.1)

| Ticker | fwd20 n | mean | median | sd | hit>0 | hit>+5% | fwd60 n | mean | median | sd | hit>0 | hit>+10% | vol_ann |
|--------|---------|------|--------|----|-------|---------|---------|------|--------|----|-------|----------|---------|
| **AMD** (nuevo) | 2901 | **+5.04%** | +2.62% | 17.13% | 56.1% | 44.4% | 2861 | **+15.92%** | +10.06% | 33.87% | 62.4% | 50.1% | **0.598** |
| **META** (nuevo) | 2901 | **+1.89%** | +2.30% | 9.62% | 61.3% | 34.9% | 2861 | **+5.98%** | +5.61% | 18.44% | 65.3% | 36.9% | 0.379 |
| **AVGO** (nuevo) | 2901 | **+3.22%** | +2.72% | 9.89% | 63.9% | 39.1% | 2861 | **+9.45%** | +8.34% | 15.38% | 73.6% | 44.3% | 0.395 |
| NVDA (ref) | 2901 | +5.12% | +4.84% | 13.19% | 66.5% | 49.5% | 2861 | +16.25% | +13.97% | 25.05% | 73.8% | 57.7% | 0.482 |
| KO (ref) | 2901 | +0.84% | +1.02% | 4.54% | 60.1% | 14.2% | 2861 | +2.44% | +2.47% | 6.85% | 66.3% | 14.2% | 0.179 |
| TSLA (ref) | 2901 | +3.73% | +1.35% | 18.20% | 54.2% | 39.5% | 2861 | +11.73% | +3.79% | 34.16% | 56.0% | 40.8% | 0.572 |
| MSFT (ref) | 2901 | +1.92% | +2.07% | 6.57% | 63.3% | 28.3% | 2861 | +5.71% | +6.06% | 10.46% | 71.7% | 34.1% | 0.276 |

*AMD drift 5.04% a 20d casi idéntico a NVDA 5.12% (semis puro), AVGO 3.22% intermedio, META 1.89% cercano a MSFT 1.92% — base rates muy distintas; comparar Δ vs propia base, no vs global. Vol_ann coherente con diagnóstico: AMD p99 > TSLA p95+ > NVDA p90 > AVGO/META High-vol > MSFT mediana > KO p10.*

### 5.2 Outcome por análogo (top-10) — detalle (3 tickers nuevos; 4 previos en multiticker §5.2 — no repetidos salvo referencia agregada)

**AMD:**

| fecha | mom_score en t* | close | fwd20 | fwd60 | vs base fwd20 (+5.04%) | vs base fwd60 (+15.92%) |
|-------|-----------------|-------|-------|-------|------------------------|------------------------|
| 2015-04-13 | NaN* | 2.78 | **-16.55%** | -27.70% | **-21.59pp** | **-43.62pp** |
| 2015-04-02 | NaN | 2.69 | -14.13% | -13.01% | -19.16pp | -28.93pp |
| 2017-07-06 | 1.000 | 13.02 | +1.69% | -2.07% | -3.35pp | -17.99pp |
| 2017-07-17 | 1.000 | 13.80 | -7.54% | -0.72% | -12.57pp | -16.64pp |
| 2017-07-18 | 1.000 | 13.48 | -3.41% | +2.97% | -8.45pp | -12.95pp |
| 2017-07-05 | 1.000 | 13.19 | +1.36% | -3.41% | -3.67pp | -19.33pp |
| 2017-05-05 | 1.000 | 10.19 | **+10.30%** | **+34.54%** | **+5.27pp** | **+18.62pp** |
| 2019-12-10 | 0.982 | 39.44 | **+24.16%** | +9.71% | **+19.13pp** | -6.21pp |
| 2015-04-09 | NaN | 2.72 | -14.71% | -9.19% | -19.74pp | -25.11pp |
| 2019-12-03 | 0.884 | 38.90 | **+26.22%** | **+22.01%** | **+21.18pp** | +6.09pp |

*NaN 2015: ventana 252d insuficiente (warmup, no error) — 3/10 sin mom_score.*

**META:**

| fecha | mom_score | close | fwd20 | fwd60 | vs base fwd20 (+1.89%) | vs base fwd60 (+5.98%) |
|-------|-----------|-------|-------|-------|------------------------|------------------------|
| 2015-04-13 | NaN | 82.29 | -6.02% | +3.18% | -7.92pp | -2.80pp |
| 2015-04-02 | NaN | 80.85 | -3.15% | +5.20% | -5.05pp | -0.78pp |
| 2017-07-06 | 0.517 | 147.52 | **+13.28%** | **+14.82%** | **+11.39pp** | **+8.84pp** |
| 2017-07-17 | 0.578 | 158.34 | **+6.90%** | +7.43% | **+5.00pp** | +1.45pp |
| 2017-07-18 | 0.576 | 161.44 | +5.00% | +6.07% | +3.10pp | +0.09pp |
| 2017-07-05 | 0.544 | 149.03 | **+12.61%** | **+12.23%** | **+10.72pp** | **+6.25pp** |
| 2017-05-05 | 0.517 | 148.93 | +2.26% | **+13.06%** | +0.36pp | **+7.08pp** |
| 2019-12-10 | 0.611 | 199.12 | **+8.68%** | **-15.62%** | **+6.78pp** | **-21.60pp** |
| 2015-04-09 | NaN | 81.45 | -4.55% | +6.55% | -6.45pp | +0.57pp |
| 2019-12-03 | 0.609 | 197.09 | +5.51% | -1.20% | +3.62pp | -7.18pp |

**AVGO:**

| fecha | mom_score | close | fwd20 | fwd60 | vs base fwd20 (+3.22%) | vs base fwd60 (+9.45%) |
|-------|-----------|-------|-------|-------|------------------------|------------------------|
| 2015-04-13 | NaN | 9.46 | -2.03% | +2.44% | -5.25pp | -7.00pp |
| 2015-04-02 | NaN | 9.44 | -1.78% | +5.89% | -5.00pp | -3.56pp |
| 2017-07-06 | 0.725 | 18.34 | **+6.49%** | +3.61% | **+3.27pp** | -5.83pp |
| 2017-07-17 | 0.715 | 19.43 | +0.76% | -0.81% | -2.46pp | -10.26pp |
| 2017-07-18 | 0.715 | 19.57 | +1.12% | +0.22% | -2.10pp | -9.23pp |
| 2017-07-05 | 0.709 | 18.07 | **+9.39%** | +5.32% | **+6.17pp** | -4.13pp |
| 2017-05-05 | 0.743 | 17.59 | **+11.38%** | **+10.16%** | **+8.15pp** | +0.71pp |
| 2019-12-10 | 0.579 | 26.73 | -1.81% | **-20.58%** | -5.03pp | **-30.02pp** |
| 2015-04-09 | NaN | 9.60 | -3.73% | +5.78% | -6.95pp | -3.66pp |
| 2019-12-03 | 0.561 | 26.01 | **+6.24%** | -6.09% | **+3.02pp** | **-15.54pp** |

*Precios split-ajustados parquet. Nota: AVGO y AMD sufren split/consolidaciones históricas (AMD ~2.7 en 2015 vs 514 hoy, AVGO ~9.4 vs 393), liquides/régimen distinto a actual — misma limitación que NVDA pre-AI documentada.*

### 5.3 Agregado k5 / k10 vs base rate por ticker (3 nuevos + 4 previos reutilizados — comparabilidad directa)

| Ticker | k | n_análogos mom válido | mean fwd20 | median fwd20 | hit>0 fwd20 | mean fwd60 | median fwd60 | hit>0 fwd60 | Δ vs base mean (fwd20 / fwd60) | Δ/σ (fwd20) |
|--------|---|------------------------|------------|--------------|-------------|------------|--------------|-------------|--------------------------------|-------------|
| **AMD** (nuevo) | 5 | 3/5 | **-7.99%** | -7.54% | **20% (1/5)** | -8.11% | -2.07% | 20% | **-13.02pp / -24.03pp** (peor que base) | **-0.76** |
|  | 10 | 7/10 | **+0.74%** | -1.02% | **50% (5/10)** | +1.31% | -1.40% | 40% | **-4.29pp / -14.61pp** | **-0.25** |
| **META** (nuevo) | 5 | 3/5 | **+3.20%** | +5.00% | **60% (3/5)** | +7.34% | +6.07% | 100% | **+1.31pp / +1.36pp** | +0.14 |
|  | 10 | 7/10 | **+4.05%** | +5.26% | **70% (7/10)** | +5.17% | +6.31% | 80% | **+2.16pp / -0.81pp** | **+0.22** |
| **AVGO** (nuevo) | 5 | 3/5 | **+0.91%** | +0.76% | 60% (3/5) | +2.27% | +2.44% | 80% | **-2.31pp / -7.18pp** | -0.23 |
|  | 10 | 7/10 | **+2.60%** | +0.94% | **60% (6/10)** | +0.59% | +3.03% | 70% | **-0.62pp / -8.85pp** | **-0.06** |
| **NVDA** (ref) | 5 | 3/5 | +3.74% | +2.53% | 80% (4/5) | +7.70% | +15.13% | 60% | -1.39pp / -8.55pp | -0.11 |
|  | 10 | 7/10 | **+10.52%** | +10.80% | 80% | +15.79% | +15.14% | 70% | **+5.40pp / -0.47pp** | **+0.41** |
| **KO** (ref) | 5 | 3/5 | +1.96% | +2.39% | 100% | +1.19% | +2.18% | 60% | +1.12pp / -1.25pp | +0.25 |
|  | 10 | 7/10 | **+2.11%** | +2.30% | 90% | +0.96% | +1.59% | 60% | **+1.27pp / -1.48pp** | **+0.28** |
| **TSLA** (ref) | 5 | 3/5 | +13.82% | +13.84% | 100% | +17.69% | +11.27% | 100% | **+10.09pp / +5.97pp** | +0.55 |
|  | 10 | 7/10 | **+16.01%** | +13.28% | 90% | +32.46% | +16.40% | 100% | **+12.27pp / +20.73pp** | **+0.67** |
| **MSFT** (ref) | 5 | 3/5 | +8.04% | +5.22% | 100% | +7.21% | +6.63% | 100% | **+6.12pp / +1.50pp** | +0.93 |
|  | 10 | 7/10 | **+7.75%** | +6.30% | 100% | +7.30% | +7.07% | 90% | **+5.84pp / +1.59pp** | **+0.89** |

*Δ/σ = (k10 mean – base mean)/sd base fwd20 — normaliza por vol ticker-específica (KO 4.5% vs AMD 17.1%). Es la métrica comparable entre tickers con Δpp absoluto engañoso para high-beta.*

---

## 6. Matriz comparativa growth ampliado — ¿se replica la ventaja TSLA?

### 6.1 Tabla comparativa k10 (horizonte fwd20 primario — el que mostró jugo en multiticker)

| Ticker | Grupo | vol_ann | base fwd20 mean | k10 mean fwd20 | **Δ k10 vs base fwd20** | Δ/σ | k10 median | k10 hit>0 fwd20 | hit base | Δ hit pp | k10 mean fwd60 | **Δ fwd60** | hit>0 fwd60 |
|--------|-------|---------|-----------------|-----------------|--------------------------|-----|------------|-----------------|----------|----------|-----------------|-------------|-------------|
| **TSLA** | Growth alta-beta (auto) | 0.572 | 3.73% | **16.01%** | **+12.27pp** | **+0.67** | 13.28% | 90% | 54.2% | **+35.8pp** | 32.46% | **+20.73pp** | 100% |
| **MSFT** | Core large-cap (mediana) | 0.276 | 1.92% | **7.75%** | **+5.84pp** | **+0.89** | 6.30% | 100% | 63.3% | +36.7pp | 7.30% | +1.59pp | 90% |
| **NVDA** | Growth semis/AI | 0.482 | 5.12% | **10.52%** | **+5.40pp** | +0.41 | 10.80% | 80% | 66.5% | +13.5pp | 15.79% | -0.47pp | 70% |
| **META** | Growth social (nuevo) | 0.379 | 1.89% | **4.05%** | **+2.16pp** | +0.22 | 5.26% | 70% | 61.3% | +8.7pp | 5.17% | -0.81pp | 80% |
| KO | Defensivo | 0.179 | 0.84% | 2.11% | +1.27pp | +0.28 | 2.30% | 90% | 60.1% | +29.9pp | 0.96% | -1.48pp | 60% |
| **AVGO** | Semis diversificado (nuevo) | 0.395 | 3.22% | 2.60% | **-0.62pp** | -0.06 | 0.94% | 60% | 63.9% | -3.9pp | 0.59% | **-8.85pp** | 70% |
| **AMD** | Semis puro extremo (nuevo) | 0.598 | 5.04% | 0.74% | **-4.29pp** | **-0.25** | -1.02% | 50% | 56.1% | -6.1pp | 1.31% | **-14.61pp** | 40% |

**Lectura honesta — ¿se replica la ventaja TSLA en growth/high-beta?**

**No. La ventaja TSLA no se replica sistemáticamente en growth/high-beta; es idiosincrática.**

- TSLA es **outlier positivo**: +12.27pp fwd20 (+0.67σ), +20.73pp fwd60. Ninguno de los 3 nuevos lo replica. El más cercano es META (+2.16pp, +0.22σ, 5.6× menor que TSLA) y NVDA/MSFT previos (+5.4pp/+5.8pp, ambos <½ de TSLA). 
- **AMD es el contraejemplo más elocuente**: siendo el ticker de **mayor vol (0.598, p99)** y más cercano a TSLA en vol (0.572) y narrativa semis, su k10 es **peor que base** (-4.29pp, -0.25σ fwd20; -14.61pp fwd60) y k5 es catastrófico (-13pp). Si la premia fuese "high-beta growth sistemático", AMD debería liderar — hace lo opuesto.
- **AVGO es nulo**: -0.62pp fwd20 (-0.06σ, esencialmente base) y **-8.85pp fwd60**. Semis diversificado no hereda premia.
- **META es modesto**: +2.16pp (70% hit vs 61% base) no es distinguible de KO defensivo (+1.27pp) en magnitud económica; a 60d incluso revierte (-0.81pp). Su IC Wilson n=10 para hit>0 70% es 39-89% (cubre base 61%).
- **Normalizado por vol (Δ/σ)** confirma el orden: MSFT +0.89 > TSLA +0.67 > NVDA +0.41 > KO +0.28 > META +0.22 > AVGO -0.06 > AMD -0.25. El mejor Δ/σ es **MSFT (core mediana, no high-beta)** — opuesto a hipótesis growth. High-beta puro (AMD) es negativo.
- **Rango intra-ticker en mismos 10 análogos** (prueba de heterogeneidad): TSLA -0.37% a +37.98% (σ18% base), AMD -16.55% a +26.22% (σ17%), META -6.02% a +13.28% (σ9.6%), AVGO -3.73% a +11.38% (σ9.9%). La dispersión es del orden de la vol base — el matching macro no reduce varianza idiosincrática.
- **k5 vs k10**: AMD k5 -7.99% mean (20% hit) vs k10 +0.74% (50% hit) — inestable con k; TSLA es estable positivo en ambos k. Esto sugiere que AMD sufre especialmente del cluster 2015 (-14% a -16% en 3 fechas), mientras TSLA capitalizó ese mismo cluster (+12% a +18%). Mismo régimen macro, **outcome opuesto por ticker** — prueba de idiosincrasia.

*Implicación:* la heterogeneidad intra-growth domina al factor común macro. Si el matching macro fuese señal sistemática para high-beta, los 5 growth (NVDA/TSLA/AMD/META/AVGO) deberían covariar positivamente y compartir signo de Δ — en cambio Δ fwd20: TSLA +12.27, NVDA +5.40, META +2.16, AVGO -0.62, AMD -4.29 → **2/5 positivos con magnitud, 2 nulos/negativos, 1 outlier positivo**. No hay factor growth común extraíble de este régimen.

### 6.2 ¿Todos los growth covarían en el mismo régimen? — correlación de outcomes en los mismos 10 análogos vs full sample

Esto responde directamente: *si el régimen macro fuese driver común, los outcomes de growth deberían correlacionar positivamente en los mismos 10 análogos, más que el par growth-defensivo.*

**Correlación Pearson fwd20 en los 10 análogos (n=10, ruidosa) + full sample (n=2901/2861, estable):**

| Par (fwd20) | **r en 10 análogos** | r full sample 2901d | Interpretación |
|-------------|----------------------|---------------------|----------------|
| **AMD–TSLA** | **+0.60** | +0.26 | Alta en análogos, pero AMD media es -4pp vs TSLA +12pp — correlación positiva no implica nivel; viene de 2 fechas extremas 2019 (+26/+24% AMD, +38/+28% TSLA) que arrastran r. Sin esas 2, r cae. |
| AMD–NVDA | +0.59 | +0.55 | Similar a full — no aporta señal régimen específica. |
| AMD–META | +0.56 | +0.29 | Similar. |
| AMD–AVGO | +0.47 | +0.42 | Similar a full. |
| **META–NVDA** | +0.37 | +0.48 | Ligeramente menor que full — no amplifica. |
| META–AVGO | **+0.57** | +0.43 | Similar. |
| NVDA–TSLA | **+0.05** | **+0.35** | **Caída drástica**: growth–growth estrella NVDA-TSLA colapsa de 0.35 full a 0.05 en análogos — opuesto a hipótesis de régimen común. |
| AVGO–TSLA | **-0.35** | **+0.38** | **Invierte signo** (full +0.38 → análogos -0.35). Mismo régimen, outcomes opuestos. |
| MSFT–TSLA | +0.20 | +0.41 | Mitad que full. |
| KO–NVDA | **+0.72** | +0.07 | **Invierte al alza**: defensivo KO correlaciona 0.72 con NVDA en análogos vs 0.07 full — artefacto de 2017-05-05 (ambos + muy positivos) que infla r con n=10. |
| KO–TSLA | +0.08 | +0.09 | Igual que full (bajo). |
| META–TSLA | -0.05 | +0.31 | Se anula. |

**fwd60 en 10 análogos:**

| Par (fwd60) | r 10 análogos | r full | Nota |
|-------------|---------------|--------|------|
| NVDA–AMD | **+0.91** | +0.48 | Inflado por 2017-05-05 (+58% NVDA, +34% AMD) — outlier único explica r. |
| META–AVGO | **+0.91** | +0.50 | Idem: ambos caen -20% el 2019-12-10 mientras TSLA +74% — cluster 2019 divide. |
| TSLA–META | **-0.71** | +0.22 | **Invierte fuerte**: full +0.22 → análogos -0.71 (TSLA outlier 74%/121% en 2019 donde META -15%/-1%). |
| TSLA–AVGO | **-0.65** | +0.35 | Idem. |
| NVDA–KO | +0.77 | -0.07 | Invierte al alza (full negativo → análogos +0.77). |

**Matriz completa fwd20 (10 análogos, Pearson, n=10):**

```
          NVDA    KO  TSLA  MSFT   AMD  META  AVGO
NVDA      1.00  0.72  0.05 -0.21  0.59  0.37  0.79
KO        0.72  1.00  0.08 -0.65  0.59  0.53  0.66
TSLA      0.05  0.08  1.00  0.20  0.60 -0.05 -0.35
MSFT     -0.21 -0.65  0.20  1.00 -0.36 -0.69 -0.46
AMD       0.59  0.59  0.60 -0.36  1.00  0.56  0.47
META      0.37  0.53 -0.05 -0.69  0.56  1.00  0.57
AVGO      0.79  0.66 -0.35 -0.46  0.47  0.57  1.00
```

**Matriz completa fwd20 full sample (n=2901):**

```
          NVDA    KO  TSLA  MSFT   AMD  META  AVGO
NVDA      1.00  0.07  0.35  0.59  0.55  0.48  0.51
KO        0.07  1.00  0.09  0.21  0.12  0.12  0.15
TSLA      0.35  0.09  1.00  0.41  0.26  0.31  0.38
MSFT      0.59  0.21  0.41  1.00  0.41  0.50  0.49
AMD       0.55  0.12  0.26  0.41  1.00  0.29  0.42
META      0.48  0.12  0.31  0.50  0.29  1.00  0.43
AVGO      0.51  0.15  0.38  0.49  0.42  0.43  1.00
```

**Lectura comparativa growth covariación:**

- **En full sample**, los growth covarían positivamente entre sí (NVDA–MSFT 0.59, NVDA–AMD 0.55, MSFT–META 0.50, AVGO–NVDA 0.51) — hay factor growth común contemporáneo.
- **En los 10 análogos (mismo régimen macro)**, esa estructura **se rompe**: NVDA–TSLA 0.05 vs 0.35 full, TSLA–AVGO -0.35 vs +0.38, TSLA–META -0.05 vs +0.31, MSFT se desacopla negativamente de KO (-0.65) y META (-0.69). Solo AMD mantiene correlaciones ~0.5-0.6 con todos los growth, pero con nivel medio opuesto a TSLA.
- **KO–NVDA 0.72 en análogos vs 0.07 full** indica que el subconjunto de 10 no preserva la correlación contemporánea — es artefacto de n=10 con clusters temporales (2017-05-05, 2019-12-10) y dispersión alta. Un r sobre 10 puntos tiene SE≈0.33; cualquier r entre -0.65 y +0.65 es ruido.
- **Implicación**: no hay evidencia de que el régimen macro "calma alcista VIX bajo" sincronice outcomes growth. Si fuese driver común, los growth deberían correlacionar **más** en análogos que en full — observamos lo contrario (NVDA-TSLA cae, TSLA-AVGO invierte). La señal macro se lava por idiosincrasia.

### 6.3 Distancia actual vs outcome — ¿predice dentro de k=10?

Dentro de k=10, distancia no correlaciona con fwd20 de forma consistente (ya visto en multiticker, se replica):

| Ticker | corr(dist, fwd20) k=10 | corr(dist, fwd60) |
|--------|------------------------|-------------------|
| AMD | **+0.63** | +0.72 |
| META | +0.33 | -0.24 |
| AVGO | +0.28 | -0.29 |
| NVDA (ref) | +0.12 | +0.31 |
| TSLA (ref) | +0.41 | +0.52 |
| MSFT (ref) | -0.22 | -0.09 |
| KO (ref) | +0.08 | -0.14 |

Signos mixtos, magnitud inestable; AMD muestra "más lejano → mejor outcome" (opuesto a hipótesis más cercano → mejor). No hay relación estable; con n=10 cualquiera de estas r es indistinguible de ruido (IC 95% para r incluye 0 salvo r>0.63 con n=10 barely).

---

## 7. Sensibilidad y notas bibliográficas (heredado multiticker §7-8, no re-ejecutado — no reemplaza método principal)

Como exige el hito, cualquier mejora bibliográfica va como sensibilidad separada, no reemplazo. Se hereda verbatim de multiticker:

- **VIX ponderado ×2**: top-5 overlap 3/5, top-10 6/10 — core estable, no frágil al 2×. No se adopta como métrica principal; aplica igual a los 3 nuevos (ranking macro idéntico).
- **Residuos RMT** (Achitouv/MONEY): no implementado completo por requerir matriz 50×50, eigendecomp, threshold red y GBM — fuera de solo-lectura barato y deja de ser comparativo HMM. Dejado como próximo paso (pipeline Achitouv sobre `rmt_mp_*.txt` + `rmt_loadings_8factors.csv`).
- **Achitouv (RMT+red), MONEY (hipergrafo 13F), Gorduza (analyst GAT Sharpe 4.06)**: red complementa RMT, no sustituto; sin dato 13F/I/B/E/S en cache ni repo público, no replicable en solo-lectura. Ver multiticker §8 y `BIBLIOGRAFIA_SUN_2024.md` (206L, 14 queries, fichas).

Para esta extensión: **no se probó Mahalanobis como principal** — se mantiene euclídea congelada verbatim. Nota opcional: Mahalanobis con shrinkage sobre Σ 9-d (SPY-QQQ ρ≈0.9, TLT-AGG correlacionadas) daría distancias distintas y podría mover 40% del top-10 (análogo a VIX×2), pero requiere elegir regularización (Ledoit-Wolf vs empírico) — hiperparámetro sin pre-registro, fuera de solo-lectura. Si se desea en diseño futuro, pre-registrar Σ rolling causal + shrinkage γ fijo.

---

## 8. Lectura honesta — ¿hay jugo consistente en growth o es ruidoso e idiosincrático?

**Evidencia a favor de jugo macro (débil, ya en multiticker, no ampliada por growth3):**

- Existen análogos genuinamente cercanos (0.74–0.90, <p1, 0.04–0.3th pctil) — régimen actual no es único.
- En esos análogos, TSLA/MSFT/NVDA superan base en 20d (multiticker), hit>0 80-100% vs 54-66% base. Pero con n=10, IC Wilson cubre base.

**Evidencia en contra (más pesada — reforzada por growth3):**

- **Replicación fallida en growth/high-beta:** AMD (-0.25σ), AVGO (-0.06σ), META (+0.22σ) no replican TSLA (+0.67σ). Con 5 growth evaluados, Δ fwd20 ordena TSLA +12.27 > MSFT +5.84 > NVDA +5.40 > META +2.16 > AVGO -0.62 > AMD -4.29 — **el ticker de mayor vol (AMD 0.598) es el peor**, el de mediana vol (MSFT 0.276) es el segundo mejor. No hay monotonicidad vol→premia.
- **Heterogeneidad de outcome domina, también intra-growth:** mismos 10 análogos, fwd20 rangos AMD -16.5% a +26.2% (σ17% base), TSLA -0.37% a +38% (σ18%), META -6% a +13.3% (σ9.6%), AVGO -3.7% a +11.4% (σ9.9%). La dispersión es del orden de la vol base — el matching macro no reduce varianza idiosincrática.
- **Idiosincrático visible en mom_score actual vs análogos:** AMD actual 1.00 vs análogos 1.00/0.98/0.88 (homogéneo pero nivel extremo), META actual 0.172 vs análogos 0.517-0.611 (diverge), TSLA actual 0.339 vs 0.63-0.69 en 2017, MSFT 0.306 vs 0.58-0.61 — régimen macro similar ≠ momentum idio similar. AMD en momentum extremo 178% implica base distinta (no comparable a TSLA 0.9%).
- **Correlación growth colapsa en análogos:** NVDA–TSLA 0.05 vs 0.35 full, TSLA–AVGO -0.35 vs +0.38 full, TSLA–META -0.05 vs +0.31 — régimen macro no sincroniza growth. Full sample sí muestra covariación growth (NVDA-META 0.48, MSFT-META 0.50), pero desaparece en análogos.
- **Dist→outcome inconsistente**: signos mixtos (-0.22 MSFT a +0.63 AMD), no predice.
- **n=10 insuficiente y cluster temporal**: top-10 dominado por 2 clusters (2015-04 ×3, 2017-05/07 ×5) + 2 fechas 2019-12 — autocorrelación (consecutivos 2017-07-17/18, 2015-04-02/09/13). Un evento 2017 bull (NVDA +42% 2017-05-05) sesga agregado. Con 7 tickers ×2 k ×2 horizontes = 28 comparaciones implícitas, cualquier "premia" es ilusoria sin corrección BH/PBO.
- **Selección growth más extrema refuta hipótesis**: AMD es el stress test de high-beta — si el factor fuese vol, AMD debería liderar; lidera a la baja. Esto refuerza que TSLA es caso **idiosincrático** (auto/energy narrative, split, squeeze) no factor común.

**Implicación para idea de Cline (matching explícito para gates):**

- Esta extensión **no sostiene que el matching macro sea gate por sí solo para growth/high-beta** — la evidencia es mixta y, con growth ampliado, **más negativa** que con 4 tickers. Solo high-beta idiosincrático (TSLA) muestra premia; ampliado a 3 growth más, 2/3 son nulos/negativos y el tercero (META) es marginal.
- Matching continuo podría ser **feature adicional** (distancia al centroide HMM, kNN ponderado) pero requiere interacción `régimen × ticker` (no explorada) — el régimen puro no basta. Un gate que favorezca TSLA perjudicaría AMD en el mismo régimen.
- **No se duplica diseño de Cline:** no se propone umbral, gate ni backtest. Este piloto **NO es ese diseño** — es solo lectura que muestra que la hipótesis "high-beta growth sistemáticamente supera en calma VIX bajo" **no replica**.

---

## 9. Limitaciones (15 — 14 del multiticker + 1 nueva growth3)

1. **N pequeño y no OOS:** k=5/10 anecdótico (n=10 → SE mean fwd20 ≈ sd/√10: AMD 5.4pp, META 3.0pp, AVGO 3.1pp); IC 95% Wilson para hit>0 50% es 24-76%, 70% es 39-89% (cubre base 56-64%). Sin walk-forward ni corrección por múltiples comparaciones (k, horizonte, 7 tickers = 28 tests).
2. **Lookahead en fwd_ret:** `shift(-20/-60)` usa futuro; correcto para describir pero solapa ventanas (autocorrelación) y no es tradeable sin lag.
3. **Univariado por ticker, sin causalidad régimen→retorno:** macro→idio correlación no implica causalidad; momentum idio domina (AMD actual 178% vs META -24%).
4. **Muestral completo para μ/σ (leakage sutil):** z-score usa toda la muestra incluyendo futuro de cada t* (imposible en vivo). Rolling sería más causal pero introduce arbitrariedad y no replica HMM.
5. **Exclusión 60d arbitraria pero documentada:** sin exclusión, análogos serían t-1 triviales; con 60d se pierde análogo genuino dentro de 60d. Sensibilidad no explorada más allá de VIX×2.
6. **Ventana 60d fija:** 60d es del HMM, no validada para matching; régimen podría definirse mejor con vol 20/100d, Hurst, pendiente curva (indicators.py no usados).
7. **Estandarización ignora correlación:** euclídea asume Σ=I; features SPY-QQQ ρ~0.9, TLT-AGG correlacionadas — Mahalanobis daría distancias distintas (no probada como principal, nota §7).
8. **Precios split-ajustados y microestructura:** fwd crudo no descuenta costes/slippage; precios 2015 AMD 2.7 vs 514 hoy, AVGO 9.4 vs 393, META 80 vs 590 (liquidez/régimen distinto, splits, IPO 2012) — heterogeneidad estructural no controlada.
9. **Warmup momentum NaN:** 3/10 análogos 2015 sin mom_score (252d) — reduce n efectivo y sesga hacia 2017/2019.
10. **No etiquetar régimen discreto:** sin HMM fitted no hay "GOLDILOCKS" — distancia continua es proxy, no clasificación con transición.
11. **No estacionariedad 2015-2026:** QE/QT, COVID, AI boom, META IPO-post — distancia estacionaria puede emparejar z similar pero contexto estructural distinto (AMD 2015 penny vs 2026 mega-cap).
12. **Sensibilidad métrica limitada:** solo VIX×2 explorado; no L1, coseno, Mahalanobis shrinkage ni rolling z-score.
13. **[Multiticker] Selección de tickers y comparabilidad de base rates:** elección humana (no random) con criterio vol/corr explícito; base rates muy distintas (AMD 5.04% vs KO 0.84% a 20d) — Δ vs base no comparable en absoluto; sin normalizar por vol (Δ/σ) se exagera high-beta. Comparar Δ sin dividir por σ exagera high-beta (corregido en §5.3 con Δ/σ).
14. **[Multiticker] Análogos compartidos vs heterogeneidad de outcomes:** distancia macro-pura → 10 análogos idénticos por construcción — no se testea matching per-ticker (con features idiosincráticas) que daría ranking distinto. Correlación inter-ticker en análogos (NVDA–TSLA 0.05 vs -0.08 NVDA–KO en multiticker) sugiere matching macro insuficiente; haría falta interacción régimen×ticker, no explorada.
15. **[NUEVA growth3] Selección growth y contraste con TSLA:** ampliar solo growth/high-beta (AMD/META/AVGO) introduce sesgo de selección hacia cola alta-vol (p99–p75) sin grupo control defensivo adicional; el contraste correcto habría sido ampliar balanceado (1 high, 1 defensive, 1 SMID) para testar monotonicidad. Además, heterogeneidad intra-growth (semis puro vs plataforma vs diversificado) es mayor que la diferencia growth-vs-defensivo: AMD -0.25σ vs AVGO -0.06σ vs META +0.22σ vs NVDA +0.41σ en mismos análogos — el "factor growth" no es coherente ni extraíble. La conclusión "TSLA idiosincrático" depende de n=10 y del outlier actual de AMD (mom 178%): si AMD estuviese en mom 0.3 como TSLA, su outcome podría diferir. No se controla por mom_score actual (confounder).

---

## 10. Trazabilidad

- **Código leído:** `backend/app/core/regime_classifier.py:34-55,1-210` (features 9-d, `is_fitted=False` → GOLDILOCKS default), `backend/app/core/signal_engine.py:73-90,137` (momentum_score), `backend/app/core/indicators.py:25-30,381` (RSI, mom_12_1), `backend/app/core/backtest_engine.py:23` (horizonte 20d), `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (vol_ann, corr SPY, ICs), `PILOTO_REGIME_MATCHING_MULTITICKER.md §2-6` (matriz, μ/σ, ranking, base rates).
- **Parquet solo lectura (60 archivos, 2921-2923 filas c/u):** `SPY.parquet` (→2026-08-14, 776.34), `EFA/QQQ/GLD/DBC/TIP/TLT/AGG/^VIX.parquet` (→2026-08-17 pero truncado a 2026-08-14 para vector actual, VIX 14.25), `AMD.parquet` (514.39), `META.parquet` (589.85), `AVGO.parquet` (392.99) + `NVDA/KO/TSLA/MSFT.parquet` de referencia (225.16/87.71/342.27/495.40) — verificados `pd.read_parquet` solo lectura, no modificados, `ls backend/data/cache/*.parquet` 60 archivos.
- **Scripts efímeros solo-lectura (/tmp, no trackeados):** `piloto_regime.py` (matriz 2863×9, scaler μ/σ, dists n=2801, `np.save /tmp/dists.npy`, `/tmp/feat_df.csv` 2863×9, `/tmp/distances.csv` 2801 + top-10 0.7405-0.9010), `piloto_nvda.py` (base rate + outcome), `piloto_extra.py/extra2/extra3/check_feat_detail.py` (scaler params, HMM invocabilidad, permutation p≈0.10) — reusados verbatim multiticker. Nuevo ` /tmp/piloto_growth3.py ` (este hito: snapshot AMD/META/AVGO, base rates 2901/2861, fwd por análogo 10 fechas, agregado k5/k10, corr 7×7 fwd20/60 en 10 análogos + full 2901, Δ/σ, corr dist→outcome) — `python3 /tmp/piloto_growth3.py` inline, no persiste modelo.
- **Matriz & métrica congeladas verificadas:** `feat_df.csv` 2863×9 `tail -1` 2026-08-14 0.0608/0.0828/0.0433/-0.024/-0.051/-0.0001/-0.0002/0.0087/14.25; `scaler.mean_/_scale_` coinciden verbatim con tabla §2.1; `distances.csv` 2801 filas, stats min 0.7405 p5 1.39 median 2.66 max 12.95 mean 3.02 sd 1.50 — idéntico a pilotos previos; ranking top-10 idéntico (2015-04-13 … 2019-12-03) — se **reusó sin recalcular**, solo lectura.
- **Verificación no-escritura:** `git status --porcelain` previo/vacío (o solo `?? PILOTO_REGIME_MATCHING_GROWTH3.md` tras escritura de este archivo); `git diff --stat` sin cambios en `backend/data/cache/*.parquet`, `fortress.db`, `trial_registry`, `ledger`; `git log --oneline -3` b41c1a1/38ef62c/d199899 intactos. No se tocó `PRE_REGISTRO_*`, `ONBOARDING.md`, `ROADMAP.md`.
- **Métrica congelada:** euclídea z-score muestral declarada en §2 de los 3 pilotos antes de cualquier `np.linalg.norm`; sensibilidad VIX×2 ya reportada separada en multiticker §7 — no se añadió como principal aquí.

---

## 11. Entrega y handoff

**Archivo:** `PILOTO_REGIME_MATCHING_GROWTH3.md` (este archivo, raíz worktree `/Users/boris/orca/workspaces/fortress_core/test-opencode-orca/PILOTO_REGIME_MATCHING_GROWTH3.md`) — referencia a `PILOTO_REGIME_MATCHING_MULTITICKER.md` (380L, b41c1a1) y `PILOTO_REGIME_MATCHING_NVDA.md` (239L, 38ef62c) no tocados.

**Stats clave growth3 (k=10, fwd20 primario):**

| Ticker | vol_ann | base mean fwd20 | k10 mean | **Δ** | Δ/σ | hit>0 k10 vs base | k10 mean fwd60 | Δ fwd60 |
|--------|---------|-----------------|----------|-------|-----|-------------------|-----------------|---------|
| **TSLA (previo, único con ventaja)** | 0.572 | 3.73% | 16.01% | **+12.27pp** | +0.67 | 90% vs 54% | 32.46% | +20.73pp |
| MSFT (previo) | 0.276 | 1.92% | 7.75% | +5.84pp | **+0.89** | 100% vs 63% | 7.30% | +1.59pp |
| NVDA (previo) | 0.482 | 5.12% | 10.52% | +5.40pp | +0.41 | 80% vs 66% | 15.79% | -0.47pp |
| **META (nuevo)** | 0.379 | 1.89% | 4.05% | +2.16pp | +0.22 | 70% vs 61% | 5.17% | -0.81pp |
| KO (previo) | 0.179 | 0.84% | 2.11% | +1.27pp | +0.28 | 90% vs 60% | 0.96% | -1.48pp |
| **AVGO (nuevo)** | 0.395 | 3.22% | 2.60% | -0.62pp | -0.06 | 60% vs 64% | 0.59% | **-8.85pp** |
| **AMD (nuevo)** | 0.598 | 5.04% | 0.74% | **-4.29pp** | **-0.25** | 50% vs 56% | 1.31% | **-14.61pp** |

*Con n=10, cualquier "Δ" tiene SE 3-5pp y p de permutación no significativo; heterogeneidad intra-growth (-0.25σ a +0.67σ) domina.*

**Veredicto sintético (español, solo-lectura):** el patrón **TSLA no se replica** sistemáticamente en growth/high-beta. De 5 growth evaluados en el mismo régimen (NVDA/TSLA/AMD/META/AVGO), solo TSLA muestra premia económica grande; el más volátil (AMD 0.598) es negativo, AVGO nulo, META marginal. El mejor Δ/σ es MSFT (mediana vol, no high-beta). La correlación growth-growth colapsa en análogos (NVDA-TSLA 0.05 vs 0.35 full; TSLA-AVGO -0.35 vs +0.38). **Ventaja TSLA es idiosincrática, no factor growth/high-beta.** Esto debe leerse como **no evidencia** para gate macro sistemático en growth — requiere interacción régimen×ticker y validación walk-forward causal con costes si se quiere rigor.

**No commit aún** — archivo nuevo untracked `PILOTO_REGIME_MATCHING_GROWTH3.md`, previos commits intactos, parquet/db/registry no tocados. Orquestador commiteará.

---

*Piloto solo-lectura — no ledger, no trial_registry, no pre-registro. Segunda extensión concreta del piloto NVDA→multiticker sobre matriz y métrica congeladas (2863×9, μ/σ §2.1, L2 z-space, exclusión 60d, fecha 2026-08-14, ranking 2801 top-5/10 idéntico) ampliada a 3 growth/high-beta para test de replicación TSLA — heterogeneidad e idiosincrasia documentadas, sin narrativa forzada.*
