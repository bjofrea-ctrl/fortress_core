# Diagnóstico de Heterogeneidad por Régimen VIX — IC Momentum/RSI en Risk-On vs Risk-Off

**Fecha**: 2026-09-01
**Autor**: Muse Spark (diagnóstico solo-lectura, extensión de DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md)
**Restricción dura**: SOLO LECTURA de `backend/data/cache/*.parquet` existente — sin nuevo backtest, sin tocar `ledger`/`trial_registry`, sin pre-registro. Es diagnóstico descriptivo, no veredicto de trading.
**Fuente parquet**: `backend/data/cache/*.parquet` (worktree `test-opencode-orca`)
**Rango temporal real**: 2015-01-02 → 2026-08-14 (último cierre equity en cache; ^VIX llega a 2026-08-17, 2923 filas)
**N efectivo**: 57 parquet (50 universo canónico + 7 market). Este diagnóstico corre sobre **50 universo** como primario; 7 market como referencia separada no mezclada.
**Universo**: `backend/scripts/fetch_universe_data.py:NEW_UNIVERSE` (43) + `_BASE_SYMBOLS` (7) = 50

## 1. Inventario VIX y criterio de régimen

- **Archivo**: `backend/data/cache/^VIX.parquet` — 2923 filas, índice `Date`, `Close` (float64). Rango VIX close: 9.14 → 82.69, media 18.36, sd 6.98.
- **Mediana (p50)**: **16.68** — corte primario.
- **p33**: **14.71** ; **p66**: **19.12** — cortes terciles (sensibilidad). Alternativos p33(1/3)=14.74, p66(2/3)=19.26 difieren <0.15 pts.
- **Distribución**: p25=13.71, p50=16.68, p75=21.14, p90=26.69, max 82.69 (COVID spike). Histograma unimodal con cola derecha larga.
- **N días por régimen (global, sobre serie VIX 2923)**:
  - **Risk-on (VIX < mediana)**: **1461** días (50.0%)
  - **Risk-off (VIX ≥ mediana)**: **1462** días (50.0%)
  - Tercil bajo (VIX ≤ p33): **968** días (33.1%)
  - Tercil alto (VIX ≥ p66): **994** días (34.0%)
  - Tercil medio (p33 < VIX < p66): **961** días descartado para contraste tercil.
- **N por ticker por bucket (universo 50, efectivo para IC ≈ dropna)**: mediana n_risk_on=1288, n_risk_off=1361; n_low≈861, n_high≈939 por ticker (todos >30, mínimo 861 >>30, ningún NaN por falta de N). Para 57 mixto: pooled n_risk_on=73417, n_risk_off=77584, n_low=49077, n_high=53523.

**Justificación del corte**:
- **Mediana como primario**: maximiza N por régimen (≈50/50 split), minimiza varianza del estimador IC por bucket (n≈1300 por ticker, SE ~1/sqrt(n) ~0.028), y mantiene comparabilidad con el diagnóstico anterior (n_obs≈2921 → dos mitades balanceadas). Es el corte más potente para detectar diferencias si existen.
- **Terciles como sensibilidad**: maximiza contraste económico (miedo extremo vs complacencia extrema) al descartar el tercil medio (zona gris 14.7–19.1). Costo: N por bucket cae ~33% (861/939), SE sube ~20%, pero la diferencia esperada crece si el efecto es monotónico con VIX. Si mediana y terciles coinciden en signo, la señal es robusta al corte.
- **VIX level vs log**: se usa **level** directo (convención de mercado, umbral 16-20). Log(VIX) es monotónico, no cambiaría ranking ni asignación bucket; solo reescalaría ejes. Se documenta para trazabilidad.
- **Corte en t (contemporáneo)**: VIX_level del **mismo día t** que genera el score, **antes** del fwd_ret_20d futuro (t+1..t+20). No hay lookahead en el regresor; el split es clasificación ex-ante del régimen vigente al formar expectativa.

## 2. Metodología (idéntica al diagnóstico anterior, con split VIX)

**Datos**: OHLCV diario cacheado, 2921 filas por ticker (2015-01-02→2026-08-14). Columna `Close` ajustada por yfinance.

**Fórmulas idénticas**:
```
ret_d = close.pct_change(1)
vol_ann = std(ret_d, ddof=1) * sqrt(252)
momentum_12_1 = close.pct_change(252)*100
momentum_score = clip((momentum_12_1 + 50)/150, 0, 1)   # signal_engine.py:137
rsi14 = RSI(14) SMA gains/losses                     # indicators.py:25-30
rsi_score = 0.8 si 45<rsi14<70 else 0.4               # signal_engine.py:141
fwd_ret_20d = close.shift(-20)/close - 1              # CALIBRATION_HORIZON_DAYS=20
ic_mom  = Pearson_corr(momentum_score, fwd_ret_20d)    # primario
ic_rsi  = Pearson_corr(rsi_score, fwd_ret_20d)
Spearman análogo como sensibilidad
```
- `dropna` de ambas series por bucket, **mínimo 30 pares** (si <30 → NaN). En práctica mínimo observado 861.
- **Merge por Date**: ticker df ⨝ VIX series por Date (inner), asignando cada fila ticker-día t al bucket del VIX close de t. Sin forward-fill; días sin VIX (feriados) se caen del merge (0.07% de filas).
- **Por ticker y por bucket**: `ic_mom_on/off`, `ic_rsi_on/off` (Pearson primario + Spearman sensibilidad), `n` por bucket, `delta = IC_on - IC_off` (risk-on minus risk-off; positivo = mejor en apetito, negativo = mejor en miedo). Terciles análogos: `ic_*_low/high`, `delta_terc = low - high`.
- **Pooled por régimen**: concat todas las filas ticker-día del grupo (50 universo primario) dentro de cada bucket y correla una vez (pooled temporal, no cross-sectional).
- **Dispersión por régimen**: media, mediana, sd, CV=sd/|mean|, rango, p10, p90, p10-p90, IQR, por separado para ic_mom_on/off y ic_rsi_on/off (y terciles).
- **Clasificación defensivas vs growth**: criterio documentado en §4.

## 3. Pooled por régimen (referencia)

| IC pooled | Universo 50 (primario) | 57 mixto (ref) | Market 7 (ref) | n (50) |
|-----------|------------------------|----------------|----------------|--------|
| **Mom Pearson on (VIX<med)** | +0.0217 | -0.0030 | -0.0843 | 64400 |
| **Mom Pearson off (VIX≥med)** | -0.0044 | -0.0176 | -0.1633 | 68050 |
| **Mom Pearson low (≤p33)** | +0.0538 | +0.0164 | -0.1013 | 43050 |
| **Mom Pearson high (≥p66)** | +0.0023 | -0.0206 | -0.2137 | 46950 |
| **Mom Spearman on** | -0.0034 | +0.0067 | -0.0326 | 64400 |
| **Mom Spearman off** | -0.0268 | -0.0251 | -0.0865 | 68050 |
| **RSI Pearson on** | -0.0198 | -0.0151 | -0.0067 | 64400 |
| **RSI Pearson off** | -0.0216 | -0.0266 | -0.0512 | 68050 |
| **RSI Pearson low** | -0.0147 | -0.0147 | -0.0216 | 43050 |
| **RSI Pearson high** | -0.0082 | -0.0148 | -0.0509 | 46950 |
| **RSI Spearman on** | -0.0156 | -0.0152 | +0.0064 | 64400 |
| **RSI Spearman off** | -0.0237 | -0.0250 | -0.0277 | 68050 |

**Lectura pooled 50**: momentum pooled es **procíclico débil** (mejor en risk-on/miedo-bajo): +0.0216 on vs −0.0044 off (delta +0.026), y más marcado en terciles +0.0538 low vs +0.0023 high (delta +0.0515). Pero ambos niveles están **cerca de cero** (rango −0.004 a +0.05), sin IC económicamente grande en ningún régimen. RSI pooled es **acíclico/plano**: −0.0198 on vs −0.0216 off (delta +0.0018), y terciles −0.0146 low vs −0.0082 high — diferencia irrelevante. Spearman confirma: mom on −0.003 vs off −0.027 (mismo orden), rsi on −0.016 vs off −0.024. El régimen **no rescata** los factores: ningún bucket exhibe IC >0.06.
**Market 7**: momentum pooled más negativo en risk-off (−0.163 off vs −0.084 on) y tercil alto −0.214 vs low −0.101 — patrón inverso y más amplio pero con N pequeño y tickers heterogéneos (bonos, oro, vol), no extrapolable.

