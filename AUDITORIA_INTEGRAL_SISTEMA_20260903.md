# AUDITORÍA INTEGRAL DEL SISTEMA — fortress_core (óptica Simons)

**Fecha**: 2026-09-03 · **Autor**: Kilo Code (worktree `test-kilo-orca`), 3 exploraciones paralelas (capa agentes/LLM, matemáticas vs código, loops/memoria) + verificación directa de cada hallazgo crítico contra el artefacto. Complementa —no repite— `AUDITORIA_NIVEL_DIOS_20260902.md` (cuya Fase 0 ya se ejecutó: seed `45ddc3f`, etiquetado honesto `ad5d40c`, pnl_r real `1466dcc`).

**Pregunta que responde**: si Jim Simons tuviera que construir un sistema de trading automatizado desde cero para máxima rentabilidad sobre esta base, ¿qué encontraría, qué respetaría y qué rehacería?

---

## 1. Veredicto ejecutivo

El proyecto tiene **el aparato de falsificación de un shop cuantitativo serio montado sobre el aparato de ejecución de un proyecto universitario**. Un sistema de trading rentable necesita cinco capas: datos → señal → validación → ejecución → feedback. Las capas 1-3 (con la brecha muestral conocida de B2) están en percentil alto institucional. **Las capas 4-5 no existen como sistema**:

- El pipeline diario que decide el dinero corre `SignalEngine` solo — **la capa multi-agente (Bull/Bear/Professor/Judge) NO se importa en ninguna ruta de decisión real** (`pipeline_daily_signal.py:42-59` importa solo indicators+signal_engine+costs). Es una fachada de dashboard.
- El sistema **no aprende de sus operaciones**: `record_prediction` solo tiene caller manual (`governance.py:161`), el historial queda vacío, el "Resumen de Enseñanza" es ficción estadística (accuracy=0.5, n=0).
- **`reconcile_open_positions` no tiene NINGÚN caller en producción** (solo `test_paper_trading.py`) → la condición (c) del gate "sin órdenes huérfanas" es **inejecutable hoy**: el contador de días limpios mide una definición que nadie verifica.
- **No existe kill-switch**: un paper trading que diverja no detiene nada; `monthly_report.py` etiqueta EMPEORA pero nadie lo lee automáticamente.
- **Opciones: presencia CERO** (sin Black-Scholes, IV, griegas, cadenas — verificado). Para un objetivo declarado de "máxima rentabilidad posible", la familia de estrategias con mejor Sharpe histórico por unidad de capital en el mundo real (variance risk premium, gamma hedging flows, PEAD en opciones) **no tiene ni el primitivo**.

Simons construiría desde el loop, no desde la señal: un sistema que no mide su propia ejecución no puede aprender, y aprender es lo único que produce rentabilidad sostenida.

---

## 2. Lo que está a nivel institucional (verificado, no romper)

1. **Aparato estadístico**: DSR Bailey-LdP completo con Lo/Mertens y skew/kurtosis reales (`backtest_engine.py:629-640`), PBO/CSCV con C(16,8) combinatorial y Sharpe OOS en O(1) (`pbo_cscv_mom_rsi.py:285-355`), Newey-West Bartlett en todos los trials IC, purga+embargo en walk-forward (`probabilistic_engine.py:641-713`), Bonferroni con ledger anti-evasión y reconciliación git (`trial_registry.py:40-54`), bootstrap de bloques circulares seeded, Platt/PAV isotonic, cópulas con estimador cerrado por Kendall τ.
2. **Anti-lookahead real**: `execution_lag_days=1` en todas las rutas del motor (entrada open t+1, stops detectados en cierre t ejecutados open t+1, dataset de calibración con el mismo lag, HMM causal con refit walk-forward). El fix VIX del HMM (ordenar estados por vol media ascendente, `93b5718`) verificó 4 refits empíricos.
3. **Honestidad de etiquetas**: el motor heurístico se auto-declara `motor="heuristico_no_validado"`, 51 trials en ledger con solo 2 CUMPLE y cero falsas promociones.
4. **Operación**: launchd 12/12 jobs versionados y cargados (auditoría de hoy a la mañana), backups sin --delete, idempotencia del pipeline con `client_order_id` determinista y 3 capas anti-duplicado.
5. **Conformal conectado a producción** (no es código muerto): la abstención fuerza NO_INVERTIR (`decision.py:71`, calibración n≥30 en `:94`).

