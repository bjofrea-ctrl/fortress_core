# HANDOFF — Híbrido objetivo × subjetivo: pre-registro del trial y huecos de datos

> **Para**: OpenCode (y cualquier agente que retome esto). **De**: Cline, sesión 2026-09-25.
> **Origen**: pedido de Boris — evaluar TradingAgents (auditoría en
> `ANALISIS_TRADINGAGENTS_VS_FORTRESS.md`) y su propuesta de arquitectura híbrida
> "objetiva + subjetiva". Este documento deja **verificado** qué existe, qué no, y **qué
> decisiones quedan abiertas para definir** — sin re-litigar nada ya refutado.

## 0. Lo que NO hay que volver a discutir (ya refutado, con artefacto)

| Línea | Veredicto | Artefacto |
|---|---|---|
| Sentimiento AAII como factor de ranking | **NO CUMPLE** | Trial #8 / Fase 0.6 — `fase06_retest_20260812_175055.txt` |
| FinBERT sobre 8-K 2.02 (tono de earnings) | **NO CUMPLE 0/3** | Trial #17 / §27 — `trial_finbert_eventstudy_20260817_163512.txt` |
| Fundamentales EDGAR (15 ratios) como ranking | **NO CUMPLE** | Trial #9 / Fase 0.6 |
| Tríada LLM sobre datos propios | **sin justificación medida** | §A9 — "306 llamadas HTTP decorativas… `validate_triad_llm.py` nunca produjo justificación" |
| TradingAgents como motor/capa de decisión | **no adoptar** | `ANALISIS_TRADINGAGENTS_VS_FORTRESS.md` §3 |

