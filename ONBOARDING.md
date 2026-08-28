# ONBOARDING — leé esto primero, siempre

Si sos un agente de IA (Claude, Cline, OpenCode, o cualquier otro) empezando una sesión nueva
en `fortress_core`: este archivo existe para que puedas ponerte a trabajar sin repetir
investigación ya hecha, sin re-litigar decisiones ya tomadas, y sin romper la disciplina que
costó semanas construir. Leelo completo antes de tocar código.

Última actualización: 2026-08-23.

**Coordinación vía Orca (nuevo, 2026-08-22/23)**: el trabajo entre Claude Code, OpenCode y
Kilo Code se coordina ahora con [Orca](https://www.onorca.dev) (app instalada, CLI
`orca`) — cada agente corre en su propia terminal/worktree, Claude Code puede crear
tareas y leer resultados directo (`orca terminal create/send/wait/read`) sin que Boris
relaye texto entre sesiones. Detalle completo (comandos, gotchas, symlink de `kilo`
roto, telemetría bloqueada por firewall) en la memoria persistente de Claude Code
(`reference_orca_orchestrator.md`) — si sos otro agente sin acceso a esa memoria,
pedile a Boris el resumen o mirá `PLAN_LARGO_PLAZO.md` para el estado de tareas en
curso. Cline y OpenCode dentro de Orca usan comandos genéricos de terminal (no la
capa de orquestación "de primera clase", que solo cubre Claude Code/Codex/Cursor/
OpenCode oficialmente).

**Dos tareas en curso ahora mismo, dispatchadas por Claude Code vía Orca, sin cerrar
todavía** (verificar contra `git log` y `data/cache/` antes de asumir que siguen
corriendo o que ya terminaron):
- **Tarea M** (KAMA/HMA/Supertrend, `PLAN_LARGO_PLAZO.md`) — Kilo Code, terminal Orca
  creada 2026-08-23 en worktree `test-kilo-orca`.
- **PBO/CSCV de fidelidad completa** (reconstruir los 21 trials reales de
  `signal_diagnosis` con `backtest_engine.run`, no vecinos de parámetros) — OpenCode,
  terminal Orca en worktree `test-opencode-orca`. Motivo: el PBO de hoy (§40) usó un
  proxy de parámetros vecinos, declarado como limitación — esta es la versión de
  fidelidad total que quedó pendiente ahí mismo.

---

## Qué es este proyecto, en una frase

Sistema de trading cuantitativo (Python/FastAPI + React) que investiga si hay una señal
estadísticamente real para operar un universo de 50 símbolos de acciones — con un rigor
metodológico deliberadamente alto (DSR, PBO/CSCV, RMT, rank IC intra-día con Newey-West,
pre-registro de criterios antes de correr cualquier trial).

## Lo primero que tenés que saber, sin excepción

**Hoy no hay señal comercial verificada — y hay más evidencia de esto que nunca.** Tres
líneas de investigación independientes (selección de 50 símbolos, rotación sectorial,
timing sobre un basket único) se probaron con evidencia rigurosa y las tres se descartaron.
Encima, en 2026-08-22 se sometió al ÚNICO factor no refutado (momentum+RSI) a controles que
nunca se le habían hecho: PBO/CSCV (dos veces, 0.24 y 0.47 — riesgo de sobreajuste de
selección de parámetros) y **validación OOS fresca con definición congelada del motor**
(Sharpe +1.33, pero DSR 0.6077 — no cruza el 0.95 requerido). Ni el condicionamiento por
régimen (Tarea P) ni por Information Discreteness (Tarea O) lo rescataron. Si alguien te
pide "conectemos esto a un broker" o "pongamos esta señal en vivo" — la respuesta correcta
sigue siendo "todavía no", ahora con más capas de evidencia respaldándola, no menos.

**Hallazgo de mayor impacto de toda la investigación (2026-08-20, T0.2)**: se encontró y
arregló un bug real de look-ahead en `backtest_engine.py` — la señal se decidía y ejecutaba
al cierre de la MISMA barra (imposible en trading real). Fix: `execution_lag_days=1`
(default nuevo), ejecución en la apertura del día siguiente. Impacto medido: Sharpe
0.57→0.38, CAGR 0.95%→0.70% (universo 7 símbolos, `RESUMEN_IMPACTO_EXECUTION_LAG.md`) — el
número viejo estaba inflado por lookahead. Cualquier backtest de PnL corrido ANTES de este
fix con `backtest_engine.run()` (no los tests de rank-IC puro) debe leerse con esa reserva.