---

## 3. Debilidades verificadas hoy (nuevas, no en NIVEL_DIOS)

| # | Severidad | Hallazgo | Evidencia |
|---|---|---|---|
| D1 | **CRÍTICA** | Capa multi-agente LLM desconectada del dinero: el pipeline diario no la importa. El dashboard muestra gobernanza que no decide nada. | `pipeline_daily_signal.py:42-59` vs `triad_agents.py`/`advanced_agents.py` sin callers en pipeline |
| D2 | **CRÍTICA** | Condición (c) del gate inejecutable: `reconcile_open_positions` sin caller productivo → "día limpio" no se verifica, contador de racha contaminado de origen | `paper_trading.py:169` definido; solo `test_paper_trading.py` consume; ROADMAP:43-45 exige reconcile |
| D3 | **CRÍTICA** | Sin kill-switch ni alertas: divergencia PnL paper vs esperado no detiene nada; `daily_notify` descargado, `monthly_report` es runner manual sin launchd | grep kill/halt en `app/core` → 0 hits |
| D4 | **CRÍTICA** | Loop de aprendizaje vacío: `record_prediction` sin caller automático, historial n=0, "Resumen de Enseñanza" ficción; `pipeline_signal_log.jsonl` con 4 líneas de checkpoints | `governance.py:161-164`; `pipeline_daily_signal.py:57` declara "paso 4c futuro" |
| D5 | ALTA | DSR del motor sub-deflaciona: `DEFAULT_N_TRIALS=5` (`backtest_engine.py:651`) vs 51 trials reales en ledger; los scripts de validación deflacionan bien — el motor no | `backtest_engine.py:651` vs `trial_registry` |
| D6 | ALTA | PBO §39 (0.2358, el vigente) entra al cierre del mes de decisión (close[m-1]→close[m], lag 0) — inconsistente con el estándar T0.2 propio; §40 y validación OOS sí usan open→close | `pbo_cscv_mom_rsi.py:141-143` vs `validacion_oos_fresca_mom_rsi.py:296` |
| D7 | ALTA | Prompts LLM contradicen la semántica de los scores (reglas con IC invertido, prompt no lo explica; umbral de corrección ±0.5 es mitad del rango); Professor decide sin ver un solo precio (ni fecha de dato — datos stale invisibles) | `triad_agents.py:183-187, 469-488, 509`; `advanced_agents.py:623-632` |
| D8 | MEDIA | Memory engineering decorativa: `knowledge_repo` = 17 entradas hardcodeadas con Jaccard keyword-matching (campo embeddings nunca poblado), `rag_memory.json` 6 entradas triviales duplicadas; signal_engine/pipeline jamás lo consultan | `knowledge_repo.py:213-327` |
| D9 | MEDIA | Duplicación: definición congelada de señal en 3+ lugares sin contrato compartido; 97 scripts con utilidades copiadas (DSR/bootstrap/load_symbol) | B6 NIVEL_DIOS, sigue abierto |
| D10 | MEDIA | Sizing por-activo sin estructura de cartera: las cópulas miden dependencia de colas pero no ajustan exposición; los 8 factores RMT residuales existen y nadie los usa | `adaptive_risk.py` solo Kelly ¼ por trade; `rmt_factor_scores_8factors.csv` huérfano |
| D11 | BAJA | Ineficiencia LLM: GovernanceSystem se re-instancia por request (6 clientes LLM cada vez); /predict sobre universo puede disparar ~306 llamadas HTTP | `governance.py:51-53, 124` |
| D12 | BAJA | Costos default obsoletos en `run()` (0.001 vs 0.0005 vigente §33) — los callers serios lo pasan explícito, pero un script nuevo que no lo haga hereda 2× el costo | `backtest_engine.py:267` |

