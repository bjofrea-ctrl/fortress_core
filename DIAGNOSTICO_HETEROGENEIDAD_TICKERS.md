# Diagnóstico de Heterogeneidad entre Tickers — Base Empírica para Pesos por Ticker vs Globales

**Fecha**: 2026-09-01
**Autor**: Muse Spark (diagnóstico solo-lectura, orquestado por OpenCode)
**Restricción dura**: SOLO LECTURA de parquet cache existente en `backend/data/cache/*.parquet` — no se recalculó ni re-ejecutó backtest, no se tocó `ledger`/`trial_registry`, no se creó pre-registro. Es diagnóstico descriptivo, no veredicto de trading.
**Fuente parquet**: `backend/data/cache/*.parquet` (worktree `test-opencode-orca`)
**Rango temporal real**: 2015-01-02 → 2026-08-14 (último cierre disponible en cache; el updater diario quedó estancado post 2026-08-14 por bug conocido en `data_updater.sh` — ver ROADMAP).
**N efectivo en artefacto**: **57 parquet** (50 del universo canónico + 7 tickers de mercado/regime). **Proyectado 102** (7 base + 95 expandidos) **NO existe en este worktree**: la ampliación a 102 (PROPUESTA_AMPLIACION_UNIVERSO.md con 52 tickers adicionales, ~28 SMID puros) solo está materializada en el worktree `test-kilo-orca` (130 parquet, 2015-01-02→2026-08-31). Este diagnóstico reporta sobre el **artefacto real disponible aquí (N=57/50)**, documenta la divergencia y recomienda re-ejecutar idéntica metodología tras sincronizar los 102 (rsync de cache).
**Universo canónico aquí**: `backend/scripts/fetch_universe_data.py:NEW_UNIVERSE` (43) + `_BASE_SYMBOLS` (7) = 50 (definición de `backend/app/api/routes/opportunities_universe.py:19-35`). Verificado: `missing = ∅` para los 50.
**Market tickers**: AGG, DBC, EFA, GLD, TIP, TLT, ^VIX (usados por `GlobalRegimeClassifier`, no son señales tradables).

## Referencias de pesos globales e IC pooled del motor

| Dimensión | Valor | Fuente verificada |
|-----------|-------|-------------------|
| **Pesos runtime** | `w_mom_runtime = 0.6642`, `w_rsi_runtime = 0.3358` | `backend/app/core/signal_engine.py:85-90` (`_momentum_ic=0.0637, _rsi_ic=0.0322`, `w = ic_mom/(ic_mom+ic_rsi)`), eco runtime `backend/data/cache/pipeline_run_decide_20260826_081420.txt`, tests `backend/tests/test_pipeline_daily_signal.py: w==0.6642/0.3358` |
| **Definición score** | `score = w_mom*momentum_score + w_rsi*rsi_score` | `signal_engine.py:145`, `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:26` |
| **Origen ICs que derivan los pesos** | `momentum IC = 0.0637`, `RSI IC = 0.0322` (Pearson **pooled** 2019-2024, SPY/QQQ/AAPL/MSFT/GOOGL/AMZN/NVDA, solo días elegibles) | `signal_engine.py:73-84` comentario + `RESUMEN_VALIDACION_VARIABLES.md` |
| **Método IC del motor** | `SignalQualityMetrics.compute_ic` = correlación **Pearson**; `compute_rank_ic` = **Spearman rank** (`backend/app/core/probabilistic_engine.py:173-186`). Los priors del blend usan **Pearson pooled** (proporcional a \|IC\|). Los diagnósticos intra-día walk-forward usan Spearman por fecha con SE Newey-West; para este diagnóstico **primario = Pearson** (comparable al pooled que derivó los pesos) y se reporta Spearman como sensibilidad. | Verificado en código |
| **ICs pooled re-medidos aquí (solo lectura, derivados de close)** | **Universo 50**: MOM Pearson **+0.0016** (Spearman −0.0185), RSI Pearson **−0.0223** (Spearman −0.0212), n≈132k/145k filas ticker-día. **57 mixto** (50+7 market): MOM Pearson −0.0122, RSI Pearson −0.0207. | Cálculo derivado en este diagnóstico desde OHLCV cache (no del panel de factores original) — ver limitaciones |
| **Contraste con priors del motor** | Los ICs que derivaron los pesos (0.0637/0.0322, 2019-2024, solo elegibles, panel de factores) son **más positivos** que los pooled re-medidos aquí sobre serie completa (sin filtro `eligible`, ventana 2015-2026, sin `trend/adx/vol` gates). La diferencia refleja que el gate concentra señal (documentado: IC momentum dentro del gate >> fuera) y cambio de ventana/método. Este diagnóstico no reestima el gate; solo cuantifica heterogeneidad per-ticker con metodología homogénea. | `AUDITORIA_MECANICA.md`, `SESSION_LOG.md:1259` |

> **Nota sobre IC pooled**: el diagnóstico intra-día correcto (ONBOARDING.md §2) es rank IC por fecha con Newey-West, no pooled. El pooled se usa aquí **solo** como referencia para el peso global histórico y para comparación descriptiva, no como test de significancia. Los IC individuales per-ticker también son pooled por ticker (Pearson sobre serie temporal de ese ticker), no cross-sectional.

## Clasificación Large vs SMID

