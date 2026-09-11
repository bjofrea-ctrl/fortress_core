# Auditoría de utilidad del dashboard — ¿lo que muestra sirve al análisis definido?

> ⚠️ SUPERADO por `AUDITORIA_DASHBOARD_UTILIDAD_20260911.md` (formato oficial con las 6 dimensiones
> pedidas + tablas por sección + resumen priorizado). Este archivo queda como borrador de trabajo.
> No borrar: conserva el historial de la primera pasada.

Fecha: 2026-09-10 · Rama: `audit/dashboard-utilidad` (off `main` c345072) · **solo auditoría, cero fixes de código**
Método: mapear cada sección/dato del dashboard contra (a) su fuente real en el backend y (b) lo que el
propio proyecto definió como su análisis — `ONBOARDING.md`, `ROADMAP.md`, `DISENO_INSTRUMENTO.md`,
`DICCIONARIO_INDICADORES.md`. Veredicto por campo: **ALTA** (sirve directo al análisis) / **MEDIA**
(útil pero con vacío de contexto/caveat) / **BAJA** (poca utilidad o riesgo de lectura).

---

## 1. Resumen ejecutivo

El dashboard ES básicamente fiel al propósito: la **Mesa+Detalle** muestra el instrumento diagnóstico
real (M2 calibrado, gates del motor, tesis de salida, evidencia del ledger, costo medido). La tab
**Fundamentos** embebe el motor canónico completo (Greenblatt/Piotroski/Altman/Beneish) con datos
reales. Los problemas de utilidad NO están en "dato inventado" (no encontré ninguno: toda fuente se
rastrea a un artefacto o al motor) sino en **cuatro vacíos de contexto** que degradan la utilidad real:

1. **La tab Portfolio muestra el BASELINE de investigación sin vintage ni caveat.** `backtest_results.json`
   (CAGR 0.41%, arranca 2019-01-02) se presenta como "curva de capital" y KPIs sin avisar que es el
   backtest de un FIX DE INVESTIGACIÓN (no la operativa, no un resultado validado por DSR/PBO).
2. **La palabra "INVERTIR" en la Mesa** sin que exista señal comercial validada (ONBOARDING: más evidencia
   de que NO hay señal que nunca). El badge de honestidad lo mitiga, la semántica del estado no.
3. **Detalle de costa vs fondo**: el modo "TradingView" (widget externo) y "Lightweight (EOD)" se
   duplican; el chart local es el único que pinta las zonas mecánicas. No es inútil, es redundante.
4. **Portfolio sin drill-down**: cuál run generó `backtest_results.json`, con qué params y universos.

Ninguno se arregló (regla de esta tarea). Priorización al final.

---

## 2. Marco: qué análisis definió el proyecto (fuente de verdad)

**Fundamental** (`PLAN_MOTOR_FUNDAMENTALES_AUTOMATIZADO.md`, `fundamentals_screen.py::compute_indicators`):
el motor canónico AAI calcula exactamente la batería Greenblatt/Piotroski/Altman/Beneish: ROIC (NOPAT/invested
capital) + EV/EBIT (Greenblatt), ROE, gross margin, FCF/NI, buyback yield, Piotroski F-score, Altman Z,
Beneish M, P/E, upside vs price-target-consensus, fair value label (líneas 178-266). Fuente: estados EDGAR
(99/100 con cobertura) + foto de mercado FMP (backfill del 2026-09-10, `PRE_REG_PROFILE_EDGAR_BACKFILL`).

**Técnico** (`DICCIONARIO_INDICADORES.md` + `signal_engine`): las gates del motor usan EMA50/EMA200 (tendencia),
ADX14 (fuerza), RSI14 (momentum/sobrecompra), volume_ratio (confirmación), ATR14 (stops 2×ATR / target 4×ATR),
régimen HMM 4 estados (`.core.regime_classifier`: GOLDILOCKS/REFLATION/DEFLATION/STAGFLATION).
Momentum 12-1, MACD, Bollinger, Stochastic existen en `calculate_all_indicators` (market.py los expone) pero NO
entraron como gates (ver `RESUMEN_VALIDACION_VARIABLES.md` — refutados/validados según el caso).

