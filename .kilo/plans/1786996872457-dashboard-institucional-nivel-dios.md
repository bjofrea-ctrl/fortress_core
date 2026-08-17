# Dashboard institucional nivel dios — CONSOLIDADO (Claude Code + plan Kilo Code)

**Estado**: plan final de implementación. Base: rebuild completado de Claude Code
(2026-08-17, verificado: build 624.82 kB OK, contrato GovernancePanel real, CSS tokens,
apiUrl por props) + plan original Kilo Code (advisor API, etiquetas proyectadas,
Exit Thesis Monitor, charts institucionales). El usuario pidió UNO consolidado.

## 0. Decisión de carpeta (cambiada vs plan original)

Claude Code TERMINÓ y su trabajo está commiteado → se construye **directamente sobre
`frontend/`** (git como red de seguridad). NO se crea `frontend_v2/`. Un solo dashboard;
mantener dos era la precaución para la colisión, que ya no existe.

## 1. Qué se conserva de Claude Code (verificado, no se reescribe)

- `Layout.tsx` patrón de paneles colapsables + estado central (se reordena en vistas, §3).
- `Header.tsx` (estado del sistema), `index.css` tokens dark + animaciones + reduced-motion.
- Módulos funcionales intactos: `EquityCurve`, `RegimePanel`, `MonteCarloPanel`,
  `TradeDistribution`, `TradesTable`, `OpportunitiesPanel`, `GovernancePanel`
  (contrato verificado contra backend), `MarketOverview`, `KPICards`, `LiveTicker`,
  `SymbolSummary`, `TechnicalIndicators`, `hooks/useDecision.ts`.
- Build pipeline (Vite+TS+Tailwind) y `apiUrl` como prop única.

## 2. Marco de honestidad (no negociable — viene de ONBOARDING #1/#4)

- Sin señal comercial validada (28 trials NO CUMPLE). El dashboard es **apoyo a decisión
  con evidencia citada**: badge global "Apoyo a decisión — sin señal comercial validada"
  + n de evidencia junto a cada etiqueta de resultado.
- Filosofía del usuario verificada como el diferencial del proyecto: la ganancia está en
  la SALIDA (se sale cuando se pierde la tesis de entrada; perder poco > ganar mucho).
  El **Exit Thesis Monitor** (§4.3) es la feature central.
- Precios de entrada/salida = zonas mecánicas del motor (gates, stops EVT §19, barreras
  M1, plan de salida 4 mecanismos), nunca "niveles predichos".

## 3. Etiquetas proyectadas — pre-registro ANTES de pintarlas en la UI

Escribir en `PLAN_MEJORA_MATEMATICA.md` como doc de mapeo (NO consume slot: es
presentación de evidencia existente). Verificar primero contra el artefacto real
`data/cache/asesoria_combinaciones_20260817_110427.txt` (no copiar de memoria):

| win_prob calibrado | Etiqueta | Evidencia a citar |
|---|---|---|
| ≥ 0.70 | GANANCIA_PROYECTADA | VPP real 87.5% (n=8) |
| 0.65–0.70 | GANANCIA_PROYECTADA | VPP real 73.7% (n=19) |
| 0.45–0.65 | NEUTRO | sin selectividad medida |
| < 0.45 | RIESGOSA | se muestra "sin apoyo estadístico" (la cola baja no tiene evidencia de selectividad — no afirmar "pérdida proyectada" como predicción) |

UI: si n<30, el n se muestra junto a la etiqueta. Régimen DEFLATION: banner global que
bloquea etiquetas de entrada (mecánica real del motor).

## 4. Backend — router nuevo `/api/advisor` (solo lectura; nada se rompe)

`backend/app/api/routes/advisor.py`, registrado en `main.py`. Reutiliza `_compute_ticket`
de `decision.py` — NO reprogramar lógica de motor.

