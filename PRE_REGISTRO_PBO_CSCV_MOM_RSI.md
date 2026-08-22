# PRE-REGISTRO — PBO/CSCV sobre baseline momentum+RSI (único baseline que sobrevivió)

**Fecha de pre-registro**: 2026-08-22
**Estado**: 🟡 BORRADOR — NO EJECUTADO (en cola — Kilo/Cline/OpenCode ocupados)
**Autor**: OpenCode (Muse Spark) — draft para Boris, a la espera de slot libre
**Referencia**: ONBOARDING.md reglas #1–#3 — este documento se escribe ANTES de correr; no se edita después de ver el resultado.

---

## 1. Hipótesis

**H0 (nula — lo que PBO mide)**: El baseline de producción **momentum + RSI** — seleccionado como "el mejor que queda" entre **~21 trials del ledger `signal_diagnosis`** — **no tiene edge OOS real** y su ranking IS es artefacto de selección entre múltiples candidatos. Bajo H0, la configuración rankeada #1 IS cae **por debajo de la mediana OOS** con probabilidad ≥ 0.5.

**H1 (alternativa)**: El ranking IS del baseline es estable OOS — la probabilidad de degradar bajo la mediana (PBO) es baja (< umbral pre-registrado).

> Nota de alcance (decisión del usuario 2026-08-22): **Tarea L (BH→BY) NO se rehace** y la tabla DSR/N_eff de ese contraste es **solo calibración**. Lo único accionable es este PBO/CSCV: mide **overfitting de proceso** (haber mirado 21 candidatos y quedarse con el menos malo), no overfitting de un solo backtest. PBO ≠ DSR: DSR pregunta "¿este Sharpe es casualidad dado n_trials?"; PBO pregunta "¿el procedimiento de elegir el mejor IS me deja peor que la mediana OOS?".

---

## 2. Qué es exactamente el baseline "momentum+RSI"

Verificado contra el artefacto y el código (no contra resúmenes):

| Dimensión | Definición verificada | Fuente |
|---|---|---|
| **Score** | `score = w_mom * momentum_score + w_rsi * rsi_score`, con `w_mom = 0.0637/(0.0637+0.0322) ≈ 0.664`, `w_rsi ≈ 0.336` (proporcional a \|IC\| pooled diagnóstico). | `backend/app/core/signal_engine.py:85-90` |
| **momentum_score** | `momentum_12_1 = close.pct_change(252)*100` → `clip((mom+50)/150, 0, 1)`. Nombre histórico "12-1" pero implementación actual es **252d sin skip de 1m** (`indicators.py:277`). | `backend/app/core/indicators.py:277`, `signal_engine.py:122-123` |
| **rsi_score** | `rsi14 = RSI(14)` sobre `close` → `0.8 si 45 < rsi < 70 else 0.4` (`signal_engine.py:125-126`). Gate adicional: `40 < rsi < 75` y `adx14 ≥ 20` y `volume_ratio ≥ 1` y `close > ema50 > ema200` y `score ≥ 0.60`. | `signal_engine.py:147-175`, `208-217` |
| **trend/adx** | `trend` constante entre elegibles, `adx` marginal (IC +0.0679 t=+2.31 nominal, no sobrevive Bonferroni) → **siguen como gates duros, fuera del blend** (decisión §0.5a). | `PLAN_MEJORA_MATEMATICA.md §8/0.5a` |
| **Horizonte diagnóstico** | `fwd_return_20d` (20 ruedas) para ICs; `CALIBRATION_HORIZON_DAYS = 20` en backtest. | `backtest_engine.py:23` |
| **Universo** | **50 símbolos**: 7 base (`SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA`) + 43 `NEW_UNIVERSE` (`backend/scripts/fetch_universe_data.py`). Canónico desde Tarea F (`opportunities_universe.py`). | `RESUMEN_VALIDACION_VARIABLES.md §5`, `ROADMAP.md Tarea F` |
| **Ventana** | `2019-01-01 → 2026-08-04` (OHLC diario vía `load_universe` / `data_updater` 22:00 diario). Ventanas OOS del proyecto: **W1 2020-2021, W2 2022-2023, W3 2024-2026-08-04**, piso `≥30 trades/ventana`. | `PLAN_MEJORA_MATEMATICA.md §0.6.1`, artefacto `baseline_clean_20260811_150643.txt` |
| **Costos** | `COST_PER_SIDE = 0.0005` (0.05%/lado, medido M4; antes 0.0015 asumido) + `slippage 0.0005` en `backtest_engine.run`. | `backend/app/config.py:46-53` |
| **Baseline limpio** | `backend/data/cache/baseline_clean_20260811_150643.*` — DSR OOS `0.0714 / 0.0284 / 0.1727` (W1/W2/W3, n=103/47/113 trades, sharpe 0.2562/−0.0542/0.5299, PF 1.3785/1.0882/1.4878). **Ninguna ventana cruza DSR ≥ 0.90** — no es "válido por sí solo", es el único modo documentado que no se refutó como peor que alternativas. | `baseline_clean_20260811_150643.txt`, `RESUMEN_VALIDACION_VARIABLES.md §1` |
| **N_eff estimado** | 20–50 (reportado por el usuario para esta tarea; DSR/N_eff solo calibración, no gate). | Contexto de la tarea |

