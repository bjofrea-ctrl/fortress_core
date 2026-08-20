# Resumen de impacto — Lag de ejecución (T0.2)

**Fecha:** 2026-08-20
**Ticket:** T0.2 — `PLAN_INTEGRACION_INDICAGENT.md` (Fase 0)
**Objetivo:** cuantificar el sesgo del supuesto de ejecución en la MISMA barra que
genera la señal, comparando `execution_lag_days=0` (el bug, señal y ejecución al cierre
de `date`) contra `execution_lag_days=1` (default nuevo: ejecución en la APERTURA de la
barra siguiente, `open[date+1]`). Esto es el "medir antes de creer" no negociable del repo.

## Configuración del backtest usado

- **Universo (precio):** SPY, QQQ, AAPL, MSFT, GOOGL, NVDA, AMZN (7 símbolos, desde
  `backend/data/cache/`, período de descarga 2019-2023).
- **Universo (mercado/régimen):** SPY, EFA, QQQ, GLD, DBC, TIP, TLT, AGG, ^VIX (desde 2015).
- **Período backtest:** 2021-01-01 a 2023-12-31 (3 años, universo chico para correr rápido).
- **Capital inicial:** 25,000. Comisión/slippage defaults del motor (0.001 / 0.0005).
- **Script:** `backend/scripts/measure_execution_lag_impact.py`.

## Resultados

| Métrica | lag=0 (bug, cierre de `date`) | lag=1 (open de `date+1`) | Delta (lag1 − lag0) |
|---------|-------------------------------|---------------------------|----------------------|
| n_trades | 26 | 28 | +2 |
| CAGR | 0.0095 | 0.0070 | −0.0025 |
| Sharpe | 0.5690 | 0.3803 | −0.1887 |
| max_drawdown | −0.0252 | −0.0242 | +0.0010 |
| win_rate | 0.731 | 0.714 | −0.0165 |
| Deflated Sharpe | 0.4159 | 0.2968 | −0.1192 |

## Lectura

- Con la ejecución realista (lag=1) el backtest rinde MENOS: Sharpe 0.57 → 0.38 (−33%),
  CAGR 0.95% → 0.70%. Es el efecto esperado: parte del "alpha" medido con lag=0 era un
  artefacto de lookahead (decidir con el cierre de `date` y ejecutar al MISMO cierre).
- El max_drawdown mejora marginalmente (menos profundo) y n_trades sube +2 en este
  universo/periodo (el desplazamiento cambia el gate de cooldown/regime en algunos lunes).
- El slippage calibrado (`COST_PER_SIDE=0.0005`) NO compensa el gap entre cierre-decisión
  y apertura-ejecución: el sesgo persiste y es medible.
- Conclusión operativa: el fix es correcto y se adopta como default (`EXECUTION_LAG_DAYS=1`).
  Los backtests históricos corridos con el motor previo sobreestimaban rendimiento.

## Cómo se implementó (resumen)

- `backend/app/core/backtest_engine.py`: parámetro `execution_lag_days: int = 1` en `run()`.
  - Entradas: señal generada con el cierre de `date` → se ejecuta a `open[next_date]`, con
    `entry_date = next_date`. El score/factores/ATR de `date` siguen siendo el insumo de la
    decisión (no cambia el criterio de selección, solo el precio/fecha).
  - Salidas (stops `check_all_stops` y técnicas): un stop detectado con el cierre de `date`
    se ejecuta a `open[next_date]`.
  - `_build_calibration_dataset`: misma regla (entry = `open[i+1]`), para no volver a
    calibrar sobre el sesgo.
  - `execution_lag_days=0` = comportamiento ANTERIOR (el bug).
- `backend/app/config.py`: `EXECUTION_LAG_DAYS: int = 1`.
- `backend/tests/test_backtest_engine.py` (nuevo): 3 tests — entrada en open siguiente con
  gap +5%, lag=0 conserva el cierre de la señal, y salida en open siguiente.
- `backend/app/core/barrier_labeling.py`: docstring actualizado al nuevo timing + se agregó
  `verify_fidelity()` (verificaba el espejo de las reglas de barrera con `adaptive_risk.py`).

## Tests

- Suite completa `backend/.venv/bin/python -m pytest -q`: verde (275 base + 3 nuevos de
  backtest_engine + 1 nuevo de verify_fidelity). No se introdujeron rojos nuevos.
