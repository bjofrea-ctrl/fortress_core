# Diagnóstico de Heterogeneidad VIX ROLLING 240d + Gate Eligible — IC Condicional

**Fecha**: 2026-09-01 (tercera iteración)
**Autor**: Muse Spark (diagnóstico solo-lectura, extensión de DIAGNOSTICO_HETEROGENEIDAD_VIX_REGIMEN.md §12)
**Restricción dura**: SOLO LECTURA de `backend/data/cache/*.parquet` existente — sin nuevo backtest, sin tocar `ledger`/`trial_registry`, sin pre-registro. Es diagnóstico descriptivo, no veredicto de trading.
**Fuente parquet**: `backend/data/cache/*.parquet` (worktree `test-opencode-orca`)
**Rango temporal real**: 2015-01-02 → 2026-08-14 (equities, 2921 filas por ticker; ^VIX llega a 2026-08-17, 2923 filas)
**N efectivo**: 57 parquet (50 universo canónico +7 market). Este diagnóstico corre sobre **50 universo** como primario; 7 market como referencia no mezclada.
**Universo**: `backend/scripts/fetch_universe_data.py:NEW_UNIVERSE` (43) + `_BASE_SYMBOLS` (7) = 50 — ver `backend/app/api/routes/opportunities_universe.py:19-35`

> **Objetivo**: replicar el test defensivas vs growth por régimen VIX pero con metodología mejorada que corrige dos limitaciones R2/R3 documentadas: deriva secular de VIX level y IC incondicional ruidoso. Implementa **VIX rank rolling 240d** (régimen relativo) y **IC dentro del gate eligible** (IC condicional).

## 1. VIX Rank Rolling 240d — inventario y fórmula

**Archivo**: `backend/data/cache/^VIX.parquet` — 2923 filas, índice `Date`, `Close` float64. Rango VIX close 9.14→82.69, media 18.36, sd 6.98, mediana 16.68.

**Fórmula exacta usada (primaria)**:

```
para cada día t:
  ventana trailing W_t = VIX_close[t-239 .. t]  (240 días, inclusive t)
  si len(W_t) < 240 → rank = NaN (excluye esos días; no usa ventana parcial)
  rank = posición ordinal de VIX_close[t] dentro de W_t ordenada ascendente, ties método average
  percentile rank_240d[t] = (rank - 1) / (len(W_t) - 1)   ∈ [0, 1]
```

Equivalente a `pandas Series(W_t).rank(method='average', pct=False)` transformado a `[0,1]` como `(r-1)/(n-1)`. Sensibilidad `rank(pct=True)` = `r/n` ∈ (0,1] difiere ≤0.004 (1/240); correlación entre ambas definiciones = **1.000**.

Implementación: `pandas rolling(window=240, min_periods=240).apply(lambda w: (pd.Series(w).rank(method='average').iloc[-1]-1)/(len(w)-1))` — causal, inclusive, sin lookahead.

**Distribución del rank (validación de uniformidad)**:

| estadístico | valor |
|-------------|-------|
| N válidos | **2684** (2923 − 239 warmup) |
| media | 0.4577 |
| mediana | 0.4561 |
| sd | 0.3150 |
| min / max | 0.0000 / 1.0000 |
| p10 / p90 | 0.0377 / 0.9079 |
| p25 / p50 / p75 | 0.159 / 0.456 / 0.731 |
| histograma 10 bins [0,0.1)...[0.9,1] | [491, 296, 232, 215, 202, 250, 250, 245, 214, 289] (esperado uniforme ≈268 por bin) |

Lectura: distribución **aprox uniforme pero no perfecta**: exceso en cola izquierda (rank≈0, VIX muy bajo relativo a 240d) con 491 obs en bin [0,0.1] vs 289 en [0.9,1]. Media 0.458 <0.50 indica leve sesgo a VIX relativo bajo en el periodo (VIX tendió a comprimir post-COVID vs máximos 2020). Desviación menor, aceptable para bucket 50/50.

**Definición de régimen rolling**:

- **Risk-on (VIX bajo relativo)** = `rank_240d < 0.5` (percentil por debajo de mediana trailing)
- **Risk-off (VIX alto relativo)** = `rank_240d ≥ 0.5`
- Sensibilidad terciles rolling: **low** = `rank ≤ 0.33`, **high** = `rank ≥ 0.66`, medio (0.33,0.66) descartado.

**N días globales por bucket (sobre serie VIX rank 2684 válidos)**:

| bucket | N | % de válidos |
|--------|---|--------------|
| Risk-on (rank<0.5) | **1436** | 53.5% |
| Risk-off (rank≥0.5) | **1248** | 46.5% |
| Low tercil (≤0.33) | **1083** | 40.3% |
| High tercil (≥0.66) | **860** | 32.0% |
| Medio descartado (0.33-0.66) | **741** | 27.6% |

Asimetría leve (53.5/46.5) proviene de media rank <0.5. Terciles no son 33/33/33 exactos por discreta y ties, pero cercanos.

**N por ticker por bucket (efectivo tras merge ticker ⨝ VIX rank, antes de gate)**:

Mediana por ticker (N=50): n_on_total≈1434, n_off_total≈1248, n_low_total≈1082, n_high_total≈860 (todos >800, idéntico a global porque todos los tickers comparten calendario; diferencias <2 por feriados).

**N por ticker por bucket eligible (tras gate, efectivo para IC)**:

| | mediana | media | sd | min | max | p10 | p90 |
|---|---------|-------|----|-----|-----|-----|-----|
| n_elig_total | 326 | 317 | 51 | 191 | 407 | 256 | 371 |
| n_on_elig | 172.5 | 176 | 33 | 104 | 257 | 132 | 213 |
| n_off_elig | 125.5 | 123 | 33 | 48 | 178 | 82 | 159 |
| n_low_elig | 129.5 | 130 | 28 | 77 | 195 | 95 | 157 |
| n_high_elig | 82.0 | 80 | 28 | 29 | 126 | 44 | 103 |

Un ticker con n_high_elig=29 queda con **IC=NaN** por regla <30 (1 caso: DIS high bucket 48→29 tras dropna fwd).

Justificación del rank rolling: adapta a **deriva secular** (VIX 17 en 2017 ≠ VIX 17 en 2022) porque mide posición relativa dentro de 240d (~1 año hábil). Captura régimen relativo, no nivel absoluto; corrige limitación R2 del diagnóstico anterior que usaba mediana muestral 16.68 fija (no estacionaria, confunde era con régimen).

## 2. Gate eligible del motor — definición exacta y trazabilidad

**Localización código**:

- `backend/app/core/signal_engine.py:158-175` — `compute_factor_frame()` define `eligible`
- `backend/app/core/signal_engine.py:208-217` — `generate_signal()` aplica gates duros idénticos + `overall >=0.60`
- `backend/app/core/indicators.py:9-59,370-411` — fórmulas exactas de indicadores

**Gates (todos deben pasar para eligible==True)**:

| gate | línea | condición exacta | fórmula del indicador |
|------|-------|------------------|-----------------------|
| **Trend** | `signal_engine.py:158` | `close > ema50 > ema200` (estricto) — ambas desigualdades deben cumplirse | `ema(span=N, adjust=False)` — `pandas ewm(span=N, adjust=False).mean()` sobre `close` — `indicators.py:9-10` |
| **ADX** | `:170` / `:210` | `adx14 ≥ 20` | `adx()` `indicators.py:48-59`: `plus_dm=high.diff().clip(lower=0)`, `minus_dm=-low.diff().clip(upper=0)`, `TR=max(high-low, abs(high-close.shift()), abs(low-close.shift()))`, `atr = TR.rolling(14).mean()`, `plus_di=100*plus_dm.rolling(14).mean()/atr`, `minus_di` análogo, `dx=100*abs(plus_di-minus_di)/(plus_di+minus_di)`, `adx=dx.rolling(14).mean()` |
| **RSI** | `:170` / `:212` | `40 < rsi14 < 75` (estricto) | `rsi()` `indicators.py:25-30`: `delta=close.diff()`, `gain=delta.where(delta>0,0).rolling(14).mean()`, `loss=-delta.where(delta<0,0).rolling(14).mean()`, `rs=gain/loss`, `rsi=100-100/(1+rs)` |
| **Vol ratio** | `:170` / `:214` | `volume / sma(volume,20) ≥ 1.0` | `volume_sma20 = volume.rolling(20).mean()` — `indicators.py:13-14,379-380`, `volume_ratio=volume/volume_sma20` |
| **Score** | `:216` solo en `generate_signal` | `overall = mom*0.664 + rsi*0.336 ≥ 0.60` — **NO incluido en `compute_factor_frame().eligible`** | `momentum_score = clip((momentum_12_1+50)/150,0,1)` — `signal_engine.py:137`, `rsi_score=0.8 si 45<rsi<70 else 0.4` — `:141`, pesos `0.6639/0.3361` — `signal_engine.py:85-86` |

