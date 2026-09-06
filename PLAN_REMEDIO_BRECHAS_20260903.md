# PLAN DE REMEDIO DE BRECHAS — fortress_core

**Fecha**: 2026-09-03 · **Autor**: Kilo Code · **Baseline**: `AUDITORIA_INTEGRAL_SISTEMA_20260903.md` (D1-D12) + `AUDITORIA_NIVEL_DIOS_20260902.md` (B0-B7, F0-F3, I1-I10) + respuesta "capacidad de detección" (4 brechas).

**Objetivo**: remediar por completo las 4 brechas de capacidad declaradas — (1) ciego a ineficiencias de tamaño realista (subpotencia), (2) sin motor intradía, (3) sin patrones multivariados, (4) incapaz de distinguir patrón de ineficiencia capturable (loop de ejecución abierto) — más la familia ausente (opciones), respetando el gate de 90 días.

**Restricción rectora**: el gate corre sobre un sistema congelado en su ruta de decisión. Todo lo que se construye durante el gate es observabilidad, contabilidad que la propia definición del gate exige, acumulación de datos, o tooling pre-trial. Nada que altere la señal medida. Cambios a `paper_trading.py` posteriores al arranque del contador: solo emergencias declaradas (resetean el contador explícitamente).

---

## 0. Principio de urgencia (leer primero)

El contador de días limpios arrancó el 2026-09-02 con 2 condiciones verificables (a: pipeline rc=0; b: updater sin PRECIOS: ERROR) y **una inejecutable (c: reconcile sin huérfanas — D2, sin caller productivo)**. Cada día que pasa:

- o cuenta sin verificar (c) → racha potencialmente contaminada, descubierta el 1/12 (peor caso),
- o la evaluación se corre hasta completar 60 días REALES → cada semana de retraso en Fase A desplaza la fecha de evaluación una semana.

**Fase A es esta semana.** El 1/12 no es fecha fija — es `max(2026-12-01, arranque_contador + 60 días limpios verificados)`.

---

## FASE A — Cerrar el loop y blindar el gate (hoy → ~09-08; ~4-6 sesiones de agente; 100% permitido durante el gate)

### A0. Harness de integridad del cache de datos (yfinance) — PRECONDICIÓN, bloquea A1
- **Contexto**: se encontró contaminación cruzada en el cache de yfinance — `data_ingestion.py` tiene diseño append-only (solo pide desde `last_date` en adelante, nunca re-verifica ni repara filas viejas) — y en 3 clusters (24-26/ago, 31/ago, 1/sep 2026) al menos 38 barras completas de OTROS símbolos quedaron congeladas en 29 parquets (ej.: KO tenía la barra exacta de CRM; CMCSA tenía un +622.9% falso que en realidad era la barra de PM). Ya fue saneado a mano (re-descarga completa de los 102 símbolos con `auto_adjust=True`, verificado sin duplicados restantes) pero el diseño que lo permitió sigue intacto — puede volver a pasar en cualquier corrida futura. También hay 64 huecos de fechas faltantes en 57/102 símbolos (ej. AKAM/AMAT/AMGN faltan 2026-08-28) que el diseño append-only nunca repara porque no re-pide fechas intermedias ya pasadas. Especificación derivada de `COMPARACION_FUENTES_DATOS.md` §10/§10.3 (medida, no de opinión) — no reinventar, ese documento es la referencia.
- **Qué** (4 partes, la 4 diferida):
  1. Validador de sanidad de retornos: flag de cualquier |retorno diario| > umbral por clase de símbolo (large-cap 15-20%), barato (segundos), corre en cada actualización de cache. Habría atrapado las 38 barras el día que entraron (24-ago), antes de congelarse.
  2. Reconciliación cache vs. descarga fresca del MISMO yfinance (muestra diaria rotativa o full): (a) filas cuyo OHLCV matchea otro símbolo → bloqueo + re-descarga del archivo completo; (b) mosaico (plateaus del ratio) → re-descarga completa del archivo; (c) huecos intermedios → re-descarga del tramo. Hoy nada de esto existe: el refresh solo mira el extremo derecho (`last_date`).
  3. Freeze de snapshot por trial: el pre-registro de cada trial registra el hash del cache que consume (o copia congelada a un directorio del trial) — única defensa contra el reajuste retroactivo para reproducibilidad; hoy no existe ni git ni backup de los parquets.
  4. **Diferido, solo pre-registrado en A0, no se implementa ahora**: cross-check Finnhub↔FMP cuando FMP produzca datos. Hoy no es implementable (0 datos, `calls_used: 0`/`failed: 102`) y hay un desborde de cuota estructural (universo 102 × 5 endpoints = 510 calls > 250/día del free tier) que debe resolverse antes (universo por mitades en días alternos, o cache 90-días con refresh incremental) — junto con validar el `FIELD_MAP` de Finnhub con `verify_finnhub_mapping.py` (existe, nunca corrió).
