# PLIST_TZ_AUDIT.md

Auditoría de zona horaria de los jobs launchd de Fortress Core.
Generado 2026-09-07 (auditoría profunda Kilo, items menores).

## Contexto
- El Mac de Boris corre en **ART** = `America/Argentina/Buenos_Aires` (UTC-3, **sin DST**).
- launchd interpreta `StartCalendarInterval` en la hora LOCAL del sistema (ART).
- El mercado US y los datos que consumen varios colectores viven en **ET** (`America/New_York`,
  UTC-5 EST en invierno ~nov–mar, UTC-4 EDT en verano ~mar–nov).
- Por eso un mismo horario ART tiene dos equivalencias ET según la época del año.

## Jobs cargados (launchctl list, 14)

| # | Label | Trigger repo (ART) | Trigger desplegado (ART) | Equiv ET (sobre repo) | DST | Origen |
|---|-------|--------------------|---------------------------|------------------------|-----|---------|
| 1 | com.fortress.data-freshness | relativo 3600s | relativo 3600s | N/A (no pared) | N/A | repo |
| 2 | com.fortresscore.agentwatcher | KeepAlive | KeepAlive | N/A | N/A | LaunchAgents sólo |
| 3 | com.fortresscore.api | KeepAlive | KeepAlive | N/A | N/A | repo |
| 4 | com.fortresscore.autobackup | relativo 600s | relativo 600s | N/A (no pared) | N/A | repo |
| 5 | com.fortresscore.backupdatos | 23:00 | 23:00 | 23:00→21:00 ET/22:00 ET | sí (salta ±1h ET) | repo |
| 6 | com.fortresscore.bovedabackup | 23:30 | 23:30 | 23:30→21:30 ET/22:30 ET | sí (salta ±1h ET) | repo |
| 7 | com.fortresscore.dashboard | KeepAlive | KeepAlive | N/A | N/A | repo |
| 8 | com.fortresscore.dataupdater | 22:00 | 22:00 | 22:00→20:00 ET/21:00 ET | sí (salta ±1h ET) | repo |
| 9 | com.fortresscore.diskhealth | relativo 14400s | relativo 14400s | N/A (no pared) | N/A | repo |
| 10 | com.fortresscore.fundamentals_screen | 22:30 | 22:30 | 22:30→20:30 ET/21:30 ET | sí (salta ±1h ET) | repo |
| 11 | com.fortresscore.intraday | relativo 1800s | relativo 1800s | N/A (no pared) | N/A | repo |
| 12 | com.fortresscore.ivcollector | 22:35 | 22:35 | 22:35→20:35 ET/21:35 ET | sí (salta ±1h ET) | repo |
| 13 | com.fortresscore.keepawake | KeepAlive | KeepAlive | N/A | N/A | LaunchAgents sólo |
| 14 | com.fortresscore.pipeline | 09:35; 15:40; 22:10 | 10:35; 16:40; 23:10 | 09:35→07:35 ET/08:35 ET; 15:40→13:40 ET/14:40 ET; 22:10→20:10 ET/21:10 ET | sí (salta ±1h ET) | repo ⚠ repo≠desplegado |

## Notas / hallazgos
- **14 jobs cargados** en launchctl. `com.fortresscore.agentwatcher` y `com.fortresscore.keepawake`
  NO tienen plist en el repo (solo en `~/Library/LaunchAgents`); su trigger es KeepAlive, sin pared.
- **Divergencia pipeline** ⚠: el plist del repo (`com.fortresscore.pipeline.plist`) dice
  `09:35 / 15:40 / 22:10 ART`, pero el plist DESPLEGADO en LaunchAgents dice
  `10:35 / 16:40 / 23:10 ART` (**+1h en cada disparo**). launchd ejecuta el de LaunchAgents,
  así que el horario REAL hoy es 10:35/16:40/23:10. Causa probable: ajuste manual por DST
  (ART no tiene DST, así que el +1h es arbitrario). **Decisión pendiente de Boris/Kilo**:
  ¿cuál es el horario intencional? Al mergear el repo, el horario bajaría a 09:35/15:40/22:10.
- **Dos plists `freshness`**: `com.fortress.data-freshness` (cargado, `check_data_freshness.sh` 1h) y
  `com.fortresscore.data-freshness` (NO cargado, `check_session_log_freshness.py` 4h). Tras esta
  auditoría el check de session-log se integró DENTRO del latido (`check_data_freshness.sh`), por lo
  que el plist separado es redundante; se recomienda eliminarlo para evitar confusión de labels.
- **`com.fortresscore.daily_notify.plist`** existe en el repo pero NO está cargado en launchctl.
- La integración del latido se detalla en el commit de esta auditoría.

## Plists en repo NO cargados (anexo)

- `com.fortresscore.daily_notify` — 16:30 ART — NO cargado
- `com.fortresscore.data-freshness` — relativo 14400s — NO cargado
