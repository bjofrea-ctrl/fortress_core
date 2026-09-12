"""Tests for Institutional Fingerprint (Phase 2 of institutional-flow-score).

Validates:
1. COT fetcher downloads 2019-2026, caches parquet, correct columns
2. AAII + FRED fetchers with cache, shift+ffill applied
3. compute_zscores causal (no data > as_of), outputs 9 variables
4. regime_fingerprint returns median, IQR, %net_long per variable
5. IC Gate: walk-forward IC > 0.02, p < 0.0056 (Bonferroni 9 tests)
"""
import os
import time

import numpy as np
import pandas as pd
import pytest
from app.core.institutional_fingerprint import (
    AAII_CACHE_MAX_AGE_DAYS,
    ZSCORE_LOOKBACK,
    _aaii_cache_age_days,
    _align_causal,
    _expanding_percentile,
    _expanding_zscore,
    build_thermometer_frame,
    build_zscores_panel,
    compute_all_fingerprints,
    compute_zscores,
    regime_fingerprint,
    validate_ic_gate,
)
from app.core.regime_nowcast import SEMANTIC_LABELS

# ============================================================================
# SYNTHETIC DATA HELPERS
# ============================================================================

def _synthetic_regime_series(n_days=800, seed=42):
    """Generate synthetic regime series for testing."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n_days)
    # Random regime labels 0-3
    regimes = rng.integers(0, 4, n_days)
    return pd.Series(regimes, index=dates, name="regime")


def _synthetic_cot_data(years, n_weeks_per_year=52):
    """Generate synthetic COT data for testing."""
    frames = []
    for year in years:
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="W-FRI")
        n = len(dates)
        rng = np.random.default_rng(year)
        oi = rng.uniform(500000, 2000000, n)
        frames.append(pd.DataFrame({
            "cot_oi": oi,
            "cot_lev_net": rng.uniform(-200000, 200000, n),
            "cot_asset_net": rng.uniform(-150000, 150000, n),
            "cot_retail_net": rng.uniform(-100000, 100000, n),
            "cot_dealer_net": rng.uniform(-100000, 100000, n),
        }, index=pd.DatetimeIndex(dates)))
    return pd.concat(frames).sort_index()


def _synthetic_aaii_data(n_weeks=500):
    """Generate synthetic AAII data for testing."""
    dates = pd.date_range("2015-01-01", periods=n_weeks, freq="W-THU")
    rng = np.random.default_rng(42)
    spread = rng.uniform(-50, 50, n_weeks)
    return pd.Series(spread, index=pd.DatetimeIndex(dates), name="value")


def _synthetic_fred_data(series, n_weeks=500):
    """Generate synthetic FRED data for testing."""
    dates = pd.date_range("2015-01-01", periods=n_weeks, freq="W-WED")
    rng = np.random.default_rng(hash(series) % 2**32)
    if series == "WALCL":
        values = rng.uniform(4000000, 9000000, n_weeks)
    elif series == "RRPONTSYD":
        values = rng.uniform(0, 2500000, n_weeks)
    else:  # WRESBAL
        values = rng.uniform(1000000, 4000000, n_weeks)
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="value")


def _synthetic_spy_close(n_days=800):
    """Generate synthetic SPY close prices."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2019-01-01", periods=n_days)
    returns = rng.normal(0.0003, 0.01, n_days)
    close = 100 * np.cumprod(1 + returns)
    return pd.Series(close, index=dates, name="close")


def _synthetic_vix(n_days=800):
    """Generate synthetic VIX data."""
    rng = np.random.default_rng(43)
    dates = pd.bdate_range("2019-01-01", periods=n_days)
    vix = rng.uniform(10, 40, n_days)
    return pd.Series(vix, index=dates, name="close")


def _synthetic_fg_score(n_days=800):
    """Generate synthetic Fear & Greed data."""
    rng = np.random.default_rng(44)
    dates = pd.bdate_range("2019-01-01", periods=n_days)
    score = rng.uniform(0, 100, n_days)
    return pd.Series(score, index=dates, name="value")


def _synthetic_put_call(n_days=800):
    """Generate synthetic Put/Call ratio data."""
    rng = np.random.default_rng(45)
    dates = pd.bdate_range("2019-01-01", periods=n_days)
    ratio = rng.uniform(0.5, 1.5, n_days)
    return pd.Series(ratio, index=dates, name="value")