- **Dónde**: `backend/app/core/data_ingestion.py` (el diseño append-only a corregir/envolver), nuevo módulo de validación (integridad de cache), enganchado en la misma ruta de actualización diaria que hoy solo pide `last_date` en adelante.
- **Verificación**: test que siembra una fila con OHLCV de otro símbolo → detectada y dispara re-descarga; test que siembra un salto de retorno >20% en un large-cap → flag generado; test que siembra un hueco de fecha intermedio → detectado y re-descargado el tramo (no solo el extremo derecho); corrida real sobre los 102 símbolos confirmando 0 contaminaciones y 0 huecos restantes, con el harness quedando activo en cada actualización subsiguiente (no una pasada única).
- **Remedia**: el defecto de diseño (no yfinance en sí) que permitió 2+ semanas de historia contaminada sin detección, verificado independientemente (ver `COMPARACION_FUENTES_DATOS.md` §3/§4/§6/§9 — ningún veredicto del ledger quedó contaminado por suerte calendárica, pero el próximo trial que use el cache completo ya no la tiene). Bloquea a **A1**: el reconciler de A1 y el contador de días limpios de A2 no son confiables si el cache de precios que alimenta el pipeline puede contener barras cruzadas o huecos sin detectar.
- **Riesgo**: nulo/bajo — es observabilidad + reparación dirigida del cache, no cambia la lógica de decisión del motor (respeta la restricción del gate: solo contabilidad/tooling pre-trial).
- **Esfuerzo**: 1.5-2 sesiones (partes 1-3; la parte 4 queda pre-registrada, no ejecutada, hasta resolver la cuota FMP).

### A1. Reconciler dentro del pipeline — hace verificable la condición (c)
- **Qué**: invocar `PaperTrader.reconcile_open_positions()` en la fase 22:10 (post-cierre, idempotente, solo órdenes huérfanas) y registrar `reconcile: {orphan_closed: n, unexplained: n}` en `pipeline_state.json` + línea en `pipeline_diario.log`.
- **Dónde**: `backend/scripts/pipeline_daily_signal.py` (fase DECIDE/22:10, después del cierre de órdenes), consumiendo `backend/app/core/paper_trading.py:169`.
- **Verificación**: test de integración con DB sembrada (1 huérfana → cerrada con pnl_r real ≠ 0.0, línea presente en state/log); corrida real una noche; `launchctl` intacto.
- **Remedia**: D2. **Riesgo**: nulo (la definición del gate ya lo exige — sin esto el gate no es evaluable). **Esfuerzo**: 1 sesión.

### A2. Contador de días limpios AUTOMÁTICO — elimina el contador manual
- **Qué**: `backend/scripts/clean_days_counter.py` — parsea (a) las 3 corridas del día con `rc=0` en `pipeline_diario.log`, (b) ausencia de `PRECIOS: ERROR` en `data_updater.log` del día, (c) `reconcile.unexplained == 0` en `pipeline_state.json`. Escribe `data/clean_days.json` (racha + tabla por día con evidencia de cada condición). Corre al final de la fase 22:10. Día hábil = día de semana con corrida del updater presente.
- **Verificación**: siembra un día con cada condición rota en logs de test → el día NO cuenta; el JSON muestra el porqué. Semana retroactiva desde el arranque real del reconciler (días previos con (c) no verificada quedan marcados `UNVERIFIED_C` — decisión pre-declarada de Boris al aprobar este plan).
- **Remedia**: amenaza #4 (contador manual) + hace el 1/12 mecánico. **Esfuerzo**: 1 sesión.

