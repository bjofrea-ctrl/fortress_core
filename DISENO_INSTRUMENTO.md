# Fortress como instrumento diagnóstico — diseño y plan

> Documento de diseño escrito el 2026-08-14 tras releer completo el documento
> "Quantamental God" (conversación de Boris con Qwen) y contrastarlo contra el estado
> real del repo, verificado en código. Es la capa de **qué construimos y por qué**;
> no reemplaza a `ONBOARDING.md` (reglas) ni a `ROADMAP.md` (pendientes).

---

## 1. Método

Se releyó el documento completo sin saltear secciones y se clasificó **cada** técnica
mencionada en cuatro categorías, contrastando contra el código y los artefactos reales
del repo — no contra el recuerdo de la conversación. Toda afirmación de "ya existe" o
"no existe" de este documento fue verificada con búsqueda en el árbol.

---

## 2. Lo primero: el arco de las preguntas de Boris

Antes de juzgar las respuestas de Qwen, vale leer las preguntas. Tienen una estructura
que no es casual:

| # | Pregunta | Qué busca en realidad |
|---|---|---|
| 1 | Analizá este video de un trader de Goldman | Aprender de la práctica real, no de gurús |
| 2 | Qué indicadores son **académicamente confiables** | Evidencia por encima de popularidad |
| 3 | Qué agregarías para más **sensibilidad y especificidad** | ⬅ **la pregunta clave** |
| 4 | Cómo accedo a eso gratis o barato | Conciencia de restricción de recursos |
| 5 | Árboles y flujos de decisión | Estructura de la decisión, no el indicador |
| 6 | Qué agregarías a nivel dios | Frontera |
| 7 | Cómo distribuyo el trabajo entre 3 LLM | Orquestación sin brechas |
| 8 | Nivel dios con eficiencia de recursos + a cuánto aspirar | Realismo |
| 9 | *"mejor que ganar más es perder mejor"* | ⬅ **conclusión propia, no de Qwen** |

**Lo que revela el arco**: la pregunta 3 usa *sensibilidad* y *especificidad* — el
vocabulario clínico de un radiólogo. No es una metáfora prestada: es cómo Boris piensa
un problema de decisión bajo incertidumbre. Y en la pregunta 9 llega solo a la
conclusión correcta, la que separa al operador profesional del minorista.

**Ese marco es el activo intelectual más valioso de toda la conversación, y es de
Boris, no de Qwen.** El diseño de la sección 5 lo toma como base.

---

## 3. Clasificación completa del documento Qwen

### 3.1 Ya existe en el repo — Qwen no aporta nada nuevo

| Técnica que Qwen propone | Dónde ya vive |
|---|---|
| Deflated Sharpe Ratio | Criterio de corte de todos los trials (DSR ≥ 0.90) |
| Purged CV / PBO / CSCV | `ONBOARDING.md`, metodología base |
| Newey-West | Todos los rank IC intra-día |
| HMM detección de régimen | `app/core/regime_classifier.py` (4 estados semánticos) |
| Stops por ATR | `ControllerAgent.regime_stops` |
| Criterio de Kelly | `KellyPositionSizer` |
| Monte Carlo / VaR | `prob_loss` en Fase 0.6 |
| PCA / RMT | Fase 0.5 |
| EVT / colas | Fase 1, §19 (ξ>0 en 28/50) |
| Multi-agente Toro/Oso/Riesgo | `triad_agents.py` + `advanced_agents.py` |
| Track record por agente | `ProfessorAgent.record_prediction` |
| Cópulas, calibración, Bayes online | `probabilistic_engine.py` |

**Nota importante**: el arnés de validación (capa 5 de Qwen, su "corona") es el **piso**
de este proyecto desde hace semanas. Qwen lo lista como librerías a instalar.

### 3.2 Ya se probó y se refutó — no reconstruir sin evidencia nueva