> **Decisión de este diagnóstico**: `eligible` primario = `compute_factor_frame` (4 gates sin score) — es el filtro **condicional** que importa para medir IC dentro de la población candidata a trade, sin condicionar en la propia variable de score (que truncaría su distribución y sesgaría la correlación). Sensibilidad con `overall≥0.60` se reporta separadamente.

**Replicación en este diagnóstico**:

- Para cada ticker parquet, se derivan `ema50`, `ema200`, `rsi14`, `adx14`, `volume_sma20`, `volume_ratio` con **mismas fórmulas pandas** (ewm adjust=False, rolling mean idéntico). Sin `ffill` final: NaNs mantienen `eligible=False` (líneas 370-411 hacen `ffill().dropna()` en pipeline real; aquí se preserva NaN como no eligible, desviación mínima documentada y conservadora).
- Se evalúa `eligible = trend_ok & adx>=20 & rsi>40 & rsi<75 & vol_ratio>=1.0` fila a fila.
- Luego se hace `merge` con `VIX rank_240d` por `Date` (inner, sin forward-fill) y se filtra `eligible==True` **antes** de correlacionar.

**Tasa de elegibilidad**:

| métrica | valor |
|---------|-------|
| n_elig_total mediano por ticker | **326** filas (sobre 2921, 11.2%) |
| tasa elegibilidad media | **10.86%** (mediana 11.16%, rango 6.5%-13.9%, sd 1.76%) |
| min / max | 191 (PFE) / 407 (SPGI) |
| con score≥0.60 (sensibilidad) | mediana **~140** filas, total universo **7318** filas (~6-7% del total, ~60% de los eligible) |
| pooled eligible (concat 50 tickers, dropna) | on **8651** / off **6163** / low **6495** / high **3978** filas válidas (mom_score,fwd) |
| pérdida de N vs diagnóstico incondicional | antes n≈1300 por bucket; ahora **≈173 on / 126 off** (caída **~87%**, SE( Pearson ) ≈1/√n sube de 0.028 a **0.076 on / 0.089 off**, SE(Δ) ≈0.12) |

La elegibilidad filtrada es **selectiva**: solo ~1 de cada 9 días pasa el cuarteto trend/adx/rsi/vol. Esto condiciona varianza (ver limitación 15).

## 3. IC por ticker por régimen (eligible) — metodología

**Fórmulas score idénticas al diagnóstico anterior** (`signal_engine.py:137-142`, `backtest_engine.py:23`):

```
momentum_12_1 = close.pct_change(252)*100
momentum_score = clip((momentum_12_1 + 50)/150, 0, 1)
rsi14 = RSI(14) SMA gains/losses  (indicators.py:25-30)
rsi_score = 0.8 si 45 < rsi14 < 70 else 0.4
fwd_ret_20d = close.shift(-20)/close - 1   (CALIBRATION_HORIZON_DAYS=20)
ic_mom  = Pearson_corr(momentum_score, fwd_ret_20d)   primario
ic_rsi  = Pearson_corr(rsi_score, fwd_ret_20d)
Spearman análogo sensibilidad
dropna del par (score,fwd); mínimo 30 pares → si <30 → NaN
```

**Procedimiento**: sobre filas `eligible==True`, se particiona por `rank_240d` bucket y se correla por ticker y bucket (`ic_mom_on_elig`, `ic_mom_off_elig`, etc.). `delta = IC_on - IC_off` (risk-on minus risk-off; positivo = mejor en VIX bajo relativo). Terciles `low≤0.33` vs `high≥0.66` análogo `delta_terc = low - high`. Pooled eligible: concat todas las filas eligible del grupo 50 por bucket y correla una vez.

## 4. Pooled eligible por régimen

| IC pooled eligible | Pearson | Spearman | n (filas eligible válidas, 50 tickers concat) |
|--------------------|---------|----------|-----------------------------------------------|
| **Mom on (rank<0.5)** | **+0.0593** | +0.0225 | 8651 |
| **Mom off (rank≥0.5)** | **+0.0696** | +0.0239 | 6163 |
| **Δ mom on−off** | **−0.0103** | −0.0014 | — |
| **Mom low (≤0.33)** | **+0.0937** | +0.0563 | 6495 |
| **Mom high (≥0.66)** | **+0.1012** | +0.0590 | 3978 |
| **Δ terc mom low−high** | **−0.0075** | −0.0027 | — |
| **RSI on** | **−0.0093** | −0.0069 | 8651 |
| **RSI off** | **+0.0084** | −0.0007 | 6163 |
| **RSI low** | **−0.0053** | −0.0063 | 6495 |
| **RSI high** | **+0.0195** | +0.0021 | 3978 |

**Lectura pooled eligible**:

- Momentum pooled se vuelve **ligeramente positivo** en ambos regímenes tras gate (+0.059 on / +0.070 off) vs incondicional +0.022/-0.004 anteriormente. El gate eleva el nivel ~3-7pp, pero el **diferencial entre regímenes es nulo** (−0.01). Terciles confirman: low +0.094 vs high +0.101, Δ≈−0.008. No hay régimen-dependencia pooled tras condicionar en eligible; ningún bucket supera +0.10.
- RSI pooled sigue **acíclico** (~0 en ambos buckets, rango −0.009 a +0.020). Spearman replica Pearson.
- Conclusión: el gate no rescata señal por régimen a nivel agregado; solo desplaza el nivel medio de mom de levemente negativo/cero a levemente positivo, sin crear separación on/off.

## 5. Tabla cruda por ticker (50 universo — Pearson primario, eligible)

Columnas: `ticker | grupo | vol_ann | n_elig_total | n_on_elig | n_off_elig | ic_mom_on_elig | ic_mom_off_elig | Δmom | ic_rsi_on | ic_rsi_off | Δrsi | ic_mom_low | ic_mom_high | Δterc_mom | n_low | n_high`. Spearman en Apéndice A. Δ = on − off (positivo = mejor en VIX bajo relativo). n_* son pares válidos (score,fwd) por bucket, tras dropna.