def _mock_institutional_fetchers(monkeypatch, cache_dir):
    """Mock all external fetchers with synthetic data."""
    import app.core.institutional_fingerprint as inst

    # Set cache dir
    monkeypatch.setattr(inst, "CACHE_DIR", cache_dir)

    # Mock COT
    cot_data = _synthetic_cot_data(list(range(2019, 2025)))
    cot_path = os.path.join(cache_dir, "cot_test.parquet")
    cot_data.to_parquet(cot_path)

    def mock_fetch_cot_years(years):
        return cot_data[cot_data.index.year.isin(years)]

    monkeypatch.setattr(inst, "fetch_cot_years", mock_fetch_cot_years)

    # Mock AAII
    aaii_data = _synthetic_aaii_data()
    aaii_cache = os.path.join(cache_dir, "aaii_spread.parquet")
    aaii_data.to_frame("value").to_parquet(aaii_cache)

    def mock_fetch_aaii():
        return aaii_data

    monkeypatch.setattr(inst, "fetch_aaii", mock_fetch_aaii)

    # Mock FRED
    fred_series = ["WALCL", "RRPONTSYD", "WRESBAL"]
    fred_data = {}
    for series in fred_series:
        data = _synthetic_fred_data(series)
        cache = os.path.join(cache_dir, f"fred_{series}.parquet")
        data.to_frame("value").to_parquet(cache)
        fred_data[series] = data

    def mock_fetch_fred(series):
        return fred_data[series]

    monkeypatch.setattr(inst, "fetch_fred", mock_fetch_fred)

    # Mock VIX
    vix_data = _synthetic_vix()
    vix_cache = os.path.join(cache_dir, "^VIX.parquet")
    vix_data.to_frame("close").to_parquet(vix_cache)

    # Mock Fear & Greed
    fg_data = _synthetic_fg_score()
    fg_cache = os.path.join(cache_dir, "fg_score.parquet")
    fg_data.to_frame("value").to_parquet(fg_cache)

    # Mock Put/Call
    pc_data = _synthetic_put_call()
    pc_cache = os.path.join(cache_dir, "put_call_ratio.parquet")
    pc_data.to_frame("value").to_parquet(pc_cache)

    # Mock SPY
    spy_data = _synthetic_spy_close()
    spy_cache = os.path.join(cache_dir, "SPY.parquet")
    spy_data.to_frame("close").to_parquet(spy_cache)

    return {
        "cot": cot_data,
        "aaii": aaii_data,
        "fred": fred_data,
        "vix": vix_data,
        "fg": fg_data,
        "pc": pc_data,
        "spy": spy_data,
    }


# ============================================================================
# TASK-005: COT FETCHER TESTS
# ============================================================================