**Decorativo confirmado**: `drift_detector.py` (KS+Bonferroni bien hecho, cero consumidores), FatTailMonteCarlo con dof=5 fijo no fiteado (GARCH citado, jamás implementado), `REGIME_ALLOCATION` HMM sin consumidor, `detect_hallucination`/`validate_confidence_consistency` de hardiness solo en tests, prompts CONTROLLER/JUDGE sin caller LLM.

---

## 4. Oportunidades — dónde está la rentabilidad en la mesa (ordenada por Sharpe esperado por esfuerzo)

1. **Cerrar el loop de ejecución (pre-gate, urgente)**: reconciler en pipeline + kill-switch por divergencia + telemetría decision_price vs fill_price por orden (I9). Convierte cada oficio paper en una muestra del libro de costos propio → el 0.10%/lado asumido se vuelve 0.10% medido, por símbolo y tamaño. Es construcción, permitida durante el gate.
2. **Opciones — línea nueva POST-gate (la familia ausente)**: el único frente donde un shop chico con datos gratuitos puede encontrar estructura no arbitrada por HFT: VRP (venta de vol sistemática con filtro de régimen), hedging de gamma flows (GEX como señal de represión de vol intradía — pega directo con el colector 1-min ya acumulando), PEAD vía opciones (coste de carry de la señal). Primitivo necesario: surface de IV por yfinance options (gratis) + las barras 1-min Alpaca. PRE-REGISTRO obligatorio como toda familia nueva; sin él, ni un solo trial.
3. **Intradía (I3 ya corriendo)**: colector 1-min de 7 símbolos acumulando desde 02/09. Las dos señales con t>10 del proyecto (gap-reversion t=−11.29, reversión intradía t≈−19) viven ahí. Ampliar a 102 símbolos = ~8MB/sem (auditoría de hoy) — costo cero, valor acumulativo.
4. **Meta-labeling (I5) — la única familia nueva de trial que cambia el objetivo**: en vez de cazar alpha crudo con n chico, un modelo secundario filtra los trades del baseline congelado usando features de contexto (régimen, vol, spread proxy). `barrier_labeling.py` (M1) ya está construido. El efecto necesario para ser rentable es menor — y el paper trading acumula labels gratis cada semana.
5. **Pesos jerárquicos (I4)**: la heterogeneidad per-ticker (pooled +0.06 vs mediana −0.074) no se resuelve con peso global; shrinkage James-Stein es el estimador correcto. Trial pre-registrable que arregla la vulnerabilidad w_mom 0.6642.
6. **Sizing de cartera con los 8 factores RMT**: ya computados, ya validados vs Marchenko-Pastur — usarlos para neutralizar exposición al factor mercado y residuales en vez de dejarlos como CSV huérfano.
7. **Señal multivariada**: ridge/elastic-net sobre los 102 activos con selección por IC, reemplazando el score lineal 2 factores + gates. Solo después del meta-labeling (si el filtro funciona, el step-up a multivariada tiene sentido; antes no).

---

## 5. Amenazas