| ticker | grupo | vol_ann | n_elig_total | n_on_elig | n_off_elig | ic_mom_on_elig | ic_mom_off_elig | Δmom | ic_rsi_on_elig | ic_rsi_off_elig | Δrsi | ic_mom_low_elig | ic_mom_high_elig | Δterc_mom | n_low_elig | n_high_elig |
|--------|-------|---------|--------------|-----------|------------|----------------|-----------------|------|----------------|-----------------|------|---------------|---------------|------------|------------|-------------|
| AAPL | Resto | 0.2878 | 340 | 160 | 161 | -0.2012 | 0.1585 | -0.3597 | -0.1636 | 0.1054 | -0.2690 | -0.2800 | -0.0057 | -0.2743 | 126 | 93 |
| ABBV | Defensiva_manual | 0.2664 | 338 | 187 | 139 | 0.1928 | -0.1571 | 0.3499 | 0.0428 | 0.0251 | 0.0177 | 0.3047 | -0.2544 | 0.5591 | 141 | 103 |
| ACN | Resto | 0.2723 | 363 | 199 | 127 | 0.0103 | -0.0419 | 0.0522 | -0.0197 | -0.1109 | 0.0912 | 0.0616 | 0.0132 | 0.0484 | 143 | 77 |
| ADBE | Growth_manual | 0.3370 | 326 | 159 | 133 | -0.2380 | 0.1231 | -0.3611 | -0.1070 | 0.0588 | -0.1658 | -0.2445 | 0.2454 | -0.4899 | 124 | 84 |
| AMD | Growth_manual | 0.5983 | 271 | 163 | 108 | -0.2154 | 0.0753 | -0.2907 | 0.0939 | 0.0430 | 0.0509 | -0.1322 | 0.2560 | -0.3882 | 122 | 60 |
| AMGN | Resto | 0.2520 | 263 | 127 | 125 | -0.1589 | -0.2141 | 0.0552 | 0.0975 | -0.0409 | 0.1384 | -0.1654 | -0.1177 | -0.0476 | 95 | 83 |
| AMZN | Resto | 0.3314 | 372 | 194 | 139 | 0.1577 | -0.0897 | 0.2474 | 0.0566 | -0.0044 | 0.0610 | 0.1843 | -0.1100 | 0.2943 | 147 | 89 |
| AVGO | Growth_manual | 0.3953 | 391 | 257 | 116 | 0.0051 | 0.0457 | -0.0405 | 0.0294 | 0.0426 | -0.0131 | 0.0334 | 0.1418 | -0.1084 | 195 | 79 |
| BAC | Resto | 0.3037 | 296 | 181 | 105 | -0.1769 | 0.1722 | -0.3491 | -0.0419 | -0.0193 | -0.0226 | -0.1771 | 0.2345 | -0.4116 | 137 | 64 |
| BRK-B | Resto | 0.1909 | 326 | 202 | 124 | -0.0324 | 0.2387 | -0.2711 | 0.1773 | -0.1424 | 0.3196 | 0.0153 | 0.3255 | -0.3102 | 160 | 80 |
| CAT | Resto | 0.3080 | 292 | 175 | 117 | 0.3316 | 0.0251 | 0.3064 | -0.0748 | 0.0565 | -0.1313 | 0.3652 | 0.0541 | 0.3111 | 135 | 74 |
| CMCSA | Resto | 0.2591 | 290 | 179 | 84 | -0.2289 | -0.1946 | -0.0343 | 0.0333 | -0.0080 | 0.0413 | -0.2388 | -0.1706 | -0.0681 | 132 | 45 |
| COST | Defensiva_manual | 0.2154 | 361 | 155 | 178 | -0.0787 | -0.1100 | 0.0313 | -0.0359 | -0.1232 | 0.0873 | -0.0840 | -0.1189 | 0.0349 | 117 | 112 |
| CRM | Growth_manual | 0.3541 | 304 | 158 | 116 | -0.0927 | 0.1843 | -0.2770 | -0.0345 | -0.0181 | -0.0164 | -0.1085 | 0.1934 | -0.3019 | 109 | 73 |
| CSCO | Resto | 0.2594 | 291 | 145 | 124 | -0.1669 | -0.0666 | -0.1003 | -0.0012 | -0.2510 | 0.2497 | -0.0750 | -0.2908 | 0.2158 | 98 | 79 |
| CVX | Resto | 0.2901 | 242 | 128 | 114 | -0.1701 | 0.1722 | -0.3423 | -0.2215 | 0.2631 | -0.4846 | -0.2435 | 0.2382 | -0.4817 | 91 | 88 |
| DIS | Resto | 0.2802 | 191 | 104 | 48 | -0.4032 | 0.0220 | -0.4253 | 0.0182 | 0.0835 | -0.0653 | -0.3821 | nan | nan | 78 | 29 |
| GE | Growth_manual | 0.3473 | 245 | 137 | 82 | -0.2075 | 0.0748 | -0.2823 | -0.0944 | -0.2662 | 0.1718 | -0.3382 | 0.0367 | -0.3749 | 105 | 60 |
| GOOGL | Resto | 0.2913 | 355 | 192 | 136 | -0.0713 | -0.0631 | -0.0082 | -0.0686 | -0.0735 | 0.0050 | 0.0075 | 0.0736 | -0.0661 | 149 | 85 |
| HD | Resto | 0.2442 | 291 | 165 | 98 | -0.2226 | -0.3062 | 0.0836 | 0.1063 | 0.3143 | -0.2081 | -0.1134 | -0.3659 | 0.2524 | 121 | 69 |
| IBM | Resto | 0.2728 | 228 | 142 | 79 | -0.0550 | 0.1409 | -0.1959 | -0.0640 | 0.0279 | -0.0919 | -0.0319 | 0.0559 | -0.0878 | 108 | 56 |
| INTU | Growth_manual | 0.3329 | 358 | 188 | 143 | 0.1107 | 0.0257 | 0.0850 | -0.0330 | -0.0167 | -0.0163 | 0.1599 | 0.1394 | 0.0205 | 129 | 99 |
| JNJ | Defensiva_manual | 0.1832 | 283 | 154 | 126 | 0.3890 | 0.1487 | 0.2403 | -0.0480 | 0.0748 | -0.1228 | 0.4091 | 0.2045 | 0.2046 | 108 | 82 |
| JPM | Resto | 0.2696 | 329 | 222 | 92 | -0.2471 | 0.0753 | -0.3223 | 0.0328 | -0.1512 | 0.1840 | -0.2376 | 0.0427 | -0.2804 | 158 | 54 |
| KO | Defensiva_manual | 0.1791 | 319 | 165 | 141 | 0.1200 | -0.3888 | 0.5088 | 0.1058 | -0.0024 | 0.1082 | 0.1275 | -0.4315 | 0.5590 | 124 | 102 |
| LIN | Resto | 0.2239 | 342 | 226 | 116 | 0.0350 | -0.3123 | 0.3473 | -0.0210 | 0.0401 | -0.0611 | 0.1049 | -0.3754 | 0.4803 | 179 | 76 |
| LLY | Resto | 0.2979 | 318 | 169 | 119 | 0.0458 | -0.1478 | 0.1936 | -0.1176 | 0.1819 | -0.2995 | -0.0434 | 0.1263 | -0.1697 | 123 | 82 |
| MA | Resto | 0.2626 | 379 | 204 | 151 | 0.1226 | -0.0259 | 0.1484 | 0.1294 | -0.0548 | 0.1841 | 0.1774 | 0.0126 | 0.1648 | 163 | 100 |
| MCD | Defensiva_manual | 0.2021 | 372 | 167 | 170 | -0.0162 | -0.2177 | 0.2016 | -0.1513 | 0.0583 | -0.2095 | 0.1048 | -0.2545 | 0.3593 | 128 | 113 |
| META | Growth_manual | 0.3785 | 332 | 202 | 96 | 0.2780 | 0.0504 | 0.2276 | -0.0531 | 0.0744 | -0.1274 | 0.3139 | -0.0393 | 0.3532 | 160 | 61 |
| MRK | Resto | 0.2276 | 286 | 152 | 126 | -0.0212 | -0.0988 | 0.0776 | 0.0137 | -0.0666 | 0.0804 | 0.0787 | -0.0913 | 0.1700 | 114 | 86 |
| MSFT | Resto | 0.2762 | 349 | 190 | 152 | 0.0290 | -0.2727 | 0.3017 | 0.0512 | 0.0468 | 0.0044 | 0.1704 | -0.1684 | 0.3388 | 147 | 95 |
| NFLX | Growth_manual | 0.4259 | 319 | 150 | 126 | -0.0264 | -0.2876 | 0.2612 | -0.0429 | -0.0725 | 0.0296 | 0.0180 | -0.2042 | 0.2222 | 121 | 99 |
| NVDA | Growth_manual | 0.4819 | 399 | 216 | 150 | -0.0359 | 0.0608 | -0.0966 | -0.0772 | -0.0386 | -0.0386 | -0.0151 | 0.0141 | -0.0292 | 164 | 102 |
| ORCL | Resto | 0.3423 | 290 | 194 | 90 | -0.2129 | -0.2470 | 0.0341 | 0.1223 | 0.0659 | 0.0564 | -0.1168 | -0.1797 | 0.0628 | 144 | 41 |
| PEP | Defensiva_manual | 0.1923 | 348 | 193 | 132 | -0.0360 | -0.1126 | 0.0766 | -0.0020 | 0.0902 | -0.0921 | 0.2288 | -0.1918 | 0.4206 | 148 | 96 |
| PFE | Resto | 0.2337 | 271 | 111 | 123 | 0.1628 | -0.3455 | 0.5083 | 0.1516 | -0.0204 | 0.1720 | 0.3400 | -0.3970 | 0.7370 | 81 | 73 |
| PG | Defensiva_manual | 0.1868 | 309 | 160 | 149 | 0.0539 | 0.0220 | 0.0319 | -0.0480 | 0.1056 | -0.1536 | 0.0381 | -0.0217 | 0.0599 | 140 | 103 |
| PM | Defensiva_manual | 0.2380 | 297 | 160 | 122 | -0.0166 | 0.3193 | -0.3359 | -0.0621 | -0.1522 | 0.0901 | -0.0830 | 0.2959 | -0.3789 | 122 | 86 |
| QCOM | Growth_manual | 0.3862 | 229 | 138 | 91 | -0.1893 | -0.0252 | -0.1641 | 0.0048 | -0.1558 | 0.1606 | -0.2449 | 0.0872 | -0.3321 | 102 | 50 |
| QQQ | Resto | 0.2196 | 407 | 215 | 165 | -0.0566 | -0.2091 | 0.1525 | -0.0088 | 0.1339 | -0.1427 | 0.0163 | -0.1649 | 0.1812 | 154 | 99 |
| SPGI | Resto | 0.2605 | 374 | 226 | 139 | 0.1996 | -0.0520 | 0.2515 | -0.0354 | 0.1120 | -0.1473 | 0.3471 | 0.1778 | 0.1693 | 170 | 78 |
| SPY | Resto | 0.1760 | 401 | 220 | 168 | 0.0523 | -0.1205 | 0.1728 | -0.0157 | -0.0145 | -0.0013 | 0.1748 | -0.1222 | 0.2970 | 149 | 96 |
| TMO | Resto | 0.2592 | 343 | 170 | 146 | 0.0650 | -0.2310 | 0.2960 | 0.2162 | -0.0963 | 0.3125 | 0.0316 | -0.1450 | 0.1767 | 120 | 90 |
| TSLA | Growth_manual | 0.5720 | 233 | 131 | 90 | 0.2111 | 0.3420 | -0.1309 | -0.1045 | 0.0525 | -0.1569 | 0.2047 | 0.4049 | -0.2002 | 101 | 68 |
| TXN | Resto | 0.3090 | 328 | 185 | 132 | 0.0335 | -0.2978 | 0.3313 | 0.0202 | 0.0346 | -0.0144 | 0.0572 | -0.1236 | 0.1808 | 140 | 82 |
| UNH | Defensiva_manual | 0.2940 | 349 | 187 | 139 | 0.1608 | 0.0394 | 0.1214 | -0.0283 | 0.0700 | -0.0983 | 0.2369 | 0.0230 | 0.2139 | 130 | 89 |
| V | Resto | 0.2423 | 364 | 209 | 125 | 0.0131 | -0.0658 | 0.0789 | 0.0449 | 0.0088 | 0.0361 | 0.0382 | -0.0565 | 0.0947 | 161 | 78 |
| WMT | Defensiva_manual | 0.2176 | 343 | 182 | 161 | -0.0081 | 0.0397 | -0.0478 | 0.0571 | 0.0595 | -0.0025 | 0.1792 | 0.0412 | 0.1380 | 133 | 104 |
| XOM | Resto | 0.2751 | 219 | 112 | 107 | -0.3885 | 0.1868 | -0.5753 | -0.0602 | -0.0210 | -0.0391 | -0.3971 | 0.1740 | -0.5711 | 82 | 77 |

