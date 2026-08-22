# Plan de Integración — Hallazgos de indicAgent aplicables a Fortress Core

**Origen:** análisis comparativo de github.com/WallStArb/indicAgent contra el codebase real de
Fortress Core (indicadores, señales, régimen, riesgo, backtesting), en 4 pasadas sucesivas
(infraestructura general, indicadores, entradas/salidas + temporalidad, barrido final de SMC/
gobernanza/agentes/ingesta). Este documento consolida los hallazgos accionables en tickets
discretos para ejecución por agentes de coding (OpenCode / Kilo Code).

**Fecha de redacción:** 2026-08-20
**Status:** current — 9 de 11 tickets cerrados (T0.1, T0.2, T1.1–T1.3, T2.1, T2.2, T2.3;
T1.5, T1.6). Restante: T1.4 (código + tests listos, A/B documental en curso).

---

## Cómo usar este documento

1. **Fase 0 es bloqueante.** No implementar nada de Fase 1 o Fase 2 sin cerrar Fase 0 primero.
   Ambos tickets de Fase 0 cuestionan si los backtests históricos existentes son válidos — si
   alguno confirma un bug real, los resultados de `PLAN_MEJORA_MATEMATICA.md`, `ROADMAP.md`, y
   cualquier decisión tomada con esos backtests quedan bajo sospecha hasta remedir.
2. **Cada ticket es atómico e independiente salvo que la sección "Dependencias" diga lo
   contrario.** Un agente puede tomar un ticket, implementarlo, correr su criterio de
   aceptación, y parar ahí — no asuman que hay que hacer la fase completa de una sentada.
3. **Regla no negociable de este repo (ver `ONBOARDING.md`):** ningún ticket de este plan
   autoriza a afirmar "esto mejora el motor" solo porque el código corre o un test pasa. Un
   ticket que agrega una *feature* o *fix* nueva (ej. Hurst exponent como gate, IC/FDR
   sistemático) queda en estado *disponible pero no promovido* hasta que alguien lo mida con
   la misma disciplina que el resto del proyecto (walk-forward, DSR, Bonferroni/FDR) y lo
   documente en un archivo `PLAN_*` o `RESUMEN_*` nuevo. Los tickets de Fase 0 son la excepción
   — son *fixes* de corrección, no features, y no requieren ese pre-registro.
4. **No romper la fidelidad declarada entre módulos.** `barrier_labeling.py` declara
   explícitamente que replica `adaptive_risk.py::check_all_stops` "verbatim, en el mismo orden
   de prioridad" y tiene un `verify_fidelity()` para detectar drift. Cualquier ticket que toque
   `adaptive_risk.py` (ej. T1.4, T1.5) DEBE correr `verify_fidelity()` después y actualizar
   `barrier_labeling.py` en el mismo PR si el orden o los umbrales cambiaron — no dejarlo para
   después.
5. **Convención de nombres de archivo del repo:** todo en español, `snake_case.py` para
   módulos dentro de `backend/app/core/`, `test_<module>.py` plano dentro de `backend/tests/`
   (sin subcarpetas), documentos de planificación en `MAYUSCULAS_CON_GUION_BAJO.md` en la raíz
   del repo (no hay carpeta `docs/` — por eso este archivo vive en la raíz, seteando el
   precedente de que estos documentos van ahí).
6. **Verificación de rutas:** todas las rutas de archivo citadas abajo fueron confirmadas
   leyendo el repo real al momento de escribir este plan (2026-08-20), no son suposiciones.

---

## Fase 0 — Auditoría crítica (bloqueante, hacer primero)

### T0.1 — [CRÍTICO] Look-ahead acotado en `WalkForwardRegimeGate.label_series` vía decodificación Viterbi de bloque completo

**ESTADO: ✅ CERRADO (2026-08-20, OpenCode).** Método nuevo `predict_regime_series_causal`
(día-por-día, sin leakage) en `regime_classifier.py`; `regime_gate.py::label_series` ahora
lo usa. 12 tests verdes (2 nuevos: causal no usa futuro vs bloque sí); ruff limpio. Suite
completa: los 4 tests de market/live/predict que quedaron rojos son de OTRA sesión que
cambió market.py en paralelo (auto-backup d2819ab 12:29) — no de este ticket. Ver SESSION_LOG.

**Objetivo:** eliminar el look-ahead bias residual (acotado a ≤63 días) en el etiquetado de
régimen que usa `regime_gate.py`, causado por decodificar un bloque de recalibración completo
en una sola llamada Viterbi en vez de barra por barra.

**Contexto — qué encontré exactamente (no es una hipótesis, está confirmado leyendo el código):**

Hay dos caminos de uso del HMM en el repo, y tienen comportamiento distinto:

- **`backtest_engine.py::run()` (líneas 393-401):** en el loop principal, cada lunes llama
  `self.regime_classifier.predict_current_regime({s: df[df.index <= date] ...})`, que dentro de
  `regime_classifier.py::predict_current_regime` (líneas 86-114) llama `self.model.predict(scaled)`
  sobre datos truncados a `<= date` y solo lee `aligned[-1]` (la etiqueta del último día). Esto
  **es causal correctamente**: aunque `.predict()` es Viterbi (decodificación de secuencia
  completa, no forward-filter puro), como el array pasado siempre termina en `date` y solo se
  lee la última etiqueta, no hay información posterior a `date` que pueda filtrarse — Viterbi no
  tiene acceso a nada más allá del último índice del array que le pasás. **Este camino está bien,
  no tocar.**
- **`regime_gate.py::WalkForwardRegimeGate.label_series` (líneas 83-153):** para cada bloque de
  `recalib_every=63` días hábiles, ajusta el HMM con datos estrictamente anteriores al bloque
  (correcto, sin leakage de fit), pero después llama **una sola vez**
  `series = clf.predict_regime_series(predict_data)` (línea 123) pasando datos hasta
  `window_end_date` (el final del bloque completo), y publica las 63 etiquetas de ese bloque
  desde ese único decode. Como `predict_regime_series` (en `regime_classifier.py`, líneas
  116-129) también usa `self.model.predict(scaled)` — Viterbi sobre la secuencia completa
  pasada — la etiqueta del día 1 del bloque puede estar informada por el día 63 del mismo
  bloque. Es el mismo tipo de leakage "a nivel de decodificación" que indicAgent documenta
  como problema abierto y no resuelto en su propio `regime_writer.py` (ver
  `docs/architecture/architecture-v3-alphaengine-pipeline.md` — probaron un fix walk-forward
  refit y no mostró mejora medible, lo dejaron parqueado). Acá el caso es análogo pero más
  fácil de arreglar porque Fortress ya tiene el patrón correcto (`predict_current_regime`)
  implementado y probado en el otro camino — solo hay que reusarlo.

**Impacto:** `WalkForwardRegimeGate` se usa como infraestructura para la compuerta macro (M3,
ver `regime_gate.py` docstring) — cualquier trial que use `label_series()`/`label_symbol_dates()`
para decidir "operar sí/no" según régimen histórico tiene esta ventana de leakage de hasta 63
días. El loop principal de `backtest_engine.py::run()` NO la usa (usa `predict_current_regime`
directamente), así que el motor de trading base no está afectado — pero cualquier trial que
dependa de `regime_gate.py` para pre-registrar una hipótesis sí podría estar viendo resultados
optimistas.

**Archivos afectados:**
- `backend/app/core/regime_classifier.py` (método `predict_regime_series`, líneas 116-129)
- `backend/app/core/regime_gate.py` (método `WalkForwardRegimeGate.label_series`, líneas 83-153)
- `backend/tests/test_regime_gate.py` (existente — extender)
- `backend/tests/test_regime_classifier.py` (existente — extender)

**Qué cambiar (pseudocódigo):**

