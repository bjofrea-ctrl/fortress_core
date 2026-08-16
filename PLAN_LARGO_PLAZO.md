# Plan de largo plazo — para Cline y OpenCode, trabajo autónomo

> Igual que `ORDENES_MODULOS.md`: cada bloque es autocontenido, dice qué leer y qué no.
> Regla de oro sigue vigente: un solo escritor por tarea. Nada de esto toca el motor
> de producción — todo vive en `backend/scripts/` + docs, con revert automático si
> no cumple.

## Estado de partida (verificado hoy, no asumir nada más)

- Instrumento diagnóstico M1-M8 completo y verificado: 216 tests, ruff limpio.
- **La línea "macro-como-compuerta" queda CERRADA.** Se probó dos veces: la medición
  original (+0.198 GOLDILOCKS/−0.173 DEFLATION) estaba contaminada por lookahead
  (§3.1); la re-medición limpia (`PLAN_MEJORA_MATEMATICA.md:519-527`) da GOLDILOCKS
  +0.112, REFLATION +0.106, STAGFLATION +0.121, DEFLATION +0.249 — ningún `|t|>2`,
  el patrón contra-régimen NO se sostiene. **No retomar sin evidencia nueva.**
- `AGENTS.md` de este repo tiene la doctrina de equipo — leerlo si es sesión nueva.

## Regla no negociable para las tres tareas de abajo

Cada una termina en un **trial que corre contra datos reales**. Todas deben:
1. Pre-registrarse en `PLAN_MEJORA_MATEMATICA.md` (próxima sección libre — verificar
   el número más alto con `grep -o '§[0-9]*' PLAN_MEJORA_MATEMATICA.md | sort -u | tail -1`)
   **ANTES** de correr el script. Metodología + criterio de éxito/fracaso fijados por
   escrito antes de ver un resultado.
2. Confirmar `n_trials` y familia contra el ledger real:
   `cd backend && .venv/bin/python -c "from app.core.trial_registry import consumed_budget, current_threshold; print(consumed_budget('motor_signal'), current_threshold('motor_signal'))"`
   — no asumir el número, leerlo.
3. Si NO CUMPLE: se documenta con su artefacto (`data/cache/`, timestamp) y se revierte
   (el script se puede dejar, pero no se integra nada al motor).
4. Registrar el trial en el ledger (`app/core/trial_registry.py: register_trial(...)`)
   al cerrar, con su veredicto.

---

## Tarea A — Triple Barrier como target de investigación (Cline)

```
PROBLEMA: toda la investigación histórica de este proyecto midió factores contra
fwd_return_20d (retorno a horizonte fijo). El motor real sale por barreras (M1,
app/core/barrier_labeling.py — ya construido y con 17 tests, no tocar ese archivo).
Nunca se re-testearon los factores YA REFUTADOS (momentum_score, rsi_score,
adx_score — RESUMEN_VALIDACION_VARIABLES.md §1) contra el objetivo que el motor
persigue de verdad.

HIPÓTESIS: un factor puede ser nulo contra fwd_return_20d (ruido de magnitud) y
tener poder real contra "¿toca TP antes que SL?" (probabilidad binaria, robusta a
colas). No contradice el diagnóstico de "generador vacío" — lo refina.

TAREA:
1. Leer SOLO: backend/app/core/barrier_labeling.py (firmas de label_symbol/summarize,
   no tocar), backend/scripts/diagnose_horizon_largo.py (mismo patrón de rank IC
   intra-día + Newey-West que hay que replicar).
2. Construir backend/scripts/retest_triple_barrier.py:
   - Para cada símbolo del universo 50 (fetch_universe_data.NEW_UNIVERSE + los 7
     originales), correr label_symbol(df) → obtener 'label' (+1/-1/0) por fecha.
   - Rank IC intra-día (Spearman por fecha, igual que todos los trials previos)
     entre momentum_score/rsi_score/adx_score y 'label' (NO fwd_return_20d).
   - Newey-West SE, mismo patrón de diagnose_horizon_largo.py.
   - Ventanas W1/W2/W3 (2020-2021 / 2022-2023 / 2024-2026), mismas de siempre.
3. PRE-REGISTRAR antes de correr: criterio DSR o significancia (seguir el patrón de
   §21.1), familia "motor_signal" en el ledger, Bonferroni sobre 3 factores × 3
   ventanas = 9 tests nuevos.
4. Correr, documentar veredicto con artefacto, registrar en el ledger.

REGLAS: Python 3.9, no tocar barrier_labeling.py ni el motor, no commitear sin
autorización de Boris.
```

