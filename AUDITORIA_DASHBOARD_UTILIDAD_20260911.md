# AUDITORÍA — Utilidad del dashboard, sección por sección y dato por dato

Fecha: 2026-09-11 · Rama: `audit/dashboard-utilidad` · **Evaluación pura: cero código tocado.**
Fuente de verdad: ONBOARDING.md, ROADMAP.md, DISENO_INSTRUMENTO.md, DICCIONARIO_INDICADORES.md.
Método: (1) cada sección → endpoint → `archivo:función` que calcula el dato; (2) claves JSON del
backend vs lecturas literales del frontend (sincronía real, no inspección visual); (3) artefactos
locales abiertos; (4) cada dato se califica en las 6 dimensiones pedidas (la columna Sinc. es
definitoria: Sí con evidencia / No + qué falla). Gama de Utilidad: Alta/Media/Baja/Nula.

**Operatividad verificada hoy:** Mesa/Detalle (motor puro, sin pipeline), CostField M4 (persistido),
Evidence (trial_registry vivo), Fundamentos (cron 22:30, artefactos 08/09-09 vigentes) son vivos.
Atención local: `fortress.db` 0 filas en `portfolio_snapshots`/`signal_ledger` y
`decision_states*.json` ausente — el Portfolio-real y las tesis sólo viven si el pipeline los escribe
(verificar en VPS/espejo antes de declararlo en producción; la UI maneja `no_data`/vacío sin romper).

## A. Marco del análisis definido

**Fundamental** (`compute_indicators` 178-266): Greenblatt (ROIC, EV/EBIT) / Piotroski F / Altman Z /
Beneish M + ROE, margen bruto, FCF/NI, buyback, fcf_yield, P/E, upside vs consenso, fair value. Fuente:
EDGAR (99/100) + foto FMP (backfill 09-10).

**Técnico** (`DICCIONARIO` + `signal_engine`): gates EMA50/200 (tendencia), ADX14 (fuerza), RSI14,
volume_ratio, ATR14 (stops 2×/target 4×), HMM 4 regímenes (GOLDILOCKS/REFLATION/DEFLATION/STAGFLATION).

**Instrumento** (`DISENO_INSTRUMENTO`): M2 calibrado (win_prob+intervalo+abstención), M1, M3, M4, M5, M6.
"Perder poco > ganar mucho" → exit thesis.

**Límite honesto**: sin señal comercial verificada (ONBOARDING; badge fijo + `honesty_badge`).

## B. MESA — tabla de tickets (fuente: `advisor.py:advisor_universe`)

| Dato | Fuente backend | Sinc. | Utilidad | Justificación |
|---|---|---|---|---|
| Estado INVERTIR/VIGILAR/NO_INV | `_compute_ticket` (`decision.py:99`) vía `generate_signal` | **Sí** — `t.state` leído literal (`MesaView.tsx:21,144`) | Media | Motor real; sin señal validada (ONBOARDING) es diagnóstico, no orden. |
| Cierre | `close` en `_build_tickets_sync` (`advisor.py:309`) | **Sí** — `fmtPrice(t.last_close)` (146) | Alta | Ancla técnico del ticket. |
| Win prob | calibrador M2 (`decision.py:118`) | **Sí** — `%` o "—" si null (148-149) | Alta | Núcleo M2; null honesto fuera de gate. |
| Proyección §29 + n | `_projected_label` (`advisor.py:86-97`, n=8/19) | **Sí** — badge + `n=` + tooltip evidence (`Badges.tsx:20-23`) | Alta | Única selectividad medida, siempre citada. |
| Dist EMA50 / EMA200 | `advisor.py:325-326` (reuse indicadores) | **Sí** — `fmtPct` + sort dedicado (27-28,151-156) | Alta | Filtro de tendencia definido. |
| Stop / Target | zonas mecánicas 2×ATR/4×ATR | **Sí** — rojo/verde + `fmtPrice` (157-158) | Alta | Honestas por diseño (zonas, no predicción). |
| Δ transición | `_transition` vs estados previos (`advisor.py:352-354`) | **Sí** — glyph (159, `Badges.tsx:41-54`) | Media | Sin explicación inline de la definición. |
| Expand: razón/score/payoff/ATR | ticket completo | **Sí** (166-168) | Alta | Transparencia total de la decisión. |
| Expand: gates Trend/ADX/RSI/Vol | `sig["indicators"]` (`decision.py:136-144`) | **Sí** — `.toFixed` con guards (174-175) | Alta | Los 4 gates definidos, nada más ni menos. |
| Expand: M2 + abstención | conformal (`decision.py:122-129`) | **Sí** — intervalo + ⚠ (180-185) | Alta | La abstención es el éxito según DISENO §8. |
| Banner régimen/stale/block | `_staleness` (`advisor.py:127-135`), `blocked_reason` DEFLATION | **Sí** (48-54, 43-47) | Alta | Meta-datos de confianza esenciales. |
| `factors` | `sig["factors"]` (`decision.py:166`) | **No consumido** — NADIE lo monta (`UniverseTable`/`DecisionPanel` muertos, `grep -l` vacío) | Baja (inutilizado, no inventado) | Dato real del motor sin lector → gap, no ruido. |
| Filtro/orden por estado | estado+win_prob | **Sí** (15-30) | Media | Operacional, no analítico. |

