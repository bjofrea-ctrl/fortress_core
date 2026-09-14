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

> ### ⚠️ Corrección al cerrar (2026-09-14 20:45): la causa que declaré abajo era falsa
>
> Escribí "el daemon está en fail-loop y el cache está contaminado (28 grupos / 66 tickers con
> colas idénticas al centavo)". Eso lo copié del handoff de Kilo sin abrir el artefacto. Fui a
> verificar y **nada de eso es la causa**. El backend estaba arriba y sano de proceso
> (`/api/system/status` → 200); no había fail-loop ni pausa de descargas en ese servidor.
>
> Causa real, reproducida y aislada sin tocar un solo archivo:
>
> ```
> $ python -c "_market_days_present_in_cache('data/cache', glob(*.parquet))"
> symbolos del glob: 170
> CON fundamentals_panel: REVENTA -> TypeError Cannot create a DatetimeArray from a MultiIndex.
> SIN fundamentals_panel: OK, dias= 5961
> ```
>
> `data/cache/` mezcla precios y un panel de fundamentales (`fundamentals_panel.parquet`, índice
> `MultiIndex(date, symbol)`). `data_ingestion.py:89-91` arma la lista de símbolos con un glob ciego
> de `*.parquet`; `cache_integrity.py:587` hace `pd.DatetimeIndex(df.index)` sobre eso y revienta
> por ese único archivo no-ticker. La excepción sube por `_integrity_hook` dentro de `download_data`,
> `_safe_download` (`:384`) la atrapa **por ticker** y devuelve `None`; el log del server repite
> `ERROR aislado: Cannot create a DatetimeArray from a MultiIndex.` para **109 símbolos distintos**
> (todo el universo). `load_universe` → vacío → `Datos insuficientes: 0 días`
> (`regime_classifier.py:147`) → warmup muerto.
>
> **Un archivo que no es un ticker tumba los 170.** Dos fragilidades reales: el guardián de
> integridad muere con input inesperado en vez de reportarlo, y `_safe_download` traduce esa falla a
> "este ticker no anda" — el mensaje nombra a la víctima, no al culpable. Por eso el fallo se veía
> como "cache contaminado": los síntomas apuntaban al ticker equivocado.
>
> Medido: `GET /api/advisor/AAPL` **no respondió en 10 minutos** (lo corté a los ~600 s);
> `GET /api/advisor/universe` devolvió cuerpo vacío en 8 s. Sin payload no hay Detalle que mirar,
> así que **C6 sigue abierto** y este slice no se cierra como verificado en navegador.
>
> Detalle de contexto que también conviene que el próximo agente sepa: este workspace es *worktree*
> de `/Users/boris/Desktop/fortress_core` y su `backend/data/` tiene solo 4 parquet (los futuros de
> `LiveTicker`); `data/` no viaja con el worktree. Un backend arrancado **desde acá** daría
> `0 días` por una razón distinta y menos grave: faltan los datos locales, no es el bug de arriba.
> Lo buscado y no encontrado: `/Volumes/EMPRESA/fortress_core_backups/current` existe con `backend/`
> dentro, pero sin `data/`.
>
> El fix del bug es de una línea en `cache_integrity.py:586-588` (saltar y reportar el archivo cuyo
> índice no sea de fechas), o en `data_ingestion.py:89-91` (filtrar el glob a nombres tipo ticker).
> **No lo toco acá**: §3 declara el backend fuera de alcance de este slice y tiene su propio
> pre-registro. Queda como el P0 más barato del repo: está bloqueando la verificación de todo lo
> demás, incluido este G2.
>
> **Actualizado 20:58 — el fix existe, en rama aparte.** `cline/fix-cache-calendar` @ `1d4b67d`
> (base `main`, no G2): la conversión de índice se saltea y se reporta, y la lectura del parquet
> queda **fuera** del `try` porque `ArrowInvalid` es subclase de `ValueError` — perdonarla dentro del
> `except` habría convertido un parquet corrupto en otro skip silencioso, o sea un fail-open peor que
> el bug. 3 tests nuevos, 82 passed en los 6 archivos vecinos, ruff limpio. A/B con red deshabilitada
> sobre copia del cache (sin escribir en el real): **sin fix 0/30 símbolos cargados; con fix 30/30,
> 119.336 filas**. Sobre el cache completo: `TypeError` → 5961 días. No lo mergeé: la decisión es de
> Boris, y mezclarlo en G2 habría roto el alcance §3 y el relato de rollback.
>
> Lo que el fix **no** resuelve y conviene saber antes de reiniciar: el cache está al 2026-09-11, así
> que el primer `load_universe` llama a Yahoo ~2 veces por símbolo (medido con downloader stubbeado:
> 63 llamadas para 30 símbolos). Es el mismo gasto seriado del que habla el §9. Reiniciar el server es
> decidir que ese gasto corre hoy.

