"""One-shot 09-09: sanea parquets con columnas duplicadas (close+Close...).

Bug: data_ingestion.py lowercaseaba sin deduplicar; 102 parquets en
data/cache/ tienen close+Close, high+High... de contaminación vieja de
esquema. Al lowercasear quedan 2 'close' literales -> df['close'] devuelve
DataFrame -> validate_returns rompe (truth value of Series ambiguous) ->
500 en /api/advisor/universe y /api/advisor/theses.

Este script: para cada parquet, lowercasa, y si hay duplicados se queda con
la columna que tenga más valores no-nulos (la real), dropea la redundante,
y reescribe el archivo. Idempotente: correr 2 veces es no-op la 2da.

Uso: cd backend && PYTHONPATH=. .venv/bin/python -m scripts.repair_duplicate_columns [--dry-run]
"""
import glob
import os
import sys

import pandas as pd

CACHE_DIR = "data/cache"


def repair_parquet(path: str, dry_run: bool = False) -> str:
    df = pd.read_parquet(path)
    orig = list(df.columns)
    low = [str(c).lower() for c in orig]
    if len(low) == len(set(low)):
        # Ya limpio (o sin duplicados al lowercasear): solo normalizar
        # a minúsculas si hace falta, sin tocar datos.
        if orig != low:
            if not dry_run:
                df.columns = low
                df.to_parquet(path)
            return "lowercased"
        return "ok"
    # Duplicados: quedarse con la de más non-null por nombre.
    df.columns = low
    keep = {}
    for i, c in enumerate(df.columns):
        if c not in keep or df.iloc[:, i].count() > df.iloc[:, keep[c]].count():
            keep[c] = i
    df = df.iloc[:, sorted(keep.values())]
    if not dry_run:
        df.to_parquet(path)
    return f"dedup {len(orig)}->{len(df.columns)}"


def main() -> int:
    dry = "--dry-run" in sys.argv
    files = sorted(glob.glob(os.path.join(CACHE_DIR, "*.parquet")))
    fixed, already, lower = 0, 0, 0
    for f in files:
        try:
            status = repair_parquet(f, dry_run=dry)
        except Exception as e:  # noqa: BLE001 - reportar y seguir
            print(f"ERROR {f}: {e}")
            continue
        if status.startswith("dedup"):
            fixed += 1
            print(f"{status}: {os.path.basename(f)}")
        elif status == "lowercased":
            lower += 1
        else:
            already += 1
    print(f"--- {len(files)} parquets: {fixed} deduplicados, {lower} lowercased, {already} ok"
          + (" (DRY-RUN)" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