**La propuesta de Boris NO es reeditar esto.** Es una categoría distinta y legítima: **la
interacción** (¿la pata subjetiva condiciona el resultado del motor objetivo?). Está en la
misma categoría que `RESUMEN_VALIDACION_VARIABLES.md` §3 ("mejora en combinación, no probado
solo"), donde el ridge purgado tiene IC OOS +0.0156 y sin embargo, como score del motor,
fue refutado (#13). Ese es el precedente metodológico exacto: **combinar puede dar IC mejor
y no traducirse en PnL**. El trial debe medir PnL/DSR, no solo IC.

## 1. Evidencia verificada de esta sesión (todo con `file:line`)

### 1.1 Lo que YA existe (y Boris describió sin saber que existía)

- **"Abstención con razón, no silencio" ya está implementado**:
  `backend/app/api/routes/decision.py:54` `_STATE_RANK = {"NO_INVERTIR":0,"VIGILAR":1,"INVERTIR":2}`
  y `_state_rule()` (línea 57) devuelve siempre `(estado, razón)`:
  - `"régimen bloquea entradas"` (estado 3 = DEFLATION)
  - `"no pasa gate técnico"` · `"sin win_prob calibrado (calibración insuficiente)"`
  - `"win_prob calibrado X < 0.50"` → NO_INVERTIR · `"zona de vigilancia"` → VIGILAR
  - **`"M2 abstención (intervalo muy ancho)"` → VIGILAR** ← el instrumento conforme degradando INVERTIR
  - `"gate + win_prob >= 0.60 + M2 operativo"` → INVERTIR
- **Instrumento conforme (M2)**: `backend/app/core/conformal.py`, split-conformal α=0.10,
  n≥30 para calibrar; integrado en `decision.py::_fit_calibrators`.
- **Pata subjetiva (parte)**: `backend/app/core/market_sentiment.py` — AAII (desde 1987) + COT
  CFTC + FRED (WALCL/RRPONTSYD/WRESBAL), con disciplina anti-lookahead declarada
  (`shift(1) + ffill`, línea 258-278).
- **FinBERT earnings**: `backend/app/core/earnings_sentiment.py` (369 filings, 48 símbolos).
- **Perfiles institucionales**: `backend/app/core/institutional_fingerprint.py` (consume COT + AAII).

### 1.2 Lo que NO existe (verificado por búsqueda, no por omisión)

- **CNN Fear & Greed**: se midió en un smoke real el 2026-09-11 (32.2 "fear", put/call 0.74,
  VIX 17.8 — `ANALISIS_CICLO_INSTITUCIONAL.md` §22-30) **pero `thermometer.py` NO existe** en
  `main` ni en la historia de git (`git log --all -- '**/thermometer.py'` = vacío). Fue
  prototipo, no caño. **GDELT tone**: mismo caso.
- **Finnhub**: key presente, **nunca produjo datos** ("cache inexistente, mapeo FIELD_MAP nunca
  validado contra key real" — `COMPARACION_FUENTES_DATOS.md` §8).
- **Benzinga / Tiingo / Polygon / Databento**: 0 apariciones en el repo.
- **Job diario para COT/AAII/F&G**: no existe. `dataupdater` (22:00) refresca OHLCV + FinBERT;
  COT/AAII se piden **on-demand** (`institutional_fingerprint.py:460`, `predict.py:135`),
  y el resultado se ve: **el cache de COT estaba al 2026-08-04** (6 semanas de lag, declarado
  como limitación en `ANALISIS_MIEDO_20260914.md` §3).
- **Circuito de aprendizaje cerrado**: `backend/data/professor_memory.json` =
  `{"lessons": [], "agent_history": {}, "weight_adjustments": {}}` — **cero predicciones
  registradas** (hallazgo D4). `rag_memory.json` = 6 lecciones, todas de `SYSTEM`.

### 1.3 Corrección de un dato que yo mismo reporté mal

`DEFAULT_N_TRIALS` **ya está resuelto** (A6): `backtest_engine.py:658`
`DEFAULT_N_TRIALS = None  # sentinel` → `_resolve_default_n_trials()` lee
`consumed_budget("signal_diagnosis")` en runtime, con fallback explícito a **29** +
`n_trials_fallback_reason` en el payload. El D5 ("DSR deflacta por 5 vs 51 reales") **está
arreglado**. Pero queda una **pregunta abierta real** (ver §4, D2): la deflación es
**por familia**, y el ledger tiene **51 entradas** en total.

---

## 2. La arquitectura corregida — tres patas, no dos

La propuesta era "objetiva vs subjetiva". La corrección de esta sesión (verificada contra el
propio docstring de `market_sentiment.py`: *"mide la ACTITUD de la gente, no posiciones (a
diferencia del COT)"*) es que **"¿el mercado lo está comprando?" no se responde con texto** —
se responde con posición y flujo:

| Pata | Pregunta | Insumos | Estado en el repo |
|---|---|---|---|
| **Objetiva** | ¿hay edge? | Precio, volumen, fundamentales, macro | `signal_engine` + HMM — operativa, **sin edge confirmado** (DSR 0.6077 < 0.95) |
| **Acción** | ¿ya lo compraron? | COT, put/call, F&G, volumen relativo, breadth | COT ✅ existe y **no está cableado al motor** (grep: no aparece en `signal_engine.py` ni en `regime_classifier.py`) |
| **Expectativa** | ¿qué creen que pasará? | Texto (FinBERT, noticias), AAII | FinBERT ✅ / AAII ✅ / noticias ❌ |

Consecuencias de diseño que esto habilita:
1. La pata **Acción tiene historia larga y gratis** (COT se descarga por año vía
   `com_fin_txt_{year}.zip`, `market_sentiment.py:91`), a diferencia de la expectativa (texto),
   que no tiene vintage y **solo se puede acumular hacia adelante**.
2. Por eso: **hay una parte del híbrido testeable con datos ya disponibles** (acción × objetivo),
   sin comprar ninguna API.
3. La métrica de la pata subjetiva no tiene que ser "edge": puede ser **calidad de abstención**
   (VPP bajo abstención, métrica primaria de M2 en `conformal.py`). Convertir INVERTIR en
   VIGILAR *con razón* es un resultado medible — y es la tesis de Boris ("mejor que ganar más es
   perder mejor").

## 3. La pregunta medible (una sola)

> **¿El resultado del motor objetivo (retorno/PnL a horizonte H, con sus costos y lag=1)
> cambia de forma estadísticamente significativa según el estado de la pata subjetiva/acción
> medido point-in-time el mismo día?**

Forma técnica: **interacción**, no factor suelto. Dos variantes (decisión de OpenCode, §4 D1):
- **A (condicional)**: particionar la señal del motor por estado de la pata subjetiva y comparar
  retornos entre grupos (Newey-West + Bonferroni de la familia).
- **B (puerta)**: la pata subjetiva actúa como *filtro* (no opera cuando no acompaña) y se mide
  VPP bajo abstención vs VPP operando siempre (protocolo M2 ya existente en `conformal.py`).

**Lo que el trial debe reportar**: veredicto binario CUMPLE/NO_CUMPLE contra umbral declarado
ANTES, con n_trials declarado, artefacto en `data/cache/`, y registro en `trial_registry.json`
con `veredicto` + `artefacto` (obligatorios si status COMPLETED — `trial_registry.py:404`).

**Criterio que recomiendo declarar** (OpenCode puede cambiarlo, pero ANTES de correr):
- Diferencia de **PnL neto** (no IC) entre grupos, con t-NW, contra el umbral vigente de la
  familia: `current_threshold(familia)` (`trial_registry.py:932`) — derivado de las entradas,
  **nunca hardcodeado**.
- Declaración explícita de que **NO_CUMPLE es un resultado útil** (filtra o no filtra: ambas
  respuestas sirven).

## 4. Decisiones abiertas — lo que OpenCode tiene que definir

Cada una cambia el resultado antes de verlo; por eso van acá y no en el chat.

| # | Decisión | Por qué importa | Dónde mirar |
|---|---|---|---|
| **D1** | Variante A (condicional) vs B (puerta/abstención) | Miden cosas distintas: A busca edge condicional, B busca mejor abstención. **B tiene precedente de funcionar** (M2 corregido, trial #17) | `conformal.py`, `decision.py::_state_rule` |
| **D2** | ¿Familia nueva (`hibrido_objetivo_x_subjetivo`) o subfamilia existente? | El umbral y el `consumed_budget` son **por familia** (`trial_registry.py:915/932`). Una familia nueva arranca con su propio presupuesto → cambia la vara. Declararlo antes es lo que separa pre-registro de p-hacking | `trial_registry.py` |
| **D3** | Qué pata entra: ¿Acción (COT/put-call), Expectativa (AAII/FinBERT), o ambas? | Si son dos, son **dos trials**, no uno (si no, se diluye la corrección por comparaciones múltiples) | `market_sentiment.py`, `earnings_sentiment.py` |
| **D4** | Horizonte H y métrica | El precedente de la casa es 20 ruedas (replay de calibración en `decision.py::_fit_calibrators`); declararlo y no moverlo | `decision.py:80` |
| **D5** | ¿Se extiende `COT_START_YEAR=2019` hacia atrás? | CFTC publica años anteriores con el mismo patrón de URL; hoy el módulo **trunca la historia por una constante** (`market_sentiment.py:93`). Extender es gratis y da 10+ años más de pata Acción | `market_sentiment.py:91-123` |
| **D6** | ¿Reserva ahora (`register_trial_reservation`) o entrada post-gate? | El ledger valida el gate solo (`_gate_window_check`, línea 755). Una reserva consume slot Bonferroni (n≥1 obligatorio) | `trial_registry.py:690, 755` |
| **D7** | MDE/potencia | `_mde_check` (línea 344): hay que declarar el efecto mínimo detectable. Si la potencia no alcanza, el veredicto correcto es **INEJECUTABLE**, no un resultado | `trial_registry.py:344`, `test_mde_power.py` |

## 5. Los tres huecos de datos (y qué hacer con cada uno)

| Hueco | Evidencia | Acción propuesta | Costo |
|---|---|---|---|
| **COT truncado + sin refresco** | `COT_START_YEAR=2019` (`market_sentiment.py:93`); cache al 2026-08-04 (`ANALISIS_MIEDO_20260914.md` §3) | (a) extender años hacia atrás; (b) job que lo refresque junto al resto | gratis, ~1 script |
| **F&G sin caño** | `thermometer.py` no existe; el dato se midió una vez el 11-09 (`ANALISIS_CICLO_INSTITUCIONAL.md`) | decidir si se implementa como módulo congelado (no como smoke) — **solo si D1/D3 lo requieren** | gratis, ~1 módulo |
| **Noticias sin vintage** | 0 módulos de noticias en el repo | acumular **texto crudo por día, inmutable**, mismo patrón que `collect_iv_surface.py` ("el caño antes de que pase el agua"). El texto crudo es el activo durable; la opinión del modelo es derivada y caduca | gratis, ~1 colector + plist |

## 6. Trampas conocidas — no repetirlas

1. **No inferir PnL desde IC.** El precedente más caro del proyecto: el ridge purgado tenía IC
   OOS **+0.0156** (ICIR 0.78, +0.0285 sobre el blend simple) y como score del motor fue
   **refutado** (trial #13, DSR 0/3). El IC mejor **no se tradujo en PnL**. Este trial debe
   reportar PnL neto.
2. **No usar lag 0.** El estándar del proyecto es `execution_lag_days=1` (fix T0.2, open→close
   del día siguiente). El §39/PBO vigente arrastra una limitación lag-0 declarada (A8) que
   **no se puede repetir** en un trial nuevo.
3. **No correr sobre el holdout.** El ledger tiene `_holdout_check` + `_holdout_escape_active`
   (líneas 225-310) y `_declared_historical_end`. Un trial que toca el holdout se marca solo.
4. **No dejar el criterio para después.** `validate_umbral_aplicado` (línea 891) compara el
   umbral declarado en el pre-registro contra el aplicado: si no coinciden, es un hallazgo
   contra el trial.
5. **No revivir Finnhub** ni pagar feeds nuevos antes de saber si la interacción existe con los
   datos gratis que ya están en el repo.
6. **No apagar/encender `GOVERNANCE_LLM_ENABLED` para "probar".** A9 la apagó por falta de
   evidencia; se re-enciende **solo** si un trial la valida.
7. **Cuidado con el cache.** `COMPARACION_FUENTES_DATOS.md` documenta que el defecto más grave
   del proyecto no fue divergencia entre fuentes, sino **corrupción dentro de una sola fuente
   (yfinance) congelada por el diseño append-only**. Cualquier serie nueva debe nacer con
   validación, no después.

## 7. Checklist de entrega (para el cierre de OpenCode)

- [ ] Pre-registro escrito **antes** de correr: familia, hipótesis, n_trials, umbral, H, MDE,
      corrección por comparaciones múltiples, criterio de éxito/fracaso.
- [ ] Las 7 decisiones de §4 resueltas y **escritas** (no en el chat).
- [ ] Entrada en el ledger vía `register_trial()` (o reserva vía
      `register_trial_reservation()`) con los campos obligatorios de `_validate_entry`: `id`,
      `fecha`, `familia`, `hipotesis`, `n_trials_consumidos`, `umbral_aplicado`, `seccion_doc`
      (+ `status`).
- [ ] Si se corre: artefacto en `data/cache/` y `veredicto` (CUMPLE/NO_CUMPLE) — ambos
      obligatorios para status COMPLETED.
- [ ] `ROADMAP.md` actualizado + entrada en `SESSION_LOG.md`.
- [ ] Si algún hallazgo cambia una decisión ya tomada: citarlo en
      `RESUMEN_VALIDACION_VARIABLES.md`.

## 8. Protocolo de comunicación entre agentes (Herdr)

Estamos dentro de **Herdr** (`/usr/bin/herdr`, v0.8.2; `HERDR_ENV=1`). Estado verificado al
inicio de esta sesión:

| Agente | Pane | Estado |
|---|---|---|
| `fortress-opencode` (orquestador) | `w2:p1` | `idle` — "OC \| Orquestador workspace fortress en espera" |
| Cline (esta sesión) | `w2:p3` | — |

**Comandos** (interfaz `herdr agent`, verificada en v0.8.2):
```bash
herdr agent list                                    # descubrir agentes y panes
herdr agent prompt fortress-opencode "<texto>"      # encolar trabajo (--wait --timeout N para esperar)
herdr agent read fortress-opencode --source recent-unwrapped --lines 120
herdr agent wait fortress-opencode --until blocked --timeout 120000
```

**Regla de oro de la lectura** (documentada por Herdr): OpenCode renderiza su transcript en
*alternate screen*, y leer historia larga requiere el agente **idle** (`agent_not_idle` si está
trabajando). Por eso el protocolo es:

> **OpenCode escribe su análisis y sus preguntas como Markdown en un archivo del repo y
> responde con la ruta.** Leer el archivo es más confiable que leer el pane.

Entregables esperados de OpenCode (uno o ambos):
- `ANALISIS_OPENCODE_HIBRIDO.md` — las 7 decisiones resueltas con su fundamento, y cualquier
  corrección a las afirmaciones de este documento (con `file:line`).
- `PRE_REGISTRO_HIBRIDO_OBJETIVO_X_SUBJETIVO.md` — el pre-registro en sí, si decide escribirlo.

**Instrucción explícita**: si algo de este documento está mal, **corregirlo contra el artefacto
y decirlo**. Este handoff fue escrito verificando, pero no es palabra santa — la regla 1 de
`ONBOARDING.md` aplica también a lo que escribo yo.

## 9. Fuentes y artefactos de esta sesión

**Auditoría del repo externo**: `ANALISIS_TRADINGAGENTS_VS_FORTRESS.md` (commit `7005e33`) ·
clone `/tmp/TradingAgents` @ `35543d0248bf89fcb92b17a15858ad0c0e940687` (v0.5.1, Apache-2.0).

**Del repo propio** (verificado con lectura o grep, no por memoria):
`backend/app/api/routes/decision.py` (`_STATE_RANK:55`, `_state_rule:57`,
`_fit_calibrators:80`) · `backend/app/core/conformal.py` · `backend/app/core/market_sentiment.py`
(`COT_URL:91`, `COT_START_YEAR:93`, `fetch_cot_years:123`, `fetch_aaii:208`, shift(1)+ffill:258-278) ·
`backend/app/core/earnings_sentiment.py` · `backend/app/core/institutional_fingerprint.py:460,759` ·
`backend/app/core/trial_registry.py` (`_validate_entry:404`, `register_trial:623`,
`register_trial_reservation:690`, `_gate_window_check:755`, `complete_trial:770`,
`trials_by_family:907`, `consumed_budget:915`, `current_threshold:932`, `_mde_check:344`) ·
`backend/app/core/backtest_engine.py:658` (A6) ·
`backend/data/{professor_memory,rag_memory,trial_registry}.json` ·
`backend/scripts/collect_iv_surface.py` (patrón de acumulación inmutable).

**Documentos citados**: `RESUMEN_VALIDACION_VARIABLES.md` (§1, §2, §3) ·
`PLAN_MEJORA_MATEMATICA.md` §27 · `ANALISIS_MIEDO_20260914.md` (uso manual del híbrido + COT
stale) · `ANALISIS_CICLO_INSTITUCIONAL.md` (smoke F&G) · `COMPARACION_FUENTES_DATOS.md` §8 ·
`B3_PREREGISTRO.md` (formato de pre-registro) · `PLAN_IMPLEMENTACION_REMEDIO_20260903.md`
§A6/§A9 · `ONBOARDING.md` (reglas 1-5) · Herdr `agent-guide.md` + `/docs/agent-automation/`.