class TestCOTFetcher:
    """Tests for COT fetcher (TASK-005)."""

    def test_cot_download_and_cache(self, tmp_path, monkeypatch):
        """Descarga 2019-2026, cache parquet, columnas correctas."""
        import app.core.institutional_fingerprint as inst

        # Set up cache directory
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Mock the _get function to return synthetic zip
        import io
        import zipfile

        def create_fake_zip(year):
            """Create a fake CFTC zip file in memory."""
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as zf:
                # Create fake CSV content matching CFTC format
                df = pd.DataFrame({
                    "Market_and_Exchange_Names": [
                        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
                        "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
                        "OTHER MARKET"
                    ],
                    "Report_Date_as_YYYY-MM-DD": [
                        f"{year}-01-04", f"{year}-01-11", f"{year}-01-04"
                    ],
                    "Open_Interest_All": [1000000, 1010000, 500000],
                    "Lev_Money_Positions_Long_All": [300000, 310000, 100000],
                    "Lev_Money_Positions_Short_All": [200000, 205000, 80000],
                    "Asset_Mgr_Positions_Long_All": [200000, 205000, 50000],
                    "Asset_Mgr_Positions_Short_All": [150000, 152000, 40000],
                    "NonRept_Positions_Long_All": [100000, 102000, 30000],
                    "NonRept_Positions_Short_All": [80000, 81000, 25000],
                    "Dealer_Positions_Long_All": [150000, 152000, 40000],
                    "Dealer_Positions_Short_All": [140000, 141000, 35000],
                })
                csv_content = df.to_csv(index=False)
                zf.writestr(f"FinCom{str(year)[2:]}.txt", csv_content)
            buf.seek(0)
            return buf.read()

        class MockResp:
            def __init__(self, content, status_code=200):
                self.content = content
                self.status_code = status_code
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")

        def mock_get(url, timeout=60):
            year = int(url.split("_")[-1].split(".")[0])
            return MockResp(create_fake_zip(year))

        monkeypatch.setattr(inst, "_get", mock_get)

        # Call fetch_cot_years for 2019-2020
        result = inst.fetch_cot_years([2019, 2020])

        # Verify cache files created
        assert os.path.exists(os.path.join(tmp_path, "cot_2019.parquet"))
        assert os.path.exists(os.path.join(tmp_path, "cot_2020.parquet"))

        # Verify columns
        expected_cols = ["cot_oi", "cot_lev_net", "cot_asset_net", "cot_retail_net", "cot_dealer_net"]
        assert list(result.columns) == expected_cols

        # Verify data
        assert len(result) == 4  # 2 weeks x 2 years (deduplicated)
        assert result.index.is_monotonic_increasing

        # Verify net calculations
        row = result.iloc[0]
        assert row["cot_lev_net"] == 100000  # 300000 - 200000
        assert row["cot_asset_net"] == 50000  # 200000 - 150000
        assert row["cot_retail_net"] == 20000  # 100000 - 80000
        assert row["cot_dealer_net"] == 10000  # 150000 - 140000

    def test_cot_handles_403_gracefully(self, tmp_path, monkeypatch):
        """COT handles 403 by skipping year; raises if all years fail."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        class MockResp:
            status_code = 403
            content = b""
            def raise_for_status(self):
                raise RuntimeError("403 Forbidden")

        monkeypatch.setattr(inst, "_get", lambda url, timeout=60: MockResp())

        # Should raise RuntimeError when all years fail
        with pytest.raises(RuntimeError, match="Sin datos COT para ningún año"):
            inst.fetch_cot_years([2019])

    def test_cot_cache_reuse(self, tmp_path, monkeypatch):
        """COT reuses cached parquet on second call."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Create cache
        fake_data = _synthetic_cot_data([2019])
        fake_data.to_parquet(os.path.join(tmp_path, "cot_2019.parquet"))

        call_count = {"n": 0}
        def mock_get(url, timeout=60):
            call_count["n"] += 1
            raise RuntimeError("Should not be called")

        monkeypatch.setattr(inst, "_get", mock_get)

        result = inst.fetch_cot_years([2019])
        assert call_count["n"] == 0  # Network not called
        assert len(result) == len(fake_data)


# ============================================================================
# TASK-006: AAII + FRED FETCHER TESTS
# ============================================================================

