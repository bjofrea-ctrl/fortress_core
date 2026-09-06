# PRE-REGISTRO — B8: win-rate/R:R real del motor + cap de sizing regime-aware

**Fecha**: 2026-09-06 · **Autor**: Claude Code (Boris aprobó, ver conversación) · **Ticket**: B8 (nuevo, no estaba en `PLAN_REMEDIO_BRECHAS_20260903.md`)

## 1. Motivación (por qué existe este ticket)

Boris propuso probar un perfil de money-management: riesgo 1%/trade, win-rate
25-40%, ~30 trades/mes, reward:risk 4-8:1, 24 meses. Simulación Monte Carlo
(5.000 trayectorias, 720 trades, compounding de fracción fija 1%) dio:

| win rate | R:R | E[R]/trade | CAGR mediana (24m) | maxDD mediana |
|---|---|---|---|---|
| 0.25 | 4:1 | 0.25R | 126% | 25% |
| 0.30 | 6:1 | 1.10R | 4.196% | 15% |
| 0.40 | 8:1 | 2.60R | 741.591% | 10% |

**Veredicto de la simulación**: incluso la esquina más conservadora del rango
compone a un CAGR que no existe en ningún track record real en 2 años. Esto
NO es un bug de la simulación — es la matemática de compounding a fracción
fija sobre 720 "trades" **asumidos independientes**. Dos supuestos rotos:

1. **Independencia falsa**: 30 trades/mes sobre un universo de 102 acciones
   correlacionadas (mismo mercado, mismo régimen HMM) tienen un N efectivo
   muy menor a 720 — el riesgo real de cola es mayor que el que asume un
   Bernoulli i.i.d.
2. **Win-rate/R:R no medido**: el 25-40%/4-8:1 es una firma de sistema mucho
   mejor que el edge que el proyecto tiene validado hoy (DSR=0.6077 histórico,
   Sharpe diario plausible ~0.10, ver `ANALISIS_MDE_GATE_DICIEMBRE_2026.md`).
   No hay evidencia de que el motor real produzca esos números.

## 2. Qué mide este ticket (dos entregables separados, no un trial de edge)

**2a. Medición (no trial, no consume slot Bonferroni)**: instrumentar el
`signal_ledger` para calcular, sobre las señales YA CERRADAS (`status='closed'`)
del motor real (paper trading + histórico si aplica):
- win-rate real: `% de trades con pnl_r > 0`.
- R:R real realizado: `mediana(pnl_r | pnl_r>0) / abs(mediana(pnl_r | pnl_r<0))`.
- frecuencia real: trades/mes efectivos (no asumidos).
- Reportar estos 3 números con intervalo de confianza (bootstrap, no asumir
  normalidad — n va a ser chico al día de hoy). Si el ledger no tiene
  suficientes trades cerrados (`n < 30`), el output debe decir explícitamente
  "n insuficiente para estimar, no inventar un número" — no rellenar con el
  25-40%/4-8:1 de la simulación.
- Script: `backend/scripts/measure_realized_edge.py` + test con ledger
  sintético (casos: n=0, n<30, n≥30 con distribución conocida para validar
  el cálculo).

**2b. Cap de sizing (usa `adaptive_risk.py`, no lo reemplaza)**: agregar un
techo de crecimiento tipo fractional-Kelly al `AdaptiveRiskManager` existente:
- Nueva función/método que, dado el win-rate/R:R REAL medido en 2a (no el
  asumido), calcule el Kelly óptimo y aplique una fracción conservadora
  (p.ej. Kelly/4, parametrizable) como techo de `risk_per_trade` — nunca el
  1% fijo sin límite superior de crecimiento.
- Debe integrarse con `get_regime_thresholds()` existente: el cap por Kelly
  fraccionario se combina (mínimo) con el `max_exposure` ya definido por
  régimen — no lo reemplaza, lo acota más cuando corresponde.
- Si 2a devuelve "n insuficiente", el cap debe usar un default conservador
  documentado (no el Kelly de la simulación optimista) — declarar cuál y por
  qué.
- Tests: caso con edge medido positivo claro (Kelly cap correcto), caso con
  edge medido negativo o insuficiente (cap conservador, no Kelly negativo
  aplicado a ciegas).

## 3. Qué NO hace este ticket

- No promete ni valida que el motor real vaya a lograr 25-40%/4-8:1 — esa
  combinación queda documentada como firma ASPIRACIONAL, no como parámetro
  de producción.
- No toca el criterio DSR del gate de diciembre (eso es C1, ya resuelto por
  separado).
- No es un trial de `trial_registry` — es instrumentación + gestión de
  riesgo, igual categoría que A2 (measurement/infra), no consume slot.

## 4. Criterio de cierre

- `measure_realized_edge.py` corre sobre el ledger real y da un resultado
  (número real o "n insuficiente", nunca inventado).
- `AdaptiveRiskManager` tiene el cap fractional-Kelly integrado y testeado.
- Commit con referencia a este documento; NO mergear a main sin verificación
  independiente (correr los tests, no aceptar el self-report).
