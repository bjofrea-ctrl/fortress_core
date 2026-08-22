# PRE-REGISTRO — Validación OOS fresca del baseline momentum+RSI (post-PBO 0.4688)

**Fecha de pre-registro**: 2026-08-22
**Estado**: 🟡 BORRADOR — NO EJECUTADO
**Autor**: OpenCode (Muse Spark) — draft para Boris, validación sólida post-PBO sustancial
**Referencia**: ONBOARDING.md reglas #1–#3 — este documento se escribe ANTES de correr; no se edita después de ver el resultado. Doctrina del usuario (2026-08-14, punto 8): "Siempre lo sólido, lo mejor — nunca lo más fácil."

---

## 1. Hipótesis

**H0 (nula)**: El baseline de producción **momentum + RSI** — seleccionado como "el mejor que queda" entre **21 trials signal_diagnosis** (PBO/CSCV 0.4688 sustancial, PRE_REGISTRO_PBO_CSCV_MOM_RSI.md §4) — **no tiene edge OOS real en datos no usados para la selección**. Su Sharpe OOS en ventana fresca es ≤ 0 y/o su DSR con N_eff=21 no supera el azar (DSR < 0.95).

**H1 (alternativa — lo que se afirmaría si CUMPLE)**: El baseline tiene edge OOS real en datos completamente fuera del período de selección (2019-01-01→2023-12-31 usado en CSCV): **Sharpe_OOS > 0 y DSR ≥ 0.95 con N_eff=21** en la ventana OOS fresca. No es "rentable seguro" — es "no es artefacto de selección y merece seguir como baseline no promovido hasta validación más larga".

> Nota de alcance (decisión del usuario 2026-08-22):
> - **T1.4 estructural** (91→31 trades, Sharpe 0.28→0.38, informativo) queda **no promovible** sin trial W1/W2/W3 DSR≥0.90 — **no se toca** en este pre-registro.
> - **Tarea L (BH→BY)** no se rehace; **DSR/N_eff es calibración** (Sharpe 1.5–1.7 para DSR≥0.95 con N_eff 20–50) — útil como referencia, no como gate que se re-deriva.
> - **regime_classifier random_state=42 determinista**, updater 22:00 **solo agrega post-2023-12-31**, par A/B 2021-2023 válido — se respeta; la ventana OOS fresca no re-escribe historia.
> - **El atajo fácil está PROHIBIDO**: ajustar pesos w_mom/w_rsi al mejor Sharpe full-período (1.25 del grid PBO), mover banda RSI al techo, o rebajar umbral PBO a 0.30 para que "pase". Eso es **cherry-picking post-hoc**. Este pre-registro sella el camino sólido.

---

## 2. Qué es exactamente el baseline "momentum+RSI"

Verificado contra el artefacto y el código (no contra resúmenes) — idéntico a PRE_REGISTRO_PBO_CSCV_MOM_RSI.md §2:

| Dimensión | Definición verificada | Fuente |
|---|---|---|
| **Score** | `score = w_mom * momentum_score + w_rsi * rsi_score`, con `w_mom = 0.0637/(0.0637+0.0322) ≈ 0.664`, `w_rsi ≈ 0.336` (proporcional a \|IC\| pooled diagnóstico). **NO se ajusta** en esta validación. | `backend/app/core/signal_engine.py:85-90` |
| **momentum_score** | `momentum_12_1 = close.pct_change(252)*100` → `clip((mom+50)/150, 0, 1)`. Nombre histórico "12-1" pero implementación actual es **252d sin skip de 1m** (`indicators.py:277`). | `backend/app/core/indicators.py:277`, `signal_engine.py:122-123` |
| **rsi_score** | `rsi14 = RSI(14)` sobre `close` → `0.8 si 45 < rsi < 70 else 0.4` (`signal_engine.py:125-126`). | `signal_engine.py:125-126` |
| **Gates duros** | `40 < rsi < 75` y `adx14 ≥ 20` y `volume_ratio ≥ 1` y `close > ema50 > ema200` y `score ≥ 0.60`. **NO se mueven**. | `signal_engine.py:147-175`, `208-217` |
| **trend/adx** | `trend` constante entre elegibles, `adx` marginal (IC +0.0679 t=+2.31 nominal, no sobrevive Bonferroni) → **siguen como gates, fuera del blend**. | `PLAN_MEJORA_MATEMATICA.md §8/0.5a` |
| **Horizonte diagnóstico** | `fwd_return_20d` (20 ruedas) para ICs; `CALIBRATION_HORIZON_DAYS = 20` en backtest. | `backtest_engine.py:23` |
| **Universo** | **50 símbolos**: 7 base (`SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA`) + 43 `NEW_UNIVERSE` (`backend/scripts/fetch_universe_data.py`). Canónico desde Tarea F (`opportunities_universe.py`). **NO se cambia**. | `RESUMEN_VALIDACION_VARIABLES.md §5`, `ROADMAP.md Tarea F` |
| **Costos** | `COST_PER_SIDE = 0.0005` (0.05%/lado, medido M4; antes 0.0015 asumido) + `slippage 0.0005` en `backtest_engine.run` (config vigente). `EXECUTION_LAG_DAYS=1`. | `backend/app/config.py:46-60` |
| **Baseline limpio** | `backend/data/cache/baseline_clean_20260811_150643.*` — DSR OOS `0.0714 / 0.0284 / 0.1727` (W1/W2/W3, n=103/47/113 trades, sharpe 0.2562/−0.0542/0.5299). **Ninguna ventana cruza DSR ≥ 0.90** — es el único modo documentado que no se refutó como peor que alternativas. | `baseline_clean_20260811_150643.txt` |
| **N_eff estimado** | 20–50 (reportado por el usuario; DSR/N_eff solo calibración). Para esta validación se usa **N_eff=21 conservador** (consumed_budget signal_diagnosis al momento del PBO), no N=1. | Contexto tarea + §40 |

---

## 3. Método — validación OOS fresca (lo sólido, no lo fácil)

### 3.1. Qué mide y qué NO mide

- **Mide**: si el baseline con **hiperparámetros congelados** (pesos, bandas RSI, gates) tiene **edge OOS real en datos que nunca vieron la selección de los 21 trials**. Es **validación fuera de muestra pura**, no ajuste ni re-ranking.
- **NO mide**: PBO de una sola config (PBO<0.10 no aplica a N=1 — no se re-rankea). PBO ya se midió (0.4688 sustancial, PRE_REGISTRO_PBO_CSCV_MOM_RSI.md). Este paso **no repite PBO** — reporta **Sharpe/DSR/win_rate** de la única config, sin comparar contra vecinas.
- **Distinto de**: ajustar pesos al mejor Sharpe full-período (1.25) o mover banda RSI al techo — eso sería **re-usar IS** (lo fácil). Acá la ventana OOS es **disjunta** del período de selección.

### 3.2. Ventana OOS fresca — completamente fuera del período de selección

