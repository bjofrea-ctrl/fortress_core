# TradingAgents (TauricResearch) vs fortress_core — auditoría de código y comparación

> Escrito el 2026-09-25. Extiende `RESEARCH_EXTERNA_CRITICA.md` §1 (2026-08-12), que había
> evaluado **TradingAgents a nivel paper**. Esto es la **auditoría a nivel código** de la
> versión vigente, hecha clonando el repo y leyéndolo, no leyendo su README.

## 0. Correcciones fácticas antes de empezar

| Dato | Lo que se creía | Lo verificado |
|---|---|---|
| Licencia | "MIT" | **Apache-2.0** (`LICENSE`, línea 1: "Apache License Version 2.0"). Permisiva y compatible con reuso — pero exige **atribución + aviso de cambios** si se copia código |
| Origen | "MIT" (instituto) | **TauricResearch** (org). Los autores del paper son Xiao, Sun, Luo, Wang (arXiv:2412.20138), adscritos a UCLA/MIT; el repo es de una org de investigación, no del MIT |
| Versión | — | **v0.5.1**, commit `35543d0248bf89fcb92b17a15858ad0c0e940687`, 2026-09-24 (393 commits, 108.6k estrellas, 20.8k forks) |

**Artefacto de verificación**: `git clone --depth 1` en `/tmp/TradingAgents` (temporal, no
va al repo). Todo número de este documento sale de ahí: `find`, `wc -l`, `grep`, `cat`
sobre el árbol clonado.

---

## 1. Qué es TradingAgents, medido

| Métrica | TradingAgents | fortress_core |
|---|---|---|
| Archivos `.py` | 166 | 278 (sin `.venv`) |
| Líneas Python | 22.901 | ~17.900 solo en `backend/app/core` (+114 scripts) |
| Archivos de test | 75 (`test_*.py`; 77 entradas con `conftest.py`+`__init__.py`) | 82 (`test_*.py`; 83 con `conftest.py`) |
| Funciones de test | no contadas (archivos livianos, ~130 líneas de promedio) | **1.017** (`grep -c 'def test_'`) |
| Stack | LangGraph + LangChain + pydantic + typer/rich | FastAPI + pandas/numpy/scipy + React |
| Superficie de producto | CLI (2 comandos) | API 16 routers + dashboard React + jobs launchd versionados (`scripts/*.plist`) |
| Datos | 5 vendors online (yfinance, SEC EDGAR, FRED, Polymarket, Alpha Vantage) + Reddit/StockTwits | Parquet propio (universo 50 + intradía) + EDGAR + FinBERT local |
| Persistencia | markdown append-only (`trading_memory.md`) | SQLite (`fortress.db`) + JSON + parquet |

### 1.1 Arquitectura real (verificada en `tradingagents/graph/`)

Grafo LangGraph (`setup.py`) con este flujo — **todos los nodos son LLM**:

```
START → [Market | Sentiment | News | Fundamentals]   cada analista con su tool-loop
      → Bull Researcher ⇄ Bear Researcher            debate por conteo de turnos
      → Research Manager (modelo deep)               → plan de inversión
      → Trader (modelo quick)                        → Buy / Hold / Sell + niveles
      → Aggressive ⇄ Conservative ⇄ Neutral          debate de riesgo
      → Portfolio Manager (modelo deep)              → rating 5 niveles + sizing
      → END
```

- `conditional_logic.py`: el corte del debate es por **conteo de turnos**
  (`2*max_debate_rounds`, `3*max_risk_discuss_rounds`), no por convergencia ni por criterio
  de calidad del argumento.
- `checkpointer.py`: checkpoint SQLite por nodo → un run caído reanuda. Verificado, y es
  una pieza genuinamente buena.
- `structured.py` + `agents/schemas.py`: los 3 agentes que deciden (Research Manager,
  Trader, Portfolio Manager) devuelven **pydantic** usando el modo nativo de cada proveedor
  (`json_schema` OpenAI/xAI, `response_schema` Gemini, tool-use Anthropic). Incluye
  reparación de campos: placeholders ("N/A", "None") → `None`, `"$1,234.50"` → número, y
  `"15%"` → **descartado a propósito** (un porcentaje leído como nivel pondría un stop en
  $15 sobre una acción de $600).
