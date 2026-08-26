"""Reporte mensual por variante del ensamble (Frente 2, Semana 2).

Runner del mecanismo construido en app/core/monthly_report.py. Uso:

    PYTHONPATH=. python scripts/monthly_report.py                # todo el historial
    PYTHONPATH=. python scripts/monthly_report.py --mes 2026-09  # regenerar UN mes
    PYTHONPATH=. python scripts/monthly_report.py --db ruta/a/fortress.db

Imprime el reporte por variante/mes y la bitácora acumulada. Cada corrida
deja los veredictos registrados en la tabla monthly_report_log de la MISMA
db del signal_ledger (upsert idempotente). NO toca trial_registry.json.
"""
import argparse
import sys

from app.core.monthly_report import MonthlyReporter


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default="fortress.db",
                    help="ruta a la SQLite del signal_ledger (default fortress.db)")
    ap.add_argument("--mes", default=None,
                    help="regenerar solo este mes 'YYYY-MM' (default: todo)")
    args = ap.parse_args()

    rep = MonthlyReporter(db_path=args.db)
    out = rep.generate(month=args.mes)

    print("=" * 70)
    print(f"REPORTE MENSUAL — generado {out['generated_at']} "
          f"(umbral calibración {out['umbral_calibracion']:.0%} del esperado)")
    print("=" * 70)
    if not out["rows"]:
        print("Sin filas cerradas en el ledger todavía — el mecanismo está "
              "listo y espera historial real.")
    for r in out["rows"]:
        print(f"\n[{r['variant']}] {r['month']}")
        print(f"  {r['diagnostico']}")
        if r.get("sharpe_annualized") is not None:
            print(f"  (anualizado ref.: {r['sharpe_annualized']:.2f})")

    bit = rep.bitacora()
    if bit:
        print("\n" + "-" * 70)
        print("BITÁCORA ACUMULADA (meses que calibraron bien por variante)")
        for b in bit:
            print(f"  {b['variant']}: {b['en_calibracion']}/{b['meses']} meses "
                  f"EN_CALIBRACION | debajo={b['debajo_esperado']} "
                  f"negativos={b['negativos']} no-medibles={b['no_medibles']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
