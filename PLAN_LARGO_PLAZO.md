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

## Ronda 2026-08-19 (noche) — Kilo Code y OpenCode

> Verificado antes de escribir esto: tabla maestra de ROADMAP.md está 100% 🟢
> salvo LEAN (parqueado, no tocar) y broker real (bloqueado, correcto). Las dos
> tareas de abajo son de investigación/verificación de solo lectura — ninguna
> toca `advisor.py` ni el motor de decisión. No se pisan entre sí (una es
> backend/datos, la otra es frontend/navegador).

### Tarea F — Por qué `/api/advisor/universe` devuelve 44 símbolos y no 50 (Kilo Code)

**ESTADO**: 🟢 CERRADO (2026-08-19, Kilo Code + OpenCode) — **NO es bug**. El endpoint
itera `opportunities.SYMBOLS`, una lista curada HARDCODED de 44 símbolos — distinta del
"universo 50" (BASE_SYMBOLS 7 + NEW_UNIVERSE 43) que usan los trials de investigación y
la medición de costos. Verificación empírica: `load_universe(SYMBOLS)` cargó 44/44 (0
descartados), el loop de `advisor_universe` no descarta nada. Diferencia de listas:
50−44 = [AMD, CMCSA, DIS, INTU, META, PFE, QCOM, SPGI, TSLA]; 44−50 = [ABT, GS, WFC].
No es subconjunto. Artefacto `diagnostico_universo_20260819_174613.txt`. Acción no
aplicada (diagnóstico): cubrir los 50 sería cambiar `opportunities.SYMBOLS` — decisión
del usuario. NO reasignar.

```
CONTEXTO: ROADMAP.md fila "Dashboard institucional consolidado" registra que la
verificación en vivo del endpoint mostró "universe 44 símbolos régimen 2" sin
explicar la causa. Nunca se investigó si es esperado (filtrado por régimen o
por datos insuficientes) o un bug real.

TAREA (solo lectura/diagnóstico, sin tocar advisor.py):
1. Leer backend/app/api/routes/advisor.py función `advisor_universe` (línea
   ~178) y `_compute_ticket` — identificar bajo qué condición un símbolo del
   universo de 50 queda afuera del array de respuesta (return None, excepción
   silenciosa, filtro explícito, datos insuficientes).
2. Correr el endpoint (o el mismo código en un script/notebook de diagnóstico)
   contra el universo 50 real y listar EXACTAMENTE cuáles 6 símbolos faltan y
   por qué (log del motivo por símbolo).
3. Documentar el hallazgo en ROADMAP.md (fila nueva o actualizar la existente):
   si es comportamiento esperado (ej. datos insuficientes para esos 6), decirlo
   con evidencia; si es un bug, describirlo y proponer el fix en un pre-registro
   corto en PLAN_MEJORA_MATEMATICA.md ANTES de tocar el endpoint — no cambiar
   `advisor.py` en esta tarea sin ese pre-registro aprobado.

REGLAS: NO modificar advisor.py ni el motor de señal en esta tarea — es
diagnóstico. Si el fix es trivial y sin riesgo (ej. loggear el motivo del
descarte), documentarlo como propuesta, no aplicarlo. No commitear/pushear sin
autorización de Boris.
```

### Tarea G — Verificación visual del navegador del dashboard (OpenCode)

**ESTADO**: 🟢 CERRADO (2026-08-19, OpenCode) — verificación hecha con Chrome
headless + CDP (verificación post-render del DOM + logs de consola, no solo
endpoints). Las 4 vistas cargan sin errores de consola; CostField muestra datos
reales (0.017% · n=156 · curva 1/10/50); Detalle renderiza chart Lightweight
Charts + Zonas mecánicas + M2 + Plan de salida 4 mecanismos. **Hallazgo no
bloqueante (backend, NO arreglado)**: `/api/advisor/AAPL` tarda ~80s por intentos
de descarga de Yahoo de símbolos fantasma en `_compute_ticket` — propuesto como
fix aparte (no aplicado). Ver ROADMAP fila dashboard + SESSION_LOG. NO reasignar.

```
CONTEXTO: ROADMAP.md fila "Dashboard institucional consolidado" tiene
"Pendiente explícito: verificación visual del navegador" desde el 2026-08-17 —
nunca se hizo. Ahora además incluye el chip CostField.tsx nuevo (Tarea E).

TAREA:
1. Levantar el frontend (`npm run dev` o el flujo que ya use el proyecto) y
   abrir las 4 vistas lazy-loaded (Mesa/Detalle/Portfolio/Gobernanza).
2. Confirmar por vista: sin errores de consola, chart Lightweight Charts
   renderiza con EMA50/200 y zonas mecánicas, widget TradingView degrada bien
   si falla, CostField.tsx visible en el Layout con el tooltip
   p50/p95/n/fecha, Exit Thesis Monitor visible, Evidence Footer con datos
   reales del trial_registry (no placeholders).
3. Documentar el resultado (capturas o descripción) en ROADMAP.md, cerrando el
   "pendiente explícito" de esa fila con evidencia concreta. Si encontrás un
   bug visual, documentarlo con severidad — no lo arregles en esta tarea salvo
   que sea CSS trivial y aislado (no lógica de datos).

REGLAS: solo frontend. No tocar backend/advisor.py. No commitear/pushear sin
autorización de Boris.
```

### Verificación de la Ronda 2026-08-19 (noche)