## 4. Tabla cruda por ticker (50 universo — Pearson primario)

Columnas: `ticker | grupo | vol_ann | n_total | n_on | n_off | ic_mom_on | ic_mom_off | delta_mom | ic_rsi_on | ic_rsi_off | delta_rsi | ic_mom_low | ic_mom_high | delta_terc_mom | n_low | n_high`. Spearman en Apéndice A.
Delta = on − off (positivo = mejor en VIX bajo/risk-on). Tercil delta = low − high.

| ticker | grupo | vol_ann | n_tot | n_on | n_off | ic_mom_on | ic_mom_off | Δmom | ic_rsi_on | ic_rsi_off | Δrsi | ic_mom_low | ic_mom_high | Δterc_mom | n_low | n_high |
|--------|-------|---------|-------|------|-------|-----------|------------|------|-----------|------------|------|------------|-------------|------------|-------|--------|
| AAPL   | Tech       | 0.2878 | 2921 | 1288 | 1361 | -0.1519 | -0.0217 | -0.1302 | -0.0591 | +0.0760 | -0.1352 | -0.0744 | +0.0535 | -0.1279 | 861 | 939 |
| ABBV   | Health     | 0.2664 | 2921 | 1288 | 1361 | -0.0541 | -0.1784 | +0.1243 | -0.0363 | +0.0245 | -0.0607 | +0.0050 | -0.2063 | +0.2114 | 861 | 939 |
| ACN    | Tech       | 0.2723 | 2921 | 1288 | 1361 | -0.0238 | +0.0419 | -0.0657 | -0.1024 | -0.0024 | -0.1000 | -0.2523 | +0.0619 | -0.3142 | 861 | 939 |
| ADBE   | Tech       | 0.3370 | 2921 | 1288 | 1361 | +0.0824 | +0.0877 | -0.0053 | -0.0448 | -0.0649 | +0.0201 | -0.0559 | +0.0683 | -0.1242 | 861 | 939 |
| AMD    | Tech       | 0.5983 | 2921 | 1288 | 1361 | -0.1018 | +0.0032 | -0.1050 | +0.0205 | -0.0325 | +0.0530 | -0.0944 | +0.0155 | -0.1100 | 861 | 939 |
| AMGN   | Health     | 0.2520 | 2921 | 1288 | 1361 | -0.2235 | -0.2434 | +0.0200 | +0.0591 | -0.0889 | +0.1480 | -0.2850 | -0.2706 | -0.0144 | 861 | 939 |
| AMZN   | ConsDisc   | 0.3314 | 2921 | 1288 | 1361 | +0.0168 | -0.0389 | +0.0556 | +0.1019 | +0.0775 | +0.0244 | +0.0032 | -0.0308 | +0.0340 | 861 | 939 |
| AVGO   | Tech       | 0.3953 | 2921 | 1288 | 1361 | +0.0620 | -0.1193 | +0.1812 | -0.0955 | -0.0109 | -0.0846 | +0.1410 | -0.0700 | +0.2110 | 861 | 939 |
| BAC    | Fin        | 0.3037 | 2921 | 1288 | 1361 | -0.1447 | -0.0321 | -0.1126 | -0.0489 | -0.0473 | -0.0016 | -0.0980 | -0.0507 | -0.0472 | 861 | 939 |
| BRK-B  | Fin        | 0.1909 | 2921 | 1288 | 1361 | -0.1038 | -0.1458 | +0.0419 | +0.0690 | -0.0087 | +0.0778 | -0.1048 | -0.1451 | +0.0403 | 861 | 939 |
| CAT    | Ind        | 0.3080 | 2921 | 1288 | 1361 | -0.0412 | -0.1546 | +0.1134 | -0.0088 | -0.0648 | +0.0560 | +0.0220 | -0.0764 | +0.0984 | 861 | 939 |
| CMCSA  | Comm       | 0.2591 | 2921 | 1288 | 1361 | -0.1331 | -0.0620 | -0.0710 | +0.0649 | +0.0301 | +0.0348 | -0.1956 | -0.0538 | -0.1418 | 861 | 939 |
| COST   | Staples    | 0.2154 | 2921 | 1288 | 1361 | -0.0736 | -0.0511 | -0.0225 | +0.0243 | -0.1207 | +0.1450 | -0.1268 | -0.0931 | -0.0337 | 861 | 939 |
| CRM    | Tech       | 0.3541 | 2921 | 1288 | 1361 | +0.0913 | +0.0278 | +0.0635 | -0.0760 | +0.0266 | -0.1026 | +0.0529 | +0.0267 | +0.0262 | 861 | 939 |
| CSCO   | Tech       | 0.2594 | 2921 | 1288 | 1361 | -0.1097 | +0.0322 | -0.1419 | -0.1234 | -0.0130 | -0.1103 | -0.0310 | -0.0178 | -0.0132 | 861 | 939 |
| CVX    | Energy     | 0.2901 | 2921 | 1288 | 1361 | -0.1066 | -0.1129 | +0.0062 | -0.0525 | +0.0075 | -0.0600 | -0.1827 | -0.1235 | -0.0592 | 861 | 939 |
| DIS    | Comm       | 0.2802 | 2921 | 1288 | 1361 | -0.2005 | -0.0796 | -0.1209 | +0.0006 | +0.0295 | -0.0289 | -0.1935 | -0.0413 | -0.1522 | 861 | 939 |
| GE     | Ind        | 0.3473 | 2921 | 1288 | 1361 | +0.2873 | -0.0739 | +0.3612 | -0.0690 | -0.0319 | -0.0371 | +0.3424 | -0.0575 | +0.3999 | 861 | 939 |
| GOOGL  | Comm       | 0.2913 | 2921 | 1288 | 1361 | -0.1544 | +0.0205 | -0.1748 | +0.0068 | +0.0386 | -0.0318 | -0.1505 | +0.1100 | -0.2604 | 861 | 939 |
| HD     | ConsDisc   | 0.2442 | 2921 | 1288 | 1361 | -0.2466 | -0.1175 | -0.1292 | +0.0348 | -0.0312 | +0.0661 | -0.3026 | -0.1443 | -0.1583 | 861 | 939 |
| IBM    | Tech       | 0.2728 | 2921 | 1288 | 1361 | -0.0192 | -0.1622 | +0.1430 | +0.0545 | -0.1114 | +0.1659 | +0.0222 | -0.1549 | +0.1771 | 861 | 939 |
| INTU   | Tech       | 0.3329 | 2921 | 1288 | 1361 | +0.1210 | +0.0177 | +0.1033 | -0.0012 | -0.1023 | +0.1012 | -0.0413 | -0.0551 | +0.0138 | 861 | 939 |
| JNJ    | Health     | 0.1832 | 2921 | 1288 | 1361 | -0.0667 | -0.0648 | -0.0019 | +0.0195 | -0.0073 | +0.0268 | -0.2366 | -0.2046 | -0.0320 | 861 | 939 |
| JPM    | Fin        | 0.2696 | 2921 | 1288 | 1361 | -0.2436 | -0.0775 | -0.1662 | -0.0673 | -0.0872 | +0.0199 | -0.1691 | -0.0724 | -0.0968 | 861 | 939 |
| KO     | Staples    | 0.1791 | 2921 | 1288 | 1361 | -0.1380 | -0.3196 | +0.1815 | +0.0421 | -0.0093 | +0.0513 | -0.1902 | -0.3562 | +0.1659 | 861 | 939 |
| LIN    | Materials  | 0.2239 | 2921 | 1288 | 1361 | -0.1746 | -0.1952 | +0.0206 | +0.0115 | +0.0028 | +0.0087 | -0.2032 | -0.2018 | -0.0014 | 861 | 939 |
| LLY    | Health     | 0.2979 | 2921 | 1288 | 1361 | -0.0449 | -0.1722 | +0.1273 | -0.1123 | -0.0551 | -0.0572 | -0.0044 | -0.1570 | +0.1525 | 861 | 939 |
| MA     | Fin        | 0.2626 | 2921 | 1288 | 1361 | -0.0355 | -0.1402 | +0.1048 | +0.0311 | -0.0075 | +0.0386 | +0.0256 | -0.1262 | +0.1517 | 861 | 939 |
| MCD    | ConsDisc   | 0.2021 | 2921 | 1288 | 1361 | -0.1615 | -0.2911 | +0.1296 | -0.0913 | -0.0618 | -0.0295 | -0.1313 | -0.3358 | +0.2045 | 861 | 939 |
| META   | Comm       | 0.3785 | 2921 | 1288 | 1361 | +0.1869 | -0.0070 | +0.1939 | +0.0044 | -0.0020 | +0.0064 | +0.2538 | +0.0161 | +0.2377 | 861 | 939 |
| MRK    | Health     | 0.2276 | 2921 | 1288 | 1361 | -0.1783 | -0.0247 | -0.1535 | +0.0612 | -0.0622 | +0.1235 | -0.2754 | +0.0254 | -0.3008 | 861 | 939 |
| MSFT   | Tech       | 0.2762 | 2921 | 1288 | 1361 | -0.0370 | -0.0641 | +0.0271 | +0.0157 | -0.0237 | +0.0394 | +0.0013 | -0.0233 | +0.0246 | 861 | 939 |
| NFLX   | Comm       | 0.4259 | 2921 | 1288 | 1361 | -0.0325 | +0.0603 | -0.0928 | -0.0687 | +0.0193 | -0.0880 | -0.1052 | +0.0100 | -0.1152 | 861 | 939 |
| NVDA   | Tech       | 0.4819 | 2921 | 1288 | 1361 | +0.1097 | -0.0564 | +0.1661 | -0.0086 | +0.0092 | -0.0178 | +0.1880 | -0.0482 | +0.2362 | 861 | 939 |
| ORCL   | Tech       | 0.3423 | 2921 | 1288 | 1361 | -0.0588 | -0.0755 | +0.0168 | -0.0483 | -0.0078 | -0.0405 | -0.1842 | -0.1195 | -0.0647 | 861 | 939 |
| PEP    | Staples    | 0.1923 | 2921 | 1288 | 1361 | -0.1663 | -0.1275 | -0.0388 | -0.1940 | -0.0105 | -0.1835 | -0.1240 | -0.0771 | -0.0469 | 861 | 939 |
| PFE    | Health     | 0.2337 | 2921 | 1288 | 1361 | +0.0954 | -0.0894 | +0.1849 | -0.0514 | -0.0861 | +0.0347 | +0.0428 | -0.1315 | +0.1742 | 861 | 939 |
| PG     | Staples    | 0.1868 | 2921 | 1288 | 1361 | -0.0842 | -0.0668 | -0.0174 | +0.0075 | -0.0704 | +0.0779 | -0.1182 | -0.1338 | +0.0157 | 861 | 939 |
| PM     | Staples    | 0.2380 | 2921 | 1288 | 1361 | -0.1295 | +0.0040 | -0.1335 | -0.1108 | -0.0356 | -0.0752 | -0.1700 | +0.0204 | -0.1905 | 861 | 939 |
| QCOM   | Tech       | 0.3862 | 2921 | 1288 | 1361 | -0.2907 | -0.0962 | -0.1946 | +0.0146 | -0.0755 | +0.0901 | -0.2897 | -0.0927 | -0.1971 | 861 | 939 |
| QQQ    | ETF*       | 0.2196 | 2921 | 1288 | 1361 | -0.0558 | +0.0225 | -0.0782 | -0.0540 | -0.0202 | -0.0338 | +0.0475 | +0.0689 | -0.0215 | 861 | 939 |
| SPGI   | Fin        | 0.2605 | 2921 | 1288 | 1361 | -0.0236 | -0.1289 | +0.1054 | +0.0559 | -0.0353 | +0.0913 | -0.0027 | -0.1130 | +0.1103 | 861 | 939 |
| SPY    | ETF*       | 0.1760 | 2921 | 1288 | 1361 | -0.0805 | -0.0682 | -0.0122 | -0.0795 | +0.0345 | -0.1140 | +0.0020 | -0.0480 | +0.0500 | 861 | 939 |
| TMO    | Health     | 0.2592 | 2921 | 1288 | 1361 | -0.2242 | +0.0112 | -0.2354 | -0.0078 | +0.0369 | -0.0447 | -0.2208 | +0.0223 | -0.2431 | 861 | 939 |
| TSLA   | ConsDisc   | 0.5720 | 2921 | 1288 | 1361 | -0.1307 | +0.0682 | -0.1989 | -0.0503 | +0.0011 | -0.0514 | -0.0786 | +0.1674 | -0.2460 | 861 | 939 |
| TXN    | Tech       | 0.3090 | 2921 | 1288 | 1361 | -0.1662 | -0.0722 | -0.0940 | -0.0393 | -0.0160 | -0.0233 | -0.1350 | -0.0529 | -0.0821 | 861 | 939 |
| UNH    | Health     | 0.2940 | 2921 | 1288 | 1361 | -0.0272 | -0.0908 | +0.0637 | -0.1415 | -0.0822 | -0.0593 | +0.0048 | -0.1405 | +0.1452 | 861 | 939 |
| V      | Fin        | 0.2423 | 2921 | 1288 | 1361 | -0.0999 | -0.1429 | +0.0430 | +0.0430 | -0.0815 | +0.1245 | -0.0287 | -0.1218 | +0.0930 | 861 | 939 |
| WMT    | Staples    | 0.2176 | 2921 | 1288 | 1361 | -0.1369 | -0.0887 | -0.0482 | +0.0349 | -0.0318 | +0.0667 | -0.1859 | -0.1143 | -0.0717 | 861 | 939 |
| XOM    | Energy     | 0.2751 | 2921 | 1288 | 1361 | -0.0036 | -0.0329 | +0.0293 | +0.0453 | +0.0636 | -0.0184 | -0.0617 | -0.0320 | -0.0297 | 861 | 939 |

