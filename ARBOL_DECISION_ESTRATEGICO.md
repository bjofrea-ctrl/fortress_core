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

  **Ejemplo concreto con nombres reales del universo: shock exógeno tipo
  terremoto (Boris, 2026-08-26)** — misma heterogeneidad sectorial de
  arriba, esta vez con símbolos ya presentes en `NEW_UNIVERSE`
  (`fetch_universe_data.py`), no solo especulación:
  - **Suben** (patrón de reconstrucción): **CAT** (maquinaria pesada para
    remoción de escombros/reconstrucción), **HD** (pico de ventas
    post-desastre — patrón que retail ya rastrea después de huracanes en
    EEUU). Fuera del universo pero conceptualmente relevante: generadores
    (Generac), homebuilders, y reaseguradoras SIN exposición en la zona
    (el mercado de seguros se endurece a nivel nacional después de un
    evento grande, no solo en la zona afectada).
  - **Bajan**: aseguradoras/reaseguradoras con exposición concentrada en
    la zona (ninguna en el universo actual — no hay AIG/Travelers/Chubb,
    queda conceptual); bancos regionales con hipotecas concentradas ahí
    (JPM/BAC están en el universo pero demasiado diversificados
    nacionalmente para que un sismo regional les pegue fuerte);
    **semiconductoras si el sismo pega cerca de una planta de
    fabricación** — conecta con A6.3 (riesgo geográfico de la capa
    "pala," no documentado ahí todavía) — precedente real del mismo
    mecanismo: terremotos en Taiwán interrumpieron producción de chips y
    movieron acciones de semiconductoras globalmente. AVGO/QCOM/TXN están
    en el universo actual y tienen exposición a fabricación.
  - **Advertencia honesta — falacia de la ventana rota (Bastiat)**: que
    CAT/HD suban no significa que el terremoto sea bueno para la
    economía — es capital destruido siendo reemplazado, no riqueza
    nueva. Para el modelo de trading es irrelevante (el precio sube
    igual, eso es lo que se opera), pero no hay que confundir "sube el
    precio" con "es positivo" al leer este ejemplo.
  - **Movimiento especulativo vs. fundamental (Boris, 2026-08-26)**: el
    salto de precio inicial (CAT/HD subiendo, aseguradoras cayendo) es
    reacción a la narrativa, instantánea — el traspaso real del
    costo/margen a las ganancias reportadas (**cost pass-through**,
    concepto de economía industrial) es lento e incierto (contratos
    vigentes, competencia, rigidez de precios). Si el traspaso no se
    completa como el mercado asumió el día 1, el precio revierte —
    patrón conocido en finanzas conductuales como **hipótesis de
    sobrerreacción** (De Bondt & Thaler, 1985) / "comprá el rumor, vendé
    la noticia." Es simétrico: aplica igual al ganador temporal
    (cementera que sube y revierte) que al perdedor temporal (aseguradora
    que cae de golpe y puede recuperar si la exposición real es menor a
    la temida). Herramienta académica para medirlo de verdad si algún día
    se pre-registra: **metodología de estudio de eventos** (Fama/
    MacKinlay) — retorno anormal acumulado en ventanas día 0/día+5/día+20
    para separar el "pop" de anuncio de la deriva fundamental posterior.
  - **Marco epistémico que amarra todo lo de hoy**: no se predice el
    futuro con certeza — se asigna un peso de probabilidad explícito
    basado en mecanismo + clase de referencia, y se corrige cuando llega
    evidencia nueva (**pronóstico calibrado**, término más citado:
    Philip Tetlock, *Superforecasting*). Es el hilo común entre reference
    class forecasting (próximo oro), destrucción creativa, y esta
    distinción especulativo/fundamental.
  - **Estructura de apuesta que captura ambos lados (Boris, 2026-08-26)**:
    comprar cementera + shortear aseguradora en el mismo evento es una
    operación **long/short basada en evento** (event-driven long/short),
    específicamente un **pairs trade / relative value trade** — la
    propiedad clave no es "ganar por los dos lados" sino quedar
    **neutral al mercado**: la ganancia depende del SPREAD entre las dos
    patas, no de si el mercado sube o baja en general, así que reduce
    exposición al riesgo sistemático que sí tiene una posición long-only
    simple. **Verificado en el código, no solo conceptual**: fortress_core
    hoy es long-only — `execution_costs.py` y `pipeline_daily_signal.py`
    solo generan `"buy"` para entradas; `"sell"` aparece únicamente como
    cierre de una posición larga, nunca como apertura de un short
    independiente. Esta estrategia de dos patas es conceptualmente sólida
    pero NO ejecutable con la arquitectura actual sin agregar mecánica de
    venta en corto — cambio estructural real, no un ajuste de parámetro,
    y ninguna decisión de hacerlo sin definición explícita de Boris.

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

  **Secuencia del colapso: ¿cae primero el oro o la pala? (Boris,
  2026-08-26)**: hipótesis con dos mecanismos concretos, ninguno testeado
  todavía (no hubo busto de IA en este ciclo — queda documentado, no
  pre-registrado):
  1. **Efecto bullwhip** (cadena de suministro): una desaceleración chica en
     demanda final se amplifica río arriba porque los proveedores (palas)
     operan con backlog/capacidad construida por adelantado — un enfriamiento
     leve en monetización de IA puede traducirse en un frenazo brusco de
     pedidos de chips/datacenters.
  2. **Asimetría de visibilidad**: el capex de las palas es discrecional,
     trimestral, con guidance público — se repriea rápido. El ingreso del
     oro (contratos/suscripciones multianuales) es más opaco/gradual — tarda
     más en mostrarse en resultados reportados. Consecuencia esperada: la
     acción de la pala se mueve ANTES que la del oro, aunque el oro sea la
     causa raíz.
  Precedente parcial (no prueba, solo patrón histórico similar): la burbuja
  .com — Cisco/Nortel/fibra óptica colapsaron con la misma dinámica de
  sobre-oferta ya descrita arriba (entraron competidores, se construyó
  capacidad de más, un enfriamiento leve de demanda produjo compresión de
  margen brutal).

  **El próximo oro (Boris, 2026-08-26)**: pregunta genuinamente especulativa,
  no estadística — el universo actual de 50 large-caps no puede responderla
  (la mayoría de los candidatos ni cotiza todavía). Lo reusable no es
  predecir el ganador sino el MARCO: categoría con alta incertidumbre sobre
  QUIÉN gana pero una dependencia física/de infraestructura común que TODOS
  los competidores necesitan sin importar quién gane (igual que
  semiconductores para IA). Candidatos que menciona el mercado hoy (no
  predicción del proyecto, solo ejemplos del marco): robótica
  (actuadores/sensores/motores), computación cuántica
  (criogenia/materiales especializados), biotecnología/longevidad
  (secuenciación/automatización de laboratorio), economía espacial, fusión.
  Queda 100% conceptual — no hay pre-registro posible sin universo/datos.

  **Método para asignar probabilidad sin certeza: razonamiento por clase de
  referencia (Boris, 2026-08-26)**: cuando el caso es genuinamente nuevo (no
  hay serie de tiempo que backtestear), la forma correcta de fundamentar una
  probabilidad no es inventar una historia sobre ESE caso puntual (Kahneman/
  Tversky lo llaman "inside view") sino compararlo contra la clase de casos
  históricos/actuales que comparten su estructura ("outside view" /
  *reference class forecasting*, formalizado por Flyvbjerg) y usar la tasa
  base de esa clase. Es la versión cualitativa del mismo principio que
  sostiene el backtest cuantitativo del proyecto — DISTINTA herramienta,
  mismo espíritu: no confiar en la narrativa, confiar en el patrón repetido.
  Ejemplo aplicado (robótica vs. jarrones de greda, ambos como candidatos a
  "próximo oro"): robótica comparte con la clase de referencia de "oros"
  exitosos (fiebre del oro, ferrocarriles, internet, IA) cuatro rasgos
  verificables hoy — curva tecnológica en mejora exponencial (hereda los
  avances de percepción/control de la IA ya validada), flujo de capital de
  riesgo real y observable (Figure, Tesla Optimus, Unitree, plataformas de
  NVIDIA), driver de demanda estructural creciente (escasez de mano de obra,
  envejecimiento poblacional — datos demográficos verificables), y encaje en
  la clase "tecnología de propósito general que abarata un costo
  estructural" (abarata trabajo físico, igual que la IA abarató trabajo
  cognitivo). Jarrones de greda no comparte ninguno de los cuatro. La
  probabilidad más alta para robótica no es predicción del ganador — es que
  la evidencia disponible la ubica dentro de la clase de referencia de
  "oros" exitosos, y el otro candidato no está en ninguna clase relevante.

  **El liderazgo de mercado rota — destrucción creativa (Boris, 2026-08-26,
  ejemplos Nokia/Moderna)**: los 10 mejores activos de hoy no son los de
  hace 10 años ni serán los de dentro de 10-20 años — patrón documentado en
  economía como *destrucción creativa* (Schumpeter). Nokia y Moderna
  ilustran DOS mecanismos distintos de rotación, no el mismo:
  1. **Disrupción** (Nokia, "dilema del innovador" — Christensen): dominaba
     optimizando su tecnología existente (Symbian) hasta que un paradigma
     nuevo (touchscreen/iOS/Android) volvió obsoleta esa competencia
     central. Cambian las reglas de la categoría entera, no es un ciclo de
     oferta/demanda.
  2. **Reversión a la media por catalizador** (Moderna): no la desplazó
     tecnología nueva, la infló una demanda temporal (pandemia) que se
     desvaneció — mismo mecanismo que el ciclo de la "pala" ya documentado
     en A6.3 (escasez → sobreoferta → colapso de margen), aplicado a una
     empresa completa en vez de una categoría de proveedores.

  **Implicancia metodológica verificada en el código (no solo observación
  económica)**: el universo de 50 símbolos del proyecto
  (`backend/scripts/fetch_universe_data.py::NEW_UNIVERSE`) es una lista
  **estática**, fijada una vez, sin refresco automático. Si algún día se
  decide "actualizarla a los líderes actuales," eso mismo introduce el
  riesgo clásico de sesgo de supervivencia (survivorship bias) en cualquier
  backtest histórico corrido con esa nueva composición — construir el
  universo con el conocimiento de HOY de quién ganó y correrlo hacia atrás.
  No es una alarma para actuar ahora (cambiar el universo es decisión de
  Boris, no automática) — queda documentado como riesgo metodológico
  conocido, no algo a descubrir tarde.

  **Horizonte de inversión como filtro de relevancia (Boris, 2026-08-26)**:
  no todos los mecanismos de A6.x aplican en la misma escala de tiempo —
  el horizonte determina cuáles pesan:
  - **Corto plazo (días-semanas)** — horizonte en el que opera HOY el
    proyecto (momentum 12-1 meses, entradas/salidas de checkpoint en el
    orden de días): destrucción creativa tipo Nokia es prácticamente
    irrelevante (tarda años en completarse). Pesan cadencia por
    volatilidad (A6.2) y régimen macro actual (M3). Riesgo de universo
    estático es bajo.
  - **Mediano plazo (meses a 1-2 años)**: empieza a pesar el ciclo de la
    "pala" (A6.3, reversión a la media estilo Moderna) — se completa en
    esa ventana. El régimen macro de M3 rota varias veces en esta escala.
  - **Largo plazo (años-décadas)**: se vuelve central la destrucción
    creativa tipo Nokia y el riesgo de survivorship bias del universo
    estático (arriba) — un "comprá y mantené" de 10-20 años sobre el
    universo fijo de hoy apuesta a que ninguno de los 50 se vuelva el
    próximo Nokia, sin mecanismo de reemplazo.
  **Nota honesta de alcance**: el proyecto opera hoy en el primer tramo
  (corto plazo) — la mayoría de lo discutido en A6.3/destrucción creativa/
  próximo oro es relevante a un horizonte que el proyecto TODAVÍA no
  opera. Vale como marco para el futuro, no como algo que deba cambiar la
  operativa actual.

  **Principio organizador: necesidad estable vs. producto transitorio
  (Boris, 2026-08-26, ejemplo vela→LED)**: miopía del marketing (Theodore
  Levitt, 1960, *Marketing Myopia*) — su ejemplo canónico son los
  ferrocarriles, que creyeron estar en el "negocio de trenes" en vez del
  "negocio de transporte," y por eso los desplazaron autos y aviones: no
  porque el transporte dejó de ser necesario, sino porque se aferraron al
  PRODUCTO en vez de a la NECESIDAD. Complemento moderno: *Jobs to be Done*
  (Christensen) — el cliente "contrata" algo para resolver un trabajo
  (job); el job es estable, lo que se contrata para resolverlo cambia.
  Vela → filamento incandescente → LED: mismo job (ver en la oscuridad),
  tres cadenas de suministro completamente distintas (cera/mecha vs.
  tungsteno/vidrio vs. semiconductores) — el fabricante de velas que se
  definía por el producto, no por la necesidad, no tenía mecanismo de
  adaptación cuando llegó la electricidad; hoy la vela es casi decorativa.

  **Reformula el marco del "próximo oro" (arriba)**: el punto de partida
  correcto no es listar industrias candidatas (robótica, cuántica,
  biotech) sino listar **necesidades humanas estables** que nunca
  desaparecen — luz/visión, comunicación, movilidad, salud/longevidad,
  energía, alimento, refugio, **amplificación de capacidad cognitiva** — y
  preguntar qué solución tecnológica resuelve HOY cada una. La IA no es el
  oro actual por ser IA — es el oro porque es la solución actual al need
  de amplificar capacidad cognitiva, el mismo need que antes resolvieron
  la calculadora, la computadora, internet.

  **Ejemplo con cadena completa, no un solo salto (Boris, 2026-08-26)**:
  movilidad — trenes (rieles/acero) → auto a combustión (motor/petróleo) →
  auto eléctrico (batería/litio/semiconductores) → auto autónomo
  (sensores/LIDAR/cómputo, especulativo) → dron personal (motores/
  baterías/materiales livianos, especulativo). Mismo need resuelto por al
  menos cinco cadenas de suministro distintas en menos de 150 años, cada
  una con su propio "vendedor de palas" y su propio Nokia potencial —
  confirma que el principio no es anecdótico de la luz, se repite need por
  need.

  **Advertencia honesta que le agrega a A6.3**: la lógica de "no importa
  qué empresa de IA gane, vendele a todas" (diversificación por categoría)
  protege DENTRO de un paradigma tecnológico — pero no protege si el
  paradigma entero (chips de silicio) es reemplazado por otra forma de
  resolver el mismo need (cómputo cuántico, fotónico, neuromórfico). Los
  vendedores de semiconductores de hoy podrían ser las velas de mañana si
  eso pasa — riesgo de nivel superior al de A6.3, no cubierto por su
  propia lógica de diversificación.