```python
# regime_classifier.py — agregar método nuevo, NO modificar predict_regime_series
# (puede seguir existiendo para usos donde el leakage acotado sea aceptable / diagnóstico)
def predict_regime_series_causal(self, price_data: Dict[str, pd.DataFrame]) -> pd.Series:
    """Como predict_regime_series pero decodifica día por día: para cada fecha,
    trunca price_data a esa fecha y llama predict_current_regime, tomando solo
    la última etiqueta. O(n) llamadas a Viterbi en vez de 1, pero sin leakage
    dentro de la ventana. Usar en cualquier contexto donde el leakage acotado
    de predict_regime_series no sea aceptable (walk-forward gates, trials
    pre-registrados)."""
    if not self.is_fitted:
        return pd.Series(dtype=int)
    feats = self._extract_features(price_data)
    if feats.empty:
        return pd.Series(dtype=int)
    labels = {}
    for date in feats.index:
        truncated = {s: df[df.index <= date] for s, df in price_data.items()}
        result = self.predict_current_regime(truncated)
        labels[date] = result["state"]
    return pd.Series(labels)

# regime_gate.py — WalkForwardRegimeGate.label_series:
# reemplazar la línea:
#   series = clf.predict_regime_series(predict_data)
# por:
#   series = clf.predict_regime_series_causal(predict_data)
# El resto del método (assert anti-lookahead línea 131, construcción de labels/states)
# no cambia.
```

**Nota de performance:** este cambio multiplica por ~63 la cantidad de decodificaciones HMM
por bloque. Dado que `label_series` corre una vez por backtest/trial (no en tiempo real), el
costo adicional es aceptable — pero si algún trial corre `label_series` en un loop de
optimización de hiperparámetros, medir el tiempo de ejecución antes/después y considerar
cachear `clf` por bloque (ya se hace) y paralelizar el loop de fechas si es necesario.

**Criterio de aceptación:**
1. Nuevo test en `test_regime_classifier.py`: generar una serie sintética donde el régimen
   verdadero cambia abruptamente a mitad de un bloque de 63 días; verificar que
   `predict_regime_series_causal` no le asigna a los primeros días del bloque el régimen que
   solo se vuelve evidente después del cambio (comparar contra `predict_regime_series`, que sí
   debería "adelantarse" — el test tiene que mostrar la diferencia entre ambos métodos, no solo
   que uno corre).
2. Nuevo test en `test_regime_gate.py`: correr `label_series` con el método causal sobre un
   panel real (mismo fixture que ya usa el archivo) y verificar que el assert anti-lookahead
   (línea 131 de `regime_gate.py`) sigue pasando.
3. `backend/.venv/bin/pytest backend/tests/test_regime_classifier.py backend/tests/test_regime_gate.py -v` en verde.
4. No modificar `predict_current_regime` ni el loop de `backtest_engine.py::run()` — ya están
   correctos, tocarlos es fuera de alcance de este ticket.

**Dependencias:** ninguna — puede empezar de inmediato.

**Prioridad:** CRÍTICO.

---

### T0.2 — [CRÍTICO] Ejecución en la misma barra usada para generar la señal (`generate_signal` + `backtest_engine.run`)

**ESTADO: ✅ CERRADO (2026-08-20, OpenCode).** Se implementó la alternativa simple del
ticket: parámetro `execution_lag_days: int = 1` en `run()` (0 = bug anterior, 1 = default
nuevo, ejecución en open de `date+1`). Se aplicó a entradas, salidas (stops y técnicas) y
`_build_calibration_dataset`. `EXECUTION_LAG_DAYS=1` en config.py. Test nuevo
`test_backtest_engine.py` (gap overnight +5%, verifica entry_price=open[siguiente]).
`verify_fidelity()` agregado a barrier_labeling.py. **Impacto medido** (RESUMEN_IMPACTO_EXECUTION_LAG.md):
Sharpe 0.57→0.38 (−33%), CAGR 0.95%→0.70% — el lag=0 sobreestimaba; se adopta lag=1.
Suite 279 passed, ruff limpio. Ver SESSION_LOG.

**Objetivo:** eliminar el supuesto de ejecución no realista donde el backtest calcula
indicadores y genera la señal usando el cierre de la fecha `date`, y transacciona (compra/vende)
al precio de cierre de esa misma fecha `date` — algo imposible en trading real, porque el
cierre oficial de una barra diaria no está disponible para operar hasta después de que el
mercado cerró.

**Contexto — qué encontré exactamente:**

En `backtest_engine.py::run()`, línea 401:
```python
sig = self.signal_engine.generate_signal(df.loc[:date], symbol, regime_info["state"])
```
`df.loc[:date]` incluye la barra de `date` completa (OHLCV ya cerrado). Dentro de
`signal_engine.py::generate_signal` (línea 127): `latest = stock_data.iloc[-1]` — la fila de
`date` — y línea 144: `entry = latest.close` — el cierre de `date`. Después, en
`backtest_engine.py` línea 444: `cost = sig["entry_price"] * shares * (1 + slippage) * (1 +
commission)` — la compra se ejecuta a `sig["entry_price"]`, que es ese mismo cierre de `date`,
con un haircut multiplicativo de slippage/comisión, pero sin ningún desplazamiento temporal.
Mismo patrón en las salidas (línea 314): `exit_price = current_prices.get(symbol,
pos["entry_price"]) * (1 - slippage)` donde `current_prices[symbol]` también es el cierre de
`date` (línea 293).

Esto es el mismo problema de fondo que indicAgent resuelve con su regla "executable returns
only" (`ln(open[T+N+1]/open[T+1])`, nunca `ln(close[T+N]/close[T])`) — pero en la versión
específica de Fortress el problema no es el horizonte de medición del retorno, es que **la
señal y la ejecución comparten la misma barra**. El equivalente correcto para un sistema
diario end-of-day como Fortress es: la señal se calcula con el cierre de `date` (información ya
disponible después del cierre), pero la ejecución debe ocurrir en la apertura de `date + 1`
(la primera oportunidad real de operar con esa información), no en el cierre de `date`.

**Impacto:** esto es potencialmente el hallazgo de mayor impacto de todo el análisis. Afecta
CADA trade de CADA backtest corrido hasta ahora con `backtest_engine.py::run()` — Sharpe, CAGR,
drawdown, win rate, todo. El slippage actual (`settings.COST_PER_SIDE = 0.0005`, medido por M4
contra fills reales de Alpaca paper trading) probablemente absorbe parte de este sesgo en la
práctica (porque fue calibrado contra fills reales, no contra un modelo teórico), pero no hay
garantía de que compense exactamente el gap entre "cierre teórico usado para decidir" y
"apertura real del día siguiente donde se podría ejecutar" — sobre todo en símbolos con gaps
overnight grandes.

**Archivos afectados:**
- `backend/app/core/backtest_engine.py` (método `run`, líneas 233-469; también
  `_build_calibration_dataset`, líneas 41-89, que tiene el mismo patrón)
- `backend/app/core/signal_engine.py` (método `generate_signal`, no necesita cambiar la lógica
  de entry price en sí — el fix es en cómo `backtest_engine.py` usa esa fecha, no en qué precio
  reporta `generate_signal`)
- `backend/app/core/barrier_labeling.py` (declara explícitamente "Se opera sobre cierres
  diarios, igual que el motor" — si este ticket cambia el motor a ejecutar en la apertura
  siguiente, `barrier_labeling.py` deja de ser fiel y hay que actualizarlo en el mismo PR,
  correr `verify_fidelity()`)
- `backend/tests/test_backtest_engine.py` (no existe todavía — crear)

**Qué cambiar (pseudocódigo):**

```python
# backtest_engine.py::run() — idea general: separar "día de decisión" de "día de ejecución"

for i, date in enumerate(dates):
    # ... (cálculo de equity, stops, etc. sobre precios de 'date' se mantiene igual:
    #      eso es mark-to-market legítimo, no ejecución de una decisión nueva)

    if date.dayofweek == 0 and risk_manager.can_open_new_position(date):
        # generar señales con datos hasta 'date' (sin cambios: esto SÍ es información
        # legítimamente disponible al cierre de 'date')
        signals = [...]  # como hoy

        # NUEVO: la ejecución de señales nuevas ocurre en la apertura del PRÓXIMO
        # día hábil disponible en 'dates', no en el cierre de 'date'.
        next_date = dates[i + 1] if i + 1 < len(dates) else None
        if next_date is not None:
            for sig in signals[:5]:
                symbol = sig["symbol"]
                if symbol in positions or symbol not in indicators_cache:
                    continue
                if next_date not in indicators_cache[symbol].index:
                    continue
                next_open = indicators_cache[symbol].loc[next_date, "open"]
                # recalcular entry_price/stop_loss/take_profit relativos a next_open,
                # no al 'entry' que generate_signal calculó sobre el close de 'date'
                # (el score/factores/ATR calculados con datos de 'date' siguen siendo
                # válidos como INSUMO de la decisión — lo que cambia es el precio de
                # ejecución, no el criterio de selección)
                real_entry = next_open
                # ... resto de la lógica de sizing/cash usa real_entry en vez de
                #     sig["entry_price"]
```

