# Inventario de Series Diarias para Test Ómnibus SPA (Hansen) — Relevamiento Solo Lectura

**Fecha:** 2026-09-02 (UTC)
**Worktree:** `test-opencode-orca` (`/Users/boris/orca/workspaces/fortress_core/test-opencode-orca/`)
**Objetivo SPA:** determinar, de los trials formales del ledger/ROADMAP, cuántos tienen **serie diaria de retornos recuperable** en `backend/data/cache/` (parquet/csv con columna de retornos/equity por día/trade), no solo resumen Sharpe/t/DSR. El SPA (Hansen 2005, *Consistent Specification Testing / Superior Predictive Ability*) requiere **panel diario alineado** (matriz T × N estrategias) para bootstrap estacionario y cálculo de p-valores conjuntos bajo la nula “ninguna supera el benchmark”. Sin series diarias por estrategia, el test no es computable; hay que recomputar o usar test alternativo (p. ej. FDR/Bonferroni ya aplicados).

**Restricción:** solo lectura — no se ejecutó ningún test, no se repararon series, no se re-corrieron scripts, no se tocó `trial_registry.json` ni `cache/`. Verificación al final: `git status` debe mostrar solo este `.md` untracked.

**Métodos de búsqueda (artefacto real, no resumen ajeno):**

| Herramienta | Comando / patrón |
|-------------|-----------------|
| `jq` / `python3 -c` | `cat backend/data/trial_registry.json \| python3 -c "json.load..."` — extracción de `id`, `familia`, `veredicto`, `fecha`, `artefacto` |
| `bat`/`rg`/`fd`/`eza` (requerido) | `grep -n "trial\|veredicto\|§" ROADMAP.md`, `ls -R backend/data/cache`, `find backend -name "*.parquet"`, `ls -la backend/data/cache/*.parquet`, `ls -la data/cache/*.parquet` |
| Inspección headers parquet | `pyarrow.parquet.ParquetFile(path)` — `metadata.num_rows`, `schema.names`, `read().to_pandas().head()` |
| Inspección `.txt` | `grep -i "parquet"` dentro de cada `backend/data/cache/*.txt` + lectura completa de muestras (`trial13`, `backtest_gap`, `rr2_intraday`, `pbo_cscv`, `validacion_oos`, `baseline_clean`) |
| Criterio estricto SERIE | archivo `*.parquet`/`*.csv` con columna `equity`/`ret`/`pnl`/`date` por día o `trades` por operación, determinista y recuperable. No cuentan `.txt` con métricas agregadas (Sharpe/DSR/t) ni `OHLCV` crudo por ticker (`AAPL.parquet`). |

