# Plan de largo plazo — para Cline y OpenCode, trabajo autónomo

> Igual que `ORDENES_MODULOS.md`: cada bloque es autocontenido, dice qué leer y qué no.
> Regla de oro sigue vigente: un solo escritor por tarea. Nada de esto toca el motor
> de producción — todo vive en `backend/scripts/` + docs, con revert automático si
> no cumple.

**Actualizado: 2026-08-17.** Estado verificado contra ROADMAP.md, trial_registry.json, y artefactos en data/cache/.

## Estado de partida (verificado hoy, no asumir nada más)

- **Suite actual: 242 tests pasando** (no 216 ni 70/70).
- **Tarea A (Triple Barrier)** y **Tarea C (Lead-lag)**: CERRADAS con artefactos.
- **Tarea C (Command Code, §26 indicadores semanales)**: CERRADA — NO CUMPLE (2026-08-17).
- **Tarea B (FinBERT) PASO 1**: HECHO. `earnings_sentiment.py` + CLI + 25 tests. Acumulación completa: 48/48 símbolos, 369 filings. **PASO 2**: CERRADO — trial §27 NO_CUMPLE (2026-08-17, Kilo Code): el tono del comunicado 8-K 2.02 no predice retorno relativo a 20 ruedas (0/3 ventanas, signo inconsistente). Línea cerrada con la evidencia disponible; la store se conserva para re-acumulación futura.
- **Instrumento M1-M8 completo**: todos los módulos implementados, faltan trials que los usen.
- **ADX t=+2.31 nominal**: único factor con señal positiva. §25 (2026-08-17, Cline) lo probó en
  walk-forward OOS por ventana → **NO CUMPLE** (W1 +0.79 / W2 +1.54 / W3 +1.47, 0/3 cruzan
  Bonferroni-9 2.77). Queda **marginal-no-robusto con evidencia OOS, CERRADO como candidato a
  "bueno"**. No retomar sin evidencia nueva.
- **La línea "macro-como-compuerta" queda CERRADA.** Se probó dos veces y no sostiene. No retomar sin evidencia nueva.
- `AGENTS.md` de este repo tiene la doctrina de equipo — leerlo si es sesión nueva.
- **Problema estructural reconocido**: el proyecto tiene criterios claros para refutar, pero no para aceptar "bueno". El trial M2 (abstención calibrada) es el primero que responde "¿debería el motor callarse cuando no hay señal?" con evidencia existente.

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

## Tarea A — Trial de abstención calibrada M2 (OpenCode)

**ESTADO**: 🟢 CERRADO (2026-08-17) — trials #16 (tautológico: abstención 100% por
defecto estructural de M2) y #17 (con M2 corregido: hipótesis REFUTADA — la abstención
no mejora el VPP, p=0.4347). Pre-registros §24/§24.1. Línea cerrada como refutada;
M2 corregido queda disponible para scores futuros. NO reasignar.

```
PROBLEMA ESTRUCTURAL: El proyecto tiene criterios claros para refutar (DSR, Bonferroni,
pre-registro), pero no definió qué cuenta como "bueno" para decidir operar. Cada trial
termina en NO CUMPLE, y eso está bien — pero ADX quedó en tierra de nadie (t=+2.31
nominal, único factor positivo).

M2 (conformal.py) YA ESTÁ CONSTRUIDO: 16 tests, métrica vpp_bajo_abstencion, Split
Conformal Prediction con garantía de cobertura. Lo que falta es el TRIAL que lo
pruebe contra el baseline real.

HIPÓTESIS: El motor debería abstenerse (no operar) cuando la señal es débil. Un
instrumento que se abstiene el 80% del tiempo y acierta el 20% restante es un ÉXITO,
no un fracaso — mejora el VPP de lo que sí opera.

TAREA:
1. Pre-registro YA HECHO en PLAN_MEJORA_MATEMATICA.md §24 (nueva sección).
2. Construir backend/scripts/trial_m2_abstention.py:
   - Cargar baseline_clean_20260811_150643_trades.parquet (los 286 trades del baseline).
   - Para cada trade, obtener el score que tenía en el momento de entrada (usar
     la lógica existente de signal_engine o predictive_engine — NO reinventar).
   - Calibrar ConformalAbstentionEngine sobre W1 (2020-2021), predecir W2/W3.
   - Métrica primaria: vpp_bajo_abstencion (predicciones que NO se abstuvieron vs
     outcomes reales). Secundaria: cobertura empírica del intervalo 90%.
3. CRITERIO DE ÉXITO (pre-registrado):
   - vpp_bajo_abstencion > baseline_vpp (el VPP de operar todo sin filtro).
   - Cobertura empírica dentro de ±5pp del nominal 90%.
   - Familia "motor_signal", n_trials=9 (el siguiente en el ledger).
4. Correr, documentar veredicto con artefacto, registrar en ledger.

REGLAS: Python 3.9, NO tocar conformal.py ni el motor, solo scripts/ nuevo.
Artefacto en data/cache/trial_m2_abstention_YYYYMMDD_HHMMSS.txt.
```