## C. DETALLE por símbolo (fuente: `advisor.py:advisor_symbol`)

| Dato | Fuente backend | Sinc. | Utilidad | Justificación |
|---|---|---|---|---|
| Chart EOD 400 barras + EMA50/200 | OHLCV parquet + overlays (`advisor.py:541-563`) | **Sí** (`TradingViewChart` 66-73) | Alta | Análisis técnico directo con datos reales. |
| Widget TradingView externo | externo | Sí (externo) | Baja-Media | Duplica sin zonas del proyecto; redundante. |
| Veredicto score/win_prob/ATR/payoff | `_compute_ticket` | **Sí** (81-88) | Alta | Resumen ejecutivo del ticket. |
| Gates + M2 + plan salida 4 mecánicas | `sig`, conformal, `_exit_plan(regime_state)` | **Sí** (ver §B; `o.exit_plan.partial_tp.trigger` leído en Opportunities 227-231; M1 en Detail) | Alta | Plan = mecánica real (PARTIAL_TP/TRAILING/TECHNICAL/REGIME_STOP). |
| Tesis entrada + razones | `_evaluate_thesis` (`advisor.py:629-674`) + snapshot `decision_theses.json` | **Sí** — status/entry/reasons leídos (`ThesisMonitor.tsx:57-66`) | Alta | "Perder poco" operacionalizado; reglas severas coherentes. |
| Fundamentales (15 ratios EDGAR) | `get_edgar_fundamentals` (`edgar_fundamentals.py:149`) → `RATIO_COLS` | **Sí** — genérico `Object.entries` (168-170) | Alta | Panel que crece con el panel sin hardcode. |
| "Sin cobertura" honesto | `fundamentals_coverage` (`advisor.py:568`) | **Sí** (179-186) | Alta | Nunca inventa. |

## D. PORTFOLIO (fuentes: `backtest.py` + `risk.py` + `trades.py`)

**Vintage del baseline (evidencia):** `backtest_results.json`: equity 25000→25614 (6 símbolos reales:
GOOGL/NVDA/AAPL/MSFT/AMZN/QQQ, salidas 2019-12→2024-11, 303 trades, 1510 pts). Es un FIX DE
INVESTIGACIÓN de 6 large-cap, NO el universo 50 ni el baseline vigente de ninguna Fase. Todos los
componentes manejan `no_data`/vacío sin romper (`KPICards.tsx:34`, `EquityCurve.tsx:33-36`,
`MonteCarloPanel.tsx:36`, `TradesTable.tsx:48`, `TradeDistribution.tsx:32-35`, `RiskPanel.tsx:26-29`).

