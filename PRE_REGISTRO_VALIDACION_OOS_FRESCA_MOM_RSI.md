# PRE-REGISTRO — Validación OOS fresca del baseline momentum+RSI (definición EXACTA congelada)

**Fecha de pre-registro**: 2026-08-22
**Estado**: 🟢 EJECUTADO 2026-08-22 (corrida única) — veredicto mecánico **NO_CUMPLE** (apéndice al final; criterios §5 intactos)
**Autor**: OpenCode (ox-alpha) — tarea asignada por Boris 2026-08-22 tras PBO/CSCV N=21 = 0.4688 (NO_CUMPLE sustancial, `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md` §4 / PLAN_MEJORA_MATEMATICA.md §40)
**Referencias**: ONBOARDING.md reglas #1–#3 · PLAN_MEJORA_MATEMATICA.md §39/§40 · RESUMEN_STOP_ESTRUCTURAL.md (T1.4, no se toca) · Tarea L BH→BY (no se rehace, solo calibración)
**Regla de oro**: este documento se escribe ANTES de correr y NO se edita después de ver el número. La única edición posterior permitida es agregar el artefacto y el veredicto mecánico (§9).

---

## 1. Por qué esta prueba existe

El PBO/CSCV N=21 (§40) midió **overfitting de proceso**: elegir la mejor IS entre 21 trials no generaliza mejor que la mediana OOS. Eso NO dice que momentum+RSI pierda afuera — dice que el proceso selectivo no puede acreditarlo. La consecuencia declarada en §40 fue exacta: *"cualquier 'mejor de 21' futuro exige validación OOS fresca"*.

Esta ES esa validación, y su diseño anti-atajo es la razón de ser:

- **CERO re-optimización.** Los parámetros quedan CONGELADOS en la definición exacta de producción (`signal_engine.py`). Prohibido explícitamente: ajustar pesos w_mom/w_rsi al mejor Sharpe, mover la banda RSI al techo, o rebajar umbrales "para que pase". Eso sería cherry-picking post-hoc — exactamente lo que el PBO 0.4688 acaba de condenar.
- **Datos que el baseline nunca vio para seleccionarse.** El baseline se calibró/lockeó con datos ≤ 2023-12-31 (los trials W1/W2/W3 cubren hasta ahí; el updater acumula solo desde entonces). La ventana OOS fresca arranca 2024-01-01: datos que existían DESPUÉS de que la definición quedó congelada.

**H0 (nula)**: el baseline momentum+RSI con definición exacta NO tiene edge neto OOS fresco — Sharpe_OOS ≤ 0, o el Sharpe observado es indistinguible de cero una vez descontado el presupuesto de selección ya consumido (DSR < 0.95).
**H1 (alternativa)**: Sharpe_OOS > 0 Y DSR ≥ 0.95 sobre la ventana OOS fresca.

---

## 2. Definición EXACTA congelada — verificada contra el código, no contra resúmenes

Fuente única: `backend/app/core/signal_engine.py` + `backend/app/core/indicators.py`. El script NO hardcodea los pesos: los lee de `SignalEngine(...).factor_weights[0]`.