**Instrumento diagnóstico** (`DISENO_INSTRUMENTO.md`): M2 (score calibrado + intervalo + abstinencia + cobertura
empírica), M1 (etiquetado por barreras = réplica de las reglas de salida), M3 (compuerta de régimen), M4 (costos
medidos), M5 (deriva), M6 (ledger). Filosofía: "mejor perder poco que ganar mucho" → salir cuando se pierde la tesis.

**Restricción honesta (no negociable)**: ONBOARDING: "hoy no hay señal comercial verificada". El
dashboard lo declara en el badge fijo y en cada respuesta (`honesty_badge`).

---

## 3. Inventario sección por sección

### 3.1 MESA (tab "Mesa de decisión")

| Sección / dato | Componente | Endpoint | Fuente real | Utilidad | Evidencia |
|---|---|---|---|---|---|
| Banner régimen + staleness | MesaView | `/api/advisor/universe` | `_staleness()` sobre `_cache_date()` (cache OHLCV real) | **ALTA** (meta-dato de confianza esencial) | advisor.py 127-135; MAX_STALE_BD=2 |
| `blocked_reason` (DEFLATION → bloqueo entradas) | MesaView | idem | `blocked_reason` real del régimen | **ALTA** | advisor.py 577-580 |
| Estado INVERTIR/VIGILAR/NO_INVERTIR | MesaView | idem | `_compute_ticket` → `generate_signal` (motor real) | **MEDIA** (ver §4.2: semántica sin validación) | advisor.py 292-328 |
| Win prob | MesaView | idem | calibrador M2 (`ProbabilityCalibrator`) | **ALTA** (instrumento M2; siempre con "—/abstención") | advisor.py 71-98, 308 |
| Proyección (§29, etiquetas con n) | `ProjectedBadge` | idem | `_projected_label` con evidencia VPP real n=8/19 | **ALTA** (mapea a la única selectividad medida) | advisor.py 86-97 |
| Dist EMA50 / EMA200 | MesaView | idem | del motor (`generate_signal` reusa indicadores) | **ALTA** (filtro de tendencia definido) | advisor.py 313-326 |
| Stop / Target | MesaView | idem | zonas mecánicas (2×ATR/4×ATR) — honestas por diseño | **ALTA** (a sabiendas que son zonas, no predichos) | DetailView docstring 19-21 |
| Δ transición | MesaView | idem | `_transition` vs `decision_states` previos | **MEDIA** (útil, sin explicación de definición) | advisor.py 352-354 |
| Expand de fila: razón, score, payoff, ATR, gates, M2 | MesaView (FragmentRow) | idem | ticket completo | **ALTA** (transparencia de la decisión completa) | MesaView 161-200 |
| Filtro por estado / orden institucional | MesaView | idem | estado+win_prob | **MEDIA** (utilidad operacional, no analítica) | MesaView 15-30 |

### 3.2 DETALLE (tab Mesa → fila → "Ver detalle")

| Sección / dato | Componente | Endpoint | Fuente real | Utilidad | Evidencia |
|---|---|---|---|---|---|
| Chart Lightweight EOD (400 barras, EMA50/200 overlay) | TradingViewChart | `/api/advisor/{symbol}` | parquet OHLCV real + overlays del motor | **ALTA** | advisor.py 541-563 |
| Widget TradingView externo | TVWidget | externo | proveedor ajeno | **BAJA-MEDIA** (duplicado; no pinta zonas del proyecto) | DetailView 74-76 |
| Veredicto: reason, score, Win prob, ATR, Payoff | DetailView | idem | `_compute_ticket` real | **ALTA** | DetailView 81-88 |
| Gates técnicos (Trend/ADX/RSI/Vol) | DetailView | idem | `sig["indicators"]` del motor | **ALTA** (definidos en metodología) | client.ts 80-87 |
| M2: punto/intervalo/abstención | DetailView | idem | calibrador conformal real | **ALTA** (núcleo del diseño M2) | MesaView 180-185 |
| Plan de salida (partial TP/trailing/technical/regime stop) | DetailView | idem | `_exit_plan(regime_state)` — mecánica real del motor | **ALTA** | advisor.py 539; ROADMAP verif. 2026-08-19 |
| Tesis de entrada + razones de degradación | DetailView | `/api/advisor/theses` | snapshot persistido `decision_theses.json` | **ALTA** (filosofía operacionalizada) | advisor.py 396-412; 629+ |
| Fundamentales EDGAR o "sin cobertura" honesto | DetailView | `/api/advisor/{symbol}` | `get_edgar_fundamentals()` | **ALTA** (null honesto, nunca inventado) | advisor.py 565-568 |