| Parámetro | Valor pre-registrado | Justificación |
|---|---|---|
| **Período de selección (IS usado en CSCV)** | **2019-01-01 → 2023-12-31** (el CSCV PBO usó 2019→2026-08-04, pero el ledger de 21 trials se cerró al 2023-12-31 para selección; el propio updater solo agrega post-2023-12-31). Este rango **NO se toca** en la validación. | Es el período que el PBO auditó — reutilizarlo sería leakage de selección. |
| **Ventana OOS fresca** | **2024-01-01 → 2026-08-04** como **OOS puro** (o desde último dato del ledger hasta hoy si hay más historia acumulada por el updater 22:00). **Efectiva con embargo**: `OOS_start_efectivo = primer día hábil ≥ IS_end + CALIBRATION_HORIZON_DAYS (20 ruedas)` → **2024-01-31** (20 ruedas hábiles después de 2023-12-31; ver §3.3). El Sharpe/DSR se calcula **solo sobre retornos diarios desde el start efectivo** (purgado). | Datos que **nunca participaron** de la selección de los 21. El updater 22:00 ya los acumula ("pipe antes que agua" — doctrina punto 3). Si la data llega a 2026-08-14 (verificado hoy), se usa hasta el último dato disponible, documentado en artefacto. |
| **Embargo** | **20 ruedas** (`CALIBRATION_HORIZON_DAYS`) entre IS y OOS. | Evita leakage por retornos solapados: un trade abierto el 2023-12-20 con horizonte 20d solapa con OOS; el embargo asegura que ningún `fwd_return_20d` del IS contamine el OOS. Mismo horizonte que el backtest y que §39/§40. |
| **Métrica primaria** | **Sharpe anualizado neto** (retornos diarios de equity, `×√252`, misma que `backtest_engine.calculate_metrics`) **con costos 0.0005 + slippage 0.0005 y `EXECUTION_LAG_DAYS=1`** (config vigente `backend/app/config.py`). | Sharpe es la métrica que el proyecto usa para DSR y para decidir trials de motor (W1/W2/W3). Costos/lag son los vigentes — no se abaratan para que "pase". |
| **Métrica primaria ajustada** | **DSR ≥ 0.95 con N_eff=21 conservador** (no 0.90, no N=1). T = nº de retornos diarios OOS efectivos (no meses). Cálculo DSR Bailey & López de Prado fiel (ver §3.4). | DSR≥0.95 es la vara que el usuario marcó como útil en Tarea L (Sharpe 1.5–1.7 para N_eff 20–50). Se exige 0.95 aquí porque el PBO fue sustancial — la barra post-overfitting debe ser más alta que la estándar 0.90. N=21 conservador alinea con calibración, no con "n=1 no corrige nada". |
| **Métricas secundarias (informativas, no gate)** | **Win rate**, **profit factor**, **cagr**, **max_drawdown**, **n_trades OOS**, **Sharpe CI (bloques circulares)** si disponible. **PBO no aplica** (N=1) — se reporta solo Sharpe/DSR/win_rate, no re-ranking. | Informan magnitud y robustez, no deciden promoción. |

### 3.3. Detalle del embargo y ventana efectiva

- IS: `2019-01-01 → 2023-12-31` (1258 ruedas hábiles en SPY).
- Embargo: 20 ruedas hábiles → primera rueda post-embargo es **2024-01-31** (SPY trading days: 2024-01-02 es la 1ª post-2023-12-31, 2024-01-30 es la 20ª, 2024-01-31 la 21ª → OOS efectivo).
- OOS efectivo: **2024-01-31 → 2026-08-04** (649 ruedas raw 2024-01-01→2026-08-04, **637 ruedas efectivas post-embargo ≈ 30.3 meses**). Verificado hoy: `AAPL 649 rows OOS raw, 637 post-embargo; SPY last 2026-08-14` — hay ~30 meses efectivos, suficiente (ver §8).
- Si el updater acumuló hasta 2026-08-14, el OOS se extiende a 2026-08-14 (657 ruedas raw, +8 días vs 08-04) — documentado en artefacto como ventana real usada.

### 3.4. Cálculo DSR — fiel a Bailey & López de Prado (2014)

Implementación idéntica a `backend/app/core/backtest_engine.py:629-638` (no reinventada):

```
gamma = 0.5772156649
e_max_sr = (1-gamma)*Phi^{-1}(1-1/N) + gamma*Phi^{-1}(1-1/(N*e))   # N = N_eff = 21
sr_daily = mean(returns_diarios) / std(returns_diarios)            # sin anualizar
if len(returns) > 3:
  skew = returns.skew()
  kurt = returns.kurtosis()   # Fisher? El motor usa pandas kurtosis (Fisher)
  var_num = max(1 - skew*sr_daily + (kurt-1)/4 * sr_daily^2, 1e-8)
  sr_std = sqrt(var_num / (len(returns)-1))
  sr_0 = sr_std * e_max_sr
  DSR = Phi( (sr_daily - sr_0)/sr_std )
else DSR = 0
Sharpe_anual = sr_daily * sqrt(252)
```

