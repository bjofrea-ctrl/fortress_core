# M5b — Verificación de captura intradía 2026-09-07 (post keep-awake)

**Ticket**: M5b-VERIFICATION (Kilo, 2026-09-07) · **Autor**: OpenCode · **Worktree**: `test-opencode-orca`
**Task ID**: task_000ed0c7b7dc · **Dispatch**: ctx_2588fa9253e1

---

## Veredicto

**El mecanismo M5 funciona: tras la activación del keep-awake (caffeinate PID 63704, 11:56:43
-03), el colector intradía corrió sin un solo gap de Mac dormida.** El día 2026-09-07 produce
0 barras nuevas **porque es Labor Day** (mercado US cerrado — confirmado contra el calendario
oficial de Alpaca), no por dormida ni por falla del colector.

| Métrica | Resultado |
|---|---|
| Runs post-keepawake (11:56→14:34 -03) | 7 corridas (12:02, 12:32, 13:02, 13:33, 14:03, 14:34 + una en curso) — **cero gaps** |
| Assertions de energía (pmset) | `PreventUserIdleSystemSleep` + `PreventSystemSleep` sostenidas por PID 63704 desde 11:56:43, renovadas en cada summary |
| Barras nuevas hoy | 0 — **correcto**: 2026-09-07 NO es día de trading (Labor Day) |
| Calendario Alpaca (autoritativo) | 2026-09-03 ✓ · 2026-09-04 ✓ · **2026-09-07 ausente** · 2026-09-08 ✓ — salta de 04 a 08 |
| Estado del parquet | 30/30 símbolos intactos, última barra 2026-09-04 20:00Z (cierre del viernes) |

## Evidencia

### 1. Keep-awake activo y sostenido

- `ps`: `caffeinate -i -s` PID 63704, iniciado 11:56 (verificado vivo 14:30+).
- `pmset -g assertions`: `PreventUserIdleSystemSleep 1` con PID 63704 como owner.
- `scripts/keep_awake.log`: el job `com.fortresscore.keepawake` (launchd, KeepAlive) chequea
  cada 30s; desde 11:56 registra ininterrumpidamente "caffeinate ya corriendo (PID 63704)
  — no se lanza otro".
- pmset log: `PID 63704(caffeinate) Created PreventSystemSleep ... 11:56:43 -0300` y summaries
  periódicos con el contador de assertion en aumento (00:13:18 → 00:43:18 → …), es decir,
  la assertion nunca se soltó.
- El guard de horario del script (09:25–16:05 ET weekdays) no mató el caffeinate: hoy es
  lunes dentro de horario — consistente.

### 2. Colector intradía corrió hoy SIN gaps post-11:56

Timestamps exactos de runs (decodificados de `X-RateLimit-Reset` en
`scripts/intraday_collector.log`, zona America/Santiago):

```
07-09-2026: 01:26 01:56 02:26 02:56 03:27 03:57 04:27 04:57 05:28 05:58 06:28
            06:58 07:28 07:59 08:29 08:59 | GAP 1h (Mac dormida) | 10:00 10:30
            11:00 11:31 | GAP 30min (ver nota) | 12:02 12:32 13:02 13:33 14:03 14:34
```

- Cada run: `requests=30 barras=0`, headers `X-RateLimit-Remaining≈184-198/200` — el colector
  está vivo, autenticado y dentro de cuota; 0 barras porque el mercado está cerrado
  (Labor Day) — la API no devuelve barras para hoy.
- La última barra de todos los símbolos es `2026-09-04T20:00:00Z` (= 16:00 ET viernes,
  cierre de sesión) — sin barras de sábado/domingo/Labor Day, exactamente lo esperado.
- Los dos gaps pre-11:56 (08:59→10:00 y 11:31→12:02) ocurrieron **antes** de que el
  keepawake estuviera activo (cargado 11:56); son dormidas de la Mac legítimas del
  régimen pre-M5, no fallas del colector.

### 3. Benchmark pre-gate (viernes 2026-09-04) — el contraste que motivó M5

El viernes la Mac durmió **dentro** de la sesión de mercado:

- Runs del log: `… 12:21 12:51 13:21` → **gap de 7h31m** → `20:52 21:22 21:53 …`
  (13:21 local = 12:21 ET intra-sesión; el gap cubre 12:21→19:52 ET, casi toda la tarde
  de trading).
