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


class _InertFmp:
    """FMP sin key: is_available False — sin red real en los tests de ingest."""

    api_key = None
    base_url = ""

    def is_available(self):
        return False


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
# Formulario ANUAL aceptado: 10-K (domestico) y 20-F (foreign private issuer).
# El filtro vive en _collect_annual_points via ANNUAL_FORM_PREFIXES. Se prueban
# ambos por parametrizacion sobre un companyfacts sintetico con un cierre FY
# completo (income+balance+cash), sin tocar red.
# ---------------------------------------------------------------------------
def _annual_facts(form):
    """Companyfacts sintetico con un unico cierre anual (FY2023) bajo `form`.

    Suficiente para que build_fmp_shaped_payload() arme las 3 listas SI el form
    es anual; debe devolver None si el form es un parcial (10-Q/6-K)."""
    def node(val, start=None):
        e = {"val": val, "end": "2023-12-31", "form": form, "fp": "FY", "fy": 2023,
             "filed": "2024-02-15"}
        if start:
            e["start"] = start
        return e
    return {
        "entityName": "Foreign Issuer Inc",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax":
                    {"units": {"USD": [node(500.0, "2023-01-01")]}},
                "NetIncomeLoss": {"units": {"USD": [node(111.0, "2023-01-01")]}},
                "Assets": {"units": {"USD": [node(1000.0)]}},
                "Liabilities": {"units": {"USD": [node(400.0)]}},
                "StockholdersEquity": {"units": {"USD": [node(600.0)]}},
                "NetCashProvidedByUsedInOperatingActivities":
                    {"units": {"USD": [node(222.0, "2023-01-01")]}},
            },
            "dei": {},
        },
    }


@pytest.mark.parametrize("form", ["10-K", "10-K/A", "20-F", "20-F/A"])
def test_annual_forms_are_collected(form):
    payload = ef.build_fmp_shaped_payload("FI", _annual_facts(form))
    assert payload is not None, f"{form} debe tratarse como cierre anual"
    assert payload["_data_source"] == "edgar_primary"
    inc, bal, cf = (payload["income_statement"], payload["balance_sheet"],
                    payload["cash_flow"])
    assert inc and bal and cf, "las 3 listas de statements deben armarse"
    assert inc[0]["revenue"] == 500.0
    assert inc[0]["netIncome"] == 111.0
    assert bal[0]["totalAssets"] == 1000.0
    assert bal[0]["totalShareholderEquity"] == 600.0
    assert cf[0]["operatingCashFlow"] == 222.0


@pytest.mark.parametrize("form", ["10-Q", "10-Q1", "6-K", "8-K"])
def test_partial_forms_are_rejected(form):
    # Un parcial (10-Q domestico / 6-K extranjero / 8-K corriente) NO constituye
    # serie anual -> build devuelve None. Protege el filtro ANNUAL_FORM_PREFIXES
    # contra regresiones (p. ej. aceptar 6-K contaminaria flujos anuales).
    assert ef.build_fmp_shaped_payload("FI", _annual_facts(form)) is None


def test_foreign_issuer_20f_no_longer_requires_fmp():
    # Regresion especifica del universo: CHKP (Check Point) archiva 20-F y JAMAS
    # 10-K; antes del soporte 20-F caia a FMP (ingestion_returned_none bajo
    # rate-limit). Verifica que un 20-F con los tags us-gaap de CHKP produce
    # payload EDGAR sin necesidad de red.
    payload = ef.build_fmp_shaped_payload("CHKP", _annual_facts("20-F"))
    assert payload is not None
    assert payload["balance_sheet"][0]["totalLiabilities"] == 400.0


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
    ing = FundamentalsIngestion(fmp=_InertFmp(), edgar_dir=str(edgar_dir), cache_dir=str(cache_dir))
    payload = ing.ingest_symbol("AAPL")
    assert payload is not None
    assert payload["_data_source"] == "edgar_primary"
    assert payload["income_statement"] and payload["balance_sheet"] and payload["cash_flow"]
    # Sin FMP (key/key apagada): el backfill de foto no corre y el payload EDGAR
    # conserva su stub; el símbolo NO se descarta por eso (criterio A3).
    assert (payload.get("profile") or {}).get("price") is None
    assert ing.last_fmp_calls == 0
    # cache escrito en disco
    assert (cache_dir / "AAPL.json").exists()