### A3. Kill-switch por divergencia — pre-registrado HOY, antes de que haga falta
- **Qué**: reglas pre-declaradas (mismo estándar que la definición de día limpio, escrita antes de necesitarla): STOP si (i) drawdown paper > 10% del capital, (ii) PnL realizado diario < −3σ vs esperado, (iii) fill rate < 80% en órdenes del día (ejecución rota), (iv) staleness de precios > 2 ruedas (updater muerto — patrón 15-22/08). Acción: escribe `data/STOP_FILE` que la fase ENTER respeta (pausa entradas NUEVAS; nunca bloquea EXIT ni reconcile), notificación macOS (`osascript`) como piso sin Telegram, rearme solo manual. Días bajo STOP no cuentan como limpios (interrupción, por definición del gate).
- **Dónde**: `pipeline_daily_signal.py` (check al inicio de ENTER) + `scripts/kill_switch.py` (reglas + evaluación, testeado con fixtures de cada condición).
- **Remedia**: D3. **Riesgo**: bajo — solo agrega capacidad de frenar. **Esfuerzo**: 1-1.5 sesiones.

### A4. Hash-guard del motor — congelamiento verificable
- **Qué**: manifiesto `scripts/motor_manifest.json` (sha256 de `signal_engine.py`, `paper_trading.py`, `backtest_engine.py`, `decision.py`, `adaptive_risk.py`, `conformal.py`, `regime_classifier.py`) firmado por el commit que arranca el contador limpio. La fase `health` (3×/día) verifica el manifiesto: cambio no declarado = día NO limpio + alerta. Cambios declarados (bugfix con commit descriptivo) actualizan el manifiesto y el contador REINICIA explícitamente — visible, nunca silencioso.
- **Remedia**: amenaza #3 (reset de contabilidad vigente sin detector). **Esfuerzo**: 0.5 sesión.

### A5. Telemetría de ejecución por orden (I9) — el libro de costos propio
- **Qué**: por cada orden del pipeline registrar `decision_price`, `fill_price`, `slippage_implicit = (fill−decision)/decision`, side, qty, símbolo, fase → tabla `execution_telemetry` en `fortress.db`. Reporte semanal (`scripts/execution_cost_report.py`): distribución de slippage por símbolo/tamaño vs el 0.10%/lado asumido §33. Después de N≥30 fills: el costo vigente pasa de supuesto a medido.
- **Dónde**: `pipeline_daily_signal.py` en el mismo lugar donde ya captura `fill` (líneas 390-409) — extender el dict + INSERT.
- **Remedia**: brecha #4 (ejecución medida). **Esfuerzo**: 1 sesión.

### A6. Fix DSR n_trials del motor (D5) — nivel bug
- **Qué**: `backtest_engine.py:651` `DEFAULT_N_TRIALS=5` → `n_trials: Optional[int] = None`; si None, cuenta los trials del ledger (`signal_diagnosis` reales: 29+) en vez de 5. Callers explícitos no cambian.
- **Verificación**: test que el DSR default deflaciona con N del ledger; el 0.6077 de la validación OOS NO se recalcula (usó N correcto — solo el default del motor sub-deflacionaba).
- **Esfuerzo**: 0.5 sesión.

### A7. Enforcement técnico del gate — el ledger obedece la Regla 0
- **Qué**: `trial_registry.py` rechaza pre-registros con fecha dentro de la ventana del gate salvo categoría allow-list explícita (`bugfix`/`infraestructura`), con mensaje que cite la Regla 0 del ROADMAP. Un agente que intente un trial "inocente" durante el gate choca contra código, no contra documento.
- **Remedia**: amenaza #2 (pilotos sin pre-registro durante el gate — ya pasó una vez). **Esfuerzo**: 0.5 sesión.

### A8. PBO §39 lag-0 (D6) — documentar ahora, re-corregir post-gate
- **Qué**: nota en `PLAN_MEJORA_MATEMATICA.md §40.1` declarando la entrada lag-0 (close[m-1]→close[m]) como limitación del vigente 0.2358; pre-registro listo (categoría `bugfix` post-gate) del re-run con open(m)→close(m). NO se re-corre durante el gate — es medición de hipótesis existente, no bug de producción.
- **Esfuerzo**: 0.25 sesión.