### 3.3 PORTFOLIO

| Sección / dato | Componente | Endpoint | Fuente real | Utilidad | Evidencia |
|---|---|---|---|---|---|
| KPI: CAGR/Sharpe/MaxDD/PF/TotalTrades | KPICards | `/api/backtest/metrics` | `data/backtest_results.json` (baseline) | **MEDIA** — **caveat de vintage ausente** (§4.1) | backtest.py 23-32; artifact real CAGR 0.41% |
| Curva de capital + drawdown | EquityCurve | `/api/backtest/equity-curve` | mismo baseline JSON | **MEDIA** — mismo caveat + sin fecha visible | backtest.py 35-59 |
| Régimen HMM 4 estados | RegimePanel | `/api/risk/monitor` | `PortfolioSnapshot` (fortress.db) + `regime_classifier` | **ALTA** (compuerta M3 real) salvo `no_data` si no hay snapshot | risk.py 20-38 |
| Riesgo adaptativo (equity/drawdown/positions/violations_60d) | RiskPanel | `/api/risk/monitor` | fortress.db (RiskEvent) | **ALTA** | risk.py 26-38 |
| Trades Reales (backtest + PAPER con origin explícito) | TradesTable | `/api/trades/combined` | backtest JSON + `signal_ledger` en fortress.db | **ALTA** (distingue backtest de paper real) | trades.py 147-184 |
| Monte Carlo (Media P&L, percentiles) | MonteCarloPanel | `/api/backtest/monte-carlo` | baseline JSON (MC del backtest) | **MEDIA** — mismo caveat de baseline | backtest.py 91-100 |
| Distribución de trades | TradeDistribution | `/api/backtest/trades` | baseline JSON trades | **MEDIA** — mismo caveat | backtest.py 62-88 |

### 3.4 GOBERNANZA

| Sección / dato | Componente | Endpoint | Fuente real | Utilidad | Evidencia |
|---|---|---|---|---|---|
| Resumen de mercado | MarketOverview | `/api/market/overview` | OHLCV cache + maestro | **MEDIA** (contexto macro, sin metodología propia) | market.py |
| Gobernanza multi-agente | GovernancePanel | `/api/governance/analyze/{sym}` + `/status` | tríada→controlador→profesor NIM (LLM real, fallback determinista, rate-limited) | **MEDIA-ALTA** (segunda opinión explícitamente no validada; A9 declara modo) | governance.py 1-30, 57-86; panel 64-69 |
| Oportunidades (motor) | OpportunitiesPanel | `/api/opportunities/today` | motor real (SignalEngine + régimen + universe canónico 50) | **ALTA** (filtros ADX/RSI/Momentum/Tendencia = métodos definidos) | opportunities.py 19-27 |

### 3.5 FUNDAMENTOS

| Sección / dato | Componente | Endpoint | Fuente real | Utilidad | Evidencia |
|---|---|---|---|---|---|
| Screener completo del motor canónico (iframe) | FundamentalsPage | `/api/fundamentals/screen/dashboard.html` | HTML generado por `fundamentals_artifacts.render_artifacts` (cron 22:30) desde `screen_<fecha>.json` | **ALTA** (Greenblatt/Piotroski/Altman/Beneish reales; tras fix 10-09: 47/47 con price/mcap) | fundamentals_screen.py 142-161; verif. real 09-10 |

### 3.6 Globales

| Sección / dato | Componente | Endpoint | Fuente real | Utilidad | Evidencia |
|---|---|---|---|---|---|
| Ticker en vivo (contrato propio) | LiveTicker | propio | mercado en vivo | **MEDIA** (contexto, no ingresa al motor) | Layout 100 |
| Costo real por lado — M4 | CostField | `/api/costs/current` | medición real de ejecución (paper) o "SIN MEDICIÓN" honesto | **ALTA** (única fuente de costos medidos; caveat papel en tooltip) | CostField 1-54 |
| Evidence footer (ledger de trials + B5) | EvidenceFooter | `/api/advisor/evidence` | `trial_registry` (ledger de verdad) | **ALTA** (firma institucional del proyecto) | EvidenceFooter 1-61 |
| Badge honestidad | Layout | universo | `honesty_badge` real | **ALTA** | Layout 90-96; advisor 378-382 |

---

## 4. Auditoría dato-a-dato — hallazgos críticos