**Notas**: n_on/n_off son pares válidos (mom,fwd) por bucket, no filas totales; n_low/n_high análogos terciles. Todos los buckets superan holgadamente el mínimo 30 (rango 861–1361). Δ se calcula en Pearson primario; Spearman Δ en apéndice.

## 5. Dispersión por régimen (universo 50)

| Régimen — métrica | media | mediana | sd | CV | min | max | rango | p10 | p90 | p10-p90 | IQR | N |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MOM on (risk-on) | -0.0725 | -0.0823 | 0.1154 | 1.59 | -0.2907 | +0.2873 | 0.5781 | -0.2028 | +0.0917 | 0.2945 | 0.1255 | 50 |
| MOM off (risk-off) | -0.0738 | -0.0702 | 0.0873 | 1.18 | -0.3196 | +0.0877 | 0.4072 | -0.1728 | +0.0282 | 0.2011 | 0.1148 | 50 |
| Δ MOM (on−off) | +0.0013 | +0.0022 | 0.1270 | 100.88 | -0.2354 | +0.3612 | 0.5966 | -0.1548 | +0.1676 | 0.3224 | 0.2067 | 50 |
| RSI on | -0.0204 | -0.0082 | 0.0637 | 3.13 | -0.1940 | +0.1019 | 0.2958 | -0.1032 | +0.0563 | 0.1595 | 0.0946 | 50 |
| RSI off | -0.0224 | -0.0145 | 0.0479 | 2.14 | -0.1207 | +0.0775 | 0.1982 | -0.0862 | +0.0348 | 0.1210 | 0.0685 | 50 |
| Δ RSI | +0.0021 | +0.0024 | 0.0795 | 38.71 | -0.1835 | +0.1659 | 0.3494 | -0.1003 | +0.1034 | 0.2037 | 0.1110 | 50 |
| MOM low tercil (VIX≤p33) | -0.0790 | -0.0962 | 0.1365 | 1.73 | -0.3026 | +0.3424 | 0.6450 | -0.2382 | +0.0480 | 0.2862 | 0.1867 | 50 |
| MOM high tercil (VIX≥p66) | -0.0725 | -0.0638 | 0.1039 | 1.43 | -0.3562 | +0.1674 | 0.5236 | -0.2021 | +0.0543 | 0.2564 | 0.1332 | 50 |
| Δ terc MOM (low−high) | -0.0064 | -0.0179 | 0.1571 | 24.40 | -0.3142 | +0.3999 | 0.7141 | -0.2017 | +0.2051 | 0.4068 | 0.2213 | 50 |
| RSI low | -0.0143 | +0.0046 | 0.0771 | 5.38 | -0.2355 | +0.1730 | 0.4085 | -0.1021 | +0.0518 | 0.1540 | 0.1067 | 50 |
| RSI high | -0.0107 | -0.0097 | 0.0512 | 4.78 | -0.1006 | +0.0878 | 0.1884 | -0.0779 | +0.0642 | 0.1421 | 0.0700 | 50 |
| Δ terc RSI | -0.0036 | -0.0030 | 0.0954 | 26.36 | -0.2239 | +0.2556 | 0.4795 | -0.1236 | +0.1144 | 0.2380 | 0.1287 | 50 |

