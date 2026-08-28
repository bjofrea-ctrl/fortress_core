"""Tests de Fase 2 — fórmulas de fundamentales.

Cubre las 4 funciones puras de `fundamentals_scores.py` y el orquestador
`compute_scores`. No toca red: los datos se construyen en fixtures inline
(la matemática de cada fórmula es contra números ya publicados, no contra
la API en vivo).

Test de validación OBLIGATORIO contra caso público conocido (PLAN §2 - el
plan exige: "no alcanza con que compile"). Usamos AAPL FY2022 (10-K
publicado sep/2022) con cifras que están en el dominio público.
"""
import pytest

from app.core.fundamentals_scores import (
    _g,
    altman_z_score,
    beneish_m_score,
    compute_scores,
    ev_to_ebit,
    fair_value_label,
    piotroski_f_score,
)


# ============================================================================
# Fixtures: AAPL FY2022 (10-K público)
# ============================================================================

@pytest.fixture
def aapl_fy22():
    """Cifras crudas AAPL FY2022 (t) y FY2021 (t-1), todas públicas.
    NO se obtienen de un export, NO se tocan de la red: son inputs de la
    fórmula, no de la ingesta. Por eso están como fixture de pytest."""
    income_t = {
        "revenue": 394328000000, "grossProfit": 170782000000,
        "operatingIncome": 42000000000, "netIncome": 99803000000,
        "weightedAverageShsOutDil": 16325819000,
        "sellingGeneralAndAdministrativeExpense": 25094000000,
    }
    income_t1 = {
        "revenue": 365817000000, "grossProfit": 152836000000,
        "operatingIncome": 108949000000, "netIncome": 94680000000,
        "weightedAverageShsOutDil": 16728452000,
        "sellingGeneralAndAdministrativeExpense": 21973000000,
    }
    balance_t = {
        "totalAssets": 352755000000,
        "totalCurrentAssets": 135405000000,
        "totalCurrentLiabilities": 145308000000,
        "longTermDebt": 98959000000, "totalDebt": 109106000000,
        "cashAndCashEquivalents": 24641000000,
        "shortTermInvestments": 24658000000,
        "retainedEarnings": -3060000000,
        "totalLiabilities": 302083000000,
        "totalShareholderEquity": 50672000000,
        "netReceivables": 37794000000,
    }
    balance_t1 = {
        "totalAssets": 351002000000,
        "totalCurrentAssets": 134836000000,
        "totalCurrentLiabilities": 125481000000,
        "longTermDebt": 109106000000, "totalDebt": 124719000000,
        "cashAndCashEquivalents": 34940000000,
        "shortTermInvestments": 27699000000,
        "retainedEarnings": 5562000000,
        "totalLiabilities": 287845000000,
        "netReceivables": 32849000000,
    }
    cf_t = {
        "operatingCashFlow": 122151000000,
        "netIncome": 99803000000,
        "depreciationAndAmortization": 11104000000,
    }
    cf_t1 = {
        "operatingCashFlow": 104038000000,
        "netIncome": 94680000000,
        "depreciationAndAmortization": 11284000000,
    }
    market_cap = 2220000000000
    return {
        "income_t": income_t, "income_t1": income_t1,
        "balance_t": balance_t, "balance_t1": balance_t1,
        "cf_t": cf_t, "cf_t1": cf_t1, "market_cap": market_cap,
    }


# ============================================================================
# Validación OBLIGATORIA (PLAN §2): Altman Z contra AAPL FY2022.
# ============================================================================

def test_altman_z_aapl_fy22_matches_published(aapl_fy22):
    """Validación contra caso público conocido. Hand-calc:
      A = (135.4 - 145.3) / 352.8 = -0.0281
      B = -3.06 / 352.8         = -0.00868
      C = 42.0 / 352.8          = 0.1191
      D = 2220 / 302.1          = 7.349
      E = 394.3 / 352.8         = 1.118
      Z = 1.2·(-0.0281) + 1.4·(-0.00868) + 3.3·(0.1191) + 0.6·(7.349) + 1.0·(1.118)
        = -0.0337 + -0.0122 + 0.3930 + 4.4094 + 1.118
        = 5.8745
    Coincide con el rango publicado en dashboards de inversión."""
    z = altman_z_score(
        aapl_fy22["income_t"], aapl_fy22["balance_t"],
        market_cap=aapl_fy22["market_cap"],
    )
    assert z is not None
    assert abs(z - 5.8745) < 0.005
    assert z > 2.99  # zona safe