**Fuente buscada**: `PROPUESTA_AMPLIACION_UNIVERSO.md` — **NO existe en este worktree** (`test-opencode-orca`). Búsqueda con `rg` y `fd` confirma ausencia. Falla cerrada con evidencia de `eza` (lista de 40 *.md sin ese archivo). Equivalente documentado: `test-kilo-orca/PROPUESTA_AMPLIACION_UNIVERSO.md` (v2 corregida 2026-09-01) y `test-opencode-orca/RESUMEN_VALIDACION_VARIABLES.md §5`.

**Criterio aplicado aquí** (honesto, sin inventar):

| Grupo | Tickers en este cache (57) | Criterio | Count |
|-------|----------------------------|----------|-------|
| **Large** | Los 50 del universo canónico (7 base + 43 NEW_UNIVERSE) — todos large/mega-cap por construcción (META, TSLA, AVGO, BRK-B, LLY, JPM, WMT, V, UNH, XOM, MA, ORCL, PG, COST, HD, JNJ, ABBV, BAC, MRK, CRM, KO, ADBE, PEP, AMD, NFLX, TMO, CVX, CSCO, ACN, MCD, IBM, LIN, QCOM, GE, INTU, PM, CMCSA, DIS, TXN, CAT, AMGN, PFE, SPGI) | `PROPUESTA_AMPLIACION_UNIVERSO.md §2-3`: "Los 43 de NEW_UNIVERSE son todos large/mega-cap ... market cap $2B-50B para los nuevos" — los 50 actuales son 100% large | 50 |
| **ETF/Market** | AGG, DBC, EFA, GLD, TIP, TLT, ^VIX | `opportunities_universe.py:35` `MARKET_TICKERS`, régimen macro | 7 |
| **SMID** | (vacío en este cache) — los ~28 SMID puros (TYL, AKAM, FFIV, EPAM, CHKP, QLYS, BR, STAG, QRVO, MPWR, etc.) y ~24 large-mid de la propuesta 52 existen solo en `test-kilo-orca` | `PROPUESTA_AMPLIACION_UNIVERSO.md §4-5` (52 adicionales, 54% SMID $2-50B) | 0 |

**Implicancia**: el desagregado por cap en este artefacto compara **Large (50) vs ETF/Market (7)**; **SMID queda vacío** y no permite testar la hipótesis central de la ampliación (que SMID aporta dispersión). Se reporta Large puro y se deja la comparación Large-vs-SMID como **próximo paso** tras sincronizar cache 102.

## Metodología (fórmulas)

**Datos de entrada**: OHLCV diario cacheado por parquet (índice Date, columnas Close/High/Low/Open/Volume), 2921 filas por ticker (≈252 días/año × 11.6 años).

**Volatilidad anualizada**:
```
ret_d = close.pct_change(1)
vol_ann = std(ret_d, ddof=1) * sqrt(252)
```
Ventana completa disponible por ticker (2015-01-02→2026-08-14). No se winsoriza.

**Autocorrelación de retornos**:
```
ac_k = corr(ret_d, ret_d.shift(k)), k ∈ {1,5,20}
```
Pearson sobre pares con ambas observaciones no-nulas. Sin ajuste de significancia; solo descriptivo de persistencia/reversión.

**Indicadores derivados (idénticos al motor, sin pre-registro nuevo)**:
- `momentum_12_1 = close.pct_change(252)*100` (`indicators.py:381`)
- `momentum_score = clip((momentum_12_1 + 50)/150, 0, 1)` (`signal_engine.py:137`)
- `rsi14 = RSI(14)` sobre close con SMA simple de gains/losses (`indicators.py:25-30`)
- `rsi_score = 0.8 si 45 < rsi14 < 70, else 0.4` (`signal_engine.py:141`)
- `fwd_ret_20d = close.shift(-20)/close - 1` (horizonte `CALIBRATION_HORIZON_DAYS=20`, `backtest_engine.py:23`)

**IC individual por ticker**:
```
ic_mom  = Pearson_corr(momentum_score, fwd_ret_20d)  [primario, comparable al pooled del motor]
ic_mom_spear = Spearman_corr(momentum_score, fwd_ret_20d)  [sensibilidad]
ic_rsi  = Pearson_corr(rsi_score, fwd_ret_20d)
ic_rsi_spear = Spearman_corr(rsi_score, fwd_ret_20d)
```
Sobre serie temporal de ese ticker, `dropna` de ambas series, mínimo 30 pares (si <30 → NaN). No se filtra por `eligible` (trend/adx/vol gates) para mantener metodología homogénea entre tickers; esto separa el efecto puro del factor del efecto del gate.

**IC pooled**:
```
ic_pooled = corr( concat_{ticker}(factor_score), concat_{ticker}(fwd_ret_20d) )
```
Concatenando todas las filas ticker-día (pooled temporal, no cross-sectional por fecha). Se reporta para universo 50 y para 57 mixto.

**Dispersión**: media, mediana, sd, **coef. variación CV = sd/|mean|** (adimensional, compara dispersión relativa entre métricas con escalas distintas), rango = max-min, p10-p90, IQR = Q75-Q25. CV con |mean| evita signo; si |mean|≈0, CV diverge → se reporta como ∞ y se interpreta junto al rango absoluto.

**Deltas vs pooled**:
```
delta_mom = ic_mom_individual - ic_pooled_mom_uni
delta_rsi = ic_rsi_individual - ic_pooled_rsi_uni
```

## Tabla cruda por ticker (57 filas — artefacto real; 102 proyectado no materializado aquí)

Columnas: `ticker | cap_group | n_obs | vol_ann | ac1 | ac5 | ac20 | ic_mom (Pearson) | ic_rsi (Pearson) | ic_mom - ic_pooled_mom | ic_rsi - ic_pooled_rsi` con `ic_pooled_mom_uni = 0.001556`, `ic_pooled_rsi_uni = -0.022274` (Pearson, universo 50).

