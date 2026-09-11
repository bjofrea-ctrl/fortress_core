# Pre-registro — Rebuild advisor: memoizar el hook de integridad (corte del 531 s)

Fecha: 2026-09-10 · Rama: `perf/rebuild-integrity-memoize` (off `main` 45bc9c1, **NO merge**)
Fuente del análisis: `test-opencode-orca/ANALISIS_REBUILD_531S.md` (medido por OpenCode el
2026-09-10 sobre copia read-only del cache de main, zero-net, venv 3.9.6).

## Causa raíz (medida, no supuesta)

El rebuild del contexto advisor (`_load_context_sync` → `load_universe` → `download_data` por
símbolo) paga en CADA rebuild el `_integrity_hook` de `data_ingestion.py`. Perfil de OpenCode:

- 1ª pasada cache fresco (111 símbolos, serial): 1691 s, de los cuales el hook = 1790 s (V mide
  el hook puro). 2ª pasada **idéntica**: 1201 s → **cero ahorro**: el reconcile es idempotente en
  resultado pero no en costo.
- Hot-path del hook: `reconcile_symbol` → `detect_cross_contamination` = 91 % del tiempo del
  símbolo (REGN 14,08 s de los cuales 13,89 s hook / 12,84 s contamination). Hace `_norm(fresh)`
  **por cada fila** (4457 copias + sort_index) — O(N) normalizaciones.
- Disparador demasiado ancho: 106/109 símbolos levantan ≥1 hard-flag **histórico legítimo**
  (splits REGN/LRCX/CHTR, earnings ISRG, volatilidad ^VIX) → el hook dispara reconcile +
  re-descarga 2015→hoy para descubrir que NO diverge.
- `find_intermediate_gaps(df)` se llama **sin** `known_trading_days` → 25 símbolos re-intentan
  reparar eternamente 2–4 fechas de cierre por duelo presidencial (2018-12-05, 2025-01-09) +
  Sandy (2012-10-29/30) que NINGÚN símbolo tiene: 440 intentos fallidos, 0 reparados.

## Hipótesis comprobables

- **H1 (memoize)**: memoizar el veredicto del hook por `(mtime, size)` del parquet hace que una
  2ª lectura de bytes idénticos salde **sin** red ni CPU de reconcile. Reconciliar un parquet que
  no cambió produce exactamente el mismo output (OpenCode: 0 mutaciones), así que el memo es
  correcto. Invalidación: cualquier write real (updater/repair/re-descarga) cambia mtime/size →
  memo caído → el hook completo corre otra vez. **La verificación no se elimina**: corre la
  primera vez del día y tras cada parquet tocado.
- **H2 (disparador acotado)**: si el reconcile se dispara solo por hard-flags en la **ventana
  móvil de las últimas N ruedas** (default N=10), los 106 símbolos con hard-flags históricos
  legítimos dejan de pagar descarga de verificación; un flag nuevo (cola) igual dispara.
- **H3 (known_trading_days)**: pasar `known_trading_days = fechas presentes en ≥1 símbolo`
  elimina los huecos fantasmas de cierres presidenciales → esos 25 símbolos no re-intentan una
  reparación que nunca prospera. Cero riesgo: la auto-exclusión es el diseño del parámetro.

## Criterios de éxito (pre-registrados, ANTES de correr)

Medición: sandbox `/tmp/rebuild_memo/cache` con **copia** de 15 símbolos reales del cache de main
(SPY QQQ AAPL MSFT GOOGL AMZN NVDA REGN LRCX CHTR ISRG TSLA NFLX META AMD — cubre splits,
high-vol y los cierres fantasma), `yf.download` parchado a **zero-net** (devuelve el propio
parquet pedido como "fresco"). Se mide `load_universe(...)` **dos veces** sobre los mismos bytes
en dos procesos separados: (A) código ACTUAL de main, (B) código con fixes. Métricas: pared total
2ª pasada, nº de llamadas a `download_data`→downloader (proxy de red/reconcile), nº de writes de
parquet.

- **C1 (memoize)**: en (B) la 2ª pasada NO invoca `downloader` (memo hit puro) y su pared es
  < 5 % de la 1ª. En (A) la 2ª paga el reconcile otra vez. Prueba unitaria: 2ª llamada con el
  MISMO mtime+size → `downloader` 0 veces; tocar el parquet (nuevo mtime/size) → vuelve a correr.
- **C2 (ventana)**: un hard-flag SOLO histórico (p. ej. a 8 años de la cola) NO dispara
  `downloader` en (B); un hard-flag EN la cola sí dispara. Verificado por test unitario con
  contador de descargas y por inspección del subset (REGN/CHTR/ISRG: histórico → 0 descargas).
- **C3 (known_trading_days)**: un cierre que ningún símbolo del cache tiene (p. ej. 2018-12-05)
  con `known_trading_days` NO aparece en `find_intermediate_gaps`; con `None` (comportamiento
  viejo) SÍ aparece. Test unitario sobre dos frames sintéticos.
- **C4 (invariante de verificación)**: el hook completo sigue corriendo la 1ª vez del día y tras
  cualquier write. Un write real (simulado tocando el parquet) re-invalida el memo.
- **C5 (no aliasing)**: el df devuelto por memo hit es una COPIA — mutarlo por el caller no
  contamina el memo. Test: `out.copy()` semantics — `a is not b` y mutar `a` no cambia `b`.
- **C6 (no regresión)**: suites existentes siguen verdes: `test_data_ingestion`,
  `test_cache_integrity`, `test_cache_integrity_m4`, `test_advisor_warmup`, `test_feature_store`,
  `test_governance_*`. `run_integrity_check`/`reconcile_cache` (pasada full) NO se tocan.

