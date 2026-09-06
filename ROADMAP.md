# Roadmap — fortress_core

Documento vivo que centraliza TODO lo que quedó abierto, en todas las áreas — no sólo
matemática/investigación. Existe porque el rigor que se aplicó a la validación estadística
nunca se declaró explícitamente para el resto del proyecto, y eso no puede depender de que
alguien se acuerde de pedirlo cada vez.

**Cómo se usa**: al empezar cualquier sesión de trabajo (con cualquier herramienta — Claude
Code, Cline, OpenCode), leer este documento primero. Al cerrar, actualizarlo antes de cerrar
— marcar lo que se cerró, agregar lo que apareció nuevo. Ningún ítem se da por cerrado sin
marcarlo acá, aunque se haya resuelto "de pasada" en otra conversación.

Última actualización: 2026-09-05 (Fase A casi cerrada: A0/A1/A3/A4/A5/A6/A7/A8/A9
comiteados y verificados; falta A2. B1 comiteado; B2 pendiente de re-auditoría).

**⏱️ CONTADOR DEL GATE — día 1/60 limpio, arrancado 2026-09-02.** Universo 102
confirmado en vivo desde el 02/09. **El contador sigue sin correr de verdad**:
no existe `backend/data/clean_days.json` en ningún repo — es A2, el próximo
ticket. Actualizar esta línea a mano cada vez que se verifique un día limpio
(ver definición en regla 0) hasta que A2 lo automatice.

## PENDIENTE AHORA — chequear primero, antes de leer el resto

Coordinación multi-agente vía Orca (Claude Code como coordinador; Kilo Code, OpenCode,
Cline como implementadores). Verificar contra `git log --oneline -10`,
`ps aux | grep screening_palas` y las ramas de cada worktree antes de asumir estado.

0. **REGLA VIGENTE — GATE DE 90 DÍAS (decisión de Boris, 2026-09-02, tras auditoría
   `AUDITORIA_NIVEL_DIOS_20260902.md` + análisis externo GLM 5.3)** — 🔴 la más
   importante de todo este documento, léela antes que cualquier otra cosa.
   **Cero hipótesis nuevas, cero pilotos nuevos, cero frentes de investigación
   nuevos hasta que el paper trading (con la contabilidad corregida de
   `paper_trading.py`, commit `1466dcc`) acumule datos limpios.**
   **Precondición (agregada 2026-09-02 tras revisión GLM): la fecha mide
   TIEMPO LIMPIO, no calendario** — exige ≥60 días de pipeline 3×/día
   corriendo SIN interrupciones con la contabilidad corregida vigente. Si
   el colector/pipeline tiene una semana muerta entre hoy y la fecha, la
   evaluación corre hasta completar los 60 días limpios — no se decide con
   menos del único activo que el gate necesita. Fecha de
   evaluación: **2026-12-01, o más tarde si faltan días limpios** (90 días
   es el piso, no el techo). **Definición de "día limpio" (fijada 2026-09-02,
   ANTES de que haga falta, para que el 1/12 no sea debate)**: cuenta si Y
   SOLO SI las 3 condiciones se cumplen ese día hábil — (a) `pipeline_diario.log`
   muestra `rc=0` en sus 3 corridas programadas (9:35/15:40/22:10 ET); (b)
   `data_updater.log` sin línea `PRECIOS: ERROR`; (c) `reconcile_open_positions`
   corrió sin dejar órdenes huérfanas con `pnl_r` sin explicar (ver
   `paper_trading.py` commit `1466dcc`). Un día que falla cualquiera de las 3
   NO cuenta y no rompe la racha retroactivamente — solo no suma. Universo:
   **102 confirmado en vivo desde 2026-09-02** (corrida 09:35 ya lo usó, sin
   paso de migración pendiente) — el contador no espera nada más para
   arrancar. **Criterio pre-declarado — RE-ESPECIFICADO por Boris el 2026-09-05**
   (fundamento: `ANALISIS_MDE_GATE_DICIEMBRE_2026.md §6 opción 1`; el análisis
   vive en la rama `bjofrea-ctrl/fundamentales-automatizado`, commit `c602a30`, y
   llega al tronco con B5). El texto del 2026-09-02 queda reemplazado acá, en
   este único lugar, y la re-especificación **no es precedente para tocar ningún
   otro criterio estadístico**:

   - **DSR≥0.90 en ≥2/3 ventanas se evalúa y sigue vigente SOLO sobre las
     ventanas OOS históricas pre-corte (W1/W2/W3, ~500 días hábiles c/u).** No
     es una barra nueva ni más permisiva: es exactamente el mismo estándar que ya
     rigió todos los trials formales del proyecto, aplicado donde el diseño **sí
     tiene potencia para decidir**. Sin cambios.
   - **El gate de diciembre (paper prospectivo, ~60-90 días) verifica el TUBO, no
     el edge.** Tres condiciones, todas medibles y ninguna de ellas una prueba de
     descubrimiento: **(a)** racha de días limpios ininterrumpida bajo las
     condiciones a+b+c ya definidas arriba; **(b)** `fill rate` y slippage
     medidos (A5) dentro de lo que predice el modelo de costos; **(c)** coherencia
     paper-vs-señal — las señales que debieron dispararse se dispararon, sin
     discrepancias no explicadas.
   - **Para que nadie lo lea al revés: esto NO es una segunda prueba estadística
     de edge**, es un chequeo operativo de que el tubo corrió limpio y acumuló el
     único activo que el proyecto necesita. **La prueba de edge sigue siendo la
     de las ventanas OOS históricas.** Exigir DSR≥0.90 a ~60 días de paper con
     horizonte semanal pedía un SR anual ~6.7-8.5 contra un efecto plausible de
     0.10: era casi imposible por construcción y habría convertido el gate en
     teatro — refutación garantizada por falta de potencia, no por falta de edge.
   - **La condición de salida NO se toca**: si a la fecha el tubo no corre limpio
     o la coherencia paper-vs-señal no se sostiene, se decide CON DATOS entre
     (a) reducir el proyecto a mantenimiento, (b) pivotar el frente de
     investigación, o (c) aceptarlo como laboratorio personal sin aspiración de
     capital — no se seguirá pateando la decisión sin condición de salida (esto es
     lo que el pre-mortem señaló como causa real de burnout, no el código).
   - **Trabajo paralelo, sin bloquear nada**: se sigue acumulando data (intradía
     B1, IV B2) con la aspiración declarada de alcanzar DSR≥0.90 también sobre
     ventanas de paper más largas. Es aspiración, no precondición: no frena el
     gate de diciembre mientras tanto.
   **Lo único permitido en paralelo mientras corre el gate** (mecánico,
   ninguno depende de investigación nueva): F0 de la auditoría (bugs, no
   decisiones), el colector intradía I3, telemetría de ejecución I9, y
   cerrar lo que ya estaba abierto antes de esta regla (mapeo HMM B6,
   inventario de series para el SPA — cerrado, ver hallazgo abajo, latido
   de datos I-heartbeat). PBO vigente: **§39 (0.2358) cerrado como oficial
   2026-09-02** (ver `PLAN_MEJORA_MATEMATICA.md §40.1`) — §40 (0.4688)
   queda citado con limitación, no revocado. Nada de esto consume el tiempo
   del gate; el gate lo consume solo el paper trading corriendo solo, todos
   los días.

> **Gate de 60 días (arrancó 2026-09-02) — estado al 2026-09-05**: la Fase A de
> `PLAN_REMEDIO_BRECHAS_20260903.md` quedó cerrada en **A0** (harness de integridad
> del cache yfinance — contaminación cruzada verificada y saneada, precondición de
> A1), **A1** (reconciler de órdenes huérfanas en la fase 22:10), **A3** (kill-switch
> por divergencia — `STOP_FILE` confirmado que NO bloquea EXIT/reconcile), **A4**
> (hash-guard del motor con drift de A6 declarado y `verify` rc=0), **A5** (telemetría
> de ejecución por orden), **A6** (n_trials del ledger, no número mágico), **A7** (el
> ledger enforcea la Regla 1 de `ONBOARDING.md` con chokepoint único), **A8**
> (pre-registro PBO lag-0 **sellado y NO ejecutado** — docs-only), **A9** (flag
> `GOVERNANCE_LLM_ENABLED` + cartel explícito en el dashboard) y **B1** (colector
> intradía 7→30 símbolos líquidos). Todo verificado independientemente (no por
> autoreporte de agente) antes de aceptar cada commit.
>
> 🔴 **Falta A2, y es lo único que impide que el gate sea evaluable**: no existe
> `backend/data/clean_days.json` en NINGÚN repo. Sin ese contador la racha de días
> limpios **no está corriendo**; el `motor_manifest bump` que declaró el drift de A6
> ordena "reiniciar el contador a mano" sobre un archivo que todavía no existe. Es
> el próximo ticket en curso (2026-09-05).
>
> **B2** (colector de superficie IV) implementado por OpenCode, autoreporte 12/12 +
> 524/524, pero la auditoría independiente se cortó por un rate-limit de sesión (no
> por hallazgo) — sigue sin comitear hasta reintentarla.
>
> ✅ **La cita "Regla 0 del ROADMAP" (bug real, propagado a código y al propio ticket)
> ya está corregida en todos lados**: código, mensajes de error, tests, y
> `PLAN_REMEDIO_BRECHAS_20260903.md` líneas 67/68/88 (era la **Regla 1 de
> `ONBOARDING.md`**: "Ningún trial de motor sin criterio pre-registrado").

1. **A6.3 — screening PALA/RESTO/POOLED** — 🟢 trial original CERRADO
   (29/08, `COMPLETED`/`NO_CUMPLE`, ver §12 de `PRE_REGISTRO_SCREENING_PALAS.md`).
   **Saneamiento del check APROBADO por Boris (29/08) — 🟢 CERRADO (31/08)**:
   Kilo implementó el check corregido (N_TRIALS igualado a 17 SOLO para la
   comparación, sin tocar el default de ningún script), corrió los 3
   procesos paralelos (PALA/RESTO/POOLED) y el ledger quedó
   `screening_palas_saneada_a63` = `COMPLETED`/`NO_CUMPLE`
   (artefacto `data/cache/screening_palas_parallel_raw_20260830_partial.txt`,
   verificado por mí antes de commitear el cierre del ledger).
   **W3 investigado a fondo (OpenCode, 30/08,
   `INVESTIGACION_W3_A63_20260830.md` en worktree `test-opencode-orca`,
   spot-check verificado por mí)**: no es un parámetro mal puesto — es
   una diferencia ESTRUCTURAL real entre los dos scripts. El baseline
   corre continuo (una sola pasada 2019→2026 troceada en ventanas
   después) con estado que se arrastra entre ventanas: posiciones
   abiertas cruzando fronteras, equity compuesto, HMM con ~20 refits
   walk-forward acumulados hacia 2024 y 5 años de evidencia bayesiana.
   El screening corre PALA/RESTO/POOLED como 3 `BacktestEngine`
   independientes (equity=25000 fresco, sin posiciones, HMM fiteado de
   una sola vez sobre 9 años de historia de golpe). Esa diferencia
   genera +28-46% más trades en W3 del screening vs. el baseline — cifra
   verificada, no inferida. Se descartaron rango de fechas (delta
   trades=0) y costo (empeora, no explica) como causas. Aislar la causa
   exacta requiere un experimento controlado nuevo — **es un trial
   nuevo, necesita pre-registro y aprobación de Boris**, no se ejecuta
   solo. `PRE_REGISTRO_SANEAMIENTO_CHECK_A63.md` sigue siendo la
   referencia del saneamiento aprobado; no confundir con el veredicto
   NO_CUMPLE ya sellado del trial original (ese no se reabre).

1b. **Trial #21 — Asimetría direccional de factores** (OpenCode, 30/08) —
   🟢 **CERRADO — GRIS por cobertura: 0/3 ventanas interpretables**
   (registrado NO_CUMPLE con nota; ledger `signal_diagnosis` 27→28, slot
   consumido por reserva Track A). Diseño de Cline aprobado por Boris
   30/08 → pre-registro formal `PRE_REGISTRO_ASIMETRIA_DIRECCIONAL.md`
   congelado ANTES de correr (enmiendas pre-congelación: slot 23→28 por
   conteo ledger real, umbrales scipy 2.50/2.74). Script
   `backend/scripts/diagnose_asimetria_direccional.py` (ruff limpio,
   etiquetado §2 verificado con test unitario), corrida ÚNICA 20:09,
   artefacto `trial21_asimetria_direccional_20260830_200908.txt`. **El
   gate de cobertura §5 (≥75 fechas con ambos lados Y ≥10 símb/lado) falló
   en las 3 ventanas: el lado DOWN es estructuralmente escaso en el
   universo 50 large-cap (mediana DOWN por fecha = 4 global; fechas con
   DOWN≥10: solo 21%).** El estudio NO refutó la asimetría — nunca
   alcanzó evidencia; la hipótesis queda no-resuelta-por-insuficiencia.
   Lo que sí se aprende: cualquier trial futuro que necesite el lado DOWN
   con piso ≥10/lado sobre este universo debe ampliar universo (100+
   con small/mid caps) o recalibrar X por pre-registro NUEVO (slot 29) —
   jamás edición retroactiva de este. Ver `PLAN_MEJORA_MATEMATICA.md
   §48/§48.1`.
2. **Motor de fundamentales automatizado** (Cline, rama
   `bjofrea-ctrl/fundamentales-automatizado`, NO mergeada a `main`) — 🟢
   Fases 1-3 CERRADAS y verificadas independientemente (63 tests, paridad
   bit-a-bit 1000/1000 con el motor real). Fase 4 (integración: endpoint
   solo-lectura + cron diario 22:00 mismo patrón que dataupdater + pestaña
   dashboard vía iframe de `generar_dashboard()`) — decisiones cerradas
   28/08 tarde: universo completo (50 símbolos) corrida diaria (~250/250
   llamadas FMP, sin margen — por eso se pidió procesar en lotes de 5 con
   checkpoint parcial y reintento al día siguiente, no el mismo día), y
   dashboard cacheado del último cron (NUNCA recalculado on-demand, para
   no quemar cuota con cada vista). **Fase 4 CERRADA de verdad el 29/08
   noche** (commit `67109a6`), tras dos rondas de auditoría real (no
   confiar en "tests en verde" ni en "listo" sin correr todo yo mismo —
   pasó dos veces en 24h, ver SESSION_LOG):
   - Cron real instalado y versionado (`fundamentals_screen_daily.sh` +
     `com.fortresscore.fundamentals_screen.plist`, 22:30).
   - Dashboard/Excel se generan de verdad — `render_artifacts()` llama a
     `generar_excel()`/`generar_dashboard()` del motor canónico
     **vendorizado** en `backend/app/core/motor_canonico/` (decisión: un
     cron que corre solo a las 22:00 no puede depender de un path fuera
     del repo). Hash verificado byte-a-byte contra el zip oficial r13 de
     la skill (`84abe308e7e8e710f2cf2e7649bd9d6074c1e7de1ab8c7dd0f26f3b51768995d`).
   - Fixture de paridad recuperado (Boris re-exportó el Excel el 29/08) y
     estabilizado en `backend/tests/fixtures/canon/` (dentro del repo, no
     en `~/Downloads`) — el skip ahora es ruidoso (`REQUIRE_PARIDAD=1`
     hace fallar en vez de saltear en silencio) y quedó un guard-rail:
     una segunda referencia al mismo fixture en `test_fundamentals_ingestion.py`
     seguía apuntando al path viejo perdido — encontrado en la auditoría
     final, corregido antes de aceptar el commit.
   - Contaminación de tokens del modelo (caracteres chinos) limpiada.
   - Verificado por mí, corriendo todo de cero: 93 passed, 0 skipped
     (suite completa + paridad estricta), tamaños/hashes de los artefactos
     en disco coinciden exacto con lo reportado.
   - **VERIFICADO VISUALMENTE (01/09, `backend/VERIFICACION_VISUAL_DASHBOARD.md`)**:
      el dashboard/Excel generados por `render_artifacts()` (motor vendorizado) se
      compararon estructuralmente contra el export real de InvestingPro
      (`market_view_export.xlsx`, fixture canon). El motor produce el formato canónico
      correcto: 2 hojas (Screening + Instructivo), 37 columnas en 6 bandas de color,
      freeze_panes E3, DataBar en Price vs Fair Value, 15 tooltips, fills por
      balde/veredicto, dashboard HTML grid7 con funnel 13/25/227/532/203. Todas las
      diferencias vs el export input son intencionales (el motor enriquece el export
      con el sistema de bandas y clasificación propio). Veredicto: **CERRADO**.
   Sigue necesitando `FMP_API_KEY`/`FINNHUB_API_KEY` reales para probar
   contra la red de verdad (hasta ahora todo probado con mocks, declarado
   así explícitamente, no ocultado).
3. **Bug data_ingestion.py umbral >7 días** — 🟢 CERRADO (OpenCode, commit
   `b4a6797`).
4. **Launchd pipeline diario (com.fortresscore.pipeline)** — 🟢 verificado
   27/08 (orden invertido vs. plan, documentado, no bloqueante).
5. **Cron: `com.fortresscore.bovedabackup`** (diario 23:30) — 🟢 INSTALADO
   27/08.
6. **Limpieza de procesos huérfanos** (27/08 noche): 2 procesos `opencode`
   huérfanos de 5 días (~92% CPU c/u) encontrados y matados.
7. **DISCO LLENO — resuelto 28/08 AM, causa real encontrada**: la Mac quedó
   con 53MB libres de 234GB (100% de capacidad) — culpable:
   `~/.cline/data/db/hub-events-hub-production.db`, **95GB en un log
   interno de telemetría de Cline que nunca se poda** (bug de Cline, no del
   proyecto). Borrado + matado el proceso "hub" (PID 98427, separado de
   cualquier terminal de trabajo) que lo tenía abierto → **97GB libres
   ahora**. Esto explica el crash de Kilo de la noche anterior (no fue el
   proveedor del modelo, fue ENOSPC). Candidatos de limpieza NO urgentes
   que quedaron sin tocar: `~/.colima` (23GB, VM de Docker aparentemente sin
   uso) y `~/.cache` (17GB, cache genérico recreable) — revisar si `.cline`
   vuelve a crecer así con el tiempo, puede repetirse.