### A9. Honestidad de la capa multi-agente (D1) — etiquetar, no desconectar
- **Qué**: flag `GOVERNANCE_LLM_ENABLED` (default `false`) en la ruta `/predict`/`/governance` → el dashboard muestra gobernanza como "descriptiva — no conectada a decisiones del pipeline" y no quema llamadas NIM decorativas. El pipeline no la usa (verificado D1) — nada del gate cambia.
- **Esfuerzo**: 0.5 sesión.

**Salida de Fase A**: gate evaluable (a+b+c verificables por máquina), contador automático corriendo, kill-switch armado, motor congelado con hash, telemetría de fills acumulando. La racha limpia EMPIEZA a contar de verdad.

---

## FASE B — Acumular donde estará el edge (semanas 1-8, paralela al gate; solo datos, tooling y versionado — cero hipótesis)

### B0. Granja de ejecución fantasma (PROPUESTO 2026-09-03 por Kilo — requiere OK de Boris: segunda cuenta paper Alpaca) — el dato que nadie está acumulando
- **Qué**: `backend/scripts/shadow_executor.py` — misma señal congelada del pipeline, **cero variantes de señal, cero evaluación de retornos**, cuenta paper Alpaca SEPARADA, órdenes chicas fijas (qty 1/3/10) muestreadas a horas distintas del día (09:35, 12:00, 14:00, 15:30) sobre los 30 símbolos de B1. Todo taggeado `SHADOW_` en client_order_id. Mide por orden: fill vs decision price, latencia de fill, fills parciales, spread proxy (quotes IEX), hora del día, tamaño.
- **Por qué es lo más palanca por dólar**: agosto midió n=156 fills en total; la granja produce **600-1800 fills reales para el 1/12** — el libro de costos propio (A5) pasa de anecdótico a estadística, con curva de costo por hora/tamaño que D3 (intradía) necesita DESDE el día 1, features de fill real para el meta-labeling (D1) y el modelo de costos que la familia opciones (D2) también requerirá. Convierte 60 días de gate muerto en el dataset más escaso del proyecto: la microestructura de nuestra propia ejecución.
- **Gate-legal**: es telemetría de ejecución I9 amplificada — plomería, no hipótesis; el Regla 0 la permite explícitamente ("telemetría de ejecución I9"). La cuenta separada es el detalle estructural que impide contaminar el ledger oficial del gate.
- **Verificación**: los reportes de A5 separan oficial vs SHADOW_ por tag; ningún flujo del pipeline oficial lee la cuenta shadow; kills del shadow executor no tocan el pipeline.
- **Esfuerzo**: 1-2 sesiones + la cuenta (10 min).

### B0.bis (secundarias, una línea)
- **Validación cruzada de precios yfinance↔Alpaca al ingerir**: `check_data_freshness.sh` verifica antigüedad, no corrección (auditado 09-03: solo age/mtime); un bad tick silencioso envenena todo el aparato estadístico aguas abajo. Cross-check diario del close, flag divergencia >0.5%, alerta en el latido. ~0.5 sesión.
- **Fund-the-moat**: el screening AAI ya produce artefactos diarios solo; si monetiza, financia los datos que son el techo real de D2/D3 (constituyentes point-in-time, data de opciones). Ingreso no correlacionado mientras el gate corre. Sin acción técnica ahora — decisión de producto de Boris a post-gate.

### B1. Colector intradía 7 → 30 líquidos (etapas 15 → 30)
- **Qué**: extender `collect_intraday_1min.py` con lista staged (SPY, QQQ + 28 de mayor liquidez del universo 102), monitor de rate/cuota Alpaca en el propio log, rollback trivial (lista es parámetro). Al ritmo medido (auditoría 09-03): ~4MB/sem a 30 símbolos — despreciable.
- **Por qué**: las dos señales con t>10 del proyecto son intradía; sin cross-section no hay trial futuro posible. 30 símbolos dan la potencia mínima para un diseño intradía pre-registrable post-gate.
- **Esfuerzo**: 0.5 sesión + vigilancia 1 semana.

