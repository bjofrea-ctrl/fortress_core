# PLAN DE IMPLEMENTACIÓN — REMEDIO DE BRECHAS (con fundamentos)

**Fecha**: 2026-09-03 · **Autor**: Kilo Code · **Para**: conversación con Claude Code (orquestador) y aprobación por fase de Boris.
**Deriva de**: `PLAN_REMEDIO_BRECHAS_20260903.md` (f643956 + B0 en f9134bd) · `AUDITORIA_INTEGRAL_SISTEMA_20260903.md` (D1-D12) · `AUDITORIA_NIVEL_DIOS_20260902.md`.
**Status**: borrador para discusión — NINGÚN código escrito aún. Fase A implícitamente aprobada ("ok" de Boris al plan base 09-03); B0 requiere OK explícito (segunda cuenta paper); el resto se aprueba por fase.

---

## 0. Fundamentos transversales (leer antes de los tickets)

### F0.1 — Qué está congelado y qué no (la pregunta que Claude debe stress-testear)

La Regla 0 (ROADMAP:26-66) congela la **ruta de decisión**: señal congelada + contabilidad corregida vigente (commit `1466dcc`). De eso se derivan tres clases de archivo:

| Clase | Archivos | Regla durante el gate |
|---|---|---|
| **Núcleo congelado** | `signal_engine.py`, `paper_trading.py`, `backtest_engine.py`, `decision.py`, `adaptive_risk.py`, `conformal.py`, `regime_classifier.py` | Editar = reset del contador + alerta. Solo emergencia declarada por Boris. A4 lo enforcementa con hash. |
| **Ruta operativa** | `pipeline_daily_signal.py`, `daily_signal_pipeline.sh` | Editable DURANTE la Fase A (A1/A2/A3/A5 la extienden), **congelada al cierre de Fase A** con el manifiesto completo. Desde ahí, misma regla que el núcleo. |
| **Aditivo puro** | scripts nuevos, tablas DB NUEVAS, colectores, launchd, docs | Siempre editable — no toca la señal ni la contabilidad medida. |

**Decisión pre-declarada (fundamento)**: la racha oficial NO es retroactiva al 09-02. Arranca cuando el manifiesto completo (núcleo + pipeline post-Fase-A) se firma (~09-08). Los días 09-02→firma quedan `UNVERIFIED_C` en el contador (la condición (c) era inejecutable — D2). **Honestidad > optimismo**: una racha que empieza con días no verificables es exactamente el patrón de auto-engaño que el aparato estadístico del proyecto existe para impedir. Coste: ~5 días de racha. Beneficio: el 1/12 es inatacable.

### F0.2 — Por qué wrapper y no editar `paper_trading.py` (A1)

`reconcile_open_positions` (paper_trading.py:169-217) ya está correcto post-1466dcc: calcula pnl_r real `(cp−open)/open`, loguea a stderr cada fallback, devuelve el número de cierres. Lo que NO devuelve es el desglose `{cerradas, sin_explicar}` que la condición (c) necesita. Editarlo para devolver un dict = reset del contador por un cosmético. **El wrapper verifica (c) SIN tocar el método**: tras llamar `reconcile()`, re-consulta `ledger.open_orders()` vs `client.get_positions()` — huérfana residual = orden en ledger sin posición en broker. `(c) OK ⟺ huérfanas_residuales == 0 ∧ closes_del_día(exit_reason=RECONCILE) con close_fill_price no-null o fallback logueado`. La segunda cláusula se verifica leyendo el ledger (columna `close_fill_price`) + el propio stderr capturado.

### F0.3 — Asimetría del kill-switch (A3)

El STOP frena **entradas nuevas, nunca EXIT ni reconcile**. Fundamento: en un sistema paper sin señal validada, el riesgo direccional se acumula solo entrando; salir nunca empeora el estado de contabilidad, quedarse dentro sí (el incidente deAugosto: posiciones huérfanas acumulándose invisible). Días bajo STOP no cuentan como limpios por definición ("corriendo SIN interrupciones" — ROADMAP:33) — el kill-switch es caro a propósito: si fuera barato, se normalizaría y dejaría de ser señal.