**Notas**: `n_on_elig`/`n_off_elig` son filas eligible válidas por bucket; todos los tickers superan 30 salvo 1 celda high (DIS high n=48→29 tras dropna fwd → NaN). Mediana n_on_elig 172.5 vs n_off_elig 125.5 — asimetría refleja distribución rank 53.5/46.5 y composición temporal del gate. `grupo` = Defensiva_manual (N=10), Growth_manual (N=11), Resto.

## 6. Dispersión por régimen (universo 50, eligible)

| Régimen — métrica | media | mediana | sd | CV | min | max | rango | p10 | p90 | p10-p90 | IQR | N |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MOM on eligible (rank<0.5) | -0.0239 | -0.0189 | 0.1723 | 7.21 | -0.4032 | +0.3890 | 0.7923 | -0.2233 | +0.1935 | 0.4167 | 0.2316 | 50 |
| MOM off eligible (rank≥0.5) | -0.0392 | -0.0339 | 0.1784 | 4.55 | -0.3888 | +0.3420 | 0.7308 | -0.2886 | +0.1734 | 0.4620 | 0.2604 | 50 |
| Δ MOM (on−off) | +0.0153 | +0.0537 | 0.2592 | 16.96 | -0.5753 | +0.5088 | 1.0841 | -0.3430 | +0.3089 | 0.6519 | 0.4091 | 50 |
| RSI on eligible | -0.0046 | -0.0177 | 0.0879 | 19.05 | -0.2215 | +0.2162 | 0.4377 | -0.1047 | +0.1079 | 0.2126 | 0.1028 | 50 |
| RSI off eligible | +0.0062 | +0.0170 | 0.1105 | 17.90 | -0.2662 | +0.3143 | 0.5805 | -0.1433 | +0.1063 | 0.2495 | 0.1157 | 50 |
| Δ RSI | -0.0108 | -0.0078 | 0.1548 | 14.34 | -0.4846 | +0.3196 | 0.8042 | -0.1700 | +0.1732 | 0.3432 | 0.2022 | 50 |
| MOM low tercil (rank≤0.33) | +0.0155 | +0.0248 | 0.2037 | 13.11 | -0.3971 | +0.4091 | 0.8062 | -0.2445 | +0.3056 | 0.5502 | 0.2897 | 50 |
| MOM high tercil (rank≥0.66) | -0.0161 | +0.0126 | 0.2009 | 12.47 | -0.4315 | +0.4049 | 0.8364 | -0.2617 | +0.2396 | 0.5013 | 0.3043 | 49 |
| Δ terc MOM (low−high) | +0.0398 | +0.0628 | 0.3083 | 7.75 | -0.5711 | +0.7370 | 1.3081 | -0.3808 | +0.3715 | 0.7523 | 0.4224 | 49 |

**Sensibilidad Spearman** (mismo N): MOM on Spearman mediana −0.02 (IQR 0.23), MOM off −0.01 (IQR 0.25), Δmom_s mediana +0.02 IQR 0.38; RSI on −0.01 IQR 0.11, RSI off +0.01 IQR 0.12 — orden y magnitud replican Pearson; ningún ticker cambia conclusión por rank.

**Lectura comparativa vs incondicional**:

- **Nivel**: medianas eligible MOM on −0.019 vs off −0.034 (vs incondicional −0.082 / −0.070) — el gate desplaza ambas medianas hacia cero/positivo ~5-6pp, pero siguen centradas cerca de cero.
- **Dispersión absoluta por régimen**: rango MOM on 0.79 vs off 0.73 (vs incondicional 0.58/0.41), IQR on 0.232 vs off 0.260 (vs 0.126/0.115). Condicionar en eligible **aumenta** la heterogeneidad (sd 0.17 vs 0.11 antes, IQR casi duplica). El régimen no reduce dispersión; el gate la amplifica (selección sobre trend/volatilidad introduce varianza extra).
- **Delta entre regímenes**: mediana Δmom +0.054 (IQR 0.409, p10 −0.343 p90 +0.309) vs incondicional +0.002 (IQR 0.207). El Δ mediano sube levemente pero con **más ruido** (IQR duplica) por caída de N. p10-p90 de Δmom ahora 0.65 (vs 0.32 antes). Δrsi mediana −0.008 (IQR 0.20) vs +0.002 antes — ambos centrados en cero.
- **Terciles**: Δterc mom mediana +0.063 IQR 0.422 (vs incondicional −0.018 IQR 0.221) — mismo patrón: mediana pequeña, dispersión muy ancha.