def test_ingest_symbol_missing_edgar_falls_through(tmp_path):
    # Sin archivo EDGAR y sin FMP (sin key): el adaptador no debe inventar nada.
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    ing = FundamentalsIngestion(fmp=_InertFmp(), edgar_dir=str(tmp_path), cache_dir=str(cache_dir))
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


# ---------------------------------------------------------------------------
# Backoff/retry del fetcher de SEC (fetch_edgar_universe_facts.py). Offline:
# se monkeypincha _http_get, nunca toca red. Regresion del bug 2026-09-09: el
# loop anterior tragaba HTTPError 429/503 como `fail` SIN reintentar (caso ACN),
# dejando el cache EDGAR incompleto y obligando al screen a caer a FMP.
# ---------------------------------------------------------------------------
import importlib.util
import urllib.error
from http.client import HTTPMessage
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "fetch_edgar_universe_facts",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "fetch_edgar_universe_facts.py"),
)
fef = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fef)


def _http_error(code, retry_after=None):
    err = urllib.error.HTTPError("http://x", code, "throttled", HTTPMessage(), None)
    err.headers = {"Retry-After": retry_after} if retry_after else {}
    return err


def _load(monkeypatch):
    def fake(url):
        raise AssertionError("no debe tocar red en tests")
    monkeypatch.setattr(fef, "_http_get", fake)
    # acelerar cualquier sleep
    monkeypatch.setattr(fef, "_backoff_seconds", lambda a, r=None: 0.0)
    return fef


def test_fetch_reintenta_429_503_hasta_exito(tmp_path, monkeypatch):
    _load(monkeypatch)
    import gzip as _gz
    seq = [_http_error(429), _http_error(503),
           _gz.compress(b'{"cik": 1, "us-gaap": {}}')]
    calls = {"n": 0}
    def flaky(url):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        r = seq[i]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(fef, "_http_get", flaky)
    out = tmp_path / "ACME_companyfacts.json"
    assert fef.fetch("0000000001", out) is True
    assert calls["n"] == 3               # 2 throttleos + 1 exito
    assert out.exists() and not os.path.exists(str(out) + ".part"), "no debe quedar parcial"
    assert json.loads(out.read_text())["cik"] == 1


def test_fetch_agota_reintentos_sin_dejar_archivo(tmp_path, monkeypatch):
    _load(monkeypatch)
    monkeypatch.setattr(fef, "SEC_MAX_RETRIES", 4)
    calls = {"n": 0}
    def always429(url):
        calls["n"] += 1
        raise _http_error(429)
    monkeypatch.setattr(fef, "_http_get", always429)
    out = tmp_path / "ACME_companyfacts.json"
    assert fef.fetch("1", out) is False
    assert calls["n"] == 5               # 4 reintentos + intento inicial
    assert not out.exists()              # nunca se escribe un parcial


def test_fetch_no_reintenta_404(tmp_path, monkeypatch):
    _load(monkeypatch)
    calls = {"n": 0}
    def only404(url):
        calls["n"] += 1
        raise _http_error(404)
    monkeypatch.setattr(fef, "_http_get", only404)
    assert fef.fetch("1", tmp_path / "ACME_companyfacts.json") is False
    assert calls["n"] == 1               # 4xx no transitorio: falla ya


def test_backoff_respeta_retry_after_y_tope(monkeypatch):
    monkeypatch.setattr(fef, "SEC_BASE_BACKOFF", 1.0)
    monkeypatch.setattr(fef, "SEC_MAX_BACKOFF", 30.0)
    # jitter determinista (=1.0) => valores predecibles sin depender del azar
    monkeypatch.setattr(fef, "random", type("R", (), {"uniform": staticmethod(lambda a, b: 1.0)})())
    assert fef._backoff_seconds(0, "12") == 13.0         # Retry-After 12 + jitter 1.0
    assert fef._backoff_seconds(0, "999") == 30.0        # Retry-After topa en MAX
    assert fef._backoff_seconds(10) == 30.0              # crece pero topa en MAX
    assert fef._backoff_seconds(1) == 2.0                # base * 2**attempt * 1.0