1. `GET /api/advisor/universe` — mesa consolidada en UNA llamada (mata el N+1):
   estado INVERTIR/VIGILAR/NO_INVERTIR + razón, win_prob + etiqueta §3, gates crudos,
   último cierre + fecha del dato, distancia a EMA50/200, stop EVT implícito (fórmula
   real de `adaptive_risk.py` + EVT §19), barreras M1 vigentes, transición vs día previo,
   `thesis_status` (§4.3), y `stale: bool` (cache >2 ruedas viejo → avisar).
2. `GET /api/advisor/{symbol}` — detalle: OHLCV EOD del cache, indicadores para
   overlays (EMA50/200, banda EVT, barreras M1), fundamentals desde `edgar_fundamentals.py`
   si hay cobertura (si no: `null` + flag "sin cobertura EDGAR" — NUNCA inventar),
   plan de salida `_exit_plan`, intervalo M2, historia de estados.
3. `GET /api/advisor/theses` — Exit Thesis Monitor: para cada símbolo con snapshot de
   entrada (estado INVERTIR en `decision_states.json` extendido), compara gates/régimen/
   barreras de la entrada vs hoy → VIGENTE / DEGRADADA (cuál gate se rompió) /
   TESIS_ROTA (razón mecánica + riesgo de cola EVT visible).
4. `GET /api/advisor/evidence` — footer de confianza: n_trials por familia, umbral
   vigente, últimos veredictos — leyendo `trial_registry.json` vía `trial_registry.py`.

Tests: `tests/test_advisor_api.py` (patrón repo: asyncio.run + monkeypatch). Cero LLM
en estos endpoints.

## 5. Frontend consolidado — arquitectura de pantallas (no scroll infinito)

### 5.1 Dep nueva
`lightweight-charts` (TradingView open-source). `recharts` se queda para curvas donde ya
funciona (equity, MC, distribución).

### 5.2 Identidad visual (mantener tokens de Claude Code, afinar a TV)
Mantener: dark theme, animaciones, reduced-motion, scrollbar. Ajustar: fondo a `#131722`,
paneles `#1e222d`, verde/rojo TV `#26a69a`/`#ef5350`, tipografía monoespaciada para todos
los números tabulares. La línea "Capital: $25,000 | Ceiling: -12%" hardcodeada en
Layout.tsx → sacarla de `GET /api/advisor/universe` (o `/api/system/status`) para que
sea dato, no texto.

### 5.3 Navegación: tabs por estado en Layout (sin react-router)
- **Vista MESA** (home): tabla del universo 50 desde `/api/advisor/universe` — estado
  coloreado, win_prob, etiqueta §3, cierre, distancia EMA, stop EVT, tesis (§4.3),
  transición ↑↓, orden/filtro por columna, banner de régimen + badge de honestidad.
  Selector de símbolo pasa a estar DRIVEN POR EL UNIVERSO (50), no la lista hardcodeada
  de 7 (`SYMBOLS` en Layout.tsx se elimina). Click fila → Vista DETALLE.
- **Vista DETALLE {símbolo}**:
  - Carta principal: Lightweight Charts — velas EOD + EMA50/200 + banda stop EVT +
    líneas de barreras M1 + marcador del día de decisión. Siempre con sello "al último
    cierre <fecha>".
  - Toggle a widget TradingView embebido como vista secundaria (usuario pidió ambos).
  - Panel decisión: tesis de entrada (qué gates pasaron), zona de entrada mecánica,
    plan de salida 4 mecanismos con niveles concretos, intervalo M2, etiqueta §3 con n.
  - Panel fundamental: snapshot EDGAR o "sin cobertura" honesto.
- **Vista PORTFOLIO**: EquityCurve + RegimePanel + MonteCarlo + TradeDistribution +
  TradesTable (los componentes existentes, reordenados).
- **Vista GOBERNANZA**: GovernancePanel (existente, contrato verificado) +
  OpportunitiesPanel. Fuera de la vista default: dispara LLM real (rate-limited).
- **Footer permanente** (todas las vistas): Evidence Ledger vivo desde
  `/api/advisor/evidence` — familias, n consumidos, umbral, últimos veredictos. Es la
  firma de confianza institucional. Reemplaza el texto estático actual.

