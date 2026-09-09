# B3 — Pre-registro de approach (Regla 1: ningún trial sin criterio pre-registrado)

Ticket: **B3 Feature store versionado (I6)** — `PLAN_REMEDIO_BRECHAS_20260903.md` §B3 /
`PLAN_IMPLEMENTACION_REMEDIO_20260903.md` §B3. Mata la divergencia silenciosa de
utilidades copiadas: `build_factor_panel` emite dataset con hash de versión + manifest
(índice); los scripts consumen POR VERSIÓN.

## Alcance de ESTA sesión (rebanada vertical, no B3 completo)
B3 completo son 2-3 sesiones / 97 utilidades. Esta sesión entrega:
1. Infraestructura versionada (`feature_store.py`).
2. `build_factor_panel` escribe versionado + manifest (solo cambia el sumidero, no el df).
3. 1 consumidor migrado a `load_panel()` con golden bit-a-bit (`diagnose_ic_by_regime.py`).
4. 1 golden de deduplicación (`bootstrap`).
El resto (otras utilidades, otros 7 consumidores) queda para sesiones siguientes
(el plan dice "repartidas", "un commit por script"). **NO toca la ruta de decisión de
señal** → gate-legal (gate 90 días hasta 2026-12-01).

## Diseño
Nuevo `backend/app/core/feature_store.py`:
- `write_panel(df, meta)` → `data/cache/factor_panel_<sha12>.parquet` (sha256 de bytes, 12 hex)
  + `data/cache/manifest.json` (índice: version, created_utc, parquet, n_rows, columns,
  date_min/max, universe, commit, meta). Reusa patrón `motor_manifest._sha256`; escritura
  atómica (temp + replace).
- `load_panel(version=None)` / `latest_panel()` / `panel_index()` → lee por versión
  (el manifest es el índice). **Fallback legacy**: si no hay manifest, glob
  `data/cache/factor_panel_*.parquet` y lee el más nuevo (no rompe consumidores viejos).
- **Decisión de ruta**: se usa `data/cache/` (NO `data/panels/` del plan) a propósito —
  así los 8 scripts consumidores existentes (glob `factor_panel_*.parquet`) siguen
  funcionando sin big-bang. El rename a `data/panels/` es follow-up trivial cuando todos
  adopten `load_panel()`. Se documenta como desviación deliberada.
- `build_factor_panel.py`: reemplaza su escritura por timestamp con `write_panel(panel, meta=...)`.
  El dataframe es idéntico; solo cambia el archivo de salida.
- Consumidor migrado: `diagnose_ic_by_regime.py` pasa de glob+read_parquet a `load_panel()`.

## Deduplicación (golden condicional) — `bootstrap`
Canonical `circular_block_bootstrap_ci` (`app/core/probabilistic_engine.py:721`) vs
reimplementación `_boot_ci` (`scripts/measure_realized_edge.py:86`).
- Golden: mismos inputs con RNG seed fijo → comparar CI resultante.
  - Si idénticos → migrar `measure_realized_edge.py` a importar el canonical (sin cambio de resultados).
  - Si divergen → **NO migrar**; documentar la divergencia en el cierre (el plan lo permite:
    "si difiere, se documenta la divergencia ANTES de adoptar el core").

## Criterio de éxito pre-registrado (Regla 1)
- **Umbral de aceptación**: todos los tests en `tests/test_feature_store.py` PASAN con el
  venv de producción (`/Users/boris/Desktop/fortress_core/backend/.venv`, Python 3.9.6,
  pandas 2.2.0, pyarrow 15.0.0, pytest 8.3.4).
- **Corrección**: el df producido por `build_factor_panel` es BIT-IDÉNTICO (columnas, filas,
  valores) antes y después del refactor (golden T5). `load_panel` devuelve contenido
  idéntico a `write_panel` (T1).
- **No-go / rollback automático**: si T5 falla (el refactor alteró el df), revertir el cambio
  de `build_factor_panel` y reportar. Si el golden de bootstrap diverge y no se puede
  reconciliar, se documenta y NO se migra.
- **Entrega**: commit en rama `bjofrea-ctrl/b3-feature-store` (sin merge a main).

## No-goals (explícitos)
- No migrar DSR/deflated_sharpe completo ni `load_symbol` ×4 en esta sesión.
- No migrar los otros 7 consumidores en esta sesión.
- No cambiar señal medida ni ruta de decisión.
