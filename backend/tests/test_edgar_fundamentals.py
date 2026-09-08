"""Tests offline del adaptador EDGAR (XBRL companyfacts -> payload FMP-shaped).

NO toca red: usa el fixture tests/fixtures/edgar/edgar_companyfacts_aapl.json
y el cache de fundamentals_ingestion montado en tmp_path.

Verifica:
  - load_edgar_companyfacts (missing -> None, presente -> dict)
  - build_fmp_shaped_payload: forma FMP (3 listas de statements) con los
    nombres de campo canonicos que lee compute_scores, y totalDebt derivado.
  - compute_scores sobre el payload EDGAR: tribunales CALIDAD/SALUD (ROIC,
    ROE, Piotroski, Beneish, margenes) se computan; Altman Z queda None por
    falta de market cap (comportamiento documentado, no bug).
  - FundamentalsIngestion con edgar_dir: ingest_symbol siembra el cache con
    _data_source='edgar_primary' y screen_payload corre sin error.
"""
import json
import os
import shutil

import pytest

from app.core import edgar_fundamentals as ef
from app.core.fundamentals_ingestion import FundamentalsIngestion
from app.core.fundamentals_scores import compute_scores
from app.core.fundamentals_screen import screen_payload

FIXT_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "edgar")
FIXT = os.path.join(FIXT_DIR, "edgar_companyfacts_aapl.json")


def _facts():
    with open(FIXT) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# load_edgar_companyfacts
# ---------------------------------------------------------------------------
def test_load_missing_returns_none(tmp_path):
    assert ef.load_edgar_companyfacts("ZZZZ", tmp_path) is None


def test_load_present_returns_dict(tmp_path):
    shutil.copy(FIXT, tmp_path / "AAPL_companyfacts.json")
    facts = ef.load_edgar_companyfacts("AAPL", tmp_path)
    assert isinstance(facts, dict)
    assert facts["entityName"] == "Apple Inc."


# ---------------------------------------------------------------------------
# build_fmp_shaped_payload
# ---------------------------------------------------------------------------
def test_payload_shape_and_fields():
    payload = ef.build_fmp_shaped_payload("AAPL", _facts())
    assert payload is not None
    assert payload["_data_source"] == "edgar_primary"
    inc, bal, cf = payload["income_statement"], payload["balance_sheet"], payload["cash_flow"]
    assert len(inc) == 2 and len(bal) == 2 and len(cf) == 2
    # punto mas reciente primero (FY2023)
    assert inc[0]["calendarYear"] == "2023"

    # Campos income que lee compute_scores
    for f in ("revenue", "operatingIncome", "incomeBeforeTax", "incomeTaxExpense",
              "netIncome", "eps", "epsdiluted", "weightedAverageShsOutDil",
              "weightedAverageShsOut", "sharesOutstanding",
              "sellingGeneralAndAdministrativeExpense"):
        assert f in inc[0], f"falta campo income {f}"

    # Campos balance
    for f in ("totalAssets", "totalCurrentAssets", "cashAndCashEquivalents",
              "shortTermInvestments", "totalCurrentLiabilities", "longTermDebt",
              "longTermDebtCurrent", "shortTermBorrowings", "totalLiabilities",
              "totalShareholderEquity", "retainedEarnings",
              "propertyPlantEquipmentNet", "netReceivables"):
        assert f in bal[0], f"falta campo balance {f}"
    # totalDebt DERIVADO = LT + currentLT + ST borrowings
    row = bal[0]
    assert row["totalDebt"] == (row["longTermDebt"] + row["longTermDebtCurrent"]
                                + row["shortTermBorrowings"])

    # Campos cash
    for f in ("operatingCashFlow", "capitalExpenditure", "freeCashFlow",
              "commonStockRepurchased", "dividendsPaid",
              "depreciationAndAmortization"):
        assert f in cf[0], f"falta campo cash {f}"

    # Sin precio/market cap por diseno
    assert payload["profile"].get("marketCap") is None
    assert payload["price_target_consensus"] is None


def test_build_returns_none_when_no_tags(tmp_path):
    empty = {"entityName": "X", "facts": {"us-gaap": {}, "dei": {}}}
    assert ef.build_fmp_shaped_payload("X", empty) is None


# ---------------------------------------------------------------------------
# compute_scores sobre el payload EDGAR
# ---------------------------------------------------------------------------
def test_compute_scores_edgar_no_market_cap():
    payload = ef.build_fmp_shaped_payload("AAPL", _facts())
    scores = compute_scores(payload)
    assert isinstance(scores, dict)
    # Tribunales CALIDAD/SALUD: se computan integramente desde EDGAR.
    assert scores["piotroski_f_score"] is not None
    assert scores["beneish_m_score"] is not None
    # Dependientes de precio/market cap: None por diseno (documentado).
    assert scores["altman_z_score"] is None
    assert scores["ev_to_ebit"] is None


# ---------------------------------------------------------------------------
# Integracion: FundamentalsIngestion usa EDGAR como primario
# ---------------------------------------------------------------------------
def test_ingest_symbol_edgar_primary(tmp_path):
    edgar_dir = tmp_path / "edgar"
    cache_dir = tmp_path / "cache"
    edgar_dir.mkdir()
    shutil.copy(FIXT, edgar_dir / "AAPL_companyfacts.json")
    ing = FundamentalsIngestion(edgar_dir=str(edgar_dir), cache_dir=str(cache_dir))
    payload = ing.ingest_symbol("AAPL")
    assert payload is not None
    assert payload["_data_source"] == "edgar_primary"
    # cache escrito en disco
    assert (cache_dir / "AAPL.json").exists()


def test_ingest_symbol_missing_edgar_falls_through(tmp_path):
    # Sin archivo EDGAR y sin FMP (sin key): el adaptador no debe inventar nada.
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    ing = FundamentalsIngestion(edgar_dir=str(tmp_path), cache_dir=str(cache_dir))
    # Sin fixture y sin FMP key real => ingest_symbol debe devolver None
    # (comportamiento legacy preservado: EDGAR ausente => fallback FMP).
    assert ing.ingest_symbol("ZZZZ") is None


def test_screen_payload_runs_on_edgar_payload():
    payload = ef.build_fmp_shaped_payload("AAPL", _facts())
    result = screen_payload(payload)
    assert isinstance(result, dict)
    # Ratios crudos (CALIDAD/SALUD) computables desde EDGAR.
    for k in ("roic", "roe", "gross_margin", "roic_5y",
              "piotroski_f_score", "beneish_m_score"):
        assert k in result, f"falta {k}"
    assert result["roic"] is not None
    assert result["roe"] is not None
    assert result["gross_margin"] is not None
    assert result["piotroski_f_score"] is not None
    assert result["beneish_m_score"] is not None
    # Dependientes de precio: None por diseno (documentado, no bug).
    assert result["altman_z_score"] is None
    assert result["ev_to_ebit"] is None