**No confíes en ningún resumen sin verificarlo contra el artefacto real.** Esta es la regla
más importante del proyecto y la que más veces evitó un error real: números pegados en un
chat, citas de fuentes externas, o "ya está hecho" — todo se verifica leyendo el archivo,
corriendo el test, o mirando el commit, antes de aceptarlo o de construir algo encima. Pasó
más de una vez en esta investigación que un resumen sonaba bien y el artefacto decía otra
cosa (label mal puesta, veredicto mal leído, fuente académica citada que resultó ser el
backtest apalancado 12x de un desconocido en GitHub con 0 estrellas, no datos reales del
Medallion Fund).

---

## Documentos del proyecto — cuál leer para qué

| Documento | Para qué sirve |
|---|---|
| **`ROADMAP.md`** | **Qué falta, hoy.** Léelo siempre después de este archivo. Tabla maestra de todo lo abierto (investigación, código, seguridad, producto), con estado y bloqueo. Se actualiza cada vez que algo se cierra. |
| **`PLAN_MEJORA_MATEMATICA.md`** | Historia completa de la investigación matemática: cada auditoría, cada corrección de metodología, cada veredicto con su artefacto citado. Si necesitás entender POR QUÉ se descartó algo, está acá. |
| **`RESUMEN_VALIDACION_VARIABLES.md`** | Tabla resumen rápida: qué variables se probaron, cuáles funcionan, cuáles no. |
| **`AUDITORIA_TECNICA.md`** | Estado del código/infraestructura/seguridad/agentes — todo lo que NO es la investigación matemática. |
| **`SESSION_LOG.md`** | Bitácora cronológica extensa. No leer entero — consultar puntual si hace falta reconstruir una fecha específica. |
| **`CLINE_CONTEXT.md`** | Mecánica operativa (backup, comandos de emergencia) sigue vigente. La sección "ESTADO ACTUAL" está congelada en una sesión muy vieja (agosto, "Sesión 2") — **ignorala**, está superada por este archivo y por `ROADMAP.md`. |

---

## Reglas de trabajo no negociables

Estas reglas existen porque romperlas ya costó errores reales en este proyecto, documentados
en `PLAN_MEJORA_MATEMATICA.md`. No son sugerencias de estilo.

1. **Ningún trial de motor sin criterio pre-registrado.** El umbral de significancia, la
   corrección por comparaciones múltiples (Bonferroni cuando corresponda), y el criterio de
   éxito/fracaso se escriben en el script ANTES de correrlo, no se deciden mirando el
   resultado. Se rompió esta regla dos veces en esta sesión (con ADX y con el piso de trades
   de un trial de timing) — las dos veces la conclusión final se sostuvo, pero el proceso
   estaba mal y quedó documentado como lección.
2. **El test cross-sectional correcto es intra-día con Newey-West, nunca pooled.** Un rank IC
   pooled (todas las fechas y símbolos mezclados) mide la dirección del mercado, no habilidad
   de selección — es el error más importante que se corrigió en toda la investigación.
3. **Si un trial no cumple el criterio, se revierte automáticamente.** Revertir = borrar el
   script, dejar el artefacto de evidencia archivado, la producción nunca se toca durante el
   experimento (inyección por subclase/mock, no por edición directa del motor real).
4. **Ninguna señal en vivo se muestra al usuario antes de pasar el gate de validación.**
   Mostrar una señal con IC negativo o sin validar como si fuera una recomendación real es
   activamente engañoso.
5. **Nunca citar una fuente externa (paper, repo, foro) sin verificarla primero.** Ver el caso
   de "medallion-pub" en `PLAN_MEJORA_MATEMATICA.md` §13 — un repo de GitHub con 0 estrellas
   fue citado como si tuviera datos reales del Medallion Fund. No vuelva a pasar.
6. **Actualizar `ROADMAP.md` cuando algo se cierra o aparece algo nuevo.** No dar nada por
   cerrado "de palabra" — si no está marcado en la tabla, para el próximo agente no existe.
7. **Nunca pegar tokens/credenciales en el chat.** Ya pasó dos veces en este proyecto
   (QuantConnect, dos incidentes separados). Si aparece un secreto en la conversación,
   asumilo comprometido y pedile al usuario que lo rote — no lo repitas, no lo guardes en un
   archivo trackeado por git.