8. **Dashboard — pestaña AAI** — 🟢 CERRADO (30/08, Cline, commit `483024f`):
   `FundamentalsPage.tsx`, iframe del endpoint de Fase 4 con manejo de
   503/404/red caída. Verificado por mí: typecheck limpio, 5/5 tests
   propios pasan. Queda pendiente el ítem de inversiones sintéticas
   (no cubierto, separado de esto).
9. **Activar modo real del pipeline diario (`pipeline_daily_signal.py`)** —
   🟡 PRIORIDAD, para después de A6.3/Fase 4 (decisión de Boris 29/08). El
   pipeline corre 3x/día (9:35/15:40/22:10) hace 3 días seguidos sin fallar,
   pero el log de señales (`pipeline_signal_log.jsonl`) solo tiene 4 líneas,
   todas con `checkpoint_override=True` — validación mecánica del tubo
   (orden+registro), NO señal real todavía. Falta apagar el modo checkpoint
   para que empiece a acumular historial prospectivo real, comparable contra
   el backtest. **NO activar sin confirmación explícita e inequívoca de
   Boris** — implica órdenes/señales reales, es difícil de revertir. El
   29/08 se le preguntó A) anotar para después vs B) activar ya, y la
   respuesta ("Sí" repetido dos veces sin elegir) no alcanzó ese umbral —
   se optó por A) hasta tener una confirmación sin ambigüedad.
10. **ATLAS — Sistema de ingeniería inversa precio→indicador por ticker**
    (`DISENO_ATLAS_INGENIERIA_INVERSA_20260901.md`, commit `23f4aee` →
    implementación `0f2c798`) — 🟢 **CERRADO capa 1 (descriptiva)**, 01/09.
    Origen: trabajo de Boris 30/08 con Kilo (worktree `test-kilo-orca`,
    `INGENIERIA_INVERSA_POR_TICKER.md`) exploró NVDA/AAPL/EPAM/QLYS de forma
    puntual; Boris pidió generalizar a un SISTEMA reutilizable sobre todo el
    universo. Diseño (aprobado 01/09) propuso dos capas: ATLAS descriptivo
    (cualquier celda, sin ledger) y GRADUACIÓN (pre-registro + deflactación
    Bonferroni por conteo real de celdas — única vía a regla). Implementación
    v1 (alcance declarado: universo 50 canónico, 3 ind, 3 horiz, W1/W2/W3/TOTAL,
    9 celdas régimen sin h60 por §5.4): `backend/scripts/atlas_ticker.py`
    (988 líneas, 8 funciones, offline, cache-only, sin tocar el motor).
    Outputs: `atlas_celdas.csv`, `fichas/<TICKER>.md`, `resumen_arquetipos.md`,
    `atlas_meta.json`, `kilo_validacion.csv` (con `--kilo-validacion`).
    Tests: 5 grupos del §8.5 del diseño — sin look-ahead (x_t invariante a h),
    gates cobertura (INSUFICIENTE cuando N<3), convención t−1→t+h, idempotencia,
    conteo real de celdas. **13 tests passed, 1 skip, suite conjunta
    41 passed** con `test_fundamentals_screen.py` (sin romper nada).
    Validación cruzada Kilo (gratis): NVDA × momentum_12_1 × h20 × TOTAL →
    atlas spread Q5−Q1 = +306bp, piloto Kilo spread high−low = +249bp,
    **ambos positivos → match_direccional TRUE**. Hallazgo visual del piloto
    2y/60d (NVDA reversionista) y 5y/60d (EPAM desplome) preservados como
    celdas del atlas — heterogeneidad por ticker confirmada por construcción.
    Capa 2 (graduación) NO implementada, esperando decisión de Boris.

Si alguna de estas cambió de estado cuando leas esto, actualizá esta sección
(borrala o marcá cerrado) — no la dejes desactualizada.

---

## Backlog futuro — NO AHORA, sólo después de cerrar lo de arriba

### 9. Estrategia de scalping MTF (video de YouTube) — comparación futura, NO desarrollar todavía

Boris trajo un prompt (generado por otra IA a partir de un video de YouTube de un
influencer de trading, "Alex Ruiz") para programar un bot de scalping multi-temporal
(H4/H1 sesgo, M5 estructura+Fibonacci, M1 gatillo por ruptura de "diagonal"+volumen) más
un motor de `RiskManager`/`CostAndRiskEngine`. **Decisión (29/08): queda en espera, se
retoma como desarrollo posterior — una vez cerrado el trabajo actual — para comparar
contra la estrategia propia del proyecto, NO para reemplazarla ni mezclarse con el
ledger existente.**

Reservas técnicas ya planteadas, para no perderlas cuando se retome:

- El gatillo central ("ruptura de diagonal" en M1) es una línea de tendencia dibujada a
  mano en el video — inherentemente subjetiva. Cualquier implementación algorítmica
  (ZigZag, regresión lineal) es una *aproximación inventada*, no la estrategia original.
  Cualquier backtest futuro estaría validando esa aproximación, no la estrategia del video.
- Es scalping M1: la categoría más sensible a costos que existe (spread+slippage pueden
  comerse la esperanza matemática por completo — el propio material del video lo admite).
  No tomar en serio ningún resultado de backtest sin costos realistas modelados desde el
  primer día (no como ajuste posterior).
- Requiere infraestructura que este proyecto no tiene hoy: datos M1/M5/H1 de forex/índices/
  cripto (MT5, ccxt, IB — no hay conexión a ninguno), y un motor de backtesting distinto
  (`backtrader`/`vectorbt`, no `BacktestEngine` existente). Es un proyecto de infraestructura
  aparte, no una tarea dentro del código actual.
- Si se retoma: tratar como sandbox aislado (worktree propio, sin tocar `trial_registry.json`
  de producción), con pre-registro previo igual que cualquier otra hipótesis nueva, y con el
  nivel de escepticismo más alto posible dado el origen (video, no investigación).

### 10. Timeframes según horizonte — swing vs. intradía (nota de referencia)

Pedido de Boris: documentar qué mirar en cada caso, para tenerlo presente al comparar
estrategias de distinto horizonte (útil cuando se retome el ítem 9).

| | **Swing trading** (días–semanas) | **Intradía / scalping** (minutos–horas, cierra el mismo día) |
|---|---|---|
| Timeframe de decisión | Diario (D1), a veces 4H para afinar entradas | M1–M15 |
| Timeframe de contexto/sesgo | Semanal (W1) para tendencia macro | H1/H4 para sesgo intradía |
| Sensibilidad a costos (spread/slippage/comisión) | **Baja** — el costo es una fracción chica del movimiento esperado por trade. Es justo por esto que el enfoque diario actual de `fortress_core` es viable con costos de 0.05-0.10%/lado. | **Muy alta** — el costo puede ser una fracción grande (o mayor) del movimiento esperado. La estrategia vive o muere en la ejecución real, no en el backtest histórico. |
| Tamaño de muestra necesario | Pocos trades por año → hace falta **muchos años** de historia para significancia estadística (de ahí DSR, Bonferroni, ventanas de varios años como en A6.3). | Muchos trades por año → significancia en cantidad de trades se alcanza rápido, pero el riesgo de sobreajuste a un régimen de volatilidad específico es mayor. |
| Riesgo estructural propio | Gaps overnight/fin de semana. | Liquidez que se seca en rupturas, ejecución a peor precio (slippage) justo cuando la señal es más fuerte. |
| Infraestructura necesaria | Datos EOD alcanzan (lo que ya tiene el proyecto). | Datos intradía/tick, feed cercano a tiempo real, conexión a broker — nada de esto existe hoy en `fortress_core`. |

---

## Plan de implementación consolidado (2026-08-12) — para ejecutar en tandas

El usuario pidió cerrar todo lo pendiente, no sólo lo más urgente. Se secuencia en tandas
chicas en vez de un cambio gigante — mismo criterio de todo el proyecto: verificar entre
pasos, no acumular riesgo. Cada tanda termina con `pytest` completo + commit + este documento
actualizado antes de pasar a la siguiente.

**Modo de trabajo — "fallo, arreglo y sigo" aplica con un límite claro**:
- ✅ Aplica sin pedir permiso: bugs de código normales que aparezcan haciendo estas tandas
  (un import roto, un test que falla por un detalle menor, un typo) — arreglarlos y continuar.
- ❌ NO aplica a nada que toque el motor/investigación (Tanda D): ahí un fallo no se
  "arregla y sigue", se documenta con su artefacto y se decide — la regla no-negociable
  #1 y #3 de `ONBOARDING.md` (pre-registro antes de correr, revert si no cumple el criterio)
  sigue vigente sin excepción. "Arreglar rápido" y "criterio pre-registrado" son cosas
  distintas — no mezclar.

### Tanda A — Código, P1 restante ✅ (cerrada 2026-08-12, commit `a56e516`)
1. ✅ Alinear versión de Python: `backend/Dockerfile` fijado a `python:3.9-slim` (igual que
   el `.venv` real, 3.9.6; todas las deps soportan 3.9).
2. ✅ `README.md`: sacada la mención de Redis, corregida la versión (3.9), documentados los
   27 endpoints reales (tabla completa, 8 routers + `/health`).
3. ✅ Docstrings de Controller/Judge en `advanced_agents.py` corregidos — ahora dicen
   "lógica determinista — no usa LLM" (el flujo de gobernanza sí usa NIM en la tríada,
   pero estos dos agentes son pura lógica).
   Verificación: `pytest` desde `backend/` → 80 passed, 11.58s. Nota: correr pytest desde
   la raíz del repo se cuelga (config en `backend/pytest.ini`); invocación canónica:
   `cd backend && .venv/bin/python -m pytest`.

### Tanda B — Seguridad recién detectada ✅ (cerrada 2026-08-12, commit `217eb51`)
4. ✅ Backup específico de `fortress.db` agregado a `scripts/auto_backup.sh` (función
   `backup_db()`) y `scripts/backup.sh` (paso 6.5): `sqlite3 .backup` (seguro con
   escrituras concurrentes) → `/Volumes/EMPRESA/fortress_core_backups/db/`, retención
   de 20 snapshots.
5. ✅ Rate limit en memoria (sin Redis, el stack no lo tiene) en
   `backend/app/api/rate_limit.py`: ventana deslizante por IP (10 llamadas/60s, default),
   `X-Forwarded-For` aware, log de uso + 429 al exceder. Aplicado a
   `predict/analyze/{symbol}` y `governance/analyze/{symbol}` (los dos GET sin auth que
   disparan LLM real). Tests: `tests/test_rate_limit.py` (4).
   Extras detectados al pasar: `backend/data/` (estado de runtime) ignorado en .gitignore.
   Verificación: `pytest` → 84 passed, 11.07s.

### Tanda C — Código, P2 ✅ (cerrada 2026-08-12, commit `6ae0770`)
6. ✅ Verificado con grep, sin remover: `ProbabilisticEngine` (wrapper) y
   `KellyPositionSizer` SOLO los usa `scripts/test_probabilistic.py` (smoke script de
   desarrollo); `RiskParityAllocator` SOLO `scripts/test_system.py`. No son código
   muerto en sentido estricto → no se tocaron. El módulo `probabilistic_engine.py`
   se queda (backtest_engine, signal_engine y opportunities importan 6 clases útiles
   de ahí: CopulaRiskAnalyzer, ProbabilityCalibrator, BayesianOnlineUpdater, etc.).
7. ✅ `prompt_engine.py` ELIMINADO (659 líneas). `HardinessChecker` (lo único en uso,
   en `triad_agents.py`) movido intacto a `app/core/hardiness.py`; también se eliminó
   `scripts/test_prompt_engine.py` (probaba código muerto) y se portó su cobertura a
   `tests/test_hardiness.py` (7 tests). **Bug latente encontrado y documentado**: el
   assert de alucinación del script viejo NUNCA pudo pasar — `detect_hallucination`
   solo matchea formato "clave: valor", no texto libre.
8. ✅ Tests de integración para 6 de los 7 routers sin cobertura (governance y
   opportunities ya la tenían): `test_backtest_api.py` (8), `test_market_api.py` (6),
   `test_live_api.py` (4), `test_predict_api.py` (6), `test_risk_api.py` (2),
   `test_system_api.py` (2) — patrón del repo: `asyncio.run` directo + monkeypatch,
   sin httpx. **Bug real encontrado y arreglado**: el muestreo de
   `/api/backtest/equity-curve` con `step = len//300` no muestreaba nada entre 300 y
   599 puntos; ahora `ceil(len/300)`.
9. ✅ CI en `.github/workflows/ci.yml`: jobs `lint` (ruff) y `test` (pytest) en cada
   push/PR, Python 3.9. `ruff.toml` en raíz: target py39, `select = [E4,E7,E9,F,I,W]`
   (E501 fuera a propósito: las líneas largas del repo son contenido académico/prompts,
   no código). Autofix inicial: 117 violaciones corregidas + 14 manuales (semicolons,
   `== True` → `.is_(True)`, vars ambiguas `l` → `lesson`, vars sin uso → `_`).
   `ruff==0.16.2` agregado a requirements-dev. Lint: 0 errores. pytest: 119 passed.

### Tanda D — Investigación (en paralelo a A/B/C, no bloquea ni bloquea código)
10. ✅ §13.1 gap-reversion: backtest con costos reales (2026-08-12) — pre-registrado en
    `PLAN_MEJORA_MATEMATICA.md §13.1`, corrido (`backtest_gap_costs.py`, artefacto
    `backtest_gap_costs_20260812_173951.txt`): **NO CUMPLE**. Retorno bruto medio diario
    del fade EW ≈0 (t-NW −0.20) — la significancia del IC (t=−11.29) no se traduce en
    retorno promedio ni antes de costos; neto (0.30%/trade) t-NW **−11.53**. §13 queda
    CERRADO: gap-reversion es hallazgo académico, no capturable. Ejecución intradía se
    descarta definitivamente con esta infraestructura.
11. ✅ §12 régimen-vs-volatilidad — CERRADO como pista sin acción (2026-08-12, decisión
    del usuario): no se conecta TARGET_VOLATILITY, no se reducen estados HMM, no se
    espera más historia. Si se retoma, es con pre-registro nuevo y razón nueva.
12. ✅ Fase 0.6 — re-test sentimiento/fundamentales contra panel limpio + universo 50
    (2026-08-12): **NO CUMPLE para ambas variantes (0/3 ventanas cada una)**. Artefacto
    `fase06_retest_20260812_175055.txt`, pre-registro `PLAN_MEJORA_MATEMATICA §0.6.1`.
    DSR: V1 = 0.041/0.002/0.225 (W1/W2/W3), FUND = 0.121/0.004/0.330 vs baseline 0.071/
    0.028/0.173. Refutación #8/#9 CONFIRMADA con ejecución arreglada y universo 50.
    Limitación declarada: cobertura EDGAR 5/50 (10%) diluye la pata FUND. La única
    variable con cobertura completa (AAII) es más débil que baseline en 2/3 ventanas.
    Baseline post-fix universo 50: único modo de operación documentado.
13. ✅ Investigación académica/foros de trading cuántico externa (2026-08-12) — informe
    completo en `RESEARCH_EXTERNA_CRITICA.md`: TradingAgents/FinCon validan el patrón
    multi-agente LLM (nuestra variante determinista es la defensa al fallo TradeTrap);
    Barber-Odean 2000 + Taiwan 2008 + survival 44/24/15% confirman risk-mgmt-first y
    no-over-trading como únicas reglas con evidencia; trading cuántico: cerrado como
    no-relevante para 50 símbolos (híbrido NISQ solo aporta en miles de activos).
14. ✅ §15 rank IC por sub-período (2026-08-12) — motivado por el hallazgo NY Fed
    (overnight drift real, desvanecido post-2021). Momentum/RSI/ADX: sin quiebre de
    régimen, sin señal Bonferroni-robusta ni antes ni después de 2022. No es que algo
    se rompiera — nunca hubo señal robusta en ningún momento de la muestra.
15. ✅ Fix `.gitignore` (2026-08-12) — la Tanda B excluyó sin querer TODOS los
    artefactos `.txt` de diagnóstico (patrón `data/` sin anclar). Corregido a patrones
    específicos; recuperados los 4 artefactos generados mientras estuvo roto.
16. ✅ §18.1 C6 (MA200 fade) — backtest con costos reales (2026-08-13) — pre-registrado
    en `PLAN_MEJORA_MATEMATICA.md §18.1`, corrido (`backtest_c6_costs.py`, artefacto
    `backtest_c6_costs_20260813_135830.txt`): **NO CUMPLE**. Panel verificado fiel a §16
    (3703 filas, Pearson IC −0.1582, Spearman −0.1129 — idénticos al artefacto de §16).
    LS (gate): bruto −0.000019/día (t-NW −0.07), NETO −0.000228/día (t-NW **−0.88**),
    Sharpe −0.27, 45.5% días positivos, 2661 días con posición. SO (info): neto −0.000758
    (t-NW −2.92). Diagnóstico: `E[sign×fwd] = +0.00017` — en 7 años alcistas dist>0 la
    mayor parte del tiempo, el fade está short casi siempre y paga el drift del mercado;
    el hallazgo vive en exceso de mercado (§18, t=−2.87), no en nivel → la mecánica LS
    cruda no lo capitaliza. §18 queda CERRADO: C6 es hallazgo académico, mismo destino
    que gap-reversion. Baseline universo 50 sigue siendo el único modo de operación
    documentado. **Tanda D completa.** Siguiente frente: Fase 1 EVT o Fase 2
    Kalman+GP-BO (decisión del usuario).
17. ✅ §18.2 C6 HEDGEADO (market-neutral por beta) — INTENTO FINAL (2026-08-13) —
    pre-registrado en `PLAN_MEJORA_MATEMATICA.md §18.2` (regla de parada del usuario:
    sin tercera variante), corrido (`backtest_c6_hedge.py`, artefacto
    `backtest_c6_hedge_20260813_154313.txt`): **NO CUMPLE → §18 CERRADO DEFINITIVO.**
    Betas pre-muestra 2015-2018 (|β| medio 1.11), check de integridad ok (n=3703,
    Pearson −0.1582, Spearman −0.1129, P(dist>0)=0.744). LS-HEDGE bruto **+0.000149/día**
    (t-NW +1.01 — el hedge neutralizó el drift, pasó de −0.000019 crudo), NETO
    −0.000292 (t-NW −1.97). La señal existe en exceso de mercado pero es más chica
    que sus propios costos (+0.30% bruto/trade vs 0.63% hedged): real, no tradeable.
    C6 = hallazgo académico, línea MA200 CERRADA. Baseline universo 50 = único modo
    de operación documentado. Tanda D + línea C6 completas.
