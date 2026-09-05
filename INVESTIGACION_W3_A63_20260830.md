# Investigación W3 — Causa real de divergencia del check de sanidad A6.3

**Worktree:** `test-opencode-orca` (`/Users/boris/orca/workspaces/fortress_core/test-opencode-orca`)  
**Fecha:** 2026-08-30  
**Autor:** verificador independiente (no escribió `screening_palas.py` auditado)  
**Mandato:** investigar **solo W3 (2024-01-01 -> 2026-08-04)** — las otras dos ventanas ya convergen tras igualar N_TRIALS.  
**Restricciones:** SIN re-correr ningún backtest, SIN tocar `PRE_REGISTRO_SCREENING_PALAS.md` ni `PRE_REGISTRO_SANEAMIENTO_CHECK_A63.md` (sellados). Solo lectura de artefactos y código fuente. Evidencia cruda, no inferencia.

---

## 0. Contexto que se da por probado (rondas previas)

| Ventana | POOLED screening (N=5) S/D | Baseline nuevo (N=17) S/D | dS | dD | dD corregido a N=17 |
|---------|----------------------------|---------------------------|----|----|---------------------|
| W1 | 0.4967 / 0.3138 | 0.5586 / 0.1508 | 0.062 OK | 0.163 FUERA | 0.020 OK |
| W2 | 0.2888 / 0.2164 | 0.3478 / 0.0900 | 0.059 OK | 0.126 FUERA | 0.012 OK |
| W3 | 0.7074 / 0.4886 | 0.3085 / 0.0932 | 0.399 FUERA | 0.395 FUERA | 0.160 FUERA |

- Costo 0.15%->0.10% explica Sharpe W1/W2. Confirmado.
- N_TRIALS 5 vs 17 explica DSR W1/W2 al homogeneizar. Confirmado (`NormalDist` vs `scipy` diff <=1e-16).
- **W3 diverge en ambas métricas incluso homogeneizado.** Rango de fechas descartado (delta trades 10 días = 0, ver §3.3).
- Queda W3 como **no resuelto**, pendiente de esta investigación.

---

## 1. Línea (1): Warmup del regime_classifier (HMM)

### 1.1 Código fuente — dónde y cómo se fitea el HMM

`backend/app/core/backtest_engine.py:308-309` (único fit inicial, previo al loop):
```python
train_market = {s: df[df.index < start_date] for s, df in market_data.items()}
self.regime_classifier.fit(train_market)
```

`backend/app/core/regime_classifier.py:78-84` (fit):
```python
def fit(self, price_data: Dict[str, pd.DataFrame]) -> None:
    feats = self._extract_features(price_data)  # growth_SPY/EFA/QQQ 60d, infl GLD/DBC/TIP 60d, rates TLT/AGG 60d, VIX
    if len(feats) < 252:
        raise ValueError(f"Datos insuficientes: {len(feats)} días")
    scaled = self.scaler.fit_transform(feats.values)
    self.model.fit(scaled)  # GaussianHMM 4 estados, random_state=42, n_iter=200
```

Features: `_extract_features` concatena `pct_change(60)` de SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG + `vix_level` diario, `ffill().dropna()`. Requiere >=252 días.

### 1.2 Evidencia cruda — qué `start_date` ve cada corrida

**Baseline continuo** (`backend/scripts/backtest_baseline_clean.py:28-29,72-73`):
```python
START = "2019-01-01"
res_base = BacktestEngine(...).run(price_data, market_data, pd.Timestamp(START), pd.Timestamp(END))
# train_market = market_data < 2019-01-01  -> ventana 2015-01-02 -> 2018-12-31 (~4 años, ~1008 días hábiles)
```

**Screening W3 independiente** (`test-kilo-orca/backend/scripts/screening_palas.py:28-31,88-89,104`):
```python
WINDOWS = [("W3", "2024-01-01", "2026-08-04")]
full_price = load_universe(SYMBOLS, "2016-01-01", "2026-08-14")  # cache real 2015-01-02->...
market_data = load_universe(MACRO, "2016-01-01", "2026-08-14")
# run_subset(... "2024-01-01", "2026-08-04")
# train_market = market_data < 2024-01-01  -> ventana 2015-01-02 -> 2023-12-31 (~9 años, ~2260 días)
```

Verificación empírica `load_universe` devuelve cache completo independientemente del `start` pedido:
```
MARKET 2016 SPY rows 2921 idx min 2015-01-02 -> max 2026-08-14
PRICE  2016 SPY rows 2921 idx min 2015-01-02 -> max 2026-08-14
PRICE  2019 SPY rows 2921 idx min 2015-01-02 -> max 2026-08-14   # idéntico
```
(`backend/app/core/data_ingestion.py:145-153` muestra que `load_universe` no filtra por `start/end`, solo usa cache para backfill/refresh.)