Aplicar el mismo criterio (ejecutar en la apertura de la barra siguiente, no en el cierre de la
barra de decisión) a las salidas por stop/target en `check_all_stops` — esto es más delicado
porque un stop debería dispararse intrabar idealmente, pero como Fortress no tiene datos
intradía, el ajuste mínimo aceptable es: un stop detectado con el cierre de `date` se ejecuta
en la apertura de `date + 1`, igual que las entradas.

**Alternativa más simple si el rediseño completo es muy invasivo para un primer ticket:**
en vez de reestructurar el loop, agregar un parámetro `execution_lag_days: int = 1` a `run()` y
un `EXECUTION_LAG_DAYS` en `app/config.py`, documentar el comportamiento actual como
`execution_lag_days=0` (el bug), y correr ambos backtests (0 y 1) sobre el mismo período para
cuantificar el tamaño del sesgo antes de decidir si el fix se vuelve el comportamiento default.
Esto respeta la cultura de "medir antes de creer" del repo (ver `ONBOARDING.md`).

**Criterio de aceptación:**
1. Nuevo archivo `backend/tests/test_backtest_engine.py` con un test que arma un panel
   sintético con un gap overnight grande y conocido (ej. +5% de apertura a apertura) y verifica
   que con `execution_lag_days=1` el precio de entrada registrado en `trades` coincide con la
   apertura del día siguiente, no con el cierre del día de la señal.
2. Correr `calculate_metrics` sobre el mismo panel/período con `execution_lag_days=0` vs `=1` y
   documentar la diferencia de Sharpe/CAGR/max_dd en un archivo nuevo
   `RESUMEN_IMPACTO_EXECUTION_LAG.md` en la raíz (mismo patrón que `RESUMEN_TRABAJOS_20260817.md`)
   — esto es el "medir antes de creer" no negociable del repo, no opcional.
3. `barrier_labeling.py::verify_fidelity()` sigue pasando después del cambio (o se actualiza
   `barrier_labeling.py` en el mismo PR si el orden/timing de las barreras cambió).
4. `backend/.venv/bin/pytest backend/tests/ -v` completo en verde (no solo los tests nuevos —
   este cambio toca el loop central del backtest, correr toda la suite).

**Dependencias:** ninguna, pero se recomienda hacer después de T0.1 (mismo espíritu de
auditoría, y T0.1 es más contenido/rápido de validar primero).

**Prioridad:** CRÍTICO.

---

## Fase 1 — Código portable directo

### T1.1 — Proxy de Order Flow Imbalance (OFI) desde OHLCV puro

**ESTADO: ✅ CERRADO (2026-08-20, Kilo Code).** Implementado y diagnosticado:
`ofi_proxy`/`ofi_features` en `indicators.py` + wiring en `calculate_all_indicators`
(6 columnas `ofi_*`), 6 tests nuevos en `test_indicators.py` (13 passed), entrada en
`DICCIONARIO_INDICADORES.md`. El IC de diagnóstico se corrió como trial pre-registrado
§37 (PLAN_MEJORA_MATEMATICA.md): rank IC cross-sectional de `ofi_ewma_fast_z`
(z rodante causal 100d) vs fwd_20d, universo 50, W1/W2/W3 → **0/3 ventanas con |t|>3.023
y signo +1 (máx t +0.19; TOTAL t −1.66) → NO_CUMPLE**. Ledger signal_diagnosis 19→20.
`ofi_*` queda disponible en los indicadores pero NO se promueve a `_factor_scores`
(regla no negociable del repo: medir antes de integrar — se midió y no predice).
Artefacto: `backend/data/cache/trial_ofi_proxy_20260820_184638.txt`.

**Objetivo:** agregar una función que aproxime el desequilibrio de flujo de órdenes usando
solo datos OHLCV diarios (sin ticks — Fortress usa `yfinance`, no hay acceso a datos de tick),
adaptada de `ofi.py` de indicAgent.

**Adaptación necesaria (no es copy-paste):** el `ofi.py` de indicAgent calcula esto por barra
intradía con estado incremental por (símbolo, timeframe) vía EWMA de 5/20 periodos y z-score
rolling de 100 barras — eso traduce razonablemente a un dataframe diario sin necesitar
arquitectura de streaming, porque `indicators.py` de Fortress ya opera sobre el DataFrame
completo de una vez (no incremental).

**Archivos afectados:**
- `backend/app/core/indicators.py` (agregar función nueva + wire en `calculate_all_indicators`)
- `backend/tests/test_indicators.py` (existente — extender)
- `DICCIONARIO_INDICADORES.md` (existente — agregar entrada nueva, es la convención del repo
  para documentar cada indicador)

**Qué cambiar (pseudocódigo, adaptado de `ofi.py` de indicAgent a pandas vectorizado):**

```python
def ofi_proxy(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Proxy de Order Flow Imbalance sin datos de tick — adaptado de indicAgent ofi.py.
    (close - low) / (high - low + eps) * volume: >0.5 del rango hacia arriba con
    volumen alto sugiere presión compradora."""
    eps = 1e-9
    raw_ofi = (close - low) / (high - low + eps) * volume
    return raw_ofi

def ofi_features(high, low, close, volume, span_fast=5, span_slow=20, z_window=100) -> pd.DataFrame:
    raw = ofi_proxy(high, low, close, volume)
    ofi_ewma_fast = raw.ewm(span=span_fast, adjust=False).mean()
    ofi_ewma_slow = raw.ewm(span=span_slow, adjust=False).mean()
    price_return = close.diff()
    ofi_spike_z = (raw - raw.rolling(z_window).mean()) / (raw.rolling(z_window).std() + 1e-9)
    price_return_z = (price_return - price_return.rolling(z_window).mean()) / (price_return.rolling(z_window).std() + 1e-9)
    ofi_divergence = ofi_spike_z - price_return_z  # positivo = OFI más alcista que el precio
    return pd.DataFrame({
        "ofi_ewma_fast": ofi_ewma_fast, "ofi_ewma_slow": ofi_ewma_slow,
        "ofi_spike_z": ofi_spike_z, "ofi_divergence": ofi_divergence,
    })

# En calculate_all_indicators(df), agregar:
#   df = df.join(ofi_features(df.high, df.low, df.close, df.volume))
```

**Criterio de aceptación:**
1. Test unitario con datos sintéticos donde el cierre está pegado al high con volumen alto en
   varias barras consecutivas → `ofi_ewma_fast` debe ser consistentemente positivo.
2. `calculate_all_indicators` sigue devolviendo un DataFrame sin NaN después de `.dropna()`
   (verificar que el warmup de 100 barras para el z-score no rompe el pipeline con paneles
   cortos — puede necesitar `min_periods` en los rolling).
3. Correr `diagnose_factor_ic` (ya existe en `backtest_engine.py`) incluyendo `ofi_divergence`
   como candidato — NO wirearlo a `signal_engine.py::_factor_scores` todavía, eso requiere
   medir IC primero (regla no negociable del repo).
4. `backend/.venv/bin/pytest backend/tests/test_indicators.py -v` en verde.

**Dependencias:** ninguna.

**Prioridad:** ALTO.

---

### T1.2 — Proxy de Cumulative Volume Delta (CVD) desde OHLCV puro

**ESTADO: ✅ CERRADO (2026-08-20, Kilo Code).** Implementado y diagnosticado:
`cvd_proxy`/`cvd_features` en `indicators.py` + wiring en `calculate_all_indicators`
(4 columnas `cvd_*`), 5 tests nuevos (suite del módulo 18 passed). Decisión de diseño
documentada en el docstring y en DICCIONARIO_INDICADORES.md §4: el reset por sesión
intradía NO aplica a barras diarias → acumulación rolling 20d en su lugar. El IC de
diagnóstico se corrió como trial pre-registrado §38: `cvd_rolling_z` (z rodante causal
100d) vs fwd_20d, universo 50, W1/W2/W3 → **0/3 ventanas con |t|>3.038 y signo +1
(máx t +0.73 W1, W2 −0.84, W3 +0.38) → NO_CUMPLE**. Ledger signal_diagnosis 20→21.
`cvd_*` queda disponible en los indicadores pero NO se promueve a `_factor_scores`.
Artefacto: `backend/data/cache/trial_cvd_proxy_20260820_185959.txt`.