| Dato | Fuente backend | Sinc. | Utilidad | Justificación |
|---|---|---|---|---|
| KPI (CAGR/Sharpe/MaxDD/PF/Trades) | `backtest.py:get_backtest_metrics` ← JSON base | **Sí** — valida `status!=="no_data"` (`KPICards.tsx:34,63-70`) | Media | Real pero es un baseline de 6 large-cap sin fecha/contexto visible → **roto como lectura** (§G). |
| Curva equity + drawdown | `backtest.py:get_equity_curve` (sampleo ≤300) | **Sí** (33-36) | Media | Idem §G. |
| Régimen HMM + Riesgo (equity/DD/posiciones/viol.60d) | `risk.py:risk_monitor` ← `fortress.db:portfolio_snapshots/risk_events` | **Sí** — keys 1:1 (`RiskPanel.tsx:9-14,42`; `RegimePanel.tsx:8-13,42,44`) | Alta | Compuerta M3 + riesgo vivos **si el pipeline escribe** (local: 0 filas → `no_data` honesto, no roto). |
| Trades backtest vs PAPER (origin explícito) | `trades.py` ← JSON base + `fortress.db:signal_ledger` | **Sí** — `origin` + filas abiertas (`TradesTable.tsx:123`) | Alta | La única vista que separa investigación de operativa real. |
| Monte Carlo (Media P&L/percentiles) | `backtest.py:get_monte_carlo` | **Sí** (16,36) | Media | MC del mismo baseline de 6 → §G. |
| Distribución de trades | `backtest.py:get_trades` (últimos 50/total 303) | **Sí** (32-35) | Media | Muestra truncada; marca `total` pero no la ventana. |

## E. GOBERNANZA (fuentes: `governance.py` + `opportunities.py` + `market.py`)

**Caso 1 verificado (sin tocar código): la capa lee bien.** `/status` manda `governance_llm_enabled`
(`governance.py:82-89`); el panel lee EXACTAMENTE ese flag (`GovernancePanel.tsx:186,202-223`) y nunca
infiere el modo de un texto; `blocked_by_a9` también mapeado (233-237,490-497). `/analyze/{sym}` devuelve
`predictive{decision...}` + `governance{triad,controller,judge,professor,final_decision,final_reason}`
(`governance.py:195-209` + `advanced_agents.py:597-707`): el frontend lee todas esas claves literales
(182,244-274,306-356,360-462,465-500) — **sincronía 100% verificada, cero campos huérfanos**.

| Dato | Fuente backend | Sinc. | Utilidad | Justificación |
|---|---|---|---|---|
| Badge modo + nota A9 | `/governance/status` → flag real | **Sí** (186-237) | Alta | Reactivación legible: nadie puede leer "LLM" donde hay fallback. |
| Tríada bull/bear/contrarian + consenso | `process_governance` (`advanced_agents.py:597-611`) | **Sí** — scores×100 + verdictos + `consensus.toFixed(3)` (243-274) | Media-Alta | Segunda opinión con LLM real cuando el flag lo permite; NUNCA validada como señal → consultiva. |
| Controller aprobado/rechazado + sizing/stops + risk checks | `controller` (613-626) | **Sí** — todos leídos incl. `risk_checks` iterado (306-394) | Alta | La única parte conectable a decisión real (approved/size). |
| Professor (reco/lecciones/RAG) + Judge (veredicto/razonamiento/condiciones) | `professor`/`judge` (667-707) | **Sí** — null-safe (`??`, `?.`, includes COMPRAR/VENDER) (317-356,397-434,436-462) | Media | Audit trail valioso; Juez muestra "status" cuando no interviene (702) — coherente. |
| Score/decisión/probabilidades predictivas | `predictive` (195-202) | **Sí** — `decisionColor` con fallback + `%` (182,277-299) | Media | Motor `heuristico_no_validado` declarado (predict.py) — consultivo. |
| Oportunidades: score/win_prob/factors/gates/entry/stop/TP/payoff/ATR/exit_plan/g2 | `opportunities.py:today` (136-155) | **Sí** — TODAS leídas con null-guards (`OpportunitiesPanel.tsx:166-231`, `win_prob`→"n/d") | Alta | El único "ranking accionable" del dashboard y es motor real (gates definidos). |
| MarketOverview: price/retornos 30d-90d-total/vol/52w/range_pos | `market.py:get_market_overview` (149-207, SYMBOLS canónicos) | **Sí** — sort Total/30D/vol (`MarketOverview.tsx` 27-60) | Media | Contexto técnico útil (posición en rango 52s, vol); NO es señal — bien presentado como tabla. |
| Header: ceiling/riesgo/LLM/phase | `/system/status` (`system.py`) | **Sí** — badges exactas (`Header.tsx:42-48`) | Alta | Parámetros de riesgo y modo visibles siempre. |
| LiveTicker 30s (price/change/%) | `/market/live/overview` (live.py, TTL 30s, yfinance) | **Sí** — click→detalle (`LiveTicker.tsx:73-80`) | Media | Contexto en vivo; NO alimenta el motor (TTL backend 300s EOD) — sin pretensión analítica. |

## F. FUNDAMENTOS + GLOBALES

