# PRE-REGISTRO — Reconciliación pipeline diario vs backtest (método congelado)

**Fecha de pre-registro**: 2026-08-26
**Estado**: 🟡 BORRADOR — NO EJECUTADO (método congelado, activación condicional)
**Autor**: OpenCode (gentle-orchestrator) — Track B del plan "nivel dios" consolidado
**Referencia**: ONBOARDING.md reglas #1–#3 · PRE_REGISTRO_SCREENING_PALAS.md (formato) · ARBOL_DECISION_ESTRATEGICO.md (Track B, punto 4 consolidado)
**Regla de oro**: este documento se escribe ANTES de tener datos suficientes y NO se edita después de ver los resultados. La activación (paso 4c) requiere 60-90 días de paper trading real acumulados.

---

## 1. Propósito

**Problema**: el proyecto mide la calidad de la señal con backtests históricos (DSR/PBO). Pero el backtest asume execution_lag=1, slippage=0.0005 fijo, fills perfectos al open. Si el pipeline diario real ejecuta con slippage distinto, fills parciales, o timing distinto, **el DSR del backtest es decorativo** — no predice lo que el paper-trading va a hacer.

**Objetivo**: definir el método de comparación entre la equity curve del pipeline real y la equity curve del backtest sobre el mismo periodo, con tolerancias numéricas que disparen alerta cuando el backtest deje de predecir la ejecución real.

**FUDE (Fuera de Alcance Definido) — paso 4b**: este pre-registra el método y el logging mínimo. La comparación real, la activación del gate y las alertas son **paso 4c** (en 2-4 semanas, con 60-90 días de paper trading).

---

## 2. Esquema de datos — congelado

### 2.1. Campos que el pipeline emite (pipeline_signal_log.jsonl)

Cada evento (decision/execution) registra:

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `event` | str | sí | `"decision"` (señal emitida en decide) o `"execution"` (orden ejecutada en enter/exit) |
| `phase` | str | sí | `"decide"` / `"enter"` / `"exit"` |
| `symbol` | str | sí | ticker (ej. `"NVDA"`) |
| `signal_id` | str | sí | identificador único (`{symbol}__{entry_date}` o `chkpt__{symbol}__{date}`) |
| `side` | str | sí | `"buy"` / `"sell"` |
| `entry_date` | str\|null | sí | ISO date de la decisión/compra |
| `qty` | int\|null | sí | cantidad de acciones |
| `price_ref` | float\|null | sí | precio de referencia al decidir (close del día de señal) |
| `score` | float\|null | sí | score compuesto (momentum+RSI) que generó la señal |
| `fill_price` | float\|null | sí | precio real de llenado (null en decision) |
| `client_order_id` | str\|null | sí | id de orden en el broker paper |
| `pipeline_run_ts` | str | sí | timestamp ISO del momento de logging |
| `source` | str | sí | origen (`pipeline_daily_signal.phase_*`) |
| `checkpoint_override` | bool | no | true si es inyección de mecanismo (no señal real) |
| `frozen_echo` | dict | no | snapshot de pesos del motor (solo en decision) |
| `status` | str | no | submitted/skipped/error (solo en execution) |
| `skip_reason` | str | no | motivo de skip (solo en execution) |
| `error` | str | no | mensaje de error (solo en execution) |

### 2.2. Campos que el backtest_emite (calculate_metrics + equity_curve)

El backtest ya produce (vía `BacktestEngine.run` → `calculate_metrics`):

| Campo | Fuente | Descripción |
|---|---|---|
| `date` | `equity_curve[].date` | fecha de cada barra |
| `equity` | `equity_curve[].equity` | valor de la equity ese día |
| `returns` | `equity_curve[].equity` pct_change | retorno diario |
| `trades[]` | `trades` | lista de trades con entry_date, exit_date, entry_price, exit_price, qty, pnl |
| `sharpe_ratio` | `calculate_metrics` | Sharpe anualizado del periodo |
| `deflated_sharpe` | `calculate_metrics` | DSR (ajustado por n_trials) |

### 2.3. Alineación (cómo se juntan)

La comparación se hace **por fecha** (date):

- **Equity curve del pipeline**: se reconstruye desde `pipeline_signal_log.jsonl` filtrando `event="execution"` y `status="submitted"`, agrupando por `entry_date`/`exit_date`, aplicando los fills reales (`fill_price`) y los costos reales (`settings.COST_PER_SIDE + 0.0005`).
- **Equity curve del backtest**: se corre `BacktestEngine.run` sobre el **mismo rango de fechas** (mismo `start_date`/`end_date`) con la **misma definición congelada** (pesos del motor leídos en runtime, gates duros, sin regime-gate).
- **Exclusiones**: los eventos con `checkpoint_override=true` se excluyen de la equity curve del pipeline (son de mecanismo, no de señal).

---

## 3. Métrica de comparación — congelada

### 3.1. Métrica primaria: Sharpe rolling en ventana móvil

- **Ventana**: 20 días hábiles (~1 mes).
- **Cálculo**: Sharpe anualizado (mean/std × √252) sobre los retornos diarios de cada equity curve, en ventana móvil.
- **ΔSharpe(t)** = `Sharpe_pipeline(t) − Sharpe_backtest(t)` en cada punto de la ventana.