| ticker | cap_group  | n_obs | vol_ann | ac1     | ac5     | ac20    | ic_mom  | ic_rsi  | delta_mom | delta_rsi |
|--------|------------|-------|---------|---------|---------|---------|---------|---------|-----------|-----------|
| AAPL   | Large      |  2921 | 0.2878 | -0.0512 | +0.0111 | -0.0114 | -0.0681 | +0.0152 | -0.0697 | +0.0375 |
| ABBV   | Large      |  2921 | 0.2664 | +0.0119 | +0.0157 | +0.0076 | -0.1250 | -0.0029 | -0.1265 | +0.0194 |
| ACN    | Large      |  2921 | 0.2723 | -0.0605 | +0.0249 | -0.0215 | +0.0150 | -0.0493 | +0.0134 | -0.0271 |
| ADBE   | Large      |  2921 | 0.3370 | -0.0718 | -0.0053 | -0.0314 | +0.0824 | -0.0563 | +0.0808 | -0.0340 |
| AGG    | ETF/Market |  2922 | 0.0519 | +0.0113 | -0.0041 | -0.0030 | +0.0655 | +0.0459 | +0.0640 | +0.0682 |
| AMD    | Large      |  2921 | 0.5983 | -0.0505 | -0.0254 | +0.0209 | -0.0368 | -0.0075 | -0.0383 | +0.0147 |
| AMGN   | Large      |  2921 | 0.2520 | -0.0656 | +0.0184 | -0.0224 | -0.2343 | -0.0149 | -0.2358 | +0.0074 |
| AMZN   | Large      |  2921 | 0.3314 | -0.0036 | +0.0129 | -0.0075 | -0.0172 | +0.0846 | -0.0188 | +0.1069 |
| AVGO   | Large      |  2921 | 0.3953 | -0.0613 | -0.0034 | +0.0119 | -0.0583 | -0.0537 | -0.0598 | -0.0314 |
| BAC    | Large      |  2921 | 0.3037 | -0.0333 | +0.0300 | -0.0026 | -0.0870 | -0.0515 | -0.0886 | -0.0292 |
| BRK-B  | Large      |  2921 | 0.1909 | -0.1038 | +0.0206 | +0.0019 | -0.1407 | +0.0208 | -0.1423 | +0.0431 |
| CAT    | Large      |  2921 | 0.3080 | -0.0026 | -0.0049 | -0.0120 | -0.1242 | -0.0440 | -0.1258 | -0.0217 |
| CMCSA  | Large      |  2921 | 0.2591 | -0.0956 | +0.0012 | -0.0251 | -0.0822 | +0.0424 | -0.0837 | +0.0647 |
| COST   | Large      |  2921 | 0.2154 | -0.0217 | +0.0198 | +0.0086 | -0.0572 | -0.0544 | -0.0587 | -0.0321 |
| CRM    | Large      |  2921 | 0.3541 | -0.0381 | -0.0096 | +0.0066 | +0.0293 | -0.0265 | +0.0277 | -0.0043 |
| CSCO   | Large      |  2921 | 0.2594 | -0.0812 | -0.0009 | -0.0437 | -0.0403 | -0.0675 | -0.0418 | -0.0453 |
| CVX    | Large      |  2921 | 0.2901 | -0.0719 | +0.0348 | +0.0031 | -0.1044 | -0.0180 | -0.1060 | +0.0043 |
| DBC    | ETF/Market |  2922 | 0.1800 | +0.0272 | +0.0024 | +0.0199 | -0.0298 | +0.0810 | -0.0314 | +0.1033 |
| DIS    | Large      |  2921 | 0.2802 | -0.0568 | +0.0133 | +0.0046 | -0.1223 | +0.0124 | -0.1238 | +0.0347 |
| EFA    | ETF/Market |  2922 | 0.1726 | -0.0851 | +0.0405 | -0.0120 | -0.1118 | -0.0266 | -0.1133 | -0.0043 |
| GE     | Large      |  2921 | 0.3473 | -0.0217 | +0.0236 | -0.0240 | +0.0602 | -0.0551 | +0.0586 | -0.0329 |
| GLD    | ETF/Market |  2922 | 0.1613 | +0.0014 | -0.0160 | -0.0347 | +0.0353 | -0.0126 | +0.0337 | +0.0097 |
| GOOGL  | Large      |  2921 | 0.2913 | -0.0337 | -0.0063 | -0.0081 | -0.0371 | +0.0213 | -0.0386 | +0.0436 |
| HD     | Large      |  2921 | 0.2442 | -0.0696 | -0.0053 | -0.0207 | -0.1587 | -0.0025 | -0.1603 | +0.0197 |
| IBM    | Large      |  2921 | 0.2728 | -0.0060 | +0.0358 | -0.0311 | -0.1137 | -0.0375 | -0.1153 | -0.0153 |
| INTU   | Large      |  2921 | 0.3329 | -0.0536 | +0.0264 | +0.0170 | +0.0382 | -0.0567 | +0.0366 | -0.0345 |
| JNJ    | Large      |  2921 | 0.1832 | -0.0675 | +0.0158 | -0.0033 | -0.0656 | +0.0062 | -0.0672 | +0.0285 |
| JPM    | Large      |  2921 | 0.2696 | -0.0873 | +0.0501 | +0.0168 | -0.1420 | -0.0792 | -0.1436 | -0.0569 |
| KO     | Large      |  2921 | 0.1791 | -0.0296 | +0.0569 | -0.0424 | -0.2529 | +0.0115 | -0.2544 | +0.0338 |
| LIN    | Large      |  2921 | 0.2239 | -0.0925 | -0.0007 | -0.0104 | -0.2016 | +0.0011 | -0.2031 | +0.0234 |
| LLY    | Large      |  2921 | 0.2979 | -0.0430 | +0.0081 | -0.0070 | -0.0992 | -0.0807 | -0.1008 | -0.0584 |
| MA     | Large      |  2921 | 0.2626 | -0.0744 | -0.0265 | -0.0186 | -0.0764 | +0.0089 | -0.0780 | +0.0312 |
| MCD    | Large      |  2921 | 0.2021 | -0.1035 | +0.0216 | -0.0228 | -0.2237 | -0.0742 | -0.2253 | -0.0520 |
| META   | Large      |  2921 | 0.3785 | -0.0348 | +0.0045 | +0.0376 | +0.0436 | -0.0036 | +0.0421 | +0.0187 |
| MRK    | Large      |  2921 | 0.2276 | -0.0555 | +0.0133 | -0.0067 | -0.0902 | -0.0051 | -0.0918 | +0.0172 |
| MSFT   | Large      |  2921 | 0.2762 | -0.1061 | +0.0156 | +0.0016 | -0.0672 | -0.0118 | -0.0687 | +0.0105 |
| NFLX   | Large      |  2921 | 0.4259 | -0.0032 | -0.0325 | +0.0113 | +0.0203 | -0.0196 | +0.0187 | +0.0027 |
| NVDA   | Large      |  2921 | 0.4819 | -0.0731 | +0.0077 | +0.0215 | +0.0149 | +0.0007 | +0.0134 | +0.0230 |
| ORCL   | Large      |  2921 | 0.3423 | -0.0302 | -0.0111 | +0.0000 | -0.0919 | -0.0329 | -0.0934 | -0.0107 |
| PEP    | Large      |  2921 | 0.1923 | -0.1405 | +0.0520 | -0.0579 | -0.1446 | -0.0942 | -0.1461 | -0.0720 |
| PFE    | Large      |  2921 | 0.2337 | -0.0305 | +0.0089 | -0.0338 | -0.0158 | -0.0709 | -0.0173 | -0.0487 |
| PG     | Large      |  2921 | 0.1868 | -0.0801 | +0.0121 | -0.0101 | -0.0679 | -0.0381 | -0.0695 | -0.0158 |
| PM     | Large      |  2921 | 0.2380 | -0.0528 | +0.0226 | -0.0161 | -0.0476 | -0.0682 | -0.0491 | -0.0460 |
| QCOM   | Large      |  2921 | 0.3862 | -0.0713 | -0.0222 | +0.0074 | -0.1794 | -0.0327 | -0.1809 | -0.0104 |
| QQQ    | Large      |  2921 | 0.2196 | -0.1049 | +0.0161 | -0.0003 | -0.0137 | -0.0447 | -0.0153 | -0.0225 |
| SPGI   | Large      |  2921 | 0.2605 | -0.0904 | +0.0439 | -0.0244 | -0.0967 | +0.0015 | -0.0982 | +0.0238 |
| SPY    | Large      |  2921 | 0.1760 | -0.1186 | +0.0379 | -0.0021 | -0.0919 | -0.0221 | -0.0935 | +0.0001 |
| TIP    | ETF/Market |  2922 | 0.0566 | +0.0733 | +0.0402 | +0.0021 | -0.0054 | +0.0195 | -0.0070 | +0.0418 |
| TLT    | ETF/Market |  2922 | 0.1480 | -0.0257 | +0.0289 | +0.0182 | -0.0096 | +0.0198 | -0.0112 | +0.0420 |
| TMO    | Large      |  2921 | 0.2592 | -0.0501 | +0.0330 | +0.0060 | -0.0712 | +0.0185 | -0.0727 | +0.0408 |
| TSLA   | Large      |  2921 | 0.5720 | -0.0059 | -0.0267 | +0.0081 | +0.0141 | -0.0257 | +0.0125 | -0.0034 |
| TXN    | Large      |  2921 | 0.3090 | -0.1446 | +0.0551 | -0.0163 | -0.1252 | -0.0345 | -0.1267 | -0.0123 |
| UNH    | Large      |  2921 | 0.2940 | -0.0317 | +0.0126 | -0.0332 | -0.0660 | -0.1091 | -0.0676 | -0.0869 |
| V      | Large      |  2921 | 0.2423 | -0.1145 | -0.0010 | -0.0364 | -0.1195 | -0.0298 | -0.1210 | -0.0076 |
| WMT    | Large      |  2921 | 0.2176 | -0.0400 | -0.0116 | +0.0142 | -0.1033 | -0.0018 | -0.1048 | +0.0204 |
| XOM    | Large      |  2921 | 0.2751 | -0.0174 | +0.0460 | +0.0007 | +0.0020 | +0.0443 | +0.0004 | +0.0666 |
| ^VIX   | ETF/Market |  2923 | 1.3672 | -0.0537 | +0.0038 | +0.0140 | -0.1790 | -0.0561 | -0.1805 | -0.0338 |