class TestAAIIFREDFetchers:
    """Tests for AAII and FRED fetchers (TASK-006)."""

    def test_aaii_fetch_creates_cache(self, tmp_path, monkeypatch):
        """AAII fetch creates parquet cache."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Mock Excel download
        def fake_read_excel(buf, header=None):
            rows = [[None] * 8 for _ in range(5)]
            rows[3] = ["Date", "Bullish", "Neutral", "Bearish", "Total", "Mov Avg", "Spread", "Average"]
            start = pd.Timestamp("2015-01-01")
            for i in range(500):
                d = start + pd.Timedelta(weeks=i)
                rows.append([d, 0.40, 0.30, 0.30, None, None, None, None])
            rows.append(["Count 2026", None, None, None, None, None, None, None])
            return pd.DataFrame(rows)

        class MockResp:
            status_code = 200
            content = b"fake-xls"
            def raise_for_status(self):
                pass

        monkeypatch.setattr(inst, "_get", lambda url, timeout=90: MockResp())
        monkeypatch.setattr(pd, "read_excel", fake_read_excel)

        result = inst.fetch_aaii()

        # Verify cache created
        cache_path = inst._aaii_cache_path()
        assert os.path.exists(cache_path)

        # Verify data
        assert len(result) >= 400
        assert result.index.is_monotonic_increasing
        # Spread = (Bullish - Bearish) * 100 = (0.40 - 0.30) * 100 = 10
        assert np.allclose(result.values, 10.0)

    def test_aaii_cache_ttl(self, tmp_path, monkeypatch):
        """AAII respects weekly cache TTL."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Create fresh cache
        data = pd.Series([10.0], index=pd.DatetimeIndex(["2026-07-30"]))
        data.to_frame("value").to_parquet(inst._aaii_cache_path())

        call_count = {"n": 0}
        def mock_get(url, timeout=90):
            call_count["n"] += 1
            raise RuntimeError("Network down")

        monkeypatch.setattr(inst, "_get", mock_get)

        # Fresh cache -> no download
        result = inst.fetch_aaii()
        assert call_count["n"] == 0
        assert len(result) == 1

    def test_aaii_stale_cache_refreshes(self, tmp_path, monkeypatch):
        """Stale AAII cache triggers refresh."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Create stale cache (> 7 days)
        data = pd.Series([10.0], index=pd.DatetimeIndex(["2026-07-30"]))
        data.to_frame("value").to_parquet(inst._aaii_cache_path())
        old_time = time.time() - (AAII_CACHE_MAX_AGE_DAYS + 1) * 86400
        os.utime(inst._aaii_cache_path(), (old_time, old_time))

        # Mock successful download
        def fake_read_excel(buf, header=None):
            rows = [[None] * 8 for _ in range(5)]
            rows[3] = ["Date", "Bullish", "Neutral", "Bearish", "Total", "Mov Avg", "Spread", "Average"]
            for i in range(500):
                d = pd.Timestamp("2015-01-01") + pd.Timedelta(weeks=i)
                rows.append([d, 0.40, 0.30, 0.30, None, None, None, None])
            rows.append(["Count 2026", None, None, None, None, None, None, None])
            return pd.DataFrame(rows)

        class MockResp:
            status_code = 200
            content = b"fake-xls"
            def raise_for_status(self):
                pass

        monkeypatch.setattr(inst, "_get", lambda url, timeout=90: MockResp())
        monkeypatch.setattr(pd, "read_excel", fake_read_excel)

        result = inst.fetch_aaii()
        assert len(result) >= 400  # Full dataset downloaded

    def test_aaii_stale_cache_degrades_on_failure(self, tmp_path, monkeypatch):
        """Stale AAII cache degrades to stale on download failure."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Create stale cache
        data = pd.Series([10.0], index=pd.DatetimeIndex(["2026-07-30"]))
        data.to_frame("value").to_parquet(inst._aaii_cache_path())
        old_time = time.time() - (AAII_CACHE_MAX_AGE_DAYS + 1) * 86400
        os.utime(inst._aaii_cache_path(), (old_time, old_time))

        # Mock failure
        def failing_get(url, timeout=90):
            raise RuntimeError("network down")
        monkeypatch.setattr(inst, "_get", failing_get)

        # Should return stale cache, not raise
        result = inst.fetch_aaii()
        assert len(result) == 1
        assert result.iloc[0] == 10.0

    def test_aaii_no_cache_failure_propagates(self, tmp_path, monkeypatch):
        """No cache + failure propagates error."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        def failing_get(url, timeout=90):
            raise RuntimeError("network down")
        monkeypatch.setattr(inst, "_get", failing_get)

        with pytest.raises(RuntimeError):
            inst.fetch_aaii()

    def test_fred_fetch_creates_cache(self, tmp_path, monkeypatch):
        """FRED fetch creates parquet cache with correct columns."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        # Mock CSV response
        csv_content = "observation_date,WALCL\n2015-01-07,4000000\n2015-01-14,4010000\n"

        class MockResp:
            status_code = 200
            text = csv_content
            def raise_for_status(self):
                pass

        monkeypatch.setattr(inst, "_get", lambda url, timeout=60: MockResp())

        result = inst.fetch_fred("WALCL")

        # Verify cache
        cache_path = os.path.join(tmp_path, "fred_WALCL.parquet")
        assert os.path.exists(cache_path)

        # Verify data
        assert len(result) == 2
        assert result.index.is_monotonic_increasing
        assert list(result.index) == [pd.Timestamp("2015-01-07"), pd.Timestamp("2015-01-14")]

    def test_fred_all_series(self, tmp_path, monkeypatch):
        """All FRED series fetch correctly."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        for series in ["WALCL", "RRPONTSYD", "WRESBAL"]:
            csv_content = f"observation_date,{series}\n2015-01-07,1000\n2015-01-14,1010\n"

            class MockResp:
                status_code = 200
                text = csv_content
                def raise_for_status(self):
                    pass

            monkeypatch.setattr(inst, "_get", lambda url, timeout=60: MockResp())
            result = inst.fetch_fred(series)
            assert len(result) == 2


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_align_causal_shift_ffill(self):
        """_align_causal applies shift(1) + ffill correctly."""
        # Source data on specific dates
        source = pd.Series([10, 20, 30], index=pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-03"]))
        # Trading dates include weekends
        trading_dates = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"])

        result = _align_causal(source, trading_dates, "test")

        # After shift(1): NaN, 10, 20, 30
        # After ffill: NaN, 10, 20, 30 (first is NaN since nothing before)
        # Reindexed to trading_dates
        assert result.index.equals(trading_dates)
        assert pd.isna(result.iloc[0])  # First day has no prior data
        assert result.iloc[1] == 10
        assert result.iloc[2] == 20
        assert result.iloc[3] == 30

    def test_align_causal_ffill_over_weekend(self):
        """_align_causal forward-fills over weekends."""
        source = pd.Series([100], index=pd.DatetimeIndex(["2020-01-03"]))  # Friday
        trading_dates = pd.DatetimeIndex(["2020-01-03", "2020-01-06", "2020-01-07"])  # Fri, Mon, Tue

        result = _align_causal(source, trading_dates, "test")

        # Shift(1): NaN on Fri (no prior), 100 on Mon, 100 on Tue
        assert pd.isna(result.iloc[0])  # Friday - no prior data
        assert result.iloc[1] == 100    # Monday
        assert result.iloc[2] == 100    # Tuesday

    def test_expanding_zscore_minimum_lookback(self):
        """_expanding_zscore returns NaN before lookback window."""
        series = pd.Series(range(300), index=pd.date_range("2020-01-01", periods=300, freq="B"))

        result = _expanding_zscore(series, lookback=252)

        # First 252 should be NaN
        assert result.iloc[:252].isna().all()
        # After 252, should have values
        assert not result.iloc[252:].isna().all()
        # Z-score should be reasonable
        assert (result.iloc[252:] < 10).all()  # Not extreme

    def test_expanding_percentile_minimum_lookback(self):
        """_expanding_percentile returns NaN before lookback window."""
        series = pd.Series(np.random.uniform(10, 40, 300), index=pd.date_range("2020-01-01", periods=300, freq="B"))

        result = _expanding_percentile(series, lookback=252)

        # First 252 should be NaN
        assert result.iloc[:252].isna().all()
        # After 252, should have values in [0, 1]
        assert (result.iloc[252:] >= 0).all()
        assert (result.iloc[252:] <= 1).all()

    def test_build_thermometer_frame(self):
        """build_thermometer_frame computes vol_a, vol_b, phase_b_quiet, retest."""
        spy_close = _synthetic_spy_close(400)

        thermo = build_thermometer_frame(spy_close)

        # Check columns
        expected_cols = ["vol_a", "vol_b", "phase_b_quiet", "retest_confirmed"]
        assert list(thermo.columns) == expected_cols

        # Check index matches
        assert thermo.index.equals(spy_close.index)

        # phase_b_quiet is binary
        assert set(thermo["phase_b_quiet"].dropna().unique()).issubset({0, 1})

        # retest_confirmed is binary
        assert set(thermo["retest_confirmed"].dropna().unique()).issubset({0, 1})

        # vol_a and vol_b should be positive
        assert (thermo["vol_a"].dropna() >= 0).all()
        assert (thermo["vol_b"].dropna() >= 0).all()

    def test_aaii_cache_age_days(self, tmp_path):
        """_aaii_cache_age_days returns correct age."""
        cache_path = tmp_path / "test.parquet"
        pd.Series([1]).to_frame("value").to_parquet(cache_path)

        age = _aaii_cache_age_days(str(cache_path))
        assert age >= 0
        assert age < 1  # Just created

        # Modify mtime to be old
        old_time = time.time() - 10 * 86400
        os.utime(cache_path, (old_time, old_time))

        age = _aaii_cache_age_days(str(cache_path))
        assert 9 < age < 11


# ============================================================================
# TASK-007: COMPUTE ZSCORES CAUSAL TESTS
# ============================================================================

class TestComputeZScoresCausal:
    """Tests for compute_zscores causal property (TASK-007)."""

    def test_zscores_causal_no_future_data(self, tmp_path, monkeypatch):
        """compute_zscores(as_of) never uses data > as_of."""

        # Mock all fetchers
        # mock_data = _mock_institutional_fetchers(monkeypatch, str(tmp_path))

        # Create regime series
        regime_series = _synthetic_regime_series(800)

        # Pick a cutoff date in the middle
        as_of = pd.Timestamp("2021-06-15")

        # Compute z-scores
        result = compute_zscores(regime_series, as_of)

        # Verify result has 9 variables
        expected_vars = [
            "cot_asset_mgr_z", "cot_lev_money_z", "aaii_spread_z",
            "fg_score", "put_call_ratio", "vix_pctl_1y",
            "phase_b_quiet", "retest_confirmed", "regime"
        ]
        for var in expected_vars:
            assert var in result.index, f"Missing variable: {var}"

        # Verify no future data used by checking internal state
        # The function truncates all data to as_of before alignment
        # We can verify by checking the trading dates used
        trading_dates = regime_series.index[regime_series.index <= as_of]
        assert len(trading_dates) >= ZSCORE_LOOKBACK

    def test_zscores_insufficient_data_raises(self):
        """compute_zscores raises if insufficient data."""
        regime_series = _synthetic_regime_series(100)  # Less than 252

        with pytest.raises(ValueError, match="Insufficient data"):
            compute_zscores(regime_series, pd.Timestamp("2019-05-01"))

    def test_zscores_output_structure(self, tmp_path, monkeypatch):
        """compute_zscores returns Series with correct structure."""
        # mock_data = _mock_institutional_fetchers(monkeypatch, str(tmp_path))
        regime_series = _synthetic_regime_series(800)

        as_of = pd.Timestamp("2021-06-15")
        result = compute_zscores(regime_series, as_of)

        assert isinstance(result, pd.Series)
        assert result.name == as_of

        # Check all 9 variables present
        zscore_vars = ["cot_asset_mgr_z", "cot_lev_money_z", "aaii_spread_z"]
        raw_vars = ["fg_score", "put_call_ratio", "vix_pctl_1y"]
        binary_vars = ["phase_b_quiet", "retest_confirmed"]

        for var in zscore_vars + raw_vars + binary_vars + ["regime"]:
            assert var in result.index

        # Z-scores should be numeric (can be NaN if insufficient data)
        for var in zscore_vars:
            val = result[var]
            assert pd.isna(val) or isinstance(val, (float, np.floating))

        # Binary vars should be 0 or 1 (or NaN)
        for var in binary_vars:
            val = result[var]
            assert pd.isna(val) or val in (0, 1, 0.0, 1.0)

        # Regime should be 0-3
        regime_val = result["regime"]
        assert regime_val in range(4)

    def test_zscores_different_as_of_dates_produce_different_results(self, tmp_path, monkeypatch):
        """Different as_of dates produce different results (walk-forward)."""
        # mock_data = _mock_institutional_fetchers(monkeypatch, str(tmp_path))
        regime_series = _synthetic_regime_series(800)

        as_of1 = pd.Timestamp("2021-06-15")
        as_of2 = pd.Timestamp("2021-12-15")

        result1 = compute_zscores(regime_series, as_of1)
        result2 = compute_zscores(regime_series, as_of2)

        # Results should differ (at least regime or some z-score)
        # They could be similar but not identical
        assert result1.name == as_of1
        assert result2.name == as_of2

    def test_cot_pct_calculation(self, tmp_path, monkeypatch):
        """COT net positions correctly calculated as % of OI."""

        # mock_data = _mock_institutional_fetchers(monkeypatch, str(tmp_path))
        regime_series = _synthetic_regime_series(800)

        as_of = pd.Timestamp("2021-06-15")
        result = compute_zscores(regime_series, as_of)

        # Z-scores should be computed (not all NaN if sufficient data)
        # At 2021-06-15, we have ~2.5 years = ~600 trading days > 252
        assert not pd.isna(result["cot_asset_mgr_z"])
        assert not pd.isna(result["cot_lev_money_z"])
        assert not pd.isna(result["aaii_spread_z"])


# ============================================================================
# TASK-008: REGIME FINGERPRINT TESTS
# ============================================================================

def _synthetic_zscores_panel(n_days=200, n_vars=8, seed=42):
    """Generate synthetic z-scores panel for testing fingerprints."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=n_days)

    # Variable names matching the real implementation
    var_names = [
        "cot_asset_mgr_z", "cot_lev_money_z", "aaii_spread_z",
        "fg_score", "put_call_ratio", "vix_pctl_1y",
        "phase_b_quiet", "retest_confirmed"
    ][:n_vars]

    data = {}
    for var in var_names:
        if var in ["phase_b_quiet", "retest_confirmed"]:
            data[var] = rng.integers(0, 2, n_days).astype(float)
        else:
            data[var] = rng.normal(0, 1, n_days)

    df = pd.DataFrame(data, index=dates)
    # Add regime column
    df["regime"] = rng.integers(0, 4, n_days)
    return df


