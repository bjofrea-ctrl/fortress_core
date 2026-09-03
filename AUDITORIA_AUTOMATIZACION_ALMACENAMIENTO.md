# Auditoría de Automatización y Almacenamiento — 2026-09-03

Auditoría de infraestructura (mantenimiento, no investigación). Ejecutada por Kilo Code
(worktree `test-kilo-orca`) contra el repo autoritativo `~/Desktop/fortress_core` (main,
commit base 55633ac). Todo lo afirmado abajo fue verificado contra el artefacto real
(launchctl, logs, plists, df/du) el 2026-09-03 ~08:15 EDT.

---

## 1. Inventario launchd: qué debería existir vs qué existe

**Crontab: vacío.** Toda la automatización del proyecto es launchd (LaunchAgents de usuario).

### Estado por job (10 plists en repo + 1 huérfano detectado)

| # | Job (Label) | Commiteado en repo | Cargado en launchd | Última corrida real (log) | Exit | Estado |
|---|---|---|---|---|---|---|
| 1 | `com.fortresscore.api` | sí | sí (idéntico) | viva (uvicorn, log 09-03 06:40) | 0 | OK |
| 2 | `com.fortresscore.dashboard` | sí | sí (idéntico) | viva (vite preview :3000, log 09-03 06:06) | 0 | OK |
| 3 | `com.fortresscore.dataupdater` | sí | sí (idéntico) | 09-02 22:03, rc=0 (`data_updater.log`) | 0 | OK |
| 4 | `com.fortresscore.pipeline` | sí | sí (idéntico) | 09-02 22:10 fase health, rc=0 (`pipeline_diario.log`) | 0 | OK |
| 5 | `com.fortresscore.backupdatos` | sí | sí (idéntico) | 09-02 23:20, 4 grupos, 367M (`backup_datos.log`) | 0 | OK |
| 6 | `com.fortresscore.bovedabackup` | sí | sí (idéntico) | 09-03 06:06 (kickstart), 0 actualizados, 2 sin cambios | 0 | OK* |
| 7 | `com.fortresscore.diskhealth` | sí | sí (idéntico) | 09-03 06:06, 0 avisos, 86GB libres | 0 | OK |
| 8 | `com.fortress.data-freshness` | sí | sí (idéntico) | 09-03 07:06, errores=0 warnings=0 | 0 | OK |
| 9 | `com.fortresscore.intraday` | **NO estaba → ARREGLADO** | sí | 09-03 07:36, 0 barras nuevas (mercado cerrado, correcto) | 0 | FIXED |
| 10 | `com.fortresscore.autobackup` | **NO estaba → ARREGLADO** | sí | corre cada 10 min (commits auto-backup en git log) | 0 | FIXED |
| 11 | `com.fortresscore.fundamentals_screen` | sí | **NO estaba → CARGADO HOY** | solo corridas manuales (últ. 09-02 18:17, con error de render) | — | FIXED (primera corrida launchd: hoy 22:30) |
| 12 | `com.fortresscore.daily_notify` | sí | NO (intencional) | nunca | — | BY DESIGN: requiere TELEGRAM/SMTP configurados (vacíos per ONBOARDING); no cargar hasta configurar |

*bovedabackup: un `Permission denied` puntual en `boveda_backup_launchd.log` (09-01 06:46,
ambas bóvedas) durante un episodio de montaje del disco externo; verificado hoy: ambas
bóvedas presentes e **idénticas** byte a byte en `/Volumes/EMPRESA` (`cmp` OK). El job
funciona; el error fue del montaje, no del script.

### Hallazgos y acciones tomadas

1. **`fundamentals_screen` commiteado pero nunca cargado** (el caso ya conocido, confirmado
   como el único pendiente además de `daily_notify` que es intencional). Verificado no
   destructivo antes de cargar: `fundamentals_screen_daily.sh` + `run_fundamentals_screen.py`
   solo escriben artefactos en `backend/data/cache_fundamentals_screen/` (json/html/xlsx +
   `state.json` resumible) y append a logs; sin `rm`/`rmtree`/`DELETE`; no toca credenciales
   (FMP_API_KEY la lee Settings desde `.env`); política de cuota FMP explícita sin reintentos
   el mismo día; `RunAtLoad=false` → cargarlo NO disparó ninguna corrida (primera corrida
   programada: hoy 22:30, tras dataupdater 22:00). **Acción: copiado a
   `~/Library/LaunchAgents/` y `launchctl load -w`** — verificado en `launchctl list`
   (`- 0 com.fortresscore.fundamentals_screen`).
   Nota: las corridas manuales del 02/09 terminaron con "screening 0 símbolos → falló
   render" (FMP devolvía vacío para varios tickers, state.json lo refleja); con `--resume`
   el job de esta noche retoma desde el último símbolo exitoso. A verificar mañana en
   `scripts/fundamentals_screen_launchd.log`.
2. **Drift inverso detectado y cerrado: `intraday` y `autobackup` cargados pero sin plist en
   repo.** Ambos plists existían solo en `~/Library/LaunchAgents/` — si la Mac se restaura
   desde GitHub, la automatización del colector intradía y del auto-backup git se perdían
   silenciosamente. **Acción: copiados a `scripts/` y commiteados** (junto con este
   documento). Con esto, los 12 jobs del proyecto quedan 100% versionados.
3. **Cero drift contenido**: para los 8 jobs que existían en ambos lados, `diff` plist
   repo vs instalado = idéntico en todos.