**Notas de lectura**:
- `n_obs` = filas OHLCV totales; `n_ic` efectivo para IC es ≈ n_obs − 252 (warmup momentum) − 20 (fwd) ≈ 2650 por ticker; varía levemente por NaN iniciales.
- `cap_group`: Large = 50 universo, ETF/Market = 7 régimen, SMID = 0 en este cache.
- ICs negativos dominan en momentum: solo 10/50 tickers superan el pooled MOM Pearson (20%). En RSI, distribución centrada: 25/50 (50%) superan el pooled.
- ^VIX vol_ann 1.367 (>100% anual) y ac1 +0.07: outlier de mercado; no es comparable y se excluye del resumen Large.

## Resumen de dispersión — heterogeneidad cuantificada

### Universo 50 (Large puro) — primario

| Métrica | media | mediana | sd | CV (sd/|mean|) | min | max | rango (max-min) | p10 | p90 | p10-p90 | IQR | N |
|---------|-------|---------|----|--------------|-----|-----|-----------------|-----|-----|---------|-----|---|
| vol_ann | 0.2901 | 0.2725 | 0.0894 | 0.31 | 0.1760 | 0.5983 | 0.4223 | 0.1922 | 0.3871 | 0.1950 | 0.0910 | 50 |
| ac1 | -0.0587 | -0.0561 | 0.0368 | 0.63 | -0.1446 | +0.0119 | 0.1565 | -0.1050 | -0.0060 | 0.0990 | 0.0488 | 50 |
| ac5 | +0.0126 | +0.0131 | 0.0220 | 1.75 | -0.0325 | +0.0569 | 0.0894 | -0.0126 | +0.0441 | 0.0567 | 0.0274 | 50 |
| ac20 | -0.0079 | -0.0068 | 0.0194 | 2.45 | -0.0579 | +0.0376 | 0.0955 | -0.0332 | +0.0144 | 0.0476 | 0.0286 | 50 |
| ic_mom (Pearson) | -0.0748 | -0.0738 | 0.0756 | 1.01 | -0.2529 | +0.0824 | 0.3353 | -0.1608 | +0.0212 | 0.1820 | 0.0995 | 50 |
| ic_rsi (Pearson) | -0.0238 | -0.0239 | 0.0384 | 1.62 | -0.1091 | +0.0846 | 0.1938 | -0.0713 | +0.0188 | 0.0900 | 0.0542 | 50 |

