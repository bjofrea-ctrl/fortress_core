# Miedo premarket 2026-09-14 — lectura retail vs institucional contra hipótesis

**Fecha**: 2026-09-14 ~09:00 ART (premarket EE.UU.) · **Autor**: Kilo (orquestador).
**Pedido**: Boris — evaluar la noticia de miedo con las hipótesis planteadas,
aprovechando la caída para testearlas. Solo números verificados esta mañana
(fuente entre paréntesis en cada dato); lo no verificable se declara.

## 1. Qué pasó (hechos)

- **Viernes 09-11 cerró ARRIBA**: SPY +0.85% (764.29), QQQ +0.87% (yfinance).
- **Lunes premarket en rojo**: ES −0.75%, NQ −1.70%; **VIX 18.02, +13.76%**
  (yfinance; VIX cotiza casi 24h, el dato es de hoy).
- **Driver** (titulares Bloomberg/WSJ/IBD/Yahoo vía RSS 09-14): apelaciones de
  OpenAI/Anthropic sobre seguridad IA golpean el trade de IA global + petróleo
  sobre US$100 + PPI arriba de pronóstico (apuestas de hike). Cóctel: miedo
  concentrado en liderazgo AI/momentum + inflación.
- **Distancia a máximos (SPY en vivo, 1y)**: máx 252d 777.88 → **−1.7%**.
  El mercado está a menos de 2% de máximos: NO hay piso ni drawdown.

## 2. Retail: pesimismo leve, lejos de capitulación

- **AAII spread (cache propio)**: +2.18 (09-03) → **−1.39 (09-10)**. Flip a
  neto bajista en una semana — dirección correcta para "ambiente de venta",
  pero MAGNITUD irrelevante contra los umbrales medidos del doc:
  - Umbral "piso con miedo": **AAII < −15** (media en pisos −8.3, SCHW −14.7).
  - Lectura actual −1.39: **orden de magnitud por debajo**. No hay capitulación
    minorista medible; hay incomodidad temprana.
- CNN Fear&Greed: timeout de red desde este host hoy (limitación declarada);
  referencia válida más cercana: smoke del termómetro 09-11 → 32.2 "fear",
  put/call 0.74 (extreme fear), VIX 17.8.

## 3. Institucional: sin lectura fresca (limitación honesta)

- **COT CFTC**: último dato en cache **2026-08-04** (6 semanas de lag + sin
  refresco reciente). La firma institucional (asset managers netos +682k vs
  leverage −291k en retests, doc §3.1) **no es medible hoy**. No se afirma
  posicionamiento institucional actual.
- **Régimen HMM**: sin corrida fresca sobre datos confiables (ver §5 incidente
  de cache) — no se declara régimen. Por contexto (VIX 18, drawdown −1.7%,
  momentum cayendo por liderazgo AI): **compatible con GOLDILOCKS tensionado
  o inicio de transición, NO con STAGFLATION establecido** (sin evidencia de
  estanflación en precios hoy).

## 4. Evaluación contra hipótesis planteadas

**H1 — Ciclo institucional (piso −15% → alza lenta → retest → markup).**
NO APLICA hoy: requiere piso (−15% desde máximos) y estamos a −1.7%.
Un gap-down de miedo en máximos NO es la pata (A) del patrón; es, como
máximo, ruido previo a un eventual piso futuro. Si el selloff profundiza
hacia −15%, ESTE documento deja pre-registrados los triggers a vigilar:
AAII < −15, COT asset managers acumulando en el piso, y régimen para el
filtro de timing.

**H2 — Retest como timing.** Solo tiene edge medido en STAGFLATION
(fwd60 +7.3% vs +2.6% control); en GOLDILOCKS el retest es PEOR que
piso+bote (+3.7% vs +6.8%). Sin régimen declarado y sin piso, **ninguna
acción de timing se deriva de hoy**. Intentar "comprar el dip" por narrativa
sería operar fuera de los números propios.

**H3 — Termómetro (miedo medible).** El pulso existe (VIX +13.8%, futuros
rojos, AAII en flip), pero por debajo de todos los umbrales de etiqueta
"piso con miedo". Lectura: **miedo intradiario en techo, no capitulación**.

## 5. Incidente de datos (bloqueante para todo lo que use el motor)

**El cache de precios de producción está contaminado** (ver SESSION_LOG de hoy
para la evidencia completa): 28 grupos / 66 tickers con colas idénticas
(ej. SPY=AAPL=TSLA=510.37 vs 764.29/332.27/365.44 en vivo; volúmenes 13x),
historias reescritas completas vs espejo Sep-2, VIX cache en 96 vs 18 real.
El daemon API (código main sin piso en el loop de warmup) está en loop
patológico (ciclos de 862s/1258s + hits 0.0s, 82% CPU sostenido, 453 líneas
de log) reescribiendo el cache en tandas. **Ningún backtest, ticket, régimen
HMM ni screen que lea `backend/data/cache/*.parquet` es confiable hasta
resolverlo.** Los gauges usados en §§1-3 (futuros/VIX/AAII en vivo o archivos
propios verificados) NO dependen de ese cache y sostienen este análisis.
Acción propuesta a Boris: (a) ordenar merge del fix-forward con piso
(`fix/warmup-criterio2-20260911`, frena el spin), (b) decidir recuperación
del cache (espejo Sep-2 + re-descarga limpia tras identificar el escritor),
(c) no correr decisiones del motor hasta entonces.

## Veredicto (una línea por hipótesis)

- H1 ciclo institucional: **no aplica** (sin piso; triggers pre-registrados arriba).
- H2 retest-timing: **sin acción** (sin régimen STAGFLATION declarado).
- H3 termómetro: **miedo leve en techo** (VIX +13.8%, AAII −1.39, sin capitulación).
- H-motor: **BLOQUEADO por incidente de datos** hasta resolución.