| Componente | Definición congelada | Fuente verificada |
|---|---|---|
| Pesos score | `w_mom = round(0.0637/(0.0637+0.0322), 4) = 0.6642`, `w_rsi = 0.3358` (priors IC-proporcionales; SIN BayesianOnlineUpdater — pesos fijos) | `signal_engine.py:85-90` |
| momentum_score | `clip((momentum_12_1 + 50)/150, 0, 1)`; `momentum_12_1 = close.pct_change(252)*100` — 252d SIN skip de 1m (nombre histórico "12-1") | `indicators.py:277`, `signal_engine.py:122-123` |
| rsi_score | `0.8 si 45 < rsi14 < 70 (estricto), sino 0.4` | `signal_engine.py:125-126` |
| Score total | `overall = w_mom*momentum_score + w_rsi*rsi_score`; señal requiere `overall >= 0.60` | `signal_engine.py:206,216` |
| Gates duros | `close > ema50 > ema200` · `adx14 >= 20` · `40 < rsi14 < 75` (estricto) · `volume_ratio >= 1.0` | `signal_engine.py:208-215` |
| Indicadores | ema50/ema200 EWM span adjust=False; rsi Wilder-simplificado rolling-mean 14; adx 14 según `indicators.adx`; volume_ratio = vol/SMA20(vol) | `indicators.py:7-49,266-298` |
| Universo | 50 canónico (`app/api/routes/opportunities_universe.SYMBOLS`) | Tarea F |
| Costos | `COST_PER_SIDE = 0.0005` + `slippage = 0.0005` → 0.001/lado, 0.002 ida-y-vuelta por mes con posiciones (convención conservadora full-rebalance, igual que §39/§40) | `config.py:53` |
| Ejecución | Señal decidida al cierre del último día de trading del mes m (solo datos ≤ fecha de decisión); entrada a OPEN del primer día hábil de m+1 (`execution_lag_days=1` fiel); salida a CLOSE del último día hábil de m+1 | `config.py:60` |
| Régimen/BMA/stops | NO simulados: sin regime-gate (regime_state≠3), sin stops/barriers, sin sizing Kelly ni caps de exposición. Pesos fijos prior (sin refinamiento online). **Limitación declarada** (igual que §39/§40): mide el EDGE de la señal congelada, no el P&L del motor completo | §8 |

**Checks de fidelidad al motor (estilo §39, anclados al código real)**:
- F1 — universo: 50/50 símbolos cargados del cache; abortar si falta alguno.
- F2 — score: la serie vectorizada del script debe ser IDÉNTICA (max|Δ| < 1e-12) a `SignalEngine.compute_score_series(df, regime_state=0)` en ≥3 símbolos de muestra.
- F3 — gates: la máscara elegible del script debe ser IDÉNTICA a `SignalEngine.compute_factor_frame(df)['eligible']` en los mismos símbolos.
- F4 — cobertura: ≥30% de los meses OOS efectivos con ≥1 señal.
- F5 — signo del edge bruto: retorno medio mensual BRUTO (ex-costos) sobre meses con señal > 0.
- F6 — T mínimo: si meses efectivos < 24 → NO CORRER; documentar fecha estimada de disponibilidad. (Esperado: T≈30.)

---

## 3. Ventana OOS fresca y embargo

- **Corte IS/OOS**: 2023-12-31. Todo lo ≤ corte es historia de calibración del baseline (prohibido usarlo para nada acá); todo lo ≥ 2024-01-01 es OOS fresco.
- **Ventana OOS nominal**: 2024-01-01 → última fecha completa disponible en cache. **Dato verificado hoy**: los 50 parquet terminan en **2026-08-14** (el updater de precios viene fallando desde ~2026-08-15 por `ModuleNotFoundError: No module named 'scripts'` — bug operativo reportado aparte; NO se descarga nada nuevo para esta corrida, prohibición explícita de la tarea).
- **Embargo de 20 ruedas** (`CALIBRATION_HORIZON_DAYS = 20`, `backtest_engine.py:23`): el primer retorno mensual OOS (enero-2024) proviene de decisiones tomadas 2023-12-29 cuyo forward return solapa el corte IS/OOS → **se descarta el retorno mensual de enero-2024 completo** (~21 ruedas ≥ 20). Desde febrero-2024 las decisiones usan exclusivamente datos post-corte.
- **Mes parcial final excluido**: agosto-2026 está cortado a 2026-08-14 (~mitad de mes) → su retorno tendría horizonte ≠ mensual. Se excluye.
- **Ventana OOS efectiva**: retornos mensuales **2024-02 → 2026-07 = 30 meses** (T=30). Decisiones tomadas entre 2024-01-31 y 2026-06-30, todas con datos post-corte+embargo.

---

## 4. Métrica primaria — Sharpe NETO + DSR de Bailey