## 7. Defensivas vs Growth — test dentro del gate eligible

**Hipótesis**: defensivas (staples/health low-beta) deberían sostener momentum/RSI en risk-off (VIX alto relativo); growth (tech alta-beta) en risk-on. Se mide, no se asume.

**Criterio explícito** (idéntico al diagnóstico anterior, sin re-clasificación ex-post):

- **Defensivas manual (lista Boris)**: KO, JNJ, PG, PEP, COST, WMT, PM, MCD, ABBV, UNH — N=10
- **Growth manual (alta-beta/tech)**: NVDA, AMD, TSLA, META, AVGO, NFLX, ADBE, CRM, QCOM, GE, INTU — N=11
- **Alternativos objetivos**: low-vol <0.23 (p25 del universo) vs high-vol >0.35 (p75+), mismos umbrales del diagnóstico anterior (vol_ann mediana 0.273, IQR 0.091)

**Defensivas manual — N=10**

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off eligible | +0.0990 | +0.1178 | 0.2306 | 0.1992 | -0.3359 | +0.5088 |
| Δrsi | -0.0473 | -0.0376 | 0.1127 | 0.1866 | -0.2690 | +0.0919 |
| mom_on eligible | +0.0229 | +0.0761 | 0.1421 | 0.1671 | -0.0787 | +0.3890 |
| mom_off eligible | -0.0440 | -0.0417 | 0.1995 | 0.1856 | -0.3888 | +0.3193 |
| rsi_on | -0.0321 | -0.0170 | 0.0721 | 0.0796 | -0.1636 | +0.0758 |
| rsi_off | +0.0589 | +0.0206 | 0.0891 | 0.0691 | -0.1261 | +0.1158 |
| Δterc mom | +0.2092 | +0.2170 | 0.2819 | 0.3259 | -0.0065 | +0.5591 |

**Growth manual — N=11**

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off eligible | -0.1309 | -0.0972 | 0.2120 | 0.3019 | -0.3611 | +0.2612 |
| Δrsi | -0.0163 | -0.0111 | 0.1131 | 0.1233 | -0.1658 | +0.1606 |
| mom_on eligible | -0.0359 | -0.0364 | 0.1766 | 0.2563 | -0.2380 | +0.2780 |
| mom_off eligible | +0.0608 | +0.0608 | 0.1513 | 0.0635 | -0.0252 | +0.3420 |
| rsi_on | -0.0429 | -0.0380 | 0.0616 | 0.0717 | -0.1070 | +0.0294 |
| rsi_off | -0.0167 | -0.0270 | 0.1048 | 0.1033 | -0.1558 | +0.1063 |
| Δterc mom | -0.2002 | -0.1481 | 0.2681 | 0.3491 | -0.4899 | +0.2222 |

**Low-vol (<0.23) — N=12 — tickers: BRK-B, COST, JNJ, KO, LIN, MCD, MRK, PEP, PG, QQQ, SPY, WMT**

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off eligible | +0.1151 | +0.1268 | 0.1972 | 0.1795 | -0.0399 | +0.5088 |
| Δrsi | -0.0318 | -0.0158 | 0.1477 | 0.2098 | -0.2690 | +0.1732 |
| mom_on | -0.0121 | +0.0334 | 0.1249 | 0.0860 | -0.0787 | +0.3890 |
| mom_off | -0.1113 | -0.0934 | 0.1822 | 0.2377 | -0.3888 | +0.2387 |
| Δterc mom | +0.1929 | +0.2162 | 0.2336 | 0.2561 | -0.0065 | +0.5591 |

**High-vol (>0.35) — N=8 — tickers: AMD, AVGO, CRM, META, NFLX, NVDA, QCOM, TSLA**

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off eligible | -0.1138 | -0.0639 | 0.2083 | 0.2188 | -0.2907 | +0.2612 |
| Δrsi | -0.0148 | -0.0139 | 0.1004 | 0.0958 | -0.1363 | +0.1606 |
| mom_on | -0.0311 | -0.0082 | 0.1749 | 0.1734 | -0.2380 | +0.2780 |
| mom_off | +0.0556 | +0.0557 | 0.1787 | 0.0746 | -0.1039 | +0.3420 |
| Δterc mom | -0.1543 | -0.0981 | 0.2678 | 0.3431 | -0.3489 | +0.2612 |

**Lectura honesta — ¿aparece patrón limpio? NO — y ahora con signo invertido respecto a la hipótesis.**

- **Median Δmom on−off eligible**: defensivas **+0.099** (IQR 0.20) vs growth **−0.131** (IQR 0.30) — diferencia **0.23** a favor de defensivas **procíclicas** (mejor en VIX bajo relativo), opuesto a lo esperado (defensiva resiliente en miedo). Low-vol +0.115 vs high-vol −0.114 — mismo signo invertido, idéntica separación ~0.23.
- **Pero IQRs se solapan y ambos cruzan cero**: defensivas p10 −0.077 p90 +0.366; growth p10 −0.291 p90 +0.228 — intervalos solapados en 0.30 de rango. Diferencia entre medianas (0.23) < IQR de cada grupo (0.20-0.30) y < p10-p90 de Δ general (0.65). No hay separación sistemática.
- **RSI**: defensivas Δrsi −0.047 vs growth −0.016 — diferencia −0.031, indistinguible de ruido (IQR >0.12).
- **Terciles**: defensivas Δterc +0.209 vs growth −0.200 — amplifica la inversión de signo pero con IQR >0.32 y p10-p90 que cruza cero en ambos grupos.
- **Nivel por régimen** (no solo delta): defensivas mom_on +0.023 vs mom_off −0.044 (procíclicas); growth mom_on −0.036 vs mom_off +0.061 (contracíclicas). En el diagnóstico incondicional ocurría lo opuesto (growth procíclico leve). El gate **invierte** el orden — señal de inestabilidad, no de régimen-dependencia robusta.
- **Conclusión**: la hipótesis defensiva resiliente en VIX alto no se sostiene; dentro del gate aparece incluso el patrón contrario, pero sin significancia ni separación limpia. Sostener narrativa procíclica o contracíclica sería forzar sobre ruido amplificado por N pequeño.

**Contraejemplos ticker-nivel donde la hipótesis NO se cumple (mín 8 ejemplos, valores numéricos eligible)**:

- **XOM** (Resto/energy, vol 0.275): ic_mom_on **−0.388**, off **+0.187**, Δ=**−0.575** — peor en risk-on por 58pp, opuesto a procíclico global.
- **KO** (defensiva): on +0.120, off **−0.389**, Δ=**+0.509** — mejor en risk-on por 51pp, pero defensiva debería brillar en risk-off; cumple procíclico pero viola defensiva.
- **PFE** (health): on +0.163, off −0.345, Δ=+0.508 — mismo patrón extremo procíclico, no estable.
- **DIS** (comm): on −0.403, off +0.022, Δ=−0.425 — fuerte contracíclico, pero no es growth.
- **ADBE** (growth): on −0.238, off +0.123, Δ=−0.361 — peor en risk-on por 36pp, opuesto a growth procíclico esperado.
- **AAPL** (tech): on −0.201, off +0.159, Δ=−0.360 — peor en risk-on.
- **BAC** (fin): on −0.177, off +0.172, Δ=−0.349 — peor en risk-on.
- **PM** (defensiva): on −0.017, off +0.319, Δ=−0.336 — **contracíclica** (mejor en risk-off) — dentro del mismo grupo defensivo hay signos opuestos (KO +0.51 vs PM −0.34, rango 0.84).
- **JPM** (fin): on −0.247, off +0.075, Δ=−0.322 — peor en risk-on.
- **TSLA** (growth emblema): on +0.211, off +0.342, Δ=−0.131 — mejor en risk-off por 13pp, opuesto a growth procíclico.
- **NVDA** (growth): on −0.036, off +0.061, Δ=−0.097 — contracíclico leve, no procíclico.