- `reflection.py` + `decision_log.py` + `settlement.py`: loop de aprendizaje. Cada decisión
  se guarda pendiente y en corridas posteriores **del mismo ticker** se liquida contra el
  retorno realizado **y el alpha contra el benchmark regional**, con ventana de tenencia
  (default 5 días). La reflexión se inyecta como lección en el prompt siguiente
  **filtrando por `as_of`** — solo lecciones cuyo resultado ya era conocido en la fecha de
  análisis (su issue #1251).

### 1.2 Capa de datos: lo mejor del repo

`dataflows/router.py`: registro declarativo de vendors por categoría (precios, indicadores,
fundamentales, news, macro, prediction markets). Dos decisiones de diseño que valen:

1. **Degradación por categoría.** Las categorías opcionales (`macro_data`,
   `prediction_markets`) degradan a un sentinel si el vendor falla; las core (precios,
   fundamentales, news) **levantan excepción** — un primary roto es ruidoso a propósito.
2. **Guardas point-in-time centralizadas** (`dataflows/date_window.py`, 124 líneas):
   - `as_of(requested, trade_date)`: el modelo **no puede** pedir una fecha posterior a la
     del run — si pasa hoy en vez de la fecha histórica, se clampea.
   - `in_window()`: ventana semiabierta, timestamps normalizados a UTC, item sin fecha
     **descartado** en backtest (no se puede probar que no es futuro).
   - `coverage_gap()`: cuando un feed solo devuelve lo más reciente, devuelve el texto
     explícito *"no es una ausencia de X: la fuente no cubre esa ventana"*. Distingue
     **"no hay dato"** de **"no lo observamos"** — honestidad metodológica real.
   - `withhold_live_profile()`: los perfiles de compañía (`Ticker.info`) no tienen vintage
     histórico → se retienen explícitamente en un run histórico en vez de servir datos de hoy.

### 1.3 Capa LLM

`llm_clients/`: 16 proveedores (OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen global/CN,
GLM global/CN, MiniMax global/CN, OpenRouter, Mistral, Moonshot, Groq, NVIDIA NIM, Bedrock,
Ollama, cualquier endpoint OpenAI-compatible). Piezas concretas:

- `capabilities.py`: tabla declarativa **por modelo** (¿acepta `tool_choice`? ¿`json_mode`?
  ¿necesita `reasoning_split`? ¿requiere devolver `reasoning_content` en el turno
  siguiente?). El cliente consulta la tabla en vez de tener escaleras de `if` por nombre de
  modelo, y documenta el *por qué* de cada excepción (el 400 de DeepSeek thinking con
  `tool_choice`, el enum restringido de MiniMax M2.x).
- `factory.py`: reintentos con presupuesto configurable (`llm_max_retries`, backoff,
  respeta `Retry-After`), y coerción estricta de `max_tokens`/`temperature` que **falla
  fuerte** ante configuración inválida en vez de degradar en silencio.
- `model_catalog.py`: catálogo por proveedor; decisión explícita de exponer solo IDs
  versionados y dejar los aliases auto-actualizables detrás de "Custom model ID" (un alias
  cambia de comportamiento cuando el proveedor rota el modelo detrás).

### 1.4 Su "backtest" — qué es y qué no es

`tradingagents/backtest.py` (208 líneas) corre el **grafo completo** sobre una grilla
(ticker × fecha, `--every N` días) y agrega: hit-rate y alpha medio **por rating**. El
propio docstring dice, textual:

> *"Scope: this evaluates decision quality. It is not a portfolio simulator, and must not
> grow one. Turning a rating into a filled order needs a quantity, a fill price and a cash
> ledger, none of which the system has; inventing them here would put an execution model
> behind an evaluation tool. Cells are therefore independent."*

Y el README agrega: *"Backtest results are not guaranteed to match any published figure...
Treat the framework as a research scaffold for studying multi-agent analysis, not as a
strategy with a fixed, replicable return."*

**Traducción operativa**: su backtest mide *"¿el rating que dio el LLM tenía razón?"*, no
*"¿el sistema gana plata?"*. No hay precio de fill, no hay tamaño, no hay caja. Es una
métrica de acierto direccional, con celdas independientes (sin cartera que arrastre
posiciones).

### 1.5 Lo que NO existe en el repo (verificado por grep, no por omisión de lectura)

`grep -rniE 'deflated|sharpe|purged|cross-validation|walk-forward|bonferroni|newey|
pbo|transaction cost|slippage|commission' --include='*.py' --include='*.md' .` →
**0 coincidencias en todo el repo** (no sólo en el código: tampoco en tests, README ni
CHANGELOG). Ni una.

| Ausente | Qué implica |
|---|---|
| Sharpe, DSR, PBO/CSCV, purged CV, walk-forward, Bonferroni, Newey-West | Su hit-rate por rating es **descriptivo, no inferencial**: no hay forma de saber si un 60% de aciertos con n=30 es habilidad o azar. Reportan el número crudo |
| Costos: comisión, slippage, spread | El alpha que reportan es **bruto**; ni siquiera hay un campo donde ponerlo |
| Pre-registro / ledger de trials | No hay registro de cuántas cosas se probaron → no hay deflación por comparaciones múltiples. Justamente lo que `trial_registry.py` hace acá |
| Sizing/riesgo numérico | Buscan "stop-loss" y "position sizing" solo en **prompts** (el LLM los propone como texto). No hay ATR-based sizing, ni Kelly, ni vol targeting, ni VaR en código. `portfolio.py` (64 líneas) solo formatea el libro del usuario para el prompt |
| Reproducibilidad | Reconocida como no resuelta: sampling del modelo + *"Live data moves. News, StockTwits and Reddit return different content as time passes, so a run today sees different inputs than a run last week even for the same historical trade date"* |

Esa última fila importa más de lo que parece: sus guardas `as_of`/`in_window` filtran **por
timestamp lo que el feed devuelve**, pero si el feed **no tiene** el pasado, el run
histórico queda con noticias/social de hoy. Ellos lo manejan marcando `coverage_gap()` y
**descartando items sin fecha** — mitigación honesta, pero no resuelve la ausencia de datos
históricos. Es exactamente el problema que acá se resuelve con parquet propio congelado.

### 1.6 Costo de una corrida

Cada celda del backtest es un grafo completo: 4 analistas con tool-loops (varias llamadas
cada uno) + 2 turnos de debate alcista/bajista + manager + trader + 3 turnos de debate de
riesgo + portfolio manager ≈ **15-25 llamadas LLM por ticker-fecha**, con modelos
"reasoning-first" por default (GPT-6 Sol/Luna en v0.5.1). Con 10 tickers × 10 fechas son
cientos de llamadas por barrido, y el resultado **no es reproducible** entre corridas.
Comparado con el motor de fortress: determinista, local, cero costo marginal, reproducible
bit a bit.

---

## 2. Comparación por dimensión

### 2.1 Donde TradingAgents es superior (sin discusión)

| # | Dimensión | Su artefacto | Nuestro estado |
|---|---|---|---|
| 1 | **Orquestación multi-agente** | Grafo declarativo LangGraph con estado tipado, ramas condicionales, checkpointer por nodo y resume de run caído | `advanced_agents.py` encadena pasos con `if/else` y llamadas HTTP secuenciales de 30s; sin grafo, sin resume |
| 2 | **Salida estructurada de agentes** | pydantic + modo nativo por proveedor + reparación de campos con criterio documentado | `generate_json()` hace `find("{")`/`rfind("}")` + `json.loads`; un JSON malformado → `None` → todo el veredicto se pierde |
| 3 | **Robustez de proveedores** | 16 proveedores, tabla de capacidades por modelo, reintentos con backoff/`Retry-After`, coerción estricta de config | 2 caminos (NIM / OpenRouter por prefijo de string), slugs hardcodeados con nota *"a validar en primera llamada viva"*, y ante 429 solo loguea warning y devuelve `None` |
| 4 | **Guardas point-in-time como capa** | Módulo central que **toda** herramienta respeta, con clamp `as_of` que impide al modelo salirse de la fecha | Protección equivalente pero a nivel motor (cache integrity, `execution_lag_days=1`, PAUSE flags) — no hay guarda por-tool porque no exponemos tools a LLMs |
| 5 | **Licencia y distribución** | Apache-2.0, `pyproject`, entry point `tradingagents`, Docker, CI, i18n multi-idioma, cobertura global (crypto, HK, .SA/Bovespa) | Repo propio sin packaging; alcance deliberadamente acotado a 50 símbolos US |
| 6 | **Documentación de decisiones** | `CHANGELOG.md` con número de issue por cambio, y comentarios que explican el *por qué* del workaround | Buena, pero en docs paralelos; el código tiene menos "por qué" inline |
| 7 | **UX de investigación** | TUI `rich` con progreso por nodo, selección de analistas/rounds, `--portfolio`, `--run-id` para reanudar un barrido | Dashboard web (mejor para mirar), pero sin flujo interactivo de "corré esto y explorá" |

### 2.2 Donde empatamos

| Dimensión | Ambos tenemos |
|---|---|
| Patrón bull/bear | Triada BULL/BEAR/CONTRARIAN (`triad_agents.py`) vs Bull/Bear Researcher + risk debate. Mismo patrón de "firma simulada" |
| Fundamentales SEC EDGAR | `edgar_fundamentals.py` (472 líneas) vs `dataflows/vendors/sec_edgar.py` (243) |
| Macro / FRED | Macro compuesto propio con IC medido (negativo, invertido) vs vendor FRED + Polymarket |
| Sentimiento | FinBERT local + AAII vs LLM + StockTwits/Reddit + screening Jev |
| Contenedores/CI | `docker-compose.yml`, `.github/workflows/ci.yml`, ruff | ídem |
| Log de decisiones | `signal_ledger.py` + `decision_history` (SQLite) vs `decision_log.py` (markdown) |

### 2.3 Donde los superamos (y por qué importa)

| # | Dimensión | Nuestro artefacto verificado | Por qué es superior |
|---|---|---|---|
| 1 | **Aparato estadístico** | DSR, PBO/CSCV, purged CV, rank IC intra-día con Newey-West, Bonferroni, MDE/potencia, RMT 8 factores, EVT, HMM de régimen, cópulas, conformal split (α=0.10, abstención) | **Ellos tienen cero**. Grep = 0 hits. Su salida es descriptiva; la nuestra es inferencial con corrección por comparaciones múltiples |
| 2 | **Ledger de trials pre-registrado** | `trial_registry.py` (984 líneas) + `audit_trial_budget.py`; criterio escrito ANTES de correr, reversión automática si no cumple | No existe allá. Sin ledger, "probamos varias cosas" no se puede deflactar |
| 3 | **Realismo de ejecución** | `execution_lag_days=1` (fix T0.2 de look-ahead real), `execution_costs.py` con **costos medidos contra Alpaca paper**, `barrier_labeling.py` que replica las salidas reales del motor, `execution_telemetry.py` | Su backtest es explícitamente *"not a portfolio simulator"*: sin fill, sin tamaño, sin costos |
| 4 | **Integridad de datos** | `cache_integrity.py` (883 líneas), `clean_days.py` + contador de 60 días, reconciler diario, `PAUSE_YAHOO_MASS_DOWNLOAD`, calendario NYSE con feriados reales | Para el *backtest* ellos admiten que la data histórica de news/social no existe. Nosotros corremos sobre parquet congelado y verificable |
| 5 | **Loop de ejecución** | `paper_trading.py` con contabilidad corregida, pipeline 3×/día por launchd, `reconcile_open_positions`, `kill_switch`, `drift_detector.py`, `monthly_report.py` | Ellos deciden y escriben markdown; no hay contabilidad, ni posiciones, ni PnL operativo |
| 6 | **Producto** | 16 routers API (`backend/app/api/routes/`) + dashboard React + jobs launchd + `notifier.py` | Su superficie es una CLI. Nada que mirar, nada que monitorear |
| 7 | **Disciplina de honestidad** | Regla "nada de señal en vivo sin gate", `RESUMEN_VALIDACION_VARIABLES.md` con lo refutado, hallazgos D1-D12 de la auditoría Simons | Ellos son honestos en el README (declaran no reproducibilidad) pero **no tienen el aparato** para saber si su rating funciona |
| 8 | **Densidad de test** | 82 archivos / **1.017 funciones de test** (`backend/tests`) | 75 archivos, muchos de prompt/integración; sin métrica equivalente, pero el orden es claro |
| 9 | **Costo marginal por corrida** | 0 (determinista, local) | 15-25 llamadas LLM por celda, no reproducibles |

---

## 3. Veredicto: ¿se puede usar? ¿se puede integrar?

**Respuesta corta: no como motor, no como capa de decisión, no como backtest. Sí como fuente
de 3 patrones concretos, y la licencia (Apache-2.0) permite copiar con atribución.**

El desacuerdo no es de calidad de código — su código es bueno, está mejor probado que la
media y mejor documentado que el nuestro en varios puntos. El desacuerdo es de **qué es cada
cosa**:

| | TradingAgents | fortress_core |
|---|---|---|
| Naturaleza | **Instrumento cualitativo**: produce análisis razonado en lenguaje natural | **Instrumento de validación**: produce un veredicto falsable con umbral |
| Pregunta que responde | "¿qué opina una firma simulada sobre este papel hoy?" | "¿esto predice, con corrección por comparaciones múltiples?" |
| Salida | texto + rating de 5 niveles | p-value, DSR, cobertura conformal, abstención |
| Falla si | se le pide reproducibilidad y PnL | se le pide conversación y matiz narrativo |

Meter TradingAgents en el loop de decisión de fortress sería **exactamente** lo que
`RESEARCH_EXTERNA_CRITICA.md` §1 y `AUDITORIA_INTEGRAL_SISTEMA_20260903.md` D1 ya adjudicaron
en contra: la capa multi-agente LLM no decide dinero acá, y TradeTrap (2025) documenta por
qué no debería. Esta auditoría no cambia ese veredicto — lo refuerza con una razón nueva y
concreta: **el repo no tiene el aparato para saber si su propia salida funciona**, así que no
puede aportar veredicto, solo narrativa.

**Lo que sí aporta: ingeniería.** De la auditoría salen tres cosas que ellos resolvieron bien
y nosotros tenemos resueltas peor — todas en la capa LLM/gobernanza, que hoy está **apagada
por decisión** (`GOVERNANCE_LLM_ENABLED=false`, A9) y por lo tanto **no toca el motor
validado ni el gate de 60 días**.

---

## 4. Qué adoptar, concretamente

### 4.1 Adoptable ahora (capa muerta, cero riesgo para el gate)

**C1 — Reintentos con presupuesto y backoff en `NvidiaNIMClient.generate()`**
- *Estado actual verificado* (`advanced_agents.py:268-314`, 429 en la línea 300): ante 429 solo
  `logger.warning("nim_rate_limited", ...)` y `return None`; el caller cae a determinista sin
  distinguir "se agotó la cuota" de "el modelo devolvió algo raro". Con OpenRouter free esto
  pasa seguido.
- *Qué copiar*: el patrón de `llm_clients/factory.py` — `llm_max_retries` configurable,
  backoff exponencial con jitter, respeto del header `Retry-After`.
- *Costo*: ~30 líneas en `advanced_agents.py`, 0 dependencias nuevas, testeable con
  monkeypatch de `requests.post` (patrón que ya usa `test_nim_client.py`).
- *Criterio de éxito verificable*: test nuevo que simula 429→429→200 y exige 3 intentos y
  éxito; con `max_retries=0` el comportamiento actual se reproduce exacto.

**C2 — Tabla declarativa de proveedores reemplazando los slugs hardcodeados**
- *Estado actual verificado*: `TRIAD_LLM_MODELS` / `GOVERNANCE_LLM_MODELS` con slugs como
  `"moonshotai/kimi-k3"` y `"openrouter/minimax/minimax-m3:free"`, con el comentario
  *"Slugs a validar en primera llamada viva"*, y routing por prefijo de string
  (`_resolve_provider`).
- *Qué copiar*: un `PROVIDER_REGISTRY` (nombre → `base_url`, settings-key, ¿soporta
  structured output?, cómo se llama el ID en el wire) en vez de parsear prefijos. No hay que
  copiar sus 16 proveedores ni su catálogo: la idea, no el archivo.
- *Por qué importa*: hoy un slug inválido se descubre en producción como
  `nim_bad_response` a las 2 AM; con tabla + validación al arranque, se descubre al importar.
- *Criterio de éxito*: test equivalente a su `test_provider_registry` que falle si un slug no
  está registrado o si dos agentes usan un proveedor sin key configurada.

**C3 — Cerrar el look-ahead latente en `RAGMemorySystem`** *(hallazgo nuevo de esta
auditoría, no un copy-paste)*
- *Estado actual verificado* (`knowledge_repo.py:383-417`): `record_lesson()` guarda
  `timestamp = ahora` y `retrieve_agent_memory()` recupera por similitud Jaccard **sin ningún
  filtro temporal**. Si la gobernanza se re-enciende y se corre sobre una ventana histórica,
  las lecciones **del futuro** entran al prompt de un análisis del pasado.
- *Qué copiar*: el patrón `as_of` de `decision_log.py` (su issue #1251) — cada lección guarda
  la fecha en que su resultado **se conoció** (`resolution_date`), y la recuperación filtra
  `resolution_date <= fecha_de_análisis`.
- *Riesgo actual*: **latente, no activo** — capa apagada (A9) y D1 documenta que ni se importa
  en el pipeline diario. Se arregla antes de re-encenderla, no después.
- *Criterio de éxito*: test que registra una lección fechada 2030 y verifica que no aparece en
  un contexto `as_of=2026-01-01`.

### 4.2 Adoptable cuando la gobernanza se re-encienda (diseño, no urgencia)

**C4 — Salida estructurada real en los agentes de gobernanza.** Hoy `generate_json()` tolera
un JSON malformado devolviendo `None` (se pierde el veredicto completo) y `PROFESSOR_PROMPT`
tiene que gritar *"El campo decision es OBLIGATORIO y debe ser exactamente la palabra en
inglés APPROVE o REJECT"*. Eso es un problema de validación resuelto con mayúsculas en un
prompt. `pydantic` ya es dependencia del proyecto (viene con FastAPI): un `GovernanceVerdict`
con `Literal["APPROVE","REJECT"]` elimina esa clase entera de fallo, y el patrón de reparación
de campos de `schemas.py` ("N/A" → `None`, `"$1,234.50"` → número, rango/hedge → descartar el
campo y no el veredicto) es directamente trasladable.
- *Criterio de éxito*: mismo prompt + salida estructurada → 0 respuestas descartadas por
  parseo en una corrida de N llamadas (medir antes/después con el mismo input).

**C5 — Resume por paso en corridas largas.** `analyze()` hace hasta 3 llamadas HTTP síncronas
de 30s por símbolo; una corrida del universo son ~306 llamadas
(`PLAN_IMPLEMENTACION_REMEDIO_20260903.md`). El checkpointer por nodo de LangGraph ataca
exactamente "se cayó a mitad y no sé dónde quedó". **Sin adoptar LangGraph**: un checkpoint
JSON por símbolo/paso con el mismo contrato (`thread_id`, `checkpoint_step`,
`clear_on_success`) alcanza.

### 4.3 Lo que NO hay que hacer (y por qué)

| Tentación | Por qué no |
|---|---|
| Portar el grafo a LangGraph y reemplazar el pipeline | Cambia el motor por 5 dependencias pesadas (langchain-core/anthropic/openai/google-genai + langgraph) para ganar orquestación que ya tenemos |
| Usar su `backtest.py` como validación | No mide PnL, no tiene costos, no es reproducible, y sus propias celdas lo declaran fuera de alcance. Usarlo como "validación" violaría la regla 1 de `ONBOARDING.md` |
| Adoptar sus vendors en vivo (StockTwits/Reddit/Polymarket/Alpha Vantage) | Rompe la disciplina de datos propios (parquet congelado, cache integrity, PAUSE flags) y reintroduce el problema que ellos admiten: en backtest no hay historia de social/news |
| Correr la tríada con GPT-6 Sol/Luna por default | Cientos de llamadas por barrido con modelos reasoning-first, no reproducibles. Nuestra capa LLM usa cuota gratis a propósito (NIM/OpenRouter free) |
| Re-encender la gobernanza LLM "porque TradingAgents muestra que sirve" | Muestra que **existe**, no que **funcione**: venden el scaffold, no un resultado. `validate_triad_llm.py` acá nunca produjo justificación (`PLAN_IMPLEMENTACION_REMEDIO_20260903.md` §A9 lo dice explícito) y el gate de 60/90 días sigue mandando |

---

## 5. Síntesis en una tabla

| Pregunta | Respuesta verificada |
|---|---|
| ¿TradingAgents es superior en algo? | Sí, en **ingeniería de orquestación LLM**: grafo declarativo con resume, salida estructurada con reparación, robustez de 16 proveedores con reintentos, guardas point-in-time centralizadas, y disciplina de escritura (CHANGELOG por issue, tests aislados de red/tz) |
| ¿En qué empatamos? | Patrón bull/bear, EDGAR, macro, sentimiento, contenedores/CI, log de decisiones |
| ¿En qué los superamos? | En **todo lo que convierte una opinión en un veredicto**: aparato estadístico (DSR/PBO/CV/Newey-West/Bonferroni/MDE), ledger de trials pre-registrado, realismo de ejecución (lag=1, costos medidos, barrier labeling), integridad de datos, loop de ejecución con contabilidad, producto (API+dashboard+automatización) y densidad de test (1.017 funciones) |
| ¿Se puede usar el repo tal cual? | Como **herramienta de investigación cualitativa suelta**, sí — es un scaffold honesto y bien hecho, y su README no promete más de lo que da. Para decidir o validar algo acá, no |
| ¿Se pueden agregar componentes? | Sí: Apache-2.0 lo permite con atribución. Son 5 patrones (C1-C5), ninguno toca el motor validado, y 3 son aplicables ya sin riesgo para el gate |
| ¿Cambia el rumbo del proyecto? | No. Refuerza el veredicto existente (`RESEARCH_EXTERNA_CRITICA.md` §1, auditoría Simons D1) con evidencia de código: **la fortaleza de este proyecto no es la capa LLM, es el aparato de validación** — que es justo lo que el repo de 108k estrellas no tiene |

**Fuentes y artefactos**: repo `github.com/TauricResearch/TradingAgents` @
`35543d0248bf89fcb92b17a15858ad0c0e940687` (v0.5.1, 2026-09-24; clonado y auditado el
2026-09-25) · `LICENSE` (Apache-2.0) · `tradingagents/backtest.py` · `graph/{setup,
conditional_logic,checkpointer,reflection}.py` · `dataflows/{router,date_window}.py` ·
`llm_clients/{factory,capabilities,model_catalog}.py` · `agents/{schemas,post_screen,
rating}.py` · `decision_log.py` + `portfolio.py` · README §Reproducibility · arXiv:2412.20138.
Del lado nuestro: `RESEARCH_EXTERNA_CRITICA.md` · `AUDITORIA_INTEGRAL_SISTEMA_20260903.md` (D1)
· `backend/app/core/{advanced_agents,knowledge_repo,triad_agents}.py` · `ROADMAP.md`
(contador del gate) · `PLAN_IMPLEMENTACION_REMEDIO_20260903.md` §A9.