- **Retorno mensual del portafolio** (equal-weight, aproximación vectorizada declarada):
  - Snapshot al cierre del último día de trading del mes m; señal por símbolo i si gates + score ≥ 0.60 con datos ≤ ese día.
  - `ret(m+1) = media_i [ close_{m+1,i} / open_{m+1,i} − 1 ]` sobre símbolos señalados en m (entrada a open = lag 1 fiel); sin señales → 0 (cash).
  - Neto = bruto − 0.002 si hubo ≥1 posición en el mes (convención §39/§40, conservadora).
- **Sharpe_OOS** = mean/std(ddof=1) × √12 sobre los T=30 retornos mensuales NETOS (incluyendo meses cash — convención §39/§40).
- **DSR (Bailey & López de Prado 2014, "The Deflated Sharpe Ratio", JoPM)** — implementación fiel en frecuencia NATIVA (mensual, no anualizada):

  ```
  SR_hat = mean/std(ddof=1) mensual
  γ3 = skewness muestral; γ4 = kurtosis Pearson (= exceso + 3)
  denom = sqrt( max(1 − γ3·SR_hat + ((γ4−1)/4)·SR_hat², eps) )
  E_max(N_eff) = (1−γ_euler)·Φ⁻¹(1 − 1/N_eff) + γ_euler·Φ⁻¹(1 − 1/(N_eff·e)),  γ_euler ≈ 0.5772
  SR0 = sqrt(V[SR_n]) · E_max(N_eff)
  DSR = Φ( (SR_hat − SR0) · sqrt(T−1) / denom )
  ```

  - **N_eff = consumed_budget("signal_diagnosis") leído del ledger AL MOMENTO DE CORRER** (≥21; hoy 22 porque §40 itself consumió uno — más conservador: mayor SR0, DSR más difícil). Nunca menor al valor del ledger.
  - **V[SR_n]** (varianza ENTRE trials de los Sharpe candidatos): no hay 21 Sharpes OOS comparables reconstruibles sin re-correr el vecindario (y re-correrlo violaría el freeze). Se adopta el proxy **conservador ya auditado del repo (Fase 0b, `backtest_engine.calculate_metrics`)**: V[SR_n] := varianza del ESTIMADOR = denom²/(T−1). Con este proxy la fórmula canónica reduce EXACTAMENTE a la implementación en uso del repo (`DSR = Φ((SR − sr_std·E_max)/sr_std)`) → el DSR aquí es directamente comparable con todos los W1/W2/W3 históricos. Conservador: sr_std mensual ≈ 0.18–0.19 >> dispersión cross-trial observada en §40 (~0.05 mensual) → infla SR0 y castiga el DSR.
- **Secundaria (reportada, no gate)**: CI 95% del Sharpe anualizado por bootstrap de bloques circulares (`probabilistic_engine.circular_block_bootstrap_ci`, bloque 3 meses, 1000 reps, seed 42 — autocorrelación mensual preservada).

## 5. Criterio pre-registrado — binario, SIN zona gris

| Resultado | Veredicto | Consecuencia |
|---|---|---|
| **Sharpe_OOS > 0 Y DSR ≥ 0.95** | **CUMPLE** | El edge sobrevive datos frescos con corrección por 20+ trials. Habilita (no ejecuta) un trial formal W1/W2/W3 del motor completo como siguiente paso. |
| **Cualquier otra cosa** (Sharpe ≤ 0, o DSR < 0.95, o fidelidad fallida) | **NO_CUMPLE** | No se promueve nada. El baseline queda NO promovible sin rediseño; el resultado se registra tal cual, sin reinterpretación. |

- Sin zona gris a propósito: después de un PBO 0.4688 sustancial, la barra para afirmar "hay edge fresco" debe ser alta y simple.
- Fidelidad fallida (F1–F6) → corrida **NO INTERPRETABLE**, se documenta como tal (no cuenta como NO_CUMPLE de la hipótesis).
- El veredicto al ledger es MECÁNICO: sale de la tabla de arriba, sin reinterpretar.

## 6. Artefacto, script y ledger — rutas congeladas