**Objetivo:** igual que T1.1 pero para CVD, adaptado de `cvd.py` de indicAgent.

**Adaptación necesaria — esta es la parte importante:** el `cvd.py` de indicAgent resetea el
acumulador cada sesión intradía a las 09:30 ET. Fortress opera en barras **diarias**, no hay
concepto de "sesión" dentro de una barra diaria — resetear "por sesión" no tiene sentido acá.
Adaptar a una ventana rolling (ej. acumulación de 20 días hábiles, resetear mensualmente o usar
un acumulador que decae) en vez de un reset intradía. Esta es una decisión de diseño que el
agente que implemente el ticket debe tomar explícitamente y documentar en
`DICCIONARIO_INDICADORES.md` — no asumir que "20 días" es automáticamente correcto sin medirlo.

**Archivos afectados:** mismos que T1.1.

**Qué cambiar (pseudocódigo):**

```python
def cvd_proxy(high, low, close, volume) -> pd.Series:
    """Proxy de delta de volumen por barra — adaptado de indicAgent cvd.py.
    (2*close - high - low) / (high - low + eps) * volume."""
    eps = 1e-9
    return (2 * close - high - low) / (high - low + eps) * volume

def cvd_features(high, low, close, volume, window=20) -> pd.DataFrame:
    bar_delta = cvd_proxy(high, low, close, volume)
    # Rolling en vez de acumulación de sesión (no aplica a barras diarias) —
    # ventana de 'window' días, no acumulador infinito (evita drift sin límite
    # en backtests largos).
    cvd_rolling = bar_delta.rolling(window).sum()
    cvd_slope_5bar = cvd_rolling.diff(5) / 5  # o polyfit si se quiere replicar indicAgent exacto
    price_change_5 = close.diff(5)
    cvd_divergence = np.sign(cvd_slope_5bar) - np.sign(price_change_5)
    return pd.DataFrame({"cvd_rolling": cvd_rolling, "cvd_slope_5bar": cvd_slope_5bar,
                          "cvd_divergence": cvd_divergence})
```

**Criterio de aceptación:** igual patrón que T1.1 (test sintético + IC diagnosis antes de
promover a `signal_engine.py`, no wirear directo).

**Dependencias:** ninguna — puede hacerse en paralelo con T1.1.

**Prioridad:** ALTO.

---

### T1.3 — Módulo de estructura de mercado (SMC): Order Blocks, Fair Value Gaps, BOS/CHoCH, Liquidity Sweeps

**ESTADO: ✅ CERRADO (2026-08-20, Kilo Code).** Módulo nuevo
`backend/app/core/market_structure.py` con los 4 detectores + `find_swing_highs/lows`
+ `analyze_market_structure` (corrida única por símbolo, devuelve el dict consumible
por T1.4: `order_block`/`fair_value_gap`/`bos_choch`/`liquidity_sweep` +
`nearest_swing_low`/`nearest_resistance`). 18 tests en
`backend/tests/test_market_structure.py` (sintéticos exactos por detector, tests de
mitigación, historial insuficiente, símbolo real sin crash, min_lookbacks 50/30/60/60),
todos verdes; suite completa 315 passed; ruff limpio. Smoke real: AAPL 2921 barras
analizado en 0.17 s (OB alcista no mitigado a 321.7, FVG bajista abierto a 309-310,
sweep alcista reclaimed — sin NaN/None). NO se promociona a señal: los detectores son
ESTADO descriptivo, y cualquier uso en score requiere su propio trial pre-registrado
(regla no negociable del repo). Entrada agregada en DICCIONARIO_INDICADORES.md.
Nota de implementación (del ticket, respetada): los 4 detectores se llaman UNA vez
por símbolo junto a `indicators_cache`, jamás dentro del loop por fecha.

**Objetivo:** crear un módulo nuevo `market_structure.py` con 4 detectores de estructura,
adaptados directamente del código fuente de indicAgent (`src/intelligence/archive/smc_context/
order_blocks.py`, `fair_value_gap.py`, `bos_choch.py`, `liquidity_sweeps.py`) — código
pandas/numpy puro, sin dependencias del resto de la arquitectura de indicAgent.

**Por qué un módulo nuevo y no meterlo en `indicators.py`:** los 4 detectores devuelven zonas
con estado (nivel superior/inferior, mitigado sí/no) en vez de una serie continua por barra
como el resto de `indicators.py` — encajan mejor como módulo propio, siguiendo el patrón de
`regime_classifier.py`/`regime_gate.py` (módulos con su propia clase/lógica de estado, no
funciones sueltas).

**Archivos afectados:**
- `backend/app/core/market_structure.py` (nuevo)
- `backend/tests/test_market_structure.py` (nuevo)
- `DICCIONARIO_INDICADORES.md` (agregar sección nueva de estructura de mercado)

**Qué cambiar (pseudocódigo — 4 funciones independientes, adaptadas de indicAgent):**

```python
# market_structure.py

def find_swing_highs(high: np.ndarray, neighbor: int = 5) -> list[int]:
    """Swing high: máximo local con 'neighbor' barras a cada lado por debajo."""
    # scipy.signal.argrelextrema(high, np.greater_equal, order=neighbor) o loop explícito

def find_swing_lows(low: np.ndarray, neighbor: int = 5) -> list[int]:
    # análogo, np.less_equal

def detect_order_blocks(df: pd.DataFrame, impulse_bars: int = 3, min_move_pct: float = 0.003) -> dict:
    """Adaptado de indicAgent order_blocks.py. Busca corridas de >= impulse_bars velas
    en la misma dirección con movimiento >= min_move_pct del precio; encuentra la última
    vela opuesta antes del impulso; trackea mitigación (si el precio volvió a operar
    dentro de la zona). Devuelve la zona activa (no mitigada) más reciente:
    {ob_type, ob_top, ob_bottom, ob_strength, ob_mitigated, ob_distance_pct}."""

def detect_fair_value_gaps(df: pd.DataFrame) -> dict:
    """Adaptado de indicAgent fair_value_gap.py. Imbalance de 3 velas:
    bar3.low > bar1.high (alcista) / bar3.high < bar1.low (bajista).
    Chequeo de relleno vectorizado con np.any sobre barras posteriores.
    Devuelve el FVG abierto más reciente:
    {fvg_type, fvg_top, fvg_bottom, fvg_midpoint, fvg_size_pct, fvg_open_count}."""

def detect_bos_choch(df: pd.DataFrame, atr: pd.Series, neighbor: int = 5) -> dict:
    """Adaptado de indicAgent bos_choch.py. BOS: cierre más allá del último swing
    high/low. CHoCH: BOS en dirección opuesta a la tendencia prevaleciente (higher-highs/
    higher-lows de los últimos 2 swings). Fuerza normalizada por ATR.
    Devuelve: {bos_detected, bos_direction, bos_level, bos_strength,
               choch_detected, choch_direction, choch_strength, smc_trend_direction}."""

def detect_liquidity_sweeps(df: pd.DataFrame, neighbor: int = 5, reclaim_bars: int = 3) -> dict:
    """Adaptado de indicAgent liquidity_sweeps.py. Mecha que perfora un swing low/high
    pero cierra adentro (stop hunt); reclaim = N barras siguientes confirman el cierre
    del lado correcto. Devuelve el sweep más reciente:
    {sweep_detected, sweep_type, sweep_level, sweep_depth_pct, sweep_reclaimed,
     sweep_strength, reclaim_velocity}."""
```

**Nota de implementación:** los 4 detectores en indicAgent devuelven "la zona más reciente",
recorriendo todo el historial en cada llamada (O(n) o peor por el loop de impulsos en
`order_blocks`) — para un DataFrame diario de Fortress (miles de barras de historia por
símbolo en un backtest de años) esto puede ser lento si se llama barra por barra dentro del
loop de `backtest_engine.py::run()`. Considerar precomputar las zonas una vez por símbolo antes
del loop principal (como ya se hace con `indicators_cache = {s: calculate_all_indicators(df)
for s, df in price_data.items()}`), no recalcular estructura desde cero en cada fecha del loop.