### 5.4 Code splitting
Dynamic import por vista (`React.lazy`) — resuelve el warning de 624 kB en un chunk;
los recharts/lightweight-charts caen solo en las vistas que los usan.

## 6. Tareas en orden (cada una termina verificable)

1. Doc de mapeo §3 en `PLAN_MEJORA_MATEMATICA.md` + verificación contra el artefacto
   de asesoría (los VPP/n citados DEBEN coincidir con el archivo, no con memoria).
2. Backend: `advisor.py` (4 endpoints) + registro en `main.py` + `tests/test_advisor_api.py`.
   `pytest` verde completo. `ruff` limpio.
3. Snapshot de tesis: extensión de `decision_states.json` (leer esquema actual primero —
   si el formato no admite la foto de entrada sin migración, crear `thesis_snapshots.json`
   aparte; NO romper lo existente ni lo que `_persist_states` escribe).
4. Frontend base: dep `lightweight-charts`, ajuste de tokens §5.2, tabs de navegación
   en Layout (conservando CollapsiblePanel para sub-paneles dentro de cada vista),
   `API_URL` a env de Vite (`import.meta.env.VITE_API_URL || "http://localhost:8000"`).
5. Vista MESA completa + componentes compartidos (badge honestidad, staleness chip,
   EtiquetasProyectadas con n).
6. Vista DETALLE con Lightweight Charts + overlays + widget TV embebido + paneles.
7. Exit Thesis Monitor (endpoint del paso 2 + UI en MESA y DETALLE).
8. Vista PORTFOLIO + GOBERNANZA (reubicación de componentes existentes, sin reescribir).
9. Footer Evidence Ledger vivo.
10. Code splitting + `npm run build` sin warning de chunk.
11. Acceptance (regla #1 — verificar contra el artefacto crudo):
    - `pytest` verde, `ruff` limpio, `tsc && vite build` OK.
    - Backend corriendo: abrir las 4 vistas; contra 3 símbolos (uno INVERTIR, uno
      VIGILAR, uno sin cobertura EDGAR) verificar que CADA dato mostrado coincide con
      la respuesta JSON cruda del endpoint correspondiente.
    - Widget TV carga; si falla la red externa, la vista Lightweight sigue operativa
      (graceful degradation, no pantalla rota).
12. Docs: ROADMAP (fila dashboard-consolidado), README frontend, SESSION_LOG;
    commit descriptivo + push + espejo rsync al disco externo si está montado.

## 7. Riesgos y fallos previstos

- **Reescribir lo que funciona**: prohibido tocar GobernancePanel/equity/régimen salvo
  reubicación — su valor está en contratos ya verificados.
- **decision_states.json**: escritura concurrente con el backend corriendo → la extensión
  del snapshot debe ser atómica (mismo patrón temporal+rename que trial_registry).
- **EOD, no realtime**: sello "al último cierre" siempre visible; el widget TV muestra
  realtime de terceros — diferencia declarada en UI (evita engaño).
- **yfinance viejo**: staleness chip visible si el cache tiene >2 ruedas de atraso.
- **Cobertura EDGAR 5/50**: UI honesta "sin datos", nunca fallback inventado.
- **LLM**: cero uso en advisor; gobernanza (que sí lo usa) queda en su vista propia
  bajo el rate limit existente.

## 8. Fuera de alcance

- Broker real (decisión de producto cerrada hasta edge validado).
- Intradía/websockets de precios propios (escalado descartado).
- Nueva investigación de señales (cualquier indicador nuevo pasa por trials
  pre-registrados; el dashboard muestra evidencia, no la crea).
- Auth de usuario/perfiles (UI pública por decisión del proyecto).

## 9. Dependencias externas de datos

- M4 runner mide costos reales mañana al open → el campo "costo por trade" del panel
  queda reservado; se llena con el artefacto `measure_execution_costs_*` cuando exista
  (reemplaza visualmente el 0.30% asumido; ver ROADMAP M4).
- Cron diario (instalado hoy 22:00) mantiene OHLCV + FinBERT frescos para el panel.