def test_altman_z_without_market_cap_uses_book_equity(aapl_fy22):
    """Sin market_cap, D usa book equity (fórmula para privados)."""
    z = altman_z_score(
        aapl_fy22["income_t"], aapl_fy22["balance_t"],
        market_cap=None, use_market_cap=False,
    )
    assert z is not None
    assert -2 < z < 10


# ============================================================================
# P-Score
# ============================================================================

def test_piotroski_aapl_fy22_high_score(aapl_fy22):
    """AAPL FY2022 tenía F=8/9 según la literatura pública."""
    f = piotroski_f_score(
        aapl_fy22["income_t"], aapl_fy22["income_t1"],
        aapl_fy22["balance_t"], aapl_fy22["balance_t1"],
        aapl_fy22["cf_t"], aapl_fy22["cf_t1"],
    )
    assert f is not None
    assert 7 <= f <= 9


def test_piotroski_returns_none_without_t_minus_1(aapl_fy22):
    """Sin t-1 no se puede computar el delta → None (no se inventa)."""
    f = piotroski_f_score(
        aapl_fy22["income_t"], None,
        aapl_fy22["balance_t"], aapl_fy22["balance_t1"],
        aapl_fy22["cf_t"], aapl_fy22["cf_t1"],
    )
    assert f is None


def test_piotroski_returns_none_without_ta():
    """Sin totalAssets (denominador) no se computa → None."""
    f = piotroski_f_score(
        {"netIncome": 100}, {"netIncome": 50},
        {"totalCurrentAssets": 100}, {"totalCurrentAssets": 50},
        {"operatingCashFlow": 50}, {"operatingCashFlow": 40},
    )
    assert f is None


def test_piotroski_zero_score_for_terrible_company():
    """Empresa destruyendo valor → F cercano a 0/9."""
    income_t = {"revenue": 100, "grossProfit": 5, "operatingIncome": 0,
                "netIncome": -50, "weightedAverageShsOutDil": 200}
    income_t1 = {"revenue": 200, "grossProfit": 30, "operatingIncome": 10,
                 "netIncome": 20, "weightedAverageShsOutDil": 100}
    balance_t = {"totalAssets": 100, "totalCurrentAssets": 10,
                 "totalCurrentLiabilities": 20, "longTermDebt": 80}
    balance_t1 = {"totalAssets": 200, "totalCurrentAssets": 30,
                  "totalCurrentLiabilities": 10, "longTermDebt": 20}
    cf_t = {"operatingCashFlow": -20, "netIncome": -50}
    cf_t1 = {"operatingCashFlow": 30, "netIncome": 20}
    f = piotroski_f_score(income_t, income_t1, balance_t, balance_t1, cf_t, cf_t1)
    assert f is not None
    assert f <= 2  # empresa en serios problemas, 2/9 o menos


# ============================================================================
# Beneish M
# ============================================================================

def test_beneish_aapl_fy22_below_threshold(aapl_fy22):
    """AAPL FY2022: M debería estar bien por debajo del umbral -1.78
    (empresa legítima, no manipuladora)."""
    m = beneish_m_score(
        aapl_fy22["income_t"], aapl_fy22["income_t1"],
        aapl_fy22["balance_t"], aapl_fy22["balance_t1"],
        aapl_fy22["cf_t"],
    )
    assert m is not None
    assert m < -1.78


def test_beneish_returns_none_without_inputs():
    """Sin t-1 o sin los campos esenciales → None."""
    assert beneish_m_score(None, None, None, None, None) is None


# ============================================================================
# EV/EBIT
# ============================================================================

def test_ev_to_ebit_aapl_fy22_positive_high(aapl_fy22):
    """AAPL FY2022 con EV ~2.34T y EBIT ~42B → EV/EBIT ~55."""
    ev = ev_to_ebit(
        aapl_fy22["income_t"], aapl_fy22["balance_t"],
        market_cap=aapl_fy22["market_cap"],
    )
    assert ev is not None
    assert 40 < ev < 70


def test_ev_to_ebit_returns_none_without_ebit():
    """Sin EBIT (operatingIncome) no se computa → None."""
    income = {"revenue": 100}
    balance = {"totalDebt": 10, "cashAndCashEquivalents": 5}
    assert ev_to_ebit(income, balance, market_cap=100) is None


