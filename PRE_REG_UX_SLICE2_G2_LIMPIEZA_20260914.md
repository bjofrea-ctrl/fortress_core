# Pre-registro UX — Slice 2: limpieza G2 (ruido, redundancia, peso muerto)

Fecha: 2026-09-14 · Rama: `cline/ux-slice2-g2-cleanup` (nace de `main` = `1789841`)
Autor: Cline · Verificación/merge: Kilo · **NO merge sin OK explícito de Boris**
Fuente: `AUDITORIA_DASHBOARD_UTILIDAD_20260911.md` §G2 (ítems 3, 4, 5), aprobados por Boris
el 2026-09-12 13:30 según `TASK_KILO_A_CLINE_20260912.md` §0 ("el freno está levantado:
las tres van a implementación").

Contexto de la base: los tres primeros commits de la rama anterior
(`ux/dashboard-control-panel`, basada en el tip de AUDIT `07bffa8`, no ancestro de `main`)
son `efbfdd4/15b2b62/2e6a258/63ad36c` → ya absorbidos en `main` vía `f207e91` + `2ff1997`,
MENOS el estado vacío de `MesaPage` y los tooltips de `MesaView`, que `main` NO tiene
(verificado con `git grep` sobre `main`: `NO_MesaPage_banner_en_main`, `NO_tooltip_en_main`).
Por eso esta rama arranca en `main` y **cherry-pickeá** `38f49d3` + `7c8ff29`
(`0568a09` + `e456efb`): superficie viva = 3 archivos de frontend, sin el lastre de la
base de auditoría. La rama vieja queda intacta para la decisión de merge de Boris.

## 0. Línea base medida ANTES de tocar nada (2026-09-14 20:12, sobre `e456efb`)

| Métrica | Valor baseline |
|---|---|
| `vitest run` (suite completa frontend) | **11 archivos, 66 passed** |
| `tsc --noEmit` | **exit 0** |
| `npm run build` (`tsc && vite build`) | **909 módulos, exit 0, 4.48s** |
| chunk `DetailPage` | 173.46 kB │ gzip 55.40 kB |
| chunk `PortfolioPage` | 406.18 kB │ gzip 110.46 kB |
| chunk `index` | 192.10 kB │ gzip 60.82 kB |
| chunk `GovernancePage` | 24.83 kB │ gzip 5.18 kB |

Ningún test frontend menciona los componentes candidatos a borrar (verificado:
`grep -rl -E 'SystemStatus|PriceChart|SymbolSummary|UniverseTable|DecisionPanel|TechnicalIndicators' src/test/`
→ sin resultados). Es decir: **hoy no hay evidencia automatizada de que existan**, y sin
embargo suman ~900 líneas leídas por el próximo agente.
## 1. Qué cambio (tres ítems, superficie mínima)

### Ítem A — G2-3: sacar el widget TradingView externo del Detalle
- `advisor/DetailView.tsx`: elimino el toggle `"local" | "tv"` y el `<TVWidget/>`. El chart
  local (Lightweight Charts, EOD, **con las zonas del motor: entrada/stop/target**) queda
  como único chart.
- Borro `advisor/TVWidget.tsx` (77 líneas): inyecta un `<script>` de
  `https://s3.tradingview.com/...` en un dashboard de repo público, muestra precio de
  terceros que **no coincide** con el cache EOD local (el propio aviso lo dice: "difiere
  del cache EOD local") y no tiene zonas del proyecto. Un chart que contradice la fuente
  canónica del instrumento no es "dos vistas", es ruido con pinta de dato.
- Renombro `advisor/TradingViewChart.tsx` → `advisor/LocalEodChart.tsx`
  (componente `TradingViewChart` → `LocalEodChart`). **Este rename es la causa raíz del
  ítem A**: un chart local llamado "TradingViewChart" es exactamente lo que hace que un
  lector confunda cuál es la fuente. Commit separado para que sea trivial de botar si
  conflicto.

### Ítem B — G2-4: `MarketOverview` deja de duplicar el precio de `LiveTicker`
- Hecho medido: `LiveTicker` se monta en `Layout.tsx` (global, o sea visible también en la
  página Gobernanza) y `MarketOverview` se monta SOLO en `GovernancePage.tsx`. En esa
  pantalla conviven **dos precios distintos del mismo símbolo**: el del ticker (30 s,
  `/api/market/live/overview`) y el grande de la card (`$price` EOD, `/api/market/overview`).
- Fix **por diferenciación, no por borrado**: saco de la card la línea grande `${price}`
  (el único dato duplicado) y dejo lo que `LiveTicker` NO tiene y es utilidad propia del
  bloque: `total_return_pct`, `30D`, `vol`, barra de rango 52s con marcador `range_position`
  y bordes `low_52w/high_52w`.
- Agrego una caption que dice dónde está el precio vivo y qué ventana es esta. Ningún dato
  nuevo: cada campo mostrado ya viene en el payload real de `/api/market/overview`
  (`MarketOverview.tsx:8-19`, interfaz `SymbolOverview`).
- El `h3` interno `📊 Market Overview` pasa a ser informativo (el título de sección lo pone
  `GovernancePage.tsx:19` — hoy hay doble título en la misma caja). **No toco** el texto
  `"Resumen de mercado"` que fija `GovernancePage.test.tsx:39`.

### Ítem C — G2-5: componentes muertos sin dueño
Verificado uno por uno contra el disco (módulos que nadie importa ni monta):

| Componente | Líneas | Único consumidor | Destino |
|---|---|---|---|
| `SystemStatus.tsx` | 45 | ninguno (`Header.tsx` tiene su propia versión inline + interfaz `SystemStatusData`) | **borrar** |
| `PriceChart.tsx` | 156 | ninguno | **borrar** |
| `SymbolSummary.tsx` | 164 | ninguno | **borrar** |
| `UniverseTable.tsx` | 209 | ninguno | **borrar** |
| `DecisionPanel.tsx` | 257 | ninguno | **borrar** |
| `hooks/useDecision.ts` | — | solo `UniverseTable` + `DecisionPanel` (ningún otro archivo lo importa) | **borrar** (muerto por transitividad) |
| `TechnicalIndicators.tsx` | 140 | ninguno | **NO se borra** → es el vehículo del ítem G3 (§5) |

Motivo extra, verificado en código: `UniverseTable`/`DecisionPanel` llaman
`/api/decision/universe` y `/api/decision/{symbol}`, y el propio backend advierte
(`advisor.py:481-484`) de que `/api/decision/universe` **persiste estados en cada llamada**
(efecto colateral de escritura) mientras `/api/advisor/universe` es de solo lectura. Un
componente muerto que llama a un endpoint que escribe es deuda de riesgo, no de estilo: si
alguien lo re-monta sin leer, el dashboard empieza a mutar estados de decisión.

**Los endpoints NO se tocan** (contrato público del backend, con tests propios y README). Lo
que desaparece es solo el consumidor UI huérfano. Queda registrado: tras este slice
`/api/market/summary/{symbol}`, `/api/decision/universe` y `/api/decision/{symbol}` quedan
sin consumidor en el dashboard.


## 2. Criterios de cierre (medibles, escritos ANTES de correr)

- **C1 — cero referencias colgantes**: tras los borrados,
  `grep -rn -E 'SystemStatus|PriceChart|SymbolSummary|UniverseTable|DecisionPanel|useDecision|TVWidget' src/`
  no devuelve ninguna importación/uso de un módulo inexistente, y `tsc --noEmit` → **exit 0**
  (TypeScript es el que corta cualquier referencia huérfana; no confío en el grep solo).
- **C2 — regresión de suite**: `vitest run` → **≥ 66 passed, 0 failed** sobre los 11
  archivos base. Se permiten tests NUEVOS (suben el total); no se acepta bajar ninguno.
- **C3 — el chart local sigue vivo y el externo no**: `DetailView.test.tsx` debe afirmar
  (a) que el chart local monta, (b) que **ya no existe** el botón "TradingView" ni el
  `tv-widget`, y (c) que las zonas mecánicas (entrada/stop/target) siguen visibles — el test
  de zonas hoy pasa por el mock del chart, no se puede aflojar.
- **C4 — MarketOverview no inventa ni duplica**: test NUEVO `src/test/MarketOverview.test.tsx`
  con payload mockeado de `SymbolOverview` que afirme (a) la card **no** renderiza `$<price>`
  (regresión de la duplicación), (b) sí renderiza el marcador de rango y la volatilidad del
  payload, (c) la caption del precio vivo está presente. Ningún campo mostrado que no esté en
  la interfaz del payload.
- **C5 — build y peso**: `npm run build` exit 0 y delta de tamaños reportado contra la tabla
  §0 (esperado: `DetailPage` y/o `index` bajan al salir el script externo; si suben, se
  explica por qué o se revierte).
- **C6 — nada afirmado sin verlo**: el criterio C4 *visual en navegador* del Slice 1 **sigue
  abierto** y este slice NO lo cierra (§4). Nada se marca como "cerrado" sin pegar la salida
  real del comando en ROADMAP/SESSION_LOG.

## 3. Fuera de alcance (cola explícita)

- **G3 (los 16 indicadores)**: se **propone** con justificación (§5), no se implementa.
- Renombrar INVERTIR, cambiar scoring, tocar la lógica de Gobernanza o de Fundamentos.
- Endpoints backend, payloads, motor, nada que toque el gate de 60 días limpios.
- Merge/rebase a `main`: decisión de Boris.

## 4. Bloqueo declarado de la verificación visual — no se finge cerrada

Abierto hoy y verificado contra el artefacto: el daemon está en fail-loop
(`advisor_warmup_failed: "Datos insuficientes: 0 días"` cada ~3 min, último 20:05 ART en
`scripts/api_server.log`) y el frente B del handoff de Kilo documenta **cache de precios
contaminado** (28 grupos / 66 tickers con colas idénticas al centavo). Ver el dashboard
servido hoy mostraría números falsos y, además, abrir el Detalle dispara `download_data()`:
con el cache ≥1 día atrás intenta refresh contra Yahoo, en plena **pausa de descargas
masivas** vigente. La verificación visual se corre cuando (a) el cache esté saneado y (b) la
pausa levante. La hace Boris o un agente con navegador. Registrar, no simular.

## 5. Hallazgo nuevo en camino a G3 (registrado, NO arreglado acá)

Verificado contra `backend/app/api/routes/advisor.py:687-731` y
`frontend/src/api/client.ts:74-92`:

1. La ruta `/api/advisor/symbol/{symbol}` ya corre `calculate_all_indicators(df.copy())`
   **en memoria, sobre el `price_data` cacheado del contexto** (0 llamadas nuevas a Yahoo) y
   solo extrae `ema50`/`ema200` para las barras. El resto (~17 columnas: `rsi14, adx14,
   atr14, macd/macd_hist, bb_*, stoch_k/d, momentum_12_1, volume_ratio, ema20, hma16, kama10,
   supertrend_line/side, hurst_exponent, realized_vol_regime, trend_bullish, volume_sma20`)
   **se calcula y se descarta**.
2. El contrato TS del frontend declara `state.indicators{close, ema50, ema200, adx14, rsi14,
   volume_ratio}` pero el backend **nunca** asigna `ticket["indicators"]` → el campo llega
   siempre `undefined`. Es un contrato que miente: ni G1 ni G2 lo cubrían porque la
   auditoría miró dato→UI, no contrato→productor.
3. Consecuencia: el subconjunto de indicadores **no cuesta compute nuevo ni descargas** si se
   expone desde lo que el Detalle ya computa. El camino que NO recomiendo es montar
   `TechnicalIndicators.tsx` tal cual: llama a `/api/market/indicators/{symbol}` →
   `download_data(start="2015-01-01")` por request, con cache contaminado y pausa vigente.

**Propuesta G3 (a validar):** mostrar en el Detalle solo los indicadores que el instrumento
usa para decidir — `ema50/ema200` (hoy visibles como `dist_ema`), `rsi14`, `adx14`,
`volume_ratio`, `atr14` y el gate `trend_ok`; **ninguno de los exóticos** (`hurst_exponent`,
`supertrend`, `kama10`, `hma16`) porque no entran al gate ni al score: mostrarlos convidaría
a leer señal donde el motor no la usa. Cifras y justificación por indicador se entregan en un
documento G3 aparte con su propio pre-registro si Kilo/Boris lo aprueban.

## 6. Reversibilidad

Nada se pierde: cada borrado existe en `main` y en el historial. El punto de recuperación de
todo lo que este slice elimina es el padre de la rama (`1789841`), y la rama anterior
`ux/dashboard-control-panel` (`ef3e3bd`) queda intacta. Doctrina: no se cierran puertas, se
saca del camino lo que estorba, con el camino de vuelta escrito.


