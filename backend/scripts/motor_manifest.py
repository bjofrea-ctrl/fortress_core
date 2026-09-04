"""
Motor manifest — hash-guard del congelamiento durante el gate (A4).

PLAN_REMEDIO_BRECHAS_20260903.md §A4: mientras dure el gate de 60 días, la
definición del motor debe estar CONGELADA de manera verificable. Si cambia un
byte de cualquiera de los 7 módulos críticos, el contador de días limpios NO
debe seguir contando sin que alguien lo declare explícitamente.

Este módulo:
  1. Mantiene `scripts/motor_manifest.json` con sha256 de los 7 módulos
     críticos + commit que firma el congelamiento.
  2. Expone `verify_manifest()` que la fase `health` del pipeline invoca
     cada corrida: si algún hash driftó → rc=2 + alerta visible.
  3. Expone `--bump` para que un humano declare un cambio legítimo
     (recalcula hashes, actualiza commit+timestamp, pero NO toca
     `data/clean_days.json` — eso lo hace A2/Cline a mano, reinicio
     EXPLÍCITO nunca silencioso).

Reglas no negociables:
  - 7 módulos críticos, ni uno más ni uno menos (es el contrato del gate).
  - Los cambios al manifiesto son SIEMPRE por CLI humana, nunca auto.
  - El hash-guard sólo observa/registra; no aborta el pipeline.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from typing import Dict, List, Tuple

# Ruta absoluta del repo = padre del padre de ESTE archivo (backend/scripts/motor_manifest.py).
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)

# 7 módulos críticos del congelamiento del gate. El orden es estable
# (también lo verifica el test); cualquier adición/eliminación es un
# cambio de CONTRATO y debe declararse explícitamente en la nota del bump.
CANONICAL_MODULES: List[str] = [
    "backend/app/core/signal_engine.py",
    "backend/app/core/paper_trading.py",
    "backend/app/core/backtest_engine.py",
    "backend/app/api/routes/decision.py",
    "backend/app/core/adaptive_risk.py",
    "backend/app/core/conformal.py",
    "backend/app/core/regime_classifier.py",
]

# El manifiesto vive en scripts/ junto a los plists, como artefacto versionado
# del repo. NO se regenera en cada corrida: es CONGELADO al arranque del gate
# y solo cambia cuando un humano hace --bump.
MANIFEST_REL = "scripts/motor_manifest.json"
MANIFEST_PATH = os.path.join(REPO_ROOT, MANIFEST_REL)

CHUNK_SIZE = 64 * 1024


def _abs(path_rel: str) -> str:
    return os.path.join(REPO_ROOT, path_rel)


def _git_head() -> str:
    """Commit corto (12 chars) del HEAD del repo. Fallback a 'unknown' si
    no estamos en un worktree git (no debería pasar — el repo es git por
    contrato, pero mejor no romper el tooling si el manifest se genera
    en un sandbox)."""
    try:
        out = subprocess.run(
            ["git", "-C", REPO_ROOT, "rev-parse", "--short=12", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def _sha256(path_abs: str) -> str:
    h = hashlib.sha256()
    with open(path_abs, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_hashes(modules: List[str] = None) -> Dict[str, str]:
    """SHA256 hex de cada módulo crítico, en el orden canónico.

    Cada entrada es un dict {path_relativo_repo: sha256_hex}. Orden estable
    = orden de CANONICAL_MODULES (también lo verifica el test)."""
    mods = modules if modules is not None else CANONICAL_MODULES
    out: Dict[str, str] = {}
    for rel in mods:
        abs_p = _abs(rel)
        if not os.path.exists(abs_p):
            raise FileNotFoundError(f"módulo crítico no encontrado: {rel} (abs={abs_p})")
        out[rel] = _sha256(abs_p)
    return out


def load_manifest(path: str = None) -> Dict:
    """Lee el manifiesto. Si no existe, devuelve dict vacío (no es error:
    el llamador decide si eso es 'drift' o 'primera instalación'."""
    p = path or MANIFEST_PATH
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: Dict, path: str = None) -> None:
    """Persiste el manifiesto de forma atómica (write a .tmp + replace)."""
    p = path or MANIFEST_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, p)


def build_manifest(commit: str = None, note: str = "") -> Dict:
    """Construye el dict del manifiesto vigente a partir del estado actual
    de los archivos. No toca disco — eso lo hace save_manifest()."""
    return {
        "commit": commit or _git_head(),
        "note": note,
        "hashes": compute_hashes(),
    }


def verify_manifest(manifest: Dict = None) -> Tuple[bool, List[str]]:
    """Compara hashes actuales con el manifiesto.

    Devuelve (ok, drifted). ok=True si todos matchean (o si no hay
    manifiesto y la fase se ejecuta sin gate formal). drifted es la
    lista de paths_relativos cuyo sha256 cambió.

    Caso especial: manifiesto ausente o sin hashes → (True, []) — el
    hash-guard se vuelve obligatorio en cuanto alguien hace --init; en
    estado "sin gate" no rompe la pipeline.
    """
    man = manifest if manifest is not None else load_manifest()
    if not man or not man.get("hashes"):
        return True, []
    declared: Dict[str, str] = man["hashes"]
    current = compute_hashes()
    drifted: List[str] = []
    # Cualquier módulo del manifiesto que ya no exista = drift
    for rel, _hash in declared.items():
        if rel not in current:
            drifted.append(rel)
    # Cualquier hash distinto = drift
    for rel, h in current.items():
        if declared.get(rel) != h:
            drifted.append(rel)
    # Dedup preservando orden
    seen = set()
    out: List[str] = []
    for x in drifted:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return (len(out) == 0), out


# ----------------------------------------------------------------- CLI


def _log_drift(drifted: List[str], log_path: str = None) -> str:
    """Escribe línea de alerta al log del pipeline (best-effort). Devuelve
    la línea escrita para stdout."""
    import datetime as _dt
    line = (
        f"[HASH-GUARD] {_dt.datetime.now().isoformat(timespec='seconds')} "
        f"DRIFT DETECTADO: {len(drifted)} módulo(s) cambiaron desde el "
        f"manifiesto declarado. Paths: {drifted}. "
        f"Día NO limpio por definición del gate (A4). "
        f"Para declarar: python -m scripts.motor_manifest --bump \"<motivo>\""
    )
    if log_path:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # logging es best-effort, no debe romper la fase
    return line


def cmd_init(args) -> int:
    """Crea el manifiesto inicial en HEAD actual. Pensado para ejecutarse
    UNA vez al arrancar el gate; bloquea si ya existe (usa --bump para
    actualizar)."""
    if os.path.exists(MANIFEST_PATH) and not args.force:
        print(f"ERROR: el manifiesto ya existe en {MANIFEST_REL}.", file=sys.stderr)
        print("Para actualizar use --bump (declaración explícita).", file=sys.stderr)
        return 2
    man = build_manifest(note=args.note or "Arranque del gate (A4).")
    save_manifest(man)
    print(f"Manifiesto inicial creado en {MANIFEST_REL}")
    print(f"  commit = {man['commit']}")
    print(f"  módulos congelados = {len(man['hashes'])}")
    for rel, h in man["hashes"].items():
        print(f"    {rel}  {h[:16]}…")
    return 0


def cmd_bump(args) -> int:
    """Recalcula hashes y actualiza commit+timestamp. ACCIÓN HUMANA
    EXPLICITA: quien hace --bump está declarando 'rompí el congelamiento
    a propósito, razón: X'. El contador de días limpios lo maneja A2/Cline
    a mano, no este script."""
    if not args.note:
        print("ERROR: --bump requiere --note con la razón del cambio.", file=sys.stderr)
        print("Esto es la declaración del gate.", file=sys.stderr)
        return 2
    man = build_manifest(commit=_git_head(), note=args.note)
    save_manifest(man)
    print(f"Manifiesto actualizado en {MANIFEST_REL}")
    print(f"  commit = {man['commit']}")
    print(f"  note   = {man['note']}")
    print()
    print("ACCIÓN REQUERIDA (manual): reiniciar el contador de días limpios")
    print("en data/clean_days.json. La razón está documentada en el manifiesto")
    print("(commit+note). El reinicio NO lo hace este script — es decisión humana")
    print("porque romper el congelamiento durante el gate es un evento, no algo")
    print("de plomería.")
    return 0


def cmd_verify(args) -> int:
    """Sólo verifica: rc=0 si OK, rc=2 si drift. Pensado para CI/cron."""
    man = load_manifest()
    if not man:
        print("OK (sin manifiesto cargado — gate no formal todavía)")
        return 0
    ok, drifted = verify_manifest(man)
    if ok:
        print(f"OK: {len(man.get('hashes', {}))} módulo(s) coinciden con el manifiesto "
              f"(commit={man.get('commit')})")
        return 0
    print(f"DRIFT: {len(drifted)} módulo(s) cambiaron desde el manifiesto:")
    for d in drifted:
        print(f"  - {d}")
    print(f"  declarado commit = {man.get('commit')}")
    print(f"  declarado note   = {man.get('note')}")
    print(f"  HEAD actual      = {_git_head()}")
    if args.log:
        _log_drift(drifted, args.log)
    return 2


def cmd_show(args) -> int:
    """Muestra el manifiesto vigente (o 'no existe')."""
    man = load_manifest()
    if not man:
        print("(sin manifiesto)")
        return 1
    print(json.dumps(man, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="crea el manifiesto inicial (una vez)")
    p_init.add_argument("--note", default="", help="nota del congelamiento")
    p_init.add_argument("--force", action="store_true", help="sobrescribir si ya existe")
    p_bump = sub.add_parser("bump", help="actualizar hashes tras un cambio declarado")
    p_bump.add_argument("--note", required=True, help="razón del cambio (obligatoria)")
    p_ver = sub.add_parser("verify", help="verificar hashes vs manifiesto")
    p_ver.add_argument("--log", default=None, help="path del log de drift (opcional)")
    sub.add_parser("show", help="mostrar el manifiesto vigente")  # argparse mantiene la referencia vía subparsers
    args = p.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "bump":
        return cmd_bump(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "show":
        return cmd_show(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