### 4.1 (MEDIA) Portfolio sin vintage ni caveat — utilidad condicionada
`backtest_results.json` es un artefacto real pero **sin metadatos de run** expuestos en la UI: no muestra
cuál trial, qué universo, qué fix de ejecución (execution_lag=1), ni el veredicto DSR/PBO de ese baseline.
Como la UI lo presenta como "Curva de capital (baseline)" (título correcto), el riesgo es que un lector lo
lea como resultado de la operativa actual. **Veredicto**: dato real pero necesita vintage + caveat inline.

### 4.2 (RIESGO de lectura) La semántica "INVERTIR" sin señal validada
El estado viene del motor, no es inventado; pero ONBOARDING afirma que no hay señal comercial verificada.
Mostrar una columna de estados con "INVERTIR" + Stop/Target fomenta lectura accionable aun con el badge
("APOYO A DECISIÓN — SIN SEÑAL COMERCIAL VALIDADA"). El propio diseño M2 dice "mejor abstenerse" (80% de
abstención es éxito). **Veredicto**: utilidad MEDIA como diagnóstico; riesgo ALTO si se lee como orden de
compra. Sugerencia (no implementada): anclar caveat por fila y priorizar la visibilidad de la abstención M2
sobre el estado.

### 4.3 (BIEN RESUELTO) La honestidad no es decorativa
Toda cifra dura visible (win_prob, proyección con n, costo real, ledger, staleness, blocked_reason) tiene
fuente real y caveat adjunto (tooltips). No encontré "dato fantasma" ni hardcode de números de análisis.

### 4.4 (MEDIA) Doble chart en detalle
Lightweight (EOD, con zonas del proyecto) + TV widget (externo, sin zonas). El modo TV es útil para
inspección rápida pero duplica sin sumar; el local es el analítico. No es un error, es redundancia.

### 4.5 (Verificaciones, no defectos)
- `FundamentalsPage` maneja correctamente 503/fallo del cron con mensaje accionable (no tab rota).
- `market/indicators` expone 16 indicadores calculados (MACD/BB/Stoch/Momentum 12-1) pero Mesa/Detalle solo
  usan los gates definidos. Cobertura no consumida, no inutilidad.
- La utilidad del tab Fundamentos dependía del bug EDGAR (profile stub) que se corrigió hoy en la rama
  `fix/fundamentals-profile-backfill` (47/47 con precio y market_cap).

---

## 5. Conclusión

**Utilidad real del dashboard: favorable.** La Mesa/Detalle y Fundamentos son el instrumento diagnóstico
que el proyecto se propuso (M2 calibrado, gates definidos, tesis de salida, ledger, costos medidos, motor
canónico fundamental completo) con datos rastreables a su fuente. Los puntos débiles son de
**contexto/presentación**, no de fuente: falta vintage+caveat en el Portfolio baseline y existe la tensión
semántica "INVERTIR" sin señal validada. El incidente de hoy (Fundamentos 0/47 con precio por el bug EDGAR)
quedó corregido; esta auditoría confirma que la utilidad del tab dependía de ese backfill.

## 6. Recomendaciones (para decidir; NO implementadas hoy)

| # | Acción | Impacto en utilidad | Esfuerzo relativo |
|---|---|---|---|
| R1 | Portfolio: mostrar fecha/vintage + caveat del baseline (`generado dd/mm/aa · no validado DSR/PBO · execution_lag=1`) | Media-alta | Bajo (meta en backend + etiqueta) |
| R2 | Mesa: anclar caveat por fila o colapsar "INVERTIR" detrás de la abstención M2 | Alta (semántica) | Medio |
| R3 | Detalle: modo default Lightweight; TV explícito como "inspección" | Media | Bajo |
| R4 | Gobernanza: timestamps de la discusión para auditabilidad (sigue A9) | Media | Bajo |
| R5 | Oportunidades: mantener; refresco universe 50 por rueda (verificado 08-19) | — | — |
| R6 | Siguiente auditoría: contrastar columna por columna el iframe de Fundamentos contra `compute_indicators` → `screen_<fecha>.json` | — | — |

Método de esta auditoría: lectura de código (frontend y backend), endpoints listados, artefactos reales
abiertos (`backtest_results.json`, `screen_<fecha>.json`, `state.json`), pre-registros vigentes. Ningún dato
mostrado quedó sin rastro a su fuente.