**Criterio de aceptación:**
1. Test por detector con casos sintéticos mínimos (ej. para FVG: armar 3 velas exactas que
   formen un gap conocido y verificar que `detect_fair_value_gaps` lo encuentra con el
   `fvg_top`/`fvg_bottom` correctos).
2. Test de mitigación: verificar que una zona detectada se marca `mitigated=True`/
   `sweep_reclaimed=True` cuando se agregan barras sintéticas que efectivamente vuelven a
   operar la zona.
3. Correr los 4 detectores sobre un símbolo real completo del panel de Fortress y confirmar
   que no rompen con NaN/None cuando no hay suficiente historia (`min_lookback` como en
   indicAgent: 50 para order blocks, 30 para FVG, 60 para BOS/CHoCH y liquidity sweeps).
4. `backend/.venv/bin/pytest backend/tests/test_market_structure.py -v` en verde.

**Dependencias:** ninguna — puede empezar en paralelo con T1.1/T1.2.

**Prioridad:** ALTO.

---

### T1.4 — Resolver de stop/target estructural (reemplaza múltiplos fijos de ATR)

**Objetivo:** en `signal_engine.py::generate_signal`, reemplazar `stop_loss = entry - 2.0 *
atr_v` / `take_profit = entry + 4.0 * atr_v` (líneas 145-146) por una jerarquía que prioriza
niveles estructurales reales (de T1.3) con fallback a los múltiplos de ATR actuales, siguiendo
el patrón de `trade_framer.py` de indicAgent.

**Archivos afectados:**
- `backend/app/core/signal_engine.py` (método `generate_signal`, líneas 120-169)
- `backend/app/core/market_structure.py` (de T1.3 — consumido acá)
- `backend/tests/test_signal_engine.py` (existente — extender)

**Qué cambiar (pseudocódigo):**

```python
# signal_engine.py — dentro de generate_signal, reemplazar el bloque de stop/target:

# ANTES:
#   stop_loss = entry - 2.0 * atr_v
#   take_profit = entry + 4.0 * atr_v

# DESPUÉS:
def _resolve_stop(entry: float, atr_v: float, market_structure: dict) -> float:
    """Jerarquía de stop estructural, adaptada de indicAgent trade_framer.py.
    Primer match gana; fallback a 2x ATR si nada estructural aplica."""
    ob = market_structure.get("order_block")
    if ob and ob["ob_type"] == 1 and ob["ob_bottom"] < entry and not ob["ob_mitigated"]:
        return ob["ob_bottom"] - atr_v * 0.20
    sweep = market_structure.get("liquidity_sweep")
    if sweep and sweep["sweep_detected"] and sweep["sweep_type"] == 1:
        return sweep["sweep_level"] - atr_v * 0.30
    swing_low = market_structure.get("nearest_swing_low")
    if swing_low is not None and swing_low < entry:
        return swing_low - atr_v * 0.25
    return entry - 2.0 * atr_v  # fallback actual, sin cambios

def _resolve_target(entry: float, atr_v: float, market_structure: dict) -> float:
    """Candidatos de target por encima de entry, el más cercano gana (RR mínimo,
    no el más lejano). Fallback a 4x ATR."""
    candidates = []
    fvg = market_structure.get("fair_value_gap")
    if fvg and fvg["fvg_type"] == 1 and fvg["fvg_bottom"] > entry:
        candidates.append(fvg["fvg_bottom"])
    resistance = market_structure.get("nearest_resistance")
    if resistance is not None and resistance > entry:
        candidates.append(resistance)
    if candidates:
        return min(candidates)  # el más cercano, no el más optimista
    return entry + 4.0 * atr_v  # fallback actual

# Y agregar gate de RR mínimo antes de devolver la señal (patrón trade_framer.py):
MIN_RR = 1.5  # valor a validar empíricamente, no asumir — ver criterio de aceptación
stop_loss = _resolve_stop(entry, atr_v, market_structure)
take_profit = _resolve_target(entry, atr_v, market_structure)
risk = entry - stop_loss
reward = take_profit - entry
if risk <= 0 or reward / risk < MIN_RR:
    return None  # no viable, no generar señal
```

`market_structure` (el dict con `order_block`/`fair_value_gap`/`nearest_swing_low`/
`nearest_resistance`) debe calcularse una vez por símbolo en `indicators_cache` (en
`backtest_engine.py`, junto con `calculate_all_indicators`) y pasarse a `generate_signal` como
parámetro nuevo — no recalcular estructura dentro de `generate_signal` en cada llamada.

**Cambio de firma:** `generate_signal(self, stock_data, symbol, regime_state, market_structure:
dict | None = None)` — con `market_structure=None` cayendo 100% al comportamiento actual (los
fallbacks de ATR), para no romper callers existentes que no lo pasen (ej. `_build_calibration_
dataset` en `backtest_engine.py`, que puede seguir usando el comportamiento viejo hasta que se
decida migrarlo también).

**Criterio de aceptación:**
1. Test que verifica que con `market_structure=None` el comportamiento es IDÉNTICO al actual
   (mismo `stop_loss`/`take_profit` que antes del cambio) — no romper el baseline existente.
2. Test que arma un `market_structure` sintético con un order block por debajo del entry y
   verifica que el stop lo usa en vez del fallback de ATR.
3. Test del gate de RR mínimo: `market_structure` sintético donde el target estructural más
   cercano da RR < `MIN_RR` → `generate_signal` debe devolver `None`.
4. Correr un backtest A/B (con y sin `market_structure`) sobre el mismo período y comparar
   métricas — documentar en `RESUMEN_STOP_ESTRUCTURAL.md` siguiendo la misma disciplina de
   medición del repo. No promover a default sin este comparativo.
5. `backend/.venv/bin/pytest backend/tests/test_signal_engine.py -v` en verde.

**Dependencias:** requiere T1.3 (market_structure.py) completo.

**Prioridad:** MEDIO (valioso pero no bloquea nada más; requiere T1.3 primero).

---

### T1.5 — Registro de parámetros versionado con reconstrucción point-in-time

**Objetivo:** los umbrales de riesgo en `REGIME_THRESHOLDS` (`adaptive_risk.py`, líneas 7-12) y
los gates duros en `generate_signal` (`signal_engine.py`, ADX≥20, RSI 40-75, volume_ratio≥1.0)
son constantes hardcodeadas. Si se ajustan en el futuro, cualquier backtest histórico que se
vuelva a correr aplicaría el valor NUEVO a fechas pasadas — el mismo tipo de leakage de
parámetro que indicAgent documenta y resuelve con su Adaptive Parameter Registry
(`ConfigService.get_at(key, timestamp)`).

**Archivos afectados:**
- `backend/app/core/config_registry.py` (nuevo)
- `backend/app/core/adaptive_risk.py` (`REGIME_THRESHOLDS`, líneas 7-12 — leer desde el
  registro en vez de constante de módulo)
- `backend/tests/test_config_registry.py` (nuevo)
- `fortress.db` (SQLite existente, ver `app/config.py::DATABASE_URL` — agregar tabla nueva, no
  requiere infraestructura adicional)

**Qué cambiar (pseudocódigo, versión simplificada del APR de indicAgent sin Kafka/hot-reload,
que Fortress no necesita porque no es un servicio 24/7):**