18. ✅ Fase 1 EVT — diagnóstico de colas universo 50 (2026-08-13) — pre-registrado en
    `PLAN_MEJORA_MATEMATICA.md §19`, corrido (`diagnose_evt_tails.py`, artefacto
    `evt_tails_20260813_155237.txt`): **PASA el gate**. GPD/POT sobre retornos
    estandarizados EWMA (λ=0.94; arch/GARCH no instalado — limitación declarada):
    ξ>0 significativo en 28/50 (56%), excesos bajo VaR-normal ≥1.5% en 47/50 (94%,
    promedio 1.95% vs 1% esperado); VaR99-GPD ≈ 3.0 z vs 2.326 normal (ratio medio
    1.26 — la regla gaussiana subestima el VaR 99% en ~26%); GPD calibra (excesos
    reales 0.98% ≈ 1%). Implicación: la regla de stop 2×ATR está sistemáticamente
    subdimensionada contra el riesgo de cola → **siguiente paso: pre-registro del
    trial de stops EVT del motor** (mismas ventanas W1-W3, DSR≥0.90, n_trials+1;
    **debe ser walk-forward** — ξ/VaR-GPD re-estimado periódicamente, no el ajuste
    fijo de muestra completa de §19 aplicado retroactivo a W1, eso sería lookahead
    del mismo tipo que §3.1. Confirmar el n_trials exacto contra el historial de
    artefactos antes de fijarlo — no asumir el número).
