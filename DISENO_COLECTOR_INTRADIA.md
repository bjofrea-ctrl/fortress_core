# Diseño Colector Intradía 1-min — I3

**Fecha**: 2026-09-02
**Régimen**: infraestructura, no investigación — no toca ledger/motor, no necesita pre-registro. Solo acumula historial para hipótesis intradía futura (no gap-reversion §13, ya muerta).
**Motivo GLM I3**: el tiempo es el único recurso no recuperable. Si en el futuro se quiere investigar hipótesis intradía nueva, hace falta historial 1-min acumulado. La cuenta paper de Alpaca (misma que `execution_costs.py`/`paper_trading.py`) da acceso gratis a barras 1-min vía `data.alpaca.markets` sin costo extra — empezar hoy maximiza ventana.

---

## 1. Revisión del cliente Alpaca existente

**Archivo**: `backend/app/core/execution_costs.py` `AlpacaPaperClient` (376 líneas pre-cambio).

Métodos disponibles antes de I3:
- `last_trade_price(symbol)` → `GET /v2/stocks/{symbol}/trades/latest` en `data.alpaca.markets` — precio de decisión.
- `get_account()` / `get_positions()` → `paper-api.alpaca.markets` — estado paper.
- `submit_market_order()` → `POST /v2/orders` + polling `GET /v2/orders/{id}` hasta `filled` — ejecución.
- **Faltante**: barras OHLCV 1-min. No había método para `GET /v2/stocks/{symbol}/bars`.

Credenciales vía `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` (env, nunca en código), mismo `market_data_base_url` para datos. El cliente ya traduce `BRK-B` → `BRK.B` solo en borde HTTP.

**Cambio I3**: se agregó `get_bars(symbol, timeframe="1Min", start, end, limit=10000, feed="iex", adjustment="raw")` en el mismo cliente, host de datos, con paginación `next_page_token` automática. `feed=iex` es gratis en paper; `sip` requiere suscripción y no se usa. El método es solo lectura, no toca trading, reutiliza `self._session` y `DEFAULT_TIMEOUT_SECONDS`.

## 2. Diseño del colector

**Archivo**: `backend/scripts/collect_intraday_1min.py` (150 líneas, `python -m scripts.collect_intraday_1min`).

**Universo inicial**: 7 `BASE_SYMBOLS` (`SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA`) — chico para empezar, cuota mínima, mismos que el motor usa como base. Extensible a 102 vía `--symbols` sin cambiar código.

**Almacenamiento**: `data/cache/intraday_1min/{SYMBOL}.parquet` (una partición por símbolo, columnas `timestamp UTC, open/high/low/close/volume/trade_count/vwap`). Parquet es el mismo formato que `data/cache/*.parquet` diario, pero separado en subdirectorio para no mezclar granularidades. Esquema:

```
timestamp: datetime64[ns, UTC] (clave, dedup)
open/high/low/close: float
volume: int
trade_count: int (n)
vwap: float (o null)
```

**Incremental** (mismo patrón que `data_updater.sh` para daily):
- Si `SYMBOL.parquet` existe → `last_ts = max(timestamp)` y `start = last_ts + 1 min`, `end = now UTC`.
- Si no existe → `start = now - 7d` (DEFAULT_DAYS_BACK=7), `end = now`. No se descarga desde 2015 — el historial intradía se acumula hacia adelante, no hacia atrás (Alpaca free limita a ~7 días de 1-min en iex sin plan pago, y el tiempo hacia atrás no es recuperable de todos modos).
- Fetch vía `client.get_bars` con paginación, normaliza cada bar `t/o/h/l/c/v/n/vw` → DataFrame, `concat` + `drop_duplicates(timestamp)` + sort, `to_parquet` atómico.

**Idempotencia**: re-correr el mismo minuto no duplica (dedup), re-correr fuera de horario da 0 barras nuevas y no sobrescribe.

**Manejo de errores**: sin credenciales → log `[collect] ERROR credenciales` y `exit 1` sin crash; `get_bars` con excepción de red → log `[SYMBOL] ERROR fetch` y continúa con siguiente símbolo; bar inválida → warn y skip. Un símbolo fallado no bloquea los otros 6.

**Logging**: stdout/stderr a `scripts/intraday_collector.log` vía launchd `StandardOutPath` (append). Cada símbolo loguea `+N nuevas, total M min->max` o `0 barras nuevas`.

**No hipótesis**: el colector no calcula indicadores, no genera señales, no escribe ledger, no toca `signal_engine.py` ni `backtest_engine.py`.

## 3. Cron launchd