**Caso 2 verificado (sin tocar código): backfill coherente de punta a punta.** `ingest_symbol` escribe
`profile{price>0,marketCap>0}` (medido 47/47 el 09-10); `get_edgar_fundamentals` es OTRA capa (panel
point-in-time `RATIO_COLS` para el Detail) y `screen_payload` lee `price/marketCap` del paquete
ingestado → el iframe canónico (`dashboard_<fecha>.html`, cron 22:30) y el Detail ven la misma foto.
El Detail muestra "sin cobertura" honesto cuando el panel no cubre (XOM-like) y el screen descarta
ella sola (no se inventa precio).

| Dato | Fuente backend | Sinc. | Utilidad | Justificación |
|---|---|---|---|---|
| Screener canónico completo (iframe) | `/api/fundamentals/screen/dashboard.html` ← `screen_<fecha>.json` (cron 22:30) | **Sí** — iframe + fallback 503 accionable (`FundamentalsPage.tsx:23-94`) | Alta | Greenblatt/Piotroski/Altman/Beneish reales sobre 47/47 con foto. |
| Panel Detail: 15 ratios EDGAR | `get_edgar_fundamentals` → `RATIO_COLS` (`edgar_fundamentals.py:51-55,149-170`) | **Sí** — genérico entries (168-170); `null`→"—" | Alta | Utilidad técnica directa; ojo: `sue_score` EXCLUIDO pre-registrado (línea 59) — coherente con el panel. |
| Costo real/lado M4 + slippage/curva | `/api/costs/current` ← medición ejec. persistida | **Sí** — `medido:false`→"SIN MEDICIÓN" honesto (`CostField.tsx:27-36`) | Alta | Base de todo neteo; tooltip con n/medición. |
| Evidence footer (ledger + B5) | `/api/advisor/evidence` ← `trial_registry` | **Sí** (`useAdvisorEvidence`→chip por familia) (`EvidenceFooter.tsx:45-58`) | Alta | Firma M6; B5 visible (inejecutables no se ocultan). |
| Badge honestidad + staleness | universe `honesty_badge`/`staleness` | **Sí** (`Layout.tsx:90-96`) | Alta | Límite de ONBOARDING siempre visible. |

## G. Resumen priorizado

### G1. Roto / desincronizado → arreglar primero
1. **Portfolio baseline sin vintage (§D).** El JSON de 6 large-cap se lee como "la cartera". Fix mínimo:
   título con fecha+universo del artifact + caveat de investigación; o esconder hasta que el baseline
   vigente lo reemplace. (Frontend-only, bajo riesgo.)
2. **`factors` del ticket sin lector (§B).** Dato real con 0 consumidores vivos (`UniverseTable`,
   `DecisionPanel` muertos). O se expone en el expand de la Mesa (1 fila) o se deja de computar para
   ahorrar payload. (Frontend o backend, ambos triviales.)

### G2. Ruido / redundante → candidato a sacar o colapsar
3. **Widget TradingView externo** (duplica el chart local sin zonas del proyecto).
4. **MarketOverview vs LiveTicker**: solapan "precio+variación" (EOD vs 30s). Utilidad distinta
   (contexto de rango vs pulso vivo) pero en la misma pantalla confunden; unificar en un solo bloque.
5. **`SystemStatus`/`PriceChart`/`SymbolSummary` muertos** (no montados salvo `Header`): borrar o revivir
   con dueño — hoy son peso muerto que confunde al próximo lector de código.

### G3. Gap real vs lo definido → falta
6. **Los 16 indicadores de `market/indicators` no se visualizan** (MACD/Bollinger/Stoch/Momentum existen
   calculados, la Mesa muestra 4 gates). Si la metodología los revalida, el Detalle es el lugar (1 panel).
7. **El `final_decision` de gobernanza no alimenta ningún ticket/mesa** (descriptivo por A9, por diseño).
   Gap conocido y declarado — no es bug; registrar la fecha en que A9 lo habilita.
8. **Tesis: sólo existen si hubo INVERTIR** (`decision_states*.json` ausente local = 0 tesis visibles).
   Correcto por diseño, pero un usuario nuevo ve el monitor vacío sin saber si es falta de tesis o de
   pipeline — 1 línea de estado ("N tesis activas / última corrida X") lo resuelve.

**Nada de lo anterior toca Gobernanza ni Fundamentos** (regla de la tarea). Implementación queda a tu
decisión, en ese orden.