**Sensibilidad Spearman** (mismo universo 50): ic_mom Spearman media -0.0753 mediana -0.0912 sd 0.0733 CV 0.97 rango 0.347 p10 -0.148 p90 +0.008 IQR 0.104; ic_rsi Spearman media -0.0220 mediana -0.0231 sd 0.0393 CV 1.79 rango 0.203 IQR 0.057 — orden y dispersión prácticamente idénticos a Pearson, sin cambio de conclusión.

### Global 57 (50 Large + 7 Market) — referencia

| Métrica | media | mediana | sd | CV | min | max | rango | p10 | p90 | IQR | N |
|---------|-------|---------|----|----|-----|-----|-------|-----|-----|-----|---|
| vol_ann | 0.2919 | 0.2664 | 0.1755 | 0.60 | 0.0519 | 1.3672 | 1.3153 | 0.1779 | 0.3898 | 0.0914 | 57 |
| ac1 | -0.0524 | -0.0536 | 0.0421 | 0.80 | -0.1446 | +0.0733 | 0.2179 | -0.1042 | -0.0030 | 0.0505 | 57 |
| ic_mom | -0.0698 | -0.0681 | 0.0772 | 1.11 | -0.2529 | +0.0824 | 0.3353 | -0.1668 | +0.0317 | 0.1058 | 57 |
| ic_rsi | -0.0196 | -0.0196 | 0.0406 | 2.07 | -0.1091 | +0.0846 | 0.1938 | -0.0693 | +0.0210 | 0.0577 | 57 |

> El 57 mixto infla la dispersión de vol (CV 0.60 vs 0.31) por el outlier ^VIX (1.367) y por AGG/TIP (0.05-0.06, bonos de baja vol). En el resto de métricas el mixto es similar al 50 puro; el resumen primario es el 50.

### Interpretación de la dispersión (respuesta principal)

| Métrica | CV (sd/|mean|) | Rango total | p10-p90 | IQR | Lectura |
|---------|---------------|-------------|---------|-----|---------|
| **vol_ann** | **0.31** (moderado) | 0.422 (0.176-0.598) | 0.195 (0.192-0.387) | 0.091 | Heterogeneidad **moderada y económicamente material**: la vol anualizada entre large-caps varía 3.4× (17.6% SPY vs 59.8% AMD, 57.2% TSLA). p10-p90 ya es 19.5pp, casi 70% de la mediana. Suficiente para justificar que un mismo umbral de `vol_ratio` o `ADX` no trate igual a KO/PG y a NVDA/TSLA. |
| **ac1** | **0.63** | 0.156 | 0.099 | 0.049 | Heterogeneidad **media-alta en términos relativos**, pero en absolutos todos los ac1 son cercanos a cero (rango −0.145 a +0.012, mediana −0.056). La dispersión es 60% de la media porque la media misma es pequeña (reversión intradía débil y heterogénea). No hay tickers con autocorrelación diaria persistente fuerte; el más positivo es ABBV +0.012. |
| **ac5** | **1.75** (CV >1) | 0.089 | 0.057 | 0.027 | CV >1 indica **media ≈0** con ruido: ac5 oscila −0.032 a +0.057 alrededor de +0.013. La dispersión relativa es alta porque el nivel es cercano a cero, no porque haya clusters nítidos. No justifica por sí misma parámetros por ticker. |
| **ac20** | **2.45** (CV >>1) | 0.096 | 0.048 | 0.029 | Mismo patrón: media −0.008 ≈0, sd 0.019, CV 2.45 refleja denominador pequeño. Rango absoluto estrecho (−0.058 a +0.038). Heterogeneidad baja en valor absoluto. |
| **ic_mom** | **1.01** | **0.335** (−0.253 a +0.082) | **0.182** (−0.161 a +0.021) | **0.099** | **Heterogeneidad alta y relevante**: CV≈1 indica sd ≈ |media|, rango 33.5pp y p10-p90 18.2pp. La señal es negativa en mediana (−0.074) y muy dispersa: cola inferior KO −0.253, LIN −0.202, MCD −0.224 vs cola superior ADBE +0.082, GE +0.060. Un peso global único promedia una distribución con signo inconsistente. |
| **ic_rsi** | **1.62** | **0.194** (−0.109 a +0.085) | **0.090** (−0.071 a +0.019) | **0.054** | CV 1.62 >1, pero rango absoluto menor que momentum (19.4pp vs 33.5pp) y IQR más estrecho (5.4pp vs 9.9pp). Heterogeneidad **alta en CV por media pequeña**, moderada en absolutos. Cola negativa UNH −0.109, PEP −0.094 vs cola positiva AMZN +0.085, CMCSA +0.042. Menos disperso que momentum, pero igualmente sin consenso de signo. |