---

## Tarea B — ADX walk-forward como candidato a "bueno" (Cline)

**ESTADO**: 🟢 CERRADO (2026-08-17) — NO CUMPLE, trial §25 corrido por Cline

```
PROBLEMA: ADX tiene t=+2.31 nominal, el único factor con señal positiva. No alcanza
para señar robusta bajo Bonferroni-4 (≈2.5), pero tampoco se probó en walk-forward.
Si se robustece en OOS, deja de ser marginal.

HIPÓTESIS: ADX como filtro único (no como parte del gate compuesto actual) podría
tener poder predictivo suficiente para justificar operar cuando adx≥20, abstenerse
cuando no.

TAREA:
1. Leer: backend/scripts/diagnose_rr2_intraday.py (patrón de rank IC intra-día),
   backend/app/core/signal_engine.py (cómo se calcula ADX hoy).
2. Pre-registrar en PLAN_MEJORA_MATEMATICA.md §25:
   - Hipótesis: adx_score (o ADX crudo) como factor único.
   - Ventanas W1/W2/W3, rank IC intra-día, Newey-West.
   - Criterio: |t|>2.77 en ≥2/3 ventanas (Bonferroni-9 por los 3 horizontes).
   - Familia "motor_signal", n_trials=10.
3. Construir backend/scripts/trial_adx_walkforward.py:
   - Para cada símbolo del universo 50, calcular ADX (usar signal_engine o
     implementación directa con el mismo lookback que el existente).
   - Rank IC intra-día entre ADX y fwd_return_20d (y/o Triple Barrier label de M1).
   - Walk-forward: calibrar en W1, testear en W2/W3.
4. Documentar veredicto con artefacto, registrar en ledger.

REGLAS: Python 3.9, NO tocar signal_engine.py sin autorización. Si CUMPLE,
discutir integración con el gate — no hacer solo.
```

---

## Tarea C — Indicadores sobre velas semanales (Command Code)

**ESTADO**: 🟢 CERRADO — NO CUMPLE (2026-08-17)

Pre-registrado §26 en PLAN_MEJORA_MATEMATICA.md, corrido
`scripts/diagnose_weekly_indicators.py`, artefacto
`data/cache/weekly_indicators_20260817_105918.txt`. Ningún indicador semanal
(momentum_20w, rsi_14w, adx_14w) alcanza |t|>2.73 bajo Bonferroni-8 en ninguna
de las 3 ventanas (máx |t|=0.44). Ruido semanal no oculta señal. Ledger
signal_diagnosis 15→16.

