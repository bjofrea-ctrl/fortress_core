# Diseño Latido de Datos — Vigilancia genérica de colectores

**Fecha**: 2026-09-02
**Régimen**: infraestructura mecánica, no investigación — mismo espíritu que `scripts/check_disk_health.sh`. No repara colectores, solo vigila y avisa.
**Objetivo GLM**: latido genérico que vigile TODOS los colectores de datos (OHLCV diario, earnings_sentiment, intraday_1min) con criterio de frescura explícito y log CLARO (prefijo `ERROR`), igual que el fix PRECIOS del `data_updater.sh`.

---

## 1. Colectores reales inventariados

Inventario con `fd`/`rg` sobre `scripts/`, `backend/scripts/`, `backend/app/core/`, `~/Library/LaunchAgents/*.plist`:

| # | Colector | Script / entrypoint | Cadencia esperada | Artefacto(s) vigilado(s) | LaunchAgent actual |
|---|----------|---------------------|-------------------|---------------------------|--------------------|
| 1 | **OHLCV diario** | `scripts/data_updater.sh` → `backend/app/core/data_ingestion.py:download_data` + `scripts/fetch_universe_data.py` (universo 102) | Diario 22:00 local (~16:00 ET) | `backend/data/cache/*.parquet` (canónico) + `data/cache/*.parquet` (legacy) — 1 parquet por ticker (OHLCV diario) | `com.fortresscore.dataupdater` (StartCalendarInterval 22:00) |
| 2 | **earnings_sentiment** | `backend/scripts/accumulate_earnings_sentiment.py` → `backend/app/core/earnings_sentiment.py:accumulate_earnings_sentiment` (FinBERT, SQLite dedup por accession) | Diario 22:00 (segundo paso de `data_updater.sh`) | `backend/data/cache/earnings_sentiment.db` (tabla `sentiment`, 778 filas al 2026-09-01) | mismo `com.fortresscore.dataupdater` |
| 3 | **intraday_1min** | `backend/scripts/collect_intraday_1min.py` → `AlpacaPaperClient.get_bars(feed=iex, 1Min)` | Cada 30 min (StartInterval 1800) | `backend/data/cache/intraday_1min/{SYMBOL}.parquet` (7 BASE_SYMBOLS: SPY,QQQ,AAPL,MSFT,GOOGL,AMZN,NVDA) | `com.fortresscore.intraday` (StartInterval 1800) |

`rg` adicional (`collect`, `intraday_1min`, `earnings_sentiment`, `fetch_universe`) no reveló otros colectores productivos vigentes. Fundamentales EDGAR (`fetch_edgar_universe_facts.py`, `build_fundamentals_panel.py`) y screenings PALAS son jobs ad-hoc, no cron continuo — fuera de alcance del latido v1.

### Paths resueltos

- `CACHE_DIR` diario es relativo `data/cache` desde `backend/` (`data_ingestion.py:7`). En launchd se resuelve vía `cd $REPO/backend` (fix del bug `ModuleNotFoundError` 2026-08-15/22).
- `earnings_sentiment.db` es `./data/cache/earnings_sentiment.db` relativo a `backend/` (`earnings_sentiment.py:63`), o `$FORTRESS_SENTIMENT_DB` si se setea.
- `CACHE_DIR` intraday es `Path(__file__).parent.parent / "data" / "cache" / "intraday_1min"` (`collect_intraday_1min.py:35`) — absoluto, no relativo.
- REPO canónico en plist: `/Users/boris/Desktop/fortress_core` (main). En worktree: `/Users/boris/orca/workspaces/fortress_core/test-opencode-orca`. El script acepta override `FORTRESS_REPO` o `REPO` env.

---

## 2. Criterio de frescura por colector

Mismo criterio que el fix **PRECIOS: ERROR** de `data_updater.sh:30-50` — fallo silencioso es bug, debe ser `ERROR` explícito en log. El latido replica: compara `mtime` del artefacto más reciente contra threshold; si supera, log `[ERROR] ... STALE`.

