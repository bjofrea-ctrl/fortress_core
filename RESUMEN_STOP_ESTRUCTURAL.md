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

A/B corrido como dos armadas paralelas (mismo período/universo/config; ver artefactos
`*_211537.txt` estructural y `*_013350.txt` baseline — `compare_structural_stop.py` con
`ARM=baseline|estructural`). Métricas sobre **2021-01-01 → 2023-12-31**, universo 50,
capital 25000, commission 0.001, slippage 0.0005, `execution_lag_days=1`.

| Métrica | baseline (ATR) | estructural (T1.4) | Δ (estruct − base) |
|---|---|---|---|
| trades | 91 | 31 | −60 (−66%) |
| Sharpe | 0.2841 | 0.3818 | +0.0977 |
| CAGR | 0.0074 | 0.0047 | −0.0027 |
| max drawdown | −0.0268 | −0.0216 | +0.0052 (menos DD) |
| win rate | 0.5714 | 0.7097 | +0.1383 |
| profit factor | 1.3660 | 1.7288 | +0.3628 |
| deflated Sharpe | 0.2411 | 0.2923 | +0.0512 |
| sortino | 0.3514 | 0.3021 | −0.0493 |
| calmar | 0.2767 | 0.2174 | −0.0593 |
| RR medio señales | 2.000 (n=333, n_struct=0) | 2.330 (n=38, n_struct=38) | +0.33 |
| avg PnL/trade | +9.84 (total +895.55) | +15.09 (total +467.91) | — |
| RR gate | — | 38 señales → 31 trades (filtra 60% vs baseline) | — |

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

**INFORMATIVO — NO se promueve a default.** La variante estructural **filtra ~66% de los
trades** (91 → 31) por el gate `RR ≥ 1.5` sobre el target más cercano — exactamente el
comportamiento esperado documentado en "Lectura esperada". Con menos trades: win rate
sube (0.57 → 0.71), profit factor sube (1.37 → 1.73), Sharpe sube (0.28 → 0.38) y DD
mejora (−2.68% → −2.16%), pero **CAGR cae** (0.74% → 0.47%) y el total PnL cae
(+895 → +467) — menos exposición, no más alpha. El RR medio estructural es 2.33 vs 2.0
del baseline (la jerarquía a veces elige targets más lejanos que 4×ATR). **Ninguna
métrica supera la vara del repo** (W1/W2/W3, DSR ≥ 0.90, walk-forward) — este A/B es
solo comparativo descriptivo sobre un único período (W2 + 2021), sin corrección
por múltiples ventanas ni DSR walk-forward. La promoción requeriría trial pre-registrado
propio (regla no negociable). `use_market_structure` queda **disponible pero no default**
(`False` por defecto, camino bit-idéntico al baseline; fidelity `barrier_labeling`
no afectada — la resolución toca solo stop/target reportados, no `check_all_stops`).

## Archivos

- `backend/scripts/compare_structural_stop.py` — runner A/B (período/armada por argv,
  RR medio, resumen de trades).
- `backend/data/cache/compare_structural_stop_20260821_211537.txt` — armada estructural
  (31 trades, métricas + RR 2.33) y `compare_structural_stop_20260822_013350.txt` —
  armada baseline (91 trades, métricas + RR 2.0). Ambas sobre el mismo período/universo.
- `backend/app/core/signal_engine.py` (`_resolve_stop`, `_resolve_target`, `MIN_RR=1.5`,
  `market_structure` param con fallback idéntico), `backend/app/core/backtest_engine.py`
  (`use_market_structure`, `market_structure_history` causal), `backend/app/core/market_structure.py`
  (`market_structure_history`, `structure_row_to_dict`). Tests `tests/test_signal_engine.py`
  (4 nuevos T1.4) + `tests/test_market_structure.py` (4 nuevos history causal) — suite
  `test_signal_engine + test_market_structure` 37 passed, ruff limpio.

## Criterios de aceptación (T1.4, líneas 595-605)

1. ✅ `market_structure=None` idéntico al baseline (stop entry−2ATR, target entry+4ATR, RR 2.0)
   — `test_generate_signal_none_structure_identico_al_baseline`.
2. ✅ Order block sintético debajo del entry → stop en `ob_bottom −0.20·ATR` (fallback si
   mitigado o por encima) — `test_resolve_stop_uses_order_block_under_entry`.
3. ✅ Target estructural cercano con RR < MIN_RR → `None` (no recorta) —
   `test_rr_gate_rejected_when_target_too_close` + positivo `test_rr_gate_accepts...`.
4. ✅ A/B backtest documentado (esta sección, artefactos arriba, período 2021-2023, universo 50).
5. ✅ `pytest tests/test_signal_engine.py -v` verde (19/19, 4 nuevos T1.4).