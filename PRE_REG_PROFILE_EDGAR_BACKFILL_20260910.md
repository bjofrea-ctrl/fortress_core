# Pre-registro — Backfill de perfil de mercado en el path EDGAR (0 Deep Dive en screening)

Fecha: 2026-09-10 · Rama: `fix/fundamentals-profile-backfill` (off `main` 45bc9c1, **NO merge**)
Fuente: bug confirmado con corrida en vivo VPS Oracle (99/100 símbolos vía EDGAR, 1 gap legítimo:
XOM sin 10-K) + **reproducido en el snapshot local** (`data/cache_fundamentals_ingestion/`:
47/47 paquetes EDGAR con `profile` STUB — solo companyName/symbol — y 0/47 con price/marketCap).

## Causa raíz (verificada contra el artefacto real, no el resumen)

En `backend/app/core/fundamentals_ingestion.py::FundamentalsIngestion.ingest_symbol`:

- Cualquier rama donde EDGAR cubre los statements devuelve sin pasar por `_ingest_live`:
  - cache **stale** → `_ingest_edgar` OK → `return edgar` (líneas 251-253)
  - cache **miss/force** → `_ingest_edgar` OK → `return edgar` (líneas 266-268)
- `_ingest_live` es el **único** sitio que llama `self.fmp.profile(sym)` y
  `self.fmp.price_target_consensus(sym)` (líneas 283-284).
- `build_fmp_shaped_payload` (`edgar_fundamentals.py:459-470`) incluye `profile` pero es un
  **stub**: solo `companyName`/`symbol`, sin `price`/`marketCap`/`beta`.
- Consecuencia en `fundamentals_screen.py::compute_indicators` (líneas 178-264): `market_cap`,
  `price`, `beta`, `buyback_yield`, `fcf_yield`, `upside`, `ev_to_ebit`, `altman_z_score`,
  `pe_ratio` quedan todos `None` → el scoring de valuación no ve precio → 0 Deep Dive / 0
  Watchlist (dashboard 09-09: 98 analizadas, 83 descartadas).

Agravante de cuota: `scripts/run_fundamentals_screen.py` cuenta 0 calls para `edgar_primary`
(líneas 309-313) y el guard de budget reserva 5 solo para símbolos SIN companyfacts (285-290).

## Hipótesis de fix (3 piezas)

- **H1 (backfill no bloqueante)**: en las ramas EDGAR, después de construir/leer los statements,
  asegurar la **foto de mercado** (profile + price_target_consensus) con una llamada FMP liviana
  de 2 endpoints. Nunca bloquea ni aborta: si FMP falla, los campos quedan `null` como hoy y el
  símbolo **no se descarta** por eso (el screen ya trata `None` sin romper).
- **H2 (cache/TTL respetados)**: cache fresco CON foto de mercado → 0 llamadas (branch actual sin
  cambios). Cache fresco SIN foto (legacy EDGAR) → backfill UNA vez (2 calls) y persiste. Refresh
  stale/miss EDGAR → backfill (2 calls) con degradación: si FMP falla y el cache previo tenía
  foto, se conserva esa foto vieja (mejor que null). `_ingest_live` intacto (5 calls, ya incluye
  profile).
- **H3 (contabilidad de cuota real)**: `FundamentalsIngestion.last_fmp_calls` reporta cuántas
  calls FMP consumió el último `ingest_symbol` (5 live / 2 backfill / 0 puro EDGAR o cache). El
  script pasa a contar **lo real** (fallback old-style para ingesters de test) y el guard de
  budget reserva 2 para símbolos con companyfacts / 5 sin él.

## Criterios de éxito (pre-registrados, ANTES de correr)

Unidad de medida real: `data/cache_fundamentals_ingestion/` (47 paquetes reales, todos EDGAR
stub) + key FMP real → `screen_2026-09-10.json` vía `run_fundamentals_screen.py`.

- **A1 — cobertura de foto**: `price` y `market_cap` no-null para ≥ **45/47** símbolos en el
  screen generado con el fix (antes: **0/47**). Si FMP está caído/rate-limited, el criterio se
  reclasifica a "queda ≥ 0 pero el símbolo NO se descarta" (A3).
- **A2 — cuota documentada y dentro del budget**: `state["calls_used"]` final ≤ 240 (budget
  diario). Esperado: ≤ 2×47 (backfill) + 5 (XOM fallback) ≈ 99.