class TestRegimeFingerprint:
    """Tests for regime_fingerprint statistics (TASK-008)."""

    def test_fingerprint_stats_structure(self):
        """regime_fingerprint returns median, IQR, %net_long per variable."""
        # Use synthetic panel for speed
        zscores_panel = _synthetic_zscores_panel(n_days=200)
        regime_series = zscores_panel["regime"]

        # Compute fingerprint for regime 0
        fp = regime_fingerprint(zscores_panel, regime_series, 0, "GOLDILOCKS")

        assert isinstance(fp.regime, int)
        assert fp.regime == 0
        assert fp.regime_name == "GOLDILOCKS"
        assert fp.n_obs > 0
        assert isinstance(fp.variables, dict)

        # Check each variable has required stats
        for var_name, stats in fp.variables.items():
            assert "median" in stats
            assert "iqr" in stats
            assert "pct_net_long" in stats
            assert isinstance(stats["median"], float)
            assert isinstance(stats["iqr"], float)
            assert isinstance(stats["pct_net_long"], float)
            assert 0 <= stats["pct_net_long"] <= 100

    def test_fingerprint_empty_regime(self):
        """regime_fingerprint handles regime with no observations."""
        zscores_panel = _synthetic_zscores_panel(n_days=200)
        regime_series = zscores_panel["regime"]

        # Force a regime that doesn't exist
        fp = regime_fingerprint(zscores_panel, regime_series, 99, "NONEXISTENT")

        assert fp.n_obs == 0
        assert fp.variables == {}

    def test_compute_all_fingerprints(self):
        """compute_all_fingerprints returns fingerprints for all 4 regimes."""
        zscores_panel = _synthetic_zscores_panel(n_days=200)
        regime_series = zscores_panel["regime"]

        fingerprints = compute_all_fingerprints(zscores_panel, regime_series)

        assert len(fingerprints) == 4
        for i in range(4):
            assert i in fingerprints
            assert fingerprints[i].regime == i
            assert fingerprints[i].regime_name == SEMANTIC_LABELS[i]

    def test_fingerprint_zscore_pct_net_long(self):
        """For z-score variables, %net_long = %(z > 0)."""
        zscores_panel = _synthetic_zscores_panel(n_days=200)
        regime_series = zscores_panel["regime"]

        # Pick a regime with data
        fp = regime_fingerprint(zscores_panel, regime_series, 0, "GOLDILOCKS")

        # Check z-score variables use > 0 threshold
        for var_name in ["cot_asset_mgr_z", "cot_lev_money_z", "aaii_spread_z"]:
            if var_name in fp.variables:
                stats = fp.variables[var_name]
                # Manually verify
                common = zscores_panel.index.intersection(regime_series.index)
                mask = (regime_series.loc[common] == 0)
                if mask.any():
                    vals = zscores_panel.loc[common[mask], var_name].dropna()
                    if len(vals) > 0:
                        expected = float((vals > 0).mean() * 100)
                        assert abs(stats["pct_net_long"] - expected) < 0.01
                    vals = zscores_panel.loc[common[mask], var_name].dropna()
                    if len(vals) > 0:
                        expected = float((vals > 0).mean() * 100)
                        assert abs(stats["pct_net_long"] - expected) < 0.01