**Conclusión cuantitativa**: la dinámica de precio **sí es distinta entre tickers** de forma medible. La mayor heterogeneidad está en **volatilidad** (moderada, material) y en **IC de momentum** (alta, con cambio de signo entre tickers). Autocorrelaciones son homogéneamente cercanas a cero y no aportan evidencia para diferenciación. Esto **no** implica que calibrar por ticker vaya a generar edge —solo que la premisa empírica "todos los tickers se comportan igual" es falsa y el promedio global esconde distribución ancha.

## Desagregado por cap_group

### Large (50) vs ETF/Market (7) vs SMID (0)

| Grupo | N | vol_ann media/mediana (sd, CV, rango) | ac1 media/mediana | ic_mom media/mediana (sd, CV, rango) | ic_rsi media/mediana (sd, CV) |
|-------|---|----------------------------------------|-------------------|--------------------------------------|-------------------------------|
| **Large (50)** | 50 | 0.290 / 0.273 (0.089, 0.31, 0.422) | −0.059 / −0.056 | −0.0748 / −0.0738 (0.076, 1.01, 0.335) | −0.0238 / −0.0239 (0.038, 1.62, 0.194) |
| **ETF/Market (7)** | 7 | 0.305 / 0.161 (0.471, 1.54, 1.315) — inflado por ^VIX 1.367 y bonos 0.05 | −0.007 / +0.001 | −0.0335 / −0.0096 (0.085, 2.53, 0.245) | +0.0101 / +0.0195 (0.046, 4.55, 0.137) |
| **SMID (0)** | 0 | — (sin datos en este cache) | — | — | — |

**¿Correlaciona con tamaño?** Con el cache actual **no es testeable**: todos los equity son Large, SMID está vacío. Dentro de Large, una inspección ordinal (sin test formal) sugiere que la dispersión no se explica solo por tamaño: los dos extremos de vol (AMD 0.598/TSLA 0.572/NVDA 0.482 en alto; SPY 0.176/KO 0.179/PG 0.187 en bajo) correlacionan con sector/beta, no con market cap dentro de Large. Para testar Large vs SMID se necesita re-ejecutar este mismo script sobre el cache 102 (50 Large + 52 nuevos, ~28 SMID $2-50B) y comparar medianas/IQR con test de rangos (Mann-Whitney) y de varianzas (Levene) — pre-registrado como siguiente paso, no como veredicto.

**Comparación IC Large vs Market**: Market tiene IC momentum ligeramente menos negativo (−0.034 vs −0.075) y RSI positivo (+0.010 vs −0.024), pero con N=7 y colas distintas (ETFs de renta fija y volatilidad) la comparación no es interpretable como "cap effect"; solo confirma que los 7 market tickers no deben mezclarse con el universo equity al estimar pesos.

## Comparación IC individuales vs pooled

### Histograma descriptivo (Pearson, universo 50)

**Momentum_score vs fwd_ret_20d**:

| Bucket IC individual | Count | % | Tickers ejemplo |
|----------------------|-------|---|-----------------|
| < −0.15 | 7 | 14% | KO −0.253, AMGN −0.234, MCD −0.224, LIN −0.202, PEP −0.145, QCOM −0.179, HD −0.159 |
| [−0.15, −0.05) | 21 | 42% | AAPL −0.068, ABBV −0.125, MA −0.076, MSFT −0.067, WMT −0.103, V −0.119, JNJ −0.066, ... |
| [−0.05, 0) | 12 | 24% | AMD −0.037, CSCO −0.040, TSLA +0.014, XOM +0.002, NVDA +0.015, GOOGL −0.037, ... |
| [0, +0.05) | 7 | 14% | CRM +0.029, META +0.044, TMO −0.071→no, INTU +0.038, ACN +0.015, NFLX +0.020, ... |
| ≥ +0.05 | 3 | 6% | ADBE +0.082, GE +0.060, (ninguno >0.10) |

- **Pooled MOM Pearson**: +0.0016. **Mediana individual**: −0.0738. **Media individual**: −0.0748.
- **Tickers que superan el pooled**: **10/50 (20%)**. El pooled está **por encima de la mediana**, pero solo porque 3 outliers positivos (ADBE, GE, META) y la heterocedasticidad de varianzas sesgan el pooled hacia cero, mientras la masa está en negativo.
- **Lectura**: el IC pooled cercano a cero **no representa** a la mayoría: 40/50 (80%) están por debajo del pooled y 28/50 (56%) están por debajo de −0.05. Un peso global proporcional a +0.0016 trataría la señal como nula/positiva cuando la mediana ticker es −0.074 (inversa).