Ninguna de las dos tareas debería tocar tests backend (son diagnóstico +
verificación visual). Si Tarea F propone un fix, queda como pre-registro
pendiente de aprobación, no aplicado. Actualizar ROADMAP.md y SESSION_LOG.md al
cerrar cada una.

---

### Tarea J — §34: reabrir C6 (MA200 hedged) bajo el costo MEDIDO (OpenCode)

**ESTADO**: 🟢 CERRADO (2026-08-19, OpenCode) — **NO CUMPLE**. §34 pre-registrado
ANTES de correr; trial formal `motor_signal` (ledger 10→11, umbral 0.991667),
artefacto `backtest_c6_hedge_costo_medido_20260819_155509.txt`. Con el costo medido
0.05%/lado (3× menor al 0.15% asumido), el LS-HEDGE NETO pasó de −0.000292 a
**+0.000010/día (t-NW +0.07)** — el costo corregido SÍ movió el neto hacia positivo,
pero la señal bruta es débil (+0.000157, t-NW +1.07) y NO cruza el criterio t-NW ≥ 2.0.
**C6 queda cerrado DEFINITIVO por segunda vez, ahora contra el costo real medido,
sin ambigüedad.** NO se integra al motor. Check integridad: n=3710/Pearson −0.1603/
Spearman −0.1148 — desviación menor vs §16 (3703/−0.1582/−0.1129) verificada como
refresh de datos (data_updater 17/08): el script ORIGINAL §18.2 re-corrido hoy da
idéntico, mi copia es fiel. NO reasignar.

**AUTORIZADO por Boris (2026-08-19 noche)**: "lo más sólido, no lo más fácil" —
se reabre C6 con el protocolo COMPLETO, no un atajo. No es un re-run casual del
script viejo: es un TRIAL FORMAL nuevo que consume `n_trials` de la familia
`motor_signal` (verificado contra el ledger real ahora: **consumidos 10,
próximo umbral Bonferroni 0.990909**).

```
CONTEXTO: §18.2 (backend/scripts/backtest_c6_hedge.py, 2026-08-13) cerró la línea
C6 como DEFINITIVA con costo asumido 0.15%/lado: BRUTO +0.000149/día (t-NW +1.01,
positivo — el hedge neutralizó el drift), NETO −0.000292/día (t-NW −1.97) — murió
por costo, no por falta de señal. Hoy (§33, 2026-08-19) el costo real medido con
156 órdenes paper es 0.05%/lado — 3× menos que el 0.15% que mató a C6. Esto es
evidencia nueva y externa (no una re-parametrización de la señal), el único motivo
que el propio §18.2 reconoce como legítimo para reabrir.

TAREA:
1. Leer backend/scripts/backtest_c6_hedge.py completo (NO modificarlo — es
   artefacto histórico, regla de §33) y backend/app/config.py (COST_PER_SIDE
   actual 0.0005).
2. PRE-REGISTRAR §34 en PLAN_MEJORA_MATEMATICA.md ANTES de correr nada:
   - Hipótesis: el fade C6 hedgeado (idéntico a §18.2: mismo universo AAPL/V/MA/
     ORCL/IBM/QCOM/TXN, misma señal dist_ma200, mismo hold 20d, mismo hedge por
     beta pre-muestra 2015-2018) deja retorno NETO diario positivo con el costo
     REAL medido (0.05%/lado, no 0.15%).
   - Metodología: IDÉNTICA a §18.2 en todo excepto el costo — panel debe
     reproducir n=3703, Pearson IC −0.1582, Spearman −0.1129 (check de
     integridad §14, igual que el original).
   - Criterio de éxito (fijado ANTES de correr, igual que §18.1/§18.2 para
     comparabilidad): `n_días_con_posiciones ≥ 100` Y retorno diario NETO medio
     > 0 con `t-NW ≥ 2.0`.
   - Familia `motor_signal`, n_trials 10→11, umbral Bonferroni 0.990909
     (confirmar de nuevo con el comando del ledger antes de cerrar, puede haber
     cambiado si otro trial corrió antes).
3. Construir `backend/scripts/backtest_c6_hedge_costo_medido.py` — COPIA
   parametrizada de `backtest_c6_hedge.py` con `cost_per_side` como argumento
   (default 0.0005), NO se edita el script original.
4. Correr. Documentar el veredicto — CUMPLE o NO CUMPLE — con artefacto real en
   `data/cache/`, sea cual sea el resultado.
5. Registrar el trial en el ledger (`trial_registry.py: register_trial(...)`)
   al cerrar, con su veredicto real.
6. Actualizar ROADMAP.md (fila C6/§18) y SESSION_LOG.md. Si CUMPLE: NO se
   integra al motor en esta tarea — queda como candidato real, la integración
   es un trial de motor aparte con su propio pre-registro. Si NO CUMPLE: la
   línea C6 queda cerrada definitivamente por segunda vez, ahora también contra
   el costo real, sin ambigüedad posible.

REGLAS: no tocar advisor.py, signal_engine.py, ni el score en vivo. No
modificar backtest_c6_hedge.py (histórico). Python 3.9. No commitear/pushear
sin autorización de Boris.
```

---

## Verificación al cerrar cualquier tarea

`cd backend && .venv/bin/python -m pytest -q` debe seguir en verde (242+ passed)
antes de dar cualquier cosa por cerrada. Actualizar `ROADMAP.md` y `SESSION_LOG.md`.
Ninguna requiere que Claude Code esté presente — son autocontenidas.