### F0.4 — Por qué MDE es un hook del pre-registro y no un reporte aparte (B5)

El ledger ya demostró (pilotos regime matching, B5-NIVEL_DIOS) que cualquier control que esté FUERA del camino de aprobación se evita. Si el MDE es un reporte opcional, no corre; si es un paso de `reserve_trial()` que rechaza diseños sub-potentes con estado `INEJECUTABLE`, no hay evasión posible. `INEJECUTABLE` no consume slot Bonferroni (no corrió) pero SÍ queda registrado — el propio registro del diseño fallido es información.

### F0.5 — Gate-legalidad de cada fase (mapa contra la Regla 0)

Regla 0 permite en paralelo: "F0 de la auditoría (bugs), colector intradía I3, telemetría de ejecución I9, cerrar lo abierto antes de la regla".
- **A1-A9**: contabilidad/observabilidad que la PROPIA definición de día limpio exige + bugs D5/D6 + etiquetado honesto D1 → permitido (F0/I9).
- **B0 granja fantasma**: telemetría I9 amplificada — misma señal, cero hipótesis, cuenta separada. **Zona gris honesta**: produce 10× datos de costos, y su plan de muestreo fija horas/tamaños pero NO prueba nada sobre retornos. La marcamos como I9-extension; Boris la aprueba explícitamente por ser cuenta nueva.
- **B1/B2 colectores**: I3-equivalentes (acumulación, cero hipótesis) → permitido.
- **B3-B6 tooling**: infraestructura, no toca señal → permitido (B6 con golden obligatorio).
- **B7 point-in-time**: sourcing de dato, no hipótesis → permitido, pero OPCIONAL (postergable sin daño).
- **D1-D6**: hipótesis nuevas → SOLO post-gate, con pre-registro + MDE. No hay excepción.

---

## 1. FASE A — Cerrar el loop y blindar el gate (semana 09-03→09-08)

> Orden interno: **A1 → A2 → A4-parcial → A3 → A5 → A6 → A7 → A8 → A9 → A4-final (freeze) → arranque oficial de racha**. A1 antes que A2 porque el contador necesita la evidencia de reconcile; el freeze completo va ÚLTIMO porque A3/A5/A9 editan el pipeline.

### A1 — Reconciler en la corrida 22:10

**Qué**: `reconcile_step()` como paso final de la fase decide (22:10) en `pipeline_daily_signal.py`, DESPUÉS de que decide escriba su artefacto (el reconcile nunca bloquea la decisión). Implementación como wrapper (F0.2): llama `PaperTrader.reconcile_open_positions(exit_date=fecha_del_día)`, luego computa `huérfanas_residuales = |{señales en ledger.open_orders()} − {símbolos en client.get_positions()}|` y `closes_sin_precio = filas de HOY con exit_reason=RECONCILE ∧ close_fill_price IS NULL`. Escribe en `pipeline_state.json`: `reconcile: {closed: n, orphan_residual: n, closes_no_price: n}` y una línea en `pipeline_diario.log`: `reconcile closed=N residual=M noprice=K`.

**Fundamento de la verificación doble**: `reconcile()` devuelve solo `int`; confiar en el return sin re-consultar dejaría invisible una carrera (orden cerrada por broker entre el reconcile y el conteo). El doble chequeo cuesta 2 llamadas API y convierte (c) en evidencia mecánica.

**Archivos**: `backend/scripts/pipeline_daily_signal.py` (+ test). NO toca `paper_trading.py`.
**Aceptación**: (i) test integración con DB sembrada: 1 huérfana → closed=1, residual=0, pnl_r real ≠ 0.0; (ii) test con posición viva → residual=0 sin cerrar nada; (iii) noche real 22:10 con línea en state+log; (iv) reconcile repetido idempotente.
**Riesgo/mitigación**: rate-limit Alpaca en get_positions/last_trade → backoff simple; si el broker no responde, `residual=UNKNOWN` → el día NO cuenta como limpio (falla cerrada, nunca abierta).

### A2 — Contador de días limpios automático