- **Sin embargo, la captura del viernes está completa**: SPY terminó el día con 400 barras
  de sesión (benchmark de días previos: 393-399) porque el diseño incremental del colector
  (`collect_one` descarga desde `last_ts+1min`) recuperó las barras de la tarde al primer
  run post-wake (sábado 09:30 local — mtime de los parquets lo confirma).
- Es decir: el benchmark pre-gate demuestra que el diseño incremental ya era resiliente a
  la dormida (recupera al despertar), pero con degradación de latencia de hasta 7h por
  sesión. M5 elimina esa degradación: con caffeinate activo no hay dormida intra-sesión.

### 4. "0 barras nuevas" hoy ≠ falla — es Labor Day

Confirmación triple e independiente:
1. Calendario Alpaca `/v2/calendar` (paper-api, credenciales del propio cliente):
   días de trading alrededor: 03, 04, **08** — el 07 no figura.
2. Regla: primer lunes de septiembre = Labor Day (2026-09-07 es primer lunes).
3. La API devuelve 0 barras con auth OK y quota OK (`X-RateLimit-Remaining=184+`) —
   comportamiento de mercado cerrado, no de error.

## Ticket 2 — Cableado intraday ↔ caffeinate (reporte + estado)

**Pregunta de Kilo**: ¿el plist `com.fortresscore.intraday` llama a caffeinate o el script lo hace?

**Respuesta verificada contra artefactos**:
- `scripts/com.fortresscore.intraday.plist` (idéntico al instalado en
  `~/Library/LaunchAgents/`): ejecuta directo
  `python -m scripts.collect_intraday_1min` cada 1800s — **NO llama caffeinate**.
- `backend/scripts/collect_intraday_1min.py`: cero referencias a caffeinate/pmset —
  **NO gestiona energía**.
- La energía la gestiona el job dedicado `com.fortresscore.keepawake` (launchd KeepAlive)
  que corre `scripts/keep_awake_market_hours.sh` (bucle 30s, caffeinate `-i -s` dentro de
  09:25–16:05 ET weekdays, se apaga solo fuera de horario).

**Evaluación**: el cableado actual es **correcto por diseño** — separación de
responsabilidades: (a) el colector es puro fetching de datos, (b) la política de energía
vive en un solo lugar audit. El viernes demuestra que aunque el colector "pierda" runs por
dormida, el diseño incremental recupera las barras al despertar (0 pérdida de datos, solo
latencia). Con keepawake activo, ni siquiera se pierde latencia.

**Fix gate-legal aplicado / recomendación**: nada que cambiar en el colector o su plist.
La única acción pendiente es de instalación en producción, ya resuelta: el plist
`com.fortresscore.keepawake` (derivado del template `__REPO_ROOT__` con rutas de
producción) ya está cargado (PID 63677) y verificado en este documento. **M5b CERRADO.**

## Aclaración de IDs (nota metodológica)

Kilo pidió registrar "I2 (intradía genuina)" e "I8 (shrinkage James-Stein)". Verificado
contra las fuentes canónicas (`AUDITORIA_NIVEL_DIOS_20260902.md` §I1-I10 y
`PLAN_REMEDIO_BRECHAS_20260903.md` Fase D):

- **I2 canónico** = "Unificar motores" (ya cerrado por B6 contrato de señal única).
- **I8 canónico** = "Test omnibus White Reality Check / Hansen SPA".
- Los conceptos pedidos — intradía genuina y shrinkage James-Stein — son canónicamente
  **D3** e **I4/D4** respectivamente.

Se registran los conceptos con sus refs canónicas correctas (D3 y I4/D4) en ROADMAP.md,
con nota de alias para no romper la trazabilidad con el dispatch de Kilo. No se propagaron
los IDs rotados al documento canónico.

## Artefactos citados

- `scripts/intraday_collector.log` — runs del colector, headers de rate limit.
- `scripts/keep_awake.log` — bucle del job keepawake.
- `pmset -g assertions` / `pmset -g log` — assertions de energía (PID 63704).
- Calendario Alpaca `/v2/calendar` (paper-api) — 2026-09-07 ausente.
- `backend/data/cache/intraday_1min/*.parquet` — 30/30 símbolos, última barra 09-04 20:00Z.
- Scripts: `backend/scripts/collect_intraday_1min.py`, `scripts/keep_awake_market_hours.sh`.
