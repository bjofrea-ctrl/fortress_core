"""Reporte semanal de costos de ejecución desde execution_telemetry (A5).

Distribución de slippage por símbolo/tamaño vs el costo ASUMIDO §33
(0.10%/lado = COST_PER_SIDE 0.0005 + slippage_referencia 0.0005). Después de
N≥30 fills oficiales el costo vigente pasa de supuesto a medido — este reporte
es la evidencia de esa transición (PLAN_REMEDIO_BRECHAS_20260903, A5).

Solo lee la tabla execution_telemetry de fortress.db; las órdenes de checkpoint
(OVERRIDE_MECANISMO) NUNCA se mezclan con las oficiales (condición (b) del gate
2026-08-25) — el desglose las muestra separadas si existen.

Uso:
  cd backend && .venv/bin/python -m scripts.execution_cost_report [--db fortress.db]
"""
import argparse
import os
import sqlite3
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

DEFAULT_DB = "fortress.db"
ASSUMED_PER_SIDE = 0.0010  # §33: 0.10%/lado (0.05% comisión + 0.05% slippage ref)
N_MIN_MEASURED = 30        # A5: con N>=30 fills oficiales el costo pasa a medido


def _rows(db_path: str, days: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = ("SELECT * FROM execution_telemetry "
           "WHERE status = 'submitted' AND fill_price IS NOT NULL")
    params: List[Any] = []
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        sql += " AND ts >= ?"
        params.append(cutoff)
    sql += " ORDER BY id"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [{k: r[k] for k in r.keys()} for r in conn.execute(sql, params).fetchall()]


def _pct(x: float) -> str:
    return f"{x * 100:+.3f}%"


def build_report(db_path: str = DEFAULT_DB, days: Optional[int] = 7) -> Dict[str, Any]:
    """Reporte: resumen global + por símbolo + por side, oficiales vs checkpoint."""
    rows = _rows(db_path, days)
    official = [r for r in rows if not r["checkpoint_override"]]
    checkpoint = [r for r in rows if r["checkpoint_override"]]

    def _stats(sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        slips = [r["slippage_implicit"] for r in sub
                 if r["slippage_implicit"] is not None]
        if not slips:
            return {"n": len(sub), "n_with_slippage": 0}
        return {
            "n": len(sub),
            "n_with_slippage": len(slips),
            "mean": statistics.fmean(slips),
            "median": statistics.median(slips),
            "min": min(slips),
            "max": max(slips),
            "stdev": statistics.stdev(slips) if len(slips) > 1 else 0.0,
        }

    by_symbol: Dict[str, Dict[str, Any]] = {}
    for r in official:
        s = r["slippage_implicit"]
        d = by_symbol.setdefault(r["symbol"], {"n": 0, "slips": []})
        d["n"] += 1
        if s is not None:
            d["slips"].append(s)

    measured = _stats(official)
    measured["assumed_per_side"] = ASSUMED_PER_SIDE
    measured["cost_basis"] = (
        "MEDIDO" if measured.get("n_with_slippage", 0) >= N_MIN_MEASURED
        else f"SUPUESTO (n={measured.get('n_with_slippage', 0)} < {N_MIN_MEASURED} fills)")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_days": days,
        "official": measured,
        "by_symbol": {k: {"n": v["n"],
                         "median_slippage": statistics.median(v["slips"]) if v["slips"] else None}
                      for k, v in sorted(by_symbol.items())},
        "checkpoint_mecanismo": _stats(checkpoint),
        "nota": "checkpoint (OVERRIDE_MECANISMO) excluido del costo oficial",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--days", type=int, default=7,
                        help="ventana del reporte (default 7 = semanal)")
    args = parser.parse_args(argv)
    if not os.path.exists(args.db):
        print(f"sin {args.db}: aún no hay telemetría (tabla se crea en el primer run real)")
        return 0
    rep = build_report(args.db, args.days)
    print(f"=== Execution cost report — A5 (ventana {rep['window_days']}d) ===")
    o = rep["official"]
    print(f"Oficiales: n={o['n']} (con slippage: {o.get('n_with_slippage', 0)}) | "
          f"base del costo: {o['cost_basis']}")
    if o.get("n_with_slippage"):
        print(f"  slippage/lado: mean={_pct(o['mean'])} median={_pct(o['median'])} "
              f"min={_pct(o['min'])} max={_pct(o['max'])} sd={o['stdev']:.5f}")
        print(f"  vs asumido §33: {_pct(ASSUMED_PER_SIDE)}/lado "
              f"(comisión+slippage supuestos)")
    for sym, d in rep["by_symbol"].items():
        med = _pct(d["median_slippage"]) if d["median_slippage"] is not None else "n/a"
        print(f"  {sym:6s} n={d['n']:3d} median_slippage={med}")
    ck = rep["checkpoint_mecanismo"]
    if ck["n"]:
        print(f"Checkpoint (mecanismo, EXCLUIDO del oficial): n={ck['n']}")
    print(f"Nota: {rep['nota']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
