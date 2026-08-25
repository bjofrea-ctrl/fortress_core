# Árbol de decisión estratégico — Fortress Core

Documento vivo, acordado con Boris (2026-08-25). Objetivo: no perder de vista el
mapa completo de caminos a explorar, en qué orden, y con qué criterio se pasa de
uno al siguiente. Ningún camino se descarta por adelantado — se agota con el
método, no con opinión.

## Principio rector

Este es un experimento. La fortaleza real del proyecto es la metodología
(pre-registro, PBO/CSCV, DSR, Bonferroni) aplicada con rigor académico — eso no
se negocia en ningún camino. Lo que sí se revisa en cada bifurcación es si el
camino elegido sigue teniendo sentido con la evidencia actual, no con lo que se
decidió hace semanas por defecto.

**Regla de oro que atraviesa TODO el árbol**: ningún trial nuevo se corre sin
pre-registro y decisión explícita de Boris (ONBOARDING.md #1). Automatizar
búsqueda amplia está bien — pero cada candidato que se prueba de verdad consume
presupuesto del mismo ledger compartido, y el umbral Bonferroni/DSR sube con
cada uno. "Probar muchísimo" y "corregir por cuánto se probó" van juntos,
siempre — la alternativa (probar sin corregir) ya se demostró que produce
overfitting de proceso con solo 27 variantes (PBO 0.47, §39/§40); a mayor
escala el problema es peor, no mejor.

## El embudo, aplicado dentro de cada rama

Antes de gastar compute caro (backtest completo, HMM, walk-forward), cada rama
usa dos etapas:

1. **Screening barato**: rank IC vectorizado u otro test rápido, cobertura
   amplia (cientos/miles de variantes si hace falta), automatizable con
   varios agentes en paralelo.
2. **Confirmación cara**: solo los sobrevivientes del screening (con su
   umbral Bonferroni ya subido por cuántos se probaron) pasan al backtest
   completo walk-forward + PBO/CSCV + DSR.

---

## Camino A — Espacio actual (50 US large-cap, diario) — EN CURSO

El camino ya recorrido: 26+ trials, todo refutado salvo momentum+RSI, que a su
vez no pasa DSR OOS (0.61 < 0.95) ni PBO (0.47, overfitting sustancial).

- **A1 — Brecha 2, M3 compuerta standalone** (asignada a Kilo, en curso). El
  candidato con mejor fundamento pendiente: ¿operar solo en régimen GOLDILOCKS
  mejora el sistema completo? Genuinamente inédito (verificado contra ROADMAP).
- **A2 — Si A1 no cumple**: re-test angosto de sentimiento + macro contra
  target de barreras (M1), el único ángulo que §23 no cubrió (§23 solo probó
  momentum/RSI/ADX contra ese target).
- **A3 — Antes de declarar A agotado**: verificar H3.1 (¿la familia `re_test`
  del ledger evade la corrección Bonferroni por diseño? — hallazgo de la
  auditoría GLM, sin decisión tomada todavía). Si el conteo de trials tiene un
  problema de contabilidad, "agotado" podría no significar lo que creemos.
- **A4 — Extensiones baratas dentro de la misma infraestructura** (no
  necesitan datos nuevos, mismo yfinance diario): estacionalidad (turn-of-
  month), variante 52-week-high (distinta de momentum 12-1), factores de
  valor/calidad SI se consigue mejor cobertura de fundamentales (EDGAR dio
  10% de cobertura — pudo matar señal por falta de dato, no por falta de
  señal real).
- **A5 — Quality + Value sistemático ("Buffett's Alpha", Boris 2026-08-25)**:
  distinto de lo ya refutado — el fundamentals test previo era ranking
  cross-sectional crudo con 10% de cobertura EDGAR (candidato a revivir por
  A4 si mejora la cobertura). Esto es otra cosa: el paper académico Frazzini/
  Kabiller/Pedersen ("Buffett's Alpha") descompone el retorno de Buffett en
  factores sistematizables — calidad (rentabilidad, estabilidad de
  ganancias), valor (P/E, P/B), bajo-beta, apalancamiento moderado — nunca
  probado acá con ese diseño. Puede correr EN PARALELO con A1 (Brecha 2,
  Kilo) — son hipótesis independientes que alimentan el mismo ledger, no
  dos caminos separados.

**Gate de salida de A**: cuando A1-A5 estén cerrados (o descartados con
evidencia) y A3 confirme que el ledger cuenta bien, recién ahí se considera
agotado el camino A — con evidencia, no por cansancio.

## Integración con el ensamble de paper trading (Boris, 2026-08-25)

Todo candidato que cierre CUMPLE en cualquier rama de este árbol (A5, B1, lo
que sea) no arranca un "modelo nuevo" separado — se suma como una fuente más
al ensamble multivariante de `PROPUESTA_PAPER_TRADING_PROSPECTIVO.md`,
combinado vía `BayesianOnlineUpdater` con el mismo criterio de Sharpe
acumulado, nunca por selección de un ganador único. El objetivo de largo
plazo (marco de Ray Dalio, "Santo Grial de la inversión"): 15-20 fuentes de
retorno genuinamente no correlacionadas reducen el riesgo del portafolio de
forma dramática, con el beneficio aplanándose después de ese número — no es
un sistema aparte, es hacia dónde converge este mismo árbol a medida que se
validan más candidatos. Un solo ledger, un solo árbol, un solo ensamble.

---

## Camino B — Universo distinto, misma infraestructura (equities, yfinance)

Hipótesis: no es solo el factor, es el mercado — S&P500/Nasdaq large-cap son
el rincón más arbitrado por institucionales/HFT/fondos cuant. Las anomalías
sobreviven donde el capital grande NO puede desplegarse a escala sin mover el
precio — restricción de capacidad, no de conocimiento.

- **B1 — Small/mid-cap US** (mejor prior, cero costo nuevo: mismo yfinance,
  otro universo). Primera opción si A se agota.
- **B2 — Mercados emergentes** (ADRs o tickers directos vía yfinance).
  Momentum documentado como más fuerte ahí en la literatura académica.

**Gate de salida de B**: mismo criterio que A — DSR/PBO con la misma vara,
agotado con evidencia.

---

## Camino C — Otra clase de activo, infraestructura ya integrada (Alpaca)

- **C1 — Cripto**. Accesible ya (Alpaca, ya probado para medir costos reales).
  Cola larga de altcoins con menos cobertura institucional que BTC/ETH.
  **Caveat real, no cosmético**: acá el riesgo no es solo de eficiencia de
  mercado — hay riesgo idiosincrático (proyectos que colapsan, rug-pulls) que
  el proyecto no maneja hoy. Necesitaría su propio modelo de riesgo antes de
  desplegar capital real, no solo el mismo motor adaptado.

---

## Camino D — Nueva fuente de datos, requiere inversión real

Acá sí hace falta evaluar costo/factibilidad con hechos actuales antes de
decidir — no citar la decisión vieja de "no escalar en serio" sin comprobar
si aplica a lo específico que se propone.

- **D1 — Opciones/GEX, snapshot diario** (preferido). Espacio donde un shop
  chico puede tener ventaja real: la mayoría no tiene el dato ni la
  infraestructura para procesarlo. Costo medio (feed de opciones, no es
  infraestructura de baja latencia). **Pendiente**: investigar costo/
  factibilidad real antes de pre-registrar nada.
- **D2 — Intradía (microestructura)** — **NO priorizado, discrepancia
  explícita con la sugerencia inicial de la auditoría externa**: intradía no
  es "menos arbitrado", es probablemente el rincón MÁS competido que existe
  (HFT con colocation, fibra dedicada). El prior ahí es peor, no mejor, para
  un shop con una Mac y una VPS chica. Además §13 (gap-reversion) ya cerró
  que la ejecución intradía no es viable con la infraestructura actual — eso
  sigue siendo cierto salvo que se decida invertir en un motor de ejecución
  intradía real, lo cual es la MISMA inversión de recursos que "escalar en
  serio" ya evaluó y descartó una vez (revisar si las condiciones cambiaron
  antes de reabrirlo).