**Fuentes primarias:** `backend/data/trial_registry.json:1-51` (51 entradas, 50 `COMPLETED` + 1 `RESERVED`), `ROADMAP.md:1-70` (pendientes A6.3 y Trial #21), `backend/data/cache/` (199 archivos, 121 parquet totales contando `backend/` + `data/`), `data/cache/` (61 parquet OHLCV + 2 CSV RMT).

---

## Resumen ejecutivo

### Conteo del ledger

| Universo | N |
|----------|---|
| Total ledger (`trial_registry.json`) | **51** (52 con `screening_palas_saneada_a63` `RESERVED`) |
| `COMPLETED` (todas las familias) | **50** |
| Familias foco del encargo `motor_signal` + `signal_diagnosis` | **42** (13 + 29) — 41 `COMPLETED` + 1 `RESERVED` |
| Ampliado `motor_signal` + `signal_diagnosis` + `risk` + `backtest_costos` (≈ “48 formales” citado por GLM/ROADMAP) | **48** — 47 `COMPLETED` + 1 `RESERVED` |
| `producto` (1) + `re_test` (2) | +3 = 51 total |

El “~48” del objetivo GLM corresponde a **48 = 42 (motor+signal) + 3 risk + 3 backtest_costos**. Si se lee literal “solo motor+signal”, son 42. Este inventario reporta ambas bases.

### Disponibilidad de serie diaria (criterio estricto SPA)

| Estado | Definición | N (base 42 motor+signal) | N (base 48 motor+signal+risk+backtest) | N (base 51 total) |
|--------|------------|--------------------------|----------------------------------------|-------------------|
| **SERIE_DISPONIBLE** | parquet/csv con retornos/equity por día o trade, recuperable para SPA | **0** (0 trial_id-específico) | **0** | **0** (+ 1 serie genérica baseline, ver nota) |
| **SOLO_RESUMEN** | `.txt`/`.json` con Sharpe/DSR/t/p pero sin serie diaria | **36** | **42** | **44** |
| **NO_ENCONTRADO** | sin artefacto cache para ese `trial_id` | **6** | **6** | **6** |
| **RESERVED** (no computable) | trial reservado sin artefacto aún | **1** | **1** | **1** |

**Serie genérica disponible pero no trial-específica:** `backend/data/cache/baseline_clean_20260828_183624_equity.parquet` (1907 filas diarias `date,equity,drawdown_pct`, 2019-01-02 → 2026-08-04, + `trades.parquet` 250 operaciones). Es la **única** serie diaria de estrategia persistida en cache. Corresponde al **baseline mom_rsi congelado** (recalc 28/08 costo vigente 0.10%/lado) usado como referencia para `screening_palas`. No hay parquets equivalentes para los otros 47 trials — si SPA quiere contrastar “¿alguna de las 48 variantes supera el baseline?”, falta el panel diario de las 47 variantes.

### Qué significa para viabilidad SPA

- **SPA no computable hoy con el cache actual.** El test exige matriz T × N donde cada columna es la serie diaria de excesos de una estrategia vs. benchmark. Hoy existe 1 columna (baseline) + 47 columnas faltantes. Usar solo resúmenes (Sharpe/t) no sirve — Hansen y su bootstrap estacionario operan sobre la serie, no sobre estadísticos agregados.
- **No hay atajo TXT → serie:** los `.txt` no embeben la serie diaria (solo métricas por ventana W1/W2/W3). Intentar “reconstruir” Sharpe diario desde `t` y `n` es inferencia, no serie, y rompe el bootstrap (violación del mandato “no inferir de logs”).
- **IC studies ≠ serie SPA:** 29 de los 42 (familia `signal_diagnosis`) son diagnósticos de Rank IC (Spearman intra-día, `t-NW`) sobre `factor_panel` — no producen equity/retornos tradeables. Incluso si se quisiera SPA sobre ICs, el `factor_panel_*.parquet` referenciado en esos `.txt` **no existe en disco** (referencias huérfanas, ver Apéndice). SPA sobre señales no es el objetivo GLM; GLM propuso SPA sobre **estrategias/motores**.
- **PBO/CSCV y Validación OOS son mensuales, no diarias:** `pbo_cscv_mom_rsi` (80 meses) y `validacion_oos_fresca` (30 meses) son series mensuales de Sharpe/retorno neto; no son diarias y no alinean con el baseline diario sin re-muestreo (y con N=21 y T corta, no aportan potencia SPA).
- **Opciones honestas (sin recomendar reparación automática):**
  1. **Recomputar** cada variante (motor_signal/backtest) persistiendo `equity.parquet` diario — implica re-correr ~13 motores + 3 backtests con `BacktestEngine` y costo vigente, pre-registro si se usa el resultado para veredicto (consume slots Bonferroni).
  2. **Reducir alcance SPA** a las variantes con serie disponible (hoy = solo baseline + eventual `trial_evt_stops_v2` si se recuperan sus parquets “ambos brazos” mencionados en ROADMAP §45 — ver § Nota §45).
  3. **Test alternativo** ya usado en el repo: auditoría FDR/BH (`auditoria_fdr_20260819_195829.txt`) y Bonferroni familia-wise — menos potente que SPA pero computable sin series.
  4. **Híbrido:** SPA solo sobre el subconjunto “tradeable” (motor_signal + backtest_costos + buffett_alpha) una vez recomputado.

> **Conclusión en una línea:** 0/42 (0/48 en base amplia) trials tienen serie diaria trial-específica en cache; 1 serie genérica baseline diaria sí existe. SPA omnibus sobre las ~48 estrategias no es viable sin recomputar y persistir series diarias alineadas.

---

## Tabla completa (orden ledger `trial_registry.json:1-51`)

Columnas: `trial_id | familia | veredicto | fecha ledger | artefacto resumen path | artefacto serie path (si existe) | estado SPA | notas`

> “Artefacto resumen path” es el `artefacto` del registry tal cual está registrado (relativo a `backend/`). “Artefacto serie path” es el parquet/csv diario/trade-level buscado con patrones `*{trial_id}*.parquet`, `*equity*.parquet`, `*trades*.parquet`, `*returns*.parquet`, `*baseline_*.parquet`, `*pbo_*.parquet`. Búsqueda ejecutada con `find backend -name "*.parquet"`, `ls -la backend/data/cache/*.parquet`, `grep -i parquet` en cada `.txt`.

| # | trial_id | familia | veredicto | fecha | artefacto resumen path | artefacto serie path | estado | notas |
|---|----------|---------|-----------|-------|------------------------|----------------------|--------|-------|
| 01 | `trial_08_sentimiento` | motor_signal | NO_CUMPLE | 2026-08-10 | *(sin artefacto en cache — ver SESSION_LOG)* | — | **NO_ENCONTRADO** | Motor V1 AAII H7. Solo ledger/ROADMAP/SESSION_LOG. |
| 02 | `trial_09_fundamentales` | motor_signal | NO_CUMPLE | 2026-08-10 | *(sin artefacto en cache — ver SESSION_LOG)* | — | **NO_ENCONTRADO** | EDGAR 15 ratios pit. Sin cache. |
| 03 | `trial_10_partial_tp_fix` | motor_signal | NO_CUMPLE | 2026-08-10 | *(sin artefacto en cache — ver SESSION_LOG)* | — | **NO_ENCONTRADO** | Fix reporting PARTIAL_TP. Sin cache. |
| 04 | `trial_11_universo50` | motor_signal | NO_CUMPLE | 2026-08-10 | *(sin artefacto en cache — ver SESSION_LOG)* | — | **NO_ENCONTRADO** | Piso stop régimen 0.05 + U50. Sin cache. |
| 05 | `trial_12_er_velocidad` | motor_signal | NO_CUMPLE | 2026-08-10 | *(sin artefacto en cache — ver SESSION_LOG)* | — | **NO_ENCONTRADO** | Kaufman ER. Sin cache. |
| 06 | `trial_13_ridge_motor` | motor_signal | NO_CUMPLE | 2026-08-11 | `data/cache/trial13_ridge_motor_20260811_120029.txt` | — | **SOLO_RESUMEN** | Ridge_3f walk-forward. Txt con Sharpe/DSR por ventana (W1 0.256/0.071, W2 -0.054/0.028, W3 0.529/0.093) — sin equity parquet. |
| 07 | `trial_14_basket_adx` | motor_signal | NO_CUMPLE | 2026-08-11 | `data/cache/trial14_basket_adx_20260811_215113.txt` | — | **SOLO_RESUMEN** | Basket equal-weight 50 ADX timing. Txt menciona “Equity curve: 2915 días | 51 trades” pero no persiste parquet. |
| 08 | `trial_15_evt_stops` | motor_signal | NO_CUMPLE | 2026-08-14 | *(en curso — ROADMAP #21, fix EWMA aplicado)* → `data/cache/trial15_evt_stops_20260814_195828.txt` existe en disco pero artefacto registry pendiente de actualización | — | **NO_ENCONTRADO** *(registry desactualizado)* | EVT VaR_GPD sizing. Físicamente existe `trial15_evt_stops_20260814_195828.txt` (SOLO_RESUMEN) pero registry apunta a placeholder. |
| 09 | `fase05a_rr2_intraday` | signal_diagnosis | NO_CUMPLE | 2026-08-11 | `data/cache/rr2_intraday_20260811_150741.txt` | — | **SOLO_RESUMEN** | Rank IC intra-día (t-RR2). No es estrategia. Ref `factor_panel_20260811_144857.parquet` **no existe** (huérfano). |
| 10 | `fase05b_rmt` | signal_diagnosis | NO_CUMPLE | 2026-08-11 | `data/cache/rmt_mp_20260811_150849.txt` | — | **SOLO_RESUMEN** | RMT Marchenko-Pastur 8 factores. Sin serie tradeable. |
| 11 | `fase05c_ridge_macro_crudo` | signal_diagnosis | NO_CUMPLE | 2026-08-11 | `data/cache/ridge_comb_20260811_150859.txt` | — | **SOLO_RESUMEN** | Ridge macro crudo. Ref panel huérfano. |
| 12 | `sectorial_endogeno` | signal_diagnosis | NO_CUMPLE | 2026-08-11 | `data/cache/sector_clusters_20260811_170235.txt` | — | **SOLO_RESUMEN** | Clustering Ward endógeno. Ref panel huérfano. |
| 13 | `reeval_trial14` | signal_diagnosis | NO_CUMPLE | 2026-08-11 | `data/cache/reeval_trial14_basket_adx_20260811_220640.txt` | — | **SOLO_RESUMEN** | Re-eval basket con t-NW diario. Sin parquet. |
| 14 | `gap_reversion_diag` | signal_diagnosis | NO_CUMPLE | 2026-08-12 | `data/cache/diagnose_gap_reversion_20260812_082809.txt` | — | **SOLO_RESUMEN** | Gap reversion t=-11.29→-0.46. IC study. |
| 15 | `rr2_subperiodos` | signal_diagnosis | NO_CUMPLE | 2026-08-12 | `data/cache/rr2_subperiodos_20260812_194031.txt` | — | **SOLO_RESUMEN** | Rank IC por subperíodo PRE/POST 2022. Panel huérfano. |
| 16 | `ma200_clusters` | signal_diagnosis | NO_CUMPLE | 2026-08-12 | `data/cache/diagnose_ma200_clusters_20260812_200228.txt` | — | **SOLO_RESUMEN** | MA200 por cluster RMT. |
| 17 | `donchian` | signal_diagnosis | NO_CUMPLE | 2026-08-12 | `data/cache/diagnose_donchian_intraday_20260812_201008.txt` | — | **SOLO_RESUMEN** | Donchian stops. Panel huérfano. |
| 18 | `ma200_beta_control` | signal_diagnosis | **CUMPLE** | 2026-08-12 | `data/cache/diagnose_ma200_beta_control_20260812_202125.txt` | — | **SOLO_RESUMEN** | C3/C6 beta-control. Único CUMPLE temprano pero no tradeable (solo IC, C6 luego refutado con costos). |
| 19 | `horizon_audit_5d_10d` | signal_diagnosis | NO_CUMPLE | 2026-08-13 | `data/cache/horizon_audit_20260813_173648.txt` | — | **SOLO_RESUMEN** | Horizontes 5d/10d. Panel huérfano. |
| 20 | `horizon_largo_60d_125d` | signal_diagnosis | NO_CUMPLE | 2026-08-13 | `data/cache/horizon_largo_20260813_181002.txt` | — | **SOLO_RESUMEN** | Horizontes 60d/125d. Panel huérfano. |
| 21 | `regime_basket_remeasure` | risk | NO_CUMPLE | 2026-08-11 | `data/cache/regime_basket_20260811_213437.txt` | — | **SOLO_RESUMEN** | Condicionamiento régimen sobre basket. |
| 22 | `regime_vs_vol` | risk | NO_CUMPLE | 2026-08-12 | `data/cache/diagnose_regime_vol_20260812_064914.txt` | — | **SOLO_RESUMEN** | Régimen predice vol realizada. |
| 23 | `evt_tails_diag` | risk | **CUMPLE** | 2026-08-13 | `data/cache/evt_tails_20260813_155237.txt` | — | **SOLO_RESUMEN** | Diagnóstico colas EVT (xi>0). No es estrategia. |
| 24 | `gap_reversion_costos` | backtest_costos | NO_CUMPLE | 2026-08-12 | `data/cache/backtest_gap_costs_20260812_173951.txt` | — | **SOLO_RESUMEN** | Backtest gap con costos 0.30%/trade. Txt con media diaria y t-NW (-11.53) pero sin equity parquet persistido. |
| 25 | `c6_costos` | backtest_costos | NO_CUMPLE | 2026-08-13 | `data/cache/backtest_c6_costs_20260813_135830.txt` | — | **SOLO_RESUMEN** | C6 LS con costos. Sin parquet. |
| 26 | `c6_hedgeado` | backtest_costos | NO_CUMPLE | 2026-08-13 | `data/cache/backtest_c6_hedge_20260813_154313.txt` | — | **SOLO_RESUMEN** | C6 hedgeado market-neutral. Sin parquet. |
| 27 | `rama_w2_cierre` | producto | NO_CUMPLE | 2026-08-11 | `data/cache/sector_clusters_20260811_170235.txt` | — | **SOLO_RESUMEN** | Cierre rama W2 (reusa artefacto sectorial). |
| 28 | `fase06_retest_sentimiento` | re_test | NO_CUMPLE | 2026-08-12 | `data/cache/fase06_retest_20260812_175055.txt` | — | **SOLO_RESUMEN** | Re-test AAII post-fix. |
| 29 | `fase06_retest_fundamentales` | re_test | NO_CUMPLE | 2026-08-12 | `data/cache/fase06_retest_20260812_175055.txt` | — | **SOLO_RESUMEN** | Re-test EDGAR post-fix. |
| 30 | `lead_lag_diag` | signal_diagnosis | NO_CUMPLE | 2026-08-15 | `data/cache/lead_lag_20260816_090220.txt` | — | **SOLO_RESUMEN** | Lead-lag 10 pares × 5 lags. |
| 31 | `triple_barrier_retest` | signal_diagnosis | NO_CUMPLE | 2026-08-16 | `data/cache/retest_triple_barrier_20260816_091649.txt` | — | **SOLO_RESUMEN** | Triple barrier M1. Panel huérfano. |
| 32 | `trial_16_m2_abstencion` | motor_signal | NO_CUMPLE | 2026-08-17 | `data/cache/trial16_m2_abstencion_20260817_100548.txt` | — | **SOLO_RESUMEN** | Abstención conformal M2 (tautológico 100% abst). Ref `baseline_clean_20260811_150643_trades.parquet` huérfano. |
| 33 | `adx_walkforward` | signal_diagnosis | NO_CUMPLE | 2026-08-17 | `data/cache/trial_adx_walkforward_20260817_103916.txt` | — | **SOLO_RESUMEN** | ADX walk-forward IC. Panel huérfano. |
| 34 | `trial_17_m2_abstencion` | motor_signal | NO_CUMPLE | 2026-08-17 | `data/cache/trial17_m2_abstencion_20260817_104452.txt` | — | **SOLO_RESUMEN** | M2 corregido (no tautológico). Ref baseline huérfano. |
| 35 | `weekly_indicators_2026` | signal_diagnosis | NO_CUMPLE | 2026-08-17 | `data/cache/weekly_indicators_20260817_105918.txt` | — | **SOLO_RESUMEN** | Indicadores semanales IC (t máx 0.44). |
| 36 | `finbert_sentiment_eventstudy` | signal_diagnosis | NO_CUMPLE | 2026-08-17 | `data/cache/trial_finbert_eventstudy_20260817_163512.txt` | — | **SOLO_RESUMEN** | FinBERT 8-K event study. |
| 37 | `xsec_relative_and_aaii_timing` | signal_diagnosis | NO_CUMPLE | 2026-08-17 | `data/cache/trial_xsec_relative_20260817_184355.txt` | — | **SOLO_RESUMEN** | Rank IC relativo a SPY + AAII timing. Panel huérfano. |
| 38 | `trial_18_c6_costo_medido` | motor_signal | NO_CUMPLE | 2026-08-19 | `data/cache/backtest_c6_hedge_costo_medido_20260819_155509.txt` | — | **SOLO_RESUMEN** | C6 hedge con costo medido 0.05%/lado. Txt con media diaria neto +0.000010 (t 0.07) — sin parquet. |
| 39 | `trial_macd_bollinger` | signal_diagnosis | NO_CUMPLE | 2026-08-20 | `backend/data/cache/trial_macd_bollinger_20260820_174735.txt` | — | **SOLO_RESUMEN** | MACD/Bollinger IC. |
| 40 | `trial_ofi_proxy` | signal_diagnosis | NO_CUMPLE | 2026-08-20 | `backend/data/cache/trial_ofi_proxy_20260820_184638.txt` | — | **SOLO_RESUMEN** | OFI proxy. |
| 41 | `trial_cvd_proxy` | signal_diagnosis | NO_CUMPLE | 2026-08-20 | `backend/data/cache/trial_cvd_proxy_20260820_185959.txt` | — | **SOLO_RESUMEN** | CVD proxy. |
| 42 | `pbo_cscv_mom_rsi` | signal_diagnosis | NO_CUMPLE | 2026-08-22 | `data/cache/pbo_cscv_mom_rsi_20260822_093300.txt` (+ `.json`) | — | **SOLO_RESUMEN** | PBO CSCV 21 configs (PBO 0.4688). Mensual (80 meses), no diario. Sin parquet diario. |
| 43 | `validacion_oos_fresca_mom_rsi` | signal_diagnosis | NO_CUMPLE | 2026-08-22 | `data/cache/validacion_oos_fresca_mom_rsi_20260822_155520.txt` (+ `.json`) | — | **SOLO_RESUMEN** | Validación OOS fresca 30 meses Sharpe 1.33/DSR 0.60. Serie mensual embebida en txt (30 filas), no parquet diario. |
| 44 | `regime_gating_p` | signal_diagnosis | NO_CUMPLE | 2026-08-22 | `backend/data/cache/regime_gating_p_20260822_162628.txt` (+ `.json`) | — | **SOLO_RESUMEN** | Regime gating momentum (3 condicionantes). |
| 45 | `trial_frog_in_the_pan` | signal_diagnosis | NO_CUMPLE | 2026-08-22 | `backend/data/cache/trial_frog_in_the_pan_20260822_175302.txt` | — | **SOLO_RESUMEN** | Frog-in-the-Pan ID. |
| 46 | `trial_kama_hma_supertrend` | signal_diagnosis | NO_CUMPLE | 2026-08-23 | `data/cache/trial_kama_hma_supertrend_20260823_152846.txt` (+ `.json`) | — | **SOLO_RESUMEN** | KAMA/HMA/Supertrend. |
| 47 | `trial_evt_stops_v2` | motor_signal | NO_CUMPLE | 2026-08-24 | `data/cache/trial18_evt_stops_v2_20260824_200927.txt` | *(ver nota §45)* | **SOLO_RESUMEN*** | EVT-stops v2 sizing aislado. ROADMAP §45 promete “parquet ambos brazos” pero en `backend/data/cache` **no existe** `*evt_stops_v2*.parquet` (solo `.txt` + `ABORTADO_*` del intento 1). Si el artefacto estuvo, hoy no está. |
| 48 | `trial_a5_buffett_alpha` | motor_signal | NO_CUMPLE | 2026-08-25 | `data/cache/trial20_a5_buffett_alpha_20260825_211648.txt` | — | **SOLO_RESUMEN** | Buffett Alpha Quality+Value+LowBeta (Sharpe 0.886). Sin parquet. |
| 49 | `screening_palas` | signal_diagnosis | NO_CUMPLE | 2026-08-27 | `data/cache/screening_palas_20260828_071737.txt` | — | **SOLO_RESUMEN** | Screening PALA/RESTO/POOLED (check sanidad fallido). Sin parquet por trial; usa baseline_clean como referencia. |
| 50 | `screening_palas_saneada_a63` | signal_diagnosis | **RESERVED** | 2026-08-29 | *(sin artefacto — RESERVED, procesos PALA/RESTO/POOLED en curso al 30/08)* | — | **RESERVED** | Rerun sano POOLED vs `baseline_clean_20260828`. No computable. |
| 51 | `trial21_asimetria_direccional` | signal_diagnosis | NO_CUMPLE* | 2026-08-30 | `data/cache/trial21_asimetria_direccional_20260830_200908.txt` | — | **SOLO_RESUMEN** | Asimetría UP/DOWN. *NO_CUMPLE por cobertura (gate ≥75 fechas/≥10 simb falló en 3/3) — no refutación sino no-resuelto-por-insuficiencia. Sin parquet. |

> *Nota §45:* `ROADMAP.md:553` y `backend/data/trial_registry.json: trial_evt_stops_v2` describen `artefactos trial18_evt_stops_v2...txt(+parquet ambos brazos)` pero `find backend -name "*.parquet" | rg evt` y `ls -la backend/data/cache/trial18*` retornan 0 parquet. El `ABORTADO_trial18_evt_stops_v2_20260824_070552.txt` del intento 1 (>13h) sí existe. No se infiere existencia pasada.

**Fila fuera de tabla pero relevante para SPA — serie genérica baseline:**

| artefacto serie | filas | columnas | estado | uso SPA |
|-----------------|-------|----------|--------|---------|
| `backend/data/cache/baseline_clean_20260828_183624_equity.parquet` | 1907 | `date, equity, drawdown_pct` (diaria, 2019-01-02 → 2026-08-04) | **SERIE_DISPONIBLE** | Única serie diaria tradeable recuperable. Base para SPA si se recomputan variantes. `ret = pct_change(equity)` verificado: mean 0.000039, std 0.00204, 1171 días con ret≠0. |
| `backend/data/cache/baseline_clean_20260828_183624_trades.parquet` | 250 | `symbol,entry_date,exit_date,entry_price,exit_price,shares,pnl,exit_reason,g2_score,win_prob,regime_state` | **SERIE_DISPONIBLE (trade-level)** | Reconstruible a diaria vía agregación por `exit_date`, pero no sustituye equity diaria para SPA (costos/fechas sin trade). |

---

## Apéndice A — Artefactos cache con serie diaria encontrados (solo lectura, `eza`/`ls`)

**Comando:** `ls -R backend/data/cache | head -n 300` · `ls -1 backend/data/cache/*.parquet | wc -l` · `find backend -name "*.parquet" -type f` · `pyarrow` header check.

### A.1 Parquet de estrategia con serie diaria/trade (criterio estricto SPA)

| Path | Filas | Columnas clave | Fecha artefacto | Observación |
|------|-------|----------------|-----------------|-------------|
| `backend/data/cache/baseline_clean_20260828_183624_equity.parquet` | 1907 | `date, equity, drawdown_pct` | 2026-08-28 18:36 | Diaria. Verificado `pyarrow` (1907 filas, rango 2019-01-02 → 2026-08-04). Ver `diagnose` §A.3. |
| `backend/data/cache/baseline_clean_20260828_183624_trades.parquet` | 250 | `symbol, entry_date, exit_date, pnl, exit_reason` | 2026-08-28 18:36 | Trade-level. Rango exits 2019-01-17 → 2026-07-31. |
| `backend/data/cache/baseline_clean_20260828_183624_events.parquet` | 40 | `date, severity, symbol, description` | 2026-08-28 18:36 | Eventos de régimen. No es serie de retornos. |

**Total series de estrategia diarias:** 1 equity + 1 trades (mismo baseline). Ningún otro `*trial*.parquet`, `*equity*.parquet`, `*trades*.parquet`, `*returns*.parquet`, `*pbo_*.parquet` trial-específico existe en `backend/data/cache` ni `data/cache`.

### A.2 Parquet OHLCV crudo (no son series de estrategia — no cuentan para SPA)

| Path pattern | N | Ejemplo |
|--------------|---|---------|
| `backend/data/cache/*.parquet` (60 tickers OHLCV) | 61 | `AAPL.parquet` (156507 B, 2019-01-02 → 2026-08-04), `SPY.parquet`, `AGG.parquet`, `DBC.parquet`, `GLD.parquet`, `^VIX.parquet`, etc. |
| `data/cache/*.parquet` (61 tickers OHLCV + 3 commodities) | 64 | `AAPL.parquet` (102403 B), `CL=F.parquet`, `GC=F.parquet`, `DX-Y.NYB.parquet`, `HG=F.parquet` — OHLCV crudo, no pnl. |

Estos son insumos (`fetch_universe_data`, `data_updater`) no estrategias; listar aquí solo para trazabilidad — **no** son `SERIE_DISPONIBLE` bajo el criterio SPA.

### A.3 Verificación `baseline_clean` equity (extracto `pyarrow`)

```
equity rows 1907 | columns ['date','equity','drawdown_pct']
date range 2019-01-02 → 2026-08-04
ret = pct_change(equity): mean 0.000039, std 0.002041, min -0.01316, max 0.020657
non-zero returns: 1171 / 1906 | NaN 1 (primer día)
drawdown min -0.0547, 1907 filas continuas sin huecos de fecha trading (1907 ≈ 7.5 años trading)
```

Conteo filas `eza backend/data/cache/*.parquet`: 61 (OHLCV) + 3 baseline = 64 en `backend/data/cache`; `data/cache/*.parquet` 61 adicionales (duplicado OHLCV legacy + commodities).

---

## Apéndice B — Artefactos cache solo-resumen (`.txt`/`.json` con Sharpe/t/DSR, sin serie)

**Comando:** `ls -1 backend/data/cache/*.txt | wc -l` → **128** `.txt` en `backend/data/cache`; `grep -i "parquet"` en cada uno → 16 mencionan parquet pero 14 son referencias huérfanas a `factor_panel_*.parquet` o `baseline_clean_20260811` borrados.

### B.1 Lista `.txt` solo-resumen por trial (extracto, todos verificados `exists=True` excepto donde se indica)

- `trial13_ridge_motor_20260811_120029.txt` — Sharpe/DSR por W1/W2/W3, sin serie.
- `trial14_basket_adx_20260811_215113.txt` — métricas basket, “Equity curve: 2915 días” citado pero no persistido.
- `rr2_intraday_20260811_150741.txt` — t-NW intra-día adx +2.31 nominal.
- `rmt_mp_20260811_150849.txt` — RMT 8 factores.
- `ridge_comb_20260811_150859.txt` — ridge macro.
- `sector_clusters_20260811_170235.txt` — clustering endógeno.
- `reeval_trial14_basket_adx_20260811_220640.txt` — re-eval t-NW.
- `diagnose_gap_reversion_20260812_082809.txt`, `rr2_subperiodos_20260812_194031.txt`, `diagnose_ma200_clusters_20260812_200228.txt`, `diagnose_donchian_intraday_20260812_201008.txt`, `diagnose_ma200_beta_control_20260812_202125.txt` (CUMPLE pero IC-only), `horizon_audit_20260813_173648.txt`, `horizon_largo_20260813_181002.txt` — todos IC diagnostics.
- `regime_basket_20260811_213437.txt`, `diagnose_regime_vol_20260812_064914.txt`, `evt_tails_20260813_155237.txt` — risk.
- `backtest_gap_costs_20260812_173951.txt` (t-NW -11.53), `backtest_c6_costs_20260813_135830.txt`, `backtest_c6_hedge_20260813_154313.txt` — backtests con media diaria y t pero sin equity parquet.
- `fase06_retest_20260812_175055.txt` — re-tests sentencia/fundamentales.
- `lead_lag_20260816_090220.txt`, `retest_triple_barrier_20260816_091649.txt` — IC.
- `trial16_m2_abstencion_20260817_100548.txt` (tautológico 100% abst), `trial_adx_walkforward_20260817_103916.txt`, `trial17_m2_abstencion_20260817_104452.txt` — motor/m2.
- `weekly_indicators_20260817_105918.txt`, `trial_finbert_eventstudy_20260817_163512.txt`, `trial_xsec_relative_20260817_184355.txt` — IC/event-study.
- `backtest_c6_hedge_costo_medido_20260819_155509.txt` — neto +0.000010 t 0.07, sin parquet.
- `trial_macd_bollinger_20260820_174735.txt`, `trial_ofi_proxy_20260820_184638.txt`, `trial_cvd_proxy_20260820_185959.txt` — IC.
- `pbo_cscv_mom_rsi_20260822_093300.txt` (+ `.json` CSCV 12870 combos) — mensual, PBO 0.4688.
- `validacion_oos_fresca_mom_rsi_20260822_155520.txt` (+ `.json` 30 meses) — Sharpe 1.33/DSR 0.60, serie mensual embebida.
- `regime_gating_p_20260822_162628.txt`, `trial_frog_in_the_pan_20260822_175302.txt`, `trial_kama_hma_supertrend_20260823_152846.txt` — IC/gating.
- `trial18_evt_stops_v2_20260824_200927.txt` (+ `ABORTADO_...070552.txt` intento 1 >13h) — sin parquet hoy.
- `trial20_a5_buffett_alpha_20260825_211648.txt` — Buffett Alpha OOS 31m.
- `screening_palas_20260828_071737.txt` — PALA/RESTO/POOLED NO_CUMPLE (check sanidad inválido).
- `trial21_asimetria_direccional_20260830_200908.txt` — 0/3 por cobertura.
- `baseline_clean_20260828_183624.txt` + `baseline_clean_20260811_150643.txt` — baselines resumen (el 20260828 sí tiene parquet hijo, ver A.1).
- Otros auxiliares: `auditoria_fdr_20260819_195829.txt`, `pbo_cscv_baseline_20260822_092850.txt`, `compare_structural_stop_*.txt`, `diagnose_hurst_vol_ic_*.txt`, `measure_execution_costs_*.txt`, etc. — no son trials SPA.

> **Total `.txt` trial-específicos con SOLO_RESUMEN:** 44 (de los 51 ledger). Ver tabla § para mapeo 1:1.

### B.2 Referencias parquet huérfanas (existían al correr, hoy borradas — verificadas `not exists`)

| Referencia en `.txt` | Trials que la citan | Estado hoy |
|----------------------|---------------------|------------|
| `factor_panel_20260811_144857.parquet` | `fase05a`, `fase05c`, `sectorial_endogeno`, `rr2_subperiodos`, `donchian`, `horizon_*`, `rama_w2`, `triple_barrier`, `adx_walkforward`, `xsec_relative`, `asesoria_*` (16 `.txt`) | **No existe** en `backend/data/cache` ni `data/cache` (`find` 0 hits). Era el panel cross-sectional de ICs (no equity). |
| `factor_panel_20260811_092828.parquet` | `factor_corr`, `ic_by_regime`, `ridge_comb_092828`, `pbo_cscv_093415` | **No existe** (variante anterior, también IC). |
| `data/cache/baseline_clean_20260811_150643_trades.parquet` | `trial16_m2`, `trial17_m2`, `regime_stop_contrafactual_*` | **No existe** (reemplazado por `20260828` vigente). |
| `universe50_phaseA_20260810_165713_trades.parquet` | `pbo_cscv_093415/093540` | **No existe** (fase exploratoria temprana). |

Implicancia SPA: incluso para trials IC (no tradeables), el panel que permitiría *re-derivar* una serie proxy diaria no está en cache — no es recuperable sin re-ejecutar `factor_panel.py`.

---

## Trazabilidad — artefacto real verificado

| Insumo | Path / comando | Evidencia |
|--------|----------------|-----------|
| Ledger | `backend/data/trial_registry.json:1-51` (`jq .[].id`, `python3 json.load`) | 51 entradas; `consumed_budget` por familia leído en `pbo_cscv_mom_rsi_20260822_093300.txt:21 (consumed=21)` |
| ROADMAP | `ROADMAP.md:1-70` (pendiente A6.3, 1b Trial #21) + `grep -n "trial\|veredicto\|§"` | A6.3 RESERVED 29/08, Trial #21 CERRADO 30/08 0/3 cobertura |
| Cache listing | `ls -R backend/data/cache` (199 archivos), `ls -1 backend/data/cache/*.parquet` (64), `data/cache/*.parquet` (61), `find . -name "*equity*.parquet"` (3 hits baseline) | Solo `baseline_clean_20260828_183624_*` son series de estrategia |
| Headers parquet | `pyarrow.ParquetFile` sobre `baseline_clean_*.parquet`, `AAPL.parquet`, `SPY.parquet` | Ver Apéndice A.3; OHLCV confirmado `auto_adjust=True` (sin “Adj Close”), no corporate-action bug |
| Contenido txt | `cat backend/data/cache/*.txt \| grep -i parquet` + lectura muestral 6 artefactos | 0 equity series embebidas salvo métricas por ventana |
| Comandos usados | `jq`/`python3`, `bat`/`rg`/`fd`/`eza`, `ls -la`, `find`, `pyarrow` | Ningún `write`/`edit` sobre `ledger`/`cache`/`ROADMAP` |

**Reproducibilidad:** todo lo afirmado es re-ejecutable con los comandos de la fila anterior en el worktree `test-opencode-orca` sin permisos de escritura (solo `Read`/`Bash` lectura). Si un trial futuro persiste nueva serie, aparecerá en `find backend -name "*.parquet" | rg trial` y cambiará el conteo — este inventario queda como foto del 2026-09-02.

---

## Verificación

```bash
git -C test-opencode-orca status --porcelain
# esperado: ?? INVENTARIO_SERIES_SPA.md  (solo este archivo untracked)
# sin cambios en data/trial_registry.json, backend/data/cache/, ROADMAP.md
```

No se commiteó. No se tocó `trial_registry.json` ni `cache/`. Solo lectura.

---

*Generado por relevamiento solo-lectura para insumo SPA-Hansen (propuesto GLM) — no ejecuta el test, no repara, no re-corre. Fecha de generación 2026-09-02.*