**Gate de salida de A**: cuando A1-A6 estén cerrados (o descartados con
evidencia) y A3 confirme que el ledger cuenta bien, recién ahí se considera
agotado el camino A — con evidencia, no por cansancio.

### Indicadores ya existentes que conectan con A6/A6.1/A6.2/A6.3 (Boris,
### 2026-08-26 — "revivir" candidatos de `DICCIONARIO_INDICADORES.md`)

Antes de diseñar desde cero cualquier pieza de A6, revisar estos — ya están
construidos o diagnosticados, con estado real conocido (no supuesto):

- **A6.1 (rezago informativo / dinero informado vs. tardío)**: `market_structure.py`
  (T1.3) ya implementa Smart Money Concepts (Order Blocks, Fair Value Gaps,
  BOS/CHoCH, Liquidity Sweeps) — 18 tests + smoke real, pero **nunca
  integrado como señal**, solo detecta zonas, no genera score. Aparte, OFI y
  CVD (proxies de flujo de órdenes desde OHLCV) ya se testearon como factor
  de score directo y salieron **NO_CUMPLE** (§37/§38, rank IC 0/3 ventanas)
  — pero ese test midió si predicen retorno a 20 ruedas, no si sirven para
  detectar la transición de cuadrante que pide A6.1, que es una pregunta de
  diseño distinta sobre los mismos datos.
