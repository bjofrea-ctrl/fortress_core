"""Tests para la persistencia de sugerencias (Pieza 2) y el router de
oportunidades (Pieza 1)."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from app.core import suggestions_store as store
from app.core.suggestions_store import (
    SUGGESTIONS_PATH, evaluate_pending, get_track_record, record_suggestions,
)


@pytest.fixture(autouse=True)
def clean_store(monkeypatch, tmp_path):
    """Aisla el store en un archivo temporal por test."""
    fake = str(tmp_path / "suggestions.json")
    monkeypatch.setattr(store, "SUGGESTIONS_PATH", fake)
    yield
    if os.path.exists(fake):
        os.remove(fake)


def test_record_and_dedup_same_day():
    s = [{"symbol": "AAPL", "score": 0.7, "win_prob": 0.55}]
    assert record_suggestions(s, "2026-08-10") == 1
    assert record_suggestions(s, "2026-08-10") == 0, "mismo día no se re-registra"
    assert record_suggestions(s, "2026-08-11") == 1, "día distinto sí"


def test_track_record_insufficient():
    assert get_track_record()["sufficient"] is False
    record_suggestions([{"symbol": "AAPL", "score": 0.7, "win_prob": 0.55}], "2026-08-10")
    assert get_track_record()["n"] == 0, "sin outcomes no cuenta"


def test_evaluate_pending_sets_outcome(tmp_path):
    n = 260
    dates = pd.bdate_range("2026-01-02", periods=n)
    close = pd.Series(np.linspace(100, 130, n), index=dates)
    df = pd.DataFrame({"close": close}, index=dates)

    # sugerencia el día 5; con +20 hábiles el precio sube -> outcome 1
    record_suggestions([{"symbol": "TEST", "score": 0.7, "win_prob": 0.5}], str(dates[5].date()))
    result = evaluate_pending({"TEST": df})
    assert result["evaluated"] == 1
    assert result["remaining"] == 0

    with open(store.SUGGESTIONS_PATH) as f:
        saved = json.load(f)
    assert saved[0]["outcome"] == 1, "precio subió a 20d -> win"
    assert saved[0]["evaluated_at"] is not None


def test_evaluate_skips_not_mature():
    n = 24  # día 5 + 20 = 25 >= 24 -> aún no vence
    dates = pd.bdate_range("2026-01-02", periods=n)
    close = pd.Series(np.linspace(100, 130, n), index=dates)
    df = pd.DataFrame({"close": close}, index=dates)
    record_suggestions([{"symbol": "TEST", "score": 0.7, "win_prob": 0.5}], str(dates[5].date()))
    result = evaluate_pending({"TEST": df})
    assert result["evaluated"] == 0, "no venció (faltan +20 hábiles)"
    assert result["remaining"] == 1


def test_track_record_with_evaluated():
    n = 300
    dates = pd.bdate_range("2025-01-02", periods=n)
    close = pd.Series(np.linspace(100, 160, n), index=dates)
    df = pd.DataFrame({"close": close}, index=dates)

    for i, sym in enumerate(["A", "B", "C", "D", "E", "F"]):
        record_suggestions([{"symbol": sym, "score": 0.7, "win_prob": 0.55}], str(dates[i].date()))
    evaluate_pending({s: df for s in ["A", "B", "C", "D", "E", "F"]})

    tr = get_track_record()
    assert tr["sufficient"] is True
    assert tr["n"] == 6
    assert tr["win_rate"] == 1.0, "tendencia alcista -> todas ganan"
    assert tr["brier"] is not None