- Si `backend/app/core/probabilistic_engine.py` expone DSR, se usa (misma fórmula); si no, implementación local fiel — verificada contra el motor.
- `returns_diarios` = `pct_change` de la equity curve diaria del backtest OOS (misma que `calculate_metrics`), **desde el start efectivo post-embargo**.

---

## 4. Criterio de éxito / fracaso — PRE-REGISTRADO y explícito

> Compromiso que ONBOARDING.md regla #1 exige sellar ANTES de correr. No se toca después de ver el número. No hay zona gris.

**Criterio primario (binario, mecánico):**

| Condición medida | Veredicto pre-registrado | Interpretación |
|---|---|---|
| **Sharpe_OOS > 0 Y DSR ≥ 0.95** (con N=21, T=OOS días efectivos) | **CUMPLE** | Edge OOS fresca con confianza ≥95% ajustada por 21 pruebas previas — el baseline sobrevive la validación OOS fresca (no implica promoción automática a señal en vivo; implica que no es artefacto de selección y merece seguir como baseline documentado). |
| **Sharpe_OOS ≤ 0 O DSR < 0.95** | **NO_CUMPLE** | **No tiene edge OOS fresca ajustado** — no se promueve; baseline queda como "único modo documentado que no se refutó como peor que alternativas" pero **no promovible sin nueva evidencia**. |

- **Sin zona gris**: a diferencia del PBO (que tenía gris 0.10–0.20), acá el criterio es binario puro — o supera ambas condiciones o no.
- **DSR≥0.95, no 0.90**: vara más exigente que la estándar del proyecto (0.90) — justificada por PBO sustancial (0.4688). Si se usara 0.90 sería rebajar la vara post-hoc.
- **Sharpe_OOS > 0**: evita que un DSR alto con Sharpe negativo (posible con N pequeño) se cuente como CUMPLE — el signo importa.
- **PBO<0.10 no aplica**: con una sola config no hay ranking IS→OOS — no se reporta PBO, no se re-rankea. Solo Sharpe/DSR/win_rate.

**Corrección por múltiples trials:**

- El ledger `signal_diagnosis` ya aplica Bonferroni por familia (`current_threshold = 1 − 0.10/(consumed+1)`). Ese ajuste corrige **p-valores individuales** (DSR).
- **DSR ya captura la corrección por N=21** — no necesita Bonferroni adicional sobre DSR. Reportar Sharpe y DSR con N=21 es suficiente. Si DSR < 0.95, el Sharpe puntual no rescata la conclusión.

**Veredicto para el ledger (lo que se registra en `trial_registry.json`):**

- **CUMPLE** si `Sharpe_OOS > 0 y DSR ≥ 0.95` → la validación OOS fresca confirma edge.
- **NO_CUMPLE** si no → no confirma (con interpretación según §8).

---

## 5. Ventana, universo y métrica — congelados

- **Universo**: 50 símbolos canónicos (`backend/app/api/routes/opportunities_universe.py` — fuente única desde Tarea F). No se cambia el universo para esta validación.
- **Ventana IS (no tocada)**: `2019-01-01 → 2023-12-31` (selección de los 21). **Ventana OOS fresca**: `2024-01-01 → 2026-08-04` (efectiva `2024-01-31 → 2026-08-04` post-embargo 20 ruedas). Si el updater acumuló hasta 2026-08-14, OOS se extiende a ese último dato — documentado en artefacto.
- **Costos**: `COST_PER_SIDE = 0.0005` + `slippage 0.0005` + `EXECUTION_LAG_DAYS = 1` (config vigente `backend/app/config.py:46-60`). Misma cuenta que el baseline limpio.
- **Métrica primaria**: Sharpe anualizado neto OOS + DSR(N=21). Secundarias: win_rate, PF, CAGR, maxDD, n_trades. No se compara contra "la mejor OOS" ni se re-mide PBO.
- **Baseline de referencia**: `backend/data/cache/baseline_clean_20260811_150643_trades.parquet` (286 trades) + `equity.parquet` — para contexto, no para re-calibrar.