### B2. Colector de superficie IV diaria (familia opciones — el caño antes del agua)
- **Qué**: `backend/scripts/collect_iv_surface.py` — post-cierre (22:35, tras fundamentals_screen), snapshot de cadenas yfinance options por símbolo (los mismos 30 de B1): strikes, expiry, last, IV, OI, volume, spot → parquet diario `data/cache/iv_surface/`. Estimación: ~2-3MB/día a 30 símbolos (~15MB/sem — dentro del presupuesto de disco). launchd `com.fortresscore.ivcollector` versionado (patrón de la auditoría 09-03: commiteado Y cargado el mismo día).
- **Por qué**: sin superficie de IV acumulada NO EXISTE la familia opciones (VRP, GEX, PEAD-vía-options) — con ella acumulando desde hoy, el primer trial post-gate tiene historial propio en vez de empezar de cero. Es I3-equivalente (acumulación de datos, cero hipótesis) — doctrina "construir el caño antes de que pase el agua".
- **Esfuerzo**: 1-1.5 sesiones.

### B3. Feature store versionado (I6) — mata la divergencia silenciosa
- **Qué**: `build_factor_panel` emite dataset con hash de versión (`data/panels/factor_panel_<hash>.parquet`); los scripts consumen por versión. Migración gradual de las 97 utilidades copiadas empezando por DSR/bootstrap/load_symbol (importar de core, no copiar). No big-bang: cada script migrado en su propio commit.
- **Remedia**: D9/B6-NIVEL_DIOS. **Esfuerzo**: 2-3 sesiones repartidas.

### B4. Holdout sellado (I7) — lo que queda de histórico 2019-2026 se protege
- **Qué**: corte 2025-09-01 registrado en el ledger como SAGRADO; `trial_registry` etiqueta cualquier pre-registro que toque datos post-corte (excepción explícita: paper trading prospectivo, que ES el OOS verdadero). El MDE (B5) computa potencia solo con pre-corte.
- **Remedia**: snooping ex-ante (B3-NIVEL_DIOS). **Esfuerzo**: 0.5 sesión.

### B5. Gate de potencia ex-ante MDE (I1) — fin de la refutación-teatro
- **Qué**: `backend/scripts/mde_power.py` — dado el diseño (n símbolos, T fechas, horizonte, autocorrelación estimada), computa el IC mínimo detectable a α corregido. Hook en el pre-registro: MDE > efecto plausible (default 0.10) → estado `INEJECUTABLE`, no consume slot ni produce "refutación". Instrumentación de medición, no investigación: no testea nada, evita tests perdidos.
- **Remedia**: brecha #1 en su raíz procesal — el sistema deja de CONFUNDIR "no pude detectarlo" con "no existe".
- **Esfuerzo**: 1 sesión.

### B6. Contrato de señal única — con equivalencia dorada
- **Qué**: un único módulo congelado para la definición de señal (hoy duplicada en signal_engine, validacion_oos, pipeline_daily_signal); los 3 consumidores importan de él. Condición innegociable: golden tests que prueban señal bit-idéntica pre/post refactor sobre el universo completo, 60 días corridos — si un solo valor difiere, rollback. Solo con golden 100% se despliega (no cambia la señal medida; el hash-guard A4 lo certifica).
- **Remedia**: D9/B6 raíz. **Esfuerzo**: 1.5 sesiones.

### B7. (Opcional, dato barato) Universo point-in-time
- **Qué**: constituyentes históricos S&P/Russell accesibles (fuente gratuita o de bajo costo) → columna `membership_date` en el panel; los backtests dejan de retroaplicar el universo de HOY a 2019.
- **Remedia**: sesgo de supervivencia (B3-NIVEL_DIOS). **Esfuerzo**: 1-2 sesiones + sourcing del dato.

---

## FASE C — Evaluación del gate (2026-12-01, o contador ≥ 60)

C1. El 1/12 (o cuando `clean_days.json` marque ≥60): `monthly_report` de la racha + telemetría A5 + veredicto contra el criterio **re-especificado por Boris el 2026-09-05**. Fundamento: `ANALISIS_MDE_GATE_DICIEMBRE_2026.md §6 opción 1` (el análisis vive en la rama `bjofrea-ctrl/fundamentales-automatizado`, commit `c602a30`, y llega al tronco con B5). El texto original de este ítem pedía `DSR≥0.90 en ≥2/3 ventanas` **sobre el paper de diciembre**; eso es exactamente lo que se corrige, porque 60 días con horizonte semanal piden un SR anual ~6.7-8.5 contra un efecto plausible de 0.10: casi imposible por construcción.