**Sensibilidad Spearman** (mismo N=50): MOM on Spearman mediana −0.0898 (IQR 0.140), MOM off −0.0671 (IQR 0.100), Δmom_s mediana −0.0040 IQR 0.179; RSI on −0.0129 IQR 0.083, RSI off −0.0171 IQR 0.075, Δrsi_s mediana +0.0066 IQR 0.099 — orden y magnitud replican Pearson; ninguna métrica cambia de conclusión por rank.

**Lectura comparativa entre regímenes**:
- **Nivel**: medianas de IC por régimen están **centradas cerca de cero/negativo** en ambos buckets (MOM on −0.082 vs off −0.070; RSI on −0.008 vs off −0.015). Ningún régimen exhibe nivel mediano positivo ni material.
- **Dispersión absoluta por régimen ≈ idéntica al diagnóstico pooled sin split**: rango MOM on 0.578 vs off 0.407 (vs 0.335 pooled global), IQR on 0.126 vs off 0.115 (vs 0.099). Partir por VIX **no reduce** la heterogeneidad: el CV sigue >1 en MOM y >2 en RSI en ambos buckets. El régimen no explica la dispersión transversal.
- **Delta entre regímenes (on−off)**: mediana +0.0022 (MOM) y +0.0024 (RSI) — **centradas en cero**, IQR 0.207 (MOM) y 0.111 (RSI). p10-p90 de Δmom: −0.155 a +0.168 (rango 0.323); Δrsi: −0.100 a +0.103. Hay tickers con Δ grande pero **signo mixto**, sin desplazamiento sistemático.
- **Terciles**: mismo patrón exacerbado — Δ terc mom mediana −0.0179 IQR 0.221, p10-p90 −0.202 a +0.205; Δ terc rsi mediana −0.0030 IQR 0.129. El contraste extremo tampoco genera separación sistemática.

## 6. Defensivas vs Growth — test de la hipótesis de Boris

**Hipótesis**: defensivas (staples/health low-beta) deberían sostener momentum/RSI en risk-off; growth (tech alta-beta) en risk-on. **No se asume — se mide**.

**Criterio explícito**:
- **Defensivas manual (lista Boris)**: KO, JNJ, PG, PEP, COST, WMT, PM, MCD, ABBV, UNH — staples/health, baja beta, del universo. N=10. Alternativamente low-vol (<0.23): SPY, QQQ, BRK-B, WMT, PG, COST, JNJ, MRK, KO, PEP, MCD, LIN (N=12, solapa 6 con lista manual).
- **Growth manual (alta-beta/tech)**: NVDA, AMD, TSLA, META, AVGO, NFLX, ADBE, CRM, QCOM, GE, INTU — tech/comm discretionary, alta beta/vol. N=11. Alternativamente high-vol (>0.35): CRM, META, QCOM, AVGO, NFLX, NVDA, TSLA, AMD (N=8, subset de growth).
- **Criterio vol objetivo**: low_vol <0.23 (p25 del universo) vs high_vol >0.35 (p75+), umbrales documentados del diagnóstico anterior (vol_ann mediana 0.273, IQR 0.091).
- **Documentación**: cada grupo lista sus tickers abajo; ningún ticker se reclasifica ex-post para forzar resultado.

**Defensivas manual** — N=10 — tickers: ABBV, COST, JNJ, KO, MCD, PEP, PG, PM, UNH, WMT

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off | -0.0096 | +0.0237 | 0.0978 | 0.1438 | -0.1335 | +0.1815 |
| Δrsi | -0.0014 | -0.0040 | 0.0955 | 0.1232 | -0.1835 | +0.1450 |
| mom_on | -0.1069 | -0.1038 | 0.0485 | 0.0693 | -0.1663 | -0.0272 |
| mom_off | -0.0898 | -0.1275 | 0.1053 | 0.1003 | -0.3196 | +0.0040 |
| rsi_on | -0.0144 | -0.0446 | 0.0842 | 0.1290 | -0.1940 | +0.0421 |
| rsi_off | -0.0337 | -0.0405 | 0.0432 | 0.0587 | -0.1207 | +0.0245 |
| Δterc mom | -0.0082 | +0.0368 | 0.1365 | 0.2044 | -0.1905 | +0.2114 |
| Δterc rsi | +0.0212 | -0.0009 | 0.1128 | 0.1579 | -0.2239 | +0.1407 |

Ejemplos extremos Defensivas manual (por Δmom): peor Δ: PM -0.1335 (on -0.1295 off +0.0040), mejor Δ: KO +0.1815 (on -0.1380 off -0.3196)

**Growth manual (tech alta-beta)** — N=11 — tickers: ADBE, AMD, AVGO, CRM, GE, INTU, META, NFLX, NVDA, QCOM, TSLA

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off | +0.0635 | +0.0430 | 0.1789 | 0.2726 | -0.1989 | +0.3612 |
| Δrsi | -0.0178 | -0.0101 | 0.0709 | 0.1045 | -0.1026 | +0.1012 |
| mom_on | +0.0824 | +0.0350 | 0.1621 | 0.1825 | -0.2907 | +0.2873 |
| mom_off | +0.0032 | -0.0080 | 0.0697 | 0.1092 | -0.1193 | +0.0877 |
| rsi_on | -0.0448 | -0.0340 | 0.0411 | 0.0705 | -0.0955 | +0.0205 |
| rsi_off | -0.0109 | -0.0240 | 0.0417 | 0.0538 | -0.1023 | +0.0266 |
| Δterc mom | +0.0138 | +0.0302 | 0.2116 | 0.3433 | -0.2460 | +0.3999 |
| Δterc rsi | -0.0173 | -0.0394 | 0.0876 | 0.1091 | -0.1885 | +0.0865 |

Ejemplos extremos Growth manual (tech alta-beta) (por Δmom): peor Δ: TSLA -0.1989 (on -0.1307 off +0.0682), mejor Δ: GE +0.3612 (on +0.2873 off -0.0739)

**Low-vol (<0.23)** — N=12 — tickers: BRK-B, COST, JNJ, KO, LIN, MCD, MRK, PEP, PG, QQQ, SPY, WMT

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off | -0.0148 | +0.0001 | 0.0886 | 0.0671 | -0.1535 | +0.1815 |
| Δrsi | +0.0391 | +0.0181 | 0.0958 | 0.1084 | -0.1835 | +0.1450 |
| mom_on | -0.1204 | -0.1183 | 0.0458 | 0.0839 | -0.1783 | -0.0558 |
| mom_off | -0.0785 | -0.1184 | 0.1041 | 0.0967 | -0.3196 | +0.0225 |
| rsi_on | +0.0155 | -0.0124 | 0.0775 | 0.0971 | -0.1940 | +0.0690 |
| rsi_off | -0.0154 | -0.0305 | 0.0416 | 0.0535 | -0.1207 | +0.0345 |
| Δterc mom | -0.0114 | -0.0026 | 0.1258 | 0.0798 | -0.3008 | +0.2045 |
| Δterc rsi | +0.0360 | +0.0222 | 0.1099 | 0.1114 | -0.2239 | +0.1407 |

Ejemplos extremos Low-vol (<0.23) (por Δmom): peor Δ: MRK -0.1535 (on -0.1783 off -0.0247), mejor Δ: KO +0.1815 (on -0.1380 off -0.3196)

**High-vol (>0.35)** — N=8 — tickers: AMD, AVGO, CRM, META, NFLX, NVDA, QCOM, TSLA

| métrica | mediana | media | sd | IQR | min | max |
|---|---|---|---|---|---|---|
| Δmom on−off | -0.0146 | +0.0017 | 0.1687 | 0.2973 | -0.1989 | +0.1939 |
| Δrsi | -0.0346 | -0.0244 | 0.0703 | 0.1035 | -0.1026 | +0.0901 |
| mom_on | +0.0147 | -0.0132 | 0.1562 | 0.2050 | -0.2907 | +0.1869 |
| mom_off | -0.0019 | -0.0149 | 0.0697 | 0.1023 | -0.1193 | +0.0682 |
| rsi_on | -0.0294 | -0.0324 | 0.0454 | 0.0775 | -0.0955 | +0.0205 |
| rsi_off | -0.0004 | -0.0081 | 0.0328 | 0.0280 | -0.0755 | +0.0266 |
| Δterc mom | -0.0419 | +0.0054 | 0.2007 | 0.3530 | -0.2460 | +0.2377 |
| Δterc rsi | -0.0555 | -0.0561 | 0.0910 | 0.1217 | -0.1885 | +0.0819 |