- **A6.2 (cadencia por volatilidad/beta)**: `realized_vol_regime`
  (`indicators.py`, ratio vol20d/vol100d) ya implementado y diagnosticado
  (`RESUMEN_HURST_VOL_REGIME.md`) — predice débilmente el NIVEL de vol
  futura (funcionó W1, no W2/W3), por eso no se promovió a señal. Pero A6.2
  no necesita predecir vol futura — necesita el régimen de vol ACTUAL para
  decidir cadencia de rebalanceo, un uso distinto del que se descartó.
- **A6/A6.3 (heterogeneidad por activo)**: Hurst exponent (`indicators.py`,
  mismo diagnóstico) mide persistencia vs. reversión a la media POR
  SÍMBOLO — una "personalidad" cuantitativa por activo que podría
  complementar el etiquetado manual de "palas" de A6.3 con algo medible en
  vez de solo cualitativo.
- **Si A4/A5 se revive con mejor cobertura de fundamentales**: `DICCIONARIO_
  INDICADORES.md` Parte II ya señala que los múltiplos de valoración
  (P/E, P/B, EV/EBITDA, FCF Yield) son el subgrupo con mejor respaldo
  académico (factor value, Fama-French) — punto de partida si se retoma,
  no el punto más débil que fue el sentimiento/AAII de Fase 0.6.