19. ⚪ Diferido — kernel methods/SVM, ML no lineal, datos alternativos/NLP de
    sentimiento (2026-08-14, decisión del usuario). Investigación externa (Perplexity,
    verificada parcialmente — mezcla contenido sólido con al menos una cifra de
    rendimiento sin fuente confiable, mismo patrón que medallion-pub) mapeó el stack
    probabilístico de fondos comparables (Renaissance/D.E. Shaw/Two Sigma/AQR/
    Citadel/Bridgewater). Cruzado contra lo ya hecho acá: HMM/régimen, PCA/RMT, EVT,
    factores momentum/fundamentales — todo YA probado con nuestro rigor, mayoría
    refutada. Lo que queda sin tocar (kernel/SVM/ML no lineal, alt-data/NLP) no se
    persigue ahora — alto riesgo de sobreajuste con n=50 símbolos/kernel-ML, y
    alt-data es la inversión de infraestructura ya deprioritizada ("no escalar en
    serio"). Se retoma **sólo cuando el plan actual esté agotado**, asumiendo que en
    ese momento el costo (datos/infra) sea aceptable — decisión explícitamente
    pospuesta, no descartada.
20. ⚪ Diferido — indicadores sobre velas SEMANALES re-muestreadas (2026-08-13,
    pedido del usuario, para más adelante). **Distinto de §21/§21.1**: esos
    variaron el horizonte del retorno futuro (5d/10d/60d/125d) sobre indicadores
    calculados con barras DIARIAS. Esto es otra pregunta: re-muestrear OHLC a
    semanal (`resample('W-FRI')`) y recalcular momentum/RSI/ADX/Bollinger/Donchian
    sobre ESA serie semanal — cambia el ruido del indicador mismo, no sólo la
    ventana de evaluación. Mismo protocolo si se retoma: rank IC intra-semana con
    Newey-West, pre-registrado, Bonferroni por cantidad de factores testeados.
    Minutos/horas: no viable — el cache es sólo barras diarias (verificado,
    `AAPL.parquet` espaciado modal 1 día calendario/hábil), y datos intradía ya se
    descartaron con gap-reversion (§13).
21. 🟢 **Trial #15 EVT — CERRADO como inválido por diseño, causa raíz confirmada
    en código (2026-08-15)** — el re-run válido (post-fix EWMA, `trial15_evt_stops_20260814_195828.txt`)
    reportó NO CUMPLE (0/3 ventanas), y tanto OpenCode como Command Code lo verificaron
    contra n por ventana/win_rate del parquet y lo cerraron. **Ese veredicto no es
    utilizable**: no es que el sizing EVT pierda contra el baseline, es que el trial
    **nunca pudo medir la diferencia**.
    **CAUSA RAÍZ (Claude Code, 2026-08-15, confirmada leyendo `backtest_engine.py:439-443`
    y `trial_evt_stops.py`, no solo hipótesis)**: `compute_position_size` recibe SIEMPRE
    `win_prob` y `payoff_ratio` no-`None` desde el motor real → toma la rama Kelly →
    `return int(min(kelly_shares, shares_by_risk, max_shares))`. `kelly_shares` **no
    depende de `stop_distance`** (solo de win_prob/payoff_ratio/price/equity), y es el
    mínimo de los tres en la enorme mayoría de los trades — confirmado numéricamente:
    ejemplo AMD 2019-01-07, shares=60 real vs 2×ATR baseline=$2.84 (13.8% precio) vs
    stop_distance EVT implícito ≈$6.20 (30% precio) — ninguno de los dos coincide con
    lo que shares=60 produciría vía `shares_by_risk`; sí coincide con un `kelly_shares`
    de fracción ~4.9%. Confirmado también que NO es el tope de posición (`max_shares`):
    solo 15.3% de los 281 trades coinciden exacto con el tope, 24.2% con margen ±1 —
    la mayoría de los shares están MUY por debajo del tope, consistente con Kelly
    dominando, no el cap. Y `EVTRiskManager.check_all_stops` nunca se sobreescribe
    (llama a `super()` sin cambios, `trial_evt_stops.py:140-142`) — el cambio EVT SOLO
    podía tocar tamaño de posición, nunca cuándo entra o sale un trade, y ni siquiera
    eso llegó a expresarse por el `min()` con Kelly.
    **Confirmación independiente (Claude Code, 2026-08-15, reconstrucción completa
    de los 281 trades del parquet)**: (a) el término EVT `var_mult×σ_EWMA_día`
    (mediana 0.052, p90 0.091, max 0.266) **NUNCA superó** el floor
    `price×position_stop` ni el `2×ATR` (`evt_term > floor` = 0, `evt_term > 2×ATR` = 0
    sobre 281/281); (b) `max_shares ≤ shares_by_risk` en 281/281 (por álgebra:
    `0.5×E/P > 0.1×E/P` siempre dado el piso 0.03) → `shares_by_risk`, donde vive la
    variable EVT, nunca es binding. El 0/3 ventanas con métricas idénticas a 4
    decimales era la firma de esto: el sistema midiéndose a sí mismo.
    **Ningún n_trials se gasta por esto** — no es un trial nuevo, es la constatación de
    que el trial #15 tal como está pre-registrado en §20 no puede responder la pregunta
    que se hizo. Si se quiere retomar la línea EVT-stops, hace falta un pre-registro
    NUEVO que aísle `shares_by_risk` del `min()` con Kelly (por ejemplo corriendo con
    `fractional_kelly=0` para esta comparación específica) — decisión del usuario, no
    de un agente. **M0 queda CERRADO como "trial inválido, no concluyente"** — distinto
    de "EVT-stops no sirve". Sin bloquear nada más del plan de mecánica.
22. ✅ M1/M1b — auditoría de horizonte COMPLETA (2026-08-13, `PLAN_MEJORA_MATEMATICA.md
    §21/§21.1`): 5d/10d/60d/125d, ninguno significativo bajo Bonferroni-12. Los
    rechazos de señal se refuerzan en los 5 horizontes probados (5d-125d).
23. ✅ **M2 — contrafáctico de las 41 salidas por REGIME_STOP_HIT CERRADO (2026-08-14)**
    — pre-registrado en `AUDITORIA_MECANICA.md` (Fase M2), corrido
    (`diagnose_regime_stop_contrafactual.py`, artefacto
    `regime_stop_contrafactual_20260814_173001.txt`): **el stop está haciendo su
    trabajo**. Puerta de fidelidad: 152 posiciones naturales reproducen el parquet
    exacto. Solo 16/41 (39%) se habrían recuperado; delta total ≈ $0 (real
    −$5,867.12 vs cf −$5,867.15); 13/41 habrían llegado a ABSOLUTE_CEILING con
    pérdidas mucho peores. Per criterio pre-registrado (<50% recuperadas) → M3 NO
    se dispara (sin hipótesis que gaste un slot de n_trials); M4 tampoco. Con esto,
    del plan de mecánica queda solo M0 (el trial EVT en curso).
24. ✅ **M6 — Ledger de trials HECHO (2026-08-14, Command Code)** — `app/core/trial_registry.py`
    (lectura/escritura de `data/trial_registry.json`, `register_trial`/`trials_by_family`/
    `consumed_budget`/`current_threshold` con corrección Bonferroni), backfill de 29
    entradas desde `PLAN_MEJORA_MATEMATICA.md` + `RESUMEN_VALIDACION_VARIABLES.md`
    (`scripts/backfill_trial_registry.py`), auditoría `scripts/audit_trial_budget.py`
    (avisa si un trial nuevo excedería el umbral declarado), 15 tests. **HALLAZGO
    (contrato M6 — el desacuerdo ES el resultado)**: el backfill cuenta **27
    n_trials_consumidos** vs el **n_trials=17** citado en §6/§0.6.1/§20 (diferencia
    +10). El backfill NO se ajustó para cuadrar: 17 = los 13 trials #1-#13 contados
    en §6 + 4 sin slot (fix #10, re-tests Fase 0.6 #8/#9); 27 = los 13 + 8
    hipótesis de motor adicionales registradas (trial #14 basket, trial #15 EVT en
    curso, diagnóstico sectorial, re-evaluación #11.1, gap, sub-períodos, MA200,
    Donchian). El número 17 subestima el presupuesto real. Artefacto:
    `data/cache/trial_registry_backfill_audit_20260814_202751.txt`.

---

## Gantt — todas las vías abiertas

```mermaid
gantt
    title Roadmap fortress_core — todas las áreas
    dateFormat X
    axisFormat Sesión %d

    section Investigación / matemática
    §13 gap-reversion: backtest con costos reales   :active, gr1, 0, 1d
    §12 régimen-vs-volatilidad: más historia o menos estados HMM :gr2, 0, 2d
    Fase 0.6: re-test sentimiento/fundamentales (panel limpio) :gr3, 0, 1d
    Investigación académica/foros externa (pendiente, nunca hecha) :crit, gr4, 0, 1d

    section Código — P0 (bajo esfuerzo, alto impacto)
    Fix contrato GovernancePanel <-> backend      :done, c1, 0, 1d
    Fix except desnudo + errores como 200 OK      :done, c2, 0, 1d
    Auth mínima + SECRET_KEY que falla si no está :done, c3, 0, 1d

    section Código — P1
    Fechas hardcodeadas de market.py (2015-2024)  :done, c4, after c3, 1d
    Alinear Python Dockerfile vs venv real        :c5, after c3, 1d
    Corregir README (Redis, versión, endpoints)   :c6, after c3, 1d
    Corregir docstring Controller/Judge (no LLM)  :c7, after c3, 1d

    section Código — P2
    Tests de integración governance + routers     :c8, after c4, 2d
    Decidir destino de prompt_engine.py           :c9, after c4, 1d
    CI básico (lint + test en push)               :c10, after c4, 1d

    section Producto / decisiones pendientes
    Uso real de LEAN/QuantConnect (parqueado, sin objetivo definido) :p1, 0, 1d
    Conexión a broker (bloqueada hasta validar edge neto de costos)  :p2, after gr1, 1d
```

---

## Tabla maestra — todo lo abierto, con dueño y bloqueo

| Área | Ítem | Estado | Bloqueado por | Próxima acción |
|---|---|---|---|---|
| Integración indicAgent | PLAN_INTEGRACION_INDICAGENT.md — Fase 1 tickets T1.1/T1.2/T1.3 + Fase 2 T2.1 (Kilo Code) | 🟢 cerrados (2026-08-20) | — | **T2.1**: el corte train/test era contiguo sin purga → `purge_bars` en `WalkForwardValidator.validate()` (default=horizon, =0 reproduce pre-fix); 7 tests. **T1.1 OFI**: `ofi_*` en indicators.py + trial §37 → **NO_CUMPLE** 0/3 (TOTAL t −1.66); ledger signal_diagnosis 19→20. **T1.2 CVD**: `cvd_*` en indicators.py (decisión rolling-20d documentada en vez del reset intradía inaplicable) + trial §38 → **NO_CUMPLE** 0/3 (TOTAL t −0.73); ledger 20→21. **T1.3 market_structure**: module new with 4 detectors SMC + `analyze_market_structure` (18 tests, smoke real AAPL 0.17s) — descriptivo disponible, NO es señal (requiere trial propio si se usa). Suite 315 passed.
**Plan T1.1-T1.6 y T2.1-T2.3 COMPLETO** — T1.4, T1.5, T1.6, T2.2, T2.3 ver filas propias; ninguna integración al motor promovida a default (todas quedan disponibles/no promovidas hasta trial walk-forward). |
| Investigación | §13 gap-reversion: backtest con costos reales | 🟢 cerrado (2026-08-12) | — | NO CUMPLE: bruto ~0 (t-NW −0.20), neto −11.53 → §13 CERRADO (PLAN §13.1, artefacto backtest_gap_costs_20260812_173951.txt) |
| Investigación | §12 régimen-vs-volatilidad | 🟢 cerrado como pista sin acción (2026-08-12) | — | Decisión del usuario: sin TARGET_VOLATILITY, sin reducir HMM, sin esperar historia. Se retoma solo con pre-registro y razón nueva |
| Investigación | Fase 0.6 — re-test sentimiento/fundamentales | 🟢 cerrado (2026-08-12) | — | NO CUMPLE 0/3 ambas variantes (artefacto fase06_retest_20260812_175055.txt): V1 DSR 0.041/0.002/0.225, FUND 0.121/0.004/0.330 vs base 0.071/0.028/0.173 → refutación #8/#9 confirmada con vara arreglada; baseline universo 50 = único modo operativo |
| Investigación | Investigación académica/foros de trading cuántico | 🟢 cerrado (2026-08-12) | — | Informe completo en `RESEARCH_EXTERNA_CRITICA.md` (verificado): TradingAgents/FinCon validan el patrón multi-agente LLM; Barber-Odean 2000 + Taiwan 2008 + survival 44/24/15% confirman risk-mgmt-first; trading cuántico cerrado como no-relevante para 50 símbolos |
| Código P0 | Contrato GovernancePanel ↔ backend | 🟢 cerrado (2026-08-12) | — | Frontend consume contrato real (`triad.{bull,bear,contrarian}.score`, `controller.approved`, `judge.verdict|status`); 5 tests de regresión en `test_governance_contract.py` |
| Código P0 | `except:` desnudo + 200 OK con error en body | 🟢 cerrado (2026-08-12) | — | `market.py`/`live.py` ahora levantan HTTPException 500; `except:` acotado a (AttributeError, TypeError, ValueError); 0 patrones restantes en routers |
| Código P0 | Auth mínima global + `SECRET_KEY` que falla si no está seteado | 🟢 cerrado (2026-08-12) | — | `hmac.compare_digest` en `verify_api_key`; Settings valida SECRET_KEY fuera de development (default bloqueado: `test_secret_key_default_blocked_outside_development`). Nota: 25/27 endpoints siguen abiertos POR DECISIÓN (UI pública con repo público) — solo rutas de escritura RAG tienen key; el resto es deliberado mientras la UI sea pública |
| Código P0 | Brecha 5 auditoría externa — cierre superficie API (handover §6.1/§6.2) | 🟢 cerrado por verificación (2026-08-24, Cline) | — | Verificado contra código más nuevo (dd47569): NO existe endpoint de escritura sin auth — los únicos 2 no-GET (POST governance record-prediction/knowledge/add) ya tienen `verify_api_key`; SECRET_KEY validator (`_require_secure_secret_key`, config.py:75-84) vigente + test pasando. La lectura "36/38 sin acceso" de la auditoría cuenta GETs de lectura (públicos por decisión de producto). Aportación: INVARIANTE nuevo `tests/test_api_write_auth.py` (inventario de escritura == 2 POST; toda ruta no-GET debe depender de `verify_api_key`; mecanismo compartido hmac.compare_digest) — la suite falla si un endpoint de escritura futuro se agrega sin auth. 8/8 tests auth en verde (3 nuevos + 5 existentes), ruff limpio, control negativo verificado. AUDITORIA_TECNICA.md §6 sincronizado |
| Código P1 | H2.3 auditoría externa — predict.py descarga por request (~57/request en /universe) | 🟢 cerrado (2026-08-25, Cline) | — | Cache compartido `_get_data()` en predict.py — MISMO patrón que advisor.py::_get_context (TTL 300s + asyncio.Lock anti-manada + run_in_threadpool). `_load_universe_prices_sync` aplica el filtro >=200 filas a nivel loader; símbolo fuera del universo -> fallback directo offloaded; /macro-correlations comparte cache (trade-off documentado). Tests: `test_predict_cache.py` NUEVO (6: no re-descarga en TTL, una sola carga para /universe x2, expiración re-carga, fallback fuera-de-universo, series cortas) + reset de cache en test_predict_api. **11 passed**, ruff limpio |
| Código P2 | H8.2 auditoría externa — staleness del advisor ¿se renderiza? | 🟢 cerrado por verificación (2026-08-25, Cline): YA renderizado | — | Cadena completa confirmada: useAdvisorUniverse -> MesaPage.tsx:38 -> MesaView.tsx:48-54 banner amarillo "Cache desactualizado (+N ruedas)" cuando stale=true; test de contrato MesaPage.test.tsx:88 corrido por mí: 6/6 passed. Sin cambio de código — la premisa de la auditoría era falsa contra el código actual |
| Código P1 | Fechas hardcodeadas de `market.py` (2015-2024) | 🟢 cerrado (2026-08-12) | — | Las 4 rutas ahora usan `download_data(symbol, "2015-01-01")` sin fin fijo (mismo patrón que predict.py/governance.py) — default a hoy. 80/80 tests sin regresión |
| Código P1 | Python 3.11 (Dockerfile) vs 3.9.6 (venv real) | 🟢 cerrado (2026-08-12, commit `a56e516`) | — | Dockerfile fijado a `python:3.9-slim` — alineado con el venv real |
| Código P1 | README desactualizado (Redis, versión, endpoints) | 🟢 cerrado (2026-08-12, commit `a56e516`) | — | README sin Redis, versión 3.9, tabla con los 27 endpoints reales |
| Código P1 | Docstring Controller/Judge dice que usan LLM (no es cierto) | 🟢 cerrado (2026-08-12, commit `a56e516`) | — | Docstrings corregidos a "lógica determinista — no usa LLM" en `advanced_agents.py` |
| Código P2 | Tests de integración governance + 7 routers sin cobertura | 🟢 cerrado (2026-08-12, commit `6ae0770`) | — | Tests de integración para 6 de los 7 routers (test_backtest_api, test_market_api, test_live_api, test_predict_api, test_risk_api, test_system_api); governance y opportunities ya tenían |
| Código P2 | `prompt_engine.py` — 659 líneas muertas con bug adentro | 🟢 cerrado (2026-08-12, commit `6ae0770`) | — | Eliminado; `HardinessChecker` movido a `app/core/hardiness.py` (7 tests); `test_prompt_engine.py` eliminado |
| Código P2 | CI básico (lint + test en push) | 🟢 cerrado (2026-08-12, commit `6ae0770`) | — | `.github/workflows/ci.yml`: jobs lint (ruff) y test (pytest) en cada push/PR, Python 3.9 |
| Frontend | Dashboard completo rediseñado (estilo institucional) | 🟢 cerrado (2026-08-17) | — | Nuevo `Layout.tsx` con paneles colapsables, Header unificado, fix contrato GovernancePanel (triad/controller/judge/professor), URLs hardcodeadas eliminadas en SystemStatus/RiskPanel, index.css modernizado. Build OK (TS sin errores), 242 tests backend pass |
| Frontend | Dashboard institucional consolidado — advisor API + mesas por vista + Exit Thesis Monitor (Kilo Code) | 🟢 cerrado (2026-08-17) | Verificación visual del navegador HECHA (2026-08-19) — ver nota final | Consolidación del rebuild de Claude Code + plan Kilo sobre `frontend/` (sin rama aparte). Backend: router `/api/advisor` (universe/symbol/theses/evidence, solo lectura, reutiliza `_compute_ticket` de decision.py — cero reprogramación del motor) + 21 tests. Frontend: 4 vistas con lazy-loading (Mesa/Detalle/Portfolio/Gobernanza), tokens TradingView exactos (#131722/#1e222d/#26a69a/#ef5350), chart Lightweight Charts con EMA50/200 + zonas mecánicas (entry/stop 2×ATR/target 4×ATR) + widget TradingView secundario con degradación graceful, etiquetas proyectadas §29 pre-registradas (mapeo verificado contra `baseline_clean_20260811_150643_trades.parquet`: ≥0.70→VPP 87.5% n=8; ≥0.65→73.7% n=19; <0.45→RIESGOSA_SIN_APOYO sin afirmar pérdida), Exit Thesis Monitor (`decision_theses.json` atómico: se sale cuando se pierde la tesis), Evidence Footer vivo desde trial_registry, badge de honestidad global, chip de staleness (>2 ruedas), API URL vía VITE_API_URL. Code splitting: bundle principal 624 kB → 152 kB. Acceptance: 263 tests backend, ruff limpio en archivos nuevos, tsc+build OK, endpoints crudos verificados en vivo (universe 44 símbolos régimen 2, CVX detalle 400 barras EMAs consistentes con gates, AAPL fundamentals EDGAR, theses, evidence tolerante a umbral str). Campo costo/trade RESUELTO por la Tarea E (2026-08-19) — ver fila propia. **UNIVERSE 44 EXPLICADO (2026-08-19, Tarea F)**: el endpoint iteraba `opportunities.SYMBOLS`, lista curada HARDCODED de 44 (distinta del universo 50 de investigación) — **NO era bug**, era duplicación manual. **FIX APLICADO (2026-08-19, decisión de Boris "los 50")**: módulo canónico `app/api/routes/opportunities_universe.py` deriva SYMBOLS desde `scripts/fetch_universe_data.NEW_UNIVERSE` (fuente única) + 7 base = **50** con dedup y fallback; opportunities/decision/advisor conectados vía re-exportación. Verificado en vivo: `/api/advisor/universe` → **50 states** (AMD/CMCSA/DIS/INTU/META/PFE/QCOM/SPGI/TSLA presentes, ABT/GS/WFC fuera), régimen STAGFLATION sin cambio, suite 271 passed. **VERIFICACIÓN VISUAL DEL NAVEGADOR (2026-08-19, Tarea G, OpenCode)**: stack levantado (uvicorn :8000 + vite :3000) y 4 vistas inspeccionadas vía Chrome headless + CDP (DOM renderizado post-fetch + logs de consola). Mesa/Portfolio/Gobernanza cargan sin errores de consola; Detalle renderiza chart Lightweight Charts (canvas, EMA50/200) + Zonas mecánicas + M2 + Plan de salida 4 mecanismos (partial tp/trailing/technical/regime stop) con datos reales; CostField visible en todas las vistas con datos reales: `COSTO REAL/LADO: 0.017% · n=156 · q1: 0.019% · q10: 0.013% · q50: 0.004%`; badge honestidad + chip staleness presentes. **HALLAZGO (no bloqueante, backend — NO arreglado en esta tarea)**: `/api/advisor/AAPL` tarda ~80s (vs MSFT 2.8s) porque `_compute_ticket` intenta descargar de Yahoo símbolos fantasma (`$BASELINE_CLEAN_..._EVENTS`, `$COT_2019`, etc.) que dan timeout de red ~1s c/u — es costo de arranque/cache fría del endpoint de detalle, no del frontend; el chart aparece al completar. **RESUELTO 2026-08-21 (Tarea K, Cline) — ver fila propia más abajo en esta tabla. Ver SESSION_LOG. **TAREA F (2026-08-19, Kilo Code) — DIAGNÓSTICO universe 44 vs 50**: NO es bug. El endpoint usa `opportunities.SYMBOLS` (44, lista curada hardcoded), NO el "universo 50" (BASE_SYMBOLS 7 + NEW_UNIVERSE 43 de `fetch_universe_data.py`/`measure_execution_costs.py`) que usan los trials de investigación. Verificado empíricamente: los 44 de SYMBOLS pasan el filtro `len(df)>200` de `load_universe` (0 descartados) → el endpoint devuelve los 44 definidos. Diferencia de listas: en 50-no-44 = [AMD, CMCSA, DIS, INTU, META, PFE, QCOM, SPGI, TSLA]; en 44-no-50 = [ABT, GS, WFC]. Artefacto: `data/cache/diagnostico_universo_20260819_174613.txt`. Acción (no aplicada, es diagnóstico): si se quiere cubrir los 50, cambiar `opportunities.SYMBOLS` al universo 50; si no, documentar 44 como universo de decisión intencional. |
| Perf | `/api/advisor/{symbol}` ~80s en frío por símbolos fantasma (Tarea K, Cline) | 🟢 cerrado (2026-08-21) | — | TRAZA confirmada: la ruta Yahoo←cache era el glob de `_cache_date()` (advisor.py) que trataba artefactos de trials como símbolos; el fix (entrado en commit `d2819ab` junto al barrido live/market/predict) itera SOLO `SYMBOLS + MARKET_TICKERS` del universo canónico (`opportunities_universe.py`, fuente única de Tarea F) — cero heurística de nombre de archivo, y toda la cadena `advisor→decision→opportunities→load_universe→download_data` usa listas canónicas (ningún glob llega a Yahoo). Verificado: `data/cache/` sin artefactos (60 parquet = tickers reales), `_cache_date()` 0.37s. Medición fría real (contexto vacío): AAPL 276s ≈ MSFT 252s — **la asimetría del bug desapareció**; el costo restante es el refit de calibradores (~4 min compute local, idéntico para cualquier símbolo), que el cache TTL 5min de `_get_context` paga una sola vez por proceso: AAPL caliente **1.36s** (~= MSFT 2.8s histórico, medido caliente). Test nuevo `test_cache_date_ignora_artefactos` (parquet BASELINE_CLEAN/COT/CAPITAL_USAGE con fecha 2030 en cache de test → cero llamadas a yfinance y no contamina la fecha del cache); suite advisor **22 passed** (Python 3.9). Limpio `import glob` muerto de advisor.py. Detalle en SESSION_LOG 2026-08-21. Sin commit/push (regla de la ronda). |
| Perf | `GET /api/advisor/universe` ~18 min frío / 3:20 caliente con 102 símbolos (2026-09-02, Cline) | 🟢 cerrado por verificación — cuello #1 + #2 (2026-09-03, Cline) | — | **Cuello #2 cerrado 2026-09-02** (cache de tickets + sig_evaluated + ema() directo): 2da llamada caliente 1.034s vs 138.6s (~134x), payload idéntico, 25/25 tests, threads descartados con evidencia (GIL 0.8x). **Cuello #1 cerrado 2026-09-03** (decisión Boris: opción 4b paralelizar, NO opción 4a TTL porque rompía "en vivo" del dashboard — doctrina §8 AGENTS.md "siempre lo sólido, no lo más fácil"): helper top-level picklable `_calibrate_symbol()` + `ProcessPoolExecutor` con `n_workers=min(os.cpu_count(), N)` cuando `update_bayesian=False` y N≥8. Update_bayesian=True mantiene la rama serial (warm-start bayesiano es estado compartido, preservado exacto). Mediciones reales con cache parquet (102 símbolos): replay paralelo **392.77s** vs ~20 min diagnóstico original = **3.06×**, subset 30 = **4.41×** (522s → 118s). **Identidad bit-a-bit verificada**: hash SHA-256 del dataset (scores+outcomes) idéntico serial vs paralelo (`bff254c92e2fd890...` para 30, `6e2b0f0a279b85f3...` para 102). Tests nuevos: `tests/test_calibration_parallel.py` (5/5 passed): identidad, branching update_bayesian, umbral, determinismo del helper, guardián anti-vacío (fix 2026-09-04: el fixture pasaba OHLCV crudo en vez de indicators_cache, dataset comparaba dos arrays vacíos). Suite advisor completa 25/25 sin regresión. Implicancia operativa: `/api/advisor/universe` en frío total ~18 min → **~9 min** (replay ~6.5 min + loop tickets ~3 min ya cacheado por cuello #2). Detalle: `DIAGNOSTICO_PERF_ADVISOR_102.md` §"Decisión tomada" |

| Producto | `signal_engine.py` comentario/cita falsa sobre ADX | 🟢 cerrado (2026-08-16, commit `243e19f`) | — | Comentarios corregidos en `signal_engine.py` (líneas 16-25 y 51-59): afirmaban "adx mostró IC negativo" cuando el artefacto corregido (§0.5a, `rr2_intraday_20260811_150741.txt`) mide **IC +0.0679, t=+2.31 nominal — POSITIVO, único factor con señal nominal**, marginal no robusto bajo Bonferroni-4 (≈2.5). La cita repetía la auditoría pooled vieja (metodología descartada). Verificado: suite completa 216 passed |
| Producto | LEAN/QuantConnect | ⚪ parqueado, uso futuro pretendido (2026-08-14) | Datos ampliados si crece el universo, o ejecución real si hay señal validada | Imagen Docker (42.5GB) borrada del disco local por espacio — recuperable gratis con `docker pull` cuando se retome. No tocar hasta que aparezca uno de los dos disparadores |
| Infraestructura | **Auditoría completa de automatización (launchd) y almacenamiento** (2026-09-03, Kilo Code) | 🟢 cerrada — 2 fixes aplicados | — | Inventario 10 plists repo vs 11 cargados, cero drift de contenido, crontab vacío. **Fix 1**: `fundamentals_screen` commiteado pero nunca cargado → verificado no-destructivo (solo escribe artefactos+logs, cuota FMP protegida, RunAtLoad=false) y **cargado con `launchctl load -w`** (primera corrida 22:30, confirmar 09-04). **Fix 2**: `intraday`+`autobackup` cargados pero SIN plist en repo (drift inverso — restaurar desde GitHub los perdía) → copiados a `scripts/` y commiteados; 12/12 jobs versionados. `daily_notify` sigue sin cargar BY DESIGN (TELEGRAM/SMTP vacíos). Almacenamiento: interno 83Gi libres (umbral diskhealth 15GB, 5.5× holgura), externo 1.8Ti; `backend/data/cache` 65MB creciendo **~5-6MB/sem (~300MB/año)** a ritmo 102 símbolos+intradía 7 símb/30min+screen diario — sin acción requerida. Bóvedas verificadas idénticas byte a byte en EMPRESA (Permission denied 01/09 fue puntual del montaje). Doc completo: `AUDITORIA_AUTOMATIZACION_ALMACENAMIENTO.md` |
| Auditoría | **Auditoría integral del sistema, óptica Simons** (2026-09-03, Kilo Code) | 🟢 cerrada — hallazgos D1-D12 verificados | — | Complementa AUDITORIA_NIVEL_DIOS (F0 ya ejecutada, F1.6 HMM ya ejecutada 93b5718). **Nuevos críticos, todos spot-checkeados contra código**: D1 capa multi-agente LLM NO se importa en el pipeline diario (solo SignalEngine decide el dinero — la gobernanza es fachada de dashboard); D2 `reconcile_open_positions` SIN caller productivo → condición (c) del gate ("sin órdenes huérfanas") inejecutable, contador de racha contaminado de origen; D3 sin kill-switch ni alertas (divergencia PnL no detiene nada); D4 loop de aprendizaje vacío (record_prediction solo manual, historial n=0); D5 DSR motor DEFAULT_N_TRIALS=5 vs 51 reales (sub-deflaciona); D6 PBO §39 entra lag-0 al cierre (inconsistente con T0.2); D10 sizing sin estructura de cartera (8 factores RMT huérfanos); **D-opciones: análisis de opciones con presencia CERO en el repo** (sin BS/IV/griegas — familia ausente entera). Recomendación única: cerrar el loop de ejecución ANTES del gate (reconciler en pipeline + kill-switch + telemetría fills + hash-guard motor + DSR n_trials unificado) — es construcción permitida; post-gate abrir opciones y meta-labeling (I5) como familias nuevas pre-registradas. Doc: `AUDITORIA_INTEGRAL_SISTEMA_20260903.md` |
| Plan | **PLAN_REMEDIO_BRECHAS_20260903.md** — remedio completo de las 4 brechas de capacidad (2026-09-03, Kilo Code) | 🔵 plan aprobado-pendiente, Fase A ES ESTA SEMANA | Boris aprueba explícitamente por fase | Fase A (gate-permitida, esta semana): **A0 harness de integridad del cache de datos yfinance — PRECONDICIÓN, bloquea A1** (contaminación cruzada verificada: 3 clusters 24-26/ago, 31/ago, 1/sep 2026, ≥38 barras completas de OTROS símbolos congeladas en 29 parquets por el diseño append-only de `data_ingestion.py` — ej. KO con la barra exacta de CRM, CMCSA con +622.9% falso que era la barra de PM; ya saneado a mano pero el diseño sigue intacto; más 64 huecos de fechas en 57/102 símbolos nunca reparados. Alcance, ver `COMPARACION_FUENTES_DATOS.md` §10/§10.3 y ticket completo en `PLAN_REMEDIO_BRECHAS_20260903.md`: (1) validador de sanidad de retornos >15-20% large-cap en cada actualización, (2) reconciliación cache-vs-yfinance-fresco para contaminación/mosaico/huecos con re-descarga dirigida, (3) snapshot/hash del cache por trial para reproducibilidad, (4) cross-check Finnhub↔FMP diferido hasta resolver el desborde de cuota (510 llamadas necesarias vs 250/día límite FMP). Bloquea A1 porque el reconciler y el contador de días limpios no son confiables sobre un cache que puede tener barras cruzadas o huecos sin detectar), A1 reconciler en pipeline 22:10 (D2), A2 contador de días limpios AUTOMÁTICO con evidencia por condición, A3 kill-switch pre-registrado (DD>10%, PnL<−3σ, fill<80%, staleness>2 ruedas; STOP_FILE que frena entradas nuevas, nunca EXIT), A4 hash-guard sha256 del motor en fase health (contador reinicia solo si cambio declarado), A5 telemetría decision-vs-fill por orden → tabla execution_telemetry (libro de costos propio I9), A6 DSR n_trials=None→ledger (D5), A7 enforcement técnico del gate en trial_registry (rechaza trials nuevos en ventana salvo bugfix/infra), A8 nota lag-0 §39 + pre-registro post-gate (D6), A9 flag GOVERNANCE_LLM_ENABLED=false (D1 honesto). Fase B (paralela, datos/tooling): B1 colector intradía 7→30, B2 colector superficie IV yfinance 22:35 diario (familia opciones empieza a acumular HOY), B3 feature store versionado I6, B4 holdout sellado 2025-09-01 (I7), B5 MDE ex-ante hook en pre-registro (I1 — fin refutación-teatro), B6 contrato de señal única SOLO con golden bit-idéntico, B7 point-in-time opcional. Fase C: evaluación 1/12 o contador≥60. Fase D (post-gate, pre-registradas): D1 meta-labeling I5 → D2 opciones VRP/GEX/PEAD-options, D4 shrinkage James-Stein I4, D6 neutralización RMT; D3 intradía genuina, D5 multivariada tras D1. **Urgencia**: cada día sin A1/A2 es un día que el contador mide sin verificar (c) — la fecha real de evaluación es max(2026-12-01, arranque + 60 días VERIFICADOS) |
| Producto | Conexión a broker real | 🔴 bloqueada, correctamente | Validar edge neto de costos primero (§13) | No avanzar hasta cerrar investigación. **Insumo listo para cuando se desbloquee** (§33.1, PLAN_MEJORA_MATEMATICA.md, evidencia JoF 2025 verificada): ranking de brokers por calidad de ejecución medida — TD Ameritrade (7.2bps RT) y Fidelity (19.7bps) en el extremo bueno; IBKR Lite/Pro (44-46bps) en el extremo malo; Alpaca/Schwab no estudiados directamente, Schwab con indicios de estar en el grupo bueno. No repetir esta investigación cuando llegue el momento |
| Seguridad | **`fortress.db` (SQLite local) nunca se respalda** | 🟢 cerrado (2026-08-12, commit `217eb51`) | — | `backup_db()` en `auto_backup.sh` + paso 6.5 en `backup.sh` (`sqlite3 .backup` → `/Volumes/EMPRESA/fortress_core_backups/db/`, retención 20). Verificado: snapshots cada ~10 min en disco externo, launchd instalado |
| Seguridad | GET endpoints sin auth que disparan LLM real (costo/abuso) | 🟢 mitigado (2026-08-12, commit `217eb51`) | — | Rate limit en memoria (10 llamadas/60s por IP) aplicado vía `RateLimitDependency` en `routes/predict.py` y `routes/governance.py`. Sin auth completa por decisión (UI pública); el rate limit acota el abuso de costo. Test: `test_rate_limit.py` |
| Código P2 | Código muerto adicional (`ProbabilisticEngine` wrapper, `KellyPositionSizer`, `RiskParityAllocator`) | 🟢 **ELIMINADO (2026-08-15, Claude Code)** | — | Verificado por M8 (Command Code, solo documental), decisión y ejecución de Claude Code. `KellyPositionSizer` y `ProbabilisticEngine` borrados de `probabilistic_engine.py` (quedan las 6 clases vivas: ProbabilityCalibrator, SignalQualityMetrics, BayesianOnlineUpdater, FatTailMonteCarlo, CopulaRiskAnalyzer, WalkForwardValidator — secciones renumeradas 1-6). `risk_parity.py` eliminado completo (archivo entero muerto). Los 2 smoke scripts NO se borraron enteros (a diferencia de `prompt_engine.py` en Tanda C) — mezclaban código vivo y muerto: se recortó solo `test_kelly`/`test_integrated` de `test_probabilistic.py` y `test_risk_parity` de `test_system.py`, conservando la cobertura smoke de lo que sigue vivo. Verificado grep repo-wide (0 referencias restantes salvo el propio docstring explicativo), ambos scripts corridos end-to-end tras el recorte, suite completa 206 passed, ruff limpio. |
| Instrumento | M1 — Etiquetado por barreras | 🟢 hecho (2026-08-14) | — | `app/core/barrier_labeling.py`, replica las 4 barreras reales de `adaptive_risk.py` en orden de prioridad; 17 tests de fidelidad (no cobertura). Ver `DISENO_INSTRUMENTO.md` |
| Instrumento | M2 — Instrumento conforme (abstención calibrada) | 🟢 hecho (2026-08-15) | — | `app/core/conformal.py`, Split Conformal Prediction, 16 tests (cobertura empírica ≈nominal verificada). Métrica primaria `vpp_bajo_abstencion`, no Sharpe |
| Instrumento | M3 — Compuerta de régimen | 🟢 hecho (2026-08-15) | — | `app/core/regime_gate.py`, walk-forward con assert anti-lookahead, 8 tests. Infraestructura lista; el TRIAL que pruebe macro IC +0.198 GOLDILOCKS/−0.173 DEFLATION como compuerta sigue sin pre-registrar — decisión del usuario |
| Instrumento | M4 — Costos medidos (Alpaca paper) | 🟢 cerrada la medición viva qty=1 (2026-08-18) | — | `app/core/execution_costs.py` (15 tests), runner corrió y completó tras 3 fixes del cliente Alpaca: (1) el último trade se pide a `data.alpaca.markets/v2/stocks/{sym}/trades/latest` — el viejo endpoint `paper-api.../v2/last/trade/` daba 404 (el crash de 2026-08-18); (2) las órdenes paper no vuelven con fill en la respuesta (nacen `pending_new`) → polling hasta filled con deadline 30s; (3) normalización de símbolos `BRK-B`→`BRK.B` (la API de datos rechaza el guion con 400). **Resultado medido**: 120 órdenes paper (60 buy + 60 sell, los 50 símbolos del universo), `cost_per_side_medido = 0.000189` (≈0.019%), slippage p50=0.000122, p95=0.000519, comisión=0 (paper sin comisión). Artefacto: `data/cache/measure_execution_costs_20260818_134338.txt` + DB `data/cache/execution_costs.db`. **CAVEAT registrado**: es costo de ejecución PAPER — fills instantáneos a último trade sin comisión; la ejecución live real tendrá más slippage y comisión ≠0. Útil como piso inferior medido, no como número final. **COST_PER_SIDE ACTUALIZADO (2026-08-19, §33)**: de 0.0015 asumido a **0.0005** (0.05%/lado) por decisión del usuario — punto medio conservador ~2.6× sobre el piso paper medido; suite 271 passed. **Tarea E (2026-08-19)**: campo de costo real construido en el dashboard sobre esta medición (`/api/costs/current`, solo lectura) — ver fila Tarea E |
| Instrumento | Tarea D — Curva de costo por tamaño qty=10/50 (Ronda 2026-08-19, Kilo Code + OpenCode) | 🟢 cerrada (2026-08-19) | — | Código: `backend/scripts/measure_execution_costs.py` (parametrizado `--qty`) + `execution_costs.py`, 21 tests costs (incl. 6 de Tarea E). **Pre-registro + resultado: PLAN_MEJORA_MATEMATICA §30**. Bloqueo real diagnosticado: el 403 NO era permisos — era `insufficient buying power` (la corrida qty=10 de la mañana entró en 18 símbolos, $81k, cash −$56k, BP 0). Se liquidaron los residuos (paper) → BP $100k y se corrió la medición completa (mercado abierto 12:13–12:14 ET): qty=10 (7 BASE_SYMBOLS buy+sell) y qty=50 (SPY+QQQ buy+sell; AAPL 50 falló por BP → fallback previsto en Enmienda 1). **Curva real (156 órdenes, fórmula contrato M4, size=1 verificado idéntico al artefacto 18/08)**: qty=1 p50 0.000122/p95 0.000519 (n=120); qty=10 p50 0.000116/p95 0.000417 (n=32); qty=50 p50 0.000029/p95 0.000098 (n=4). **VEREDICTO: curva plana/decreciente — impacto de mercado NO medible en rango 1→50; qty=1 es representativo (0.019%/lado)**. `COST_PER_SIDE` actualizado a **0.0005** (2026-08-19, §33, decisión del usuario) — ver fila M4. Endpoint `/api/costs/current` ya expone la curva (sizes 1/10/50) sin cambios de contrato |
| Producto | **Frente 2 S1 — Conector ejecución paper + ledger de órdenes** (PLAN_MAESTRO_FASE_PRODUCCION, Cline) | 🟢 hecho (2026-08-25) | Pipeline diario (OpenCode) | `AlpacaPaperClient.get_account()` (GET /v2/account) y `.get_positions()` (GET /v2/positions; símbolos `BRK.B`→`BRK-B` al formato interno, misma convención de `last_trade_price`) siguiendo el patrón de submit_market_order/last_trade_price. `SignalLedger` extendido ADITIVAMENTE (migración robusta por PRAGMA, NO rompe el record() T1.6 sobre DB pre-migrada — cubierto por test): columnas `status/open_fill_price/close_fill_price/qty` + métodos `open_order()`/`close_order()`/`open_orders()`. Nuevo `app/core/paper_trading.py::PaperTrader`: abrir orden→fila `open`; cerrar→completa pnl_r+close_fill_price; `reconcile_open_positions()` cierra órdenes contra el estado real del papel (fallback a último trade). **FIX de tests**: record() tenía COALESCE(columna,...) dentro del VALUES del INSERT OR REPLACE — SQLite NO resuelve columnas en VALUES (`no such column`); reescrito como upsert `ON CONFLICT DO UPDATE` que además preserva los fills al re-etiquetar. 6 tests nuevos contra fakes (jamás red); suites relacionadas 53 passed; ruff limpio. Motor de decisión y signal_engine.py INTACTOS |
| Producto | **Frente 2 S2 — Mecanismo del reporte mensual por variante** (PLAN_MAESTRO_FASE_PRODUCCION, Cline) | 🟢 hecho (2026-08-26) — listo, espera historial real | Pipeline diario con datos (OpenCode) | Construcción pura: NO toca trial_registry.json, NO consume presupuesto Bonferroni, sin pre-registro. `app/core/monthly_report.py::MonthlyReporter`: agrupa filas CERRADAS del signal_ledger por MES DE CIERRE × VARIANTE (de `factors_json["variant"]`, default `mom_rsi_congelada` — hoy el pipeline corre esa única definición), calcula Sharpe REALIZADO nativo por-oficio (mean/std ddof=1 de pnl_r; anualizado solo como referencia) y lo compara contra la EXPECTATIVA de la validación OOS congelada (`backend/config/expected_sharpe.json`, semilla: Sharpe mensual 0.3838 / anualizado 1.3296 de validacion_oos_fresca_20260822). Veredictos: EN_CALIBRACION (≥ umbral×esperado, umbral parametrizable default 0.5), DEBAJO_ESPERADO, NEGATIVO, SIN_DATOS (<2 oficios), DEGENERADO (std=0), ESPERADO_NO_DEFINIDO + diagnóstico liviano de una línea. Bitácora ACUMULADA en tabla propia `monthly_report_log` (fortress.db, upsert idempotente por variante+mes). Runner CLI `scripts/monthly_report.py`. Limitación documentada en el docstring: Sharpe por-oficio ≠ Sharpe cartera mensual hasta acumular meses. Smoke end-to-end verificado con DB sembrada (3 meses → 3 veredictos + bitácora); 11 tests nuevos contra fixtures, suite amplia 43 passed, ruff limpio |
| Infraestructura | **Frente 2 — Pipeline diario launchd (com.fortresscore.pipeline)** | 🟢 instalado 26/08 16:42 · verificado 27/08 11:34 — ORDEN INVERTIDO vs plan (ver detalle) | — | Instalado 26/08 16:42 (auto-backup 52c20a4) ANTES de checkpoint Semana 1 verificado 27/08 — quiebra PLAN_MAESTRO_FASE_PRODUCCION.md que exige checkpoint antes de instalar cron. Kickstart `launchctl kickstart -k gui/501/com.fortresscore.pipeline` 27/08 11:33:57 → runs 0→1 LastExit 0, Fase health (fuera de ventanas), artefacto pipeline_run_health_20260827_113404, pipeline_diario.log 2541→3300 B rc=0, pipeline_launchd.log 0 B BY DESIGN (todo redirige a pipeline_diario.log, mismo patrón que data_updater). Cache 6d at limit (último 21/08). Verificado end-to-end; no bloquea Semana 2 pero rastro corrige orden. Logs: scripts/pipeline_diario.log (canónico) + backend/data/cache/pipeline_run_*. |
| Infraestructura | **Bug data_ingestion gap >7 — cache stale 6d invisible** | 🟡 fix listo para revisión 27/08 (NO mergeado, pendiente gate) — 2 umbrales corregidos + señal explícita + 11 tests | Gate de aprobación antes de merge a main | `data_ingestion.py:31,42` `>7`→`>=1` (backfill y refresh, justificación daily updater, >=1 lee intención mejor que >0) + logs `[data_ingestion]` distinguen `attempting`/`attempted but empty`/`no new rows`/`no refresh needed`/`cache miss` (edge df.empty). Test `test_data_ingestion.py` 11 tests (gap 2 habría sido saltado con >7, gap1/0, empty/dedup). Suite 467 collected, batched 467 passed (full run >600s por heavy tests, batched OK). Vivo: AAPL 2026-08-21→2026-08-26 (3 filas 24-26, 2926→4187 con backfill 1258) tras fix; 2da corrida gap1 log distinto. Diff pendiente, no commiteado. |
| Infraestructura | **Garantías anti-evasión Bonferroni familia `re_test`** (H3.1 auditoría GLM, Cline) | 🟡 hecho en worktree — espera merge (2026-08-26) | Aprobado por Boris (2026-08-26): implementar §4.1+4.2+4.3 del análisis (`ANALISIS_RE_TEST_BONFERRONI.md`) | `trial_registry.py`: (1) `re_test_de` obligatorio cuando `familia=re_test` — objetivo existente y ANTERIOR en el registro, veredicto NO_CUMPLE, familia de investigación (no `producto`, no cadenas re_test); (2) tope `MAX_RETESTS_PER_TARGET=2` por objetivo (subirlo = decisión explícita visible en diff); (3) `n_trials_consumidos=0` solo legal en `re_test` (cierra el vector real: cero libre en cualquier familia). Invariante cruzado corriendo tanto en `register_trial()` como en carga completa (`_load_raw`) — un JSON editado a mano también explota. Backfill actualizado: las 2 entradas históricas citan su objetivo real (`fase06_retest_sentimiento`→`trial_08_sentimiento`, `fase06_retest_fundamentales`→`trial_09_fundamentales`, existencia verificada antes de escribir). Tests: 8 rutas pedidas + 2 existentes ajustadas al contrato nuevo; suite completa **420 passed**, ruff limpio. Verificado sobre copia en /tmp: ledger sin migrar falla ruidoso; con las 2 líneas migradas carga completo (47 entradas). **PENDIENTE AL MERGEAR**: migrar el `trial_registry.json` de producción agregando los 2 campos `re_test_de` (2 líneas, sin más), porque el código nuevo rechaza el archivo sin ellos POR DISEÑO |
| Auditoría | **AUDITORIA_NIVEL_DIOS_20260902.md** — auditoría cuant integral (4 líneas paralelas + verificación directa de código) | 🟡 informe emitido, plan propuesto (2026-09-02) | Decisión de Boris sobre qué fases ejecutar | Hallazgos críticos verificados: bug pnl_r=0 en `paper_trading.py:114-119`; motor heurístico no validado expuesto en /predict-family; bootstrap sin seed `backtest_engine.py:697`. Fases 0–3 propuestas en el documento (F0: fixes inmediatos; F1: integridad aparato; F2: diseño muestral/holdout/universo ampliado; F3: intradía vía LEAN). Regime matching: pausa de pilotos hasta pre-registro de graduación |


| Instrumento | M5 — Detector de deriva | 🟢 hecho (2026-08-15) | — | `app/core/drift_detector.py`, OpenCode, KS+Bonferroni+concepto, 18 tests, abstención con n<30 |
| Instrumento | M6 — Ledger de trials | 🟢 hecho (2026-08-14) | — | `app/core/trial_registry.py` + backfill 29 entradas. Hallazgo: 27 n_trials consumidos vs 17 citados — ver `SESSION_LOG.md` |
| Instrumento | M7 — Pipeline integrado M1+M2+M3 | 🟢 hecho (2026-08-15) | — | `app/core/diagnostic_pipeline.py`, `run_diagnostic_pipeline()`, 10 tests. Instrumento diagnóstico completo (M1-M8) cerrado. Falta el TRIAL pre-registrado que lo use para afirmar algo — decisión del usuario |
| Investigación | Trial #15 EVT — stops EVT walk-forward (M0) | 🟢 cerrado (2026-08-15) | — | NO CUMPLE 0/3 (DSR 0.0649/0.0253/0.1602, artefacto trial15_evt_stops_20260814_195828.txt). Fase 1 EVT cerrada: §19 diagnóstico PASA + §20 trial NO CUMPLE |
| Investigación | §22 Lead-lag entre símbolos (Tarea C, Command Code) | 🟢 cerrado (2026-08-15) | — | NO CUMPLE: 10 pares × 5 lags, ningún par con ≥2 lags consecutivos SIG(+) bajo Bonferroni-50 (|t|>3.48). Hipótesis de lead-lag refutada con la vara más estricta. Artefacto lead_lag_20260816_090220.txt. Registrado en ledger (signal_diagnosis) |
| Investigación | §23 Triple Barrier como target (Tarea A, Cline) | 🟢 cerrado (2026-08-16) | — | NO CUMPLE: re-test de 3 factores refutados (momentum/rsi/adx) contra el label de barrera M1 (en vez de fwd_return_20d), Bonferroni-9 (|t|>2.77). Ningún cruce con signo esperado; máx |t| momentum TOTAL −2.48 (signo −). "Generador vacío" confirmado también contra el target binario que el motor persigue. Artefacto retest_triple_barrier_20260816_091649.txt. Ledger signal_diagnosis n=1 |
| Investigación | §28 Test justo doble — rank IC contra retorno RELATIVO + AAII como timing de fecha (Kilo Code) | 🟢 cerrado — NO CUMPLE (2026-08-17) | — | Motivación del usuario: "es más fácil descartar que aprobar — medir bien, no con la vara fácil". Dos mediciones que nunca se habían hecho: (A) rank IC momentum/rsi/adx vs `fwd_rel = fwd_return_20d − SPY_fwd_20d` (el confusor §6.2 resuelto): 0/3 todos, t casi idénticos a los absolutos → la hipótesis "parecía débil por medir absoluto" REFUTADA con el test correcto; (B) AAII como timing de fecha (constante por fecha, verificado nunique=1 — los tests anteriores lo medían donde no podía variar): contrarian signo −1, 0/3 (W2 t=+2.94 con signo POSITIVO, no re-signable). Bonferroni-12 \|t\|>2.86 pre-registrado, fidelidad §0.5a exacta. RESUMEN §5 ítem cross-sectional: PROPUESTA → PROBADO Y REFUTADO. Artefacto `trial_xsec_relative_20260817_184355.txt`. Ledger signal_diagnosis: 17→18, umbral 0.994737 |
| Investigación | Tarea B PASO 1 — pipeline FinBERT earnings (OpenCode) | 🟢 hecho (2026-08-16) | — | `backend/app/core/earnings_sentiment.py` (store SQLite dedup por accession + fetch SEC EDGAR 8-K 2.02 + FinBERT ProsusAI/finbert, score=prob_pos−prob_neg ponderado por longitud), CLI `scripts/accumulate_earnings_sentiment.py`, 25 tests → suite 241 passed, ruff limpio. Acumulación completa universo 50: 48/48 símbolos, 369 filings, 0 errores (`earnings_sentiment_run_20260817_120713.txt`) |
| Investigación | Tarea B PASO 2 — trial sentimiento earnings (§27, Kilo Code) | 🟢 cerrado — NO CUMPLE (2026-08-17) | — | Contrato de datos (≥8 trimestres × ≥30 símbolos) desbloqueado y verificado. Event study pre-registrado en §27: pendiente HAC rel(SPY)~score por ventana E1/E2/E3, Bonferroni-9 |t|>2.77 signo + → **0/3** (t +0.38/−0.85/−0.08; spearman +0.05/−0.11/+0.03; signo inconsistente). El tono del comunicado 8-K 2.02 no predice retorno relativo a 20 ruedas. Línea cerrada con la evidencia EDGAR-proxy + 2 años + universo 50; acumulación incremental se conserva (no se borra). Artefacto `trial_finbert_eventstudy_20260817_163512.txt`. Ledger signal_diagnosis: 16→17, umbral 0.99444 |
| Investigación | Trial #16 — abstención calibrada M2 contra baseline real (pre-registro §24) | 🟢 cerrado como trial inválido, no concluyente (2026-08-17) | — | Corrido (`trial_m2_abstencion.py`, artefacto trial16_m2_abstencion_20260817_100548.txt): VEREDICTO FORMAL NO_CUMPLE pero **TAUTOLÓGICO** — abstención 100% en ambas ventanas (n_operados=0). HALLAZGO ESTRUCTURAL DE M2: (1) el ancho del intervalo NO depende del score (residuos absolutos + regresión lineal → ancho constante 2q → abstiene todo o nada, incapaz de abstención diferencial); (2) el default `max_interval_width=2×median` es SIEMPRE < 2×cuantil(91.5%) → 100% de abstención garantizada por construcción (reproducción mínima: 28/28). Cobertura empírica en rango (0.84/0.89) — el instrumento está bien calibrado y aun así nunca opera con su default. Los 16 tests no lo detectaron (fijan max_interval_width explícito). Hipótesis SIN MEDIR, no refutada. Ledger motor_signal: 8→9 consumidos. RESUELTO EN CADENA por el #17 (§24.1) |
| Investigación | Trial #17 — re-trial abstención M2 con instrumento CORREGIDO (pre-registro §24.1) | 🟢 cerrado — hipótesis REFUTADA (medida, no tautológica) (2026-08-17) | — | M2 corregido ANTES del trial (residuos relativos + default = p90 del ancho de calibración + test de regresión de abstención diferencial; suite 242 passed). Corrido (`trial_m2_abstencion.py` → trial17_m2_abstencion_20260817_104452.txt): el fix FUNCIONA — abstención ahora discrimina (W2 4.08%, W3 15.97%, no 100%). W2 NO INTERPRETABLE por fidelidad (cobertura 0.7755 fuera de [0.80,0.97]); W3 interpretable (cobertura 0.8908): VPP_M2 0.6000 vs VPP_base 0.5798, p=0.4347 ≫ 0.025 → la abstención NO mejora significativamente el VPP. VEREDICTO NO_CUMPLE → "¿debería el motor callarse cuando no hay señal?" respondida: con win_prob y esta mecánica, NO. Línea de abstención sobre win_prob CERRADA como refutada. Ledger motor_signal: 9→10, umbral próximo 0.9909 |
| Instrumento | M2 — defecto estructural de abstención detectado (2026-08-17) | 🟢 resuelto (2026-08-17) | — | Fix aplicado y verificado por el trial #17: residuos relativos `|outcome−point|/max(|point|, floor)` (ancho escala con el score → abstención diferencial) + default = p90 de los anchos de calibración + test de regresión `test_default_produce_abstencion_diferencial_no_100_ni_0` (exige abstención 1-30% con default y abstendidos = |point| máximos). Suite 242 passed. El instrumento ahora SÍ es capaz de medir — la línea de abstención sobre win_prob quedó refutada por el #17, pero M2 corregido queda disponible para scores futuros (ej. FinBERT) |
| Investigación | §25 Tarea B — ADX walk-forward (PLAN_LARGO_PLAZO, Cline) | 🟢 cerrado (2026-08-17) | — | NO CUMPLE: rank IC intra-día adx_score vs fwd_return_20d por ventana, Bonferroni-9 (|t|>2.77) en ≥2/3 → 0/3 (W1 +0.79, W2 +1.54, W3 +1.47; TOTAL ref +2.31). Señal positiva en las 3 ventanas pero ninguna significativa en aislamiento — el t TOTAL era pooling de señal débil repartida, no robustez OOS. ADX queda marginal-no-robusto con evidencia walk-forward, CERRADO como candidato a "bueno". Test secundario (premia operativa) contexto: positiva pero no sig (máx +1.73). Artefacto trial_adx_walkforward_20260817_103916.txt. Ledger signal_diagnosis: 14→15 |
| Investigación | §26 Tarea C — Indicadores semanales (PLAN_LARGO_PLAZO, Command Code) | 🟢 cerrado (2026-08-17) | — | NO CUMPLE: rank IC intra-semana (Spearman por semana, Newey-West L=1) de momentum_20w, rsi_14w, adx_14w contra fwd_ret_1w, Bonferroni-8 (|t|>2.73) en ≥2/3 ventanas → 0/3 para los 3 indicadores. W1: mom −0.17, rsi −0.08, adx +0.31. W2: mom −0.01, rsi −0.44, adx +0.16. W3: mom +0.19, rsi +0.14, adx +0.33. Máx |t| = 0.44 (rsi W2) — nowhere near significancia. Ruido semanal no oculta señal. Artefacto weekly_indicators_20260817_105918.txt. Ledger signal_diagnosis: 15→16 |
| Investigación | §34 — C6 (MA200 hedged) reabierto bajo costo MEDIDO (Tarea J, OpenCode) | 🟢 cerrado — NO CUMPLE (2026-08-19) | — | Reabrir por evidencia nueva de costos (§33: 0.05%/lado medido vs 0.15% asumido) fue el único motivo legítimo. Pre-registro §34 ANTES de correr; trial formal `motor_signal` (ledger 10→11). Corrido (`backtest_c6_hedge_costo_medido.py`, copia parametrizada de §18.2 con costo 0.0005; artefacto `backtest_c6_hedge_costo_medido_20260819_155509.txt`): **LS-HEDGE NETO +0.000010/día (t-NW +0.07)** — el costo 3× menor SÍ movió el neto de −0.000292 (§18.2) a +0.000010, pero la señal bruta es débil (+0.000157, t-NW +1.07) y ni siquiera el costo real la deja sobrevivir (criterio t-NW ≥ 2.0 NO se cumple). SO-HEDGE informativa: neto −0.000126 (t-NW −0.99). Check integridad: n=3710/Pearson −0.1603/Spearman −0.1148 — desviación menor vs §16 (3703/−0.1582/−0.1129) verificada como refresh de datos (data_updater 17/08), el script ORIGINAL re-corrido da idéntico → mi copia es fiel. **C6 CERRADO DEFINITIVO por segunda vez, ahora contra el costo real medido, sin ambigüedad.** NO se integra al motor. |
| Datos | Pipeline de datos automatizado (cache estaba 5 ruedas desactualizado, todo era manual) | 🟢 cerrado (2026-08-17, Kilo Code) | — | Brecha detectada en auditoría: OHLCV estancado al 8/10 (hoy 8/17) y acumulación FinBERT sin cron. Fix en dos pasos: (1) refresh manual ahora — 50/50 símbolos frescos ≥ 8/14; (2) `scripts/data_updater.sh` + `com.fortresscore.dataupdater.plist` INSTALADO en launchd (22:00 diario, tras cierre US): refresh OHLCV incremental + acumulación FinBERT incremental, log `scripts/data_updater.log`. Probado end-to-end: 50/50 precios, 48/48 símbolos, 0 filings duplicados (dedup OK), suite 242 passed |
| Frontend/Backend | Tarea E — campo de costo real en el dashboard (Ronda 2026-08-19, OpenCode) | 🟢 cerrado (2026-08-19) | — | `backend/app/api/routes/costs.py` NUEVO: `GET /api/costs/current` (solo lectura) lee `execution_costs.db` (registro canónico) y, si no existe/vacía, el artefacto `.txt` más reciente `measure_execution_costs_*` (JSON del RESUMEN); curva por tamaño (`sizes`) ya lista para qty=1/10/50 de la Tarea D. Sin medición → 200 `{"medido": false, "nota"}` — nunca inventa un número. Caveat PAPER siempre en la respuesta. Registrado en `routes/__init__.py` + `main.py`. Frontend: `CostField.tsx` (chip en Layout, visible en todas las vistas) + tipos en `client.ts` + `useExecutionCosts` en `hooks.ts`; tooltip con caveat y p50/p95/n/fecha. Verificado contra el artefacto real: endpoint devuelve `0.00018883729749502882` idéntico al `.txt` de 2026-08-18. 6 tests nuevos (`test_costs_api.py`, mock de db/txt, sin red), suite 271 passed, ruff limpio, tsc+build OK. NO se tocó `advisor.py` (commit 2f6fbeb intacto). Sin commit/push (regla de la ronda) |
| Frontend/Backend | **Despliegue permanente del dashboard** (2026-08-20, Kilo Code) | 🟢 cerrado (2026-08-20) | — | El pendiente más antiguo de la lista (bloqueado en plan-mode el 17/08) quedó CERRADO. Plists escritos: `scripts/com.fortresscore.api.plist` (uvicorn 127.0.0.1:8000, WorkingDirectory backend) + `scripts/com.fortresscore.dashboard.plist` (vite preview del `dist/` 127.0.0.1:3000, WorkingDirectory frontend), ambos KeepAlive + RunAtLoad + ThrottleInterval 10; instalados en `~/Library/LaunchAgents/` vía `launchctl bootstrap`. **Verificado EN VIVO**: dashboard HTTP 200 en :3000; API :8000 con `/api/system/status` 200, `/api/advisor/evidence` 200 (38 trials en ledger), `/api/costs/current` 200 → **0.000173/lado medido, n=156** (registry vigente con la corrida 19/08 de la Tarea D). Logs limpios (solo warning urllib3/LibreSSL benigno). Frontend sources sin cambios desde el build 19/08 (`find -newer` vacía) → el dist servido es el correcto. Puertos 8000/3000 libres previamente; 3000 elegido por ser origen permitido en CORS_ORIGINS. Dashboard abre permanente en **http://localhost:3000**. Kickstart tras cada rebuild: `launchctl kickstart -k gui/$(id -u)/com.fortresscore.dashboard`. La verificación visual automatizada ya se hizo el 19/08 (Chrome headless, 4 vistas OK); queda solo la mirada humana de Boris |
| Investigación | Tarea L — Auditoría FDR (Benjamini-Hochberg) sobre TODOS los factores cerrados (2026-08-19, OpenCode) | 🟢 cerrada — **sin discovery** (2026-08-19) | — | AUDITORÍA estadística retroactiva, NO trial, NO consume n_trials, solo lectura de t-stats existentes. Método (decidido antes): Stouffer weighted-z (√n), p bilateral, BH sobre m=14 factores a q=0.05 Y q=0.10. **k_rechazados=0 en ambos** — ningún factor flipea a discovery. El p más chico (ADX_daily 0.0376, t_pool +2.08) queda ~5× lejos del corte BH q=0.10 (0.0071); momentum_TB (−2.04) p chico pero signo NEGATIVO (no discovery direccional). Hipótesis "BH resucita ADX" NO se confirma. Excluidos del set con justificación: EVT (trial inválido, sin t), lead-lag (familia 50 tests), MA200-clusters §16 (misma señal que C6). Robustez: m=11 da k=0 también. Script `scripts/auditoria_fdr.py`; artefacto `data/cache/auditoria_fdr_20260819_195829.txt`(+json); §35 en PLAN_MEJORA_MATEMATICA.md; suite 271 passed. NADA se integra al motor ni cambia de estado. Sin commit/push (regla de la ronda) |
| Investigación | T0.1 — Look-ahead en `WalkForwardRegimeGate.label_series` (Fase 0 indicAgent, OpenCode) | 🟢 cerrado (2026-08-20) | — | Método nuevo `predict_regime_series_causal` (decodifica día-por-día, sin leakage ≤63d) en `regime_classifier.py`; `regime_gate.py::label_series` ahora lo usa. 12 tests verdes (2 nuevos: causal no usa futuro vs bloque sí), ruff limpio. Suite completa: los 4 rojos de market/live/predict son de OTRA sesión que cambió market.py en paralelo (auto-backup d2819ab 12:29), no de este ticket. Ver `PLAN_INTEGRACION_INDICAGENT.md` T0.1 + SESSION_LOG |
| Investigación | T0.2 — Ejecución en la misma barra de la señal en `backtest_engine.run` (Fase 0 indicAgent, OpenCode) | 🟢 cerrado (2026-08-20) | — | Alternativa simple del ticket: parámetro `execution_lag_days=1` en `run()` (0 = bug anterior, señal y ejecución al cierre de `date`; 1 = default, ejecución en open de `date+1`). Aplicado a entradas, salidas (stops y técnicas) y `_build_calibration_dataset`. `EXECUTION_LAG_DAYS=1` en config.py. **Impacto medido** (`RESUMEN_IMPACTO_EXECUTION_LAG.md`, universo 7 símbolos 2021-2023): Sharpe 0.57→0.38 (−33%), CAGR 0.95%→0.70%, max_dd −0.0252→−0.0242 — el lag=0 SOBREESTIMABA el rendimiento (parte del alpha era lookahead); se adopta lag=1. Test nuevo `test_backtest_engine.py` (gap overnight +5% → entry_price=open[siguiente]). `verify_fidelity()` agregado a barrier_labeling.py. Suite **279 passed**, ruff limpio. Sin commit/push (regla de la ronda) |
| Investigación | Tarea N — MACD (dirección) y Bollinger (régimen), §36 (PLAN_LARGO_PLAZO, OpenCode) | 🟢 cerrado — NO CUMPLE (2026-08-20) | — | Pre-registro §36 ANTES de correr (familia signal_diagnosis, n=19 → Bonferroni-19 bilateral **|t|>3.008**, umbral ledger confirmado consumed=18/threshold=0.99474). **MACD (2A, dirección)**: rank IC intra-día macd_hist vs fwd_20d, W1/W2/W3 → **0/3** (t +0.04/−0.68/+0.03; TOTAL −1.12) — sin señal direccional bajo la vara estricta. **Bollinger (i) VALIDACIÓN**: band_width vs vol realizada futura → rank IC +0.428/20d (t +50.3) y +0.393/10d (t +48.3) — **el instrumento mide régimen de vol por diseño** (validación confirmada, NO edge, no dispara trial). **Bollinger (ii) INTERACCIÓN**: mom_rsi rank IC split por tercil de banda → máx |ΔIC(expansión−tranquilo)| **0.0074** (5d), muy por debajo del umbral 0.05; split por régimen HMM débil (máx |t| DEFLATION −2.33, signo −). **VEREDICTO COMBINADO: NO_CUMPLE** (MACD NO_CUMPLE, Bollinger-ii NO_CUMPLE). Script `scripts/trial_macd_bollinger.py`; artefacto `data/cache/trial_macd_bollinger_20260820_174735.txt`; §36 en PLAN_MEJORA_MATEMATICA.md. Ledger signal_diagnosis 18→19, umbral 0.995. Nada se integra al motor. |
| Integración indicAgent | T1.6 — Taxonomía fina de outcomes + ledger `signal_ledger` (OpenCode) | 🟢 cerrado (2026-08-20) | — | `barrier_labeling.py`: el "no tocó nada, expiró" (TIME_BARRIER) se sub-clasifica en **MAX_HORIZON_PROFIT / MAX_HORIZON_LOSS / NEVER_MOVED** (umbral `NEVER_MOVED_MAX_RET=0.02`), SIN cambiar el orden de las barreras del motor; `verify_fidelity()` intacto. **Nuevo módulo `signal_ledger.py`** (tabla `signal_ledger(signal_id PK, symbol, entry_date, exit_date, exit_reason, pnl_r, factors_json, regime_state)`, upsert idempotente) — módulo aparte de `config_registry.py` (T1.5): son contratos distintos. `label_symbol(df, symbol=, ledger=)` persiste una fila por señal. **`BayesianOnlineUpdater.update()`** acepta `strength` opcional (default 1.0 = binario previo); `backtest_engine._update_bayesian_weights` usa **pnl_r** (retorno/riesgo del régimen) como fuerza, cap 10R. Tests: `test_barrier_labeling.py` 17→26, +3 strength en `test_probabilistic_engine.py`, +3 pnl_r en `test_backtest_engine.py`. Suite completa NO CORRIBLE en este cierre: `indicators.py` roto por OTRA sesión (auto-backup 46dcfa9 21:21, `def cvd_features(...): """` con docstring inline → IndentationError) — no se toca (regla). Ver `PLAN_INTEGRACION_INDICAGENT.md` T1.6 |
| Integración indicAgent | T1.5 — Registro de parámetros versionado point-in-time (OpenCode) | 🟢 cerrado (2026-08-21) | — | `config_registry.py` (nuevo): tabla `config_history(key, value, version, changed_by, reason, valid_from)` append-only, `set()` solo INSERT, `get_at()` reconstruye el valor vigente en un timestamp (point-in-time). `adaptive_risk.py`: `get_regime_thresholds(regime_state, at_date)` + `AdaptiveRiskManager.get_thresholds()` usan la fecha del backtest en curso (`RiskState.current_date` fijada por `check_all_stops`); `REGIME_THRESHOLDS` queda como seed (`changed_by="initial_estimate"`) y fallback. **Test clave del propósito**: backtest 2023 inalterado tras `set()` posterior (get_at reconstruye 2023); el mismo cambio con valid_from=2020 sí altera (sharpe 1.5603→1.6261). 10 tests nuevos en `test_config_registry.py` + fixture autouse de sesión en `conftest.py` (DB tmp, no ensucia fortress.db real). **Fix de rendimiento agregado**: cache en memoria de `get_at/get` (dentro de un backtest el registro es inmutable) — sin él, ~120k conexiones SQLite por backtest de 50 símbolos. `REGIME_THRESHOLDS` sigue importable directo (transición). Ver `PLAN_INTEGRACION_INDICAGENT.md` T1.5 |
| Integración indicAgent | T1.4 — Stop/target estructural (OpenCode, verificado 2026-08-22) | 🟢 cerrado (2026-08-21) — A/B completado 2026-08-22 | — | `signal_engine.py`: `_resolve_stop` (OB→sweep→swing_low→2ATR), `_resolve_target` (FVG→resistance→min→4ATR), `MIN_RR=1.5`, `generate_signal(..., market_structure=None)` fallback idéntico; `backtest_engine.run(use_market_structure)` con `market_structure_history` causal precomputada. Tests `test_signal_engine.py` 4 T1.4 (None idéntico, OB, RR gate reject/accept, target más cercano) + `test_market_structure.py` 4 history causal, suite 37 passed, ruff limpio. A/B 2021-2023 universo 50 (baseline 91 trades Sharpe 0.28 CAGR 0.74% vs estructural 31 trades Sharpe 0.38 CAGR 0.47% — filtra 66%, win 57→71%, PF 1.37→1.73, RR 2.0→2.33); **no promovido a default** (requiere trial W1/W2/W3 DSR≥0.90). Artefactos `compare_structural_stop_20260821_211537.txt` + `compare_structural_stop_20260822_013350.txt` + `RESUMEN_STOP_ESTRUCTURAL.md` completo (esta sesión). Ver `PLAN_INTEGRACION_INDICAGENT.md` T1.4 |
| Integración indicAgent | T2.2 — Bootstrap de bloques circulares para CI de métricas (OpenCode) | 🟢 cerrado (2026-08-21) | — | `circular_block_bootstrap_ci(returns, statistic_fn, block_size=20, n_bootstrap=1000, confidence=0.95, seed=None)` en `probabilistic_engine.py` (fancy-indexing vectorizado, `np.random.default_rng(seed)` — nunca toca estado global). `calculate_metrics()` ahora devuelve `sharpe_ci`, `cagr_ci`, `max_drawdown_ci` (tuplas lo/hi; maxdd en % como el punto; seed=42 fijo → backtest reproducible). Complementa (NO reemplaza) `conformal.py` y el Deflated Sharpe dándole CI, no solo punto. Tests `test_circular_bootstrap.py`: (1) coverage 0.942 del Sharpe verdadero en IID n=500 M=120 (percentil-bootstrap anti-conservador, umbral honesto 0.85); (2) CI de bloques ~2x más ancho que asintótico en AR(1) φ=0.6 (ese es el punto del método); (3) determinismo con seed, tipos lo≤hi, serie vacía → (nan,nan). Ver `PLAN_INTEGRACION_INDICAGENT.md` T2.2 |
| Integración indicAgent | T2.3 — Features de régimen por símbolo: Hurst exponent + realized_vol_regime (Kilo Code + cierre de medición) | 🟢 cerrado — NO promoción (2026-08-21, verificado 2026-08-22) | — | `hurst_exponent` (R/S vectorizado con `sliding_window_view`) y `realized_vol_regime` (ratio vol 20d/vol 100d — decisión explícita del plan: proxy antes que GARCH real sin evidencia medida) en `indicators.py`, integrados a `calculate_all_indicators` como columnas diagnósticas. Los 2 tests que fallaban eran el TEST, no el código: recalibrados con evidencia (Hurst: panel n=3000, 50 semillas, min 0.230 > umbral 0.2 — no se bajó la vara; vol shock: aserciones robustas multi-semilla sobre pico/media/proporción). Diagnóstico IC transversal (`scripts/diagnose_hurst_vol_ic.py`, rank IC Spearman por fecha, NW, W1/W2/W3, ref Bonferroni-19 |t|>3.008): **sin edge direccional** (hurst máx |t|=2.70 W3 con signo inestable entre ventanas; vol_regime máx |t|=0.52); clustering de vol validado solo en W1 (t=+3.25, W2/W3 nulos — limitación documentada del ratio vs nivel). **NO se promueven a `_factor_scores`**, quedan diagnósticos. Artefacto `diagnose_hurst_vol_ic_20260821_210750.txt`; detalle en `RESUMEN_HURST_VOL_REGIME.md`. Suite 358 passed re-verificada 2026-08-22 |
| Investigación | **Validación OOS fresca momentum+RSI — definición EXACTA congelada** (post-PBO 0.4688, tarea de Boris 2026-08-22) | 🟢 **cerrado — NO_CUMPLE mecánico (Sharpe_OOS +1.33 >0 pero DSR 0.6077 <0.95)** (2026-08-22) | — | La validación que §40 exigió ("cualquier 'mejor de 21' futuro exige validación OOS fresca"), SIN atajos: pesos/umbrales CONGELADOS leídos del código (`SignalEngine.factor_weights[0]` = 0.6642/0.3358, score ≥0.60, gates ADX≥20/vol≥1/close>EMA50>200/rsi 40-75), CERO re-optimización (prohibido ajustar pesos/bandas post-hoc). Portafolio equal-weight mensual vectorizado: señal al cierre último hábil del mes m → entrada OPEN primer hábil m+1 (lag 1 fiel) → CLOSE último hábil m+1; costos 0.0005+0.0005/lado (0.002/mes full-rebalance conservador). Corte IS/OOS 2023-12-31; **embargo 20 ruedas** descarta retorno ene-2024; mes parcial ago-2026 excluido → **T=30 meses efectivos (2024-02→2026-07)**, cache sin descargas (termina 2026-08-14). Fidelidad OK×6 estilo §39: universo 50/50, score y gates IDÉNTICOS al motor (max\|Δ\|=0 vs `compute_score_series`/`compute_factor_frame`), cobertura 86.7% meses con señal, edge bruto +2.37%/mes, T≥24. **Sharpe_OOS NETO +1.3296**, CI95 bootstrap bloques [+0.37,+2.32] (no incluye 0), acumulado +69.4%; **DSR Bailey&LdP2014 = 0.6077** (N_eff=consumed_budget ledger=22 conservador, T=30, skew 0.81/kurt 5.89, V[SR_n] proxy repo Fase 0b comparable con todos los DSR históricos). **Criterio pre-registrado binario sin zona gris: Sharpe_OOS>0 Y DSR≥0.95 → CUMPLE; otra cosa NO_CUMPLE → NO_CUMPLE: nada se promueve.** Lectura honesta: consistente con §39 (riesgo de GRADO no de EXISTENCIA) — la definición congelada rinde mejor en datos frescos post-lockeo (+1.33 vs ~+0.93 Sharpe_full §40), pero T=30 + colas gruesas + 22 trials consumidos no alcanzan DSR≥0.95; el DSR escala con √T (repetir con nuevo pre-registro cuando el updater acumule más meses). Pre-registro sellado ANTES de correr (`PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md`, corrida única 19.3s); script `backend/scripts/validacion_oos_fresca_mom_rsi.py`; artefacto `backend/data/cache/validacion_oos_fresca_mom_rsi_20260822_155520.txt`+`.json`. **Ledger `signal_diagnosis` 22→23**: id `validacion_oos_fresca_mom_rsi`, umbral `Sharpe_OOS>0 Y DSR>=0.95 (Bailey&LdP2014, N=ledger signal_diagnosis)`, veredicto NO_CUMPLE. No se toca T1.4/RESUMEN_STOP_ESTRUCTURAL ni Tarea L. **Hallazgo operativo aparte**: updater de precios CAÍDO desde ~2026-08-15 (`ModuleNotFoundError: No module named 'scripts'` en data_updater.sh) — cache estancado a 2026-08-14; fix aplicado hoy (cd a backend antes del paso OHLCV), la ventana 22:00 lo cura sola |
| Investigación | **PBO/CSCV momentum+RSI — auditoría de overfitting de proceso** (Tarea PBO, OpenCode) | 🟢 **cerrado — NO_CUMPLE (PBO 0.4688 ≥0.20)** (2026-08-22) | — | **Corrido UNA vez** (`backend/scripts/pbo_cscv_mom_rsi.py` nuevo, S=16→C(16,8)=12 870 splits, N=21 leído vía `trial_registry.consumed_budget(signal_diagnosis)`, Sharpe mensual neta ×√12, determinista seed 42, universo 50, ventana 2019-01-01→2026-08-04, costos 0.0005+0.0005). **PBO = 0.4688** (6 033/12 870 λ≤0; λ mediana +0.201, media +0.949, p5 −2.944/p95 +20.723, std 7.22; rank_OOS del best IS mediana 12.0 vs mediana teórica 11.0; degradación Sharpe_OOS−IS mediana −0.322; Spearman IS vs OOS +0.030). **Criterio §4 pre-registrado: PBO<0.10 CUMPLE / 0.10-0.20 gris (binario NO_CUMPLE) / ≥0.20 NO_CUMPLE / ≥0.30 sustancial** → **0.4688 → OVERFITTING de proceso, NO_CUMPLE (sustancial)**. Fidelidad OK (T=80 meses truncado a múltiplo 16, 5 meses≈105 ruedas por bloque ≥60, cobertura 85% meses con señal, edge +1.98%/mes, universo 50). Sharpe_full 21 configs +0.68→+1.25; ACTUAL w=0.664/45-70/100 Sharpe +0.934 rank 17/21 (no es el mejor full-período). **Ledger `signal_diagnosis` 21→22**: `pbo_cscv_mom_rsi`, n=1, umbral `PBO<0.10 (Bailey et al.)`, veredicto **NO_CUMPLE**, artefacto `backend/data/cache/pbo_cscv_mom_rsi_20260822_093300.txt`+`.json`, §4 `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md` (no editado post-resultado). El script previo `pbo_cscv.py` N=1 PBO=0.5 era NULO por antisimétria — este N=21 sí mide selección. **Interpretación**: elegir la mejor IS entre 21 no generaliza (mediana OOS) — firma de selección; baseline no se revoca (sigue siendo único modo documentado no-refutado, DSR 0.17 W3, pero nunca promovible sin validación OOS fresca). §39 PBO=0.2358 intermedio (27 vecinas, T=128) apunta misma dirección (riesgo de grado). Ver `PLAN_MEJORA_MATEMATICA.md §40`. |
| Investigación | §39 — PBO vía CSCV del baseline momentum+RSI: auditoría de proceso (Cline, de la cola de Boris 2026-08-22) | 🟢 cerrado — INTERMEDIO, sin acción automática (2026-08-22) | — | La prueba que faltaba al ÚNICO factor sobreviviente: ¿es el baseline un artefacto de selección? Bailey et al. 2017 CSCV sobre familia de 27 configs vecinas (pesos × banda RSI × techo momentum; ACTUAL=celda central), matriz 128 meses × 27, portafolio equal-weight mensual vectorizado con gates EXACTOS del motor (aproximación declarada sin stops/regime-gating), S=16 bloques, 12.870 combos. **PBO=0.2358 → bucket INTERMEDIO** del criterio pre-registrado (≤0.20 bajo / ≤0.50 intermedio / >0.50 alto); checks de fidelidad OK×4. Hallazgo clave: **las 27 configs tienen Sharpe positivo** (+0.55..+0.90) — riesgo de selección de GRADO, no de EXISTENCIA; y la config ACTUAL rankea 12/27 (no era el máximo in-sample → contra cherry-picking). NO se cambia ningún parámetro (mover al techo 75 sería cherry-picking post-hoc prohibido sin trial). Tarea O/P deben citar §39. Pre-registro ANTES de correr en PLAN_MEJORA_MATEMATICA §39 (con corrección de rótulo N documentada); script `backend/scripts/pbo_cscv_baseline.py`; artefacto `pbo_cscv_baseline_20260822_092850.txt`; detalle en `RESUMEN_PBO_CSCV_BASELINE.md`. No consume ledger |
| Investigación | **Tarea P — Regime gating de momentum: 3 condicionantes, trial coordinado §42** (PLAN_LARGO_PLAZO, OpenCode) | 🟢 **cerrado — NO_CUMPLE (0/3 condicionantes)** (2026-08-22) | — | Pre-registro §42 ANTES de correr: UN trial coordinado con 3 sub-hipótesis (`n_trials_consumidos=1`), Bonferroni intra-trial m=9 sobre ledger vigente `current_threshold()=0.9958333333333333` (consumido=23 → n=24) → α_trial/m=9 → **\|t\|>3.5013 bilateral**. momentum_12_1 CONGELADO (`indicators.py:277`), IC diario Spearman vs fwd_20, NW L=min(12,n//8), W1/W2/W3 canónicas, START extendido a 2015 solo para que min_history=756 del gate cubra W1. **(a) Estado HMM rezagado vía `regime_gate.py::WalkForwardRegimeGate.label_series` — PRIMER USO REAL de M3** (favorable={0}=GOLDILOCKS, defaults 63d/756d, macro SPY EFA QQQ GLD DBC TIP TLT AGG ^VIX): ΔIC(GOLDILOCKS−resto) **+0.1774 (t+3.14) W1** / +0.01 W2 / −0.07 W3 → 0/3 sig → NO_CUMPLE (W1 sugerente pero bajo la vara y sin repetición). **(b) Vol realizada 63d cartera momentum top-quintil**: ΔIC +0.07/+0.04/+0.01, t≤0.94 → NO_CUMPLE plano. **(c) Amihud agregada rolling 21d**: riesgo declarado MATERIALIZADO — percentil expanding colapsa tercil alto (1911/490/141 días; n_B=6 en W2, 0 en W3), signo W1 OPUESTO al paper (−0.1864) → NO_CUMPLE. Fidelidad OK×5 (universo 50/50, meses 24/24/31, edge pooled +0.0079 positivo, seed 42, gate 34 recalibraciones asserts OK, estados no degenerados 528/446/821/312). **GLOBAL NO_CUMPLE** — ninguna compuerta se integra al motor; línea (a) queda abierta como pista débil no confirmada. Script `backend/scripts/trial_regime_gating_p.py`; artefacto `backend/data/cache/regime_gating_p_20260822_162628.txt`(+json); §42+§42.1 PLAN_MEJORA_MATEMATICA.md. Ledger signal_diagnosis 23→24 id `regime_gating_p`. No se toca signal_engine.py ni archivos del fix cosmético |
| Investigación | **Tarea O — Frog-in-the-Pan: ID condicionando momentum_12_1, §41** (PLAN_LARGO_PLAZO, Kilo Code) | 🟢 **cerrado — NO_CUMPLE (0/3 ventanas)** (2026-08-22) | — | Pre-registro §41 ANTES de correr (familia signal_diagnosis, consumido=22 → n=23 → Bonferroni-46 bilateral ΔIC>0 **\|t\|>3.065**). Fórmula EXACTA del paper Da-Gurun-Warachka 2014 RFS sobre la MISMA ventana de formación que momentum_12_1 (`close.pct_change(252)`): ID = sign(PRET) × (%neg − %pos), días r=0 excluidos de ambas fracciones, todo causal ≤ t. Terciles de ID POR FECHA (qcut cross-sectional, tercil 1=continua / 3=discreta, mín 5 símbolos/bucket), IC diario Spearman(momentum_12_1, fwd_20) intra-bucket, ΔIC_t pareada t1−t3 con SE Newey-West L=min(12,n//8), W1/W2/W3 canónicas, universo 50 cacheado SIN descargas. Resultado: panel 119900 filas × 2398 fechas; ID sanity p10 −0.151/p50 −0.068/p90 +0.024 (masa en continuo, esperable). **ΔIC(t1−t3): W1 −0.51, W2 +2.16, W3 −0.07 → 0/3 sig → NO_CUMPLE** — la dirección promedio va a favor de la hipótesis (tercil1 +0.28 vs tercil3 −0.41 TOTAL) pero es ruido (Δ TOTAL t +0.65) e inestable por ventana. El efecto del paper (6m, cross-section grande US) no se traslada a momentum_12_1 sobre N=50 diario. Script `backend/scripts/trial_frog_in_the_pan.py`; artefacto `backend/data/cache/trial_frog_in_the_pan_20260822_175302.txt`; §41+RESULTADO en PLAN_MEJORA_MATEMATICA.md. Ledger id `trial_frog_in_the_pan` (entrada #25 física; durante la corrida OpenCode registró en paralelo validacion_oos_fresca/regime_gating_p — umbral propio ex-ante no afectado). **Nada se integra al motor** — momentum queda sin condición ID. |
| Investigación | **Tarea M — KAMA/HMA/Supertrend: familia de tendencia adaptativa, §44** (PLAN_LARGO_PLAZO, Kilo Code) | 🟢 **cerrado — NO_CUMPLE (0/9 celdas primarias)** (2026-08-23) | — | Pre-registro §44 ANTES de correr: UN trial coordinado con 3 sub-hipótesis direccionales (`n_trials_consumidos=1`), Bonferroni intra-trial m=9 sobre ledger vigente (consumido=25 → th=0.9961538461538462) → **\|t\|>3.5226 bilateral**. Factores CONGELADOS: kama_dist=(close−KAMA(er10,f2,s30))/close con ER reusado de `predictive_indicators.compute_efficiency_ratio`; hma_dist=(close−HMA(16))/close fórmula literal Hull 2005; supertrend_side∈{±1} ATR10×3.0 flip estándar. IC diario Spearman vs fwd_20d ≥5 símbolos, NW L=min(12,n//8), W1/W2/W3 canónicas, cache-only sin descargas. Resultado: kama t −0.98/−0.10/+0.27; hma −0.26/+0.31/−0.67; st −1.40/+0.55/+0.91 → **0/9 sig**; IC pooled TOTAL NEGATIVO en los tres (kama −0.0103 t−1.01; hma −0.0016 t−0.24; st −0.0126 t−1.24) — ni señal nominal, signo contrario al esperado y sin consistencia entre ventanas. Desglose por régimen GOLDILOCKS-lag EXPLORATORIO pre-declarado no-gating (2º uso real de regime_gate.py): máx \|t\|=+2.58 (st W1, n gold=43) sin repetición W2/W3 → sin pistas sobre el umbral (mismo patrón débil de Tarea P(a)). Fidelidad OK×5 (50/50 símbolos, panel 133650×2673 fechas, gate 34 recalibraciones, estados no degenerados). Script `backend/scripts/trial_kama_hma_supertrend.py`; artefacto `backend/data/cache/trial_kama_hma_supertrend_20260823_152846.txt`(+json); §44+§44.1 PLAN_MEJORA_MATEMATICA.md. Ledger signal_diagnosis 25→26 id `trial_kama_hma_supertrend`, próximo umbral 0.99630. Implementación: `wma()/kama()/hma()/supertrend()` nuevas en indicators.py como columnas diagnósticas NO wired al motor + 10 tests sintéticos de tendencia conocida; suite **367 passed**. |

| Frontend | **Infraestructura de testing de frontend** — Vitest + RTL + tests de contrato (GovernancePanel, CostField, hooks advisor) (2026-08-23, Cline vía Orca; plan de Claude Code) | 🟢 cerrado (2026-08-23) | — | Primera suite de tests del frontend (antes: cero, ver AUDITORIA_TECNICA). Deps verificadas contra package.json real (React 18.2/Vite 5/TS 5.3/Node v24): vitest@2.1.9 (línea 2.x por soporte explícito de Vite 5), jsdom@25.0.1, @testing-library/react@16.3.2 + dom@10.4.1 (peer obligatorio de RTL 16) + jest-dom@6.9.1. Config: bloque test jsdom en vite.config.ts (import desde vitest/config) + src/test/setup.ts; scripts `npm test` (vitest run) y `npm run test:watch`. **17 tests**: GovernancePanel (7) — fija el contrato post-bug-P0 (`governance.triad.{bull,bear,contrarian}.score`, `controller.approved`, `judge.verdict`, URLs `/api/governance/status` y `/api/governance/analyze/{symbol}`), error HTTP 500 visible, skeleton de loading, estado del sistema; CostField (4) — loading sin número, `medido=false` → SIN MEDICIÓN con nota en tooltip y NUNCA un % aunque venga basura (contrato de honestidad M4), medido → costo formateado + n + curva q1/q10/q50, caveat PAPER en tooltip; hooks advisor (6) — useExecutionCosts éxito/error con detail del body/refetch, useAdvisorSymbol(null) no llama a la API. Mock de global.fetch, cero red. **Verificado CORRIDO (no de palabra)**: `npx vitest run` → 17 passed (3 archivos, 14.7s, cero warnings act); `tsc` limpio (27.5s, tipa los tests también) y `vite build` OK (863 módulos, bundle principal 152.95 kB — igual al documentado, sin regresión). Commit `7c154f2` en worktree test-cline-orca (rama bjofrea-ctrl/test-cline-orca, SIN push a main — coordinación vía Orca). Backend y motor intactos. Pendiente heredado: extender cobertura a otras vistas (Mesa/Detalle/Portfolio) y considerar CI para frontend |

| Frontend | **Tests de las 4 vistas principales** (Mesa, Detalle, Portfolio, Gobernanza) + 3 fixes de degradación graceful (2026-08-24, Cline vía Orca) | 🟢 cerrado (2026-08-24) | — | Extensión del patrón Vitest+RTL a `src/test/views/`: **24 tests nuevos** (MesaPage 6: contadores por estado, banners staleness/blocked_reason, reintentar re-invoca ambos hooks, tesis ROTA primero; DetailPage 4: matching de tesis por símbolo —nunca cruza símbolos—, error con status, thesis=null graceful; DetailView 8: **zonas mecánicas** entrada/stop 2×ATR/target 4×ATR con disclaimer anti-predicción, nulls→— sin NaN/undefined, fundamentales sin cobertura EDGAR explícitos, toggle chart local↔TV, M2 abstención; PortfolioPage 3: composición de 7 paneles sin crash con endpoints colgados/500/payloads mínimos; GovernancePage 3: fallback SPY y API_URL centralizada). Charts mockeados (canvas fuera de alcance jsdom). **Hallazgo operativo previo**: los 3 commits del 23-08 NO estaban en main pese a lo reportado — recuperados del reflog y re-aplicados sobre main actualizada (cherry-picks limpios). **3 bugs reales encontrados por los tests y arreglados**: (1) `KPICards` no chequeaba `resp.ok` ni validaba forma → crasheaba el dashboard si `/api/backtest/metrics` devolvía 500 con body JSON; (2) `TradeDistribution` mostraba "NaN%" con lista de trades vacía (0/0); (3) `RiskPanel` mostraba "-NaN%" si el monitor no traía `absolute_ceiling`. Verificado CORRIDO: vitest → **41 passed (8 archivos)**, tsc limpio, vite build OK (bundle principal 152.95 kB intacto). Commit `43e614d` en worktree test-cline-orca, SIN push. Backend/motor intactos |
| Frontend | Vista unificada de trades: backtest histórico + paper real en el dashboard (Cline, 2026-09-01) | 🟢 cerrado (2026-09-01) | — | `TradesTable.tsx` ahora lee `/api/trades/combined` (nuevo router) que combina 303 trades de backtest (2019-12→2024-11, sin límite de 50) + operaciones reales del signal_ledger (fortress.db). Cada fila lleva `origin: 'backtest' | 'paper'` explícito. Columna Origen con badge BT/PAPER y columna P&L %. Ördenes paper abiertas (status=open) muestran "—" en P&L. Contrato legacy `/api/backtest/trades` intacto. 8 tests nuevos, 22 passed suites relacionadas, ruff limpio, tsc 0. Detalle en SESSION_LOG 2026-09-01 |

| Seguridad | `trial_registry.json` sin backup versionado (el rsync SÍ lo copiaba, pero sin retención propia — corrupción local se propagaba al espejo en el siguiente ciclo) | 🟢 cerrado (2026-08-24, commit `c67a99c`) | — | `backup_trial_registry()` en `auto_backup.sh` y `backup.sh` (paso 6.6), mismo patrón que `backup_db()`: timestamped, retención 20 copias en `/Volumes/EMPRESA/fortress_core_backups/trial_registry/` |
| Código | CI no corría tests de frontend (8 archivos Vitest existían, cero cobertura en push/PR) | 🟢 cerrado (2026-08-24, commit `c67a99c`) | — | Job `frontend` nuevo en `ci.yml` (setup-node 20, `npm ci`, `npm run test`). Verificado localmente con `npm ci` (mismo comando del runner): 41/41 tests, 8/8 archivos |
| Instrumento | Inconsistencia `stop_distance` sizing vs stop trigger (`adaptive_risk.py:109` usa `max(2×ATR, position_stop%)`, `:149` dispara solo con `position_stop%`) | 🟡 hallazgo de código, no bug a arreglar sin decisión de riesgo | Decisión de producto (¿el trigger debe usar la misma distancia que el sizing?), no delegable a un agente sin contexto completo | Pasado a Kilo como FYI (2026-08-24) para documentar en el marco de §45 si es relevante para el diseño — mismo código que el trial EVT-stops v2 está usando ahora, no tocar aparte |
| Investigación | **§45 Trial #18 — EVT-stops v2: sizing aislado (re-take de la línea #15)** (Kilo Code, auto-cierre autorizado) | 🟢 **cerrado — NO_CUMPLE (0/3 ventanas, dirección consistente)** (2026-08-24) | — | Pre-registro §45 APROBADO por coordinador+Boris antes de correr; neutraliza las DOS capas de inercia del Hallazgo 6: Kelly desactivado simétrico en ambos brazos + RISK_PER_TRADE_arm=0.0015 (umbral de binding 1.5%P). **GATE F7 PASÓ AL 100%**: shares_by_risk fue la restricción activa en 100% de compras en las 3 ventanas, ambos brazos — primera vez que la distancia de riesgo DECIDE tamaños (vs placebo #15). Resultado: EVT PEOR en las 3 ventanas (Sharpe 0.274/−0.001/0.601 vs BASE 0.320/0.186/0.694; DSR 0.101/0.048/0.260 vs th=0.99167 n=12; maxDD algo más profundos) — la distancia VaR-GPD más ancha achica posiciones y diluye el edge sin protección compensatoria ni en W2 bear. Línea EVT-stops CERRADA DEFINITIVA (§19+§20/Hallazgo 6+§45). Fidelidad OK×8 (anti-lookahead 254 compras/0 fallbacks; var_mult mediana 2.93; F9 identity-cache 25 pares bit-idénticos; suite 367 pre-corrida). Nota de ejecución: intento 1 abortado >13h sin veredicto (generate_signal recalcula indicadores redundantes por día×símbolo, explosión T2.3 hurst; artefacto ABORTADO_* preservado); intento 2 con parche identity intra-proceso (~37 min), metodología intacta. Incluye HALLAZGO DE CÓDIGO para decisión futura: sizing usa max(2×ATR, floor) pero trigger REGIME_STOP_HIT dispara solo por position_stop% (adaptive_risk.py:109 vs :149) — asimetría sizing/trigger, decisión de producto pendiente. Script `backend/scripts/trial_evt_stops_v2.py`; artefactos `trial18_evt_stops_v2_20260824_200927.txt`(+parquet ambos brazos); §45+§45.1 PLAN_MEJORA_MATEMATICA.md. Ledger motor_signal 11→12 id `trial_evt_stops_v2`, próximo umbral 0.99231. Producción intacta. |

| Seguridad | **`SAMPLE_PREDICTION_DATA` — señales falsas ("Polymarket: ...") entraban al composite_score en vivo, sin marcador de origen (violación ONBOARDING #4)** | 🟢 cerrado (2026-08-25, commit `33d8914`) | — | Hallazgo H1.1 de auditoría externa (GLM/fx), verificado línea por línea antes de aceptarlo. Afectaba `/api/predict/analyze/{symbol}`, `/api/predict/universe` Y `/api/governance/analyze/{symbol}` (tercer punto de uso no detectado por la auditoría, encontrado al verificar). Fix: los 3 call sites pasan `prediction_data=None` (mismo patrón que `sentiment_data`); constante eliminada. 16/16 tests relevantes (`test_predict_api`, `test_governance_auth`, `test_governance_contract`) passed |
| Investigación | Auditoría externa independiente (GLM/fx, 8 frentes + ronda 2 de verificación, 2026-08-25) | 🟢 recibida y verificada — ver `PLAN_HANDOVER_48H.md` §6.1, `AUDITORIA_GLM_RONDA2.md` | — | **H1.1**: cerrado y re-verificado independientemente en ronda 2 (camino completo confirmado línea por línea, `prediction_data=None` → sin señales fantasma → `composite_score` limpio). **H5.1** (corporate actions): CERRADO — verificado con datos reales de 4 splits (AAPL 4:1, NVDA 10:1, GOOGL 20:1, AVGO 10:1), sin saltos de precio, parquet sin columna "Adj Close" confirma `auto_adjust=True` (default yfinance 1.2.0) — no es un bug. **H4.1** (sesgo de supervivencia): parcialmente cuantificado — cota inferior por IPO tardío = 0/50 (todos arrancan 2015-01-02), pero la cota real (selección por market cap de 2026 aplicada a 2015) no se puede medir sin datos históricos de constituyentes del S&P 500 — queda como limitación estructural admitida, no accionable sin esa fuente externa. **H3.1** (familia `re_test` evade Bonferroni por diseño): DECIDIDO e IMPLEMENTADO por Boris (2026-08-26, ver fila "Garantías anti-evasión Bonferroni") — análisis independiente Cline en `ANALISIS_RE_TEST_BONFERRONI.md` (segunda mirada vs Kilo). H2.3/H8.2 (menores) sin asignar. Brecha 2 (M3 compuerta standalone) sigue asignada a Kilo. Script de verificación `backend/scripts/audit_parquet_check.py` (solo lectura, inofensivo) quedó en el repo |

| Instrumento | **A1 — M5 (drift_detector.py) sin conectar: el conformal (M2) dice re-calibrar por deriva, en realidad re-calibra por tiempo** | 🟢 docstring corregido (2026-08-25, commit `c8203a8`) · conexión real pendiente | Conectar M5 de verdad requiere pre-registro (afirmar "mejora cobertura" es un veredicto) — decisión de Boris | Hallazgo A1, ronda 3 de auditoría externa (GLM). Verificado: M5 tiene 0 consumidores en producción (sin imports fuera de su propio módulo/test, sin endpoint HTTP). Mitigante real: `advisor.py` TTL 5min + `decision.py` ventana móvil 730d ya evitan calibración estática indefinida. Corregido el docstring de `conformal.py` para reflejar el comportamiento real (recalibración periódica, no por evidencia de deriva) — sin cambio funcional. Si se decide conectar M5 de verdad (recalibración inmediata al detectar deriva en vez de esperar TTL), es un pre-registro nuevo, no un fix |

| Investigación | **§46 Trial #19 — Compuerta M3 STANDALONE sobre el motor (Brecha 2)** (Kilo Code, auto-cierre autorizado) | ⚪ **cerrado — NO INTERPRETABLE mecánico (piso insuficiente), sin consumo de slot** (2026-08-25) | Re-intento requiere pre-registro nuevo con piso alcanzable — decisión de Boris | Pre-registro §46 APROBADO por coordinador antes de correr; primera medición REAL de M3 como compuerta de operación (vs §42 condicionante diagnóstico): ALWAYS vs GATED intra-corrida, GOLDILOCKS-rezagado 21b cubre solo **28.7%** de días → GATED n=17/19/51 contra piso 30 → solo W3 computable (<2/3) → **NO registra NI consume** (motor_signal sigue 12, th 0.99231). Desglose exploratorio: mejora riesgo-retorno cuando GOLD es escaso (W1 Sharpe 0.69 vs 0.32, maxDD −1.5% vs −5.3%) y lo destruye cuando abunda (W3 0.16 vs 0.48) — el filtro vale para EVITAR malos, no para certificar buenos; pista, no evidencia. Fidelidad OK×6 (F9 identity-cache bit-idéntico, gate 34 recalibs, suite 370 pre-corrida; señales 75.7% bloqueadas). Script `backend/scripts/trial_m3_gate_standalone.py`; artefacto `trial_m3_gate_standalone_20260825_164832.txt`(+json+parquet); §46+§46.1 PLAN_MEJORA_MATEMATICA.md. Producción intacta. |
| Investigación | **§47 Trial #20 — "Buffett's Alpha" sistemático (Quality + Value + Low-Beta), A5** (Kilo Code) | 🟢 **cerrado — NO_CUMPLE mecánico (Sharpe_OOS 0.886>0, DSR 0.361<0.99231), consume 1 slot** (2026-08-25) | Si se mejora cobertura/definición de valor, el re-test corresponde a A4 (no re-abrir A5) | Pre-registro §47 aprobado por coordinador. Fase 0 (panel EDGAR point-in-time 47/48, coverage-gate 97.9%/100% PASS) + trial único (`trial_a5_buffett_alpha.py`). OOS 31m: **Sharpe neto 0.886>0, DSR 0.361 (n=13) → NO_CUMPLE binario**. Hallazgo: control equal-weight OOS Sharpe **1.50 > factor 0.886** — el composite no bate al universo naive. Familia motor_signal consume **12→13** (th vigente 0.992857). Sin promoción al ensamble. §47+§47.1 PLAN_MEJORA_MATEMATICA.md. |
| Gate | **A7 — enforcement técnico del gate en el ledger** (Cline, 2026-09-03) | 🟢 cerrado (2026-09-03) | — | `gate_window.py` (nuevo) + `_gate_window_check()` en `trial_registry.py`: trial con fecha dentro de 2026-09-02..GATE_END y `categoria` fuera del allow-list cerrado `{bugfix, infraestructura}` → `TrialRegistryError` ANTES de escribir el archivo. Chokepoint único cubre `register_trial` y `register_trial_reservation`; escape declarado `FORTRESS_ALLOW_GATE_TRIAL=1` (el conftest lo deja activo para que el resto de la suite pruebe mecánica). El mensaje cita la **Regla 1 de ONBOARDING.md con su contenido real**, verificado leyendo el doc (no un literal del test) + guarda anti-renumeración. 22 tests en `test_trial_registry_gate.py`. |
| Investigación | **A8 — PBO baseline con lag-0: pre-registro sellado, NO ejecutado** (Cline, 2026-09-03) | 🟢 cerrado como docs-only (2026-09-03) · corrida post-gate pendiente | Boris evalúa correrlo cuando exista racha ≥60 en `clean_days.json` | `PRE_REGISTRO_PBO_BASELINE_LAG0_20260903.md` + §40.1 en `PLAN_MEJORA_MATEMATICA.md` declarando la limitación lag-0 del PBO=0.2358 vigente. Criterio, umbrales (0.20/0.50), checks de fidelidad y los campos del ledger (`Umbral_aplicado`, `Familia: signal_diagnosis`, `Categoría: bugfix`) escritos ANTES de correr, per Regla 1. Red de seguridad: 15 tests `test_a8_pbo_lag0_docs.py`. **No se ejecutó ningún trial durante el gate ni se tocó `app/*.py`.** |
| Gobernanza | **A9 — flag `GOVERNANCE_LLM_ENABLED` + cartel explícito en el dashboard** (Cline, 2026-09-03) | 🟢 cerrado (2026-09-03) | — | Default `False` en `config.py`; NIM/OpenRouter guardados en `advanced_agents.py`, `predict.py` y `governance.py` (no quema llamadas decorativas). `/api/governance/status` expone `governance_llm_enabled` y `nvidia_nim_blocked_by_a9`; `GovernancePanel.tsx` muestra banner NO colapsable con el texto del plan ("descriptiva — no conectada a decisiones del pipeline") en tri-estado ACTIVA / DESACTIVADA (A9) / DESCONOCIDA — nunca asume activa si el `/status` no carga. Arreglado de paso: NVIDIA NIM decía "ACTIVO" con el pipeline bloqueado → ahora "BLOQUEADA (A9)". Contrato backend↔frontend verificado campo a campo. 6 tests nuevos, frontend 52/52, tsc y build limpios. |
| Motor | **A4 — hash-guard: drift de `backtest_engine.py` por A6 declarado y re-verify limpio** (Cline, 2026-09-03) | 🟢 cerrado (2026-09-03) | — | `motor_manifest verify` detectó drift real (rc=2) causado por A6 y no declarado al commitear. Antes de bump se verificó contra el diff que el cambio es 100% A6 (n_trials del ledger + trazabilidad; no toca señal, riesgo ni rebalanceo) → `bump --note` con la razón. `verify` → OK 7 módulos, rc=0. El reinicio del contador queda pendiente porque A2 no existe (ver ítem siguiente). |
| Gate | **A2 — contador de días limpios `backend/data/clean_days.json`** | 🔴 no existe en ningún repo (verificado 2026-09-03) | Crear el contador: sin él la racha del gate no corre y el bump de A4 no tiene qué reiniciar | Descubierto al cerrar A4: el `bump` ordena reiniciar "a mano" un archivo que nunca se creó. No es un efecto de A4/A6 — es Fase A incompleta. |
| Docs | **`PLAN_REMEDIO_BRECHAS_20260903.md` cita una "Regla 0 del ROADMAP" inexistente** (líneas 67, 68, 88) | 🔴 sin corregir en el plan (es ticket de Boris) | Corregirla a "Regla 1 de ONBOARDING.md" o el próximo agente vuelve a copiarla | Es el origen del error de cita que A7 arrastró; ya corregido en código, mensajes y tests. El ROADMAP no tiene reglas numeradas. |


**Leyenda**: 🔴 crítico/sin empezar · 🟡 en curso/parcial · ⚪ parqueado, sin decisión de producto · 🟢 cerrado

---

## Por qué existe este documento

El patrón que se repitió en esta sesión: cada vez que una herramienta (OpenCode, Cline) entregaba
un resultado, había que pedir explícitamente "verificá esto contra el artefacto real" para que
la verificación pasara — nunca ocurría por defecto. Lo mismo con el alcance: el rigor
matemático se mantuvo altísimo durante semanas, pero nadie declaró en ningún momento "che, el
resto del proyecto no está pasando por el mismo filtro" — hasta que se pidió una auditoría
explícita.

Este documento no resuelve eso solo — sigue haciendo falta que alguien (usuario o quien
retome la sesión) lo lea. Pero si se mantiene actualizado, al menos nada se pierde por
descuido: lo que no se cerró queda escrito, no depende de la memoria de una conversación
particular.