**Qué**: `backend/scripts/clean_days_counter.py`, invocado al final de la corrida 22:10 (después de A1). Para cada día hábil D (con corrida del updater presente):
- (a) `pipeline_diario.log` del D contiene 3 bloques `pipeline_daily_signal end rc=0` (horarios 09:35/15:40/22:10 — la fase interna da igual: la definición del gate exige las 3 corridas con rc=0).
- (b) `data_updater.log` del D sin `PRECIOS: ERROR`.
- (c) `pipeline_state.json` del D: `reconcile.orphan_residual == 0 ∧ closes_no_price == 0` (o `residual == UNKNOWN` → no limpio).
Escribe `data/clean_days.json`: `{streak: n, total_clean: n, days: [{date, a, b, c, clean, why}]}`. Un día que falla NO rompe la racha retroactivamente (definición del gate) — `streak` se reinicia solo en el siguiente día limpio según la semántica "60 días limpios acumulados" vs "racha consecutiva": **decisión pre-declarada: el gate exige ≥60 limpios ACUMULADOS no necesariamente consecutivos** (la definición literal dice "≥60 días de pipeline corriendo SIN interrupciones" — interpretación conservadora que Claude debe revisar; ver Open Questions #1).

**Archivos**: script nuevo + hook de 5 líneas al final del paso 22:10. Zero edits en módulos congelados.
**Aceptación**: (i) fixture de logs sembrado: día con (b) rota → `clean:false, why:"b"`; (ii) día sin reconcile (pre-A1) → `UNVERIFIED_C`; (iii) 3 verdes → `clean:true`; (iv) idempotente por fecha (re-corrida no duplica).
**Fundamento del `why` por día**: el 1/12 no puede ser un número — tiene que ser una tabla auditable de 60+ días. Si Boris tiene que discutir un día, el JSON dice exactamente qué condición falló y a qué hora.

### A3 — Kill-switch pre-registrado

**Qué**: `scripts/kill_switch.py` (evalúa reglas) + check al inicio de `phase_enter` en el pipeline. Reglas pre-declaradas HOY (antes de que exista el problema — mismo estándar que la definición de día limpio):
- K1: drawdown paper > 10% del capital (vs `portfolio_snapshots` — tabla existente).
- K2: PnL realizado del día < −3σ vs σ del propio histórico paper.
- K3: fill-rate del día < 80% (órdenes submitidas vs filled — ejecución rota).
- K4: staleness de precios > 2 ruedas (updater muerto — patrón 15-22/08).
Acción: escribir `data/STOP_FILE` (contenido: regla gatillada, timestamp, evidencia). `phase_enter` lo lee → aborta entradas NUEVAS con rc=0 logueado (`STOP_FILE activo: K3`). EXIT/DECIDE/reconcile corren igual (F0.3). Notificación: `osascript display notification` como piso (Telegram pendiente de credenciales). Rearme: SOLO manual (borrar STOP_FILE con commit o comando explícito) — sin auto-rearme, un kill que se rearma solo es un kill que no existió.

**Archivos**: script nuevo + 3 líneas en `phase_enter`. No toca módulos congelados.
**Aceptación**: test por regla con fixtures (K1 con snapshot sembrado, K4 con cache stale forzada); test de que STOP_FILE activo bloquea ENTER y NO bloquea EXIT; día con STOP activo → contador lo marca no-limpio (integración con A2: el STOP se loguea en el pipeline → falta de las 3 corridas limpias o condición explícita).
**Fundamento de los umbrales**: 10% DD = 2× el peor mes histórico del baseline; −3σ diario = cola 0.13% bajo normal (conservador para colas gordas reales); fill<80% = nivel donde agosto mostró degradación; 2 ruedas = umbral del chip de staleness del dashboard (consistencia con producto existente). Claude puede discutir cada uno — son pre-registro, no verdad revelada.

### A4 — Hash-guard del motor (freeze en dos pasos)

**Qué**: `scripts/motor_manifest.py` — genera/verifica `scripts/motor_manifest.json` (sha256 por archivo del núcleo F0.1 + `pipeline_daily_signal.py` + `daily_signal_pipeline.sh`). La fase `health` (3×/día, ya existe) lo verifica. Diferencia: cambio no declarado → día no-limpio + notificación; cambio declarado (commit descriptivo + regenerar manifiesto) → el JSON del manifiesto registra `{file, old_hash, new_hash, commit, reason, resets_counter: true}` y **el contador se reinicia explícitamente** (A2 lee el manifiesto).
**Freeze en 2 pasos**: (1) al aprobar Fase A: manifiesto del NÚCLEO ya (esos 7 archivos no se tocan en Fase A salvo A6-bugfix-ver-below); (2) al cerrar Fase A: manifiesto COMPLETO (núcleo + pipeline). Racha oficial = firma del manifiesto completo.
**Excepción A6**: `backtest_engine.py` está en el núcleo PERO A6 (n_trials default) es un bugfix D5 aprobado — se ejecuta ANTES del freeze (2 pasos: edit + regen manifiesto declarado, contador ni arrancó oficialmente aún así que no hay reset real). Orden interno por eso: A6 va temprano.
**Aceptación**: (i) cambiar 1 byte de `signal_engine.py` en un checkout de test → health lo detecta; (ii) regenerar con commit declarado → manifiesto actualizado, `resets_counter` visible; (iii) health loguea `manifest: OK`.

### A5 — Telemetría de ejecución por orden

**Qué**: tabla NUEVA `execution_telemetry` en `fortress.db` (CREATE TABLE IF NOT EXISTS — aditivo, `signal_ledger` intacta): `(ts, phase, symbol, side, qty, decision_price, fill_price, slippage_bps, source)` donde `source ∈ {OFFICIAL, SHADOW_}` (el campo ya nace preparado para B0). El pipeline ya captura `fill` (líneas ~390-409) — extender el dict + INSERT (o logger a JSONL + loader diario — decidir según coste de escritura en corrida). Reporte: `scripts/execution_cost_report.py` semanal (launchd o paso del domingo): distribución de slippage por símbolo/qty/hora, n acumulado, comparación vs 0.10%/lado §33. **Regla pre-declarada**: con n≥30 fills OFFICIAL, el costo vigente para futuros backtests pasa de supuesto §33 a medido (ventana rolling 90d) — documentado en PLAN_MEJORA_MATEMATICA como §33.1 cuando pase.
**Fundamento**: agosto midió 156 fills en UN MES con el sistema normal. El costo es la variable que YA mató una señal (gap-reversion: bruto t=−0.20 → neto t=−11.53). Medirlo por símbolo/tamaño/hora convierte el supuesto más peligroso del proyecto en su serie de datos propia.
**Aceptación**: (i) orden sembrada con decision≠fill → fila con slippage_bps correcto; (ii) reporte sobre fixture produce distribución y n; (iii) cero writes a tablas existentes; (iv) suite completa verde.

### A6 — DSR n_trials del motor (bugfix D5)

**Qué**: `backtest_engine.py:651`: `DEFAULT_N_TRIALS = 5` → parámetro `n_trials: Optional[int] = None`; si None: cuenta entradas `signal_diagnosis` del `trial_registry` (RESERVED+COMPLETED, no EXPIRED). Callers explícitos no cambian. Tests que hoy dependen del default: se fijan `n_trials=5` explícito (documentando que el cambio de default no es cambio de matemática para ellos).
**Fundamento**: el motor deflaciona con N=5 cuando el proyecto lleva 51 trials — la misma clase de autoengaño que el aparato existe para impedir. La validación OOS (0.6077) ya usaba N correcto → NO se recalcula nada publicado.
**Aceptación**: test: default None deflaciona más que 5; DSR con N del ledger < DSR con N=5 (monotonía); suite completa.

### A7 — Enforcement técnico del gate en el ledger

**Qué**: en `trial_registry.py`: `GATE = {start: date(2026,9,2), end: date(2026,12,1), allow: ["bugfix_medicion"]}`; `reserve_trial()` rechaza pre-registros con fecha en ventana salvo `category == bugfix_medicion` Y nombre en la allow-list explícita (por ahora: `pbo39_lag0_fix` — el re-run open→close de A8). El rechazo cita la Regla 0 con el texto exacto. Campo `category` nuevo, opcional, default `research`.
**Fundamento**: los 3 pilotos regime matching demostraron que la disciplina documental falla exactamente cuando un agente cree que su piloto es "solo diagnóstico". El ledger ya es el enforcement del Bonferroni — extenderlo al gate es el mismo mecanismo, no uno nuevo. La allow-list es corta A PROPÓSITO: cada entrada la aprueba Boris en este documento.
**Aceptación**: (i) `reserve_trial(fecha=2026-10-15, category="research")` → TrialRegistryError citando Regla 0; (ii) `bugfix_medicion` con nombre no listado → rechazo; (iii) `pbo39_lag0_fix` → reserva OK pero SOLO con fecha post-gate; (iv) fecha post-2026-12-01 → libre.

### A8 — Nota lag-0 §39 + pre-registro post-gate

**Qué**: adenda en `PLAN_MEJORA_MATEMATICA.md §40.1`: "el PBO vigente 0.2358 usa entrada close[m-1]→close[m] (lag 0), inconsistente con el estándar T0.2 open→close; limitación declarada; re-run pre-aprobado (`pbo39_lag0_fix`, categoría bugfix_medicion) SOLO post-gate". No se re-corre nada durante el gate.
**Fundamento**: el veredicto actual del baseline descansa en §39; declarar la limitación ANTES del re-run es lo que separa corrección de p-hacking (si el re-run diera mejor PBO, tiene que quedar claro que la limitación se declaró antes de ver el resultado).

### A9 — Honestidad de la capa LLM (D1)

**Qué**: flag `GOVERNANCE_LLM_ENABLED` (Settings, default `false`). Rutas `/predict` y `/governance` lo respetan: si false, la tríada corre determinista sin llamar NIM y el payload incluye `"governance": {"llm": false, "rol": "descriptivo_no_conectado_a_pipeline"}`. El pipeline nunca la usó (D1 verificado) → cero efecto en el gate. El dashboard hereda el label del payload.
**Fundamento**: mantener 306 llamadas HTTP decorativas por request del universo es coste sin evidencia (`validate_triad_llm.py` nunca produjo justificación). Apagar ≠ borrar: el flag es reversible en una línea si algún día un trial valida la capa.

---

## 2. FASE B — Acumular donde está el edge (semanas 1-8, paralelo)

### B0 — Granja de ejecución fantasma (REQUIERE OK DE BORIS: cuenta paper 2)

**Qué**: `backend/scripts/shadow_executor.py` + launchd `com.fortresscore.shadow` versionado+cargado el mismo día (patrón auditoría 09-03). Plan de muestreo PRE-DECLARADO (el diseño fija horas/tamaños ANTES del primer fill — mismo estándar anti-p-hacking):
- Símbolos: los 30 de B1, rotación diaria fija por fecha (hash determinista — reproducible).
- Ventanas: 09:35, 12:00, 14:00, 15:30 (4 fills-ventana potencial).
- Tamaños: qty ∈ {1, 3, 10} (un tamaño por símbolo-ventana, asignado determinista).
- Cap diario: 40 órdenes (anti rate-limit y anti ruido).
- Cuenta: paper Alpaca #2, credenciales `ALPACA_PAPER2_*` en `.env` (patrón settings con fallback env, como fix `e78cd48`).
- Señal: NINGUNA — órdenes market de tamaño fijo sin decisión (compra y venta intra-día para medir round-trip: compra 09:35 → venta 15:30 del MISMO símbolo-qty cuando el cap lo permite). NO evalúa retornos, NO toca el pipeline, NO escribe `signal_ledger`.
- Persistencia: TODO a `execution_telemetry` con `source='SHADOW_' + ventana`.
**Verificación A0 previa** (primer paso del ticket): confirmar contra la API paper de Alpaca: equity default (¿100k?), si aplica PDT a paper (no debería con >25k), límites de rate/órdenes. Si PDT aplicara: cap ajustado a <3 day-trades/5 días (≈2/día) y el plan de muestreo se re-declara ANTES del primer fill.
**Fundamento del valor**: n=156 fills/mes oficial → 600-1800/mes shadow. Curva de slippage por hora/tamaño que D3 (intradía) necesita desde el día 1, features de fill para D1 (meta-labeling), y el modelo de costos de D2 (opciones: el spread de la opción es el costo dominante — medir spreads equity primero es el calentamiento metodológico).
**Fundamento del firewall**: cuenta separada = el ledger oficial del gate NO puede contaminarse (un fill SHADOW en `signal_ledger` invalidaría la contabilidad del gate). El tag `SHADOW_` y el filtro por `source` en reportes A5 son defense-in-depth. Sin cuenta separada, B0 NO se construye (un wrapper elegante NO basta — el riesgo es existencial para el gate).
**Aceptación**: (i) 3 días corridos con 30-40 fills SHADOW_/día en telemetría; (ii) `signal_ledger` SIN filas SHADOW (test de fuego); (iii) contador de días limpios SIN cambio con shadow corriendo (prueba de aislamiento); (iv) reporte semanal A5 separa OFFICIAL vs SHADOW_.

### B1 — Colector intradía 7→30

**Qué**: extender `collect_intraday_1min.py --symbols` (ya soporta CSV — verificado `:135`): lista staged 30 = SPY, QQQ + 28 más líquidos del universo 102 (por ADV del propio OHLCV diario — determinista y pre-declarable). Monitor de cuota en el log (cuenta las llamadas por corrida). Rollback = parámetro.
**Fundamento**: 30 símbolos ≈ cross-section mínima para un rank-IC intradía con NW (con 7, el pooled es la única opción — el error que el proyecto ya corrigió en EOD). Coste disco: ~4MB/sem (auditoría 09-03).

### B2 — Colector de superficie IV (familia opciones)

**Qué**: `backend/scripts/collect_iv_surface.py` + launchd `com.fortresscore.ivcollector` a las **22:50** (hueco verificado del launchd: fundamentals_screen 22:30 termina ~22:45; backupdatos 23:00 — 10 min de oxígeno). Snapshot post-cierre por símbolo (los 30 de B1): cadenas yfinance (todas las expiries ≤ 2 años), por strike: last, IV, OI, volume, bid, ask + spot subyacente → parquet diario `data/cache/iv_surface/<date>_<sym>.parquet` (~2-3MB/día total). Retry 1× (yfinance es la fuente más frágil — regla de reintentos mínimos), fallo logueado estilo `PRECIOS: ERROR` (patrón data_updater para que A2/b-visible lo detecte si algún día se integra al latido).
**Fundamento**: sin superficie acumulada, la familia D2 (VRP/GEX/PEAD-options) no tiene NI el primer día de datos cuando el gate abra. El colector no computa NADA (ni IV implícita propia, ni surface fitting) — solo snapshots crudos: cualquier modelo se decide después, con los datos ya ahí. "El caño antes del agua" es literal: 12 semanas de acumulación al 1/12.

### B3 — Feature store versionado (I6)

**Qué**: `build_factor_panel` → emite `data/panels/factor_panel_<sha12>.parquet` + `manifest.json` (columnas, universo, rango fechas, hash, código que lo generó con commit). Consumo: los scripts nuevos POR VERSIÓN (el manifiesto es el índice). Migración de utilidades copiadas: los 3 más duplicados primero (DSR, bootstrap, load_symbol → importar de `app/core/`), un commit por script migrado, cero big-bang.
**Aceptación**: un script migrado produce output BIT-IDÉNTICO al original (golden del artefacto) — si difiere, la utilidad copiada había divergido y se documenta la divergencia ANTES de adoptar el core.

### B4 — Holdout sellado

**Qué**: corte `2025-09-01` registrado en el ledger como metadata (`holdout_from`). `trial_registry` marca con warning cualquier pre-registro cuya ventana de datos cruce el corte (rechazo en D-fase post-gate; en B-fase solo warning porque los diagnósticos capa-1 están permitidos pero deben excluir el holdout para que valga algo). El MDE (B5) computa potencia solo con pre-corte.
**Fundamento del corte**: 2025-09-01 deja ~6 años de desarrollo y ~12 meses de holdout (≈250 ruedas — suficiente para DSR por ventanas de 3). Post-gate, el paper trading prospectivo ES el segundo OOS (el holdout protegido es el primero).

### B5 — MDE ex-ante (I1)

**Qué**: `app/core/mde.py` (función pura, testeada contra tabla de potencia conocida) + hook en `reserve_trial()`: dado {n_symbols, T_dates, horizon, alpha_corregido}, computa IC mínimo detectable con potencia 0.8. Si `MDE > 0.10` (umbral pre-declarado de "efecto plausible" — la cola alta de los efectos académicos reales) → estado `INEJECUTABLE` (nuevo status: registrado, no consume slot, cita el MDE). El pre-registro DEBE incluir n_symbols/T/horizonte — sin eso el hook no firma.
**Fundamento**: cada "NO_CUMPLE por subpotencia" publicado como refutación es información falsa en el ledger. El proyecto ya lo admitió (§27/§48) — esto lo vuelve mecánico. El umbral 0.10 es discutible (Open Question #3): más alto mata trials legítimos de efectos chicos, más bajo re-permite el teatro.

### B6 — Contrato de señal única (con golden obligatorio)

**Qué**: módulo `app/core/frozen_signal.py` que expone LA definición congelada (la que hoy vive triplicada en signal_engine/validacion_oos/pipeline). Los 3 consumidores migran UNO POR UNO, cada migración con golden: señal del consumidor viejo vs módulo nuevo BIT-IDÉNTICA sobre universo completo × 60 días corridos × 3 regímenes. Un solo valor difiere → rollback del paso, no adopción.
**Orden**: primero el pipeline (el que el gate congela — migrarlo ANTES del freeze final de A4), después validacion_oos (script, sin presión de gate).
**Fundamento**: la triplicación es el riesgo de "dos motores" (B1-NIVEL_DIOS) en miniatura — la señal medida y la señal validada podrían divergir silenciosamente. El golden convierte la consolidación en la operación más segura del plan, no la más riesgosa.

### B7 — (Opcional) Universo point-in-time

Sourcing de constituyentes históricos (SHARP/CRSP son pagos; alternativas: listings de exchange vía SEC, Wikipedia de cambios de índice con validación). Solo columna `membership_date` en el panel B3. **Si el sourcing no es verificable ≥95% de cobertura por año, NO se integra** — un point-in-time a medias es peor que el sesgo declarado.

---

## 3. FASE C — Evaluación (2026-12-01 o contador ≥60)

`scripts/gate_report.py`: junta `clean_days.json` (racha + tabla), `monthly_report` del período, DSR por ventanas con N_eff del ledger, telemetría A5 resumida (costo medido vs supuesto §33), manifest status (cuántos resets declarados hubo). Veredicto contra el criterio pre-declarado (DSR≥0.90 en ≥2/3 ventanas). La decisión (a) mantenimiento / (b) pivotar / (c) laboratorio está pre-declarada en ROADMAP:52-56 — el reporte la ejecuta, no la re-abre.

---

## 4. FASE D — Familias post-gate (orden por Sharpe esperado/esfuerzo)

| # | Familia | Por qué este orden | Dependencia construida en gate |
|---|---|---|---|
| D1 | Meta-labeling (I5) | Efecto necesario MENOR (filtrar trades vs generar alpha) — la única vía realista con n chico | A5 telemetría como features + labels paper acumulándose + M1 ya construido |
| D2 | Opciones: VRP → GEX → PEAD-options | Familia ausente entera; mejor Sharpe histórico/unidad de capital accesible | B2 superficie IV (12 semanas) + B0 spreads medidos |
| D4 | Shrinkage James-Stein per-ticker (I4) | Arregla w_mom 0.6642 (heterogeneidad medida) | MDE verificará si n per-ticker alcanza |
| D6 | Neutralización RMT (8 factores ya validados) | Piezas ya construidas, cero research nuevo | Solo integración + trial |
| D3 | Intradía genuina | Requiere costos intradía REALES desde el día 1 | B1 (30 símb × 12 sem) + B0 curva hora/tamaño |
| D5 | Multivariada (ridge/elastic-net) | SOLO si D1 funciona — regresión sobre ruido con n chico es el error que el ledger ya documentó | B3 feature store + B4 holdout + B5 MDE |

Cada familia abre con pre-registro completo (umbral, corrección, éxito) + MDE ejecutable + holdout respetado — o no abre. Sin excepciones (A7 lo enforcementa).

---

## 5. Open Questions para conversar con Claude (decisiones genuinas)

1. **Semántica de los 60 días**: ¿"60 limpios acumulados" o "60 consecutivos"? La definición literal del ROADMAP dice "sin interrupciones" (consecutivos); yo pre-declaré acumulados en A2 porque una sola tarde de Alpaca caída resetearía 59 días de racha en la lectura estricta. **Mi posición**: acumulados + reporte de la peor racha consecutiva como contexto. Claude: ¿lee la Regla 0 igual?
2. **Freeze del pipeline**: yo congelo `pipeline_daily_signal.py` al cierre de Fase A (post-A1/A2/A3/A5/A9). Alternativa: congelarlo YA y despachar los pasos nuevos como sub-scripts invocados por cron separado (el pipeline intacto). Más limpio para el hash, más frágil para el orden (reconcile DEBE correr tras decide, no en paralelo). **Mi posición**: ediciones A dentro del pipeline + freeze final único.
3. **Umbral MDE 0.10**: ¿mata demasiado? Efectos académicos: momentum ~0.03-0.08, PEAD alto pero decay rápido. **Mi posición**: 0.10 default + override explícito de Boris por trial con justificación (el override queda registrado — es su dinero y su gate).
4. **B0 sin cuenta separada es NO-GO** (mi línea dura). Alternativa de Claude posible: misma cuenta con tag y filtros estrictos. Rechazo: un solo bug de filtrado contamina el gate — el downside es asimétrico.
5. **A9 apagar LLM vs mantener**: el costo es ~decenas de llamadas/día (no crítico). ¿Vale el flag o mejor quitar la capa del dashboard? **Mi posición**: flag off (reversible, documentado) — borrar es irreversible y un trial futuro podría validarla.
6. **B7 point-in-time**: ¿ahora o post-gate? Mi posición: post-gate salvo que el sourcing gratuito verifique ≥95% — es el ítem con peor ratio valor/esfuerzo de la Fase B.

## 6. Cronograma consolidado

```
Sem 1 (09-03→09-08):  A6 → A1 → A2 → A3 → A5 → A9 → A7 → A8 → A4(freeze completo) → RACHA OFICIAL
Sem 1-2 (con OK B0):  cuenta paper2 + shadow_executor + verificación A0 de límites
Sem 2-3:              B1 (7→30) + B2 (IV 22:50) + B3 (primeras migraciones)
Sem 3-8:              B4, B5, B6 (golden), B7(opcional) — B0 acumulando fills
2026-12-01:           C gate_report (o fecha por contador ≥60)
Post-gate:            D1 → D2/D4/D6 → D3 → D5
```

## 7. Criterios de éxito por fase (verificables)

- **A**: racha oficial ≥1 día con evidencia a/b/c en JSON; kill-switch pasa 4 tests de regla; 1 byte en señal → detectado; telemetría con slippage_bps real; pre-registro durante gate rechazado; `pbo39_lag0_fix` reservado post-gate.
- **B**: 30 parquets intradía/rueda; `iv_surface/` ≥30 días al 1/12; B0 ≥600 fills SHADOW_/mes con `signal_ledger` intacta; un script migrado golden-idéntico; MDE rechaza un diseño sub-potente de prueba; holdout registrado.
- **C**: `gate_report.py` produce la tabla de 60 días + DSR por ventanas + costo medido vs supuesto; decisión pre-declarada ejecutada.
- **D**: cada familia con pre-registro + MDE + holdout — cero excepciones.

## 8. Presupuesto de esfuerzo (sesiones de agente)

| Fase | Sesiones | Nota |
|---|---|---|
| A completa | 6-8 | A1:1, A2:1, A3:1.5, A5:1, A6+A8:0.5, A7:0.5, A9:0.5, A4:0.5, tests integración:1 |
| B0 | 1.5-2 | + cuenta (10 min Boris) |
| B1+B2 | 1.5 | |
| B3-B6 | 4-5 | repartidas semanas 3-8 |
| C | 1 | |
| D | post-gate | fuera de presupuesto del gate |

**Total pre-gate: ~13-17 sesiones de agente.** Sin tocar una sola línea de hipótesis.