| Colector | Threshold base | Holgura y por qué | Threshold efectivo | Check adicional opcional |
|----------|---------------|-------------------|--------------------|--------------------------|
| **OHLCV diario** | 24h (diaria) | +6h holgura red/yfinance → **30h**. Fin de semana: Viernes 22:00 → Lunes 22:00 = 72h sin trading; si hoy es lunes, threshold **76h** (72+4). Sáb/dom no deben alertar falso positivo. | 30h (mar-dom), 76h (lunes) | Verificar que parquet más reciente tenga >0 filas (`python3 -c pyarrow` si pyarrow disponible; sino solo mtime) |
| **earnings_sentiment** | 24h (diaria) | Misma cadencia que OHLCV (segundo paso del updater). Misma holgura. | 30h / 76h lunes | `sqlite3 db "SELECT count(*) FROM sentiment"` debe ser >0 y no decrecer (no implementado v1, solo mtime) |
| **intraday_1min** | 30 min (cron 1800s) | +30 min tolerancia red/paginación → **60 min (1h)** durante mercado. Tolerancia fina 0.75h (45 min) redondeada a 1h para evitar flapping. | 1h solo si mercado abierto | Si mercado cerrado (fuera de 09:30-16:00 ET o fin de semana), **SKIP** — log `[OK] ... SKIP (market closed)` sin ERROR. Cálculo ET vía `zoneinfo` Python. |

> **No corrección por feriados US**: si un lunes es feriado (mercado cerrado), el parquet OHLCV quedará con mtime del viernes y el lunes 23:00 reportará `age 73h < 76h` → OK (no falso positivo). Si el feriado cae martes, el lunes sí hubo trading y threshold 30h aplica. Feriado largo sin actualización >76h sí alertará el martes — comportamiento deseado (requiere intervención).

### Cálculo de edad

- macOS `stat -f %m <path>` → epoch segundos del mtime (BSD stat; Linux usaría `stat -c %Y` pero el target es macOS).
- `now=$(date +%s)` (epoch).
- `age_h = (now - mtime) / 3600` con 1 decimal (`awk`).
- `mtime_human=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" <path>)` para log.

---

## 3. Formato de log

Coherente con `check_disk_health.sh` (timestamp, prefijo claro) y con el fix PRECIOS (`PRECIOS: ERROR`).

**Log file**: `$REPO/logs/data_freshness.log` (append, creado si no existe; `mkdir -p logs`). `StandardErrorPath` separado: `logs/data_freshness.error.log` solo para stderr de launchd.

**Líneas**:

```
[2026-09-02 13:00:01] data_freshness: inicio (repo=/Users/boris/Desktop/fortress_core)
[2026-09-02 13:00:01] [OK] ohlcv_diario fresh: age=5.2h <= threshold 30h (mtime 2026-09-02 07:45:12 path backend/data/cache/AAPL.parquet)
[2026-09-02 13:00:01] [OK] earnings_sentiment fresh: age=12.1h <= threshold 30h (mtime 2026-09-02 00:50:00 path backend/data/cache/earnings_sentiment.db)
[2026-09-02 13:00:01] [OK] intraday_1min SKIP (market closed, age=14.3h path backend/data/cache/intraday_1min/SPY.parquet)
[2026-09-02 13:00:01] [ERROR] intraday_1min STALE: age=1.8h > threshold 1.0h (last mtime 2026-09-02 11:12:00 path backend/data/cache/intraday_1min/SPY.parquet)
[2026-09-02 13:00:01] [WARN] ohlcv_diario missing: no parquet found in backend/data/cache/*.parquet nor data/cache/*.parquet
[2026-09-02 13:00:01] data_freshness: fin (errores=1 warnings=0)
```

Convenciones:
- Prefijos: `[OK]`, `[WARN]`, `[ERROR]` — grep-friendly (`rg "\[ERROR\]" logs/data_freshness.log`).
- Siempre incluye `age`, `threshold`, `mtime`, `path` (o patrón si missing).
- `inicio`/`fin` con conteo de errores para `check_disk_health` parity.
- Exit code del script **siempre 0** (no rompe cron/launchd), pero `ERROR` visible en log.

**Rotación**: no implementada v1 (append como `data_updater.log` y `disk_health.log`). Si crece, aplicar mismo patrón manual que `data_updater.sh` (truncar >10 MB) en v2.

---

## 4. Instalación launchd

**Plist fuente**: `scripts/com.fortress.data-freshness.plist` (en repo, versionado).

```xml
Label: com.fortress.data-freshness
ProgramArguments: /bin/bash /Users/boris/Desktop/fortress_core/scripts/check_data_freshness.sh
StartInterval: 3600 (cada hora)
RunAtLoad: true
StandardOutPath: /Users/boris/Desktop/fortress_core/logs/data_freshness.log
StandardErrorPath: /Users/boris/Desktop/fortress_core/logs/data_freshness.error.log
```