---

## Estado actual del proyecto (resumen ejecutivo)

- **Investigación**: rama de selección/timing sobre 50 símbolos cerrada, sin señal comercial
  (ver arriba, ahora con PBO + OOS fresca reforzando la conclusión). Plan de integración de
  indicAgent (`PLAN_INTEGRACION_INDICAGENT.md`, 11 tickets T0.1-T2.3) **100% completo y
  verificado** (2026-08-20/22): incluye el fix de T0.2 (lookahead de ejecución), stop/target
  estructural (T1.4, no promovido), OFI/CVD/Hurst/vol-regime como diagnósticos sin edge,
  bootstrap CI para métricas. Nada de esto se promovió al motor por defecto — todo quedó
  disponible pero sin trial que lo valide como para reemplazar momentum+RSI.
- **Código**: auditoría técnica completa hecha. Los 3 ítems críticos (P0) y todo P1 cerrados.
  Dashboard institucional + API de costos + universo 50 correcto (ex-bug de 44 símbolos)
  desplegados permanentemente vía launchd (`com.fortresscore.api`/`.dashboard`).
- **Tests**: 358 passed (backend), ruff limpio. Cero tests de frontend.
- **Seguridad**: repo público en GitHub. Backup de `fortress.db` y espejo en disco externo
  automatizados. Orca (orquestador de agentes) tiene 2 IP de red no identificadas bloqueadas
  por firewall (`pfctl`, anchor `orca_block`) — **ojo**: ese firewall también bloqueó por un
  rato la conexión de Claude Code corriendo dentro de Orca (falso positivo, no confirmado el
  culpable exacto); si Claude Code dentro de Orca da "Connection refused", revisar primero
  si `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` apuntan al router local (`9router`,
  `localhost:20128`, seteados en `.zshrc` global) antes de sospechar del firewall — hacer
  `unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY` antes de lanzar `claude` en esas terminales.

## Decisiones de producto ya tomadas — no re-litigar sin evidencia nueva

- **No conectar a un broker real** hasta validar que algo sobrevive con costos reales de
  ejecución. Es la decisión de mayor consecuencia del proyecto — no se cambia por default.
- **No perseguir "escalar en serio"** (datos de alta frecuencia, miles de instrumentos,
  ejecución de baja latencia) — los recursos reales son una Mac personal + una VPS chica + un
  disco externo de 3TB. Alcanza para investigación seria a frecuencia diaria, no para
  competir en microestructura. Esta decisión se tomó explícitamente comparando contra lo que
  de verdad hace falta para un enfoque estilo Renaissance Technologies.
- **LEAN/QuantConnect está parqueado, con intención de uso futuro (2026-08-14, aclarado por
  el usuario)** — se instaló y funciona (backtest local verificado), pero no se retoma ahora.
  Dos casos de uso concretos ya identificados para cuando corresponda: (1) datos más amplios
  que yfinance si el universo se expande algún día, a bajo costo relativo; (2) conexión a
  broker real si alguna vez hay una señal validada que ejecutar (hoy no existe motor de
  ejecución en el proyecto). Filosofía explícita del usuario: bajo costo, eficiente, no
  invertir sumas grandes en algo sin retorno probado — el software "se paga solo" con
  rentabilidad futura, no se paga por adelantado. Por eso la imagen Docker
  (`quantconnect/lean`, ~42.5GB) se borró del disco local el 2026-08-14 por espacio — es
  100% recuperable gratis con `docker pull` cuando se retome esta línea; no se pierde nada
  al borrarla hoy. Nota: la API de QuantConnect requiere organización de pago para tokens
  propios (tier gratuito lo bloquea) — revisar si sigue así cuando se retome.
- **El sistema multi-agente (Bull/Bear/Contrarian → Controller → Professor → Judge) es real
  pero parcialmente determinista** — sólo el agente Professor llama efectivamente a un LLM
  (NVIDIA NIM); Controller y Judge son deterministas por diseño, aunque la documentación vieja
  decía lo contrario (ya corregido en el código, si el docstring todavía no lo refleja está
  en `ROADMAP.md` P1).

## Convenciones técnicas del repo

- Python 3.9.6 real (`backend/.venv`) — el `Dockerfile` dice 3.11, es una inconsistencia
  conocida, no asumas que el contenedor se comporta igual que el entorno local.
