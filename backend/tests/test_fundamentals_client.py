from unittest.mock import patch

from app.core.fundamentals_client import FinnhubClient

FAKE_FINNHUB_RESPONSE = {
    "metric": {
        "peExclExtraTTM": 28.5,
        "pbAnnual": 12.1,
        "roeTTM": 35.2,
        "roaTTM": 15.1,
        "totalDebt/totalEquityAnnual": 0.8,
        "currentDividendYieldTTM": 0.5,
        "epsGrowthTTMYoy": 12.3,
        "grossMarginTTM": 45.6,
        "currentRatioAnnual": 1.4,
        "assetTurnoverTTM": 0.7,
        # deliberadamente faltan ev_ebitda/fcf_yield/peg/book_value_growth,
        # para probar que los campos ausentes no rompen el mapeo
    }
}


def test_is_available_false_without_key():
    client = FinnhubClient(api_key="")
    assert client.is_available() is False
    assert client.get_fundamentals("AAPL") is None


def test_maps_known_fields_and_skips_missing(tmp_path):
    client = FinnhubClient(api_key="fake-key")
    with patch.object(client, "_fetch_raw", return_value=FAKE_FINNHUB_RESPONSE["metric"]):
        result = client.get_fundamentals("AAPL", use_cache=False)

    assert result is not None
    assert result["_data_source"] == "finnhub_live"
    assert result["pe_ratio"] == 28.5
    assert result["roe"] == 35.2
    assert "ev_ebitda" not in result  # no vino en la respuesta simulada, no debe inventarse


def test_returns_none_when_fetch_fails():
    client = FinnhubClient(api_key="fake-key")
    with patch.object(client, "_fetch_raw", return_value=None):
        assert client.get_fundamentals("AAPL", use_cache=False) is None


def test_returns_none_when_response_empty():
    client = FinnhubClient(api_key="fake-key")
    with patch.object(client, "_fetch_raw", return_value={}):
        assert client.get_fundamentals("AAPL", use_cache=False) is None