**RSI_score vs fwd_ret_20d**:

| Bucket IC individual | Count | % | Tickers ejemplo |
|----------------------|-------|---|-----------------|
| < −0.05 | 13 | 26% | UNH −0.109, PEP −0.094, MCD −0.074, QCOM −0.033, GE −0.055, LLY −0.081, JPM −0.079, ... |
| [−0.05, 0) | 15 | 30% | AAPL +0.015→no, ABBV −0.003, PFE −0.071, PM −0.068, INTU −0.057, ADBE −0.056, ... |
| [0, +0.05) | 17 | 34% | AAPL +0.015, BRK-B +0.021, GOOGL +0.021, AMZN +0.085, CMCSA +0.042, DIS +0.012, ... |
| ≥ +0.05 | 5 | 10% | AMZN +0.085, CMCSA +0.042, CAT −0.044→no, (solo AMZN destaca) |

- **Pooled RSI Pearson**: −0.0223. **Mediana individual**: −0.0239. **Media**: −0.0238.
- **Tickers que superan el pooled**: **25/50 (50%)** — distribución centrada y simétrica alrededor del pooled.
- **Lectura**: RSI es el factor más **consistente** con el pooled: mediana ≈ pooled, 50% por encima/debajo, IQR estrecho (0.054). Aun así, rango 19.4pp y CV 1.62 indican que el pooled resume mal la cola: UNH/PEP tiran negativo y AMZN/CMCSA positivo.

**Spearman (sensibilidad)**: MOM Spearman pooled −0.0185 vs mediana −0.0912 (9/50 superan), RSI Spearman pooled −0.0212 vs mediana −0.0231 (26/50 superan) — mismo patrón que Pearson; la conclusión no depende del coeficiente.

**Implicancia para pesos globales**: `w_mom=0.66` asume IC_mom > IC_rsi en magnitud (0.0637 vs 0.0322). En este panel, **|IC_mom_mediano| (0.074) > |IC_rsi_mediano| (0.024) en magnitud**, pero **con signo negativo** (no positivo). El orden de magnitud se replica, el signo no. Un peso proporcional a |IC| individual mediano daría `w_mom≈0.76`, más extremo que el global 0.66, pero calibrarlo per-ticker sobre ICs de signo mixto amplificaría ruido —ver limitaciones.

## Limitaciones explícitas (mismo rigor que ANALISIS_RMT_8FACTORES_20260830.md)

1. **Survivorship / selección**: universo 50 es top-43 por market cap + 7 base, líquidos y enlistados 2015-2026; no incluye delistados, SPACs fallidos, ni small caps con quiebra. Sesgo de supervivencia hacia large caps resilientes. Los 52 SMID propuestos fueron filtrados por historia ≥2015 y liquidez —también supervivientes.

2. **Ventana y no-estacionariedad**: ventana única 2015-01-02→2026-08-14 (≈11.6 años, 2921 días). No hay split W1/W2/W3 ni walk-forward. Los ICs y vols agregan regímenes alcista/bajista, COVID, tightening y bull 2023-24. Un ticker puede tener IC negativo en 2020-21 y positivo en 2023-26; el promedio lo esconde. La heterogeneidad reportada mezcla heterogeneidad transversal y temporal.

3. **No out-of-sample, no inferencia**: sin pre-registro, sin corrección por múltiples comparaciones, sin SE/Newey-West, sin test de diferencia de ICs. Los IC individuales son descriptivos; no se reporta significancia ni se propone umbral. Cualquier "mejora" per-ticker requeriría validación OOS con `trial_registry` y DSR (Bailey & López de Prado) como en todos los trials previos.

4. **Lookahead en fwd_ret_20d**: `close.shift(-20)` usa precio futuro 20 ruedas adelante; es correcto para IC diagnóstico pero solapa ventanas (stride 1 vs horizonte 20) y autocorrela `fwd_ret` (una caída el día t+20 afecta 20 filas). Los IC individuales no corrigen por overlap; el SE estaría inflado. No afecta el ranking relativo entre tickers (todos sufren el mismo overlap), pero invalida p-values naïve.

5. **Heterocedasticidad y pooling**: el IC pooled concatena filas con varianzas y niveles de `fwd_ret` distintos por ticker y por fecha. Tickers volátiles (AMD, TSLA) contribuyen más varianza al pooled que SPY/KO, sesgando el pooled hacia sus ICs. La comparación mediana vs pooled ya captura ese sesgo.

6. **Sin filtro eligible**: el motor solo tradea días con `trend_ok & adx≥20 & rsi 40-75 & vol_ratio≥1 & score≥0.60`. Aquí los IC se miden **sin** ese filtro para comparar tickers en igualdad de condiciones. El IC dentro del gate (el que importa para PnL) puede tener signo y magnitud distintos —documentado: gate concentra señal (IC momentum dentro >> fuera). Este diagnóstico no mide IC dentro del gate por ticker (requiere replicar gates por barra y reduciría n por ticker).

7. **Derivación de factores, no factores del motor**: `momentum_score` y `rsi_score` se derivan de `close` en este diagnóstico con la fórmula exacta del motor, pero sin el pipeline completo (`calculate_all_indicators`, `volume_sma20`, `ema50/200` exactos) ni ajustes corporativos idénticos. Es fiel a `signal_engine.py:137-142`, no a un parquet de factores cacheado (no existe `momentum_score` en los parquet OHLCV). Diferencias numéricas mínimas (<1e-6) posibles.