```
PROBLEMA: Todos los indicadores se calculan sobre barras DIARIAS. Nunca se probó
si una granularidad distinta (semanal) cambia el poder predictivo. Esto NO es cambiar
el horizonte del retorno futuro (eso ya se probó en M1/M1b) — es cambiar el RUIDO
del indicador mismo.

HIPÓTESIS: Indicadores calculados sobre velas semanales tienen menos ruido de
microestructura y podrían revelar señal que el ruido diario oculta.

TAREA:
1. Leer: backend/scripts/diagnose_rr2_intraday.py (patrón de rank IC),
   backend/app/core/signal_engine.py (cómo se calculan momentum/RSI/ADX hoy).
2. Pre-registrar en PLAN_MEJORA_MATEMATICA.md §26:
   - Universo: mismos 50 símbolos.
   - Indicadores: momentum (20 semanas), RSI (14 semanas), ADX (14 semanas).
   - Target: fwd_return_5d (1 semana hacia adelante) y/o Triple Barrier label.
   - Ventanas: re-muestrear W1/W2/W3 a semanas (mismo período, diferente granularidad).
   - Criterio: |t|>2.73 en ≥2/3 ventanas (Bonferroni-8: 3 indicadores × 3 ventanas
     — aunque solo se probando 3, el patrón del proyecto usa Bonferroni conservador).
   - Familia "signal_diagnosis", n_trials apropiado.
3. Construir backend/scripts/diagnose_weekly_indicators.py:
   - Cargar datos OHLCV del universo 50.
   - Resample('W-FRI') para convertir a velas semanales.
   - Calcular momentum/RSI/ADX sobre ESA serie semanal.
   - Rank IC intra-semana (no intra-día) contra retorno de la próxima semana.
4. Documentar veredicto con artefacto, registrar en ledger.

REGLAS: Python 3.9, NO tocar el motor existente. Script diagnóstico nuevo.
Si CUMPLE, discutir integración — no hacer solo.
```

---

---

## Ronda 2026-08-19 — Kilo Code y OpenCode

> Verificado antes de escribir esto: los 3 scripts de la ronda anterior
> (retest_triple_barrier.py, earnings_sentiment.py, diagnose_lead_lag.py) ya
> existen — no se reasignan. El bug "sin señal" (advisor.py, event loop
> bloqueado) ya está arreglado y pusheado (commit 2f6fbeb) — no tocar
> `_load_context_sync`/`_get_context()` en ese archivo salvo que sea
> exactamente para lo que dice la Tarea E.

### Tarea D — Curva de costo por tamaño (Kilo Code)

**ESTADO**: 🟡 CÓDIGO + TESTS LISTOS (21 tests costs, Kilo Code 2026-08-19) —
MEDICIÓN VIVA BLOQUEADA: **403 Forbidden de Alpaca paper** al enviar market orders
(la API key no tiene permisos de trading o la cuenta PA3QUWEX1XBJ necesita
activación). Pre-registro ESCRITO: PLAN_MEJORA_MATEMATICA.md **§30** (2026-08-19).
Acción requerida del USUARIO: habilitar trading en la cuenta paper / regenerar la
API key. Comandos listos en §30. NO reasignar a otro agente hasta desbloquear.

```
CONTEXTO: M4 ya midió costo real con qty=1 (cost_per_side_medido≈0.000189,
120 fills reales, backend/data/cache/measure_execution_costs_20260818_134338.txt).
Boris aprobó medir qty=10 y qty=50 para ver si el costo escala con el tamaño
(slippage por impacto de mercado). Esto es Tarea D, la wiring al motor real
(Tarea E de otro handoff) queda diferida hasta tener la curva completa.

TAREA:
1. Leer backend/app/core/execution_costs.py (measure_slippage, summarize — no
   modificar la firma de nada usado por M4 qty=1, solo agregar parámetro qty
   si no lo tiene ya) y el artefacto de qty=1 arriba citado, como referencia.
2. PRE-REGISTRAR en PLAN_MEJORA_MATEMATICA.md (próxima sección libre) ANTES de
   correr: hipótesis (el costo por lado sube con qty por impacto de mercado),
   qty a testear (10, 50, además del 1 ya medido), criterio de comparación
   (slippage_p50/p95 por qty, no un test estadístico formal — es medición, no
   trial de señal, así que no consume el ledger de n_trials).
3. Correr measure_execution_costs.py (o una copia parametrizada) con qty=10 y
   qty=50, SOLO con el mercado abierto (verificar horario US ET antes de
   correr), cuenta paper PA3QUWEX1XBJ (credenciales en backend/.env, NUNCA en
   chat/commit).
4. Documentar los 3 puntos (qty=1/10/50) en una tabla en PLAN_MEJORA_MATEMATICA.md,
   con los 3 artefactos citados. Actualizar ROADMAP.md M4.

REGLAS: paper trading únicamente. No tocar cost wiring al motor (settings.COST_PER_SIDE
    sigue en 0.0015, deliberado, deferred). No commitear/pushear sin autorización de Boris.
```

