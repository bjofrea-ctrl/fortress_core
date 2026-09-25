# PRE-REGISTRO — Limpieza cache + gate 0/0/0 (sellado 2026-09-24, ventana autorizada por Boris)

## Objetivo
Cache OHLCV 102 símbolos reproducible, libre de contaminación/mosaico/huecos, con hash congelado por trial.

## Estado actual verificado
- `data/cache/` y `backend/data/cache/`: 0 parquets (solo logs). Testigo vacío preservado.
- Único snapshot histórico Sep-2 contaminado (38 barras cruzadas, 7 mosaicos, 64 huecos) — NO restaurable.
- `PAUSE_YAHOO_MASS_DOWNLOAD` ACTIVO. Sin venv ni docker en este Linux (py3.14 system, pins py3.9/3.11).

## Criterio de aceptación (gate, fijado ANTES de correr)
`reconcile_cache("backend/data/cache", download_data)` → **0 contamination, 0 mosaic, 0 gaps** en 102 símbolos.
Umbrales heredados: >0.1% precio / >1% vol + matcheo otro símbolo = contaminación.
Hueco = fecha de mercado (calendario trading, no fin de semana) ausente in-range.
Éxito = gate 0/0/0 + snapshot hash sellado + pausa REACTIVADA. Fracaso = cualquier otro resultado → se revierte (cache del intento archivado como evidencia, pausa reactivada, sin promover nada).

## Pasos (en orden, con OK ya dado para la ventana completa a+b+c+d)
0. (código, sin red, pausa ON) Implementar runner ticker-por-ticker sobre `download_data` + `reconcile_symbol`: sleep 3-5s + jitter, backoff ante 429, aborta si pausa existe fuera de ventana.
1. (env, sin red masiva) Bootstrap venv aislado en `/tmp` (no en el árbol) con `requirements.txt` pineado; reportar compatibilidad py3.14 vs pins.
2. (piloto, pausa OFF temporal) 1-2 tickers → parquet + gate por símbolo. Si piloto falla o throttlea, se aborta y se reactiva pausa.
3. (ventana, pausa OFF) 102 símbolos 2015-01-01→hoy, ticker por ticker con throttle.
4. Gate inmediato 0/0/0. 5. Snapshot `cache_snapshot_for_trial` + manifest SHA256. 6. Reactivar pausa.
7. Ledger: `attach_cache_snapshot` → `cache_manifest_sha256` por trial.

## Riesgos declarados
- Sin cache limpio histórico, el primer trial post-limpieza establece la baseline.
- yfinance reajusta retroactivamente: reproducibilidad solo dentro del snapshot congelado.
- Throttle puede reaparecer: el runner para ante 429 persistentes y reactiva pausa.

## Ventana autorizada
Boris 2026-09-24: (a) pausa off temporal + (b) descarga 102 + (c) gate + (d) snapshot, atómicos. Sin commits/push sin orden separada.