---

## 6. Artefacto, script y ledger — rutas congeladas

| Ítem | Ruta / nombre pre-registrado |
|---|---|
| **Script propuesto** | `backend/scripts/validacion_oos_fresca_mom_rsi.py` — lee universo 50 canónico, ventana OOS fresca con embargo 20d, costos y lag de `config.py`, corre `BacktestEngine.run` OOS (misma mecánica que baseline), calcula Sharpe anualizado neto y DSR(N=21, T=OOS días) vía `backtest_engine.calculate_metrics` o `probabilistic_engine` si expone DSR (misma fórmula Bailey fiel). No ajusta hiperparámetros. |
| **Artefacto esperado** | `backend/data/cache/validacion_oos_fresca_mom_rsi_<YYYYMMDD_HHMMSS>.txt` + `.json` con `{sharpe_oos, dsr_n21, t_oos_dias, t_oos_meses, n_trades_oos, win_rate, pf, cagr, max_dd, ventana_efectiva, costos, N_eff, sharpe_ci, veredicto}`. El `.txt` replica el formato del baseline limpio (métricas por ventana) + Sharpe/DSR OOS efectivo. |
| **Ledger a consumir** | **Familia `signal_diagnosis`** — es un diagnóstico de validación OOS de señal (no un trial de motor con DSR walk-forward que promueva a producción). `n_trials_consumidos = 1` (22→23), `umbral_aplicado = "DSR≥0.95 N=21 OOS fresca"` — veredicto CUMPLE/NO_CUMPLE según §4. `motor_signal` **no se toca** (queda en 11 consumidos). La tabla DSR/N_eff de Tarea L queda como **calibración** sin ledger (decisión del usuario). |
| **T mínimo para correr** | **≥20 meses efectivos post-embargo** (~420 ruedas). Si T_OOS efectivo <20 meses, el script **no se corre** — se deja listo y se documenta fecha estimada de disponibilidad (ver §8). |
| **T actual verificado (2026-08-14)** | 637 ruedas efectivas ≈ **30.3 meses** (2024-01-31→2026-08-14) → **supera el piso 20 meses** → se corre **UNA sola vez** (sin re-corridas por hiperparámetro). Si se hubiera quedado <20, quedaría en cola. |

---

## 7. Implementación — qué existe y qué falta

**Existe:**

- `backend/app/core/backtest_engine.py` — `BacktestEngine.run` + `calculate_metrics` (Sharpe, DSR con n_trials, CI bloques circulares). Ya usado para baseline limpio W1/W2/W3.
- `backend/app/core/probabilistic_engine.py` — `WalkForwardValidator`, `SignalQualityMetrics`, `circular_block_bootstrap_ci` (T2.2). DSR no está aislado ahí, pero la fórmula Bailey está en `backtest_engine`.
- `backend/app/core/signal_engine.py` — baseline congelado (w=0.664/0.336, mom 252d, rsi 45-70→0.8, gates).
- `backend/app/core/trial_registry.py` — ledger con `consumed_budget("signal_diagnosis")` y `current_threshold`. El script nuevo debe leer `N_eff = 21` (no hardcodear Sharpe) y registrar con `register_trial`.
- `backend/app/config.py` — `COST_PER_SIDE=0.0005`, `EXECUTION_LAG_DAYS=1` (fuente única).
- `backend/scripts/pbo_cscv_mom_rsi.py` — plantilla de universo 50 + ventana 2019→2026; NO se copia su métrica (aquí Sharpe/DSR de una sola config, no PBO).
- Updater 22:00 (`com.fortresscore.dataupdater.plist` + `data_updater.sh`) — ya acumula OHLCV post-2023-12-31 + FinBERT; `SPY.parquet last 2026-08-14` verificado.