8. **Warmup y n**: `momentum_12_1` requiere 252 días; los primeros 252 filas por ticker son NaN y se excluyen del IC (n_ic≈2650). Tickers con splits/dividendos ajustados por yfinance pueden tener artefactos en retornos no auditados.

9. **Metric fragilidad**: `rsi_score` es binario (0.4/0.8) —su correlación con `fwd_ret_20d` es punto-biserial; pequeños cambios de banda (45-70) cambian IC. `momentum_score` es clip lineal, saturado en colas; tickers en tendencia extrema pierden gradiente.

10. **Cap group incompleto**: SMID vacío en este cache. Cualquier conclusión sobre "tamaño explica heterogeneidad" es **no testeable** aquí. La sincronización del cache 102 (rsync desde `test-kilo-orca`) es prerrequisito para desagregar Large vs SMID.

11. **No propone calibración per-ticker**: este documento **solo cuantifica heterogeneidad**. No recomienda, no estima, no valida pesos por ticker, shrinkage, ni clustering. La evidencia de heterogeneidad es **necesaria pero no suficiente** para justificar calibración: se requiere demostrar que un esquema per-ticker (o por cluster) mejora ICIR/OOS neto de costos y DSR, con pre-registro y embargo, como todos los trials §25-§44.

## Artefactos y código leído (trazabilidad)

- **Cache**: `backend/data/cache/*.parquet` (57 archivos, 2921-2923 filas c/u) —`AAPL.parquet`, `SPY.parquet`, etc. `backend/data/cache/baseline_clean_20260828_183624_*.parquet` excluidos.
- **Definición universo**: `backend/scripts/fetch_universe_data.py:12` (NEW_UNIVERSE 43), `backend/app/api/routes/opportunities_universe.py:19-35` (SYMBOLS 50), `backend/tests/test_pipeline_daily_signal.py: w==0.6642/0.3358`.
- **Pesos e IC origen**: `backend/app/core/signal_engine.py:73-90` (priors 0.0637/0.0322 → w 0.6642/0.3358), `backend/app/core/probabilistic_engine.py:173-186` (Pearson/Spearman), `backend/app/core/indicators.py:25-30,381` (RSI, momentum), `backend/app/core/backtest_engine.py:23` (CALIBRATION_HORIZON_DAYS=20).
- **Docs**: `PROPUESTA_AMPLIACION_UNIVERSO.md` (ausente en este worktree, presente en `test-kilo-orca/PROPUESTA_AMPLIACION_UNIVERSO.md:4-52`), `ANALISIS_RMT_8FACTORES_20260830.md` (plantilla de rigor), `RESUMEN_VALIDACION_VARIABLES.md`, `PLAN_MEJORA_MATEMATICA.md`, `AUDITORIA_MECANICA.md`, `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:26`, `PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md:31`.
- **Scripts de este diagnóstico** (no pre-registrados, solo lectura): `/tmp/diagnostico_heterogeneidad.py`, `/tmp/generate_md.py`, `/tmp/diag_output.txt`, `/tmp/heterogeneidad_per_ticker.csv`, `/tmp/heterogeneidad_summary.json` (efímeros, no trackeados).
- **Verificación de no-escritura**: `git status --porcelain` muestra solo este `.md` como untracked; no se modificó `fortress.db`, `backend/data/cache/*`, `trial_registry`, ni se creó `PRE_REGISTRO_*`. La restricción solo-lectura se cumplió.

## Entrega y handoff

**Archivo**: `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (este archivo) — ` /Users/boris/orca/workspaces/fortress_core/test-opencode-orca/DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md`

**Stats clave para orquestador** (universo 50, Pearson):

| Métrica | CV | rango | p10-p90 | IQR | mediana individual vs pooled |
|---------|----|-------|---------|-----|------------------------------|
| vol_ann | **0.31** | **0.422** (0.176-0.598) | 0.195 | 0.091 | — |
| ac1 | 0.63 | 0.156 | 0.099 | 0.049 | — |
| ic_mom | **1.01** | **0.335** (−0.253 a +0.082) | **0.182** | **0.099** | **mediana −0.0738 vs pooled +0.0016, delta −0.0754, 10/50 (20%) superan pooled** |
| ic_rsi | **1.62** | **0.194** (−0.109 a +0.085) | **0.090** | **0.054** | **mediana −0.0239 vs pooled −0.0223, delta −0.0016, 25/50 (50%) superan pooled** |

**Cap**: Large 50 analizado; SMID 0 en este cache — re-ejecutar tras sincronizar 102 (rsync `test-kilo-orca/backend/data/cache/*.parquet` → `test-opencode-orca/backend/data/cache/` + validar `SYMBOLS=102`).

**Próximo paso recomendado** (no veredicto): sincronizar cache 102, re-correr **idéntica** metodología (`/tmp/diagnostico_heterogeneidad.py` sin cambios salvo `cache_path` y `UNIVERSE_102` desde `test-kilo-orca/fetch_universe_data.py`), producir tabla 102 filas y test Large vs SMID (Mann-Whitney sobre vol_ann/ic_mom/ic_rsi + Levene). Solo entonces evaluar si un esquema shrinkage hacia global o por cluster aporta ICIR OOS —siempre con pre-registro nuevo.

---
*Fin del diagnóstico — 2026-09-01, solo lectura, sin veredicto de trading.*