```python
# config_registry.py
import sqlite3, json
from datetime import datetime

class ConfigRegistry:
    """Registro de parámetros versionado con historial completo, adaptado del
    Adaptive Parameter Registry de indicAgent (docs/foundation/adaptive-parameter-registry.md)
    pero sin Kafka/hot-reload — Fortress no es un servicio en vivo, no lo necesita.
    Tabla única en SQLite (fortress.db): config_history(key, value, version,
    changed_by, reason, valid_from)."""

    def __init__(self, db_path: str = "fortress.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self):
        # CREATE TABLE IF NOT EXISTS config_history (
        #   key TEXT, value TEXT, version INTEGER, changed_by TEXT,
        #   reason TEXT, valid_from TIMESTAMP, PRIMARY KEY (key, version))
        ...

    def set(self, key: str, value, changed_by: str, reason: str) -> None:
        """Inserta una nueva versión. NUNCA hace UPDATE — solo INSERT (append-only,
        igual que config_history de indicAgent)."""
        ...

    def get(self, key: str, default=None):
        """Valor vigente HOY (última versión)."""
        ...

    def get_at(self, key: str, timestamp: datetime, default=None):
        """Valor vigente en 'timestamp' — busca la última versión con
        valid_from <= timestamp. Este es el método que usa backtest_engine.py
        para reconstruir el estado histórico real de un parámetro, evitando
        que un ajuste futuro contamine un backtest de fechas pasadas."""
        ...

# adaptive_risk.py — reemplazar la constante de módulo REGIME_THRESHOLDS por:
def get_regime_thresholds(regime_state: int, at_date: datetime | None = None) -> dict:
    registry = ConfigRegistry()
    ts = at_date or datetime.now()
    return {
        "position_stop": registry.get_at(f"risk.regime.{regime_state}.position_stop", ts, default=REGIME_THRESHOLDS_FALLBACK[regime_state]["position_stop"]),
        # ... resto de campos, con REGIME_THRESHOLDS actual como fallback/seed inicial
    }
```

**Importante:** este ticket NO debe eliminar `REGIME_THRESHOLDS` como diccionario — debe
quedar como el valor semilla (`changed_by="initial_estimate"`, mismo patrón de provenance que
indicAgent) insertado en `config_history` la primera vez que se corre `_ensure_schema()`. Todo
código existente que importe `REGIME_THRESHOLDS` directamente debe seguir funcionando durante
la transición — migrar los call sites uno por uno, no en un solo cambio masivo.

**Criterio de aceptación:**
1. Test: `set()` dos versiones distintas de la misma key con timestamps distintos, verificar
   que `get_at()` con un timestamp intermedio devuelve la versión vigente en ese momento, no la
   más reciente.
2. Test de integración: correr un backtest sobre 2023, después llamar `set()` para cambiar
   `risk.regime.0.position_stop`, volver a correr el MISMO backtest sobre 2023, verificar que
   los resultados NO cambian (porque `get_at()` reconstruye el valor de 2023, no el actual) —
   este es el test que realmente valida el propósito del ticket.
3. `AdaptiveRiskManager.get_thresholds()` (ya existe, `adaptive_risk.py` línea 35) actualizado
   para usar `get_regime_thresholds()` con el `date` del backtest en curso, no la constante
   directa.
4. `backend/.venv/bin/pytest backend/tests/test_config_registry.py backend/tests/test_risk_manager.py -v` en verde.

**Dependencias:** ninguna, pero conviene hacerlo después de T0.2 (si T0.2 cambia cómo se
manejan las fechas de ejecución en el loop, mejor no pisar ambos cambios a la vez).

**Prioridad:** MEDIO.

---

### T1.6 — Extender `barrier_labeling.py` con taxonomía de outcomes más fina + ledger persistente

**Objetivo:** `barrier_labeling.py` (M1) ya replica las barreras de salida de `adaptive_risk.py`
verbatim y devuelve qué barrera cerró cada posición hipotética — esto es funcionalmente
equivalente a la mitad de lo que indicAgent llama su "taxonomía de 8 outcomes". Lo que falta es
(a) una categoría explícita de invalidación por tiempo sin activación (indicAgent:
`never_activated`, `ttl_expired_ahead/behind`) y (b) persistir los resultados en una tabla
(`fortress.db`) en vez de devolverlos solo como resultado de una corrida ad-hoc, para que
`BayesianOnlineUpdater` (en `probabilistic_engine.py`) pueda aprender de outcomes más
granulares que el `won = pnl > 0` binario que usa hoy (`backtest_engine.py::_update_bayesian_
weights`, línea 96).

**Archivos afectados:**
- `backend/app/core/barrier_labeling.py` (extender categorías de salida)
- `backend/app/core/backtest_engine.py` (método `_update_bayesian_weights`, línea 91-104)
- `backend/app/core/probabilistic_engine.py` (`BayesianOnlineUpdater` — verificar si acepta
  una señal de "fuerza" del outcome, no solo booleano `correct`)
- `backend/tests/test_barrier_labeling.py` (existente — extender)

**Qué cambiar (pseudocódigo):**

```python
# barrier_labeling.py — agregar categorías (revisar las existentes primero, no duplicar
# lo que ya está: ABSOLUTE_CEILING_BREACH, REGIME_STOP_HIT, PARTIAL_TP, TRAILING_STOP
# ya existen según el header del archivo)

# Agregar distinción entre "nunca llegó a moverse" vs "llegó a horizonte máximo sin
# tocar ninguna barrera" (hoy probablemente colapsan en la misma categoría de
# max_horizon genérica — confirmar leyendo el resto del archivo antes de tocar):
class ExitReason(Enum):
    ABSOLUTE_CEILING_BREACH = "absolute_ceiling_breach"
    REGIME_STOP_HIT = "regime_stop_hit"
    PARTIAL_TP = "partial_tp"
    TRAILING_STOP = "trailing_stop"
    MAX_HORIZON_PROFIT = "max_horizon_profit"    # nuevo: llegó al límite temporal en ganancia
    MAX_HORIZON_LOSS = "max_horizon_loss"        # nuevo: llegó al límite temporal en pérdida
    NEVER_MOVED = "never_moved"                  # nuevo: precio nunca se alejó significativamente del entry

# backend/app/core/signal_ledger.py (nuevo, o agregar tabla dentro de config_registry.py de T1.5
# si se prefiere un solo módulo de persistencia — decisión del implementador):
# CREATE TABLE signal_ledger (
#   signal_id TEXT PRIMARY KEY, symbol TEXT, entry_date DATE, exit_date DATE,
#   exit_reason TEXT, pnl_r REAL, factors_json TEXT, regime_state INTEGER)

# backtest_engine.py::_update_bayesian_weights — usar pnl_r (retorno en unidades de riesgo,
# no solo el signo) como señal de fuerza para el update Bayesiano, si BayesianOnlineUpdater
# lo soporta (revisar su firma actual en probabilistic_engine.py antes de asumir que sí).
```

**Nota:** este ticket depende de leer el resto de `barrier_labeling.py` (solo se leyeron las
primeras ~50 líneas para este plan) y la firma completa de `BayesianOnlineUpdater.update()` en
`probabilistic_engine.py` antes de escribir el pseudocódigo final — el agente que lo implemente
debe hacer esa lectura completa primero, lo de acá es la dirección, no el diff final.

**Criterio de aceptación:**
1. `barrier_labeling.py::verify_fidelity()` (ya existe) sigue pasando después de agregar las
   categorías nuevas — no cambiar el ORDEN de evaluación de las barreras existentes, solo
   agregar sub-categorías dentro de lo que hoy es un solo "no tocó nada, expiró".
2. Test que verifica que una posición sintética que nunca se mueve más de X% se etiqueta
   `NEVER_MOVED`, no `MAX_HORIZON_PROFIT`/`MAX_HORIZON_LOSS`.
3. Test de persistencia: correr el labeling sobre un panel pequeño, verificar que
   `signal_ledger` tiene una fila por señal generada con la categoría correcta.
4. `backend/.venv/bin/pytest backend/tests/test_barrier_labeling.py -v` en verde.

**Dependencias:** ninguna estricta, pero comparte espacio de diseño con T1.5 (ambos tocan
persistencia en `fortress.db`) — coordinar el schema si se hacen en paralelo.

**Prioridad:** MEDIO.

---

## Fase 2 — Metodología (reimplementar el método, no copiar código)

**Nota importante antes de esta fase:** al leer el código real de Fortress para este plan,
encontré que buena parte de lo que originalmente parecía un gap metodológico frente a
indicAgent **ya está implementado, y en algunos casos de forma más rigurosa**:

- IC/RankIC/ICIR walk-forward: ya existe (`probabilistic_engine.py::SignalQualityMetrics`,
  `WalkForwardValidator`; usado en `backtest_engine.py::diagnose_factor_ic` y
  `validate_signal_quality`).
- Corrección por comparaciones múltiples: ya se aplica Bonferroni (ver el comentario en
  `signal_engine.py` líneas 20-24: "no robusto bajo Bonferroni-4"), que es más conservador
  que el Benjamini-Hochberg FDR que usa indicAgent.