4. **Ningún plist fortress en `/Library/LaunchAgents|Daemons`** (system-wide) — correcto,
   todo es user-level. `launchctl print-disabled`: solo `com.fortress.data-freshness`
   figura "enabled" (estado normal, no disabled).
5. Jobs launchd de otros proyectos (medpersonal, agent-disk-guard, 9router) fuera del
   alcance de esta auditoría; no interfieren con los fortress.

### Verificación post-carga (recomendada para mañana 09-04)

```bash
launchctl list | rg fundamentals          # exit 0 y LastExit de la corrida 22:30
tail -20 ~/Desktop/fortress_core/scripts/fundamentals_screen_launchd.log
ls -la ~/Desktop/fortress_core/backend/data/cache_fundamentals_screen/  # screen_2026-09-03.json
```

---

## 2. Disco y almacenamiento

### Estado actual (2026-09-03 ~08:15)

| Disco | Tamaño | Usado | Libre | Umbral | Veredicto |
|---|---|---|---|---|---|
| Interno (`/`, APFS 234Gi) | 234Gi | ~124Gi (Data) | **83Gi (86GB reportados por disk_health)** | 15GB libres (criterio `check_disk_health.sh`) | **holgado, 5.5× sobre el umbral** |
| Externo `/Volumes/EMPRESA` (1.8Ti) | 1.8Ti | 56Gi | ~1.8Ti | — | montado y sano |

Directorios de agentes (umbral diskhealth: 5GB cada uno): `~/.claude` 2.2GB (el más
pesado, 44% del umbral — vigilar), `~/.cline` 260MB, `~/.kilo` 245MB, `~/.opencode` 199MB.
Cero avisos en la última corrida de `check_disk_health.sh` (09-03 06:06).

### Tamaño de los datos del proyecto (medido)

- `backend/data/cache/` completo: **65MB** (de los cuales EDGAR 22MB, spy/qqq_1min 13MB,
  ranking_panel 5.3MB, intraday_1min 924KB)
- `backend/data/` total: 65MB · `backend/fortress.db`: 136KB · `data/` raíz: 6.1MB
- Intradía 1min (7 parquets): 2,317–2,400 filas cada uno, 91–102KB por símbolo
- Artefactos fundamentals screen: 448KB acumulados (1 día)

### Estimación de crecimiento semanal (medido, no supuesto)

| Fuente | Medición base | Crecimiento/semana |
|---|---|---|
| Intradía 1min, 7 símbolos, cada 30min | ~40 bytes comprimidos/barra × 390 barras/día × 7 | **~0.55MB/sem** (~28MB/año) |
| Intradía 1min si se expandiera a 102 símbolos | escala ×14.6 | ~8MB/sem (~410MB/año) |
| Fundamentals screen diario (xlsx 379KB + html 63KB + json) | 1 día hábil medido | **~2.3MB/sem** (~120MB/año) |
| OHLCV diario 102 símbolos (incremental yfinance) | ~2-4KB/símbolo/día | ~2-3MB/sem |
| FinBERT/EDGAR earnings (incremental, solo filings nuevos) | 22MB acumulados históricos | <1MB/sem |
| Logs launchd (todos los jobs) | 1.3MB total hoy | <0.5MB/sem |
| **TOTAL backend/data/cache estimado** | | **~5-6MB/semana ≈ 300MB/año** |

### Veredicto almacenamiento

**No se requiere ninguna acción de storage ahora.** El proyecto completo de datos crece
~300MB/año contra 83GB libres — años de holgura. El incidente de los 95GB de agosto fue
`~/.cline` (bug de Cline), no datos del proyecto; la vigilancia existente (diskhealth cada
4h con umbral 15GB + agent-disk-guard cada 6h con umbral 5GB/dir) cubre ese vector.

**Pre-acuerdo preventivo (a pedido de Boris, aplica ANTES de que sea problema):** si el
disco interno baja de **30GB libres** (2× el umbral de alerta), prioridad de migración al
externo (1.8TB libres, montado): 1º nuevos artefactos grandes de backtests
(`backend/data/cache/*.parquet` de corridas > 100MB), 2º `FortressCore_Fuentes/` pasa a ser
fuente primaria con rsync inverso. **Nada se borra nunca sin confirmación explícita de
Boris** — esta auditoría no borró ni movió nada.

Recomendación única de optimización (no ejecutada, requiere tu OK): los backtests largos
del worktree de investigación podrían escribir directo a `/Volumes/EMPRESA`, pero al ritmo
actual (5-6MB/sem) no justifica tocar los scripts.

---

## 3. Estado de los respaldos (verificado hoy)

- `backupdatos` (23:00 diario): funcionó ayer 23:20, 367M totales en
  `/Volumes/EMPRESA/FortressCore_Fuentes/`, sin `--delete` (a propósito).
- Bóvedas: 2/2 idénticas byte a byte entre Desktop y EMPRESA (episodio Permission denied
  del 01/09 fue del montaje, auto-resuelto).
- Espejo completo `fortress_core_backups/current/`: 1.3GB (autobackup cada 10 min).
- Git: repo público GitHub sincronizado (auto-backup + commits manuales).

---

*Generado por la auditoría de infraestructura 2026-09-03. Próxima auditoría de este tipo:
sin fecha fija — gatillar si se agrega un job nuevo, se expande el colector intradía a los
102 símbolos, o diskhealth emite su primer aviso.*