**Falta (a construir cuando se libere slot):**

- `backend/scripts/validacion_oos_fresca_mom_rsi.py` — nuevo script que:
  1. Lee `trial_registry.json` → verifica N_eff=21 (conservador, no consumed_budget actual 22 — se usa 21 porque es el N del PBO auditado, documentado).
  2. Deriva ventana OOS efectiva: `IS_END=2023-12-31`, `EMBARGO=20`, `OOS_START_RAW=2024-01-01` → `OOS_START_EFECTIVO` = primer trading day ≥ IS_END+20 (2024-01-31) vía `SPY.parquet` trading calendar; `OOS_END` = min(`2026-08-04`, last data) o last data si > pre-registrado (documentado).
  3. Valida T efectivo: si `T_dias < 420` (~20 meses) → aborta sin artefacto y documenta fecha estimada (OOS_END + (420−T) ruedas).
  4. Carga universo 50 (`SYMBOLS` de `opportunities_universe.py`) vía `load_universe` / `data_updater` cache (sin descargas nuevas si cache fresco).
  5. Corre `BacktestEngine.run(price_data, market_data, OOS_START_EFECTIVO, OOS_END, commission=0.0005, slippage=0.0005, execution_lag_days=1)` — **sin tocar pesos/bandas**.
  6. Calcula métricas OOS efectivas: `equity_curve` → retornos diarios → `Sharpe_anual = mean/std*sqrt252`, `DSR(N=21)` vía `calculate_metrics(n_trials=21)` o fórmula Bailey fiel, `win_rate`, `PF`, `n_trades`, Sharpe CI si `probabilistic_engine.circular_block_bootstrap_ci` disponible.
  7. Escribe artefacto `.txt` + `.json` y hace `register_trial(id="validacion_oos_fresca_mom_rsi", familia="signal_diagnosis", n_trials_consumidos=1, umbral_aplicado="DSR≥0.95 N=21 OOS fresca", veredicto=CUMPLE/NO_CUMPLE)`.

---

## 8. Riesgos y limitaciones — declarados ANTES de correr

1. **T pequeño OOS (~30 meses) → intervalo ancho.** Con ~637 ruedas, el error estándar del Sharpe ≈ `1/√T_meses ≈ 0.18` (mensual) / `1/√T_dias ≈ 0.04` (diario). Un Sharpe puntual 0.5 puede tener CI que cruza 0. **Mitigación**: reportar CI de bloques circulares (T2.2, seed 42) además del punto; DSR ya incorpora T en su varianza. No se "ensancha" el umbral post-hoc si el intervalo es grande.
2. **No se corrige heterogeneidad de los 21 trials previos.** Esta validación no re-mide cada uno de los 21 en OOS — mide solo el survivor (momentum+RSI). Si el survivor falla, no sabemos si otro de los 21 habría pasado en OOS fresca — pero esa es exactamente la razón de exigir DSR≥0.95 con N=21: el ajuste por haber mirado 21 ya está en el DSR, sin necesidad de re-correrlos.
3. **Autocorrelación y tamaño mínimo IS/OOS.** El Sharpe diario puede estar autocorrelacionado por el hold medio (~11 días). El CI de bloques circulares (T2.2) mitiga; el DSR ya corrige skew/kurtosis pero no autocorrelación serial de retornos — se declara como limitación.
4. **Universo 50 con cross-section operable ~6 símbolos/día.** El Sharpe OOS ya incorpora el filtro eligible (solo se opera lo elegible), igual que el baseline limpio — no hay inconsistencia, pero el lector no debe confundir "50 símbolos" con "50 apuestas independientes por día".
5. **Lookahead del baseline.** El baseline se calibró con datos 2019–2026; la ventana OOS fresca (2024→) es posterior al cierre del ledger de selección (2023-12-31) pero anterior al PBO (2026-08-22) — no es "futuro absoluto" respecto a hoy, es "futuro respecto al momento de selección". El embargo 20d mitiga leakage de retornos solapados, pero no la "pureza temporal absoluta" (habría que esperar datos 2026-08-15→). Se documenta el compromiso.
6. **Régimen y costos.** `regime_classifier` es walk-forward con `random_state=42` determinista; `TARGET_VOLATILITY` sigue sin conectar (pista sin acción §12) — no afecta esta validación. Costos 0.0005 son piso paper medido con margen 2.6×; si el costo live real es mayor, el Sharpe OOS sería menor — se declara.
7. **N_eff vs PBO.** N_eff 20–50 corrige DSR por autocorrelación de retornos; PBO corrige por selección. Son ortogonales — un N_eff bajo no implica PBO alto. Se reportan ambos sin mezclarlos. Usar N=21 conservador alinea con PBO auditado.
8. **Fecha estimada si T<20.** Hoy T≈30 meses → no aplica. Si hubiera sido <20, la fecha estimada sería `OOS_END + (420−T_dias)` ruedas hábiles ≈ 2024-12-31 + déficit — se documentaría en el pre-registro sin correr.

