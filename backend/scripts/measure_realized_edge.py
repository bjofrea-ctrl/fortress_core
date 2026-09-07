"""B8 (PRE_REGISTRO_WINRATE_RR_SIZING_CAP_20260906.md) — 2a. Medición del edge real.

No es un trial: no consume slot del `trial_registry` (categoría instrumentation/infra,
igual que A2). Instrumenta el `signal_ledger` para calcular sobre las señales YA
CERRADAS (`status='closed'`) del motor real:

  - win-rate real:   % de trades con pnl_r > 0
  - R:R real:        mediana(pnl_r | pnl_r>0) / |mediana(pnl_r | pnl_r<0)|
  - frecuencia real: trades/mes efectivos (no asumidos)

Los 3 números salen con intervalo de confianza bootstrap (NO se asume normalidad:
n va a ser chico hoy). Si el ledger no tiene suficientes trades cerrados (n < 30),
el output dice explícitamente "n insuficiente para estimar, no inventar un número"
— NUNCA se rellena con el 25-40%/4-8:1 de la simulación Monte Carlo del ticket.

La firma 25-40%/4-8:1 queda documentada como ASPIRACIONAL y se reporta aparte,
pero jamás se usa como valor estimado.

Uso:
  python -m scripts.measure_realized_edge [--db fortress.db] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

# B8 §2a: umbral mínimo de trades cerrados para estimar. Por debajo, el output
# es "n insuficiente" y no se inventa ningún número.
MIN_SAMPLE = 30

# Firma ASPIRACIONAL del ticket (NO es un parámetro de producción, solo referencia).
ASPIRATIONAL_SIGNATURE = {"win_rate": "0.25-0.40", "rr": "4-8:1"}

DEFAULT_BOOTSTRAP = 2000
DEFAULT_SEED = 12345


def _to_date(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _closed_pairs(rows: Sequence[Dict]) -> List[Tuple[float, Optional[datetime]]]:
    """Filtra trades cerrados y devuelve (pnl_r, exit_date) como tuplas."""
    out = []
    for r in rows:
        if r.get("status") != "closed":
            continue
        try:
            pnl = float(r.get("pnl_r"))
        except (TypeError, ValueError):
            continue
        out.append((pnl, _to_date(r.get("exit_date"))))
    return out


def _months_span(dates: Sequence[datetime]) -> float:
    """Span en meses (30.44 d/m) de una lista de fechas; mínimo ~1 día."""
    ds = [d for d in dates if d is not None]
    if not ds:
        return 1.0 / 30.44
    if len(ds) == 1:
        return 1.0 / 30.44
    span_days = (max(ds) - min(ds)).days
    return max(span_days / 30.44, 1.0 / 30.44)


def _freq_of(pairs: Sequence[Tuple[float, Optional[datetime]]]) -> float:
    if not pairs:
        return 0.0
    span = _months_span([d for _, d in pairs])
    return len(pairs) / span


def _boot_ci(
    stat_fn,
    pairs: List[Tuple[float, Optional[datetime]]],
    rng: random.Random,
    n_boot: int,
) -> Tuple[float, float]:
    """IC bootstrap percentil 2.5/97.5. Descarta NaN (resample sin ganancias/pérdidas)."""
    vals: List[float] = []
    n = len(pairs)
    for _ in range(n_boot):
        sample = [rng.choice(pairs) for _ in range(n)]
        try:
            v = stat_fn(sample)
        except ZeroDivisionError:
            v = float("nan")
        if v == v:  # filtra NaN
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[min(int(0.975 * len(vals)), len(vals) - 1)]
    return (lo, hi)


def measure_realized_edge(
    rows: Sequence[Dict],
    n_bootstrap: int = DEFAULT_BOOTSTRAP,
    seed: int = DEFAULT_SEED,
) -> Dict:
    """Calcula win-rate, R:R y frecuencia reales sobre trades cerrados.

    Devuelve un dict con `sufficient` (bool). Si insuficiente, todos los
    estimadores son None y `message` explica por qué (nunca se inventa un número).
    """
    pairs = _closed_pairs(rows)
    n = len(pairs)
    result: Dict = {
        "n": n,
        "sufficient": n >= MIN_SAMPLE,
        "aspirational_signature": ASPIRATIONAL_SIGNATURE,
    }

    if n < MIN_SAMPLE:
        result.update({
            "message": "n insuficiente para estimar, no inventar un número",
            "win_rate": None,
            "win_rate_ci": None,
            "realized_rr": None,
            "realized_rr_ci": None,
            "trades_per_month": None,
            "trades_per_month_ci": None,
        })
        return result

    rng = random.Random(seed)
    pnls = [p for p, _ in pairs]
    wins = [1.0 if p > 0 else 0.0 for p in pnls]
    win_rate = statistics.fmean(wins)

    gains = [p for p, _ in pairs if p > 0]
    losses = [abs(p) for p, _ in pairs if p < 0]
    trades_per_month = _freq_of(pairs)

    win_rate_ci = _boot_ci(
        lambda s: statistics.fmean([1.0 if p > 0 else 0.0 for p, _ in s]),
        pairs, rng, n_bootstrap,
    )
    freq_ci = _boot_ci(_freq_of, pairs, rng, n_bootstrap)

    # R:R = mediana(ganancias) / |mediana(pérdidas)|. Indefinido si no hay
    # ganadores O no hay perdedores en la muestra => None, nunca se inventa.
    if gains and losses:
        realized_rr = statistics.median(gains) / statistics.median(losses)
        rr_ci = _boot_ci(
            lambda s: statistics.median([p for p, _ in s if p > 0])
            / statistics.median([abs(p) for p, _ in s if p < 0]),
            pairs, rng, n_bootstrap,
        )
        rr_note = None
    else:
        realized_rr = None
        rr_ci = None
        rr_note = "R:R indefinido: muestra sin trades ganadores o sin perdedores"

    result.update({
        "win_rate": win_rate,
        "win_rate_ci": win_rate_ci,
        "realized_rr": realized_rr,
        "realized_rr_ci": rr_ci,
        "realized_rr_note": rr_note,
        "trades_per_month": trades_per_month,
        "trades_per_month_ci": freq_ci,
        "n_bootstrap": n_bootstrap,
    })
    return result


def load_closed_trades(db_path: str = "fortress.db") -> List[Dict]:
    """Carga TODAS las filas del ledger (measure_realized_edge filtra status='closed')."""
    from app.core.signal_ledger import SignalLedger

    return SignalLedger(db_path).fetch()


def _print_report(res: Dict) -> None:
    print("=" * 60)
    print("B8 §2a — EDGE REAL DEL MOTOR (sobre trades cerrados)")
    print("=" * 60)
    print(f"Trades cerrados (n): {res['n']}")
    print(f"Suficiente para estimar: {res['sufficient']}")
    if not res["sufficient"]:
        print(f"\n>>> {res['message']}")
        print(">>> No se reporta ningún número inventado.")
    else:
        print(f"\nWin-rate real     : {res['win_rate']:.3f}   IC95 {tuple(round(x, 3) for x in res['win_rate_ci'])}")
        print(f"R:R real          : {res['realized_rr']:.3f}   IC95 {tuple(round(x, 3) for x in res['realized_rr_ci'])}")
        print(f"Trades/mes real   : {res['trades_per_month']:.2f}   IC95 {tuple(round(x, 2) for x in res['trades_per_month_ci'])}")
    print(f"\nFirma ASPIRACIONAL (NO usada como valor): {res['aspirational_signature']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="B8 §2a — medición de edge real del motor")
    ap.add_argument("--db", default=os.getenv("FORTRESS_DB", "fortress.db"))
    ap.add_argument("--json", action="store_true", help="salida JSON")
    args = ap.parse_args()

    rows = load_closed_trades(args.db)
    res = measure_realized_edge(rows)

    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        _print_report(res)


if __name__ == "__main__":
    main()