---

## 3. Método — CSCV / PBO (Bailey, Borwein, López de Prado & Zhu, 2014–2017)

### 3.1. Qué mide PBO

**PBO = P(rank_OOS < mediana)** — probabilidad de que la configuración rankeada #1 IS (in-sample) caiga por debajo de la mediana OOS (out-of-sample) entre las N configuraciones. Es **overfitting de selección**, no de una sola estrategia.

- **Logit** por split: `λ = logit(rank_OOS / (N+1))` (o equivalentemente `logit = Sharpe_OOS(rank1) − median(Sharpe_OOS)` según implementación). Histograma de logits → `PBO = P(λ < 0)`.
- Referencia: Bailey et al., *"The Probability of Backtest Overfitting"* (JoPM 2015) y *"Pseudo-Mathematics and Financial Charlatanism"* (2014). Implementación canónica: S particiones cronológicas → C(S, S/2) splits combinatorios.

### 3.2. Por qué el script previo NO sirve para esta pregunta

`backend/scripts/pbo_cscv.py` (y artefactos `pbo_cscv_20260811_093415.txt` / `093540.txt`) calcula `PBO = P(sharpe_test − sharpe_train < 0)` con **UNA sola configuración** (el baseline) y splits balanceados C(16,8)=12 870. El propio script lo advierte:

> "Con UNA configuración y submuestras balanceadas, el logit es ANTISIMÉTRICO por construcción → PBO converge a **0.5 SIEMPRE**. No es '50% de sobreajuste': es el NULO de selección."

PBO=0.5 ahí **no informa sobre selección entre 21 trials** — informa dispersión IS-vs-OOS de una sola serie (desv 0.14). Para medir selección hace falta **N ≥ 2 configuraciones** rankeadas IS.

### 3.3. CSCV propuesto para este pre-registro (N ≈ 21)