| Ítem | Ruta |
|---|---|
| Script | `backend/scripts/validacion_oos_fresca_mom_rsi.py` |
| Ejecución (UNA sola vez) | `cd backend && .venv/bin/python -m scripts.validacion_oos_fresca_mom_rsi` |
| Artefacto | `backend/data/cache/validacion_oos_fresca_mom_rsi_<ts>.txt` + `.json` |
| Ledger | `trial_registry.register_trial(id="validacion_oos_fresca_mom_rsi", familia="signal_diagnosis", n_trials_consumidos=1, umbral_aplicado="Sharpe_OOS>0 Y DSR>=0.95 (Bailey&LdP2014, N=ledger signal_diagnosis)", veredicto=CUMPLE\|NO_CUMPLE, seccion_doc="PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md §5")` |
| Determinismo | seed 42; sin RNG salvo el bootstrap CI (seed fija); lectura determinista del cache |
| Datos | SOLO `backend/data/cache/*.parquet` existente — sin descargas nuevas (tarea explícita) |

## 7. Riesgos y limitaciones — declarados ANTES de correr

1. **T corto (T=30 meses)** → error estándar del Sharpe anualizado ≈ √(12/T) ≈ 0.63: un Sharpe verdadero de ~1 podría medirse entre ~0.4 y ~1.6. El DSR con N_eff alto compensa parcialmente (exige mucho), pero el IC es ancho — por eso el CI bootstrap es obligatorio en el reporte. Si T hubiera quedado <24: NO correr y documentar fecha estimada de disponibilidad.
2. **Aproximación portafolio equal-weight mensual vs motor completo**: sin stops ATR/barrera, sin regime-gate (regime_state=3 bloquearía todo), sin sizing Kelly, sin caps de exposición, sin BMA online. Mide el EDGE de la señal congelada; NO certifica el P&L del motor. Un CUMPLE habilita el trial formal del motor; no lo reemplaza.
3. **Costo conservador full-rebalance** (0.002/mes con posiciones aunque el set de símbolos cambie poco) castiga el neto — dirección conservadora, declarada.
4. **Cache estancado a 2026-08-14** (bug del updater detectado hoy, reportado): la ventana OOS termina ahí. No se descarga nada nuevo para esta corrida. Un refresh posterior NO invalida este pre-registro pero tampoco lo extiende — otra ventana exigiría otro pre-registro.
5. **V[SR_n] proxy**: documentada en §4; es la convención auditable del repo y conservadora en la dirección correcta.
6. **No editar este documento después de correr.** Correcciones metodológicas → nuevo pre-registro (precedente #16→#17).
7. **Prohibido el atajo** (re-declaración expresa de la tarea): ajustar pesos al mejor Sharpe, mover banda RSI al techo, rebajar umbrales. Congelás parámetros y medís OOS fresco — eso es todo.

## 8. Qué NO hace esta validación

- No revoca ni promueve el baseline por sí misma: CUMPLE → habilita trial formal del motor completo; NO_CUMPLE → confirma que no hay base para promover.
- No toca T1.4 / RESUMEN_STOP_ESTRUCTURAL (informativo, cerrado).
- No rehace Tarea L (BH→BY, calibración).
- No modifica `signal_engine.py`, `backtest_engine.py`, config ni ningún parámetro de producción.

## 9. Checklist de no-ejecución

- [x] Escrito ANTES de correr: sin backtests, sin tocar el ledger, sin ejecutar python sobre datos.
- [x] Criterio §5 sellado — no se cambia al ver el número.
- [x] Definición §2 congelada contra el código real (verificado línea por línea hoy).
- [x] Ventana §3 congelada (incluye embargo 20 ruedas y exclusión del mes parcial).
- [ ] Al ejecutar: correr UNA vez → artefacto `.txt/.json` → `register_trial` veredicto mecánico → ROADMAP + SESSION_LOG. Este doc solo recibe el apéndice de resultados.
- [ ] Prohibido editar criterios post-corrida.

---

*Fin del pre-registro — borrador sellado 2026-08-22 antes de cualquier corrida.*

---

## APÉNDICE DE RESULTADOS — corrida única 2026-08-22 15:55 (única edición permitida por §9; criterios de §5 intactos)

**Ejecución**: `cd backend && .venv/bin/python -m scripts.validacion_oos_fresca_mom_rsi` — UNA sola corrida, 19.3s, sin re-corridas ni ajustes.
**Artefacto**: `backend/data/cache/validacion_oos_fresca_mom_rsi_20260822_155520.txt` + `.json`.

### Checks de fidelidad §2 — TODOS OK

| Check | Resultado |
|---|---|
| F1 universo | **50/50 símbolos** cargados del cache (sin descargas) |
| F2 score vs motor | max\|Δscore\| = **0.000e+00** vs `SignalEngine.compute_score_series` (SPY, AAPL, NVDA; 2669 filas c/u) — idéntico |
| F3 gates vs motor | **0 mismatches** vs `SignalEngine.compute_factor_frame['eligible']` en las mismas muestras |
| F4 cobertura | 26/30 meses con ≥1 señal = **86.7%** (min 30%) |
| F5 edge bruto ex-costos | **+0.0237/mes** sobre meses con señal (positivo) |
| F6 T mínimo | T=30 meses efectivos ≥ 24 → se corrió |

Ventana efectiva: **2024-02 → 2026-07, T=30 meses** (embargo descartó retorno mensual 2024-01; mes parcial 2026-08 excluido; cache termina 2026-08-14).

### Resultado primario §5

| Métrica | Valor |
|---|---|
| **Sharpe_OOS anualizado NETO** | **+1.3296** (> 0 ✓) |
| Sharpe mensual nativo | +0.383816 |
| CI 95% bootstrap bloques circulares (bloque 3m, seed 42) | [+0.3736, +2.3237] — no incluye 0 |
| Retorno acumulado neto OOS | +69.37% en 30 meses |
| **DSR Bailey & LdP 2014** (N_eff=22 ledger, T=30) | **0.6077** (< 0.95 ✗) |
| Insumos DSR | skew 0.8075 · kurt Pearson 5.8946 · E_max 1.9423 · SR0 0.3365 · V[SR_n]=3.001e−02 (proxy conservador repo) |

### VEREDICTO MECÁNICO §5: **NO_CUMPLE**

Sharpe_OOS > 0 pero DSR 0.6077 < 0.95 → NO_CUMPLE. Sin reinterpretación: el edge bruto observado es positivo y su IC no incluye cero, PERO tras descontar el presupuesto de selección ya consumido (22 trials de la familia) y con solo T=30 meses y colas gruesas (kurtosis 5.9), la evidencia no alcanza la barra pre-registrada para afirmar "edge fresco confirmado". **Nada se promueve.** El baseline sigue NO promovible; un eventual trial formal W1/W2/W3 del motor completo seguiría siendo la única vía de promoción, y esta validación NO lo habilita bajo el criterio sellado.

**Ledger**: `signal_diagnosis` 22→23 — `id=validacion_oos_fresca_mom_rsi`, n=1, umbral `Sharpe_OOS>0 Y DSR>=0.95 (Bailey&LdP2014, N=ledger signal_diagnosis)`, veredicto **NO_CUMPLE**, artefacto arriba, sección §5 de este doc.

**Lectura honesta (sin tocar el veredicto)**: el contraste con el PBO 0.4688 es informativo — el proceso de selección estaba sobreajustado, pero la definición congelada muestra su mejor desempeño histórico precisamente en los datos frescos post-lockeo (+1.33 vs Sharpe_full ~+0.93 medido en §40). Es consistente con §39: riesgo de GRADO (cuán bueno), no de EXISTENCIA (si hay algo). Con más meses de datos acumulándose por el updater, este mismo pre-registro puede repetirse con nuevo documento (no editando este) cuando T crezca — el DSR escala con √T y hoy fue el factor limitante junto a las colas gruesas.