Momentum/RSI/ADX (5 horizontes, Bonferroni-12, 0/15) · sentimiento AAII (#8, Fase 0.6) ·
fundamentales EDGAR como ranking (#9, Fase 0.6) · pares/cointegración (1225 pares) ·
gap-reversion intradía (§13, bruto ≈0 **antes** de costos) · MA200 fade (§18.1/§18.2) ·
ridge_3f como score (#13).

### 3.3 No aplicable con los recursos reales (hoy)

| Técnica | Por qué |
|---|---|
| Level 3 / order flow / DeepLOB / VPIN / OBI | Requiere datos tick; el cache son barras diarias |
| GEX | Requiere histórico de cadenas de opciones (caro). *Acumulable desde hoy con snapshot diario* |
| DIX / dark pools | Prints no disponibles gratis |
| Alt-data (tarjetas, satélite, aduanas) | Dinero real, infraestructura deprioritizada |
| Mamba / TFT / GNN | 50 símbolos × 7 años es insuficiente; sobreajuste garantizado |
| Almgren-Chriss como ejecutor | Sin broker. **Pero ver 3.4 — sirve como instrumento de medición** |

### 3.4 Aporte real y construible — el resultado de este análisis

Verificado con búsqueda en el árbol: `conformal` = **0 apariciones**,
`triple barrier` = **0**, `abstención/abstain` = **0**. Ninguno existe en el repo.

---

## 4. Los dos hallazgos que valen todo el ejercicio

### 4.1 Predicción Conforme (Conformal Prediction) — lo mejor del documento

Qwen la menciona en un párrafo y sigue de largo. Es, con diferencia, la técnica más
alineada con cómo piensa Boris y con la definición de nivel dios que él mismo aceptó:
*"un sistema que sabe cuándo NO operar"*.

**Qué hace**: envuelve **cualquier** modelo subyacente y devuelve un intervalo de
predicción con garantía estadística de cobertura en muestra finita — sin asumir
distribución. La regla operativa es directa: **si el intervalo es demasiado ancho, el
sistema se abstiene.**

**Por qué es el aporte correcto para este proyecto:**
- No necesita datos nuevos. Funciona sobre lo que ya hay.
- No necesita que exista señal fuerte — de hecho, brilla cuando la señal es débil,
  porque su trabajo es cuantificar *cuánto* no sabés.
- Es la formalización matemática de la especificidad: convierte "no operar" en una
  **salida medida del sistema**, no en la ausencia de una salida.
- Es barata: es una capa de calibración, no un modelo nuevo que entrenar.

### 4.2 El desajuste de etiquetado — encontrado verificando código

Esto no lo dice Qwen. Salió de contrastar su idea de *Triple Barrier* contra el repo.

**La investigación mide una cosa y el motor opera otra.**

- **Investigación**: el target es siempre retorno a horizonte fijo.
  `fwd_return = close.shift(-h)/close - 1` (verificado en `diagnose_ma200_clusters.py`,
  `diagnose_horizon_largo.py`, `diagnose_bull_bear_ic.py`). Se pregunta *"¿cuánto rinde
  en exactamente H días?"*
- **Motor real**: sale por barreras — `PARTIAL_TP` (`backtest_engine.py:311`), stop loss
  y take profit por régimen (`ControllerAgent.regime_stops`, `sl`/`tp` calculados por
  ATR). Nunca mantiene exactamente H días.

Es decir: **todos los veredictos de rank IC midieron el poder predictivo sobre un
objetivo que el motor nunca persigue.** Un factor puede ser inútil para "retorno a 20
días" y útil para "¿toca TP antes que SL?", que son preguntas distintas.

Esto **no invalida** los rechazos anteriores — un factor sin poder en ningún horizonte
de 5 a 125 días es una refutación seria. Pero es una dimensión del espacio de búsqueda
que nunca se exploró, y es gratis explorarla: mismos datos, misma maquinaria, sólo
cambia la definición del target.

**Triple Barrier es exactamente el etiquetado que corresponde a un motor con barreras.**

---

## 5. El proyecto que diseñaría: Fortress como instrumento diagnóstico

### La tesis

Un sistema de trading no debería construirse como un **predictor**. Debería construirse
como un **instrumento diagnóstico calibrado**.

En medicina no se pregunta *"¿este paciente tiene la enfermedad?"*. Se pregunta *"¿qué me
dice este test, con qué confianza, y cuándo no debo actuar sobre él?"*. Todo test clínico
reporta sensibilidad, especificidad, VPP y VPN — y un test bien calibrado **declara
cuándo no es informativo**.

Fortress ya es medio instrumento y nadie lo nombró así: **cada regla de los agentes
carga su IC medido** — RSI del Bull invertido por IC −0.049, trend del Bear invertido por
IC +0.0815, MACD/volumen/CMF con peso 0 por falta de efecto. Eso es un instrumento cuyos
componentes conocen su propia confiabilidad. Es rarísimo y ya existe.

**Lo que falta es la máquina formal para decir "ahora mismo no soy informativo — me
abstengo".**

### Los cuatro principios de diseño

1. **La abstención es una salida de primera clase.** No operar no es la ausencia de
   decisión: es una decisión, se mide, se reporta y se optimiza. Métrica primaria =
   **VPP bajo abstención** (de las operaciones que sí tomó, qué fracción acertó), no
   cobertura.

2. **Todo componente reporta sus características operativas medidas**, nunca afirmadas.
   Sensibilidad, especificidad, VPP, VPN, con su n y su intervalo. Si no está medido, su
   peso es 0 — la convención que el repo ya aplica en `triad_agents.py`.

3. **El objetivo de medición es el que el motor persigue.** Barreras, no horizonte fijo.
   (§4.2)

4. **Perder mejor por encima de ganar más.** Conclusión propia de Boris. Se traduce en:
   optimizar especificidad y control de cola antes que sensibilidad.

### Por qué esta tesis y no la de Qwen

Qwen propone **filtrar mejor** una señal: cuatro capas de filtrado (macro, calidad,
confirmación, ejecución) alrededor de un generador. Pero el proyecto ya demostró que el
generador está vacío para todo lo probado — y filtrar ruido no produce señal.

Un instrumento diagnóstico no necesita que el generador sea fuerte para ser valioso.
Necesita **saber cuándo su lectura es confiable**. Ese es un objetivo alcanzable con lo
que hay, y es el único camino honesto hacia "nivel dios" desde el estado actual.

---

## 6. Arquitectura modular — y la respuesta real sobre tokens

Boris preguntó a Qwen cómo modularizar para ser eficiente con LLM y tokens sin dejar
brechas. Qwen respondió: contratos Pydantic + 3 agentes en paralelo.

**Esa respuesta identifica mal el costo.** El gasto de tokens no viene del paralelismo —
viene de **re-derivar contexto**. Cada sesión, cada agente relee ONBOARDING + ROADMAP +
PLAN_MEJORA para entender dónde está parado. Ese es el costo dominante, y correr tres
agentes en paralelo lo **triplica**.

**La palanca real es la localidad de contexto**: un módulo está bien diseñado si un
agente puede trabajarlo habiendo leído sólo su contrato y sus propios archivos.

Corolario: los módulos se definen por **qué contexto exigen**, no por qué hacen.

### Los seis módulos

| # | Módulo | Contrato de entrada | Contrato de salida | Contexto que exige |
|---|---|---|---|---|
| **M1** | **Etiquetado por barreras** | panel de precios + reglas de salida del motor | columna `label_barrier` (+1 TP / −1 SL / 0 tiempo) | sólo `backtest_engine` (reglas de salida) |
| **M2** | **Instrumento conforme** | scores de cualquier modelo + labels | intervalo + `abstenerse: bool` + cobertura empírica | sólo M1 |
| **M3** | **Compuerta de régimen** | estado HMM + score macro | `operar: bool` por fecha | sólo `regime_classifier` |
| **M4** | **Costos medidos** | órdenes paper vs precio de decisión | constante de costo real, centralizada | ninguno del motor |
| **M5** | **Detector de deriva** | features + resultados en ventana | `deriva: bool` + severidad | sólo M2 |
| **M6** | **Ledger de trials** | artefactos históricos | n_trials por familia, umbral vigente | sólo los `.md` de investigación |

Ninguno exige leer el proyecto entero. Ese es el criterio de diseño, y es lo que evita
tanto el gasto de tokens como las brechas: **si un módulo necesita contexto de otro que
no está en su contrato, el contrato está mal definido** — y eso se detecta antes de
escribir código, no después.

### Reparto entre agentes

Dependencias reales: M1 → M2 → M5. M3, M4 y M6 son independientes de todo.

- **Claude Code**: M1 y M2 (el corazón; requieren juicio sobre metodología)
- **OpenCode**: M5 y M6 (mecánicos, contrato claro, verificables solos)
- **Cline**: M4 (integración externa, terminal, credenciales)
- **M3**: después de M1, porque su veredicto debe medirse con el etiquetado correcto

Un solo escritor por módulo. Nunca dos agentes en el mismo módulo.

---

## 7. Plan de ejecución

### Etapa 1 — El instrumento (M1 + M2)

1. **M1 Etiquetado por barreras**. Replicar las reglas de salida reales del motor
   (`PARTIAL_TP`, stop por régimen, TP por ATR) como función de etiquetado sobre el panel
   histórico. Es infraestructura: se construye sin ceremonia.
   *Verificación*: sobre operaciones históricas conocidas, la etiqueta debe coincidir con
   el resultado real del backtest. Si no coincide, la réplica está mal y se corrige antes
   de seguir.

2. **M2 Instrumento conforme**. Envolver el score existente del motor. Salida: intervalo
   + decisión de abstención + cobertura empírica.
   *Verificación*: la cobertura empírica debe aproximar la nominal (ej. 90% de los reales
   dentro del intervalo del 90%). Un instrumento que no calibra no se usa — se arregla.

3. **Primer veredicto pre-registrado**: ¿el motor operando **sólo** cuando M2 no se
   abstiene mejora el VPP frente a operar siempre? Criterio, umbral y familia escritos
   antes de correr. `n_trials` confirmado contra el ledger o contra el historial de
   artefactos — nunca asumido.

### Etapa 2 — En paralelo, sin dependencias

- **M4 Costos medidos**: Alpaca paper como instrumento, no como ejecutor. Centralizar la
  constante hoy hardcodeada en scripts. Rehacer el neto de §18.2 con el costo medido —
  ese veredicto ("señal real, más chica que sus costos") depende hoy de un número asumido.
- **M6 Ledger**: backfill desde `PLAN_MEJORA_MATEMATICA.md` y `SESSION_LOG.md`. Si el
  conteo no coincide con lo citado, el desacuerdo mismo es un hallazgo.
- **Snapshot diario de cadenas de opciones**: cuesta cero y cada día que no corre es
  historia irrecuperable. No habilita GEX hoy; lo habilita en 6-12 meses.

### Etapa 3 — Con el instrumento calibrado

- **M3 Compuerta de régimen**: la apuesta de mayor valor. El factor más fuerte del
  proyecto (macro, IC +0.13) se cancela entre regímenes (+0.198 GOLDILOCKS / −0.173
  DEFLATION, Fase 2) y **sólo se probó como término ponderado dentro de `ridge_3f`**, que
  se refutó por razones ajenas. Nunca como compuerta. HMM re-estimado walk-forward,
  jamás ajustado sobre la muestra completa y aplicado hacia atrás (sería lookahead del
  mismo tipo que §3.1).
- **M5 Deriva**: KS sobre features + degradación de accuracy. Cierra el bucle de
  auto-conocimiento.

### Lo que este plan deja explícitamente afuera

Meta-labeling, HRP, Almgren-Chriss como ejecutor, GEX/DIX, Mamba/GNN, datos alternativos,
y el plan de 12 semanas con tres agentes en paralelo. No por malos — por **prematuros**:
todos presuponen una señal primaria que hoy no existe. Se retoman cuando el instrumento
diga que hay algo que vale la pena filtrar.

---

## 8. Métrica de éxito — cómo sabemos que funcionó

No es Sharpe. En esta etapa la métrica es diagnóstica:

| Métrica | Qué mide | Meta de la etapa 1 |
|---|---|---|
| **Cobertura empírica de M2** | ¿el instrumento está calibrado? | dentro de ±3 pts de la nominal |
| **VPP bajo abstención** | de lo que opera, ¿cuánto acierta? | > VPP operando siempre |
| **Tasa de abstención** | ¿cuánto reconoce no saber? | se **reporta**, no se optimiza |
| **Fidelidad de M1** | ¿el etiquetado replica el motor real? | coincidencia exacta o se corrige |

Un resultado donde el sistema se abstiene el 80% del tiempo y acierta en el 20% restante
**es un éxito**, no un fracaso. Es exactamente lo que Boris formuló: *mejor que ganar
más es perder mejor*.
