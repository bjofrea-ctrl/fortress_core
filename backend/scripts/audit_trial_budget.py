"""M6 — Auditoria del presupuesto de trials por familia (ORDENES_MODULOS.md M6, paso 4).

Imprime el estado del presupuesto por familia y AVISA si un trial nuevo excederia el
umbral declarado. No registra nada: solo lee `data/trial_registry.json` y reporta.

Modo de uso:
    cd backend && .venv/bin/python scripts/audit_trial_budget.py [--proyectar-trials N]
"""
import argparse
import os
import sys

# Los scripts se corren desde backend/ (cd backend && .venv/bin/python scripts/...).
# Sin esto, `from app.core...` falla al ejecutar el archivo directamente.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.trial_registry import (
    BASE_THRESHOLD,
    STATUS_INEJECUTABLE,
    all_trials,
    consumed_budget,
    current_threshold,
    trials_by_family,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proyectar-trials", type=int, default=1, metavar="N",
                        help="cuantos trials nuevos proyectar por familia (default 1)")
    args = parser.parse_args()
    if args.proyectar_trials < 1:
        print("--proyectar-trials debe ser >= 1", file=sys.stderr)
        sys.exit(1)

    entries = all_trials()
    por_familia = trials_by_family()

    print("=" * 72)
    print("M6 — AUDITORIA DEL PRESUPUESTO DE TRIALS")
    print("=" * 72)
    if not entries:
        print("El registro esta vacio. Corre primero scripts/backfill_trial_registry.py")
        sys.exit(0)
    print(f"entradas en el registro: {len(entries)}")
    print(f"umbral base (criterio DSR del proyecto): {BASE_THRESHOLD:.2f}")
    print()
    print(f"{'familia':22s} {'entradas':>8s} {'consumidos':>10s} {'umbral actual':>14s} "
          f"{'umbral +N':>10s} {'rechazados B5':>14s}")
    print("-" * 88)
    for familia, lista in sorted(por_familia.items()):
        n_entradas = len(lista)
        consumidos = consumed_budget(familia)
        umbral_actual = current_threshold(familia)
        umbral_proyectado = 1.0 - (1.0 - BASE_THRESHOLD) / (consumidos + args.proyectar_trials + 1)
        # B5: los diseños rechazados por potencia ANTES de correr no consumen
        # presupuesto — se muestran aparte para que el rechazo sea visible y
        # auditable (no desaparece del registro, solo deja de contar como trial).
        n_rechazados = sum(1 for e in lista if e.get("status") == STATUS_INEJECUTABLE)
        print(f"{familia:22s} {n_entradas:8d} {consumidos:10d} {umbral_actual:14.4f} "
              f"{umbral_proyectado:10.4f} {n_rechazados:14d}")

    print()
    print("ADVERTENCIA (contrato M6): este umbral es el Bonferroni vigente para la")
    print("familia. Un trial nuevo que NO lo declare en su pre-registro viola la")
    print("regla 1 de ONBOARDING.md (criterio pre-registrado antes de correr).")
    print("El umbral se endurece con cada trial consumido: proyectalo SIEMPRE")


if __name__ == "__main__":
    main()