### Principio raíz: el valor es condicional al contexto actual, no fijo
### (Boris, 2026-08-26, ejemplo RAM/agua en el desierto)

Paradoja del valor (Adam Smith, diamante/agua, sin resolverla) resuelta
por la **revolución marginalista** (Menger/Jevons/Walras, 1870s, teoría de
la utilidad marginal): el valor no es propiedad intrínseca del bien, es
la utilidad de la PRÓXIMA unidad dado el estado actual del que valora.
RAM vale más que agua en contexto normal (agua abundante, utilidad
marginal de la próxima unidad ≈0); en el desierto el mismo vaso de agua
vale más — no cambió el bien, cambió el contexto, y con él la utilidad
marginal. Mismo principio que la lluvia y la uva: no hay regla fija
"lluvia=bueno/malo," depende del estado actual de la planta (floración
vs. cosecha).

**No es solo filosofía — ya está implementado en el proyecto**: M3
(`regime_gate.py`) no aplica una regla fija, lee el régimen ACTUAL
(growth/inflation/rates/vix) y condiciona el comportamiento a eso. A6.2
(cadencia por volatilidad) es la misma idea aplicada a la cadencia. Este
principio de condicionalidad al contexto es probablemente el más
fundamental de todo el bloque A6.x — explica POR QUÉ M3 y A6.2 tienen
sentido en primer lugar, no es una idea nueva sino la raíz de las que ya
existían.