- Intervalos con garantía de cobertura en muestra finita: ya existe, y es más riguroso que un
  bootstrap de bloques — `conformal.py` (M2) implementa Split Conformal Prediction (Vovk et
  al.), con abstención calibrada y corrección estructural documentada del 2026-08-17.
- Detección de deriva: ya existe (`drift_detector.py`, M5).
- Retornos "ejecutables" vs. teóricos: el problema real no era close-to-close vs. open-to-open
  (Fortress no opera intradía) sino ejecución en la misma barra de la señal — **ver T0.2**, que
  reemplaza lo que originalmente iba a ser un ticket de "metodología" acá.

Por eso esta fase quedó más corta de lo que el pedido original sugería — los tickets que siguen
son los gaps genuinos que encontré, no una reimplementación de algo que ya existe.

### T2.1 — Verificar/agregar purge-embargo en `WalkForwardValidator`

**ESTADO: ✅ CERRADO (2026-08-20, Kilo Code).** Hallazgo verificado contra el código real:
el corte train/test era CONTIGUO — no había purga ninguna (verificado en
`probabilistic_engine.py:636-653` pre-fix). No obstante, el análisis completo del mecanismo
de leakage (en el docstring de la clase, si se lee el código actual) concluye que el embargo
relevante es excluir las primeras barras del fold de TEST post-corte, ya que en este diseño
no se entrena modelo sobre train y el lado train no contamina nada (cada ventana mide test-con-test).
`validate()` ahora tiene `purge_bars: Optional[int] = None` → default `horizon` (siguiendo
el criterio de indicAgent), `purge_bars=0` reproduce el comportamiento pre-fix para comparar
resultados históricos, `purge_bars >= test_window` devuelve el error elegante
"no hay suficientes ventanas". `purge_bars` se reporta en el dict resultado.
7 tests nuevos en `tests/test_probabilistic_engine.py` (invariante de embargo por fold via
captura de índices, default=horizon, purge_bars=0 reproducible, purge explícito, degenerado,
negativo, humo end-to-end con horizonte=20 reales → IC↑ por construcción). Suite 286 passed
(279 baseline + 7). ruff limpio.

**Objetivo:** confirmar si `probabilistic_engine.py::WalkForwardValidator` ya excluye una
ventana de purga entre el fold de entrenamiento y el de test (necesaria porque
`CALIBRATION_HORIZON_DAYS=20` genera retornos con ventanas solapadas — el mismo problema que
motiva el purge/embargo de 60 barras en el IC engine de indicAgent). **No se confirmó en este
análisis** porque no se leyó el cuerpo completo de la clase — este ticket empieza con esa
lectura.

**Archivos afectados:**
- `backend/app/core/probabilistic_engine.py` (clase `WalkForwardValidator`)
- `backend/tests/test_probabilistic.py` si existe, o el archivo de test correspondiente
  (confirmar nombre real — no apareció en el listado de `backend/tests/` revisado para este
  plan, puede estar cubierto indirectamente por otro test)

**Qué hacer:**
1. Leer `WalkForwardValidator.validate()` completo.
2. Si ya implementa un gap entre train/test proporcional al horizonte de retorno (`horizon` es
   un parámetro de `validate()`, según se ve en la llamada de `backtest_engine.py` línea 132-133)
   → cerrar el ticket documentando que ya está cubierto, no reimplementar nada.
3. Si NO lo implementa → agregar un parámetro `purge_bars: int` (default = `horizon`, siguiendo
   el criterio de indicAgent de "sizeado al horizonte de retorno más largo") que excluye del
   fold de test las primeras `purge_bars` observaciones después del corte train/test.

**Criterio de aceptación:**
1. Documentar el hallazgo (ya implementado / no implementado) en un comentario en el propio
   archivo, citando esta sección del plan.
2. Si se implementa el fix: test que verifica que ninguna observación de test está dentro de
   `purge_bars` del límite del fold de entrenamiento.
3. `backend/.venv/bin/pytest backend/tests/ -k walk_forward -v` en verde.

**Dependencias:** ninguna.

**Prioridad:** ALTO (es el único gap metodológico genuinamente no confirmado — puede resultar
en "nada que hacer" o en un fix real, hay que averiguarlo).

---

### T2.2 — Bootstrap de bloques circulares para intervalos de confianza a nivel de métricas agregadas de backtest

**Objetivo:** agregar bootstrap de bloques circulares específicamente para las métricas
agregadas de `calculate_metrics()` (Sharpe, CAGR, max drawdown) — **no** para reemplazar
`conformal.py`, que ya cubre la calibración por señal individual con una garantía más fuerte
(cobertura exacta en muestra finita vs. la garantía asintótica de un bootstrap). Esto
complementa el Deflated Sharpe Ratio que ya existe (`DEFAULT_N_TRIALS`, línea 479 de
`backtest_engine.py`) dándole un intervalo de confianza, no solo un punto.

**Archivos afectados:**
- `backend/app/core/probabilistic_engine.py` (agregar función nueva, no clase — sigue el
  patrón de funciones sueltas donde aplica)
- `backend/app/core/backtest_engine.py` (`calculate_metrics`, línea 481 en adelante — agregar
  los CI al dict de retorno)
- `backend/tests/test_backtest_api.py` o nuevo test específico

**Qué cambiar (pseudocódigo):**

```python
# probabilistic_engine.py
def circular_block_bootstrap_ci(returns: np.ndarray, statistic_fn, block_size: int = 20,
                                  n_bootstrap: int = 1000, confidence: float = 0.95) -> tuple[float, float]:
    """Bootstrap de bloques circulares (no asintótico) para el intervalo de confianza
    de una métrica calculada sobre una serie de retornos autocorrelacionada.
    Adaptado de la metodología de indicAgent (docs/architecture/architecture-v3-
    alphaengine-pipeline.md, sección IC Measurement) — NO existe un archivo de código
    fuente confirmado para copiar, esto es una reimplementación desde la metodología
    descripta, no una adaptación de un archivo real."""
    n = len(returns)
    boot_stats = []
    for _ in range(n_bootstrap):
        n_blocks = int(np.ceil(n / block_size))
        start_idxs = np.random.randint(0, n, size=n_blocks)
        blocks = [np.take(returns, range(s, s + block_size), mode="wrap") for s in start_idxs]
        sample = np.concatenate(blocks)[:n]
        boot_stats.append(statistic_fn(sample))
    lo = np.percentile(boot_stats, (1 - confidence) / 2 * 100)
    hi = np.percentile(boot_stats, (1 + confidence) / 2 * 100)
    return lo, hi

# backtest_engine.py::calculate_metrics — agregar:
sharpe_ci = circular_block_bootstrap_ci(returns.values, lambda r: r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0)
# incluir sharpe_ci en el dict de retorno junto al sharpe puntual existente
```

**Advertencia explícita para el implementador:** a diferencia de los tickets de Fase 1, **no
encontré un archivo de código fuente de indicAgent para este bootstrap** — lo busqué
específicamente y no pude confirmarlo (dos intentos con timeout de red). Lo que está en el
pseudocódigo de arriba es una reimplementación estándar de la técnica descripta en la
documentación de indicAgent, no una adaptación de código verificado. Tratarlo como diseño
propio a revisar, no como "port" de algo ya probado.

**Criterio de aceptación:**
1. Test con una serie de retornos IID conocida (ej. `np.random.normal`) donde el CI bootstrap
   debe contener el Sharpe verdadero ~95% de las veces en simulación repetida.
2. Test con una serie con autocorrelación fuerte inyectada artificialmente, verificar que el CI
   bootstrap de bloques da un intervalo más ancho que un CI asintótico ingenuo calculado sobre
   la misma serie (ese es el punto del método — cuantificar la incertidumbre real).
3. `backend/.venv/bin/pytest backend/tests/ -k bootstrap -v` en verde.

**Dependencias:** ninguna.

**Prioridad:** MEDIO.

---

### T2.3 — Features de régimen por símbolo: Hurst exponent y GARCH simple