| Parámetro | Valor pre-registrado | Justificación |
|---|---|---|
| **N configuraciones** | **21** (ledger `signal_diagnosis` a 2026-08-22: `consumed_budget(signal_diagnosis)=21`, ver `backend/data/trial_registry.json`). Lista congelada al momento de escribir este draft (ver §6). | Es el proceso que se quiere auditar: "miré 21 ideas de señal y me quedé con momentum+RSI porque era lo menos malo". |
| **Métrica primaria para ranking** | **Sharpe anualizado OOS** (retornos diarios de equity, `×√252`, misma que `backtest_engine.calculate_metrics`). Si una configuración no tiene backtest (diagnósticos IC puros: gap, MA200, FinBERT...), se usa **proxy IC** mapeado a Sharpe vía `Sharpe ≈ IC × √N_eff` solo para ranking, con nota explícita de heterogeneidad (limitación §8). Alternativa limpia (preferida si el slot lo permite): reconstruir las 21 como **estrategias backtesteables** con `backtest_engine.run` (misma ventana, mismos costos 0.0005, `EXECUTION_LAG_DAYS=1`) y rankear por Sharpe real — elimina heterogeneidad. | Sharpe es la métrica que el proyecto usa para DSR y para decidir trials de motor (W1/W2/W3). Rank IC intra-día es el diagnóstico, pero PBO clásico rankea por performance OOS, no por IC. |
| **S particiones** | **16 particiones cronológicas** sobre la serie de retornos diarios OOS (misma S que `pbo_cscv.py`; `C(16,8)=12 870` combos). | S=16 es el estándar del paper (potencia vs costo). Con ~7 años (2019–2026 ≈ 1 900 ruedas), cada partición ≈ 120 ruedas — suficiente para Sharpe estable. Si S=16 deja particiones < 60 ruedas por poca historia en alguna reconstrucción, fallback a **S=12 (C=924)** — declarado acá, no post-hoc. |
| **Splits** | **Combinatorial Split CV**: por cada combo de S/2 particiones como IS y el resto como OOS, rankear las N por Sharpe_IS, tomar la #1, medir su rank_OOS. | Fiel a Bailey et al. — cada observación pertenece a IS en la mitad de los splits y a OOS en la otra mitad (balanceo combinatorio, no k-fold contiguo). |
| **PBO** | `PBO = (# splits donde rank_OOS(rank1_IS) < N/2) / # splits` — fracción de splits donde la mejor IS cae bajo la mediana OOS. | Definición canónica del paper. |
| **Logit** | `logit = log( (rank_OOS/(N+1)) / (1 − rank_OOS/(N+1)) )` por split; histograma + `P(logit < 0) = PBO`. | Visualiza concentración vs dispersión (misma figura que el script previo pero con N>1, ya no antisimétrica). |
| **Secundarios** | **Performance degradation**: `Sharpe_OOS(rank1) − Sharpe_IS(rank1)` por split (mediana y p5). **Stability**: correlación rank IS vs OOS (Spearman). | Informan magnitud de la degradación, no solo frecuencia. |

### 3.4. Artefacto esperado vs script previo

|  | Script previo (`pbo_cscv.py`) | Este pre-registro |
|---|---|---|
| N | 1 (baseline solo) | 21 (todas las candidatas) |
| Métrica | `sharpe(pnl por trade)` | `Sharpe anualizado (retornos diarios)` — comparable con DSR |
| PBO | 0.5 por construcción | Informativo (mide selección) |
| Pregunta | "¿mi única serie es estable IS vs OOS?" | "¿elegir la mejor de 21 me deja bajo la mediana OOS?" |

---

## 4. Criterio de éxito / fracaso — PRE-REGISTRADO y explícito

> Este es el compromiso que ONBOARDING.md regla #1 exige sellar ANTES de correr. No se toca después de ver el número.

**Criterio primario (PBO):**

| PBO medido | Veredicto pre-registrado | Interpretación |
|---|---|---|
| **PBO < 0.10** | **NO OVERFITTING de proceso** — el ranking IS es informativo; el baseline no es artefacto de selección. | Estándar estricto de Bailey et al. ("<10% = confianza"). |
| **0.10 ≤ PBO < 0.20** | **ZONA GRIS — overfitting leve / sospechoso** — no se declara artefacto, pero no se afirma robustez; se exige evidencia adicional (DSR, N_eff, walk-forward) antes de cualquier promoción. | Bailey et al. marcan 10–20% como "caution". |
| **PBO ≥ 0.20** | **OVERFITTING de proceso — NO_CUMPLE** — la selección entre 21 trials no es mejor que elegir al azar; el baseline rankeado "mejor" es indistinguible de la mediana OOS. | Umbral laxo del paper ("<20% aceptable" en versiones divulgativas); ≥20% = backtest overfitting. |
| **PBO ≥ 0.30** | **OVERFITTING sustancial** — desconfiar de cualquier rendimiento IS reportado del baseline. | Corte de "substantial" en la literatura. |