### 3.2. Gate de alerta (tolerancia numérica)

| Condición | Veredicto |
|---|---|
| **\|ΔSharpe\| ≤ 0.20** en ≥80% de los puntos | **CONVERGENTE** — el backtest predice la ejecución real. |
| **\|ΔSharpe\| > 0.20** en >20% de los puntos (≥6 días de 30) | **DIVERGENTE — ALERTA**: el backtest ya no predice la ejecución real. Se frena la escalación y se investiga (slippage, fills parciales, timing). |

**Justificación de la tolerancia 0.20**: el Sharpe anualizado tiene error estándar ≈ `1/√(n_días)` ≈ 0.18 para n=30. Exigir \|ΔSharpe\| ≤ 0.20 es exigir que la divergencia esté dentro de ~1 SE del estimador — conservador (no dispara por ruido), pero sensible a divergencias sostenidas (no a un día atípico).

### 3.3. Métrica secundaria (informativa, no gate)

- **\|Δequity_acumulada\|** al final del periodo: diferencia en retorno acumulado entre pipeline y backtest.
- **Fill rate**: % de señales del pipeline que lograron fill (status="submitted") vs. las que se intentaron.
- **Slippage medio real**: `fill_price − price_ref` / `price_ref` por operación, comparado vs. el 0.0005 asumido en config.

---

## 4. Frecuencia de evaluación — congelada

- **No continua**: la evaluación se corre **semanalmente** (no diariamente) para acumular datos y evitar ruido.
- **Mínimo para activar**: 60 días hábiles de paper trading real (≈ 3 meses de operación mensual). Con menos, el Sharpe rolling de 20 días tiene <3 puntos — estadísticamente vacío.
- **Activación (paso 4c)**: cuando se alcancen 60-90 días de paper trading, se implementa la función de comparación (no antes).

---

## 5. Qué NO hace este método (deliberadamente)

- **No compara en tiempo real**: la comparación es semanal, batch, no streaming.
- **No ajusta el motor automáticamente**: si hay divergencia, se alerta y se investiga — el motor no se re-entrena solo.
- **No usa datos nuevos**: trabaja 100% con el cache existente y el log del pipeline.
- **No activa alertas antes de 60 días**: el gate está congelado hasta haber datos suficientes.
- **No modifica signal_engine.py ni backtest_engine.py**: el método es un módulo nuevo que consume sus salidas.

---

## 6. Logging mínimo implementado HOY (paso 4b)

**Archivo**: `backend/scripts/pipeline_signal_log.py` + integración en `pipeline_daily_signal.py`.

- **Formato**: JSONL append-only en `backend/data/pipeline_signal_log.jsonl`.
- **Puntos de logging**: `phase_decide` (señales decididas), `phase_enter` (compras ejecutadas), `phase_exit` (ventas ejecutadas).
- **Best-effort**: cualquier excepción en el logging se traga — un fallo de logging JAMAS bloquea una orden real (verificado con tests).
- **Tests**: `backend/tests/test_pipeline_signal_log.py` (9 tests, todos OK).

---

## 7. Riesgos y limitaciones — declarados ANTES de activar

1. **60 días mínimo es arbitrario pero conservador**: el Sharpe rolling de 20 días necesita ≥3 puntos para ser estable. 60 días dan ~40 puntos — suficiente. Activar antes es ruido.
2. **El backtest y el pipeline no comparten el mismo capital**: el backtest usa `initial_capital=25000` fijo; el pipeline lee equity real de la cuenta. Si la cuenta crece/encoge, la comparación de equity curves absoluta se distorsiona — por eso la métrica es **Sharpe** (ratio, no absoluto).
3. **Checkpoint override contamina si no se filtra**: los trades de mecanismo (inyectados para validar el tubo) tienen `checkpoint_override=true` y se excluyen. Si el filtro falla, la equity curve del pipeline incluye trades que no son de señal — por eso el filtro es obligatorio y testeable.
4. **El pipeline es mensual, el backtest es continuo**: el pipeline decide/entra/sale ~mensual; el backtest corre diario. La alineación por fecha maneja esto (días sin pipeline → retorno pipeline = 0), pero la comparación es más informativa en ventanas ≥1 mes.

---

## 8. Checklist de no-ejecución (para el paso 4c)

- [x] Este documento se escribió ANTES de tener datos suficientes (hoy hay ~7-14 días de paper trading, no 60).
- [x] La tolerancia (\|ΔSharpe\| > 0.20) está sellada — no se cambia al ver los números.
- [x] El mínimo de activación (60 días) está congelado — no se activa antes.
- [x] El esquema de logging (§2.1) está implementado y testeado.
- [ ] **Al activar (paso 4c, en 2-4 semanas)**: implementar `backend/scripts/reconciliacion_pipeline_backtest.py` que lea `pipeline_signal_log.jsonl`, reconstruya equity curve del pipeline, corra backtest_engine sobre el mismo periodo, calcule ΔSharpe rolling, y dispare alerta si \|ΔSharpe\| > 0.20.
- [ ] **Prohibido**: activar antes de 60 días, cambiar tolerancias post-hoc, o usar el método para re-entrenar el motor automáticamente.

---

*Fin del pre-registro — método congelado, logging implementado, activación condicional a 60-90 días de paper trading real.*