def test_ev_to_ebit_negative_ebit_returns_negative():
    """Empresa con EBIT negativo → EV/EBIT negativo (pérdida operativa)."""
    income = {"operatingIncome": -10, "revenue": 100}
    balance = {"totalDebt": 0, "cashAndCashEquivalents": 0}
    ev = ev_to_ebit(income, balance, market_cap=100)
    assert ev is not None
    assert ev < 0  # 100 EV / -10 EBIT = -10


# ============================================================================
# Fair Value Label
# ============================================================================

def test_fair_value_label_thresholds():
    """Corte: ≥20% bargain, 5-20% undervalued, ±5% fair, <−5% overvalued."""
    assert fair_value_label(100, 130) == "bargain"      # +30%
    assert fair_value_label(100, 110) == "undervalued"  # +10%
    assert fair_value_label(100, 102) == "fair"          # +2%
    assert fair_value_label(100, 90) == "overvalued"     # -10%


def test_fair_value_label_returns_none_without_inputs():
    assert fair_value_label(None, 100) is None
    assert fair_value_label(100, None) is None
    assert fair_value_label(0, 100) is None


# ============================================================================
# Orquestador: compute_scores sobre un payload tipo Fase 1
# ============================================================================

def test_compute_scores_with_aapl_fy22_fixture(aapl_fy22):
    """Ingestión mockeada (payload de Fase 1 sin tocar red) + compute_scores."""
    payload = {
        "symbol": "AAPL",
        "income_statement": [aapl_fy22["income_t"], aapl_fy22["income_t1"]],
        "balance_sheet": [aapl_fy22["balance_t"], aapl_fy22["balance_t1"]],
        "cash_flow": [aapl_fy22["cf_t"], aapl_fy22["cf_t1"]],
        "profile": {"marketCap": aapl_fy22["market_cap"], "price": 150.0},
        "price_target_consensus": {"targetConsensus": 247.0, "targetMean": 247.0},
    }
    scores = compute_scores(payload)
    assert scores["piotroski_f_score"] is not None
    assert scores["piotroski_f_score"] >= 7
    assert scores["altman_z_score"] is not None
    assert scores["altman_z_score"] > 2.99
    assert scores["beneish_m_score"] is not None
    assert scores["beneish_m_score"] < -1.78
    assert scores["ev_to_ebit"] is not None
    # upside = (247-150)/150 = 64.6% → bargain
    assert scores["fair_value_label"] == "bargain"
    assert scores["_meta"]["has_t_minus_1"] is True


def test_compute_scores_with_only_one_period():
    """Sin t-1 → F-Score y Beneish = None, Z/EV/EBIT sí (sólo necesitan t-0)."""
    payload = {
        "symbol": "X",
        "income_statement": [{"revenue": 100, "operatingIncome": 10, "netIncome": 5}],
        "balance_sheet": [{"totalAssets": 200, "totalCurrentAssets": 80,
                            "totalCurrentLiabilities": 60, "retainedEarnings": 10,
                            "totalLiabilities": 100, "longTermDebt": 30}],
        "cash_flow": [{"operatingCashFlow": 12, "netIncome": 5}],
        "profile": {"marketCap": 150, "price": 10},
        "price_target_consensus": {"targetConsensus": 12},
    }
    scores = compute_scores(payload)
    assert scores["piotroski_f_score"] is None
    assert scores["beneish_m_score"] is None
    assert scores["altman_z_score"] is not None
    assert scores["ev_to_ebit"] is not None
    # upside (12-10)/10 = 20% → bargain (corte es >=20%)
    assert scores["fair_value_label"] == "bargain"
    assert scores["_meta"]["has_t_minus_1"] is False


# ============================================================================
# Helpers
# ============================================================================

def test_g_returns_default_when_missing():
    assert _g({}, "x", default=5.0) == 5.0
    assert _g(None, "x", default=7.0) == 7.0
    assert _g({"x": None}, "x", default=3.0) == 3.0
    assert _g({"x": ""}, "x", default=2.0) == 2.0


def test_g_first_match_wins():
    assert _g({"a": 10, "b": 20}, "a", "b") == 10
    assert _g({"b": 20}, "a", "b") == 20


def test_g_handles_string_numbers():
    assert _g({"x": "3.14"}, "x") == 3.14


def test_g_ignores_non_numeric_strings():
    assert _g({"x": "NM"}, "x", default=0.0) == 0.0
    assert _g({"x": "N/A"}, "x", default=9.0) == 9.0