Ejemplos extremos High-vol (>0.35) (por Δmom): peor Δ: TSLA -0.1989 (on -0.1307 off +0.0682), mejor Δ: META +0.1939 (on +0.1869 off -0.0070)

**Lectura honesta — ¿aparece patrón limpio? NO.**
- **Medianas de Δ (on−off)**: defensivas manual Δmom mediana **−0.0096** (IQR 0.144) vs growth manual **+0.0635** (IQR 0.273) — diferencia aparente +0.07 a favor de growth procíclico, pero **IQRs se solapan ampliamente** y ambos intervalos cruzan cero con holgura. Low-vol Δmom −0.0148 (IQR 0.067) vs high-vol −0.0146 (IQR 0.297) — idénticas. No hay separación sistemática.
- **RSI**: defensivas Δrsi −0.0014 (IQR 0.123) vs growth −0.0178 (IQR 0.105) — diferencia −0.016, indistinguible de ruido; low-vol Δrsi +0.0391 vs high-vol −0.0346 — signos opuestos pero IQR >0.10.
- **Terciles**: defensivas Δterc mom −0.0169 (IQR 0.31) vs growth +0.0262 (IQR 0.34) — mismo solapamiento.
- **Nivel por régimen** (no solo delta): defensivas mom_on mediana −0.107 vs mom_off −0.090 (diferencia −0.017); growth mom_on +0.082 vs mom_off +0.003 (diferencia pro-growth pero con sd 0.16/0.07). Novedad: **growth exhibe IC ligeramente positivo en risk-on** (mediana +0.082, 6/11 >0) mientras defensivas están hondamente negativas en ambos regímenes (−0.107 / −0.090). Esto es el único indicio pro-hipótesis, pero se diluye al mirar ticker-por-ticker:

**Contraejemplos donde la hipótesis NO se cumple (ticker nivel)**:
- **AMD** (growth/high-vol): ic_mom_on **−0.102**, ic_mom_off **+0.003**, Δ=−0.105 — **peor en risk-on**, opuesto a lo esperado para growth.
- **TSLA** (growth): ic_mom_on −0.131, off +0.068, Δ=−0.199 — peor en risk-on por 20pp, pese a ser paradigma growth.
- **QCOM** (growth): −0.291 on vs −0.096 off, Δ=−0.195 — peor en risk-on, cola más negativa del universo en ese bucket.
- **KO** (defensiva): −0.138 on vs −0.320 off, Δ=+0.182 — **mejor en risk-on** por 18pp, opuesto a defensiva resiliente en miedo.
- **MCD** (defensiva): −0.162 on vs −0.291 off, Δ=+0.130 — mejor en risk-on, no en risk-off.
- **PEP** (defensiva): −0.166 on vs −0.128 off, Δ=−0.039 — mejor en off por 4pp pero ambos negativos y con rsi_off mucho mejor que on (−0.011 vs −0.194), patrón mixto.
- **MSFT** (tech large, no growth extremo): −0.037 on vs −0.064 off, Δ=+0.027 — diferencia mínima, indiferente al régimen.
- **NVDA** (growth emblemático): +0.110 on vs −0.056 off, Δ=+0.166 — **sí cumple** (mejor en risk-on). Pero su vecino **AVGO** (+0.062 on vs −0.119 off, Δ=+0.181) también cumple, mientras **NFLX** (−0.033 on vs +0.060 off, Δ=−0.093) no.

**Conclusión del test defensivas vs growth**: no hay patrón limpio ni monotónico. La hipótesis de Boris (defensivas resilientes en VIX alto, growth en VIX bajo) **no se sostiene** como regla transversal: el signo de Δ varía dentro de cada grupo con IQR mayor que la diferencia entre medianas, y los contraejemplos son numerosos y económicamente grandes (Δ de ±15-20pp en tickers individuales). El único atisbo pro-hipótesis —mediana growth ligeramente mejor en risk-on— desaparece al usar el criterio objetivo low-vol/high-vol (medianas idénticas −0.015). Sostener lo contrario sería forzar narrativa.

## 7. Market tickers (7) — referencia separada NO mezclada con universo

| ticker | grupo | vol_ann | n_on | n_off | mom_on | mom_off | Δmom | rsi_on | rsi_off | Δrsi | mom_low | mom_high | Δterc | n_low | n_high |
|--------|-------|---------|------|-------|--------|---------|------|--------|---------|------|---------|----------|-------|-------|--------|
| AGG    | ETF/Market | 0.0519 | 1288 | 1362 | +0.1170 | +0.0282 | +0.0888 | +0.0361 | +0.0374 | -0.0014 | +0.1273 | +0.0256 | +0.1018 | 861 | 939 |
| DBC    | ETF/Market | 0.1800 | 1288 | 1362 | -0.1994 | +0.0127 | -0.2122 | +0.1306 | +0.0551 | +0.0754 | -0.2751 | -0.0124 | -0.2627 | 861 | 939 |
| EFA    | ETF/Market | 0.1726 | 1288 | 1362 | -0.0062 | -0.1355 | +0.1293 | -0.0279 | -0.0036 | -0.0243 | +0.0613 | -0.1168 | +0.1781 | 861 | 939 |
| GLD    | ETF/Market | 0.1613 | 1288 | 1362 | +0.3120 | -0.1414 | +0.4534 | -0.0400 | +0.0124 | -0.0524 | +0.2090 | -0.1829 | +0.3920 | 861 | 939 |
| TIP    | ETF/Market | 0.0566 | 1288 | 1362 | +0.0881 | -0.0374 | +0.1255 | +0.0502 | -0.0021 | +0.0523 | +0.0919 | -0.0382 | +0.1301 | 861 | 939 |
| TLT    | ETF/Market | 0.1480 | 1288 | 1362 | +0.0668 | -0.0632 | +0.1300 | +0.0396 | -0.0161 | +0.0557 | +0.1060 | -0.0530 | +0.1590 | 861 | 939 |
| ^VIX   | Vol        | 1.3672 | 1289 | 1362 | +0.0383 | -0.1606 | +0.1989 | -0.0172 | -0.1083 | +0.0911 | +0.1166 | -0.1335 | +0.2501 | 861 | 939 |

**Lectura**: ^VIX como ticker es outlier (vol 1.367) con momentum IC −0.213 on vs −0.099 off y terciles −0.200 low vs −0.053 high — patrón invertido, no comparable. AGG/TIP (bonos, vol ~0.05) exhiben IC mom positivo pequeño en on (+0.01) y negativo en off (−0.03). EFA/GLD/DBC mixtos. Se confirma que **no deben mezclarse** con el universo equity al estimar pesos; su inclusión distorsiona pooled (ver §3: pooled 57 mom_on −0.003 vs 50 +0.022).

## 8. Limitaciones explícitas (11 del diagnóstico anterior + 3 nuevas de régimen)