- Scripts de diagnóstico/investigación van en `backend/scripts/`, siempre con docstring de
  metodología pre-registrada arriba. Sus artefactos (con timestamp) van a
  `backend/data/cache/` — nunca confíes en un número sin abrir ese archivo.
- Git: auto-backup corre solo cada ~10-20 min (commits `auto-backup: <timestamp>`, ruidosos
  pero funcionan). Encima de eso, cerrar cada unidad de trabajo real con un commit descriptivo
  a mano y push a `origin/main` (repo público, no hay rama de staging).
- **Puntos de entrada de agentes — ambos apuntan a este archivo**: `AGENTS.md` (OpenCode/
  agentes que lo leen automáticamente) y `CLAUDE.md` (Claude Code). Si agregás un agente nuevo,
  registralo acá con su archivo de auto-carga.
- **Mecanismos automáticos de esta Mac (launchd)**: `com.fortresscore.autobackup.plist`
  está INSTALADO (`~/Library/LaunchAgents/`) y dispara el backup git + espejo en el disco
  externo. `com.fortresscore.dataupdater.plist` está INSTALADO (2026-08-17): a las 22:00
  diarias actualiza precios OHLCV del universo 50 (yfinance incremental) + acumulación
  FinBERT de earnings (EDGAR incremental), log en `scripts/data_updater.log`.
  `com.fortresscore.api.plist` y `com.fortresscore.dashboard.plist` están INSTALADOS
  (2026-08-20): el backend (uvicorn) permanente en :8000 y el dashboard (vite preview
  del `dist/`) permanente en **http://localhost:3000** (puerto 3000 porque
  CORS_ORIGINS lo permite). Ambos KeepAlive/RunAtLoad; logs en `scripts/api_server.log`
  y `scripts/dashboard_server.log`. Tras cada rebuild del frontend:
  `launchctl kickstart -k gui/$(id -u)/com.fortresscore.dashboard`.
  `com.fortresscore.daily_notify.plist` vive en `scripts/` pero NO está instalado
  (requiere TELEGRAM/SMTP configurados — hoy vacíos, notificación desactivada). `backup.sh`
  es el backup manual/forzado. Los snapshots de `fortress_core_backups/snapshots/` son
  manuales y viejos — el espejo vigente es `current/`. `com.fortresscore.pipeline.plist`
  está INSTALADO (2026-08-26 16:42): ventanas 09:35/15:40/22:10 ET (ENTER/EXIT/DECIDE del
  pipeline diario de paper trading), fuera de ventana corre fase `health`. Log canónico
  `scripts/pipeline_diario.log` (NO `pipeline_launchd.log`, que queda en 0 bytes por
  diseño — todo se redirige al primero). Checkpoint Semana 1 verificado 27/08 (orden
  invertido vs. el plan original, que pedía verificar antes de instalar — documentado,
  no bloqueante). `com.fortresscore.bovedabackup.plist` está INSTALADO (2026-08-27, diario
  23:30): copia `~/Desktop/BOVEDA-CLAVES-*.md.enc` a `/Volumes/EMPRESA` sin descifrar
  nunca nada — mismo principio que `backup_db()`. Log `scripts/boveda_backup.log`.
  `com.fortresscore.diskhealth.plist` está INSTALADO (2026-08-28, cada 4h): avisa en
  `scripts/disk_health.log` si el disco libre baja de 15GB o si `~/.cline`/`.kilo`/
  `.opencode`/`.claude` supera 5GB — nunca borra nada solo. Nació del incidente real
  del 27-28/08: `~/.cline/data/db/hub-events-hub-production.db` (log interno de
  Cline nunca podado) creció a 95GB y dejó la Mac en 53MB libres, tumbando una
  corrida de Kilo a mitad de noche. Es un bug de Cline, no de este proyecto — puede
  repetirse, este chequeo solo avisa temprano.
- El universo base de símbolos es consistente entre scripts: `SPY, QQQ, AAPL, MSFT, GOOGL,
  AMZN, NVDA` + `NEW_UNIVERSE` (definido en `backend/scripts/fetch_universe_data.py`).

---

## Cómo arrancar, en la práctica

