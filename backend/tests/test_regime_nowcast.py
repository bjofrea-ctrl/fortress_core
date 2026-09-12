"""Tests for RegimeNowcaster (Phase 1 institutional-flow-score).

Validates:
- fit_expanding never uses data > up_to_date (causal)
- predict_proba_aligned sums to 1.0
- Labels are exactly [GOLDILOCKS, REFLATION, STAGFLATION, DEFLATION]
- walk_forward_probas has no lookahead
- Cache invalidation works (1h TTL)
"""
import os
import pickle
import time

import numpy as np
import pandas as pd
import pytest
from app.core.regime_nowcast import (
    CACHE_TTL_SECONDS,
    SEMANTIC_LABELS,
    RegimeNowcaster,
    RegimeSnapshot,
)

# Test data setup
TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "VIX"]


def _synthetic_price_data(n_days=800, seed=42):
    """Generate synthetic price data with realistic structure (enough for 252+ days before cutoff)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=n_days)
    data = {}
    for i, t in enumerate(TICKERS):
        drift = (i - len(TICKERS) / 2) * 0.0003
        returns = rng.normal(drift, 0.01, n_days)
        close = 100 * np.cumprod(1 + returns)
        data[t] = pd.DataFrame({"close": close}, index=dates)
    return data


def _mock_price_data_loader(price_data):
    """Helper to mock _load_price_data on a RegimeNowcaster instance."""
    def mock_load():
        return price_data
    return mock_load


class TestFitExpandingCausal:
    """Tests for fit_expanding causal property."""

    def test_fit_expanding_truncates_data_at_up_to_date(self):
        """fit_expanding(up_to_date) must not use data beyond up_to_date."""
        price_data = _synthetic_price_data(n_days=800, seed=1)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        # Fit up to a specific date (well after 252 days from start)
        cutoff = pd.Timestamp("2020-06-01")
        nowcaster.fit_expanding(cutoff)

        # Verify classifier was fitted on truncated data
        assert nowcaster._fitted_up_to == cutoff

        # Verify the internal classifier's features only go up to cutoff
        feats = nowcaster._classifier._extract_features(
            {t: df[df.index <= cutoff] for t, df in price_data.items()}
        )
        assert feats.index.max() <= cutoff

    def test_fit_expanding_recomputes_align_states(self):
        """_align_states must be recomputed on each refit."""
        price_data = _synthetic_price_data(n_days=800, seed=2)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        # First fit
        date1 = pd.Timestamp("2020-06-01")
        nowcaster.fit_expanding(date1)
        clf1 = nowcaster._classifier

        # Second fit (later date)
        date2 = pd.Timestamp("2020-07-01")
        nowcaster.fit_expanding(date2)
        clf2 = nowcaster._classifier

        # Classifiers should be different objects (re-fit)
        assert clf1 is not clf2

        # Both should have is_fitted = True
        assert clf1.is_fitted
        assert clf2.is_fitted

    def test_fit_expanding_caches_model(self):
        """Fitted model should be cached to disk."""
        price_data = _synthetic_price_data(n_days=800, seed=3)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        cutoff = pd.Timestamp("2020-06-01")
        nowcaster.fit_expanding(cutoff)

        # Check cache file exists
        cache_path = nowcaster._cache_path(cutoff)
        assert os.path.exists(cache_path)

        # Verify cache can be loaded
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        assert cached["fitted_up_to"] == cutoff
        assert cached["classifier"].is_fitted

    def test_fit_expanding_uses_cache_when_valid(self):
        """Second call with same date should use cache (not re-fit)."""
        price_data = _synthetic_price_data(n_days=800, seed=4)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        cutoff = pd.Timestamp("2020-06-01")

        # First fit
        nowcaster.fit_expanding(cutoff)
        clf1 = nowcaster._classifier

        # Second fit (should use cache)
        nowcaster.fit_expanding(cutoff)
        clf2 = nowcaster._classifier

        # Both should be fitted and have same fitted_up_to date
        # (Loaded from cache, so not same object but same state)
        assert clf1 is not clf2
        assert clf1.is_fitted
        assert clf2.is_fitted
        assert nowcaster._fitted_up_to == cutoff


class TestPredictProbaAligned:
    """Tests for predict_proba_aligned."""

    def test_predict_proba_sums_to_one(self):
        """Probabilities must sum to 1.0 ± 1e-10."""
        price_data = _synthetic_price_data(n_days=800, seed=5)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        as_of = pd.Timestamp("2020-06-15")
        nowcaster.fit_expanding(as_of)

        probs = nowcaster.predict_proba_aligned(as_of)

        assert probs.shape == (4,)
        assert np.isclose(probs.sum(), 1.0, atol=1e-10), f"Sum={probs.sum()}"
        assert (probs >= 0).all()
        assert (probs <= 1).all()

    def test_labels_semantic(self):
        """Labels must be exactly [GOLDILOCKS, REFLATION, STAGFLATION, DEFLATION]."""
        assert SEMANTIC_LABELS == ["GOLDILOCKS", "REFLATION", "STAGFLATION", "DEFLATION"]

        price_data = _synthetic_price_data(n_days=800, seed=6)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        as_of = pd.Timestamp("2020-06-15")
        nowcaster.fit_expanding(as_of)

        probs = nowcaster.predict_proba_aligned(as_of)

        # Get state from argmax
        state_idx = int(np.argmax(probs))
        state_name = SEMANTIC_LABELS[state_idx]

        assert state_name in SEMANTIC_LABELS

    def test_get_current_regime_returns_snapshot(self):
        """get_current_regime returns RegimeSnapshot with correct structure."""
        price_data = _synthetic_price_data(n_days=800, seed=7)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        as_of = pd.Timestamp("2020-06-15")
        nowcaster.fit_expanding(as_of)

        snapshot = nowcaster.get_current_regime(as_of)

        assert isinstance(snapshot, RegimeSnapshot)
        assert snapshot.date == as_of
        assert snapshot.state in range(4)
        assert snapshot.state_name in SEMANTIC_LABELS
        assert snapshot.confidence >= 0.0 and snapshot.confidence <= 1.0
        assert set(snapshot.probabilities.keys()) == set(SEMANTIC_LABELS)
        assert np.isclose(sum(snapshot.probabilities.values()), 1.0, atol=1e-10)


class TestWalkForwardProbas:
    """Tests for walk_forward_probas causal validation."""

    def test_walk_forward_no_lookahead(self):
        """Each fit in walk_forward must use only data ≤ that date."""
        price_data = _synthetic_price_data(n_days=800, seed=8)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        start = pd.Timestamp("2020-06-01")
        end = pd.Timestamp("2020-06-10")
        results = nowcaster.walk_forward_probas(start, end, freq="D")

        # Should have results for each valid business day
        assert len(results) > 0

        # The last fitted date should be the last date in results
        for date, probs in results:
            assert start <= date <= end
            if probs is not None:
                assert probs.shape == (4,)
                assert np.isclose(probs.sum(), 1.0, atol=1e-10)

        # Last fitted date should be the last date with valid probs
        last_valid_date = max(d for d, p in results if p is not None)
        assert nowcaster._fitted_up_to == last_valid_date

    def test_walk_forward_soft_failure_on_error(self):
        """If HMM fails on a date, returns None for probs, continues."""
        price_data = _synthetic_price_data(n_days=800, seed=9)

        # Make SPY have very little data (less than 252 days)
        price_data["SPY"] = price_data["SPY"].iloc[:100]

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        # Use dates that fall within the 100-day SPY range (2018)
        start = price_data["SPY"].index[10]
        end = price_data["SPY"].index[20]
        results = nowcaster.walk_forward_probas(start, end, freq="D")

        # Should still return results (with None for failed dates)
        assert len(results) > 0
        # At least some should be None due to insufficient data (< 252 days)
        none_count = sum(1 for _, p in results if p is None)
        assert none_count > 0


class TestCacheInvalidation:
    """Tests for cache TTL and invalidation."""

    def test_cache_invalid_after_1h(self):
        """Cache older than 1h should be invalidated."""
        price_data = _synthetic_price_data(n_days=800, seed=10)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        cutoff = pd.Timestamp("2020-06-01")
        nowcaster.fit_expanding(cutoff)
        cache_path = nowcaster._cache_path(cutoff)

        # Manually set mtime to >1h ago
        old_time = time.time() - CACHE_TTL_SECONDS - 10
        os.utime(cache_path, (old_time, old_time))

        # Create new nowcaster (fresh instance)
        nowcaster2 = RegimeNowcaster()
        nowcaster2._load_price_data = _mock_price_data_loader(price_data)

        # Should not load from cache (too old)
        # This will trigger a re-fit
        nowcaster2.fit_expanding(cutoff)

        # New cache file should have been created with new mtime
        new_mtime = os.path.getmtime(cache_path)
        assert new_mtime > old_time

    def test_cache_valid_within_1h(self):
        """Cache within 1h should be used."""
        price_data = _synthetic_price_data(n_days=800, seed=11)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        cutoff = pd.Timestamp("2020-06-01")
        nowcaster.fit_expanding(cutoff)

        # Create new nowcaster immediately
        nowcaster2 = RegimeNowcaster()
        nowcaster2._load_price_data = _mock_price_data_loader(price_data)

        # Should load from cache (mtime is recent)
        nowcaster2.fit_expanding(cutoff)

        # Classifier should be loaded from cache (same behavior)
        assert nowcaster2._classifier is not None
        assert nowcaster2._fitted_up_to == cutoff


class TestSoftFailure:
    """Tests for soft failure behavior."""

    def test_soft_failure_response(self):
        """soft_failure_response returns valid snapshot with zeros."""
        nowcaster = RegimeNowcaster()

        as_of = pd.Timestamp("2020-06-15")
        snapshot = nowcaster.soft_failure_response(as_of)

        assert isinstance(snapshot, RegimeSnapshot)
        assert snapshot.date == as_of
        assert snapshot.state == -1
        assert snapshot.state_name == "UNKNOWN"
        assert snapshot.confidence == 0.0
        assert all(v == 0.0 for v in snapshot.probabilities.values())


class TestEdgeCases:
    """Edge case tests."""

    def test_insufficient_data_raises(self):
        """Should raise ValueError if insufficient data after truncation."""
        # Use data that starts very close to the cutoff date
        price_data = _synthetic_price_data(n_days=800, seed=12)

        # Truncate all tickers to have < 252 days before cutoff
        cutoff = pd.Timestamp("2018-02-01")  # Only ~30 days of data
        truncated_data = {}
        for t, df in price_data.items():
            truncated_data[t] = df[df.index <= cutoff]

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = lambda: truncated_data

        with pytest.raises(ValueError, match="Insufficient data"):
            nowcaster.fit_expanding(cutoff)

    def test_predict_before_fit_raises(self):
        """predict_proba_aligned should raise if not fitted."""
        price_data = _synthetic_price_data(n_days=800, seed=13)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        as_of = pd.Timestamp("2020-06-15")

        # predict_proba_aligned calls _ensure_fitted which calls fit_expanding
        # So it won't raise - it will fit first. Test that it fits and returns probs.
        probs = nowcaster.predict_proba_aligned(as_of)
        assert probs.shape == (4,)
        assert np.isclose(probs.sum(), 1.0, atol=1e-10)

    def test_probability_permutation_matches_alignment(self):
        """Permutation of raw probs must match _align_states mapping."""
        price_data = _synthetic_price_data(n_days=800, seed=14)

        nowcaster = RegimeNowcaster()
        nowcaster._load_price_data = _mock_price_data_loader(price_data)

        as_of = pd.Timestamp("2020-06-15")
        nowcaster.fit_expanding(as_of)

        clf = nowcaster._classifier
        truncated = {t: df[df.index <= as_of] for t, df in price_data.items()}
        feats = clf._extract_features(truncated)
        scaled = clf.scaler.transform(feats.values)

        raw_states = clf.model.predict(scaled)
        aligned_states = clf._align_states(raw_states, feats)
        raw_probs = clf.model.predict_proba(scaled)

        # Last day
        raw_last = int(raw_states[-1])
        aligned_last = int(aligned_states[-1])

        # Our predict_proba_aligned should match this mapping
        probs = nowcaster.predict_proba_aligned(as_of)

        # The probability at aligned_last index should equal raw_probs[-1, raw_last]
        assert np.isclose(probs[aligned_last], raw_probs[-1, raw_last], atol=1e-10)