**VERIFICACIÓN 2026-08-19 Kilo Code:**
- Scripts `measure_execution_costs.py` + `execution_costs.py` implementados y tests pasan (21/21).
- Qty=1 ya medido: 120 orders, cost_per_side ≈ 0.000189, artefacto en data/cache/measure_execution_costs_20260818_134338.txt.
- **Bloqueado**: Qty=10/50 no se puede correr: Alpaca paper API devuelve 403 Forbidden en submit_order.
  Credenciales existen (market data funciona), pero el API key no tiene trading permissions o
  la cuenta PA3QUWEX1XBJ necesita activación.
- **Falta**: activar trading permissions en la API key paper de Alpaca para PA3QUWEX1XBJ.
  Una vez hecho: `.venv/bin/python -m scripts.measure_execution_costs --qty 10`
  y `--qty 50`. Los datos caen en execution_costs.db y costs.py los sirve automáticamente.

### Tarea E — Campo de costo real en el dashboard (OpenCode)

**ESTADO**: 🟢 CERRADO (2026-08-19, OpenCode) — `backend/app/api/routes/costs.py`
(GET /api/costs/current, DB-first + fallback .txt, curva por tamaño `sizes[]`,
nunca inventa), 6 tests nuevos (suite 271 passed), frontend `CostField.tsx` en
Layout + tipos/hook. Verificado contra el artefacto real (0.00018883729749502882
idéntico al .txt). `advisor.py` NO tocado. Sin commit descriptivo (auto-backup
db56f84). NO reasignar.

```
CONTEXTO: ROADMAP.md menciona un campo "costo/trade" en el dashboard que no
existe en el frontend (verificado: 0 referencias a cost_per_side o similar en
frontend/src). Ahora hay un número real medido (Tarea D en curso, o el de
qty=1 ya cerrado) — mejor construir el campo que borrar la mención.

TAREA:
1. Leer backend/app/api/routes/advisor.py SOLO para ver el patrón de router
   existente (prefix, HTTPException) — NO TOCAR ESE ARCHIVO, fue recién
   arreglado (bug de event loop bloqueado, commit 2f6fbeb) y cualquier edición
   ahí hoy corre riesgo de pisar la Tarea D si Kilo Code también lo toca.
2. Crear backend/app/api/routes/costs.py (archivo NUEVO, propio):
   GET /api/costs/current — lee el último artefacto/registro de
   execution_costs.db (o el .txt más reciente de measure_execution_costs_*)
   y devuelve {cost_per_side_medido, slippage_p50, slippage_p95, n_ordenes,
   ventana, fecha_medicion}. Si no hay medición, 200 con
   {"medido": false, "nota": "..."} — nunca inventar un número.
3. Registrar el router nuevo en app/api/routes/__init__.py (mismo patrón que
   los demás routers).
4. Frontend: un componente/campo chico que consuma /api/costs/current y
   muestre el costo medido (o "sin medición" si medido=false) — no simular
   datos si el endpoint no tiene nada todavía.
5. Tests: backend/tests/test_costs_api.py (mock del archivo/db, no red).

REGLAS: no tocar advisor.py. Python 3.9. No commitear/pushear sin autorización.
```

### Verificación de la Ronda 2026-08-19

`cd backend && .venv/bin/python -m pytest -q` debe seguir en 265+ passed antes
de cerrar cualquiera de las dos. Actualizar ROADMAP.md (la discrepancia del
campo queda resuelta, no solo señalada) y SESSION_LOG.md.

**ESTADO 2026-08-19 (OpenCode)**: suite **271 passed** ✓ (265+ cumplido). Tarea E
CERRADA y verificada. Tarea D: código+tests listos, medición viva BLOQUEADA por
403 Alpaca (acción del usuario: activar trading en la cuenta paper PA3QUWEX1XBJ /
regenerar API key con permisos; pre-registro §30 + comandos listos). ROADMAP.md y
SESSION_LOG.md actualizados. Sin commit descriptivo (auto-backup corrió).

---

## Verificación al cerrar cualquier tarea

`cd backend && .venv/bin/python -m pytest -q` debe seguir en verde (242+ passed)
antes de dar cualquier cosa por cerrada. Actualizar `ROADMAP.md` y `SESSION_LOG.md`.
Ninguna requiere que Claude Code esté presente — son autocontenidas.