### Síntesis de cierre del bloque A6.x (Claude Code, 2026-08-26)

- **Capa fundamental (QUÉ activo)**: la idea central que sostiene A6.3,
  destrucción creativa y "próximo oro" es la MISMA — necesidad estable vs.
  producto transitorio (Levitt). Nokia colapsó por aferrarse al producto
  en vez de a la necesidad; eso ES por qué existe la destrucción creativa,
  no una coincidencia entre secciones separadas.
- **Capa técnica (CUÁNDO actuar)**: A6.1, A6.2 y la distinción
  especulativo/fundamental son todas sobre timing, no sobre selección de
  activo — la separación fruta-fundamental/fruta-técnico se mantuvo
  consistente en todo el bloque sin contradicción.
- **Metanivel**: nada de hoy predice — arma un método de pronóstico
  calibrado (reference class forecasting + event study + sobrerreacción)
  que asigna probabilidad por mecanismo, no por certeza. Reusable más
  allá de hoy.
- **Tres conexiones nuevas que solo aparecen al ver todo el bloque
  junto**:
  1. El ciclo de la "pala" (A6.3, mediano plazo, medible por compresión
     de margen) podría ser señal TEMPRANA de fase Nokia (largo plazo) —
     conecta un mecanismo medible con uno antes solo especulativo.
  2. El pop especulativo de días (cemento post-terremoto) y el ciclo de
     sobreoferta de años (la pala) son el mismo patrón — precio
     adelantándose a la economía real y corrigiendo — repetido en
     escalas de tiempo distintas, no fenómenos separados.
  3. La velocidad de reemplazo de paradigma parece acelerarse (vela→
     incandescente: décadas; touchscreen: ~5 años) — si es cierto, el
     "largo plazo" de hoy se comporta como el "mediano plazo" de hace 50
     años, y el riesgo de survivorship bias del universo estático madura
     más rápido de lo esperable ingenuamente.
- **Límite honesto**: nada de esto es estadísticamente testeable hoy con
  el rigor DSR/PBO del proyecto — son hipótesis de marco conceptual, no
  trials. Lo único accionable y verificado en código: el ejemplo del
  terremoto con nombres reales del universo (CAT/HD/AVGO/QCOM/TXN) y la
  infraestructura de shorting/pairs trade en desarrollo con OpenCode.

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