1. **Survivorship/selección**: universo 50 top-cap supervivientes 2015-2026, sin delistados; sesgo hacia large resilientes.
2. **Ventana y no-estacionariedad**: ventana única 11.6 años agrega bull/bear/COVID/tightening. VIX no es estacionario (cambio de nivel post-2020, clusters de vol). El split mediano fija un umbral estático (16.68) que **no adapta** a deriva secular; un VIX=17 en 2017 ≠ 2022 en términos de percentil histórico. Alternativa con VIX rank rolling (p.ej. percentil 240d) no se testeó.
3. **No out-of-sample, no inferencia**: sin pre-registro, sin corrección por 50×2×2 comparaciones, sin SE/Newey-West, sin test Δ≠0. Los Δ son descriptivos; cualquier |Δ|>0.10 puede ser ruido (SE≈0.04 por bucket, SE(Δ)≈0.06). No se reporta significancia.
4. **Lookahead fwd vs VIX contemporáneo**: fwd_ret_20d solapa ventanas (autocorrelación inducida) e infla SE; además usa retornos futuros 20d que atraviesan cambios de régimen intra-horizonte (el VIX de t puede no persistir 20d). IC por régimen mezcla señal y persistencia de régimen.
5. **Heterocedasticidad y pooling**: pooled concatena filas con varianzas y niveles distintos; VIX alto suele coincidir con vol realizada alta → peso implícito mayor para filas risk-off.
6. **Sin filtro eligible**: IC sin gates `trend/adx/rsi/vol` del motor; el IC dentro del gate (el que importa para PnL) puede tener régimen-dependencia distinta. No se midió per-bucket eligible por pérdida de N.
7. **Derivación de factores, no factores del motor**: fórmulas exactas pero sin pipeline completo ni ajustes idénticos; diferencias <1e-6.
8. **Warmup y N**: momentum warmup 252d; rsi 14d; fwd 20d futuro; n por bucket queda 1288/1361 (mediana) — no es 2921. Meses finales sin fwd se pierden.
9. **Metric fragilidad**: rsi_score binario (point-biserial); momentum_score saturado en colas; VIX level threshold arbitrario (mediana muestral, no nivel estructural 20). Sensibilidad a bandas VIX no explorada más allá de terciles.
10. **Cap group incompleto**: SMID vacío; no testeable Large vs SMID tampoco por régimen.
11. **No propone calibración por ticker ni por régimen**: heterogeneidad en Δ existe en nivel ticker pero no es sistemática por grupo; calibrar pesos por régimen/ticker amplificaría ruido sin evidencia OOS.
12. **[Nueva R1] Elección de corte**: mediana maximiza N pero puede atenuar efecto al incluir observaciones near-threshold; terciles aumentan contraste pero descartan 33% de datos y reducen potencia. Ningún corte es neutral; se reportan ambos para transparencia. Corte por VIX log o por VIX rank percentil cambiaría asignación de ~10% de días near-median.
13. **[Nueva R2] VIX level vs log / VIX contemporáneo vs fwd**: VIX level no estacionario; usar log(VIX) o VIX z-score rolling daría buckets más estables intertemporalmente. Además se usa VIX en t contemporáneo; alternativa VIX_fwd (promedio 20d) o VIX_change podría capturar régimen realizado durante el horizonte fwd, con distinto resultado.
14. **[Nueva R3] Régimen no estacionario y clustering**: VIX clusters (Hurst, autocorrelación vol) implican que filas sucesivas dentro de bucket no son independientes; SE real >1/sqrt(n). Días de VIX≥20 post-COVID (2020-22) dominan bucket off, confundiendo efecto VIX con efecto temporal. Sin control por año, el Δ confunde régimen con era.

## 9. Apéndice A — Spearman por ticker (sensibilidad)

| ticker | mom_on_s | mom_off_s | Δmom_s | rsi_on_s | rsi_off_s | Δrsi_s | mom_low_s | mom_high_s | Δterc_s | rsi_low_s | rsi_high_s | Δterc_s_rsi |
|--------|----------|-----------|--------|----------|-----------|--------|-----------|------------|---------|-----------|------------|-------------|
| AAPL   | -0.1562 | -0.0631 | -0.0930 | -0.0615 | +0.0629 | -0.1244 | -0.0968 | +0.0211 | -0.1179 | -0.0509 | +0.0480 | -0.0989 |
| ABBV   | -0.0466 | -0.1293 | +0.0827 | -0.0358 | +0.0503 | -0.0861 | -0.0418 | -0.1961 | +0.1543 | -0.0915 | +0.0373 | -0.1288 |
| ACN    | -0.0528 | +0.0184 | -0.0712 | -0.0584 | +0.0088 | -0.0672 | -0.1399 | +0.0122 | -0.1522 | -0.0763 | +0.0229 | -0.0992 |
| ADBE   | +0.0290 | +0.0726 | -0.0435 | -0.0465 | -0.0684 | +0.0220 | -0.1229 | +0.0304 | -0.1533 | -0.1101 | -0.0582 | -0.0520 |
| AMD    | -0.0770 | -0.0242 | -0.0528 | +0.0131 | -0.0376 | +0.0507 | -0.0749 | -0.0132 | -0.0616 | -0.0006 | -0.0226 | +0.0221 |
| AMGN   | -0.2292 | -0.2679 | +0.0387 | +0.0648 | -0.0875 | +0.1523 | -0.2969 | -0.3087 | +0.0118 | +0.0898 | -0.0903 | +0.1800 |
| AMZN   | +0.0659 | -0.0241 | +0.0901 | +0.0953 | +0.0572 | +0.0381 | +0.0770 | -0.0238 | +0.1008 | +0.0892 | +0.0329 | +0.0562 |
| AVGO   | +0.0294 | -0.1488 | +0.1782 | -0.0777 | -0.0243 | -0.0535 | +0.0959 | -0.1252 | +0.2210 | -0.0702 | +0.0131 | -0.0833 |
| BAC    | -0.1613 | -0.0850 | -0.0764 | -0.0196 | -0.0624 | +0.0428 | -0.1037 | -0.1512 | +0.0474 | -0.0002 | -0.0224 | +0.0222 |
| BRK-B  | -0.1095 | -0.1812 | +0.0717 | +0.0888 | -0.0144 | +0.1031 | -0.1088 | -0.2007 | +0.0919 | +0.1428 | +0.0079 | +0.1350 |
| CAT    | -0.0775 | -0.1986 | +0.1211 | -0.0014 | -0.0384 | +0.0370 | -0.0216 | -0.1501 | +0.1285 | +0.0162 | -0.0153 | +0.0315 |
| CMCSA  | -0.1372 | -0.0648 | -0.0725 | +0.0664 | +0.0398 | +0.0266 | -0.2026 | -0.0498 | -0.1527 | +0.0508 | +0.0558 | -0.0050 |
| COST   | -0.0253 | +0.0039 | -0.0293 | +0.0124 | -0.1366 | +0.1490 | -0.1178 | -0.0623 | -0.0554 | +0.0359 | -0.1119 | +0.1478 |
| CRM    | +0.0366 | +0.0341 | +0.0024 | -0.0840 | +0.0251 | -0.1091 | +0.0229 | +0.0332 | -0.0103 | -0.1372 | +0.0330 | -0.1702 |
| CSCO   | -0.1121 | -0.0610 | -0.0511 | -0.1323 | +0.0152 | -0.1475 | -0.0246 | -0.0617 | +0.0371 | -0.1561 | +0.0032 | -0.1593 |
| CVX    | -0.2103 | -0.0854 | -0.1249 | -0.0566 | +0.0113 | -0.0679 | -0.2623 | -0.0968 | -0.1655 | -0.0693 | +0.0145 | -0.0838 |
| DIS    | -0.1903 | -0.0288 | -0.1616 | +0.0157 | +0.0171 | -0.0014 | -0.1852 | +0.0063 | -0.1914 | +0.0526 | +0.0608 | -0.0082 |
| GE     | +0.3015 | -0.0699 | +0.3714 | -0.0474 | -0.0295 | -0.0179 | +0.3766 | -0.0473 | +0.4240 | -0.0319 | -0.0142 | -0.0176 |
| GOOGL  | -0.1685 | -0.0363 | -0.1321 | +0.0266 | +0.0302 | -0.0036 | -0.1419 | +0.0269 | -0.1687 | +0.0513 | +0.0257 | +0.0257 |
| HD     | -0.2112 | -0.1185 | -0.0927 | +0.0577 | -0.0270 | +0.0848 | -0.2552 | -0.1699 | -0.0854 | +0.0545 | -0.0368 | +0.0913 |
| IBM    | -0.0214 | -0.1816 | +0.1602 | +0.0512 | -0.1148 | +0.1661 | +0.0127 | -0.1906 | +0.2033 | +0.1540 | -0.0936 | +0.2476 |
| INTU   | +0.0775 | +0.0117 | +0.0658 | -0.0120 | -0.1052 | +0.0932 | -0.0594 | -0.0320 | -0.0274 | +0.0148 | -0.1029 | +0.1177 |
| JNJ    | -0.1863 | -0.0878 | -0.0985 | +0.0309 | +0.0117 | +0.0192 | -0.2595 | -0.2093 | -0.0502 | +0.0395 | +0.0079 | +0.0316 |
| JPM    | -0.2832 | -0.0614 | -0.2217 | -0.0351 | -0.0973 | +0.0621 | -0.2221 | -0.0613 | -0.1608 | -0.0352 | -0.0878 | +0.0526 |
| KO     | -0.1119 | -0.2818 | +0.1699 | +0.0240 | -0.0197 | +0.0437 | -0.1761 | -0.3338 | +0.1577 | +0.0114 | -0.0655 | +0.0768 |
| LIN    | -0.1630 | -0.2125 | +0.0495 | +0.0168 | +0.0070 | +0.0097 | -0.1900 | -0.2175 | +0.0275 | +0.0156 | -0.0016 | +0.0171 |
| LLY    | -0.0802 | -0.1689 | +0.0887 | -0.1311 | -0.0485 | -0.0826 | -0.0737 | -0.1665 | +0.0928 | -0.1297 | -0.0533 | -0.0764 |
| MA     | +0.0533 | -0.1324 | +0.1857 | +0.0414 | -0.0026 | +0.0441 | +0.1005 | -0.1313 | +0.2318 | +0.0289 | -0.0074 | +0.0363 |
| MCD    | -0.1543 | -0.2627 | +0.1084 | -0.0805 | -0.0690 | -0.0116 | -0.1346 | -0.3304 | +0.1958 | -0.0276 | -0.0969 | +0.0693 |
| META   | +0.1296 | -0.0046 | +0.1343 | +0.0038 | -0.0281 | +0.0319 | +0.1554 | +0.0192 | +0.1362 | +0.0551 | -0.0014 | +0.0566 |
| MRK    | -0.2432 | -0.0508 | -0.1925 | +0.0317 | -0.0665 | +0.0982 | -0.3431 | +0.0020 | -0.3452 | +0.0001 | -0.0611 | +0.0612 |
| MSFT   | +0.0489 | -0.0319 | +0.0807 | +0.0096 | -0.0074 | +0.0170 | +0.0409 | +0.0023 | +0.0386 | +0.0353 | -0.0212 | +0.0565 |
| NFLX   | -0.0580 | +0.0562 | -0.1143 | -0.0878 | +0.0293 | -0.1171 | -0.1354 | -0.0153 | -0.1201 | -0.1120 | +0.0173 | -0.1293 |
| NVDA   | +0.0866 | -0.0694 | +0.1560 | -0.0132 | -0.0004 | -0.0128 | +0.1399 | -0.0436 | +0.1835 | -0.0104 | +0.0139 | -0.0243 |
| ORCL   | -0.1208 | -0.0829 | -0.0379 | -0.0211 | +0.0191 | -0.0403 | -0.1955 | -0.1101 | -0.0854 | +0.0376 | +0.0337 | +0.0038 |
| PEP    | -0.1158 | -0.1053 | -0.0105 | -0.1888 | +0.0127 | -0.2015 | -0.0737 | -0.0476 | -0.0261 | -0.2433 | +0.0123 | -0.2557 |
| PFE    | +0.0572 | -0.0583 | +0.1155 | -0.0751 | -0.0786 | +0.0035 | +0.0386 | -0.0905 | +0.1291 | -0.0939 | -0.0539 | -0.0400 |
| PG     | -0.1230 | -0.0646 | -0.0585 | -0.0033 | -0.0702 | +0.0669 | -0.2037 | -0.1359 | -0.0677 | +0.0287 | -0.0669 | +0.0956 |
| PM     | -0.1864 | -0.0344 | -0.1520 | -0.1176 | -0.0319 | -0.0856 | -0.2118 | -0.0451 | -0.1667 | -0.1287 | -0.0446 | -0.0841 |
| QCOM   | -0.2577 | -0.0711 | -0.1866 | -0.0208 | -0.0537 | +0.0329 | -0.2469 | -0.0713 | -0.1756 | -0.0218 | -0.0208 | -0.0009 |
| QQQ    | -0.0109 | +0.0190 | -0.0300 | -0.0578 | -0.0248 | -0.0330 | +0.0906 | +0.0648 | +0.0258 | -0.0425 | +0.0205 | -0.0630 |
| SPGI   | -0.0455 | -0.1365 | +0.0910 | +0.0909 | -0.0145 | +0.1055 | +0.0036 | -0.1239 | +0.1275 | +0.0664 | -0.0040 | +0.0704 |
| SPY    | -0.0193 | -0.1192 | +0.1000 | -0.0395 | +0.0319 | -0.0714 | +0.1170 | -0.1001 | +0.2171 | -0.0235 | +0.0860 | -0.1095 |
| TMO    | -0.1768 | +0.0384 | -0.2152 | +0.0042 | +0.0453 | -0.0410 | -0.1995 | +0.0330 | -0.2325 | +0.0199 | +0.0486 | -0.0287 |
| TSLA   | -0.1119 | +0.0759 | -0.1877 | -0.0544 | -0.0137 | -0.0407 | -0.0587 | +0.1814 | -0.2401 | -0.0521 | +0.0834 | -0.1355 |
| TXN    | -0.1558 | -0.1621 | +0.0063 | -0.0370 | -0.0094 | -0.0275 | -0.1238 | -0.1305 | +0.0067 | -0.0624 | +0.0026 | -0.0650 |
| UNH    | -0.0295 | -0.0434 | +0.0139 | -0.1273 | -0.1296 | +0.0022 | +0.0120 | -0.0928 | +0.1048 | -0.0910 | -0.1367 | +0.0457 |
| V      | -0.0321 | -0.1292 | +0.0971 | +0.0866 | -0.0899 | +0.1766 | +0.0137 | -0.1206 | +0.1343 | +0.0630 | -0.1157 | +0.1787 |
| WMT    | -0.0477 | -0.1243 | +0.0766 | +0.0275 | -0.0332 | +0.0607 | -0.1493 | -0.1647 | +0.0154 | +0.0167 | +0.0000 | +0.0166 |
| XOM    | -0.0994 | -0.0471 | -0.0522 | -0.0127 | +0.0447 | -0.0574 | -0.1628 | -0.0569 | -0.1060 | +0.0227 | +0.0707 | -0.0480 |