- **DSR≥0.90 en ≥2/3 ventanas se evalúa y mantiene válido SOLO sobre las ventanas OOS históricas pre-corte (W1/W2/W3, ~500 días hábiles c/u)** — es el criterio que siempre se usó ahí y sigue vigente sin cambios.
- **El gate de diciembre verifica el TUBO, no el edge**: **(a)** racha de días limpios ininterrumpida (condiciones a+b+c ya definidas), **(b)** `fill rate`/slippage medido (A5) dentro de lo esperado, **(c)** coherencia paper-vs-señal (las señales que debieron dispararse, se dispararon; sin discrepancias no explicadas).
- **Explícito**: esto **NO** es una segunda prueba estadística de edge — es un chequeo operativo de que el tubo corrió limpio. La prueba de edge sigue siendo la de las ventanas históricas.
- **Trabajo paralelo**: se sigue acumulando data (intradía B1, IV B2) con la aspiración declarada de alcanzar DSR≥0.90 también sobre ventanas de paper más largas, sin que eso bloquee el gate de diciembre.

El `monthly_report` y el DSR por ventanas con N_eff del ledger **se siguen calculando y reportando** como evidencia descriptiva del período; lo que ya no constituyen es la condición de paso de diciembre. La decisión (a) mantenimiento / (b) pivotar / (c) laboratorio sigue pre-declarada en `ROADMAP.md`, ítem 0 «REGLA VIGENTE — GATE» — su disparador pasa a ser el estado del tubo, no la DSR del paper. Solo se ejecuta con los datos. Sin debate nuevo, sin kickear la decisión.

---

## FASE D — Familias nuevas post-gate (pre-registradas, ordenadas por Sharpe esperado por esfuerzo)

### D1. Meta-labeling (I5) — primera familia nueva
Modelo secundario que predice si cada trade del baseline congelado gana, con features de contexto (régimen HMM, vol, day-of-week, sentimiento acumulado, telemetría del propio A5). `barrier_labeling.py` (M1) ya está construido; los labels crecen con cada semana de paper. **Ataca las brechas #1 y #4 juntas**: el efecto necesario para filtrar es menor que para generar alpha, y el objetivo pasa a ser la rentabilidad REAL del trade, no el patrón crudo. Pre-registro + MDE check obligatorios.

### D2. Opciones — la familia ausente
Con B2 acumulando superficie IV desde hoy y el colector intradía (B1): (i) **VRP** — venta de vol sistemática con filtro de régimen HMM (primero simulada paper con collar sintético IV); (ii) **GEX** — exposure de gamma de dealers como señal de represión de vol intradía (pega directo con las barras 1-min y los t>10 internos); (iii) **PEAD vía opciones** — coste de carry de la señal como proxy de expectativa. Primitivos gratuitos; pre-registro estricto + MDE antes de cada trial. **Ataca brecha #1** (familia con el mejor Sharpe histórico por unidad de capital accesible a un shop chico) y la familia ausente del veredicto Simons.

### D3. Intradía genuina
Hipótesis intradía NUEVAS (no recalentar gap-reversion §13 — muerto con costos EOD) con costos intradía modelados desde el día 1 usando el libro propio (A5) y cross-section de B1. LEAN solo si la acumulación + un trial intradía pre-registrado lo justifican (imagen recuperable gratis — decisión ya tomada).

### D4. Pesos jerárquicos (I4) — shrinkage James-Stein per-ticker
Arregla la vulnerabilidad w_mom 0.6642 (pooled no representativo vs mediana per-ticker −0.074). Estimador correcto para la heterogeneidad medida. **Ataca brecha #3** (estructura más rica que el score lineal) sin cambiar de familia.

### D5. Señal multivariada (solo después de D1)
Ridge/elastic-net cross-sectional sobre el panel 102 con selección por IC — usando feature store (B3), holdout (B4) y MDE (B5). Si el meta-labeling funciona, el step-up a multivariado tiene sentido; antes no (regresión sobre ruido con n chico).

### D6. Neutralización de cartera con los 8 factores RMT
Ya computados y validados vs Marchenko-Pastur (`rmt_factor_scores_8factors.csv` hoy huérfano): sizing por exposición a factor mercado + residuales vía el Kelly existente. **Ataca D10** (sizing sin estructura de cartera) con piezas ya construidas.

---

## Matriz de trazabilidad — brecha → remedio