> En worktree el path es `/Users/boris/orca/workspaces/fortress_core/test-opencode-orca/scripts/check_data_freshness.sh` y `logs/` bajo worktree. El plist del repo usa path canónico main; ajustar al instalar desde worktree.

**Instalación** (idempotente, misma que `com.fortresscore.diskhealth`):

```bash
# 1. Copiar/symlink plist a LaunchAgents
cp scripts/com.fortress.data-freshness.plist ~/Library/LaunchAgents/com.fortress.data-freshness.plist
# o: ln -sf "$PWD/scripts/com.fortress.data-freshness.plist" ~/Library/LaunchAgents/com.fortress.data-freshness.plist

# 2. Cargar
launchctl load -w ~/Library/LaunchAgents/com.fortress.data-freshness.plist
# verificar
launchctl list | grep data-freshness
# correr a mano
launchctl kickstart -k gui/$(id -u)/com.fortress.data-freshness
tail -f logs/data_freshness.log
# desinstalar
launchctl bootout gui/$(id -u)/com.fortress.data-freshness 2>/dev/null; launchctl unload -w ~/Library/LaunchAgents/com.fortress.data-freshness.plist 2>/dev/null; rm ~/Library/LaunchAgents/com.fortress.data-freshness.plist
```

`RunAtLoad true` garantiza primer chequeo al login; `StartInterval 3600` corre cada hora sin `StartCalendarInterval` (paridad con `diskhealth` 14400).

---

## 5. Pruebas manuales

Sin ledger, sin parquet real requerido — usa archivos temp y `touch -t`:

```bash
# Ver chequeo real
bash scripts/check_data_freshness.sh
cat logs/data_freshness.log | tail -n 20
rg "\[ERROR\]" logs/data_freshness.log

# Forzar STALE: tocar un parquet a 3 días atrás
touch -t 202508300000 backend/data/cache/AAPL.parquet
bash scripts/check_data_freshness.sh; rg "ohlcv.*STALE" logs/data_freshness.log

# Forzar mercado abierto para intraday (simular): setear intraday parquet viejo
mkdir -p backend/data/cache/intraday_1min
touch -t $(date -v-2H +%Y%m%d%H%M) backend/data/cache/intraday_1min/SPY.parquet
# si el check corre dentro de 09:30-16:00 ET → debe dar STALE; fuera → SKIP

# Suite automatizada
bash tests/scripts/test_check_data_freshness.sh
```

La suite `tests/scripts/test_check_data_freshness.sh` crea `tmpdir` con estructura `backend/data/cache/` + `backend/data/cache/intraday_1min/`, toca mtimes viejos/recientes y verifica que el script emite `[ERROR]` vs `[OK]`/`SKIP`, usando `FORTRESS_REPO=$tmpdir` para aislar.

---

## 6. Qué NO hace (no repara)

- No re-ejecuta `data_updater.sh`, `collect_intraday_1min.py` ni `accumulate_earnings_sentiment.py`. Solo lee `stat` y loguea.
- No toca `ledger`, `parquet`, `cache`, credenciales (`ALPACA_*`, `FORTRESS_EDGAR_USER_AGENT`) ni `trial_registry.json`.
- No borra logs ni rota automáticamente.
- No envía notificaciones push/email — solo log local. Integración con `daily_notify` futura si se quiere.
- No valida contenido profundo (OHLCV NaN, FinBERT score drift) — solo frescura temporal y existencia.

---

## 7. Referencias

- Patrón: `scripts/check_disk_health.sh` (logging claro, umbral, `set -u`, append a `scripts/disk_health.log`, launchd 14400).
- Fix PRECIOS: `scripts/data_updater.sh:30-50` — `PRECIOS: ERROR` explícito tras `download_data` (Kilo había dejado cache 5 ruedas stale silencioso).
- Colectores: `backend/scripts/collect_intraday_1min.py:35` (CACHE_DIR), `backend/app/core/data_ingestion.py:7` (CACHE_DIR), `backend/app/core/earnings_sentiment.py:63` (DEFAULT_DB_PATH).
- Cron existentes: `~/Library/LaunchAgents/com.fortresscore.{dataupdater,diskhealth,intraday,pipeline}.plist`.