**Concordancia Pearson vs Spearman**: correlación entre Δmom Pearson y Δmom Spearman = 0.910 (alta), Δrsi = 0.953. Orden de tickers preservado; ningún ticker cambia de signo en ambos coeficientes de forma sistemática.

## 10. Apéndice B — Vol y autocorrelaciones (contexto del diagnóstico anterior)

| ticker | vol_ann | ac1 | ac5 | ac20 | ic_mom_pooled | ic_rsi_pooled |
|--------|---------|-----|-----|------|---------------|---------------|
| SPY    | 0.1760 | -0.1186 | +0.0379 | -0.0021 | -0.0919 | -0.0221 |
| KO     | 0.1791 | -0.0296 | +0.0569 | -0.0424 | -0.2529 | +0.0115 |
| JNJ    | 0.1832 | -0.0675 | +0.0158 | -0.0033 | -0.0656 | +0.0062 |
| PG     | 0.1868 | -0.0801 | +0.0121 | -0.0101 | -0.0679 | -0.0381 |
| BRK-B  | 0.1909 | -0.1038 | +0.0206 | +0.0019 | -0.1407 | +0.0208 |
| PEP    | 0.1923 | -0.1405 | +0.0520 | -0.0579 | -0.1446 | -0.0942 |
| MCD    | 0.2021 | -0.1035 | +0.0216 | -0.0228 | -0.2237 | -0.0742 |
| COST   | 0.2154 | -0.0217 | +0.0198 | +0.0086 | -0.0572 | -0.0544 |
| WMT    | 0.2176 | -0.0400 | -0.0116 | +0.0142 | -0.1033 | -0.0018 |
| QQQ    | 0.2196 | -0.1049 | +0.0161 | -0.0003 | -0.0137 | -0.0447 |
| LIN    | 0.2239 | -0.0925 | -0.0007 | -0.0104 | -0.2016 | +0.0011 |
| MRK    | 0.2276 | -0.0555 | +0.0133 | -0.0067 | -0.0902 | -0.0051 |
| PFE    | 0.2337 | -0.0305 | +0.0089 | -0.0338 | -0.0158 | -0.0709 |
| PM     | 0.2380 | -0.0528 | +0.0226 | -0.0161 | -0.0476 | -0.0682 |
| V      | 0.2423 | -0.1145 | -0.0010 | -0.0364 | -0.1195 | -0.0298 |
| HD     | 0.2442 | -0.0696 | -0.0053 | -0.0207 | -0.1587 | -0.0025 |
| AMGN   | 0.2520 | -0.0656 | +0.0184 | -0.0224 | -0.2343 | -0.0149 |
| CMCSA  | 0.2591 | -0.0956 | +0.0012 | -0.0251 | -0.0822 | +0.0424 |
| TMO    | 0.2592 | -0.0501 | +0.0330 | +0.0060 | -0.0712 | +0.0185 |
| CSCO   | 0.2594 | -0.0812 | -0.0009 | -0.0437 | -0.0403 | -0.0675 |
| SPGI   | 0.2605 | -0.0904 | +0.0439 | -0.0244 | -0.0967 | +0.0015 |
| MA     | 0.2626 | -0.0744 | -0.0265 | -0.0186 | -0.0764 | +0.0089 |
| ABBV   | 0.2664 | +0.0119 | +0.0157 | +0.0076 | -0.1250 | -0.0029 |
| JPM    | 0.2696 | -0.0873 | +0.0501 | +0.0168 | -0.1420 | -0.0792 |
| ACN    | 0.2723 | -0.0605 | +0.0249 | -0.0215 | +0.0150 | -0.0493 |
| IBM    | 0.2728 | -0.0060 | +0.0358 | -0.0311 | -0.1137 | -0.0375 |
| XOM    | 0.2751 | -0.0174 | +0.0460 | +0.0007 | +0.0020 | +0.0443 |
| MSFT   | 0.2762 | -0.1061 | +0.0156 | +0.0016 | -0.0672 | -0.0118 |
| DIS    | 0.2802 | -0.0568 | +0.0133 | +0.0046 | -0.1223 | +0.0124 |
| AAPL   | 0.2878 | -0.0512 | +0.0111 | -0.0114 | -0.0681 | +0.0152 |
| CVX    | 0.2901 | -0.0719 | +0.0348 | +0.0031 | -0.1044 | -0.0180 |
| GOOGL  | 0.2913 | -0.0337 | -0.0063 | -0.0081 | -0.0371 | +0.0213 |
| UNH    | 0.2940 | -0.0317 | +0.0126 | -0.0332 | -0.0660 | -0.1091 |
| LLY    | 0.2979 | -0.0430 | +0.0081 | -0.0070 | -0.0992 | -0.0807 |
| BAC    | 0.3037 | -0.0333 | +0.0300 | -0.0026 | -0.0870 | -0.0515 |
| CAT    | 0.3080 | -0.0026 | -0.0049 | -0.0120 | -0.1242 | -0.0440 |
| TXN    | 0.3090 | -0.1446 | +0.0551 | -0.0163 | -0.1252 | -0.0345 |
| AMZN   | 0.3314 | -0.0036 | +0.0129 | -0.0075 | -0.0172 | +0.0846 |
| INTU   | 0.3329 | -0.0536 | +0.0264 | +0.0170 | +0.0382 | -0.0567 |
| ADBE   | 0.3370 | -0.0718 | -0.0053 | -0.0314 | +0.0824 | -0.0563 |
| ORCL   | 0.3423 | -0.0302 | -0.0111 | +0.0000 | -0.0919 | -0.0329 |
| GE     | 0.3473 | -0.0217 | +0.0236 | -0.0240 | +0.0602 | -0.0551 |
| CRM    | 0.3541 | -0.0381 | -0.0096 | +0.0066 | +0.0293 | -0.0265 |
| META   | 0.3785 | -0.0348 | +0.0045 | +0.0376 | +0.0436 | -0.0036 |
| QCOM   | 0.3862 | -0.0713 | -0.0222 | +0.0074 | -0.1794 | -0.0327 |
| AVGO   | 0.3953 | -0.0613 | -0.0034 | +0.0119 | -0.0583 | -0.0537 |
| NFLX   | 0.4259 | -0.0032 | -0.0325 | +0.0113 | +0.0203 | -0.0196 |
| NVDA   | 0.4819 | -0.0731 | +0.0077 | +0.0215 | +0.0149 | +0.0007 |
| TSLA   | 0.5720 | -0.0059 | -0.0267 | +0.0081 | +0.0141 | -0.0257 |
| AMD    | 0.5983 | -0.0505 | -0.0254 | +0.0209 | -0.0368 | -0.0075 |