**Plist**: `~/Library/LaunchAgents/com.fortresscore.intraday.plist` (instalado 2026-09-02, `launchctl bootstrap gui/501`).

```xml
Label: com.fortresscore.intraday
ProgramArguments: /Users/boris/Desktop/fortress_core/backend/.venv/bin/python -m scripts.collect_intraday_1min
WorkingDirectory: /Users/boris/Desktop/fortress_core/backend
StartInterval: 1800 (30 min)
RunAtLoad: false
StandardOutPath/StandardErrorPath: /Users/boris/Desktop/fortress_core/scripts/intraday_collector.log
PYTHONPATH: /Users/boris/Desktop/fortress_core/backend
```

**Criterio de schedule**: cada 30 min todo el día (no solo horario de mercado). Fuera de 9:30-16:00 ET el fetch devuelve 0 barras y el log dice `0 barras nuevas` — costo despreciable (7 símbolos × 1 request cada 30 min = 336 requests/día, por debajo del rate limit 200/min de Alpaca). Alternativa evaluada: `StartCalendarInterval` cada 30 min 9:40-16:10 ET — más complejo, mismo efecto, se descartó por simplicidad. Si en el futuro se quiere ahorrar aún más, se puede añadir guarda de horario en el script (`if not market_open: exit 0`), pero hoy no hace falta.

**Verificación**:

```bash
launchctl list | grep intraday          # - 0 com.fortresscore.intraday (cargado, no corriendo)
launchctl kickstart -k gui/501/com.fortresscore.intraday  # correr una vez a mano
tail -f ~/Desktop/fortress_core/scripts/intraday_collector.log
ls -lh ~/Desktop/fortress_core/backend/data/cache/intraday_1min/
```

**Desinstalación**: `launchctl bootout gui/501/com.fortresscore.intraday.plist` y borrar el plist.

## 4. Riesgos y limitaciones

- **Feed iex vs sip**: `iex` es gratis pero es solo un exchange (no consolidado). Para investigación intradía, iex es suficiente como proxy; si se necesita sip (consolidado), requiere suscripción y cambiar `feed="sip"` en una línea.
- **Retención**: Alpaca free retiene 1-min solo ~7 días en iex; si el colector se cae >7 días, habrá hueco irrecuperable. El log `PRECIOS: ERROR` de `data_updater.sh` no cubre intradía — el colector loguea `ERROR fetch` pero no alerta. Mitigación futura: añadir check de hueco >1 día en `scripts/data_updater.sh` o en health check.
- **Cuota**: 7 símbolos × 30 min = 336 requests/día, cada request puede paginar (limit 10000 → ~6.5h de 1-min por request). Dentro de límites, pero si se escala a 102 símbolos, serían 4896 requests/día → evaluar batch `GET /v2/stocks/bars?symbols=SPY,QQQ,...` multi-símbolo (pendiente).
- **Almacenamiento**: 7 símbolos × 390 barras/día × 252 días ≈ 688k filas/año por símbolo → ~5 MB parquet/año por símbolo, ~35 MB total. Despreciable.
- **Zona horaria**: timestamps en UTC (`2024-01-01T09:30:00Z` es 04:30 ET verano), se guardan UTC y se convierten a ET solo en análisis.
- **No backfill histórico**: el colector no intenta reconstruir años de 1-min (costoso y con huecos). Si se necesita backfill, usar `get_bars` con `start` histórico y `feed=sip` pago.

## 5. Tests y verificación

- **Cliente**: `test_execution_costs.py` existente sigue pasando (15 tests). Nuevo test `test_get_bars_paginacion_y_traduccion` (mock `_FakeSession` con `next_page_token`) cubre paginación y `BRK-B` → `BRK.B`.
- **Colector**: `test_intraday_collector.py` (fake client, `tmp_path` cache, incremental + dedup, 0 barras fuera de horario, manejo sin credenciales). `ruff` limpio.
- **Manual**: `PYTHONPATH=backend .venv/bin/python -m scripts.collect_intraday_1min --symbols SPY --days 1` (con credenciales) debe crear `data/cache/intraday_1min/SPY.parquet` con `timestamp` UTC.

## 6. Qué no se hizo (a propósito)

- No se diseñó hipótesis intradía (no gap-reversion, no ORB, no VWAP) — solo acumulación.
- No se tocó `signal_engine.py`, `backtest_engine.py`, ledger ni slots de trial.
- No se usa `sip` ni se paga suscripción.
- No se backfillea historial largo — el tiempo hacia atrás no es recuperable gratis.

**Próximo paso si se quiere escalar**: añadir `symbols` multi en un solo request y rotar universo 102 en batches de 7 para no exceder cuota, manteniendo incremental.