**Veredicto binario para el ledger (lo que se registra en `trial_registry.json`):**

- **CUMPLE** si `PBO < 0.10` → el baseline sobrevive la auditoría de selección.
- **NO_CUMPLE** si `PBO ≥ 0.10` → no sobrevive (con matiz gris 0.10–0.20 documentado, pero binario es ≥0.10 = no pasa el estricto).

**Justificación del umbral elegido (0.10 estricto, 0.20 laxo):**

Bailey & López de Prado (2014) proponen PBO como probabilidad — sin umbral universal, pero la práctica del paper y las réplicas usan **<10% como "no overfit"** y **>30% como "overfit sustancial"**. Con N=21 y S=16 (12 870 splits), el error estándar de PBO ≈ `√(p(1−p)/n_splits)` < 0.005, así que 0.10 vs 0.20 es distinguible. Elegimos **0.10 como gate binario** porque el proyecto ya opera con DSR ≥ 0.90 (cola 10%) — misma filosofía: la barra para afirmar "no es casualidad" es 10%, no 20%. El umbral 0.20 queda como lectura secundaria ("ni siquiera pasa el laxo").

**Menciona explícita (pedida en la tarea): PBO alto = backtest overfitting** — no significa que la estrategia pierda siempre; significa que **el procedimiento de elegir la mejor IS no generaliza**: la IS #1 es tan buena como una elección aleatoria OOS. Es la firma de haber probado demasiadas variantes y quedarse con la que mejor quedó in-sample.

**Corrección por múltiples trials ya consumidos:**

- El ledger `signal_diagnosis` ya aplica Bonferroni por familia (`current_threshold = 1 − 0.10/(consumed+1)`). Ese ajuste corrige **p-valores individuales** (DSR).
- **PBO ya captura la selección** — no necesita Bonferroni adicional sobre PBO. PBO mide directamente el efecto de haber mirado N candidatos. Reportar ambos (DSR con n_trials y PBO) es complementario, no doble corrección. Si PBO ≥ 0.20, el DSR del baseline (0.17 en W3) no rescata la conclusión: el proceso que lo eligió está sobreajustado aunque un Sharpe puntual parezca decente.

---

## 5. Ventana, universo y métrica — congelados

- **Universo**: 50 símbolos canónicos (`backend/app/api/routes/opportunities_universe.py` — fuente única desde Tarea F). No se cambia el universo para este PBO.
- **Ventana de evaluación**: `2019-01-01 → 2026-08-04` (misma que el baseline limpio). Si la reconstrucción de las 21 estrategias necesita historia previa para warmup de indicadores (252d para momentum), se usa `2015-01-01` solo como warmup — **no entra al ranking IS/OOS**.
- **Costos**: `COST_PER_SIDE = 0.0005` + `slippage 0.0005` + `EXECUTION_LAG_DAYS = 1` (config vigente). Todas las N estrategias se evalúan con los mismos costos — PBO mide selección, no sensibilidad a costos.
- **Métrica primaria**: Sharpe anualizado OOS (retornos diarios de equity). Secundaria: RankIC intra-día si la reconstrucción backtesteable no es viable para algún diagnóstico (con nota de heterogeneidad §8).
- **Comparativo contra mediana**: rank_OOS vs `N/2` (mediana). PBO = P(rank_OOS < mediana). No se compara contra "la mejor OOS" (eso sería P(rank_OOS == 1), mucho más exigente y no es PBO).

---

## 6. Artefacto, script y ledger — rutas congeladas