Cada grupo contiene Δ de ambos signos con magnitud económica grande (±30-60pp), mayor que la diferencia entre medianas de grupo (23pp). No hay regla transversal.

## 8. Comparación vs diagnóstico incondicional (limitación R2/R3)

| aspecto | incondicional (VIX level fijo) | rolling eligible (este) | cambio |
|---------|-------------------------------|-------------------------|--------|
| corte | VIX <16.68 (mediana muestral) | rank_240d <0.5 (rolling) | corrige deriva secular |
| población | todos los días (n≈1300 por bucket) | solo eligible trend/adx/rsi/vol (n≈173/126) | −87% N, SE ×2.7 |
| pooled mom on/off | +0.022 / −0.004 (Δ+0.026) | +0.059 / +0.070 (Δ−0.010) | nivel sube, Δ se anula |
| pooled terc low/high | +0.054 / +0.002 (Δ+0.051) | +0.094 / +0.101 (Δ−0.008) | mismo |
| median Δmom | +0.002 (IQR 0.207) | +0.054 (IQR 0.409) | IQR duplica |
| defensivas vs growth Δmom | −0.010 vs +0.064 (dif 0.07 pro-growth) | +0.099 vs −0.131 (dif 0.23 pro-defensiva) | signo se invierte |
| conclusión régimen | no rescata factores, dispersión no se reduce | tampoco rescata; dispersión aumenta | confirma no-estructura |

El rank rolling no crea señal de régimen donde no la había; el gate tampoco: ambos elevan levemente el nivel pooled pero no generan separación on/off sistemática y **amplifican heterogeneidad**.

## 9. Limitaciones explícitas (14 del anterior + 3 nuevas de rolling/gate)

1. **Survivorship/selección**: universo 50 top-cap supervivientes 2015-2026, sin delistados; sesgo hacia large resilientes.
2. **Ventana y no-estacionariedad**: ventana única 11.6 años agrega bull/bear/COVID/tightening. Rank 240d adapta deriva de nivel pero no de dinámica de clustering (Hurst, autocorrelación vol).
3. **No out-of-sample, no inferencia**: sin pre-registro, sin corrección por 50×2×2 comparaciones, sin SE/Newey-West, sin test Δ≠0. Δs descriptivos; SE(Δ)≈0.12 por bucket eligible, cualquier |Δ|<0.25 puede ser ruido.
4. **Lookahead fwd vs VIX contemporáneo**: fwd_ret_20d solapa ventanas (autocorrelación inducida) e infla SE; además horizonte 20d atraviesa cambios de régimen intra-horizonte (rank de t puede no persistir 20d).
5. **Heterocedasticidad y pooling**: pooled concatena filas con varianzas y niveles distintos; VIX alto suele coincidir con vol realizada alta → peso implícito mayor para filas risk-off; rank rolling no corrige heterocedasticidad cross-sectional.
6. **IC anterior sin gate** corregido aquí: este diagnóstico sí condiciona en eligible, pero pierde N y gana selección (ver 15).
7. **Derivación de factores, no factores del motor**: fórmulas exactas pero sin pipeline completo `calculate_all_indicators().ffill().dropna()` idéntico; desviación mínima documentada (ffill no aplicado, NaN= no eligible).
8. **Warmup y N**: momentum warmup 252d; rsi 14d; fwd 20d futuro; tras rank 239 + gate 90% filtrado, n eligible por bucket queda 173/126 mediana — no es 2921. Últimos 20d sin fwd y primeros 240d sin rank se pierden.
9. **Metric fragilidad**: rsi_score binario (point-biserial, varianza baja); momentum_score saturado en colas; rank threshold 0.5/0.33/0.66 arbitrario (mediana rolling, no nivel estructural).
10. **Cap group incompleto**: SMID vacío; no testeable Large vs SMID tampoco por régimen.
11. **No propone calibración por ticker ni por régimen**: heterogeneidad en Δ existe pero no es sistemática por grupo; calibrar pesos por régimen/ticker amplificaría ruido sin evidencia OOS.
12. **Corte rolling depende de era**: rank 240d en ventana 2020-21 (COVID) compara VIX 30 contra 80 previos → rank bajo aunque VIX absoluto alto; régimen relativo ≠ estrés absoluto. Sensibilidad a ventana 240d no explorada (120d/60d cambiarían asignación ~15%).
13. **Ventana 240d elegida sin optimización**: 240d ≈1 año hábil es estándar pero arbitrario; ventana más corta (60d) sería más reactiva a clusters, más larga (500d) más estacionaria. No se optimizó para evitar data-snooping; se documenta como limitación.
14. **Régimen no estacionario y clustering**: VIX clusters (Hurst, autocorrelación vol) implican filas sucesivas dentro de bucket no independientes; SE real >1/√n. Días de VIX≥20 post-COVID dominan bucket off, confundiendo efecto VIX con efecto temporal. Sin control por año, Δ confunde régimen con era (mismo que antes, persiste con rank).
15. **[Nueva R4] Elección de ventana 240d y ties**: con ties y ventanas con varianza baja (VIX plano), rank average produce empates no uniformes (histograma cola izquierda 491 vs 268 esperado). Cambiar `method='min'/'max'` o ventana 120d/500d movería ~10-15% de días near-threshold; no se testeó por restricción solo-lectura.
16. **[Nueva R5] Sesgo de selección eligible (gate condiciona varianza)**: filtrar por `trend & adx & rsi & vol_ratio` selecciona días con tendencia y momentum ya positivo y vol realizada alta; condiciona la distribución de `momentum_score` (trunca cola baja) y de `fwd_ret` (selección sobre vol). El IC condicional no es comparable al incondicional; correlación dentro de selección sufre sesgo de rango restringido y collider (gate correlacionado con volatilidad que a su vez correlaciona con VIX).
17. **[Nueva R6] Pérdida de N y SE inflado**: elegibilidad 10.9% reduce n por bucket de ~1300 a ~150 (mediana 172/126), SE( Pearson ) sube ~2.7× y SE(Δ) ~0.12 (vs 0.04 antes). Potencia para detectar Δ=0.10 cae de ~85% a <30%; intervalos de confianza de Δ (±0.24) contienen casi todo el rango observado. Cualquier patrón aparente es compatible con ruido.

## 10. Apéndice A — Spearman por ticker (sensibilidad, eligible)

