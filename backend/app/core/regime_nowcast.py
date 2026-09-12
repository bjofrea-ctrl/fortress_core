"""Regime Nowcaster — walk-forward expanding window HMM with semantic alignment.

Phase 1 of institutional-flow-score: RegimeNowcaster provides causal regime
probabilities fitted on data up to a given date, with state alignment recomputed
at each refit. Cache TTL 1h, soft failure on HMM errors.
"""
import os
import pickle
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.core.regime_classifier import GlobalRegimeClassifier

SEMANTIC_LABELS = ["GOLDILOCKS", "REFLATION", "STAGFLATION", "DEFLATION"]
CACHE_TTL_SECONDS = 3600  # 1 hour


@dataclass(frozen=True)
class RegimeSnapshot:
    """Single-date regime state with aligned probabilities."""
    date: pd.Timestamp
    state: int
    state_name: str
    probabilities: Dict[str, float]
    confidence: float


class RegimeNowcaster:
    """
    Walk-forward expanding-window regime nowcaster.

    - fit_expanding(up_to_date): re-fits HMM on data ≤ up_to_date, recomputes _align_states
    - predict_proba_aligned(date): returns 4 probabilities summing to 1.0, mapped to semantic labels
    - get_current_regime(): convenience for latest available date
    - walk_forward_probas(start, end, freq): generator for validation
    - Cache: data/cache/regime_nowcaster_{date}.pkl with 1h TTL + lock
    """

    def __init__(self, n_states: int = 4, cache_dir: Optional[str] = None):
        self.n_states = n_states
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "data", "cache"
        )
        os.makedirs(self.cache_dir, exist_ok=True)

        self._classifier: Optional[GlobalRegimeClassifier] = None
        self._price_data: Optional[Dict[str, pd.DataFrame]] = None
        self._fitted_up_to: Optional[pd.Timestamp] = None
        self._lock = threading.Lock()

    def _cache_path(self, as_of: pd.Timestamp) -> str:
        """Cache filename keyed by fit date."""
        date_str = as_of.strftime("%Y%m%d")
        return os.path.join(self.cache_dir, f"regime_nowcaster_{date_str}.pkl")

    def _load_price_data(self) -> Dict[str, pd.DataFrame]:
        """Load price data from parquet cache. Only loads MARKET_TICKERS."""
        from app.api.routes.opportunities_universe import MARKET_TICKERS

        if self._price_data is not None:
            return self._price_data

        price_data = {}
        for ticker in MARKET_TICKERS:
            path = os.path.join(self.cache_dir, f"{ticker}.parquet")
            if os.path.exists(path):
                try:
                    df = pd.read_parquet(path)
                    if not df.empty and "close" in df.columns:
                        price_data[ticker] = df[["close"]].copy()
                except Exception:
                    continue
        self._price_data = price_data
        return price_data

    def _try_load_cache(self, up_to_date: pd.Timestamp) -> bool:
        """Try to load fitted model from cache. Returns True if loaded and valid."""
        cache_path = self._cache_path(up_to_date)
        if not os.path.exists(cache_path):
            return False

        # Check TTL
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime > CACHE_TTL_SECONDS:
            return False

        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)

            self._classifier = cached["classifier"]
            self._fitted_up_to = cached["fitted_up_to"]
            # Verify the cached model was fitted on the correct date
            if self._fitted_up_to == up_to_date:
                return True
        except Exception:
            pass
        return False

    def _save_cache(self, up_to_date: pd.Timestamp) -> None:
        """Save fitted model to cache atomically."""
        if self._classifier is None:
            return
        cache_path = self._cache_path(up_to_date)
        tmp_path = cache_path + ".tmp"
        try:
            with open(tmp_path, "wb") as f:
                pickle.dump(
                    {"classifier": self._classifier, "fitted_up_to": up_to_date},
                    f,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
            os.replace(tmp_path, cache_path)
        except Exception:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def fit_expanding(self, up_to_date: pd.Timestamp) -> None:
        """
        Re-fit HMM using only data available at or before up_to_date.

        This method:
        1. Truncates price data to up_to_date (inclusive)
        2. Creates new GlobalRegimeClassifier
        3. Fits on truncated data
        4. Recomputes _align_states (called internally by fit)
        5. Caches the fitted model (with lock, TTL 1h)

        Args:
            up_to_date: Maximum date to use for fitting (inclusive)
        """
        with self._lock:
            # Check cache first
            if self._try_load_cache(up_to_date):
                return

            # Load and truncate price data
            price_data = self._load_price_data()
            if not price_data:
                raise ValueError("No price data available in cache")

            truncated = {
                ticker: df[df.index <= up_to_date] for ticker, df in price_data.items()
            }
            # Verify we have enough data
            if any(len(df) < 252 for df in truncated.values()):
                raise ValueError(f"Insufficient data after truncation to {up_to_date}")

            # Fit new classifier
            clf = GlobalRegimeClassifier(n_states=self.n_states)
            clf.fit(truncated)

            self._classifier = clf
            self._fitted_up_to = up_to_date

            # Save to cache
            self._save_cache(up_to_date)

    def _ensure_fitted(self, up_to_date: pd.Timestamp) -> GlobalRegimeClassifier:
        """Ensure classifier is fitted up to the requested date."""
        if self._classifier is None or self._fitted_up_to != up_to_date:
            self.fit_expanding(up_to_date)
        if self._classifier is None:
            raise RuntimeError("Classifier not fitted")
        return self._classifier

    def predict_proba_aligned(self, as_of: pd.Timestamp) -> np.ndarray:
        """
        Get aligned regime probabilities for a specific date.

        Returns 4 probabilities summing to 1.0, ordered as:
        [GOLDILOCKS, REFLATION, STAGFLATION, DEFLATION]

        The alignment (_align_states) is recomputed at each refit, so
        probabilities are permuted to match the current semantic ordering.
        """
        clf = self._ensure_fitted(as_of)

        # Truncate price data to as_of (inclusive)
        price_data = self._load_price_data()
        truncated = {t: df[df.index <= as_of] for t, df in price_data.items()}

        # Get features up to as_of
        feats = clf._extract_features(truncated)
        if len(feats) < 60:
            raise ValueError(f"Insufficient features for {as_of}")

        # Scale and get raw probabilities
        scaled = clf.scaler.transform(feats.values)
        raw_probs = clf.model.predict_proba(scaled)

        # Get raw states for alignment
        raw_states = clf.model.predict(scaled)
        aligned_states = clf._align_states(raw_states, feats)

        # Get the last date's probabilities, permuted to semantic order
        last_idx = -1

        # Permute raw probs to semantic order using the alignment mapping
        # We need the full mapping from raw state -> semantic state
        state_mapping = {}
        for i in range(len(raw_states)):
            state_mapping[raw_states[i]] = aligned_states[i]

        # Build permuted probability vector
        permuted_probs = np.zeros(self.n_states)
        for raw_s, semantic_s in state_mapping.items():
            permuted_probs[semantic_s] = raw_probs[last_idx, raw_s]

        # Ensure sum = 1 (numerical stability)
        prob_sum = permuted_probs.sum()
        if prob_sum > 0:
            permuted_probs = permuted_probs / prob_sum
        else:
            permuted_probs = np.full(self.n_states, 1.0 / self.n_states)

        return permuted_probs

    def get_current_regime(self, as_of: Optional[pd.Timestamp] = None) -> RegimeSnapshot:
        """
        Get current regime state with aligned probabilities.

        Args:
            as_of: Date to query (default: latest available in cache)

        Returns:
            RegimeSnapshot with state, probabilities, confidence, and date
        """
        price_data = self._load_price_data()
        if as_of is None:
            # Use latest date from price data
            all_dates = []
            for df in price_data.values():
                if len(df) > 0:
                    all_dates.append(df.index.max())
            if not all_dates:
                raise ValueError("No price data available")
            as_of = max(all_dates)

        # Get aligned probabilities
        probs = self.predict_proba_aligned(as_of)

        # Get state (argmax of aligned probs)
        state = int(np.argmax(probs))
        state_name = SEMANTIC_LABELS[state]
        confidence = float(probs[state])

        return RegimeSnapshot(
            date=as_of,
            state=state,
            state_name=state_name,
            probabilities={SEMANTIC_LABELS[i]: float(probs[i]) for i in range(self.n_states)},
            confidence=confidence,
        )

    def walk_forward_probas(
        self, start: pd.Timestamp, end: pd.Timestamp, freq: str = "D"
    ) -> List[Tuple[pd.Timestamp, np.ndarray]]:
        """
        Generate walk-forward regime probabilities for validation.

        For each date in [start, end] at frequency freq:
        - Fit on data up to that date
        - Predict aligned probabilities for that date
        - Yield (date, probs) tuple

        This is for OOS validation only — each fit is strictly causal.

        Args:
            start: Start date (inclusive)
            end: End date (inclusive)
            freq: Date frequency (default 'D' for daily)

        Returns:
            List of (date, probability_array) tuples
        """
        price_data = self._load_price_data()
        if not price_data:
            return []

        # Get all available dates from SPY (primary ticker)
        spy_dates = price_data.get("SPY", pd.DataFrame()).index
        if len(spy_dates) == 0:
            return []

        # Generate date range
        date_range = pd.date_range(start=start, end=end, freq=freq)
        # Filter to dates that exist in our data
        valid_dates = [d for d in date_range if d in spy_dates]

        results = []
        for date in valid_dates:
            try:
                self.fit_expanding(date)
                probs = self.predict_proba_aligned(date)
                results.append((date, probs))
            except Exception:
                # Soft failure: return None probs, continue
                results.append((date, None))

        return results

    def soft_failure_response(self, as_of: pd.Timestamp) -> RegimeSnapshot:
        """Return a soft-failure snapshot (null probs, state=None, confidence=0)."""
        return RegimeSnapshot(
            date=as_of,
            state=-1,
            state_name="UNKNOWN",
            probabilities={label: 0.0 for label in SEMANTIC_LABELS},
            confidence=0.0,
        )