| Ítem | Ruta / nombre pre-registrado |
|---|---|
| **Script propuesto** | `backend/scripts/pbo_cscv_mom_rsi.py` — CSCV con N=21, S=16, Sharpe OOS, histograma de logits, PBO. Reutiliza `backend/app/core/probabilistic_engine.py:WalkForwardValidator` solo como referencia de ventanas; la combinatoria es `itertools.combinations` como en `pbo_cscv.py`, pero con **N Sharpe por split**, no uno solo. |
| **Artefacto esperado** | `backend/data/cache/pbo_cscv_mom_rsi_<YYYYMMDD_HHMMSS>.txt` + `.json` con `{pbo, logits, sharpe_is_rank1, sharpe_oos_rank1, perf_degradation, S, N, n_splits}`. El `.txt` replica el formato de `pbo_cscv_20260811_093415.txt` (distribución del logit p5/p25/p50/p75/p95, media, desv, PBO) pero con la tabla por ventana IS/OOS para cada una de las 21. |
| **Ledger a consumir** | **Familia `signal_diagnosis`** — es un diagnóstico de señal (rank/selección), no un trial de motor con DSR. `n_trials_consumidos = 1` (21→22), `umbral_aplicado = "PBO < 0.10 (Bailey et al.)"` — veredicto CUMPLE/NO_CUMPLE según §4. `motor_signal` **no se toca** (queda en 11 consumidos). La tabla DSR/N_eff de Tarea L queda como **calibración** sin ledger (decisión del usuario). |
| **Baseline de referencia** | `backend/data/cache/baseline_clean_20260811_150643_trades.parquet` (286 trades) + `equity.parquet` — para reproducir el Sharpe del baseline en cada partición. |
| **N = 21 — lista congelada** | Las 21 entradas `signal_diagnosis` en `backend/data/trial_registry.json` a 2026-08-22 (ver §6.1). Si al momento de ejecutar el ledger ya tiene 22 (porque otro agente cerró un diagnóstico en paralelo), N se actualiza a 22 y se documenta en el artefacto — el PBO se recalcula con el N real del ledger al momento de correr, no con el N de este draft. |

### 6.1. N = 21 — lista congelada al 2026-08-22

Extraída de `backend/data/trial_registry.json` (familia `signal_diagnosis`, orden de registro):

1. `fase05a_rr2_intraday` — Rank IC intra-día momentum/RSI/ADX (t=−0.28/+1.38/+2.31)
2. `fase05b_rmt` — RMT / Marchenko-Pastur (8 factores residuales)
3. `fase05c_ridge_macro_crudo` — Ridge macro crudo (delta −0.0046)
4. `sectorial_endogeno` — Diagnóstico sectorial endógeno (t=+1.03/+0.57)
5. `reeval_trial14` — Re-evaluación basket ADX (t-NW por ventana)
6. `gap_reversion_diag` — Gap reversion intra-día (t=−11.29→−0.46)
7. `rr2_subperiodos` — Rank IC por sub-período PRE/POST 2022
8. `ma200_clusters` — MA200 por cluster RMT (C3/C6)
9. `donchian` — Canal de Donchian (t=−0.81)
10. `ma200_beta_control` — Control de beta sobre C3/C6 (C6 t=−2.87 sobrevive)
11. `horizon_audit_5d_10d` — Auditoría de horizonte 5d/10d
12. `horizon_largo_60d_125d` — Horizontes largos 60d/125d
13. `lead_lag_diag` — Lead-lag entre símbolos (10 pares × 5 lags, Bonferroni-50)
14. `triple_barrier_retest` — Re-test factores vs label de barrera M1
15. `adx_walkforward` — ADX walk-forward por ventana (W1 +0.79/W2 +1.54/W3 +1.47)
16. `weekly_indicators_2026` — Indicadores semanales (mom_20w/rsi_14w/adx_14w)
17. `finbert_sentiment_eventstudy` — FinBERT 8-K 2.02 event study (t +0.38/−0.85/−0.08)
18. `xsec_relative_and_aaii_timing` — Rank IC vs retorno relativo + AAII timing
19. `trial_macd_bollinger` — MACD dirección + Bollinger régimen (Bonferroni-19)
20. `trial_ofi_proxy` — OFI EWMA fast (T1.1, t −2.30/+0.10/+0.19)
21. `trial_cvd_proxy` — CVD rolling (T1.2, t +0.73/−0.84/+0.38)

> Si al correr ya hay 22 (p. ej. `hurst_vol_ic` si se promociona a ledger), el script lo detecta y lo incluye — el N efectivo queda en el artefacto.

---

## 7. Implementación — qué existe y qué falta

