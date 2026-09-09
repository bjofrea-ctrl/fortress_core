"""
Feature store versionado mínimo (B3 / I6) — mata la divergencia silenciosa.

`build_factor_panel` escribe datasets versionados con hash; los consumidores
leen POR VERSIÓN a través del manifest índice. Esto da a cada panel una
identidad inmutable (hash sha12) y metadatos auditables (columnas, universo,
rango de fechas, commit que lo generó), cumpliendo B3 sin big-bang.

Decisión de ruta (documentada en B3_PREREGISTRO.md): se usa `data/cache/`
en lugar de `data/panels/` del plan, para que los 8 scripts consumidores
existentes (que hacen glob `factor_panel_*.parquet`) sigan funcionando sin
migración masiva. El rename a `data/panels/` es follow-up cuando todos
adopten `load_panel()`.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

SHORT = 12  # hex chars del hash corto (sha12)


def _repo_root() -> Path:
    # backend/app/core/feature_store.py -> parents[2] == backend/
    return Path(__file__).resolve().parents[2]


def _panels_dir(repo_root: Optional[str] = None) -> Path:
    return (Path(repo_root) if repo_root else _repo_root()) / "data" / "cache"


def _manifest_path(repo_root: Optional[str] = None) -> Path:
    return _panels_dir(repo_root) / "manifest.json"


def _git_commit(repo_root: Optional[str] = None) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=(Path(repo_root) if repo_root else _repo_root()),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _sha12_of_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:SHORT]


def _read_manifest(repo_root: Optional[str] = None) -> List[Dict[str, Any]]:
    m = _manifest_path(repo_root)
    if not m.exists():
        return []
    try:
        return json.loads(m.read_text())
    except Exception:
        return []


def _write_manifest(repo_root: Optional[str], arr: List[Dict[str, Any]]) -> None:
    m = _manifest_path(repo_root)
    tmp = m.with_suffix(".tmp")
    tmp.write_text(json.dumps(arr, indent=2, default=str))
    tmp.replace(m)  # escritura atómica (patrón motor_manifest)


def write_panel(
    df: pd.DataFrame,
    meta: Optional[Dict[str, Any]] = None,
    repo_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Escribe `factor_panel_<sha12>.parquet` + registra en `manifest.json`.

    Devuelve la entrada del manifest (version, parquet, columnas, rango, commit).
    El hash es determinista: el mismo df (mismos bytes parquet) -> misma version.
    """
    panels = _panels_dir(repo_root)
    panels.mkdir(parents=True, exist_ok=True)

    tmp = panels / "_tmp_panel.parquet"
    df.to_parquet(tmp, index=False)
    version = _sha12_of_file(tmp)

    panel_path = panels / f"factor_panel_{version}.parquet"
    tmp.replace(panel_path)  # mover al nombre final (atómico)

    entry: Dict[str, Any] = {
        "version": version,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parquet": f"data/cache/factor_panel_{version}.parquet",
        "n_rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "commit": _git_commit(repo_root),
        "meta": meta or {},
    }
    if "date" in df.columns:
        entry["date_min"] = str(df["date"].min())
        entry["date_max"] = str(df["date"].max())
    if "symbol" in df.columns:
        try:
            entry["universe"] = sorted(df["symbol"].astype(str).unique().tolist())
        except Exception:
            pass

    arr = _read_manifest(repo_root)
    arr = [e for e in arr if e.get("version") != version]  # dedupe
    arr.append(entry)
    _write_manifest(repo_root, arr)
    return entry


def panel_index(repo_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Índice de versiones (el manifest). Vacío si no hay ninguna."""
    return _read_manifest(repo_root)


def load_panel(
    version: Optional[str] = None,
    repo_root: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Lee un panel POR VERSIÓN desde el manifest (índice).

    version=None -> el más reciente por created_utc.
    Fallback legacy: si no hay manifest, glob `factor_panel_*.parquet` y lee
    el más nuevo (no rompe consumidores viejos).
    """
    root = Path(repo_root) if repo_root else _repo_root()
    arr = _read_manifest(repo_root)
    if arr:
        if version is None:
            entry = max(arr, key=lambda e: e.get("created_utc", ""))
        else:
            matches = [e for e in arr if e["version"] == version]
            if not matches:
                raise KeyError(f"version {version} no encontrada en el manifest")
            entry = matches[0]
        df = pd.read_parquet(root / entry["parquet"])
        return df, entry

    # Fallback legacy
    files = sorted((_panels_dir(repo_root)).glob("factor_panel_*.parquet"))
    if not files:
        raise FileNotFoundError("No hay panels versionados ni legacy en el feature store")
    path = files[-1]
    df = pd.read_parquet(path)
    entry = {
        "version": "legacy",
        "parquet": str(path),
        "n_rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "commit": "unknown",
        "meta": {},
    }
    return df, entry


def latest_panel(repo_root: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Atajo: carga la versión más reciente."""
    return load_panel(version=None, repo_root=repo_root)
