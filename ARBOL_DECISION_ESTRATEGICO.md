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

- **Marco organizador: fundamental vs. técnico (Boris, 2026-08-26)** — todo
  A6 en adelante se separa en dos capas distintas, que hasta hoy el proyecto
  no distinguía con claridad:
  - **Fundamental = QUÉ activo plantar (selección)**: calidad del negocio,
    posición en la cadena de valor, si encaja con la temporada/cuadrante
    actual. Es sobre el activo en sí mismo, no sobre el momento de actuar.
    A5 (Buffett's Alpha) y A6.3 (más abajo) son de esta capa.
  - **Técnico = CUÁNDO sembrar y cosechar (timing)**: el momentum+RSI que ya
    usa el motor congelado es 100% técnico — lee patrón de precio, no dice
    nada sobre si la empresa es buena o mala como negocio. M3/A1 (régimen) y
    A6.2 (cadencia por beta) son de esta capa.
  Las dos capas son complementarias, no sustitutas — un activo fundamentalmente
  bueno en el momento técnico equivocado, o un timing técnico perfecto sobre
  un activo fundamentalmente débil, pierden valor igual. El motor actual solo
  cubre la capa técnica; la capa fundamental está casi sin explorar (A5 fue
  el único intento, y era un ranking crudo, no el enfoque de A6.3).

- **A6 — Heterogeneidad sectorial/por tipo de activo (Boris, 2026-08-26)
  [capa fundamental — selección]**:
  hueco real, verificado — hasta ahora TODOS los trials (§13-§47) aplicaron
  la señal de forma UNIFORME a los 50 nombres del universo, sin diferenciar
  por sector o tipo de activo. El régimen macro (M3) condiciona el mercado
  entero (temporada general), no la "temporada" específica de cada activo; la
  estacionalidad de A4 es de calendario, no de comportamiento por tipo de
  activo. Analogía de Boris: no todas las frutas se dan en la misma época ni
  responden igual a la misma condición climática (una helada afecta distinto
  a la uva que a la sandía) — un tech stock y una utility pueden responder
  distinto al MISMO indicador porque tienen dinámicas de precio y
  vulnerabilidades estructuralmente distintas. Hipótesis: con 50 nombres
  heterogéneos tratados igual, una señal sectorial real podría diluirse en
  el promedio — coherente con que el edge nunca superó DSR pese a IC pooled
  positivo en varios factores. Prioriza profundidad (conocer a cabalidad el
  comportamiento de un sector/activo) por sobre diversificar a ciegas.
  Diseño pendiente de pre-registro: segmentar el universo por sector
  (GICS o clasificación equivalente disponible) y medir si el factor
  momentum+RSI (o algún otro ya probado) tiene IC/DSR distinto por segmento
  en vez de uniforme — screening barato primero (rank IC por sector), antes
  de comprometer presupuesto Bonferroni en confirmación cara.

  **Aclaración de alcance (Boris, 2026-08-26) — esto es la versión FÁCIL,
  no A6.1 más abajo**: no hace falta predecir cuándo cambia el régimen. La
  pregunta es más simple — analogía de Boris: "es verano y hay poca lluvia
  (dato YA conocido) — ¿plantarías uvas para buen vino, o manzanas?". M3 ya
  clasifica el cuadrante ACTUAL de forma reactiva (funciona, ya probado en
  §46) — lo que falta es la mitad más simple: dado que M3 ya dice en qué
  cuadrante estamos HOY, decidir qué sector/activo favorecer en ESE
  cuadrante conocido. Es abordable con lo que ya existe (M3 + universo de
  50), no requiere pronóstico de nada — es la prioridad práctica antes que
  A6.1.

  **Extensión (Boris, 2026-08-26)** — dos dimensiones más de la misma
  heterogeneidad, no cubiertas hoy:
  - **Sensibilidad a liquidez**: el motor ya tiene `volume_ratio>=1.0` como
    GATE binario (`signal_engine.py`), pero es un filtro de pasa/no-pasa,
    no una segmentación — no distingue si el factor se comporta distinto
    en régimen de liquidez abundante vs escasa dentro de los que sí pasan
    el gate. Hipótesis: nombres más líquidos podrían absorber momentum de
    forma distinta a los menos líquidos del mismo universo de 50.
  - **Oferta/demanda y factores geopolíticos** (analogía de Boris: la
    sandía en invierno es más cara por oferta escasa; el petróleo se mueve
    por oferta/demanda + decisiones de gobiernos/cadenas de suministro).
    Esto aplica con más fuerza a *commodities* que a las acciones del
    universo actual (50 US large-cap) — más relevante si algún día se
    evalúa Camino D (nueva fuente de datos/activo) que al Camino A tal
    como está hoy. Para equities, el equivalente más cercano y ya
    accesible sería sensibilidad sectorial a shocks de oferta (ej. energía/
    materiales vs. sectores no expuestos a insumos físicos) — overlap
    parcial con la segmentación sectorial de arriba, no una dimensión 100%
    aparte.

  **A6.1 — Factores líderes de transición de cuadrante (Boris, 2026-08-26,
  conectado a M3/§46) [capa técnica — timing]**: verificado que M3
  (`regime_gate.py`) ya construye
  features de crecimiento (`growth_SPY/EFA/QQQ`), inflación
  (`inflation_GLD/DBC/TIP`) y tasas (`rates_TLT/AGG`) + VIX — la misma
  estructura growth×inflation del marco de Dalio (4 cuadrantes), clasificada
  vía HMM. Hoy M3 es **reactivo**: clasifica el régimen ya ocurrido (retornos
  trailing) y solo prende/apaga el motor entero según el cuadrante actual
  (probado como A1/§46, cerrado NO_INTERPRETABLE por piso insuficiente).
  Propuesta de Boris: en vez de solo clasificar el cuadrante presente,
  investigar qué factores empujan la transición ENTRE cuadrantes (subida y
  bajada de crecimiento/inflación) — para usar eso como condición de
  compra/venta/rebalanceo ANTES de que el cuadrante termine de confirmarse,
  no después.

  **Nota de honestidad metodológica**: esto es un salto de dificultad real
  respecto a A6 (segmentación) — no es clasificar régimen, es *anticipar*
  su transición, más cerca de pronóstico macro que de clasificación de
  patrón. HMM por diseño es retrospectivo (ajusta estados a datos ya
  ocurridos); encontrar factores líderes con poder predictivo genuino
  (no sobreajustado) es un problema mucho más exigente, con su propio riesgo
  de overfitting si no se pre-registra con el mismo rigor que todo lo
  demás. Queda anotado como dirección de investigación futura, NO como
  trial listo para pre-registrar — requiere diseño propio (qué factores
  candidatos, qué ventana de anticipación, cómo evitar lookahead) antes de
  poder correrse.

  **Mecanismo concreto de por qué es difícil, y por dónde empezar (Boris,
  2026-08-26, analogía de la fiebre del oro)**: la escasez real de oro
  ocurre ANTES de que el mercado agregado lo sepa — hay un rezago de
  difusión de información, y mientras tanto la demanda de palas sigue
  sostenida por sentimiento/inercia conductual (la gente sigue comprando
  por hábito o esperanza, no por información nueva). Esto explica POR QUÉ
  cualquier indicador basado en PRECIO (técnico) es, por construcción, un
  eco rezagado del cambio fundamental — nunca lo detecta en el momento en
  que realmente ocurre, solo el reflejo tardío cuando ya se difundió lo
  suficiente. Consecuencia práctica: más sofisticación en patrones de
  precio no resuelve A6.1 — la brecha entre "quién ya sabe" (dinero
  informado) y "quién sigue actuando con información vieja" (dinero tardío)
  es la variable real a buscar, y se aproxima con datos de FLUJO/
  posicionamiento (institucional vs retail, dispersión de estimados de
  analistas), no con más indicadores derivados del precio mismo.

  **Traducción a diseño estadístico concreto (2026-08-26)** — toda la
  filosofía de A6/A6.1 (frutas y estaciones, uva vs zanahoria frente a la
  lluvia, cuadrantes de Dalio) se traduce a UNA idea estadística estándar:
  el efecto de un factor (momentum+RSI) no es uniforme entre activos — está
  modulado por (a) el régimen macro vigente (M3) y (b) la sensibilidad
  estructural propia de cada activo a esos mismos factores macro. En
  finanzas esto es un modelo de **cargas factoriales condicionadas
  (interacción factor×régimen×activo)** — nada exótico, es la misma lógica
  de un modelo multi-factor (estilo Fama-French) aplicada con el M3 que ya
  existe. Tres piezas, escalando de barato a caro, sin descartar ninguna:

  1. **Perfil de sensibilidad por activo (screening, barato, NO consume
     Bonferroni — es perfilado, no trial)**: para cada uno de los 50
     activos, regresión rolling de sus retornos contra los MISMOS factores
     macro que M3 ya calcula (`growth_SPY/EFA/QQQ`, `inflation_GLD/DBC/TIP`,
     `rates_TLT/AGG`, VIX). Da el "perfil de cultivo" de cada activo — cuánto
     sufre o se beneficia cada uno de cada factor — con datos que el
     proyecto ya carga para M3, sin fuente nueva.
  2. **Rank IC condicionado, no agrupado (screening, barato)**: en vez de un
     único IC de momentum+RSI pooled sobre los 50 (como todos los trials
     hasta hoy), calcular el IC SEPARADO dentro de cada celda
     (cuadrante M3 × bucket de sensibilidad del paso 1). Es la traducción
     exacta de "uva vs zanahoria cuando llueve": mismo factor, folds
     distintos según sensibilidad conocida. Si el IC condicionado es
     sustancialmente distinto entre celdas, confirma que el pooled diluye
     señal real — recién ahí vale la pena la confirmación cara.
  3. **Backtest confirmatorio (caro, SÍ consume Bonferroni, pre-registro
     obligatorio)**: solo si el paso 2 muestra heterogeneidad real, un
     trial formal que rote hacia los activos de sensibilidad favorable
     según el cuadrante M3 vigente, medido con el mismo rigor DSR/PBO de
     siempre — mismo criterio de éxito binario, mismo umbral del ledger.

  **Dónde encaja `BayesianOnlineUpdater` (verificado en código, no
  hipotético)**: ya generaliza a esto sin construir nada nuevo —
  `probabilistic_engine.py` mantiene pesos por CLAVE de texto arbitraria
  (patrón ya en uso: `f"{regimen}_{factor}"` en `triad_agents.py`).
  Extender la clave a `f"{regimen}_{sector}_{factor}"` le permitiría
  aprender pesos regimen×sector online desde `pnl_r` real, sin tocar la
  clase. **Limitación honesta**: cada clave aprende de forma INDEPENDIENTE
  (Beta-Binomial simple, sin partial pooling/shrinkage entre celdas
  relacionadas) — con 4 regímenes × ~11 sectores GICS sobre solo 50
  activos, la mayoría de las celdas tendrían muy pocas observaciones para
  aprender de forma confiable por sí solas. Un modelo jerárquico bayesiano
  de verdad (que preste fuerza estadística entre sectores relacionados)
  sería más robusto, pero eso sí es código nuevo, no una extensión de
  nombres de clave — queda anotado como mejora futura si el paso 2 confirma
  que vale la pena, no como parte del diseño mínimo.

  **A6.2 — Beta/volatilidad determina la CADENCIA, no solo el activo (Boris,
  2026-08-26) [capa técnica — timing]**: dimensión adicional real. Mayor
  beta = mayor volatilidad =
  más oportunidades de "cosecha" en ambas direcciones (sube y baja) en el
  mismo período — no es lo mismo que llueva 4 veces al año (Coca-Cola, ~4%
  anual, baja vol) que 2-3 veces al DÍA (NVIDIA, oscila varios % por
  semana/día). La definición congelada hoy rebalancea **mensual para los 50
  por igual** — el mismo problema de uniformidad de A6, pero en el eje
  TIEMPO en vez del eje activo: un rebalanceo mensual puede promediar/perder
  varios movimientos reales de un nombre de alta beta dentro del mismo mes,
  mientras que para un nombre de baja beta esa cadencia puede sobrar (pocos
  movimientos reales que capturar, mantenerse posicionado todo el período
  captura mejor las pocas "lluvias" que caen). Pregunta de Boris respondida:
  sí, la estrategia debería diferir — probablemente cadencia de
  evaluación/rebalanceo más corta para beta alta, más larga (más cercana a
  buy-and-hold dentro del universo) para beta baja.

  **Límite importante, ya cerrado antes por otra razón — no confundir**:
  esto NO reabre la discusión de ejecución intradía (§13, D2, explícitamente
  NO priorizado por competencia de HFT/colocation). "Más frecuente que
  mensual" tiene margen amplio dentro de la infraestructura diaria ya
  existente (barras diarias de yfinance) — semanal, quincenal, cadencia
  variable por beta — sin tocar microestructura ni datos intradía. Es una
  pregunta de FRECUENCIA DE REBALANCEO condicionada por volatilidad, no de
  velocidad de ejecución; distinta en su raíz de lo que §13 cerró.
  Diseño pendiente de pre-registro: mismo funnel barato→caro que A6 arriba
  — perfil de volatilidad realizada por activo (ya casi gratis, deriva del
  mismo perfil de sensibilidad del paso 1), screening de si el IC de
  momentum+RSI mejora con cadencia condicionada por beta vs. el mensual
  uniforme actual, y recién si hay señal, confirmación cara con el mismo
  rigor DSR/PBO.

  **A6.3 — Posición en la cadena de valor / "vendedor de palas" (Boris,
  2026-08-26) [capa fundamental — selección]**: patrón histórico real
  (fiebre del oro: los vendedores de herramientas y suministros ganaron de
  forma consistente mientras la inmensa mayoría de los mineros individuales
  perdía o apenas empataba; los ferrocarriles tuvieron un patrón similar con
  las empresas de rieles/acero). Distinción clave de Boris: no importa CUÁL
  empresa específica gane dentro de una categoría (IA, robótica) — las
  empresas "habilitadoras" (semiconductores, centros de datos, energía,
  componentes) le venden a TODA la categoría por igual, diversificando el
  riesgo de "apostar al ganador" entre cientos de clientes en vez de
  concentrarlo en una sola apuesta. Es 100% capa FUNDAMENTAL — clasifica el
  modelo de negocio del activo, no dice nada sobre cuándo comprar/vender
  (eso lo sigue resolviendo la capa técnica, A1/A6.1/A6.2).

  **Limitación honesta**: operacionalizar esto de verdad (revenue
  diversificado entre clientes, posición en la cadena de valor) requiere
  datos fundamentales/cualitativos — mismo obstáculo que ya mató el test de
  fundamentales crudo (cobertura EDGAR 5/50). **Atajo barato disponible
  sin esperar mejor cobertura**: el universo actual de 50 ya contiene
  nombres que califican como "pala" para la ola de IA sin necesitar datos
  nuevos — NVDA/AVGO/QCOM (semiconductores), MSFT/ORCL/CSCO (nube/
  infraestructura) — etiquetado manual de un puñado de nombres, no
  fundamentales sistemáticos de los 50. Diseño pendiente de pre-registro:
  comparar el desempeño (Sharpe/DSR) de ese subconjunto "habilitador"
  etiquetado a mano contra el resto del universo y contra el pooled actual
  — screening barato, confirmación cara solo si hay separación real.

  **La ventaja de "pala" no es estática — tiene su propio ciclo (Boris,
  2026-08-26)**: al inicio de la fiebre, pocos vendedores + demanda
  explosiva → precio/margen alto. Al final, la demanda de mineros nuevos se
  seca Y la oferta de palas se disparó (entraron competidores viendo que el
  negocio funcionaba, más mineros que abandonan y revenden sus palas
  usadas) → **sobre-stock**, precio se derrumba al costo de una pala común.
  Consecuencia: etiquetar "esto es una pala" UNA vez no alcanza — la
  pregunta correcta es en qué momento del ciclo de oferta/demanda DE LA
  PALA MISMA (no del oro/tema macro) está el activo hoy: ¿escasez de
  competidores todavía, o ya se saturó de competencia y el margen se está
  comprimiendo aunque la categoría (IA) siga creciendo? Este ciclo es
  propio de cada "pala" y distinto del ciclo macro que mide M3 — no se
  puede asumir que la ventaja de A6.3 dura para siempre solo por haberla
  identificado una vez.

**Gate de salida de A**: cuando A1-A6 estén cerrados (o descartados con
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
├─ A1 Brecha 2 M3 standalone ........... CERRADO, NO_INTERPRETABLE (§46, 2026-08-26)
├─ A2 Re-test sentimiento/macro×barreras  si A1 falla (no aplica, A1 no fue NO_CUMPLE)
├─ A3 Verificar H3.1 (Bonferroni re_test)  CERRADO, garantías implementadas (2026-08-26)
├─ A4 Extensiones baratas (estacionalidad, 52w-high, fundamentales mejor cobertura)
├─ A5 Quality+Value sistemático (Buffett's Alpha) . CERRADO, NO_CUMPLE (§47, 2026-08-26)
└─ A6 Heterogeneidad sectorial/por activo .......... pendiente de pre-registro (Boris, 2026-08-26)
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