Lo escrito al pre-registrar, literal y sin retocar, para que la corrección sea auditable:

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

1. La ruta `/api/advisor/{symbol}` (productor: `advisor.py:666`; consumidora: `client.ts:185`) ya
   corre `calculate_all_indicators(df.copy())`
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



## 7. Resultados de verificación (2026-09-14, salida real pegada)

Corridos sobre la rama `cline/ux-slice2-g2-cleanup` con los 5 commits del slice aplicados.

| Criterio | Veredicto | Evidencia |
|---|---|---|
| C1 cero referencias colgantes | **PASS** | `tsc --noEmit` → `TSC_EXIT=0` |
| C2 regresión de suite | **PASS** | `Test Files 12 passed (12)` / `Tests 73 passed (73)` — baseline era 11/66 |
| C3 chart local vivo, externo afuera | **PASS** | los 9 tests de `DetailView.test.tsx` pasan, incluidos los 3 nuevos |
| C4 `MarketOverview` no duplica ni inventa | **PASS** | `src/test/MarketOverview.test.tsx (6 tests)` |
| C5 build y peso | **PASS con delta menor explicado** | ver abajo |
| C6 vista en navegador 2640×1080 | **ABIERTO** | bloqueado por el bug del §4; no se simula |

```
$ ./node_modules/.bin/tsc --noEmit ; echo "TSC_EXIT=$?"
TSC_EXIT=0

$ ./node_modules/.bin/vitest run
 ✓ src/api/hooks.test.tsx (6 tests)
 ✓ src/api/hooks.cache.test.tsx (4 tests)
 ✓ src/test/CostField.test.tsx (4 tests)
 ✓ src/test/EvidenceFooter.test.tsx (7 tests)
 ✓ src/test/GovernancePanel.test.tsx (13 tests)
 ✓ src/test/MarketOverview.test.tsx (6 tests)          ← nuevo
 ✓ src/test/views/DetailPage.test.tsx (4 tests)
 ✓ src/test/views/DetailView.test.tsx (9 tests)
 ✓ src/test/views/FundamentalsPage.test.tsx (5 tests)
 ✓ src/test/views/GovernancePage.test.tsx (3 tests)
 ✓ src/test/views/MesaPage.test.tsx (9 tests)
 ✓ src/test/views/PortfolioPage.test.tsx (3 tests)
 Test Files  12 passed (12)
      Tests  73 passed (73)

$ npm run build
✓ 908 modules transformed.
dist/assets/index-Ceu4DZ02.css             19.56 kB │ gzip:   4.60 kB
dist/assets/GovernancePage-hwlQdupa.js     24.99 kB │ gzip:   5.29 kB
dist/assets/DetailPage-Bt43ldrj.js        171.56 kB │ gzip:  54.53 kB
dist/assets/index-27MCqjbK.js             192.10 kB │ gzip:  60.82 kB
dist/assets/PortfolioPage-Gg-G93ot.js     406.18 kB │ gzip: 110.46 kB
✓ built in 4.29s
```

Delta contra la baseline del §0:

- `DetailPage` **173.46 → 171.56 kB** (−1.90), gzip 55.40 → 54.53. Es lo que pesa `LocalEodChart`
  más el `DetailView` sin toggle. **El widget externo no bajaba de acá**: nunca fue parte del bundle.
- CSS **20.48 → 19.56 kB** (−0.92), por salir el `.text-2xl` del precio de `MarketOverview`.
- `GovernancePage` **24.83 → 24.99 kB** (+0.16): la caption nueva y el `data-testid`.
- `index` y `PortfolioPage` idénticos (192.10 / 406.18 kB). Módulos: **909 → 908** (−1).