**Existe:**

- `backend/app/core/probabilistic_engine.py` — `WalkForwardValidator`, `SignalQualityMetrics`, `circular_block_bootstrap_ci` (T2.2). No tiene CSCV multi-estrategia; solo walk-forward de una sola serie.
- `backend/scripts/pbo_cscv.py` — CSCV con N=1 (antisimétrico → PBO=0.5). Útil como plantilla de particionado (`S=16`, `itertools.combinations`, `sharpe()`), pero **no mide selección**.
- `backend/app/core/trial_registry.py` — ledger con `consumed_budget("signal_diagnosis")` y `current_threshold`. El script nuevo debe leer `N = consumed_budget(...)` al inicio (no hardcodear 21).

**Falta (a construir cuando se libere slot):**

- `backend/scripts/pbo_cscv_mom_rsi.py` — nuevo script que:
  1. Lee `trial_registry.json` → N y lista de configuraciones (o reconstruye las 21 como estrategias backtesteables si se elige la vía limpia).
  2. Para cada una de las N, genera la serie de retornos diarios OOS (si es diagnóstico sin equity, usa el proxy IC→Sharpe con nota).
  3. Particiona cronológicamente en S=16 (o 12 fallback), genera C(S,S/2) splits, rankea IS, mide rank_OOS, acumula logits.
  4. Calcula PBO, histograma, perf degradation, correlación de ranks.
  5. Escribe artefacto `.txt` + `.json` y hace `register_trial(id="pbo_cscv_mom_rsi", familia="signal_diagnosis", n_trials_consumidos=1, umbral_aplicado="PBO<0.10", veredicto=CUMPLE/NO_CUMPLE)`.

---

## 8. Riesgos y limitaciones — declarados ANTES de correr

1. **Heterogeneidad de las N configuraciones.** Las 21 no son 21 parametrizaciones del mismo modelo (p. ej. 21 thresholds de RSI); son 21 familias distintas (gap, MA200, FinBERT, OFI, CVD...). PBO asume N estrategias comparables rankeadas por la misma métrica. Si se rankea por Sharpe pero algunos diagnósticos nunca tuvieron equity curve, el proxy IC→Sharpe introduce ruido. **Mitigación preferida**: reconstruir las 21 como backtests con `backtest_engine.run` (misma ventana/costos/lag) aunque sea costoso (~21× 1 900 ruedas × 50 símbolos). Si no es viable en el slot, declarar la heterogeneidad como limitación del PBO medido.
2. **Autocorrelación y tamaño mínimo IS/OOS.** Cada partición ≈ 120 ruedas; cada split IS/OOS ≈ 960 ruedas (~8 particiones). Con S=16, el Sharpe por split tiene error estándar ≈ `1/√(n_días) ≈ 0.03` — suficiente, pero splits con pocas observaciones (si algún símbolo tiene huecos) pueden dar Sharpe ruidoso. **Mitigación**: exigir `n_días ≥ 60` por partición efectiva; si no, fallback a S=12.
3. **Overlap de ventanas forward.** Los ICs diagnósticos usan `fwd_return_20d` con stride 5d → overlap. El backtest usa barreras con horizonte variable (mediana 11d). Ambos introducen autocorrelación que Newey-West corrige en ICs pero que el Sharpe diario también sufre. **Mitigación**: usar retornos diarios de equity (ya autocorrelacionados de forma natural) y reportar `circular_block_bootstrap_ci` (T2.2) como intervalo del Sharpe, no solo el punto.
4. **N splits combinatorial explosion.** C(16,8)=12 870 es manejable (segundos). C(20,10)=184k sería costoso. S queda en 16.
5. **Lookahead del baseline.** El baseline limpio se calibró con datos 2019–2026; las particiones CSCV reutilizan esos datos. PBO no detecta lookahead de construcción del baseline (p. ej. `momentum_12_1` con 252d sin skip es una elección que ya vio los datos). **Mitigación**: documentar que PBO mide selección entre los 21 tal como existen hoy, no la "pureza" del baseline aislado.
6. **N_eff vs PBO.** N_eff 20–50 (reportado) corrige DSR por autocorrelación de retornos; PBO corrige por selección. Son ortogonales — un N_eff bajo no implica PBO alto ni viceversa. Se reportan ambos sin mezclarlos.
7. **Universo 50 con cross-section operable ~6 símbolos/día.** El rank IC intra-día real se mide sobre ~6 símbolos elegibles/día (no 50), ver `PLAN_MEJORA_MATEMATICA.md §8/0.5a`. Un PBO sobre Sharpe de equity ya incorpora ese filtro (solo se opera lo elegible), así que no hay inconsistencia, pero el lector no debe confundir "50 símbolos" con "50 apuestas independientes por día".

