# Pre-registro — Fix 500 `/api/governance/analyze/SPY` (NaN/Inf en JSON)

Fecha: 2026-09-10 · Rama: `fix/governance-500-nonfinite` (off main, NO merge)
Alcance acordado: **Capa 1** (sanear no-finites + `logging.exception`) + **Capa 2**
(reparar `SPY.parquet` con el mecanismo EXISTENTE de `cache_integrity`). Capa 3
(threadpool/macro cache, 147 s) → ticket aparte (solapa con paralelización de Kilo).

## Evidencia de la causa raíz (traceback real, production log)
`api_server.log` líneas ~27311–27452: `fastapi/routing.py:326 → starlette/responses.py:183
render → json.dumps(allow_nan=False) → ValueError: Out of range float values are not JSON
compliant` (×6). Ocurre en el RENDER de la respuesta, **fuera** del `try/except` del handler
→ `except Exception → HTTPException(500, str(e))` nunca lo ve → 500 ASGI crudo, sin detail.
Defecto de datos en `data/cache/SPY.parquet` (verificado): barra `2026-09-08` close=179.03
(vs 770.19) → hard-flag −76.8%; fila `2026-09-09` OHLCV toda NaN (`n NaN close=1`). Ambos en
el extremo derecho (append-only). Un float no-finito en el payload (composite_score/prob_up_*/
governance_result) dispara el ValueError.

## Hipótesis comprobable
H1: un float no-finito (NaN/±Inf) en el dict retornado por `analyze_with_governance` hace
fallar `JSONResponse.render` (`allow_nan=False`) → 500, sin que el `except` del handler lo vea.
H2: reparando la cola de SPY con `reconcile_symbol` (hard-flag divergente → re-descarga
completa) desaparece el NaN de origen, PERO el guard M4 (`_fresh_download_invalid_reason`) puede
rechazar el overwrite si el fresco propio trae hard-flags/huecos → hay que MEDIR, no asumir.

## Criterios de éxito (pre-registrados, ANTES de correr)

### Capa 1 — endpoint robusto y diagnosticable
- Test rojo ANTES del fix: payload con `float("nan")` (y `inf`) → `JSONResponse(body).render()`
  levanta `ValueError: Out of range float values are not JSON compliant`.
- Test verde DESPUÉS: `_json_safe()` recursivo convierte NaN/±Inf → `None`; el render NO
  levanta; los valores FINITOS pasan intactos (float/int/str/bool); dict/list/tuple anidados
  saneados en profundidad; un `nan` dentro de `governance_result` (subdict) también → None.
- El `except Exception` del handler loguea traceback con `logging.exception` (no solo `str(e)`),
  de modo que un futuro 500 deje rastro en `api_server.log`.
- Regresión: los tests existentes de governance (`test_governance_contract`,
  `test_governance_llm_flag`, `test_governance_auth`) siguen verdes.
- Umbrales: `_json_safe` NO debe mutar payloads ya limpios (identity en finito); cero falsos
  positivos (0.0 y negativos finitos NO se tocan).

### Capa 2 — reparar SPY con el mecanismo existente (no hand-roll)
- Invocar `reconcile_symbol` vía su CLI `scripts.cache_integrity_run --symbols SPY` sobre el
  cache desplegado (data/ ignorada por git → no es merge a main), con backup previo.
- Criterio verde: tras reconcile, sobre `SPY.parquet`: (a) `2026-09-09` deja de ser NaN,
  (b) `2026-09-08` close dentro de `PRICE_TOL` vs fresco (sin |retorno|>HARD 20%),
  (c) `validate_returns` sin hard-flags en la cola, (d) el mecanismo reporta `final_gaps`/
  `final_flags` acorde.
- Si el guard M4 rechaza el overwrite (fresco inválido): criterio de "bloque honesto" — NO se
  hand-rolea; se registra la razón exacta y qué haría falta. Capa 1 igual corta el 500.

### Confirmación en vivo (al cerrar)
- `/api/governance/analyze/SPY` → HTTP 200 con JSON válido (o 500 CON traceback visible si algo
  sigue mal). Si el server desplegado no se reinicia (no merge), la confirmación se hace con el
  código de la rama vía TestClient/handler in-process sobre datos reales de SPY.