| Brecha | Remedio inmediato (gate) | Remedio estructural (post-gate) |
|---|---|---|
| #1 Subpotencia (ciego a IC 0.02-0.08) | B4 holdout + B5 MDE ex-ante (deja de quemar slots en no-decidibles) + A6 (DSR honesto) | D1 meta-labeling (efecto necesario menor) + D2 opciones (Sharpe base mayor) + D4 shrinkage + B7 point-in-time |
| #2 Sin motor intradía | B1 colector 30 símbolos acumulando | D3 hipótesis intradía con costos propios desde el día 1 |
| #3 Sin multivariado (score lineal, RMT huérfano) | B3 feature store + B6 contrato única | D4 jerárquico + D5 ridge (tras D1) + D6 neutralización RMT |
| #4 Patrón ≠ ineficiencia capturable | A1 reconciler + A3 kill-switch + A5 telemetría fills + A4 hash-guard | D1 meta-labeling con labels de ejecución real + costo vigente medido (no supuesto) |
| Opciones ausentes | B2 superficie IV acumulando desde hoy | D2 VRP/GEX/PEAD-options |

**Qué NO remedia este plan (honestidad Simons)**: no garantiza que exista edge detectable en este universo/frecuencia — remedia la CAPACIDAD de detectarlo y de no mentirse sobre lo que no puede detectar. El MDE (B5) hace explícito "esto es indecidible con los datos disponibles" ANTES de quemar el slot; el 1/12 (C1) decide el futuro del proyecto con datos, no con esperanza (desde la re-especificación de Boris del 2026-09-05: C1 verifica el **tubo**; el veredicto de **edge** sale de las ventanas OOS históricas — ver C1 arriba). Si la respuesta es "no hay edge en EOD equity de 102 líquidos", el plan ya habrá construido el caño intradía + opciones donde la evidencia interna dice que vive la estructura.

## Cronograma y dependencias

```
Sem 1 (09-03→09-08):   A0→A1→A2→A4 (arranca contador VERIFICADO) → A3, A5, A6, A7, A8, A9
Sem 1-2 (con OK Boris): B0 granja fantasma (cuenta paper separada) + B0.bis cross-check precios
Sem 2-3:               B1 (15→30 símb) + B2 (IV diaria) + A5 acumulando telemetría + B0 acumulando fills SHADOW_
Sem 2-8:               B3, B4, B5, B6, B7(opcional) — sin tocar ruta de decisión (B6 solo con golden)
2026-12-01:            C1 (o fecha que fije contador ≥ 60 días limpios)
Post-gate:             D1 → (D2, D4, D6 en paralelo) → D3, D5
```

Dependencias duras: A0 antes que A1 (el reconciler y el contador de días limpios no son confiables sobre un cache de precios que puede tener barras cruzadas o huecos sin detectar); A1 antes que A2 (el contador necesita la evidencia de reconcile); A4 antes de arrancar la racha oficial (el congelamiento se firma con el manifiesto); **B0 requiere OK explícito de Boris (segunda cuenta paper) antes de construirse**; B6 solo con golden bit-idéntico + actualización de manifiesto declarada (reinicia el contador — o se difiere al 1/12 si la equivalencia no es perfecta); D2 y D3 dependen de B2/B1/B0 acumulando ≥ 2-3 meses de datos.

## Criterios de éxito verificables (por fase)

- **A**: (i) `clean_days.json` con racha ≥1 y evidencia por condición; (ii) matar el updater en un test → día no cuenta; (iii) cambiar un byte de `signal_engine.py` → hash-guard lo marca; (iv) orden sembrada con fill divergente → fila en `execution_telemetry`; (v) pre-registro de un trial durante el gate → rechazado por el ledger.
- **B**: (i) 30 parquets intradía creciendo por rueda; (ii) `iv_surface/` con ≥30 días acumulados al 1/12; (iii) un script migrado a feature store sin cambio de resultados; (iv) MDE rechaza un diseño sub-potente de prueba; (v) golden de señal 100% idéntico.
- **C**: decisión (a)/(b)/(c) ejecutada con `monthly_report` + racha como artefacto, antes del 2026-12-15.
- **D**: cada familia nueva abre con pre-registro completo (umbral, corrección, éxito) + MDE ejecutable — o no abre.