**Diferencia de warmup HMM:**
- Baseline: ~1008 días (2015-2018) — pre-COVID, pre-ciclo de suba de tasas.
- Screening W3: ~2260 días (2015-2023) — incluye COVID crash/récup, bear 2022, bull 2023.
- El HMM es no-determinístico salvo `random_state=42`, pero su **fit es sensible a la historia vista** (scaler + EM sobre features). Un shift de 5 años de ventana cambia centroides y la alineación de estados `_align_states`.

### 1.3 Walk-forward refit trimestral (no es "fit y olvidar")

`backend/app/core/backtest_engine.py:25,471-477`:
```python
REGIME_REFIT_STRIDE_DAYS = 63  # ~trimestral
if (date - last_regime_refit).days >= 63:
    self.regime_classifier.fit({s: df[df.index < date] for s, df in market_data.items()})
    last_regime_refit = date
```

Ambas corridas refitean trimestralmente de forma expansiva, **pero arrancan 5 años desfasadas**:
- Baseline W3 ya llega a 2024 con **~20 refits acumulados** (2019->2023) y un HMM que transitó todos los regímenes intermedios.
- Screening W3 arranca en 2024 con **0 refits previos** fuera de ventana; su primer fit ve toda la historia 2015-2023 de golpe.

Hipótesis (no probada con re-corridas, solo documentada): el estado del HMM en el borde de W3 (`2024-01-01`) no es comparable — baseline lo alcanza por evolución walk-forward, screening lo inicializa por salto.

### 1.4 Calibrador Platt y BayesianOnlineUpdater — mismo patrón

`backtest_engine.py:334-335` warmup inicial:
```python
cal_scores, cal_outcomes = self._build_calibration_dataset(indicators_cache, start_date, execution_lag_days=...)
calibrator.fit(cal_scores, cal_outcomes)
# dentro, con update_bayesian=True: replay semanal 200->n con CALIBRATION_HORIZON_DAYS=20, CALIBRATION_STRIDE=5
# cada win/loss hace bayesian_updater.update(f"{regime}_{factor}", correct=..., strength=min(max(|pnl/R|,1),cap))
```
Y refit trimestral `CALIBRATOR_REFIT_STRIDE_DAYS=63` con `CALIBRATOR_ROLLING_WINDOW_DAYS=730` (2 años) y `update_bayesian=False`.

Consecuencia: baseline W3 hereda **5 años de evidencia bayesiana online** (`_update_bayesian_weights` por trade, 1.0-10 en unidades R) y un calibrador rodante; screening W3 warmup arranca con replay de 9 años de historia comprimida.

---

## 2. Línea (2): Ventana independiente vs continuación (continuidad de estado)

### 2.1 Evidencia de diseño — screening = 3 runs frescos, baseline = 1 run troceado

**Screening** (`screening_palas.py:43-50,103-108`):
```python
def run_subset(price_data, market_data, start, end):
    engine = BacktestEngine(initial_capital=25000)  # fresh por ventana
    res = engine.run(price_data, market_data, pd.Timestamp(start), pd.Timestamp(end), ...)
# loop: for wname,start,end in WINDOWS: run_subset(subset_price, market_data, start, end)
```

Cada `run` crea: `indicators_cache`, `train_market fit`, `g2/g3`, `calibrator`, `risk_manager`, `equity=25000`, `positions={}`, `bayesian_updater` nuevo.

**Baseline** (`backtest_baseline_clean.py:72-92`):
```python
res_base = BacktestEngine(initial_capital=25000).run(price_data, market_data, pd.Timestamp(START), pd.Timestamp(END))
# luego:
def period_metrics(equity_curve, trades, s, e, engine, n_trials):
    eq = [p for p in equity_curve if s <= p["date"] <= e]
    tr = [t for t in trades if s <= t["exit_date"] <= e]
    return engine.calculate_metrics(eq, tr, n_trials=n_trials)
# trocea equity/trades continuos 2019->2026 por exit_date / date
```

### 2.2 Trades que cruzan frontera de ventana (prueba de continuidad)

Parquet `backend/data/cache/baseline_clean_20260828_183624_trades.parquet` (V1, 250 trades totales — nota: equity/trades guardados son V1 G2+AAII, baseline puro n=78/50 no se persistió, ver §3):
```
W1->W2 cross 1
    PFE  entry 2021-12-21 -> exit 2022-01-04  REGIME_STOP_HIT  pnl -165.55
W2->W3 cross 1
    AAPL entry 2023-11-07 -> exit 2024-01-02  TRAILING_STOP    pnl   8.01
```
En baseline continuo, trades pueden estar **abiertos** cruzando `2021-12-31` o `2023-12-31`; su PnL se atribuye a la ventana de `exit_date`, y el cash/posición se lleva puesto. En screening independiente, **no hay carry** — cada ventana empieza con `cash=25000`, `positions={}`.