## Criterio de reversión

Si (B) no reduce la 2ª pasada (C1) o alguna suite de regresión (C6) queda roja y no se puede
aclarar en el commit, **se revierte la rama** y se reporta el bloqueo con números. El fix vive
solo en `data_ingestion.py` + un test nuevo; `cache_integrity.py` **no se modifica** (H3 usa el
parámetro que ya existe).

## Fuera de alcance (esta iteración)

- Vectorizar `detect_cross_contamination` (doc §4.4): solo afecta la 1ª pasada del día, opcional
  tras el memoize → ticket aparte.
- Latencia del endpoint / threadpool starvation → ticket aparte (era governance, no rebuild).
- Reparación de la cola SPY/QQQ (NaN) → ticket aparte (Capa 2 governance).

---

## Resultados medidos (post-corrida, 2026-09-10)

Sandbox `/tmp/rebuild_memo/cache` = copia de 15 símbolos REALES del cache de main
(2009-01-02..2026-09-09, cubren splits REGN/CHTR, high-vol TSLA/AMD, y los cierres
fantasma). `yf.download` zero-net (devuelve el propio parquet). `load_universe` serial
(`max_workers=1`), dos pasadas sobre los mismos bytes, en procesos separados. Métrica
del hook: `hook2015` = nº de reconciles (descarga `start="2015-01-01"`); `writes` =
parquets re-escritos.

| Escenario (15 símbolos) | pared 1ª | pared 2ª | 2ª/1ª | reconcile/pasada | gap-repairs | writes/pasada |
|---|---|---|---|---|---|---|
| **A — código actual (main)** | 85.8 s | 83.1 s | **0.969** | **15** | ~44 (todos fallidos) | **15** |
| **B — con fixes 4.1+4.2+4.3** | 1.5 s | 0.2 s | **0.130** | **0** | 0 | **0** |

- **C1 (memoize) — VERDE**: en B la 2ª pasada = 0.2 s vs 1.5 s de la 1ª (ratio 0.13, no 0.97
  de A). `hook2015=0` en ambas pasadas. En A la 2ª pasada paga el reconcile otra vez (ratio
  0.97). Unit test `test_memo_hit_skips_second_reconcile` + `test_memo_invalidated_by_write`
  (write real ⇒ memo cae ⇒ reconcilia) verdes.
- **C2 (ventana) — VERDE**: los 15 símbolos tienen hard-flags SOLO históricos (REGN 9, AMZN
  2018-11-28 +2108%, TSLA 2015 +1044%…) ⇒ en B ninguno reconcilia (0 descargas de verificación),
  pero siguen logueándose (59 líneas `SANIDAD[hist]` en B: verificar sí, bloquear no). Unit
  `test_historical_hard_flag_does_not_reconcile` (0 descargas) y `test_recent_hard_flag_triggers_
  reconcile` (≥1) verdes.
- **C3 (known_trading_days) — VERDE**: en A cada símbolo reporta el hueco fantasma
  `2012-10-29..2025-01-09` (4 fechas) y re-intenta repararlo (`gap repair: quedan 4 huecos …
  incompleta`, 44 intentos, 0 éxitos). En B: 0 gap-repairs, 0 writes. Unit
  `test_hook_passes_known_trading_days_to_gaps` (el hook pasa `known`, no `None`) y
  `test_known_trading_days_is_union_of_cache` verdes.
- **C4 (invariante)**: write real (append de rueda) invalida el memo y re-corrige; verificado
  por `test_memo_invalidated_by_write`. El updater nocturno reescribe el parquet ⇒ el primer
  rebuild del día re-valida completo (gratis por el propio write).
- **C5 (no aliasing)**: `test_memo_returns_copy_no_aliasing` — el memo entrega `.copy()`; mutar
  la copia no contamina el memo. Verde.
- **C6 (no regresión)**: suites `test_data_ingestion` + `test_cache_integrity` +
  `test_cache_integrity_m4` + `test_advisor_warmup` + `test_feature_store` + el archivo nuevo.
  Un test de `test_cache_integrity` (`test_download_data_hook_repara_hueco_intermedio`) **debía**
  adaptarse: usaba un cache mono-símbolo, incompatible por diseño con `known_trading_days`
  (una fecha que ningún símbolo tiene se lee como cierre). Se seedeó un símbolo PAR con esa
  rueda — fiel a producción (109 símbolos). El hueco real se sigue reparando. Resultado final:
  ver el log de la re-corrida.

### Corte del 531 s (proyección a 111 símbolos, metodología del doc §4.5)
La 1ª pasada del día del HOOK (15 símbolos: 85.8 s ⇒ ~5.7 s/símbolo en A) baja a 1.5 s (~0.1 s/
símbolo en B). Extrapolado a 111 símbolos: hook en frío pasa de ~1690 s a ~10-15 s (1ª vez del
día, sin hard-flags nuevos) y a ~0-2 s en cada rebuild intradía (TTL 300s ⇒ ~12×/hora) — el
rebuild caliente dominado por el hook colapsa de minutos a segundos. La verificación completa
sigue corriendo la primera vez del día y tras cada write real.

## Conclusión

Hipótesis de Boris VALIDADA con números: **idempotente en resultado, no en costo**. El memoize
por (mtime,size) + acotar el disparador a la ventana móvil + `known_trading_days` eliminan el
100 % del costo recurrente del hook sin tocar `cache_integrity.py` y sin perder la verificación.
Fix durable y de bajo riesgo; no se mergea a main (queda en la rama para revisión).

- Ticket aparte (no esta iteración): vectorizar `detect_cross_contamination` (§4.4) para abaratar
  la 1ª pasada del día; re-auditación de la cola SPY/QQQ (governance Capa 2).