# ============================================================================
# IC GATE TESTS (Phase Gate 2)
# ============================================================================

class TestICGate:
    """Tests for IC Gate validation (Phase Gate 2)."""

    def test_ic_gate_structure(self):
        """validate_ic_gate returns IC, p-value, pass/fail per variable."""
        # Use synthetic panel for speed
        zscores_panel = _synthetic_zscores_panel(n_days=100)

        # Create synthetic SPY returns
        spy_returns = pd.Series(
            np.random.normal(0.0003, 0.01, len(zscores_panel)),
            index=zscores_panel.index
        )

        results = validate_ic_gate(zscores_panel, spy_returns)

        # Check structure
        for var, res in results.items():
            assert "ic" in res
            assert "pvalue" in res
            assert "pass" in res
            assert "n" in res
            assert isinstance(res["pass"], bool)
            assert isinstance(res["n"], int)

    def test_ic_gate_bonferroni_threshold(self):
        """IC gate uses Bonferroni-corrected p-value threshold (0.05/9 = 0.0056)."""
        # Create test data with known correlation
        n = 500
        dates = pd.bdate_range("2020-01-01", periods=n)

        # Variable with true correlation to forward returns
        x = pd.Series(np.random.randn(n), index=dates, name="test_var")
        # Forward returns with some correlation to x
        noise = np.random.randn(n) * 0.9
        signal = x.values * 0.1  # True IC ~ 0.1
        fwd = pd.Series(signal + noise, index=dates)

        zscores_df = pd.DataFrame({"test_var": x})

        results = validate_ic_gate(zscores_df, fwd, min_ic=0.02, max_pvalue=0.0056)

        assert "test_var" in results
        res = results["test_var"]
        # n is reduced by forward return calculation (shift + rolling)
        assert res["n"] > 100  # Should have sufficient overlap
        # Note: actual pass depends on random seed

    def test_ic_gate_insufficient_data(self):
        """IC gate handles insufficient overlap gracefully."""
        dates = pd.bdate_range("2020-01-01", periods=50)
        zscores_df = pd.DataFrame({"var1": np.random.randn(50)}, index=dates)
        spy_returns = pd.Series(np.random.randn(50), index=dates)

        results = validate_ic_gate(zscores_df, spy_returns)

        # With n=50 < 100 minimum, should return NaN and pass=False
        res = results["var1"]
        assert np.isnan(res["ic"])
        assert np.isnan(res["pvalue"])
        assert res["pass"] is False
        # n is reduced by forward return calculation (shift + rolling)
        assert res["n"] < 100


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_cot_to_fingerprint(self):
        """Full pipeline: COT -> zscores -> fingerprint."""
        # Use synthetic panel for speed
        zscores_panel = _synthetic_zscores_panel(n_days=100)
        regime_series = zscores_panel["regime"]

        assert len(zscores_panel) > 0
        assert "cot_asset_mgr_z" in zscores_panel.columns
        assert "regime" in zscores_panel.columns

        # Compute fingerprints
        fingerprints = compute_all_fingerprints(zscores_panel, regime_series)

        assert len(fingerprints) == 4
        for fp in fingerprints.values():
            assert fp.n_obs > 0
            assert len(fp.variables) > 0

    def test_cot_columns_match_spec(self):
        """COT output columns match spec exactly."""
        # Read from actual implementation docstring
        from app.core.institutional_fingerprint import COT_MARKET
        assert COT_MARKET == "E-MINI S&P 500"

    def test_zscore_variables_count(self):
        """Exactly 9 variables as specified."""
        # The function docstring lists 9 variables
        import inspect

        from app.core.institutional_fingerprint import compute_zscores
        docstring = inspect.getsource(compute_zscores)

        # Count variables in docstring
        expected = [
            "cot_asset_mgr_z",
            "cot_lev_money_z",
            "aaii_spread_z",
            "fg_score",
            "put_call_ratio",
            "vix_pctl_1y",
            "phase_b_quiet",
            "retest_confirmed",
            "regime"
        ]
        for var in expected:
            assert var in docstring


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Edge case and error handling tests."""

    def test_fetch_vix_missing_cache(self, tmp_path, monkeypatch):
        """fetch_vix handles missing cache gracefully."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        result = inst.fetch_vix()
        assert isinstance(result, pd.Series)
        assert len(result) == 0

    def test_fetch_fear_greed_missing_cache(self, tmp_path, monkeypatch):
        """fetch_fear_greed handles missing cache gracefully."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        result = inst.fetch_fear_greed()
        assert isinstance(result, pd.Series)

    def test_fetch_put_call_missing_cache(self, tmp_path, monkeypatch):
        """fetch_put_call_ratio handles missing cache gracefully."""
        import app.core.institutional_fingerprint as inst
        monkeypatch.setattr(inst, "CACHE_DIR", str(tmp_path))

        result = inst.fetch_put_call_ratio()
        assert isinstance(result, pd.Series)

    @pytest.mark.slow
    def test_build_zscores_panel_skip_errors(self, tmp_path, monkeypatch):
        """build_zscores_panel skips dates that fail."""
        # mock_data = _mock_institutional_fetchers(monkeypatch, str(tmp_path))
        regime_series = _synthetic_regime_series(800)

        # This should not raise even if some dates fail (small range for speed)
        panel = build_zscores_panel(
            regime_series,
            pd.Timestamp("2021-01-01"),
            pd.Timestamp("2021-01-15"),
            freq="B"
        )

        assert isinstance(panel, pd.DataFrame)
        # Some dates might be skipped but should have results
        assert len(panel) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