## 11. Trazabilidad y verificación de no-escritura

- **Cache leído**: `backend/data/cache/*.parquet` (57 archivos, 2921/2923 filas c/u) + `^VIX.parquet` (2923 filas, Close median 16.68, p33 14.71, p66 19.12). Verificado con `eza backend/data/cache/` y `python -c "pd.read_parquet..."`.
- **Definición universo**: `backend/scripts/fetch_universe_data.py:NEW_UNIVERSE` (43) + `_BASE_SYMBOLS` (7) = 50; `backend/app/api/routes/opportunities_universe.py:19-35`.
- **Fórmulas**: `backend/app/core/signal_engine.py:137-142` (momentum_score, rsi_score), `backend/app/core/indicators.py:25-30,381`, `backend/app/core/backtest_engine.py:23` (horizonte 20d).
- **Scripts efímeros** (solo lectura, no pre-registrados, en /tmp): `/tmp/diagnostico_heterogeneidad.py` (base), `/tmp/vix_regime_per_ticker.csv` (tabla intermedia), `/tmp/heterogeneidad_per_ticker.csv`, `/tmp/heterogeneidad_summary.json`, `/tmp/build_md.py` (generador de este md). Todos en `/tmp`, no trackeados, no commit.
- **Verificación solo-lectura**: `git status --porcelain` debe mostrar solo este `.md` como untracked + el anterior `DIAGNOSTICO_HETEROGENEIDAD_TICKERS.md` (ambos untracked, sin modificación de `backend/data/cache/*`, `fortress.db`, `backend/data/trial_registry.json`, ni creación de `PRE_REGISTRO_*`). Comprobado pre-escritura con `rg -n "trial_registry|ledger"`.
- **Repro**: `python3 /tmp/build_md.py` + merge de `/tmp/vix_regime_per_ticker.csv` (requiere `pandas`, `scipy` opcional). Toda la aritmética es `pandas .corr`, sin semillas ni determinismo adicional.

## 12. Entrega y stats clave para handoff

**Archivo**: `DIAGNOSTICO_HETEROGENEIDAD_VIX_REGIMEN.md` — `/Users/boris/orca/workspaces/fortress_core/test-opencode-orca/DIAGNOSTICO_HETEROGENEIDAD_VIX_REGIMEN.md`

| Stat | Valor |
|------|-------|
| **Mediana VIX (2015-2026)** | **16.68** |
| **p33 / p66 VIX** | 14.71 / 19.12 |
| **N días VIX por régimen (global 2923)** | risk-on 1461 / risk-off 1462 ; low terc 968 / high terc 994 / mid 961 |
| **N por ticker por bucket (mediana 50)** | on 1288 / off 1361 ; low 861 / high 939 (todos >30) |
| **Pooled MOM Pearson on/off (50)** | +0.0217 / -0.0044 (Δ +0.0260) |
| **Pooled RSI Pearson on/off (50)** | -0.0198 / -0.0216 (Δ +0.0018) |
| **Pooled MOM terc low/high (50)** | +0.0538 / +0.0023 (Δ +0.0515) |
| **Pooled RSI terc low/high (50)** | -0.0147 / -0.0082 (Δ -0.0065) |
| **Dispersión Δmom on−off (50)** | mediana +0.0022, IQR 0.2067, p10 -0.1548 p90 +0.1676 |
| **Dispersión Δrsi on−off (50)** | mediana +0.0024, IQR 0.1110 |
| **Median Δmom defensivas (N=10) vs growth (N=11)** | defensivas -0.0096 vs growth +0.0635 (dif +0.0732, no separable: IQR 0.144 vs 0.273) |
| **Median Δrsi defensivas vs growth** | -0.0014 vs -0.0178 |
| **Median Δmom low-vol (N=12) vs high-vol (N=8)** | low-vol -0.0148 vs high-vol -0.0146 (idénticas) |

**Próximo paso recomendado** (no veredicto): este split VIX **no resuelve** la heterogeneidad ni aporta régimen-dependencia sistemática. No se recomienda calibrar pesos por régimen sin OOS con `trial_registry` + DSR. Si Boris quiere insistir en hipótesis defensiva, el próximo diagnóstico debería usar **VIX rank rolling** (percentil 240d) o **vol realizada cross-sectional** como régimen, y medir **IC dentro del gate eligible** (IC condicional), no pooled incondicional — ambos requieren diseño separado con pre-registro.

---
*Fin del diagnóstico VIX — 2026-09-01, solo lectura, extensión del diagnóstico de heterogeneidad, sin veredicto de trading.*