1. **El gate se mide con definición inejecutable (D2)** → el 2026-12-01 llega con una racha que nadie verificó de verdad. Probabilidad ALTA de contaminación silenciosa. Mitigación: conectar reconcile al pipeline esta semana (es código, no hipótesis).
2. **Agente que corre un trial "inocente" durante el gate** — ya pasó con los 3 pilotos regime matching. El gate es disciplina documental, no enforcement técnico (contador manual, ROADMAP:16-18). Mitigación: check del ledger que rechace trials nuevos con fecha dentro del gate (bloqueo técnico barato).
3. **Edición del motor durante el gate que resetea la "contabilidad corregida"** — cada fix F0 corre ese riesgo y no hay detector. Mitigación: hash de los archivos críticos (`signal_engine.py`, `paper_trading.py`, `backtest_engine.py`) checkeado por el pipeline health en cada corrida.
4. **Fragmentación de memoria entre agentes** (Claude 2.2GB, Engram "boris", Kilo DB, CLINE_CONTEXT): las lecciones se comparten reactivamente (incidente → test), no proactivamente. El mismo fix FMP duplicado desde 2 worktrees ya demostró el modo de falla.
5. **Burnout del fundador (60% del pre-mortem)**: el sistema sigue dependiendo de que Boris arbitre decisiones de infraestructura. Mitigación en curso: agentes que cierran loops sin devolverle tareas (doctrina "cargar peso").
6. **Universo con sesgo de supervivencia + snooping ex-post no prevenido** (B3/B4 de NIVEL_DIOS, siguen abiertos): cada semana que pasa sobre el mismo histórico 2019-2026 lo quema un poco más para la confirmación final.

---

## 6. Recomendación fundada (una sola línea de acción, no menú)

**Antes del cierre del gate (hoy → diciembre), construir el loop cerrado de ejecución — es la única inversión que multiplica el valor de TODO lo demás:**

1. **Ya (sesión/s siguiente, construcción pura)**: reconciler de órdenes huérfanas dentro del pipeline `health` (D2), kill-switch por divergencia PnL (D3), telemetría decision vs fill (I9), hash-guard de archivos críticos del gate, DSR n_trials del motor unificado con el ledger (D5, 3 líneas). Con esto, el contador de días limpios pasa a medir algo real y cada oficio produce datos de costos.
2. **Durante el gate (paralelo, sin tocar hipótesis)**: congelar la capa multi-agente LLM como demo honesta — etiquetarla en el dashboard como "gobernanza descriptiva, no conectada a decisiones" (o desconectarla), no quemar llamadas API en decisiones decorativas. Fix D6 documentando el lag-0 del §39 o re-corriendo con open→close bajo pre-registro de corrección de bug de medición.
3. **Post-gate, si el paper es limpio**: abrir la línea de **opciones** (familia nueva, pre-registro, datos gratuitos ya accesibles) y **meta-labeling** (I5) como las dos familias nuevas de trial — las únicas que atacan rentabilidad en vez de repetir el diseño muestral que ya demostró subpotencia.

La lógica Simons detrás del orden: no se puede validar una señal sobre un sistema que no mide su propia ejecución; no se debe acumular más evidencia sobre un histórico ya quemado sin holdout; y las familias nuevas (opciones, meta-labeling) tienen mayor Sharpe esperado por esfuerzo que cualquier iteración más sobre momentum+RSI EOD, que ya entregó todo lo que podía entregar con n disponible.

---

## 7. Apéndice — qué se verificó hoy (trazabilidad)

- Pipeline diario sin capa agentes: imports en `pipeline_daily_signal.py:42-59` (spot-check directo).
- `reconcile_open_positions` sin callers: `rg` sobre `backend/` excluyendo tests → 0 productivos.
- Opciones inexistentes: `rg 'black.?scholes|implied.?vol|greeks|option.?chain'` → solo `typing.Optional` y sample LEAN equity.
- `DEFAULT_N_TRIALS=5`: `backtest_engine.py:651`; PBO entrada lag-0: `pbo_cscv_mom_rsi.py:141-143`.
- LLM único cliente `NvidiaNIMClient` con fallback robusto: `advanced_agents.py:230-331`; tríada semántica invertida: `triad_agents.py:183-187`;Professor sin precios: `advanced_agents.py:623-632`.
- knowledge_repo sin embeddings, 17 entradas hardcodeadas: `knowledge_repo.py:213-327`; `record_prediction` solo endpoint manual: `governance.py:161-164`.
- Fuente complementaria: `AUDITORIA_NIVEL_DIOS_20260902.md` (B0-B7, F0-F3, I1-I10) — su Fase 0 ya ejecutada; F1.6 (identificabilidad HMM) ya ejecutada `93b5718`; I3 (colector intradía) ya corriendo desde 02/09.