### 2.3 Equity compounding vs fresh start

Baseline W3 no empieza en 25000 — su equity inicial es el cierre de W2 (31/12/2023). Datos crudos V1 equity:
```
2026-01-02  27125.90  drawdown -3.48%
...
2026-08-04  26841.94  drawdown -4.49%
W3 max DD -5.47% (2026)
W3_2024 sharpe 0.5385 (252 días, 49 trades, pnl +704) -> bueno
W3_2025 sharpe 0.3559 (250 días, 11 trades, pnl +108) -> okay (pocos trades)
W3_2026 sharpe -0.5030 (147 días, 29 trades, pnl -239) -> malo, arrastra W3 total a 0.1990
```

Un W3 independiente arrancando fresco en 2024-01-01 evitaría el drawdown heredado de 2025-2026? No del todo: el -0.50 de 2026 es independiente del compounding, es de los trades de 2026 mismos. Pero el baseline **sí** compone el drawdown 2025-2026 sobre equity ya ganado en 2024, mientras un fresh W3 computaría Sharpe sobre retornos diarios desde 25000 plano.

Sin re-corridas no se puede aislar, pero la tabla muestra que **la mayor parte del drag de W3 viene de 2026** (-239 PnL, sharpe -0.50) con solo 11 trades en 2025 (desierto de señales) — patrón cualitativamente distinto a W1/W2.

---

## 3. Línea (3): n_trades y composición cualitativa W3

### 3.1 n_trades cuantitativo

| Ventana | Baseline puro (artefacto) n | Baseline V1 (parquet) n | Screening POOLED (json) n | Screening trades/año |
|---------|-----------------------------|-------------------------|---------------------------|----------------------|
| W1 | 103 / 95* (*nuevo) | 99 / 93* | 110 | 55.0 |
| W2 | 47 / 50* | 49 | 51 | 25.5 |
| W3 | 113 / 78* | 119 / 89* | **114** | **43.8** |

* viejo/nuevo baseline puro. **W3 screening +28% trades vs baseline puro nuevo (114 vs 78), +28% vs V1 (114 vs 89).** En W1/W2 la diferencia es <7%.

Normalizado por años (W1 2.0, W2 2.0, W3 2.6):
```
baseline puro trades/año: W1 46.5, W2 24.5, W3 30.0
screening POOLED trades/año: W1 55.0, W2 25.5, W3 43.8  (+46% en W3)
```

Screening W3 genera **significativamente más señales** que baseline W3 bajo idéntico costo (0.10%). Sugiere umbral de entrada más permisivo en ventana W3 independiente (fresh calibrator/HMM) vs continuo con drift bayesiano.

### 3.2 Composición por símbolo (baseline V1 — único parquet disponible)

Baseline V1 W3 top símbolos (89 trades):
```
WMT 7, CAT 6, CSCO 5, GOOGL 5, BRK-B 4, ... (distribución: ningún símbolo domina)
W1 top: INTU 7, AVGO 6, NVDA 6, QCOM 5, TXN 5
W2 top: NVDA 5, LLY 5, CVX 4
```

Screening POOLED W3 composición **no disponible** en artefactos (solo métricas agregadas, no trades parquet). Pendiente de generar si se autoriza nueva corrida con persistencia de trades por ventana.

### 3.3 Exit reasons

Baseline V1:
```
W1: TECHNICAL 31, TRAILING 28, PARTIAL_TP 25, REGIME_STOP 9
W2: TECHNICAL 16, PARTIAL_TP 15, REGIME_STOP 9, TRAILING 9
W3: TECHNICAL 32, PARTIAL_TP 21, REGIME_STOP 17, TRAILING 14, PORTFOLIO_REGIME_STOP 5
```

W3 tiene más `REGIME_STOP` (17 vs 9) y aparición de `PORTFOLIO_REGIME_STOP` (5, ausente en W1/W2) — coherente con **presión de régimen bajista en 2026** (-5.47% DD). Screening W3 con sharpe 0.707 sugiere que en modo independiente ese régimen fue menos penalizante (posible HMM distinto).

### 3.4 Métricas por sub-año W3 (baseline V1)

| Sub-ventana | Días | Trades | PnL sum | Sharpe diario |
|-------------|------|--------|---------|---------------|
| 2024 | 252 | 49 | +704.61 | 0.5385 |
| 2025 | 250 | 11 | +108.68 | 0.3559 |
| 2026-08-04 | 147 | 29 | -239.31 | -0.5030 |

2025 es **desierto de trades** (11 en 250 días, 1 cada 23 días vs 1 cada 5 días en 2024) — el filtro `eligible` casi no deja pasar señales. 2026 revierte a alta frecuencia pero con pérdidas.

---

## 4. Síntesis — qué sabemos y qué queda sin resolver

