"""B8 §2a — tests de measure_realized_edge sobre ledger sintético.

Casos del pre-registro:
  - n=0 y n<30 => "n insuficiente", NADA inventado (todos los estimadores None).
  - status filtering: sólo 'closed' cuenta.
  - n>=30 con distribución conocida => valida win-rate, R:R y sus IC bootstrap.
  - la firma ASPIRACIONAL se reporta pero NO se usa como valor estimado.
"""
import pytest
from scripts.measure_realized_edge import (
    ASPIRATIONAL_SIGNATURE,
    MIN_SAMPLE,
    measure_realized_edge,
)


def _row(pnl, status="closed", exit_date="2026-01-15"):
    return {"pnl_r": pnl, "status": status, "exit_date": exit_date}


def test_n_zero_insufficient():
    res = measure_realized_edge([])
    assert res["n"] == 0
    assert res["sufficient"] is False
    assert res["message"] == "n insuficiente para estimar, no inventar un número"
    assert res["win_rate"] is None
    assert res["realized_rr"] is None
    assert res["trades_per_month"] is None
    assert res["aspirational_signature"] == ASPIRATIONAL_SIGNATURE


def test_n_below_30_insufficient():
    rows = [_row(1.0) for _ in range(10)] + [_row(-1.0) for _ in range(10)]
    res = measure_realized_edge(rows)
    assert res["n"] == 20
    assert res["sufficient"] is False
    assert res["win_rate"] is None
    assert res["realized_rr"] is None


def test_status_filtering_excludes_open_and_pending():
    # Sólo los cerrados cuentan; abiertos/pending se ignoran.
    rows = (
        [_row(2.0, status="open") for _ in range(40)]
        + [_row(2.0, status="pending") for _ in range(10)]
        + [_row(2.0, status="closed") for _ in range(40)]
    )
    res = measure_realized_edge(rows)
    assert res["n"] == 40
    assert res["sufficient"] is True


def test_known_distribution_validates_calculation():
    # 50% win-rate: 20 ganadoras pnl=+2.0 (mediana +2.0),
    # 30 perdedoras pnl=-1.0 (mediana -1.0) => R:R = 2.0/1.0 = 2.0.
    rows = (
        [_row(2.0, exit_date="2026-01-01") for _ in range(20)]
        + [_row(-1.0, exit_date="2026-02-01") for _ in range(30)]
    )
    res = measure_realized_edge(rows)
    assert res["n"] == 50
    assert res["sufficient"] is True
    assert abs(res["win_rate"] - 0.40) < 1e-9
    assert abs(res["realized_rr"] - 2.0) < 1e-9
    # El IC95 contiene al estimador puntual.
    lo, hi = res["win_rate_ci"]
    assert lo <= res["win_rate"] <= hi
    lo2, hi2 = res["realized_rr_ci"]
    assert lo2 <= res["realized_rr"] <= hi2
    # Frecuencia: 50 trades en ~1 mes => ~50/mes.
    assert 30 < res["trades_per_month"] < 70


def test_aspirational_signature_reported_not_used_as_value():
    res = measure_realized_edge([_row(1.0) for _ in range(40)])
    assert res["aspirational_signature"]["win_rate"] == "0.25-0.40"
    assert res["aspirational_signature"]["rr"] == "4-8:1"
    # No inventa el punto medio de la firma aspiracional como estimador.
    assert res["win_rate"] != 0.325


def test_min_sample_threshold_exactly_29_insufficient():
    rows = [_row(1.0) for _ in range(29)]
    res = measure_realized_edge(rows)
    assert res["n"] == MIN_SAMPLE - 1
    assert res["sufficient"] is False


def test_min_sample_threshold_exactly_30_sufficient():
    rows = [_row(1.0) for _ in range(30)]
    res = measure_realized_edge(rows)
    assert res["n"] == MIN_SAMPLE
    assert res["sufficient"] is True
    assert res["win_rate"] == pytest.approx(1.0)