---

## 9. Checklist de no-ejecución — este documento se escribe ANTES de correr, no se edita después

- [x] Este archivo se creó **sin correr ningún backtest**, sin modificar el ledger, sin ejecutar `python` para la validación OOS (solo lectura de artefactos y código para verificar T y costos).
- [x] El criterio de §4 (`Sharpe_OOS >0 y DSR≥0.95 con N=21` → CUMPLE; si no, NO_CUMPLE, sin zona gris) está sellado acá — **no se cambia al ver el número**. Si Sharpe 0.4 con DSR 0.93, no se re-etiqueta como "casi CUMPLE"; se reporta como **NO_CUMPLE**.
- [x] La ventana OOS fresca (2024-01-31 efectiva post-embargo) y costos (0.0005/0.0005/ lag 1) están congeladas — no se prueban "otras ventanas hasta que dé".
- [x] El N_eff=21 está congelado — no se cambia a N=11 para inflar DSR post-hoc.
- [ ] **Al ejecutar (cuando se libere slot)**: correr `backend/scripts/validacion_oos_fresca_mom_rsi.py` → artefacto `validacion_oos_fresca_mom_rsi_*.txt` → `register_trial` con veredicto mecánico de §4 → actualizar `ROADMAP.md` y `PLAN_MEJORA_MATEMATICA.md` con el resultado (sin re-escribir este pre-registro). Si el script aborta por T insuficiente o Sharpe NaN, se documenta como **NO INTERPRETABLE / EN COLA**, no como NO_CUMPLE.
- [ ] **Prohibido**: editar este archivo después de correr para "alinear" el criterio con el resultado. Cualquier corrección metodológica requiere **nuevo pre-registro** (como se hizo con #16→#17 para M2).

---

## 10. Próximo paso cuando se libere slot + por qué esto es lo sólido vs lo fácil

### Próximo paso

1. Asignar slot (Kilo/Cline/OpenCode libre) → implementar `backend/scripts/validacion_oos_fresca_mom_rsi.py` según §3.2–§3.4 y §7 (derivar OOS efectivo post-embargo, validar T≥20 meses, cargar universo 50, correr BacktestEngine OOS con costos/lag vigentes, Sharpe/DSR(N=21)).
2. Correr **una sola vez** (sin re-corridas para "probar otro costo/ventana"): `cd backend && .venv/bin/python -m scripts.validacion_oos_fresca_mom_rsi` → artefacto `backend/data/cache/validacion_oos_fresca_mom_rsi_*.txt`.
3. Veredicto mecánico de §4 → `register_trial(id="validacion_oos_fresca_mom_rsi", familia="signal_diagnosis", n_trials_consumidos=1, umbral_aplicado="DSR≥0.95 N=21 OOS fresca", veredicto=CUMPLE|NO_CUMPLE, artefacto=..., seccion_doc="PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md §4")`.
4. Actualizar `ROADMAP.md` (fila validación OOS fresca → 🟢 cerrado con veredicto + artefacto) y `PLAN_MEJORA_MATEMATICA.md` (nueva § con resultado + interpretación). No editar este pre-registro.
5. Decisión: si CUMPLE → el baseline sobrevive validación OOS fresca post-PBO (no implica señal en vivo, implica que no es artefacto y puede seguir como baseline documentado con DSR informado); si NO_CUMPLE → el baseline no se promueve y cualquier "mejor de 21" futuro exige nueva hipótesis pre-registrada, no ajuste de pesos.

### Por qué esto es lo sólido vs lo fácil (doctrina punto 8)

| Atajo fácil (PROHIBIDO) | Por qué falla | Lo sólido (este pre-registro) |
|---|---|---|
| Ajustar `w_mom/w_rsi` al mejor Sharpe full-período (1.25 del grid PBO) | Reusa IS (2019→2026) para optimizar — es **lookahead de selección**: eliges el peso que mejor quedó sabiendo el futuro. | **Pesos congelados** 0.664/0.336 (IC pooled diagnóstico) — los mismos del baseline auditado. No se optimiza nada. |
| Mover banda RSI al techo (50,75) que dio mejor Sharpe en el grid | Mismo Cherry-picking — el grid se miró post-hoc para elegir el techo. | **Banda RSI congelada** 45-70 → 0.8 — la del motor de producción. |
| Rebajar umbral PBO a 0.30 para que "pase" | Re-etiqueta el fracaso como éxito sin nueva evidencia — viola ONBOARDING #1. | **Criterio DSR≥0.95 con N=21** pre-registrado, más exigente que 0.90 — sube la vara post-PBO, no la baja. |
| Re-usar ventana completa 2019→2026 y decir "Sharpe 0.93, pasa" | La ventana contiene el período de selección — es **in-sample** para los 21. | **Ventana OOS fresca 2024→ disjunta** del IS 2019→2023 con **embargo 20d** — datos nunca usados para elegir entre los 21. |
| Probar 3 ventanas OOS hasta que una dé | Grados de libertad post-hoc — infla falso positivo. | **Una sola ventana pre-registrada** (2024-01-31→2026-08-04/14) — una corrida, un veredicto. |
| Ignorar costos/lag reales | Infla Sharpe artificialmente. | **Costos 0.0005+0.0005 y lag 1** vigentes — los mismos que el baseline limpio. |

> **Pipe antes que agua** (doctrina punto 3): el updater 22:00 ya acumula OOS fresca post-2023-12-31 todos los días. Esta validación no pide "comprar histórico" — **exige datos que el pipe ya construye**. Si T fuera <20 meses, no se inventa un atajo: se espera a que el updater acumule suficiente OOS y se documenta fecha estimada. Hoy T≈30 meses → ya se puede medir, sin esperar.

### Relación con T1.4 y Tarea L

- **T1.4**: 91→31 trades, Sharpe +0.10, win 57→71% pero CAGR −0.27pp — **informativo, no promovible** sin trial W1/W2/W3 DSR≥0.90. No se re-mide ni se mezcla con esta validación (universo y mercado distintos).
- **Tarea L (BH→BY)**: DSR/N_eff calibración (Sharpe 1.5–1.7 para DSR≥0.95 con N_eff 20–50) — **no se rehace**, se usa solo como referencia de que DSR≥0.95 con N=21 es vara alta y útil.

---

*Fin del pre-registro — borrador en cola, no ejecutado. Próxima edición: solo para agregar el artefacto y el veredicto mecánico cuando se corra; el criterio de §4 no se toca.*