### Descartado con evidencia cruda:
- **Rango de fechas 10 días:** `load_universe` ignora `start/end` para filtrar (devuelve cache `2015-01-02->2026-08-14` en ambos casos; ver logs `backfill: no backfill needed, gap -364d / -1460d`). Trades W3 `2024->2026-08-04` = 89 y `2024->2026-08-14` = 89, delta 0, equity 649 filas idéntico. **No explica W3.**
- **Columna baseline/V1:** check usaba baseline puro correctamente.
- **Costo:** explica W1/W2, no W3 (W3 empeora con costo corregido).
- **N_TRIALS desigual:** explica W1/W2 DSR, no W3.

### Causas candidatas documentadas (no probadas sin re-corridas):

1. **HMM warmup desfasado 5 años + walk-forward drift** — baseline fiteado en 2015-2018 y refiteado 20 veces hasta W3 vs screening W3 fiteado en 2015-2023 de golpe. Escala de features (`scaler` + `GaussianHMM EM`) y alineación `_align_states` cambian.

2. **Ventana independiente vs continuación** — screening fresh `equity 25000 + positions {} + calibrator + bayesian_updater` por ventana vs baseline continuo con carry de posiciones (PFE, AAPL cruzando fronteras), compounding de equity y evidencia bayesiana acumulada 2019->2024. W3 independiente genera +28-46% trades que continuo.

3. **Composición cualitativa W3** — 2025 desierto (11 trades) + 2026 pérdidas concentradas (-239, sharpe -0.50) vs 2024 bueno (+704). `REGIME_STOP` y `PORTFOLIO_REGIME_STOP` emergen solo en W3. Screening W3 positivo (0.707) sugiere que fresh HMM/calibrador clasifica régimen W3 distinto (menos restrictivo).

### Lo que falta para cerrar W3 (requiere decisión de Boris, no se ejecuta aquí):

- Persistir trades/equity por ventana de screening (hoy solo métricas) para comparar símbolo a símbolo y regime_state.
- Correr un experimento **no productivo**: mismo `start_date 2024-01-01` con dos `train_market` distintos (`<2019` vs `<2024`) manteniendo todo lo demás idéntico, para aislar efecto HMM. Y/o correr baseline troceado como 3 ventanas independientes vs continuo para aislar efecto compounding.
- Cualquiera implica editar scripts / lanzar corridas -> **trial nuevo** bajo `PRE_REGISTRO_SANEAMIENTO_CHECK_A63.md §4.4`: reservar en ledger, no reabrir veredicto sellado.

---

## 5. Evidencia cruda — comandos y artefactos reproducibles

```
# Artefactos verificados (este worktree, 2026-08-30):
backend/data/cache/baseline_clean_20260811_150643.txt      # viejo 0.15% costo, N=17
backend/data/cache/baseline_clean_20260828_183624.txt      # nuevo 0.10% costo, N=17
backend/data/cache/baseline_clean_20260828_183624_equity.parquet  # V1 equity
backend/data/cache/baseline_clean_20260828_183624_trades.parquet  # V1 250 trades
/backend/data/cache/screening_palas_20260828_071737.json   # POOLED 110/51/114

# Código fuente leído (sin modificar):
backend/app/core/backtest_engine.py  líneas 25-26 (REGIME_REFIT 63d), 308-309 (fit), 334-335 (calibrator warmup), 471-477 (walk-forward refit), 585-640 (DSR), 261-309 (run)
backend/app/core/regime_classifier.py líneas 1-140 (HMM 4 estados, features 60d, scaler, _align_states)
backend/app/core/data_ingestion.py líneas 145-153 (load_universe no filtra)
backend/scripts/backtest_baseline_clean.py líneas 28-92
test-kilo-orca/backend/scripts/screening_palas.py líneas 28-108

# Comandos crudos (venv backend/.venv, cwd backend/):
pd.read_parquet('backend/data/cache/SPY.parquet') -> idx 2015-01-02->2026-08-14 (2921 filas)
load_universe(SYMBOLS, "2016-01-01", "2026-08-04") -> 2921 filas SPY idéntico a load_universe(SYMBOLS, "2019-01-01", ...)
tr[(exit>=2024-01-01)&(exit<=2026-08-04)] len 89 vs tr[(exit>=2024-01-01)&(exit<=2026-08-14)] len 89 delta 0
tr cross-window: PFE 2021-12-21->2022-01-04, AAPL 2023-11-07->2024-01-02
W3 subaños: 2024 49tr +704 sharpe 0.5385, 2025 11tr +108 sharpe 0.3559, 2026 29tr -239 sharpe -0.5030
```

---

*No se re-corrió ningún backtest. No se modificó ningún pre-registro sellado. Archivo nuevo: `INVESTIGACION_W3_A63_20260830.md`.*