- **A3 — no-descarte sin foto**: si FMP falla para un símbolo en la corrida real, ese símbolo
  sigue en `results` (no desaparece); solo quedan `price/market_cap/…` nulos. Test offline
  idéntico: FakeFmp sin profile → `ingest_symbol` devuelve payload EDGAR con `profile` stub.
- **A4 — TTL/cache**: segunda corrida sobre el mismo cache (backfill ya hecho) = **0 calls**
  nuevas (`last_fmp_calls == 0` por símbolo). Offline: test de cache-hit con foto de mercado.
- **A5 — regresión offline**: `test_fundamentals_ingestion.py`, `test_edgar_fundamentals.py`,
  `test_fundamentals_screen.py`, `test_fundamentals_screen_job.py`,
  `test_fundamentals_screen_e2e.py`, `test_fundamentals_screen_api.py`,
  `test_fundamentals_client.py`, `test_fundamentals_scores.py` en verde; invariante "nunca red
  real en tests" preservado (fakes inyectados).
- **A6 — screen_payload con EDGAR+foto**: con el payload backfilleado, `compute_indicators` ve
  `price`/`market_cap` y los indicadores de valuación dejan de ser `None` (test).
- **A7 — contabilidad en job**: símbolo EDGAR+backfill suma 2 calls a `calls_used` (test del job
  con FakeIngester con `last_fmp_calls=2`); símbolo EDGAR puro suma 0.

## Criterio de reversión

- Si A1 se cumpliera de forma adversa (price poblado pero `roic`/`roe`/ratios de calidad pasan a
  peor) → revert del commit; el backfill es **aditivo y no destructivo** (conserva statements
  EDGAR; solo adjunta profile/pt al payload y re-escribe el cache).
- Revertir en prod = `git revert` del commit; interruptor de emergencia: borrar
  `data/cache_fundamentals_ingestion/` (el job re-siembra vía EDGAR; con el código nuevo
  re-fetchea 2 calls por símbolo sin foto — documentado).

## Plan de medición

1. ANTES (referencia): `screen_2026-09-09.json` local → contar resultados con `price`/`market_cap`
   no-null (esperado 0/47).
2. Implementar en rama nueva `fix/fundamentals-profile-backfill` (off main, sin tocar perf).
3. Offline: suites A5 + tests nuevos (A3/A4/A6/A7) con fakes.
4. REAL: `python -m scripts.run_fundamentals_screen --universe <47 syms> --date 2026-09-10`
   (cache EDGAR fresco → solo backfill 2×47 + XOM 5; NUNCA re-baja statements).
5. DESPUÉS: contar `price`/`market_cap` no-null en `screen_2026-09-10.json` + `calls_used` en
   state.json + delta `last_fmp_calls` por símbolo (log).
6. Resultados: tabla antes/después aquí abajo.

## Resultados (se completa al cerrar)

| Métrica | ANTES (09-09) | DESPUÉS (09-10) |
|---|---|---|
| `price` no-null en screen | **0/47** | **47/47** |
| `market_cap` no-null en screen | **0/47** | **47/47** |
| `stale` en artifact | True | **False** |
| calls FMP reales quemadas en esta validación | 0 | **94** (smoke 2 + backfill 46×2), dentro de 240 |
| `calls_used` del artifact final (cache caliente) | 0 | 0 (corrida de verificación = cache hits puros) |
| completed / failed | 47 / 1 (XOM, gap legítimo sin 10-K) | 47 / 0 |
| Baldes | 0 con datos de valuación | Neutral 7 · Descartada 37 · Omitida 3 |

Regresión offline: **123 passed, 1 skipped, 1 deselected** (8 archivos fundamentals, una corrida
combinada; el deselected es el xfail pre-existente `test_job_aborts_when_fmp_client_unavailable`,
que tarda ~60 s por diseño roto y queda como tema aparte). Criterios: A1 ✓ (≥45/47), A2 ✓ (≤240),
A3 ✓ (test: FMP caído → símbolo sigue, campos null, nunca `profile=[]`), A4 ✓ (2ª pasada con foto =
0 calls), A6 ✓ (screen ve price/market_cap/beta), A7 ✓ (EDGAR+backfill suma 2 calls). Sin reversión.