| ticker | mom_on_s | mom_off_s | Δmom_s | rsi_on_s | rsi_off_s | Δrsi_s | mom_low_s | mom_high_s |
|--------|----------|-----------|--------|----------|-----------|--------|-----------|------------|
| AAPL | -0.2369 | 0.0921 | -0.3290 | -0.1640 | 0.0805 | -0.3277 | 0.0024 |
| ABBV | 0.0989 | -0.3143 | 0.4132 | 0.0189 | -0.0077 | 0.1931 | -0.4726 |
| ACN | -0.0073 | -0.0992 | 0.0919 | 0.0027 | -0.0942 | 0.1592 | -0.1408 |
| ADBE | -0.2457 | 0.0416 | -0.2874 | -0.1837 | 0.0492 | -0.2137 | 0.1898 |
| AMD | -0.1415 | 0.0963 | -0.2378 | 0.1057 | 0.1228 | -0.0495 | 0.2970 |
| AMGN | -0.1719 | -0.1412 | -0.0307 | 0.0965 | -0.0199 | -0.2120 | -0.1316 |
| AMZN | 0.2458 | -0.1263 | 0.3721 | 0.0673 | -0.0021 | 0.2863 | -0.1524 |
| AVGO | -0.0473 | 0.0300 | -0.0773 | 0.0445 | 0.0331 | -0.0222 | 0.1478 |
| BAC | -0.1993 | 0.0402 | -0.2396 | -0.0186 | 0.0784 | -0.1852 | 0.0967 |
| BRK-B | -0.0336 | 0.2765 | -0.3101 | 0.1704 | -0.1705 | 0.0031 | 0.3732 |
| CAT | 0.3044 | -0.0040 | 0.3084 | -0.0606 | 0.0645 | 0.3099 | 0.0334 |
| CMCSA | -0.2671 | -0.2815 | 0.0144 | 0.0483 | 0.0000 | -0.2746 | -0.2826 |
| COST | -0.0539 | -0.1272 | 0.0732 | -0.0602 | -0.1315 | -0.0727 | -0.1032 |
| CRM | -0.1329 | 0.1638 | -0.2967 | -0.0074 | -0.0178 | -0.1281 | 0.1843 |
| CSCO | -0.1597 | -0.3083 | 0.1485 | -0.0080 | -0.2476 | -0.0919 | -0.3637 |
| CVX | -0.1330 | 0.1505 | -0.2835 | -0.1496 | 0.2409 | -0.1821 | 0.2253 |
| DIS | -0.2257 | 0.2542 | -0.4799 | 0.0439 | -0.0107 | -0.2199 | nan |
| GE | -0.2235 | 0.0561 | -0.2796 | -0.0560 | -0.2595 | -0.3090 | 0.0519 |
| GOOGL | -0.0639 | -0.1827 | 0.1188 | -0.0622 | -0.0931 | 0.0105 | -0.0812 |
| HD | -0.2172 | -0.4283 | 0.2111 | 0.1100 | 0.3628 | -0.1134 | -0.5657 |
| IBM | 0.0049 | 0.1082 | -0.1033 | -0.0855 | 0.0235 | 0.0372 | 0.0768 |
| INTU | 0.1218 | 0.1039 | 0.0179 | -0.0061 | -0.1370 | 0.1324 | 0.2130 |
| JNJ | 0.1673 | 0.0238 | 0.1435 | -0.0209 | 0.0920 | 0.1993 | 0.0646 |
| JPM | -0.3122 | 0.0771 | -0.3893 | 0.0377 | -0.1074 | -0.3154 | 0.0423 |
| KO | 0.1120 | -0.3433 | 0.4553 | 0.1067 | -0.0365 | 0.1129 | -0.3931 |
| LIN | -0.0010 | -0.2571 | 0.2561 | -0.0087 | 0.0624 | 0.0933 | -0.2975 |
| LLY | 0.1076 | -0.0747 | 0.1823 | -0.1358 | 0.2019 | 0.0143 | 0.0675 |
| MA | 0.1302 | 0.0658 | 0.0644 | 0.1063 | -0.1087 | 0.1717 | 0.1610 |
| MCD | -0.0063 | -0.2915 | 0.2853 | -0.1591 | -0.0203 | 0.0919 | -0.3801 |
| META | 0.1556 | -0.0320 | 0.1876 | -0.0841 | 0.0621 | 0.2219 | -0.1192 |
| MRK | -0.0887 | -0.1312 | 0.0425 | -0.0302 | -0.0588 | -0.0147 | -0.1307 |
| MSFT | 0.0513 | -0.2299 | 0.2812 | 0.0394 | 0.0360 | 0.1041 | -0.1190 |
| NFLX | -0.1046 | -0.3051 | 0.2005 | -0.0430 | -0.0717 | -0.0557 | -0.2203 |
| NVDA | -0.1059 | 0.1033 | -0.2092 | -0.0913 | -0.0560 | -0.1057 | 0.0548 |
| ORCL | -0.2158 | -0.2987 | 0.0829 | 0.0953 | 0.1314 | -0.1304 | -0.4071 |
| PEP | 0.0131 | -0.0714 | 0.0844 | 0.0122 | 0.0871 | 0.1104 | -0.1562 |
| PFE | 0.1384 | -0.2946 | 0.4330 | 0.1273 | -0.0216 | 0.3001 | -0.3296 |
| PG | -0.0917 | -0.1835 | 0.0918 | -0.0455 | 0.1146 | -0.0958 | -0.2654 |
| PM | -0.0293 | 0.2692 | -0.2985 | -0.0886 | -0.1717 | -0.0764 | 0.2043 |
| QCOM | -0.2329 | 0.0687 | -0.3016 | 0.0250 | -0.1718 | -0.3344 | 0.1185 |
| QQQ | -0.0169 | -0.2146 | 0.1977 | -0.0280 | 0.0751 | 0.0651 | -0.1968 |
| SPGI | 0.0719 | -0.0398 | 0.1118 | 0.0077 | 0.0641 | 0.1875 | 0.1121 |
| SPY | -0.0037 | -0.2294 | 0.2258 | 0.0097 | -0.0206 | 0.1503 | -0.2021 |
| TMO | 0.0722 | -0.2539 | 0.3261 | 0.1940 | -0.1086 | 0.0308 | -0.1835 |
| TSLA | 0.2146 | 0.3087 | -0.0941 | -0.0935 | 0.0398 | 0.1838 | 0.3267 |
| TXN | 0.0409 | -0.4392 | 0.4800 | 0.0039 | 0.0157 | 0.0553 | -0.3504 |
| UNH | 0.0654 | -0.0854 | 0.1508 | -0.0695 | 0.1196 | 0.1151 | -0.0534 |
| V | 0.0681 | -0.0392 | 0.1073 | 0.0539 | -0.0258 | 0.0509 | -0.0561 |
| WMT | 0.1274 | 0.1005 | 0.0269 | 0.0167 | 0.0453 | 0.1695 | 0.1423 |
| XOM | -0.4538 | 0.2174 | -0.6712 | -0.0029 | -0.0534 | -0.5058 | 0.2549 |

Concordancia Pearson vs Spearman: correlación entre Δmom Pearson y Δmom Spearman = **0.91** (alta), Δrsi = **0.95**. Orden de tickers preservado.

## 11. Apéndice B — Vol y N eligible (contexto)