---

## Tarea B — FinBERT sobre earnings calls (OpenCode)

```
PROBLEMA: la única fuente de sentimiento probada fue AAII (encuesta de inversores
retail, refutada #8 y re-refutada Fase 0.6). FinBERT sobre TONO de earnings calls
es una fuente de datos distinta — nunca probada — y gratis (HuggingFace).

TAREA (multi-sesión, dividir en pasos):
PASO 1 — Pipeline de datos:
1. backend/app/core/earnings_sentiment.py: scraper de transcripciones (fuente
   pública gratis — evaluar Seeking Alpha o SEC EDGAR 8-K con transcripción
   adjunta) + FinBERT (transformers, pipeline "sentiment-analysis",
   modelo "ProsusAI/finbert") → score de sentimiento por (símbolo, fecha earnings).
2. Persistir en SQLite (mismo patrón que M4: backend/data/cache/earnings_sentiment.db).
3. Empezar a acumular YA — cada earnings call de cada símbolo del universo 50 que
   se reporte de acá en adelante. Esto es infraestructura, se construye libre, sin
   pre-registro (no es un trial todavía).

PASO 2 — cuando haya ≥8 trimestres acumulados para ≥30 símbolos:
4. Pre-registrar en PLAN_MEJORA_MATEMATICA.md un trial: sentiment_score como factor
   adicional en rank IC intra-día contra fwd_return_20d Y contra Triple Barrier
   (label de M1) — mismo patrón que Tarea A. Familia "motor_signal" en el ledger.

REGLAS: Python 3.9, requests/BeautifulSoup para scraping (agregar a requirements
si falta), transformers para FinBERT. No pegar a APIs pagas. No correr el trial del
paso 2 hasta tener los 8 trimestres — documentarlo como bloqueado, no simular datos.
```

---

## Tarea C — Lead-lag entre símbolos (Command Code)

```
PROBLEMA: nunca se testeó si un símbolo predice a otro (ej. NVDA→AMD por cadena de
suministro) — todo lo probado hasta hoy mide un símbolo contra su propio pasado.
Barato: no necesita datos nuevos, solo el panel diario que ya existe.

TAREA:
1. backend/scripts/diagnose_lead_lag.py: para pares de símbolos del mismo sector/
   cadena (definir la lista de pares candidatos ANTES de mirar resultados — ej.
   semis: NVDA-AMD, NVDA-AVGO; mega-cap tech: AAPL-MSFT), correlación cruzada
   desfasada (lag 1-5 días) de retornos, con el mismo Newey-West de siempre.
2. PRE-REGISTRAR la lista de pares y los lags a testear ANTES de correr (si se
   testean N pares × 5 lags, Bonferroni sobre N×5). Esto es fácil de p-hackear
   si se eligen pares después de ver qué "funciona" — no hacerlo.
3. Documentar veredicto, registrar en ledger.

REGLAS: mismas de siempre — Python 3.9, revert si NO CUMPLE, artefacto con timestamp.
```

---

## Verificación al cerrar cualquier tarea

`cd backend && .venv/bin/python -m pytest -q` debe seguir en verde (216+ passed)
antes de dar cualquier cosa por cerrada. Actualizar `ROADMAP.md` y `SESSION_LOG.md`.
Ninguna requiere que Claude Code esté presente — son autocontenidas.