---

## 9. Checklist de no-ejecución — este documento se escribe ANTES de correr, no se edita después

- [x] Este archivo se creó **sin correr ningún backtest**, sin modificar el ledger, sin ejecutar `python` (solo lectura de artefactos y código).
- [x] El criterio de §4 (`PBO < 0.10` estricto, `≥0.20` overfitting) está sellado acá — **no se cambia al ver el número**. Si el PBO sale 0.18, no se re-etiqueta como "bueno porque <0.20"; se reporta como **zona gris** y **NO_CUMPLE** binario.
- [x] La lista N=21 de §6.1 está congelada al 2026-08-22 — no se agregan/quitan candidatos post-hoc para mover el PBO.
- [x] La métrica primaria (Sharpe anualizado) y S=16 están congeladas — no se prueban "otras métricas hasta que dé".
- [ ] **Al ejecutar (cuando se libere slot)**: correr `backend/scripts/pbo_cscv_mom_rsi.py` → artefacto `pbo_cscv_mom_rsi_*.txt` → `register_trial` con veredicto mecánico de §4 → actualizar `ROADMAP.md` y `PLAN_MEJORA_MATEMATICA.md` con el resultado (sin re-escribir este pre-registro). Si el script aborta por fidelidad (S insuficiente, Sharpe NaN), se documenta como **NO INTERPRETABLE**, no como NO_CUMPLE.
- [ ] **Prohibido**: editar este archivo después de correr para "alinear" el criterio con el resultado. Cualquier corrección metodológica requiere **nuevo pre-registro** (como se hizo con #16→#17 para M2).

---

## 10. Próximo paso cuando se libere slot

1. Asignar slot (Kilo/Cline/OpenCode libre) → implementar `backend/scripts/pbo_cscv_mom_rsi.py` según §3.3 y §7 (leer `trial_registry.json` para N real, particionar S=16, rankear 21 Sharpes por split, histograma de logits).
2. Correr **una sola vez** (sin re-corridas para "probar otro S"): `cd backend && .venv/bin/python -m scripts.pbo_cscv_mom_rsi` → artefacto `backend/data/cache/pbo_cscv_mom_rsi_*.txt`.
3. Veredicto mecánico de §4 → `register_trial(id="pbo_cscv_mom_rsi", familia="signal_diagnosis", n_trials_consumidos=1, umbral_aplicado="PBO<0.10 (Bailey et al.)", veredicto=CUMPLE|NO_CUMPLE, artefacto=..., seccion_doc="PRE_REGISTRO_PBO_CSCV_MOM_RSI.md")`.
4. Actualizar `ROADMAP.md` (fila PBO/CSCV → 🟢 cerrado con veredicto + artefacto) y `PLAN_MEJORA_MATEMATICA.md` (nueva § con resultado + interpretación). No editar este pre-registro.
5. Decisión del usuario: si PBO < 0.10 → el baseline sobrevive la auditoría de selección (no implica que sea rentable, solo que no es artefacto de haber mirado 21 cosas); si PBO ≥ 0.10 → el proceso de selección está sobreajustado — el baseline no se promueve y cualquier "mejor de 21" futuro exige validación OOS fresca.

---

*Fin del pre-registro — borrador en cola, no ejecutado. Próxima edición: solo para agregar el artefacto y el veredicto mecánico cuando se corra; el criterio de §4 no se toca.*