## Fuera de alcance (esta iteración)
- Latencia 147 s / starvation del threadpool (capa 3) → ticket aparte.
- `/api/advisor/*` y `/api/opportunities/today` (misma clase de 500) → se documentan, no se tocan.
- Cambiar la lógica del motor/indicadores que producen el NaN → no (solo se sanea la salida).

---

## Resultados medidos (post-corrida, 2026-09-10)

### Capa 1 — VERDE (el fix durable)
- Suite governance sobre el worktree: **29 passed** (6 nuevos de
  `test_governance_json_nonfinite.py` + contract/llm_flag/auth sin regresión).
- Test rojo documentado verde: `JSONResponse({..nan..})` levanta
  `ValueError: Out of range float values are not JSON compliant` en `__init__`
  (starlette serializa ahí, `allow_nan=False`) — misma línea que crashaba en prod.
- `_json_safe()` recursivo: NaN/±Inf (incl. `np.float64`) → None; finitos/bool/int/str
  intactos; `JSONResponse(_json_safe(payload))` renderiza. `logger.exception` added al
  `except` del handler → traceback visible en `api_server.log`.

### Capa 2 — BLOQUE HONESTO (revert; el remedio era peor que la enfermedad)
Medición sobre el cache desplegado (`~/Desktop/fortress_core/backend/data/cache/`),
backup `SPY.parquet.bak_20260910_gov500` vs `SPY.parquet` reconciliado:
- El reconcile eliminó el NaN de cola (09-09→653.69) PERO re-baseó TODA la historia:
  2877/4446 filas difieren >1% (máx 75%), cola ~770→~616, y **introdujo 7 hard-flags
  históricos** (2015-01-02, 2018-11-28, 2018-12-13, 2022-02-03, 2022-10-27, 2023-02-02,
  2024-02-02) vs **1** en el backup. Ejs. reales: 2015-01-02 CUR 169.78→77.77 (BAK liso),
  2018-11-28 CUR 133.82→244.21 (+82%, BAK +2.3%) — contaminación cruzada clase §3, no
  ajuste legítimo.
- Ninguno matchea el sha A0 (`af0ee06a…`): yfinance re-ajusta retroactivamente (mosaico),
  así que el sha no dirime canonicidad — pero el nº de defectos sí: **2 barras malas en la
  cola (backup) << 7 barras corruptas en el histórico + base roto (reconciliado)**. Para un
  instrumento time-series esto envenena cada backtest/señal en esas fechas.
- El overwrite NO pudo venir de `repair_full_redownload`: su guard M4
  (`_fresh_download_invalid_reason`) conserva el cache ante un fresco con hard-flags. Vino
  de un path que lo saltó (refresh append-only de `download_data`). Criterio de "reparar con
  el mecanismo EXISTENTE" NO se cumple sin hand-rollear → **se revierte**.
- **Acción:** `SPY.parquet` restaurado desde el backup; el reconciliado corrupto preservado
  como `SPY.parquet.bak_20260910_gov500.CONTAMINATED` (forense). Reparo seguro de la cola
  (append-only preservando base, o re-bajar 09-08/09-09 con validación vs fresco sin tocar
  el histórico) → **ticket aparte**, no se hand-rolea acá.

### Confirmación en vivo
- `curl` al server DESPLEGADO (rama `main`, SIN Capa 1): **HTTP 200 en 23 s** — pero solo
  porque el dato reconciliado (band-aid) había borrado el NaN. Tras restaurar el dato
  honesto, cualquier `/analyze/{SYM}` con NaN de cola (SPY y también **QQQ**, verificado:
  last close=nan 2026-09-08) vuelve a ser 500-prone **en main** hasta que se deploye Capa 1.
- Por eso Capa 1 es el fix durable: coacciona no-finitos a None para CUALQUIER símbolo con
  cola sucia. **Acción requerida: mergear + redeployar para que el server en vivo quede
  robusto** (la confirmación 200 con dato honesto se reproduce in-process vía el test).

- Cambiar la lógica del motor/indicadores que producen el NaN → no (solo se sanea la salida).