1. Leé `ROADMAP.md` — ahí está la tabla actualizada de qué hacer.
2. Si vas a tocar algo del motor predictivo/investigación, buscá primero si ya se probó en
   `PLAN_MEJORA_MATEMATICA.md` o `RESUMEN_VALIDACION_VARIABLES.md` — es común que una idea que
   parece nueva ya se haya testeado y refutado.
3. Si vas a tocar código de infraestructura/API/frontend, revisá el ítem correspondiente en
   `AUDITORIA_TECNICA.md` para el detalle exacto del hallazgo antes de arreglarlo a ciegas.
4. Al terminar, actualizá `ROADMAP.md` (marcar cerrado o agregar lo nuevo) y comiteá con
   mensaje descriptivo.

---

## Trabajar desde la CLI (OpenCode en terminal)

OpenCode **no tiene migración pendiente entre interfaces**: la app de escritorio y la CLI en
terminal son el mismo motor con la misma config. Verificado 2026-08-12:

- Config única: `~/.config/opencode/` — `AGENTS.md` (reglas/persona), `opencode.json`, skills,
  plugins y MCP servers (`context7`, `engram`, `gbrain`). Desktop y CLI leen exactamente lo mismo.
- Sesiones y credenciales compartidas: `~/.local/share/opencode/` (historial `opencode.db`,
  `auth.json`). Nada es exclusivo de la app de escritorio.
- Memoria persistente (Engram): se indexa **por proyecto (el cwd de donde arrancás)**, no por
  interfaz. Arrancar desde el directorio equivocado fragmenta el contexto.

Arranque recomendado para este proyecto: `cd ~/Desktop/fortress_core && opencode`.
Con eso el namespace de memoria, las rutas relativas y git apuntan a un solo lugar.

Otros agentes: Claude Code lee `CLAUDE.md` del repo (apunta a este archivo); agentes que leen
`AGENTS.md` también llegan acá. Dos archivos, un solo punto de entrada.

---

## Ritual de apertura de sesión — si la conversación se perdió

Las conversaciones de Kilo viven en `~/.local/share/kilo/kilo.db` y NO se pierden al reiniciar
la máquina ni al actualizar la extensión. Para retomar la última sesión:

1. **Doble clic** en `~/Desktop/Recuperar-Sesion-Fortress.command` (abre Terminal y ejecuta el script), o
2. Desde Terminal: `fs` (alias en `~/.zshrc`) → retoma la última sesión.
   - `fs --listar` → muestra las sesiones guardadas
   - `fs --nueva` → arranca sin retomar nada

El script `scripts/recuperar_ultima_sesion.sh` resuelve el binario de la extensión (puede
cambiar de número de versión cuando se actualiza) y consulta la base de datos de sesiones
para encontrar la última sesión con `directory='/Users/boris/Desktop/fortress_core'`.

Si el script no funciona (extensión no instalada), el fallback es abrir VS Code una vez —
eso repara o instala la extensión automáticamente — y luego volver a intentar.

---

## Ritual de cierre de sesión — no cerrar sin esto

Cada sesión que toque código, documentos o estado deja el MISMO rastro, para que la próxima
arranque sin preguntarte nada:

1. **Estado**: actualizá `ROADMAP.md` (cerrar / agregar pendientes) y agregá una entrada con
   timestamp a `SESSION_LOG.md` (qué se hizo, por qué, veredicto con artefacto).
2. **Commit + push**: commit descriptivo (conventional commits) + `git push origin main`.
   El auto-backup cada 10-20 min documenta, pero no explica decisiones — el commit a mano sí.
3. **Espejo de recuperación**: sincronizá el disco externo:
   `rsync -a --delete --exclude .git --exclude node_modules --exclude .venv --exclude __pycache__ ~/Desktop/fortress_core/ /Volumes/EMPRESA/fortress_core_backups/current/`
4. **Memoria del agente**: guardar en Engram (proyecto **"boris"**) — qué se hizo, qué queda,
   adónde apunta el próximo paso. Si el proyecto no está indexado, crearlo con esa clave.
5. **Secretos**: si algo sensible cambió (claves, credenciales, tokens), re-cifrar la bóveda
   `BOVEDA-CLAVES-FORTRESS-CORE.md.enc` (Escritorio + `/Volumes/EMPRESA`) SOLO con autorización
   explícita del usuario. La passphrase vive únicamente en el Llavero de macOS
   (servicio `BovedaFortressCoreMasterKey`) — nunca en archivos ni chats.
