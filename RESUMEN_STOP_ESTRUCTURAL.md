# Resumen — T1.4: Stop/target estructural vs baseline ATR (A/B backtest)

Fecha: 2026-08-21 · Ticket T1.4 de `PLAN_INTEGRACION_INDICAGENT.md` (líneas 524-609)

**Código:** ya implementado (sesión previa): `_resolve_stop` (jerarquía
order_block → liquidity_sweep → nearest_swing_low → fallback 2×ATR), `_resolve_target`
(fvg → nearest_resistance → min(candidates) → fallback 4×ATR), gate `MIN_RR = 1.5`,
y `use_market_structure` en `backtest_engine.run()` con `market_structure_history`
causal precomputada por símbolo. Este documento cierra el **criterio 4 del ticket**
(líneas 602-604): el comparativo A/B sobre el mismo período y universo.

## Método

- **A/B**: misma data, mismas fechas, misma configuración; ÚNICA diferencia
  `use_market_structure=True` vs `False` en `BacktestEngine.run()`.
- **Período**: 2021-01-01 → 2023-12-31 (sugerido por el ticket/contexto de la ronda;
  cubre completo W2 2022-2023 y el año 2021 de W1; W3 2024+ queda fuera).
- **Universo**: 50 símbolos (7 base + NEW_UNIVERSE de 43), datos de `data/cache/*.parquet`
  (sin descargas nuevas).
- **Config**: capital 25000, commission 0.001, slippage 0.0005, `execution_lag_days=1`
  (fix T0.2 vigente), sin sentiment ni fundamentals (aislar el efecto estructural).
- **Runner**: `backend/scripts/compare_structural_stop.py` (armada por argv, ejecutadas en
  paralelo; salida en `backend/data/cache/compare_structural_stop_*.txt`).
- **RR medio**: payoff teórico (`reward/risk`) de las señales emitidas en el loop
  principal, capturado por monkeypatch no invasivo de `generate_signal` (solo
  `date ≥ start`; la recalibración previa no contamina el conteo).

## Resultados

<!-- Tabla A/B a completar tras el backtest -->

| Métrica | baseline (ATR) | estructural (T1.4) | Δ |
|---|---|---|---|
| trades | — | — | — |
| Sharpe | — | — | — |
| CAGR | — | — | — |
| max drawdown | — | — | — |
| win rate | — | — | — |
| RR medio señales | — | — | — |
| profit factor | — | — | — |
| deflated Sharpe | — | — | — |

## Lectura esperada (documentada antes de ver los números)

- Con `use_market_structure=True` el gate `RR ≥ MIN_RR` **filtra señales** (el target
  estructural más cercano suele dejar RR < 1.5) → menos trades que el baseline. ESO es
  parte del hallazgo, no un defecto: el baseline siempre emite con RR exacto 2.0
  (4×ATR/2×ATR).
- Un veredicto de "no mejora" NO refuta la resolución estructural en sí: mide si la
  jerarquía SMC + puerta RR, tal como está configurada, traduce en mejor resultado
  sobre este período/universo.
- La promoción a default (si el A/B favorece la variante estructural) requeriría trial
  pre-registrado propio con la vara del repo (W1/W2/W3, DSR ≥ 0.90, n_trials+1) —
  regla no negociable.

## Veredicto

*(completar tras el backtest: ¿mejora? ¿se promueve a default?)*

## Archivos

- `backend/scripts/compare_structural_stop.py` — runner A/B (mejorado en esta sesión:
  período/armada por argv, RR medio, resumen de trades).
- `backend/data/cache/compare_structural_stop_*.txt` — salidas crudas de las armadas.
- `backend/app/core/signal_engine.py`, `backend/app/core/backtest_engine.py` — código T1.4
  (sin cambios en esta sesión; solo verificación).