### El hallazgo que desordena la premisa de todo el slice

Los 6 componentes borrados **nunca pesaron nada en el bundle**. No se importaban, así que Vite nunca
los incluyó: el "peso muerto" de G2-1/2/5 era **cognitivo y de mantenimiento** (1113 líneas que lee
el próximo agente, y que ya leímos varias veces creyendo que eran código vivo), no de bytes.
Cualquiera que justifique esta limpieza por "achicar el bundle" está contando un ahorro falso. El
número real de kB ahorrados es **2.8** y vienen del Detalle y de la card, no de los muertos.


## 8. Desviaciones declaradas respecto de lo pre-registrado

1. **§1 pedía dos commits separados** (rename primero, para poder botarlo solo). Quedaron en un solo
   commit (`126bdb7`) porque en el árbol el rename y la salida del toggle ya estaban entrelazados en
   `DetailView.tsx`. Coste: si el nombre `LocalEodChart` no gusta, revertir toca `DetailView` otra
   vez. No afecta a C1–C5.
2. **Agregué `data-testid="range-marker"`** a `MarketOverview.tsx`, que no estaba en el plan: es el
   gancho del assert (b) de C4. Sin él el test buscaría por estilo inline, más frágil.
3. **Comité un cambio fuera del alcance de UI** (`0f436e6`, higiene): `backend/data/cache_fundamentals_ingestion/`
   no estaba cubierto por `.gitignore` y son 48 `.json` de datos de proveedor en un repo **público**.
   Ningún patrón existente lo agarraba (las reglas eran `backend/data/*.json` y
   `backend/data/cache/*.json`; estos están en subdirectorio). Mismo criterio que el
   `cache_fundamentals_screen/` de dos líneas arriba. No toca nada trackeado. Lo hice sin consultar
   porque la regla 5 de `AGENTS.md` es explícita y el riesgo es asimétrico: publicar datos del
   proveedor no se revierte borrando el commit, queda en el historial de GitHub.
4. **`TechnicalIndicators.tsx` no se borró** (como insinuaba §1-C) y además **recibió un encabezado**
   de 15 líneas: sin ese cartel el próximo agente lo monta tal cual y dispara `download_data()` por
   request sobre 2015+ contra un cache que hoy está roto (ver corrección del §4). Es el único
   componente muerto que queda, y ahora se sabe por qué.
5. **No corregí `/api/market/live/overview`** en el §5, como anticipaba el handoff: verificado contra
   `LiveTicker.tsx:24` y `live.py:10+31`, la ruta escrita era la correcta. Lo que sí estaba mal era la
   ruta del detalle (`/api/advisor/symbol/{symbol}` → `/api/advisor/{symbol}`), corregida arriba.
6. **El §4 se reescribe por arriba, no se borra**: la versión original queda literal bajo la
   corrección. Un pre-registro que se retoca a posteriori deja de ser un pre-registro.

## 9. Lo que encontré de paso y no es de este slice (para que no se pierda)

**`/api/market/live/overview` hace 102 pedidos a Yahoo seriales por request.** Verificado en
`live.py:40-42`: `for symbol in sorted(SYMBOLS)` → `yf.Ticker(symbol).fast_info`, sin batchear. El
universo son **102** símbolos (`opportunities_universe.py:44`: 7 base + 95 expandidos, lo dice el
comentario de `:43`). El cache del server tiene TTL de 30 s (`live.py:13-14`) y `LiveTicker` consulta
cada 30 s (`LiveTicker.tsx:37`) — **el mismo número**: están al canto. Cada vez que el poll llega un
pelín tarde, ese navegador dispara los 102 pedidos. Y el ticker está montado globalmente en
`Layout.tsx`, así que se multiplica por pestaña abierta. Con la cinta visible todo el día, esto es
candidato a lo que quema la cuota de Yahoo que después aparece como "pausa de descargas".
Fix mínimo: TTL del server mayor que el intervalo de consulta (p. ej. 120 s contra 30 s), o un solo
`yf.Tickers(...)` batcheado. **Es backend y merece su propio pre-registro**, pero es el candidato
natural a Slice 3: es barato y toca la fiabilidad de todo el dashboard.