---

## Resumen visual

```
Camino A (actual, EN CURSO)
├─ A1 Brecha 2 M3 standalone ........... Kilo, en curso
├─ A2 Re-test sentimiento/macro×barreras  si A1 falla
├─ A3 Verificar H3.1 (Bonferroni re_test) antes de cerrar A
├─ A4 Extensiones baratas (estacionalidad, 52w-high, fundamentales mejor cobertura)
└─ A5 Quality+Value sistemático (Buffett's Alpha) ... PARALELO a A1, mismo ledger
        │
        ▼ (si A se agota con evidencia)
Camino B (universo distinto, misma infra)
├─ B1 Small/mid-cap US ................. mejor prior, costo cero
└─ B2 Mercados emergentes
        │
        ▼ (si B se agota)
Camino C (otra clase de activo, infra ya integrada)
└─ C1 Cripto ............................ requiere modelo de riesgo propio
        │
        ▼ (si C se agota o se descarta por riesgo)
Camino D (nueva inversión de datos/infra — evaluar costo real antes de decidir)
├─ D1 Opciones/GEX diario ............... preferido
└─ D2 Intradía .......................... NO priorizado (peor prior, ya descartado por §13)

Todo candidato CUMPLE, de cualquier rama ──▶ ENSAMBLE de paper trading
(PROPUESTA_PAPER_TRADING_PROSPECTIVO.md) ──▶ meta Dalio: 15-20 fuentes
no correlacionadas, combinadas por Sharpe acumulado (BayesianOnlineUpdater),
nunca por ganador único. Un solo sistema, no uno paralelo.
```

## Nota sobre paralelismo (2026-08-25, revisión de GLM incorporada)

A4 (extensiones baratas en el universo actual) y B1 (small/mid-cap) no tienen
dependencia lógica real entre sí — son preguntas distintas (factor nuevo en
universo viejo vs. factor viejo en universo nuevo) y podrían correr en
paralelo si se pre-registran como familias separadas del ledger, cada una con
su propio Bonferroni. Dos condiciones antes de habilitar ese paralelismo:

1. **A3 (verificar H3.1) va primero, no en paralelo con más familias
   nuevas** — si la segmentación de familias del ledger tiene el riesgo de
   evadir Bonferroni que señaló la auditoría, sumar más familias paralelas
   antes de resolver esa duda podría empeorar el problema, no evitarlo.
2. **Capacidad de revisión, no solo estadística** — cada pre-registro nuevo
   exige la misma revisión rigurosa (verificar contra el ledger, correr
   tests, chequear el diseño) antes de aprobarse. Más paralelismo es más
   carga de esa revisión al mismo tiempo, no es gratis aunque sea
   estadísticamente sano.

## Próxima revisión

Este árbol se actualiza cada vez que un gate se cierra (con evidencia real,
artefacto citado) o se abre un nuevo camino. No es un plan fijo — es el mapa
vivo de dónde estamos parados y por qué.