**ESTADO: ✅ CERRADO (2026-08-21, Kilo Code + cierre de medición).** Código implementado
(`hurst_exponent` vectorizado + `realized_vol_regime` en `indicators.py`, integrados a
`calculate_all_indicators` como columnas diagnósticas). Tests recalibrados con evidencia
estadística (panel n=3000, 50 semillas: min H=0.230 sobre umbral 0.2 — el umbral NO se
bajó; aserciones robustas multi-semilla para el shock de vol). Diagnóstico IC transversal
(Spearman por fecha, NW L=min(12,n//8), W1/W2/W3, ref Bonferroni-19 |t|>3.008):
**sin edge direccional** en ninguna ventana (hurst máx |t|=2.70 con signo inestable;
vol_regime máx |t|=0.52); validación de clustering parcial solo en W1 (t=+3.25, W2/W3
nulos). **Veredicto: NO se promueven a `_factor_scores`** — quedan como features
diagnósticas. Detalle completo y artefacto (`diagnose_hurst_vol_ic_20260821_210750.txt`)
en `RESUMEN_HURST_VOL_REGIME.md`. Suite 358 passed (verificada 2026-08-22).

**Objetivo:** agregar 1-2 features de régimen calculadas por símbolo individual (no macro,
complementarias al `GlobalRegimeClassifier` existente que es cross-asset), siguiendo la idea de
indicAgent de que el régimen macro y el régimen idiosincrático del símbolo son preguntas
distintas (ver `docs/architecture/architecture-v3-alphaengine-pipeline.md`, sección "Two HMM
Systems, Not One" — ahí también se explica por qué es conditioning y no gating, considerar el
mismo principio acá: no usar esto como filtro binario duro sin medir primero).

**Archivos afectados:**
- `backend/app/core/indicators.py` (funciones nuevas)
- `backend/tests/test_indicators.py`
- `DICCIONARIO_INDICADORES.md`

**Qué cambiar (pseudocódigo):**

```python
def hurst_exponent(close: pd.Series, window: int = 100, max_lag: int = 20) -> pd.Series:
    """Rolling Hurst exponent vía R/S analysis. >0.5 = persistencia/tendencia,
    <0.5 = reversión a la media, ~0.5 = random walk. Usado como feature de
    régimen por símbolo, complementario al HMM macro — NO reemplazo."""
    def _hurst_window(prices: np.ndarray) -> float:
        lags = range(2, max_lag)
        tau = [np.std(np.subtract(prices[lag:], prices[:-lag])) for lag in lags]
        poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
        return poly[0] * 2.0
    return close.rolling(window).apply(lambda w: _hurst_window(w.values), raw=False)

def realized_vol_regime(returns: pd.Series, short_window: int = 20, long_window: int = 100) -> pd.Series:
    """Proxy simple de régimen de volatilidad (no un GARCH(1,1) completo — evaluar si
    vale la complejidad de un GARCH real vs. este proxy antes de invertir en la
    dependencia arch/statsmodels). Ratio de vol de corto vs. largo plazo."""
    short_vol = returns.rolling(short_window).std()
    long_vol = returns.rolling(long_window).std()
    return short_vol / long_vol
```

**Decisión explícita a tomar por el implementador:** el pseudocódigo de arriba usa un proxy de
volatilidad simple (ratio de ventanas) en vez de un GARCH(1,1) real, para no agregar una
dependencia nueva (`arch` package) sin justificación medida. Si el diagnóstico de IC (paso
siguiente) muestra que el proxy simple no tiene poder predictivo pero se sospecha que un GARCH
real sí lo tendría, ahí se evalúa agregar la dependencia — no antes.

**Criterio de aceptación:**
1. Test unitario de `hurst_exponent` con una serie sintética de random walk puro (Hurst ≈ 0.5)
   y una serie con tendencia fuerte inyectada (Hurst > 0.5 esperado).
2. Correr `diagnose_factor_ic` (ya existe) incluyendo `hurst_exponent` y `realized_vol_regime`
   como factores candidatos — **no** agregarlos a `signal_engine.py::_factor_scores` hasta que
   esto se mida y se documente en un `RESUMEN_*.md` nuevo con el mismo rigor que
   `RESUMEN_VALIDACION_VARIABLES.md` (IC, Bonferroni, walk-forward).
3. `backend/.venv/bin/pytest backend/tests/test_indicators.py -v` en verde.

**Dependencias:** ninguna.

**Prioridad:** BAJO — es exploratorio (features nuevas sin promoción garantizada), no corrige
nada roto ni es tan directamente accionable como Fase 1.

---

## Resumen de prioridades y orden sugerido de ejecución

| # | Ticket | Fase | Prioridad | Depende de |
|---|--------|------|-----------|------------|
| 1 | T0.1 — Look-ahead en `WalkForwardRegimeGate` | 0 | CRÍTICO | — |
| 2 | T0.2 — Ejecución misma-barra en `backtest_engine.run` | 0 | CRÍTICO | — |
| 3 | T1.1 — Proxy OFI | 1 | ALTO | — |
| 4 | T1.2 — Proxy CVD | 1 | ALTO | — |
| 5 | T1.3 — Módulo `market_structure.py` (SMC) | 1 | ALTO | — |
| 6 | T2.1 — Purge/embargo en `WalkForwardValidator` | 2 | ALTO | — |
| 7 | T1.4 — Stop/target estructural | 1 | MEDIO | T1.3 |
| 8 | T1.5 — Registro de parámetros versionado | 1 | MEDIO | (sugerido: después de T0.2) |
| 9 | T1.6 — Taxonomía de outcomes + ledger | 1 | MEDIO | (coordinar schema con T1.5) |
| 10 | T2.2 — Bootstrap de bloques circulares | 2 | MEDIO | — |
| 11 | T2.3 — Hurst / GARCH proxy por símbolo | 2 | BAJO | — |

Los tickets 3-6 pueden ejecutarse en paralelo entre sí y en paralelo con 1-2 (no tocan los
mismos archivos), pero **ningún resultado de un backtest corrido con 3-11 debe considerarse
válido hasta que 1 y 2 estén resueltos** — si T0.1 o T0.2 cambian números de backtest de forma
material, puede ser necesario re-priorizar o re-medir trabajo ya hecho en la Fase 1/2.

---

## Qué quedó explícitamente fuera de este plan (y por qué)

Del barrido completo de indicAgent (4 análisis previos), lo siguiente se evaluó y se descartó
activamente — no está "pendiente", está descartado con razón documentada:

- **Capa de agentes LLM (swarm, LangGraph, Head Trader, eAI):** código 100% acoplado a
  Kafka/asyncpg/OTel de indicAgent, y además no operativo ni siquiera en indicAgent (shadow
  registry con `last_eval_at IS NULL`, servicios `disabled`). Nada para portar.
- **Ingesta IBKR (`ibkr.py`):** Fortress usa `yfinance` en modo batch diario; no hay caso de uso
  para un circuit breaker de datos en vivo.
- **Costos de ejecución:** Fortress ya tiene `execution_costs.py` (M4) con medición real contra
  Alpaca paper trading — más maduro que indicAgent, que no tiene este módulo construido.
- **Gobernanza de promoción/democión (Concept Registry):** el mecanismo conceptual (n≥100,
  bootstrap CI, histéresis) ya es, en espíritu, lo que hace `barrier_labeling.py` +
  `ONBOARDING.md` con sus reglas de pre-registro — no se encontró código fuente portable
  (`concept_registry_service.py` no se pudo leer por timeout repetido), y reimplementar el
  framework completo de indicAgent sería sobre-ingeniería para las necesidades actuales de
  Fortress.
- **IC + FDR/Bonferroni como metodología nueva:** ya existe en el repo (ver nota al inicio de
  Fase 2) — no hay nada que agregar salvo la verificación puntual de T2.1.

---

## Confirmación de guardado

Este archivo quedó guardado en: **`/Users/boris/Desktop/fortress_core/PLAN_INTEGRACION_INDICAGENT.md`**

(en la raíz del repo, no en una carpeta `docs/` — el repo no tiene esa carpeta, y todos los
documentos de planificación existentes (`ROADMAP.md`, `PLAN_LARGO_PLAZO.md`,
`PLAN_MEJORA_MATEMATICA.md`, `PLAN_SENTIMIENTO.md`) viven en la raíz con nombres
`MAYUSCULAS_CON_GUION_BAJO.md` — este archivo sigue esa misma convención).
