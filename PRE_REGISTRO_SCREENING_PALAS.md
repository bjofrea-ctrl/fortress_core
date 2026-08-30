# PRE-REGISTRO — Screening "vendedor de palas": separación IA-habilitadores vs resto del universo

**Fecha de pre-registro**: 2026-08-26
**Estado**: 🟡 BORRADOR — NO EJECUTADO (documento para aprobación de Boris)
**Autor**: OpenCode (gentle-orchestrator) — draft para Boris, a la espera de aprobación explícita
**Referencia**: ONBOARDING.md reglas #1–#3 · ARBOL_DECISION_ESTRATEGICO.md (capa n, "vendedor de palas") · PRE_REGISTRO_PBO_CSCV_MOM_RSI.md (formato y familias)
**Regla de oro**: este documento se escribe ANTES de correr y NO se edita después de ver el número. Ningún backtest corre sin aprobación explícita de Boris (regla #1 ONBOARDING.md).

---

## 1. Hipótesis

**Idea (de ARBOL_DECISION_ESTRATEGICO.md, capa n)**: en un boom ("la ola"), los "vendedores de palas" — los que habilitan la tendencia sin ser los que cabalgan el hype directo — pueden mostrar un perfil de riesgo/retorno distinguible del resto del mercado. Aplicado a IA: los habilitadores de infraestructura (semiconductores, cloud, networking) pueden tener un perfil de señal momentum+RSI distinto del resto del universo.

**H0 (nula)**: el subconjunto etiquetado como "habilitador IA / pala de la ola" **NO** muestra separación de riesgo/retorno distinguishable del resto del universo bajo la señal de producción (momentum+RSI, definición congelada). Cualquier diferencia observada es ruido muestral.

**H1 (alternativa — falsable)**: el subconjunto "habilitador IA" muestra **separación real**: mejor Sharpe anualizado Y mejor DSR que el subconjunto "resto" en al menos 2 de 3 ventanas walk-forward (W1/W2/W3).

> **Clasificación explícita**: este es un **screening barato** (escalón 1 del embudo), NO un backtest confirmatorio. Su único trabajo es responder "¿hay separación suficiente para justificar el paso 2?". Si la respuesta es no, el concepto queda documentado como "screened out" y NO se inyecta al motor.

---

## 2. Subconjuntos a comparar

### 2.1. Universo canónico (50 símbolos — inalterado)

Fuente: `backend/app/api/routes/opportunities_universe.SYMBOLS` (Tarea F, canónico desde trial_11_universo50). No se modifica el universo para este screening.

### 2.2. Etiquetado "habilitador IA" (subconjunto PALA)

| Símbolo | Rol en cadena IA |
|---|---|
| **NVDA** | GPUs / cómputo IA (dominante) |
| **AVGO** | ASICs + infraestructura red IA |
| **QCOM** | Chips edge/mobile IA + modem |
| **MSFT** | Cloud (Azure) + Copilot (demanda dual: habilitador Y hipster — se incluye por peso en cómputo cloud) |
| **ORCL** | Cloud + DBs para entrenamiento IA |
| **CSCO** | Networking / switches data-center (infraestructura física IA) |

**N_PALA = 6** símbolos. Etiquetado a mano por Boris/criterio de capa n (NO es endógeno al motor, NO se optimiza — es la hipótesis externa que se quiere testear).

### 2.3. Subconjunto RESTO = universo 50 − PALA

**N_RESTO = 44** símbolos. Todo lo que no está en la tabla 2.2.

### 2.4. Subconjunto POOLED (control)

Los 50 símbolos juntos — es el baseline actual (mismo artefacto `baseline_clean_20260811_150643.*`). Sirve para verificar que la señal sigue comportándose igual en el agregado.

---

## 3. Método — comparación de 3 corridas del motor con datos filtrados

 ### 3.1. Principio

 El motor (`BacktestEngine.run`) recibe `price_data` (OHLC por símbolo) y `market_data` (series para el HMM de régimen), y construye `indicators_cache` internamente vía `calculate_all_indicators` (`backtest_engine.py:299`). **No** recibe un `indicators_cache` externo.

 Para cada subconjunto (PALA, RESTO, POOLED) se corre **la misma pipeline idéntica** con `price_data` filtrado a los símbolos del subconjunto. La señal, los gates, los costos, los stops, el execution_lag — todo congelado. Lo único que cambia es **sobre qué símbolos se evalúa el price_data**.

 **Reglas de filtrado (verificadas contra `backtest_engine.py`)**:

 - **`price_data`**: filtrado al subconjunto (PALA=6, RESTO=44, POOLED=50). El motor construye `indicators_cache` a partir de él (línea 299), así que los indicadores se calculan solo sobre los símbolos del subconjunto.
 - **`market_data`**: pasa **INTEGRO** (los 50 símbolos) en las 3 corridas. Motivo: `market_data` alimenta el `GlobalRegimeClassifier.fit()` (líneas 308-309, entrenado con datos pre-`start_date`) y el loop de fechas vía SPY (líneas 345-346). Filtrarlo contaminaría la clasificación de régimen y el calendario de trading, invalidando la comparación PALA vs RESTO.
 - **Instancia fresca**: cada corrida (PALA, RESTO, POOLED) usa su **propia instancia** de `BacktestEngine`. Motivo: `regime_classifier`, `bayesian_updater` y `signal_engine` son estado de instancia que `run()` muta (fit del HMM, updates BayesianOnlineUpdater, calibrador). Compartir instancia entre corridas contaminaría el estado.
 - **Ventanas**: `start_date`/`end_date` definen la ventana de evaluación, pero `price_data` debe incluir el historial completo desde 2019 (pre-ventana) para que el warm-start del calibrador (línea 334-336) y el fit del régimen (línea 308-309) tengan datos suficientes. No se usa `train_end_date` para recortar price_data — se pasa todo y el motor hace el split internamente.

### 3.2. Parámetros congelados (idénticos al baseline)

| Parámetro | Valor congelado | Fuente |
|---|---|---|
| Score | `w_mom=0.6642, w_rsi=0.3358`, `score = w_mom*mom + w_rsi*rsi` | `signal_engine.py:85-90` |
| momentum_score | `clip((pct_change(252)*100 + 50)/150, 0, 1)` | `indicators.py:277`, `signal_engine.py:122-123` |
| rsi_score | `0.8 si 45<rsi14<70 sino 0.4` | `signal_engine.py:125-126` |
| Gates duros | `close>ema50>ema200`, `adx14>=20`, `40<rsi14<75`, `volume_ratio>=1.0`, `score>=0.60` | `signal_engine.py:206-217` |
| Universo | **Filtrado**: PALA (6), RESTO (44), POOLED (50) | `opportunities_universe.SYMBOLS` |
| Ventanas | **W1** 2020-2021, **W2** 2022-2023, **W3** 2024-2026-08-04 | `PLAN_MEJORA_MATEMATICA.md §0.6.1` |
| Costos | `COST_PER_SIDE=0.0005`, `slippage=0.0005` | `config.py:46-53` |
| execution_lag | 1 día (`EXECUTION_LAG_DAYS=1`) | `config.py:60` |
| Stops/barriers | 2x ATR (default `AdaptiveRiskManager`) | `adaptive_risk.py` |
| Horizonte forward | `CALIBRATION_HORIZON_DAYS=20` | `backtest_engine.py:23` |
| n_trials (para DSR) | `DEFAULT_N_TRIALS=5` (default del motor, NO se overridea) | `backtest_engine.py:593` |
| Datos | Solo `backend/data/cache/*.parquet` existente — sin descargas | |

### 3.3. Métricas primarias por subconjunto y ventana

Por cada subconjunto (PALA, RESTO, POOLED) y cada ventana (W1, W2, W3):

| Métrica | Cálculo | Fuente |
|---|---|---|
| **Sharpe anualizado** | `mean/std(ret_diarios) × √252` | `backtest_engine.calculate_metrics` línea 604 |
| **DSR (Deflated Sharpe)** | Bailey & LdP 2014, frecuencia diaria nativa, skew+kurt reales, `n_trials=5` | `backtest_engine.calculate_metrics` línea 616-640 |
| n_trades | Total de trades en la ventana | piso mínimo: ≥30 trades/ventana para ser evaluable |

### 3.4. Comparación exacta

La tabla de salida tiene 3 filas × 3 columnas:

| | W1 (2020-2021) | W2 (2022-2023) | W3 (2024-2026-08) |
|---|---|---|---|
| **PALA (6)** | Sharpe, DSR, n_trades | Sharpe, DSR, n_trades | Sharpe, DSR, n_trades |
| **RESTO (44)** | Sharpe, DSR, n_trades | Sharpe, DSR, n_trades | Sharpe, DSR, n_trades |
| **POOLED (50)** | Sharpe, DSR, n_trades | Sharpe, DSR, n_trades | Sharpe, DSR, n_trades |

**Lectura**: para cada ventana, se compara PALA vs RESTO. Si PALA tiene **ambas** métricas por encima (Sharpe Y DSR), cuenta como una "victoria" de PALA. Se necesitan **≥2/3 ventanas con victoria PALA** para CUMPLE.

---

## 4. Criterio de éxito / fracaso — PRE-REGISTRADO y explícito

> Compromiso sellado ANTES de correr (ONBOARDING.md regla #1). No se toca después de ver los números.

### 4.1. Criterio primario (separación PALA > RESTO)

| Resultado | Veredicto | Interpretación |
|---|---|---|
| **PALA supera RESTO en Sharpe Y DSR en ≥2/3 ventanas** (Y PALA tiene DSR > 0.50 en esas ventanas, Y ≥30 trades/ventana en las evaluables) | **CUMPLE** | Hay separación real: el subconjunto habilitador muestra un perfil de señal distinguible y mejor. Justifica (no ejecuta) el paso 2: backtest confirmatorio inyectando el etiquetado PALA como factor/filtro en el motor. |
| **PALA supera RESTO en 2/3 ventanas pero DSR ≤ 0.50 en ambas, o <30 trades** | **ZONA GRIS** — se reporta como NO_CUMPLE binario pero se documenta la limitación | Separación visible pero sin fuerza estadística; o muestra insuficiente. No promueve. |
| **PALA NO supera RESTO en ≥2/3 ventanas** | **NO_CUMPLE** | No hay separación. El etiquetado "vendedor de palas" NO distingue comportamiento de señal bajo momentum+RSI. Concepto screened-out. |

### 4.2. Criterios secundarios (informativos, NO gate)

- **POOLED vs baseline histórico (check de sanidad con tolerancia numérica)**: la corrida POOLED debe replicar aproximadamente el baseline_clean (`DSR 0.0714/0.0284/0.1727`, `Sharpe 0.2562/-0.0542/0.5299` en W1/W2/W3). Para distinguir bug de ruido muestral, las tolerancias son:

  | Métrica | Tolerancia vs baseline_clean (por ventana) |
  |---|---|
  | **\|ΔDSR\|** | **≤ 0.05** |
  | **\|ΔSharpe\|** | **≤ 0.15** |

  - Si POOLED está **dentro** de ambas tolerancias en ≥2/3 ventanas → implementación correcta, sigue el gate normal.
  - Si POOLED está **fuera** de cualquiera de las tolerancias en ≥2/3 ventanas → posible bug de implementación → **NO INTERPRETABLE** (se documenta, se investiga, se corrige el script y se congelan nuevas tolerancias en un pre-registro nuevo antes de re-correr). Este check es **de una sola vía**: si POOLED diverge, se declara NO_INTERPRETABLE y se PARA — no se "ajustan" PALA/RESTO para compensar. Esto evita el p-hacking encubierto (declarar divergencia post-hoc para re-correr cuando PALA sale mal).
  - Las tolerancias se fijaron así: DSR tiene error estándar ≈ `√(p(1-p)/n)` que con n≈100 trades/ventana y DSR~0.10 da ≈0.03-0.04; Sharpe anualizado con ~250 rudas tiene SE ≈ 0.15-0.20. Se redondea hacia arriba para no falsos positivos de bug.

- **Dirección del DSR**: si DSR PALA > DSR RESTO en las 3 ventanas aunque no crucen el umbral 0.50 — se reporta como tendencia, no como victoria.
- **Robustez n_trades**: si PALA tiene <30 trades en una ventana, esa ventana se marca "no evaluable" y el criterio pasa a exigir 2/2 ventanas evaluables (o 2/3 si solo una es no-evaluable).

### 4.3. Umbral DSR > 0.50 — justificación

- El umbral estricto del proyecto es DSR ≥ 0.90 (BASE_THRESHOLD, `trial_registry.py:31`).
- Este screening es **exploratorio por diseño** (escalón 1 del embudo). Exigir DSR ≥ 0.90 a un subconjunto de 6 símbolos con probablemente <100 trades/ventana sería un falso negativo casi garantizado (el DSR castiga duro con n pequeño y colas gruesas).
- **DSR > 0.50** = "el Sharpe observado está por encima del SR_0 esperado bajo H0 para n_trials=5" — es evidencia **débil pero direccional**, suficiente para un screening. Si el screening pasa, el paso 2 (backtest confirmatorio con inyección real del factor) exigirá el umbral estricto DSR ≥ 0.90 con el presupuesto Bonferroni correspondiente.
- Este es el motivo por el que el screening es BARATO: su trabajo es reducir el espacio de búsqueda, NO confirmar que un factor es tradeable.

### 4.4. Binario para el ledger

- **CUMPLE** si PALA > RESTO en Sharpe Y DSR en ≥2/3 ventanas, DSR > 0.50 en esas ventanas, ≥30 trades evaluables.
- **NO_CUMPLE** en cualquier otra situación.

---

## 5. Datos — todos ya existentes

| Dónde | Qué | Estado |
|---|---|---|
| `backend/data/cache/*.parquet` | OHLC diario 50 símbolos, 2019-01-01 → 2026-08-14 | Existente (updater estancado en 2026-08-14, reportado aparte — NO se descarga nada nuevo) |
| `backend/app/api/routes/opportunities_universe.SYMBOLS` | Lista 50 símbolos canónicos | Existente |
| `backend/data/cache/baseline_clean_20260811_150643.*` | Corrida pooled de referencia | Existente |

**No requiere**: nuevas fuentes, nuevos símbolos, APIs externas, descargas. Todo está en el cache existente.

---

## 6. Familia de ledger y presupuesto

### 6.1. Familia elegida: `signal_diagnosis`

**Justificación**: este screening es un **diagnóstico comparativo de señal** — mide cómo se comporta la señal de producción (congelada, sin tocar) sobre subconjuntos predefinidos del universo. No inyecta un factor nuevo al motor (eso sería `motor_signal`). No es un backtest con costos de un hallazgo (eso sería `backtest_costos`). Es exactamente lo que `signal_diagnosis` describe: "rank IC intra-dia, RMT, horizontes, sub-periodos" — diagnóstico de señal bajo distintas particiones.

**Por qué NO `motor_signal`**: `motor_signal` es para inyectar una variable/score nueva al motor y medir DSR OOS (sentimiento, fundamentales, ridge, abstencion, etc.). Aquí el score NO cambia — solo se filtra el universo. Es análogo a un diagnóstico de sub-periodos (como `rr2_subperiodos` o `ma200_clusters`), no a una inyección de factor.

**Por qué NO una familia nueva**: crear una familia para un screening que es conceptualmente idéntico a un diagnóstico de sub-periodos añade complejidad al ledger sin ganar resolución. Si en el futuro hay screenings de otro tipo (p.ej. por sector, por market-cap), se puede reconsiderar — pero hoy `signal_diagnosis` lo captura fielmente.

### 6.2. Presupuesto

> **Fuente autoritativa**: `~/Desktop/fortress_core/backend/data/trial_registry.json` (copia de producción, main). La copia local del worktree (`test-opencode-orca`) está desactualizada porque `trial_registry.json` es **gitignored** y no se sincroniza entre worktrees.

| | Valor |
|---|---|
| Familia | `signal_diagnosis` |
| Consumido actual (producción, 2026-08-26) | **26** trials (ver §6.3) |
| Threshold actual (este trial debe superar) | **0.996296** (1 − 0.10/27) |
| Este trial consumiría | **n_trials_consumidos = 1** (26 → 27) |
| Threshold post-corrida (para el SIGUIENTE trial) | **0.996429** (1 − 0.10/28) |
| umbral_aplicado (registro) | `"DSR_PALA>0.50 Y Sharpe_PALA>Sharpe_RESTO en >=2/3 ventanas (screening barato, escalon 1 embudo)"` |

### 6.3. Lista de los 26 trials `signal_diagnosis` ya consumidos en producción (congelada al 2026-08-26)

1. `fase05a_rr2_intraday` · 2. `fase05b_rmt` · 3. `fase05c_ridge_macro_crudo` · 4. `sectorial_endogeno` · 5. `reeval_trial14` · 6. `gap_reversion_diag` · 7. `rr2_subperiodos` · 8. `ma200_clusters` · 9. `donchian` · 10. `ma200_beta_control` · 11. `horizon_audit_5d_10d` · 12. `horizon_largo_60d_125d` · 13. `lead_lag_diag` · 14. `triple_barrier_retest` · 15. `adx_walkforward` · 16. `weekly_indicators_2026` · 17. `finbert_sentiment_eventstudy` · 18. `xsec_relative_and_aaii_timing` · 19. `trial_macd_bollinger` · 20. `trial_ofi_proxy` · 21. `trial_cvd_proxy` · 22. `pbo_cscv_mom_rsi` · 23. `validacion_oos_fresca_mom_rsi` · 24. `regime_gating_p` · 25. `trial_frog_in_the_pan` · 26. `trial_kama_hma_supertrend`

---

## 7. Qué NO hace este screening (deliberadamente)

- **NO toca `signal_engine.py`** — el score (w_mom, w_rsi, momentum_score, rsi_score, gates) queda idéntico.
- **NO toca `opportunities_universe.py` / `NEW_UNIVERSE`** — el universo canónico no se modifica.
- **NO inyecta el etiquetado PALA como factor** — eso es el paso 2 (backtest confirmatorio condicional).
- **NO es el backtest confirmatorio caro** — este screening NO puede "probar" que el etiquetado PALA es tradeable. Solo puede decir "hay separación suficiente para justificar el estudio caro" o "no la hay".
- **NO modifica el ledger** — `trial_registry.json` no se toca hasta que se corra con aprobación explícita.
- **NO descarga datos nuevos** — trabaja 100% con el cache existente.

---

## 8. Riesgos y limitaciones — declarados ANTES de correr

1. **N_PALA = 6 es muy chico**: con 6 símbolos y el filtro de elegibilidad del motor (~6 símbolos/día operable), la mayoría de los días NO habrá señal en el subconjunto PALA (todos los 6 compiten por ~6 slots, pero además cada uno debe pasar los gates). Consecuencia: **n_trades PALA será bajo, probablemente <50 trades/ventana, quizás <30 en alguna** → ventana no evaluable. **Mitigación**: reportar n_trades explícitamente; si <2 ventanas son evaluables, el screening es **NO INTERPRETABLE** (no NO_CUMPLE — no alcanzó evidencia). **Implicación honesta**: un CUMPLE con N=6 es exigente por diseño (hay que superar el ruido con muestra chica).

2. **DSR con n_trials=5 es un gate LAXO (no conservador) para este screening**: el DSR usa `DEFAULT_N_TRIALS=5` (default del motor). El DSR penaliza por múltiples comparaciones: a **menor** n_trials → **menor** SR_0 (el Sharpe esperado bajo H0) → **mayor** DSR → gate **más fácil**, más permisivo. El "n_trials real" de este screening es mucho mayor que 5 (estamos mirando una partición del universo que no es independiente de las 26 pruebas previas de la familia). Si corrigiéramos por el presupuesto real (n=26+), SR_0 subiría, el DSR bajaría, y el gate sería **más difícil**. **Consecuencia honesta**: usar n_trials=5 hace que sea **más fácil** superar el umbral DSR > 0.50 de lo que sería con la corrección real. Esto es **intencional por diseño** — es un screening barato (escalón 1 del embudo), no una confirmación. Los falsos positivos que este gate laxo deje pasar los absorbe el paso 2 (backtest confirmatorio con Bonferroni real de la familia, threshold ≥ 0.996). Lo que este screening NO puede hacer es dar por confirmado nada que no sobreviva la corrección real.

3. **Etiquetado PALA no es independiente del motor**: los 6 símbolos fueron etiquetados por criterio externo (capa n, "vendedor de palas"), no por el motor. Pero el motor ya OPERABA sobre ellos (están en el universo 50). **Consecuencia**: el screening mide "¿la señal de producción funciona distinto sobre estos 6?" — NO "¿estos 6 son buenos per se". Si la señal funciona igual en PALA y RESTO, el etiquetado no añade valor. Si funciona distinto, hay una pista.

4. **MSFT y ORCL son "doble juego"**: son habilitadores (cloud) Y hipsters (Copilot, apps IA). Pueden comportarse más como "caballo de la ola" que como "pala". **Consecuencia**: si PALA "gana" pero el driver es MSFT/ORCL por su faceta de hipster, la lectura "vendedor de palas" se debilita. **Mitigación**: reportar contribución por símbolo si n_trades lo permite (análisis post-screening, no gate).

5. **Ventana W3 (2024-2026) es donde IA explotó**: si hay separación, es muy probable que aparezca solo en W3 (el boom IA post-ChatGPT). W1 y W2 (2020-2023) son pre-boom para la mayoría de estos nombres. **Consecuencia**: un resultado donde PALA solo supera en W3 (1/3) es **NO_CUMPLE** bajo el criterio pre-registrado (exige ≥2/3). Esto es correcto: queremos separación que no sea puramente "el último año de hype".

6. **No controla por sector**: PALA está concentrada en semiconductores/cloud. Si PALA > RESTO, puede ser "semiconductores > resto" (conocido) y no "habilitadores IA > resto". **Consecuencia**: el screening NO distingue "efecto sector" de "efecto habilitador". **Mitigación**: si CUMPLE, el paso 2 (confirmatorio) debe controlar por sector (comparar PALA vs otros semiconductores, no vs todo el resto). Esto se documenta como limitación, no como gate.

7. **Hindsight bias (sesgo de retrospectiva) en el etiquetado PALA**: los 6 símbolos se eligieron en **2026 SABIENDO** quiénes fueron los ganadores del boom de IA. NVDA subió >1000% desde 2022; AVGO, MSFT, QCOM también revalorizaciones masivas. La taxonomía "habilitador IA" se escribió **mirando el retrovisor**. **Consecuencia crítica**: un CUMPLE **NO** puede leerse como "los habilitadores de IA tienen mejor perfil de señal en general". Solo puede leerse como "estos 6 ganadores **ya conocidos** rindieron distinto bajo momentum+RSI". El screening no dice nada sobre si habría funcionado etiquetarlos **antes** del boom (2019-2020) o sobre si funcionaría con habilitadores de la próxima ola (quantum, edge-AI, etc.). **Implicación honesta**: el máximo resultado accionable de un CUMPLE es "justifica estudiar el paso 2 con estos 6 símbolos específicos" — NO "la taxonomía vendedor-de-palas es predictiva". Para que la taxonomía sea predictiva haría falta un test prospectivo (etiquetar hoy, evaluar en 2-3 años), que es un proyecto distinto.

---

## 9. Artefacto, script y ledger — rutas congeladas

| Ítem | Ruta / nombre pre-registrado |
|---|---|
 | **Script** | `backend/scripts/screening_palas.py` — instancia 3 `BacktestEngine` frescas, corre cada una con `price_data` filtrado al subconjunto (PALA/RESTO/POOLED) y `market_data` intacto, escribe tabla 3×3 comparativa (§3.1). |
 | **Ejecución** | `cd backend && .venv/bin/python -m scripts.screening_palas` — **UNA sola vez**, sin re-corridas. |
 | **Artefacto** | `backend/data/cache/screening_palas_<YYYYMMDD_HHMMSS>.txt` + `.json` con la tabla 3×3 (subconjunto × ventana) de Sharpe/DSR/n_trades. |
 | **Ledger (llamada real)** | `trial_registry.register_trial({id="screening_palas", fecha="<YYYY-MM-DD de corrida>", familia="signal_diagnosis", hipotesis="Screening vendedor de palas: subconjunto habilitador IA (NVDA/AVGO/QCOM/MSFT/ORCL/CSCO) vs resto (44) vs pooled (50) bajo momentum+RSI congelado. n_trials=5 (default motor, gate laxo por diseño escalon 1).", n_trials_consumidos=1, umbral_aplicado="DSR_PALA>0.50 Y Sharpe_PALA>Sharpe_RESTO en >=2/3 ventanas, >=30 trades evaluables", veredicto=CUMPLE|NO_CUMPLE, artefacto="backend/data/cache/screening_palas_<ts>.txt", seccion_doc="PRE_REGISTRO_SCREENING_PALAS.md §4"})` — **todos los campos requeridos por `_validate_entry`** (`trial_registry.py:76`): id, fecha, familia, hipotesis, n_trials_consumidos, umbral_aplicado, veredicto, artefacto, seccion_doc. |
 | **Determinismo** | seed 42 para bootstrap CI; lectura determinista del cache; sin RNG en el core del backtest. |
 | **Caso NO_INTERPRETABLE** | si el resultado es NO_INTERPRETABLE (divergencia POOLED vs baseline indicando bug, o <2 ventanas evaluables por n_trades<30) → se registra como **NO_CUMPLE** con nota en el campo `hipotesis` (`"... | NO_INTERPRETABLE: <razon>"`) y en el artefacto. El ledger no tiene un tercer estado (solo CUMPLE|NO_CUMPLE, `trial_registry.py:80`); NO_INTERPRETABLE es un matiz documental dentro de NO_CUMPLE, no un veredicto separado. |

---

## 10. Checklist de no-ejecución

- [x] Este archivo se creó **sin correr ningún backtest**, sin modificar el ledger, sin ejecutar python sobre datos.
- [x] El criterio de §4 (PALA > RESTO en Sharpe Y DSR en ≥2/3 ventanas, DSR > 0.50, ≥30 trades) está sellado — **no se cambia al ver el número**.
- [x] La lista PALA (6 símbolos, §2.2) está congelada — no se agregan/quitan post-hoc.
- [x] Las ventanas (W1/W2/W3) y costos (0.0005+0.0005) están congelados.
- [x] La familia (`signal_diagnosis`) y su presupuesto (26 consumidos → 27) están verificados contra `trial_registry.json` de producción (`~/Desktop/fortress_core/`).
- [ ] **Al ejecutar (SOLO con aprobación explícita de Boris)**: correr UNA vez → artefacto → `register_trial` con veredicto mecánico de §4 → actualizar ROADMAP.md. Este doc solo recibe apéndice de resultados.
- [ ] **Prohibido**: editar este archivo después de correr para "alinear" el criterio. Correcciones metodológicas → nuevo pre-registro.

---

## 11. Próximo paso cuando se apruebe

1. **Boris aprueba este pre-registro explícitamente** (regla #1 ONBOARDING.md).
2. Implementar `backend/scripts/screening_palas.py` según §3 y §9.
3. Correr **una sola vez** → artefacto `screening_palas_*.txt` + `.json`.
4. Veredicto mecánico de §4 → `register_trial` en `trial_registry.json`.
5. Actualizar `ROADMAP.md` (fila correspondiente → 🟢 cerrado con veredicto + artefacto).
6. **Si CUMPLE**: redactar pre-registro del paso 2 (backtest confirmatorio inyectando etiquetado PALA como factor/filtro en el motor — familia `motor_signal`, no `signal_diagnosis`).
7. **Si NO_CUMPLE**: documentar en ARBOL_DECISION_ESTRATEGICO.md como "screened out bajo momentum+RSI" y NO se inyecta al motor.

---

*Fin del pre-registro — borrador para aprobación de Boris, no ejecutado. Próxima edición: solo para agregar el artefacto y el veredicto mecánico cuando se corra con aprobación explícita; el criterio de §4 no se toca.*

---

## 12. Apéndice — resultado de la corrida (agregado post-ejecución, criterio de §4 sin modificar)

- **Corrida**: 2026-08-28, artefacto `data/cache/screening_palas_20260828_071737.txt` (+ `.json`).
- **Veredicto mecánico de §4.1**: PALA gana en 1/3 ventanas evaluables (W1 no, W2 no, W3 sí) → **NO_CUMPLE**.
- **Check de sanidad de §4.2 (POOLED vs baseline)**: **NO_INTERPRETABLE** — 3/3 ventanas fuera de tolerancia. Causa investigada (no bug): `baseline_clean_20260811_150643` corrió con costo 0.15%/lado (default viejo, N_TRIALS=17); la corrida usó costo vigente §33 (0.10%/lado) y n_trials=5 de la familia `signal_diagnosis`. Comparación inválida por desalineación metodológica, no error de implementación.
- **Registrado en el ledger** (`trial_registry.json`, 2026-08-29): `COMPLETED`, `veredicto: NO_CUMPLE`, nota NO_INTERPRETABLE en `hipotesis`. Consume 1 trial de la familia `signal_diagnosis` — no se re-abre esa reserva.
- **Investigación de la divergencia** (OpenCode, 2026-08-29, verificador independiente — no escribió `screening_palas.py`): recalculando el check con `N_TRIALS=17` (igualando al del baseline) en vez de `n_trials=5`: **W1 y W2 quedan dentro de tolerancia en Sharpe Y DSR** (2/3 ventanas — cumpliría el gate de §4.2 si se adoptara esa alineación). **W3 sigue fuera en ambas métricas** incluso corregido; se descartó como causa el rango de fechas distinto entre scripts (delta de trades = 0, verificado con datos crudos). Causa de W3 no resuelta — requiere investigación independiente (ventanas independientes vs. continuo + warmup del HMM) **antes de cualquier re-corrida**.
- **Siguiente paso propuesto (NO ejecutado, pendiente aprobación explícita de Boris)**: nuevo pre-registro que congele `N_TRIALS=17` como metodología correcta para este check y declare W3 fuera de alcance hasta su propia investigación — no se reabre ni se reinterpreta este pre-registro ni su veredicto NO_CUMPLE ya sellado.