| ticker | vol_ann | n_elig_total | elig_rate | n_on_elig | n_off_elig | n_low_elig | n_high_elig |
|--------|---------|--------------|-----------|-----------|------------|------------|-------------|
| AAPL | 0.2878 | 340 | 0.116 | 160 | 161 | 126 | 93 |
| ABBV | 0.2664 | 338 | 0.116 | 187 | 139 | 141 | 103 |
| ACN | 0.2723 | 363 | 0.124 | 199 | 127 | 143 | 77 |
| ADBE | 0.3370 | 326 | 0.112 | 159 | 133 | 124 | 84 |
| AMD | 0.5983 | 271 | 0.093 | 163 | 108 | 122 | 60 |
| AMGN | 0.2520 | 263 | 0.090 | 127 | 125 | 95 | 83 |
| AMZN | 0.3314 | 372 | 0.127 | 194 | 139 | 147 | 89 |
| AVGO | 0.3953 | 391 | 0.134 | 257 | 116 | 195 | 79 |
| BAC | 0.3037 | 296 | 0.101 | 181 | 105 | 137 | 64 |
| BRK-B | 0.1909 | 326 | 0.112 | 202 | 124 | 160 | 80 |
| CAT | 0.3080 | 292 | 0.100 | 175 | 117 | 135 | 74 |
| CMCSA | 0.2591 | 290 | 0.099 | 179 | 84 | 132 | 45 |
| COST | 0.2154 | 361 | 0.124 | 155 | 178 | 117 | 112 |
| CRM | 0.3541 | 304 | 0.104 | 158 | 116 | 109 | 73 |
| CSCO | 0.2594 | 291 | 0.100 | 145 | 124 | 98 | 79 |
| CVX | 0.2901 | 242 | 0.083 | 128 | 114 | 91 | 88 |
| DIS | 0.2802 | 191 | 0.065 | 104 | 48 | 78 | 29 |
| GE | 0.3473 | 245 | 0.084 | 137 | 82 | 105 | 60 |
| GOOGL | 0.2913 | 355 | 0.122 | 192 | 136 | 149 | 85 |
| HD | 0.2442 | 291 | 0.100 | 165 | 98 | 121 | 69 |
| IBM | 0.2728 | 228 | 0.078 | 142 | 79 | 108 | 56 |
| INTU | 0.3329 | 358 | 0.123 | 188 | 143 | 129 | 99 |
| JNJ | 0.1832 | 283 | 0.097 | 154 | 126 | 108 | 82 |
| JPM | 0.2696 | 329 | 0.113 | 222 | 92 | 158 | 54 |
| KO | 0.1791 | 319 | 0.109 | 165 | 141 | 124 | 102 |
| LIN | 0.2239 | 342 | 0.117 | 226 | 116 | 179 | 76 |
| LLY | 0.2979 | 318 | 0.109 | 169 | 119 | 123 | 82 |
| MA | 0.2626 | 379 | 0.130 | 204 | 151 | 163 | 100 |
| MCD | 0.2021 | 372 | 0.127 | 167 | 170 | 128 | 113 |
| META | 0.3785 | 332 | 0.114 | 202 | 96 | 160 | 61 |
| MRK | 0.2276 | 286 | 0.098 | 152 | 126 | 114 | 86 |
| MSFT | 0.2762 | 349 | 0.119 | 190 | 152 | 147 | 95 |
| NFLX | 0.4259 | 319 | 0.109 | 150 | 126 | 121 | 99 |
| NVDA | 0.4819 | 399 | 0.137 | 216 | 150 | 164 | 102 |
| ORCL | 0.3423 | 290 | 0.099 | 194 | 90 | 144 | 41 |
| PEP | 0.1923 | 348 | 0.119 | 193 | 132 | 148 | 96 |
| PFE | 0.2337 | 271 | 0.093 | 111 | 123 | 81 | 73 |
| PG | 0.1868 | 309 | 0.106 | 160 | 149 | 140 | 103 |
| PM | 0.2380 | 297 | 0.102 | 160 | 122 | 122 | 86 |
| QCOM | 0.3862 | 229 | 0.078 | 138 | 91 | 102 | 50 |
| QQQ | 0.2196 | 407 | 0.139 | 215 | 165 | 154 | 99 |
| SPGI | 0.2605 | 374 | 0.128 | 226 | 139 | 170 | 78 |
| SPY | 0.1760 | 401 | 0.137 | 220 | 168 | 149 | 96 |
| TMO | 0.2592 | 343 | 0.117 | 170 | 146 | 120 | 90 |
| TSLA | 0.5720 | 233 | 0.080 | 131 | 90 | 101 | 68 |
| TXN | 0.3090 | 328 | 0.112 | 185 | 132 | 140 | 82 |
| UNH | 0.2940 | 349 | 0.119 | 187 | 139 | 130 | 89 |
| V | 0.2423 | 364 | 0.125 | 209 | 125 | 161 | 78 |
| WMT | 0.2176 | 343 | 0.117 | 182 | 161 | 133 | 104 |
| XOM | 0.2751 | 219 | 0.075 | 112 | 107 | 82 | 77 |

## 12. Trazabilidad y verificación de no-escritura

- **Cache leído**: `backend/data/cache/*.parquet` (57 archivos efectivos, 2921 filas c/u equities + 2923 ^VIX) + `^VIX.parquet` rank_240d valid N=2684. Verificado con `eza backend/data/cache/` y `python -c "pd.read_parquet..."`.
- **Definición universo**: `backend/scripts/fetch_universe_data.py:NEW_UNIVERSE` (43) + `_BASE_SYMBOLS` (7) = 50; `backend/app/api/routes/opportunities_universe.py:19-35`.
- **Gates**: `backend/app/core/signal_engine.py:158-170` (`compute_factor_frame` eligible 4 gates) y `:208-217` (`generate_signal` + score≥0.60), `backend/app/core/indicators.py:9-10` (ema), `:25-30` (rsi), `:48-59` (adx), `:370-381` (volume_ratio, momentum_12_1).
- **Fórmulas**: `backend/app/core/signal_engine.py:137-142` (momentum_score, rsi_score), `backend/app/core/backtest_engine.py:23` (horizonte 20d), rank_240d fórmula §1 `(rank-1)/(n-1)` con `pandas rank(method='average')` ventana trailing 240 inclusive.
- **Scripts efímeros** (solo lectura, no pre-registrados, en /tmp): `/tmp/diagnostico_vix_rolling_gate.py` (pipeline principal), `/tmp/vix_rolling_gate_per_ticker.csv` (tabla intermedia 50 filas), `/tmp/vix_rolling_gate_summary.json`, `/tmp/build_rolling_gate_md.py` (generador de este md). Todos en `/tmp`, no trackeados.
- **Verificación solo-lectura**: `git status --porcelain` debe mostrar solo este `.md` como untracked junto a los dos diagnósticos previos (`DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md`, `DIAGNOSTICO_HETEROGENEIDAD_VIX_REGIMEN.md`), sin modificación de `backend/data/cache/*`, `fortress.db`, `backend/data/trial_registry.json`, ni creación de `PRE_REGISTRO_*`. Comprobado pre-escritura con `rg -n "trial_registry|ledger"`.
- **Repro**: `python3 /tmp/diagnostico_vix_rolling_gate.py` → `/tmp/vix_rolling_gate_per_ticker.csv` + `/tmp/build_rolling_gate_md.py` → este md. Requiere `pandas`, `scipy` opcional para Spearman. Sin semillas; determinístico sobre parquet.

## 13. Entrega y stats clave para handoff

**Archivo**: `DIAGNOSTICO_HETEROGENEIDAD_VIX_ROLLING_GATE.md` — `/Users/boris/orca/workspaces/fortress_core/test-opencode-orca/DIAGNOSTICO_HETEROGENEIDAD_VIX_ROLLING_GATE.md`

| Stat | Valor |
|------|-------|
| **VIX rank 240d N válidos** | **2684** (2923−239), mean 0.458 median 0.456 sd 0.315 |
| **N días VIX por régimen rolling global** | risk-on 1436 (53.5%) / risk-off 1248 (46.5%) ; low terc 1083 / high terc 860 / mid 741 |
| **N por ticker por bucket eligible (mediana)** | on **172.5** / off **125.5** ; low **129.5** / high **82.0** ; total eligible mediano **326** (tasa **10.9%** mean, **11.2%** median) |
| **Tasa elegibilidad global** | **7318** filas eligible con score≥0.60 / **146050** totales = **5.0%** (sin score: **15866** filas, **10.9%**) |
| **Pooled MOM Pearson eligible on/off** | **+0.059 / +0.070** (Δ **−0.010**) — n on 8651 off 6163 |
| **Pooled MOM terc low/high** | **+0.094 / +0.101** (Δ **−0.008**) — n low 6495 high 3978 |
| **Pooled RSI on/off** | **−0.009 / +0.008** (Δ −0.018) |
| **Dispersión Δmom on−off eligible** | mediana **+0.054**, IQR **0.409**, p10 **−0.343** p90 **+0.309**, rango **1.084** |
| **Dispersión Δrsi** | mediana −0.008, IQR 0.202 |
| **Median Δmom defensivas (N=10) vs growth (N=11)** | defensivas **+0.099** (IQR 0.20) vs growth **−0.131** (IQR 0.30), **dif 0.23 signo invertido vs hipótesis**, intervalos solapados |
| **Median Δmom low-vol (N=12) vs high-vol (N=8)** | low-vol **+0.115** vs high-vol **−0.114** (dif 0.23, mismo patrón invertido) |
| **SE inflado** | SE(IC) ~0.076 on / 0.089 off (vs 0.028 antes), SE(Δ) ~0.12 (vs 0.04) — pérdida potencia 87% N |

**Próximo paso recomendado** (no veredicto): este split VIX rolling + gate eligible **no resuelve** la heterogeneidad ni aporta régimen-dependencia sistemática limpia; además **invierte** el signo defensivas vs growth respecto al incondicional (señal de inestabilidad, no de estructura). No se recomienda calibrar pesos por régimen sin OOS con `trial_registry` + DSR y sin controlar sesgo de selección del gate. Si se insiste, el siguiente diseño debería fijar ventana rank alternativa (120d/500d) y régimen absoluto vs relativo como pre-registro explícito, con corrección de heterocedasticidad y N mínimo por bucket documentado.

---
*Fin del diagnóstico VIX rolling gate — 2026-09-01, solo lectura, tercera iteración heterogeneidad, sin veredicto de trading.*
