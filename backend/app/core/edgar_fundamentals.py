"""
Cargador de fundamentales point-in-time desde el panel EDGAR local.

Prefiere el panel diario construido por scripts/build_fundamentals_panel.py
(data/cache/fundamentals_panel.parquet): ratios con fecha de filing REAL
(EDGAR) y precio local del día de trading siguiente — sin lookahead.

Si el panel no existe o no cubre el símbolo/fecha, degrada al sample
hardcodeado (SAMPLE_FUNDAMENTALS) y lo marca explícitamente en
_data_source, igual que el flujo Finnhub.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

PANEL_PATH = os.environ.get(
    "FUNDAMENTALS_PANEL_PATH", "data/cache/fundamentals_panel.parquet"
)

SAMPLE_FUNDAMENTALS = {
    "AAPL": {"pe_ratio": 35.2, "pb_ratio": 55.3, "ev_ebitda": 24.5, "roe": 147.9, "roa": 31.6,
             "debt_equity": 1.75, "fcf_yield": 0.6, "div_yield": 0.4, "eps_growth": 8.2,
             "gross_margin": 46.2, "peg": 2.8, "current_ratio": 0.9,
             "asset_turnover": 1.1, "book_value_growth": 12.1, "sue_score": 1.2},
    "MSFT": {"pe_ratio": 36.8, "pb_ratio": 13.5, "ev_ebitda": 25.2, "roe": 44.1, "roa": 18.2,
             "debt_equity": 0.42, "fcf_yield": 2.3, "div_yield": 0.7, "eps_growth": 15.8,
             "gross_margin": 69.8, "peg": 2.3, "current_ratio": 1.3,
             "asset_turnover": 0.6, "book_value_growth": 9.8, "sue_score": 2.1},
    "NVDA": {"pe_ratio": 60.5, "pb_ratio": 45.2, "ev_ebitda": 40.1, "roe": 115.0, "roa": 65.4,
             "debt_equity": 0.25, "fcf_yield": 1.1, "div_yield": 0.03, "eps_growth": 89.3,
             "gross_margin": 75.8, "peg": 0.68, "current_ratio": 2.5,
             "asset_turnover": 0.9, "book_value_growth": 35.4, "sue_score": 3.5},
    "AMZN": {"pe_ratio": 38.9, "pb_ratio": 8.1, "ev_ebitda": 18.9, "roe": 22.3, "roa": 6.5,
             "debt_equity": 0.62, "fcf_yield": 0.8, "div_yield": 0.0, "eps_growth": 30.1,
             "gross_margin": 47.1, "peg": 1.3, "current_ratio": 1.0,
             "asset_turnover": 1.3, "book_value_growth": 20.5, "sue_score": 2.8},
    "GOOGL": {"pe_ratio": 26.1, "pb_ratio": 7.2, "ev_ebitda": 16.8, "roe": 30.5, "roa": 15.9,
              "debt_equity": 0.08, "fcf_yield": 3.2, "div_yield": 0.5, "eps_growth": 18.4,
              "gross_margin": 59.7, "peg": 1.4, "current_ratio": 2.2,
              "asset_turnover": 0.7, "book_value_growth": 13.2, "sue_score": 1.8},
    "SPY": {"pe_ratio": 26.5, "pb_ratio": 4.8, "ev_ebitda": 18.2, "roe": 19.8, "roa": 8.5,
            "debt_equity": 1.1, "fcf_yield": 2.5, "div_yield": 1.2, "eps_growth": 6.8,
            "gross_margin": 35.0, "peg": 3.9, "current_ratio": 1.0,
            "asset_turnover": 0.5, "book_value_growth": 5.8, "sue_score": 0.5},
}

RATIO_COLS = [
    "pe_ratio", "pb_ratio", "ev_ebitda", "roe", "roa", "debt_equity",
    "fcf_yield", "div_yield", "eps_growth", "gross_margin", "peg",
    "current_ratio", "asset_turnover", "book_value_growth", "sue_score",
]

# Especificaciones del blend de fundamentales del motor (_fundamental_signals
# en predictive_engine.py): (columna, lo, hi, dirección, peso, modo).
# sue_score EXCLUIDO pre-registrado (no derivable de EDGAR: requiere
# expectativas de consenso de analistas).
_FUND_SPECS = [
    ("pe_ratio", 5, 60, "invert", 0.12, "neg_eps"),
    ("pb_ratio", 0.5, 10, "invert", 0.12, "positive"),
    ("ev_ebitda", 3, 30, "invert", 0.08, "positive"),
    ("roe", -5, 30, "asis", 0.12, None),
    ("roa", -3, 15, "asis", 0.08, None),
    ("debt_equity", 0, 3, "invert", 0.10, None),
    ("fcf_yield", -2, 10, "asis", 0.12, None),
    ("div_yield", 0, 6, "asis", 0.06, None),
    ("eps_growth", -20, 50, "asis", 0.15, None),
    ("gross_margin", 10, 60, "asis", 0.12, None),
    ("peg", 0, 3, "invert", 0.05, "positive"),
    ("current_ratio", 0.5, 3, "asis", 0.04, None),
    ("asset_turnover", 0, 2, "asis", 0.04, None),
    ("book_value_growth", -10, 30, "asis", 0.04, "damp"),
]

_panel_cache: Optional[pd.DataFrame] = None


def _load_panel() -> Optional[pd.DataFrame]:
    global _panel_cache
    if _panel_cache is not None:
        return _panel_cache
    if not os.path.exists(PANEL_PATH):
        return None
    try:
        p = pd.read_parquet(PANEL_PATH)
        if p.index.names == ["date", "symbol"]:
            p = p.reset_index()
        p["date"] = pd.to_datetime(p["date"])
        p = p.sort_values("date")
        _panel_cache = p
        return p
    except Exception:
        return None


def compute_fundamental_score_series(
    panel: pd.DataFrame, symbol: str
) -> pd.Series:
    """Score fundamental continuo en [-1, +1] por día, replicando el blend
    de _fundamental_signals del motor predictivo (mismos pesos,
    normalizaciones y direcciones) sobre el panel point-in-time.

    - Fidelidad al motor: componente activo si el ratio existe y es != 0
      (equivalente al check `if f.get(col)` del motor con dicts EDGAR,
      donde NaN llega como None). sue_score no participa (pre-registrado).
    - Denominador por día = suma de pesos de componentes activos; sin
      componentes activos -> 0.0 (igual que el motor con dict vacío).
    """
    import numpy as np

    sub = panel[panel["symbol"] == symbol.upper()].set_index("date").sort_index()
    if sub.empty:
        return pd.Series(dtype=float)

    numer = pd.Series(0.0, index=sub.index)
    denom = pd.Series(0.0, index=sub.index)

    for col, lo, hi, direction, weight, mode in _FUND_SPECS:
        if col not in sub.columns:
            continue
        raw = sub[col].astype(float)
        active = raw.notna() & (raw != 0.0)
        normed = ((raw - lo) / (hi - lo) * 2 - 1).clip(-1, 1)

        if mode == "neg_eps":
            signal = pd.Series(
                np.where(raw > 0, -normed, np.where(raw < 0, -0.8, 0.0)),
                index=sub.index,
            )
        elif mode == "positive":
            signal = pd.Series(np.where(raw > 0, -normed, 0.0), index=sub.index)
        else:
            signal = normed.where(active, 0.0)
            if direction == "invert":
                signal = -signal
        if mode == "damp":
            signal = signal * 0.7

        numer = numer + signal.fillna(0.0) * weight
        denom = denom + active.astype(float) * weight

    score = numer.div(denom).fillna(0.0).clip(-1, 1)
    return score


def get_edgar_fundamentals(
    symbol: str, as_of: Optional[date] = None
) -> Optional[Dict]:
    """Ratios point-in-time del panel EDGAR para symbol en la fecha as_of
    (último día <= as_of). None si el panel no cubre el símbolo."""
    panel = _load_panel()
    if panel is None:
        return None
    symbol = symbol.upper()
    sub = panel[panel["symbol"] == symbol]
    if len(sub) == 0:
        return None
    if as_of is None:
        as_of = datetime.now().date()
    mask = sub["date"] <= pd.Timestamp(as_of)
    if not mask.any():
        return None
    row = sub.loc[mask].iloc[-1]
    out = {}
    for col in RATIO_COLS:
        v = row.get(col)
        out[col] = None if pd.isna(v) else float(v)
    return out


def get_fundamentals(
    symbol: str, as_of: Optional[date] = None
) -> Optional[Dict]:
    """Resolución: panel EDGAR -> sample hardcodeado (marcado)."""
    edgar = get_edgar_fundamentals(symbol, as_of)
    if edgar is not None:
        edgar["_data_source"] = "edgar_point_in_time"
        return edgar
    data = SAMPLE_FUNDAMENTALS.get(symbol.upper())
    if data is None:
        return None
    return {**data, "_data_source": "sample_hardcoded_not_live"}


# ============================================================================
# Adaptador XBRL companyfacts -> payload con FORMA FMP (ingesta quota-free)
# ============================================================================
# SEC EDGAR companyfacts (data.sec.gov/api/xbrl/companyfacts) NO tiene cuota y
# expone los estados financieros crudos point-in-time. Lo usamos como FUENTE
# PRIMARIA para sembrar el cache de FundamentalIngestion (ver
# fundamentals_ingestion.FundamentalsIngestion._ingest_edgar), desbloqueando el
# screening del universo 50 sin quemar la cuota 250/dia de FMP (free tier).
# FMP queda como secundaria / cross-check cuando falta el archivo EDGAR.
#
# El payload resultante emula EXACTAMENTE la forma que devuelve
# FundamentalsIngestion._ingest_live():
#   {symbol, ingested_at, income_statement:[{...}], balance_sheet:[{...}],
#    cash_flow:[{...}], profile:{...}, price_target_consensus:None,
#    _data_source:"edgar_primary"}
# para que screen_payload() / compute_scores() no noten la diferencia.
#
# LIMITACION DOCUMENTADA (honesta, no un bug): EDGAR no trae precio / market
# cap, asi que los indicadores dependientes de precio (P/E, FCF yield, EV/EBIT,
# upside, fair value, y el factor D del Altman Z) quedan None hasta enriquecer
# el profile (yfinance / FMP). Los tribunales de CALIDAD y SALUD (ROIC, ROE,
# Piotroski, Beneish, margenes) SI se computan integramente desde EDGAR.
#
# LIMITACION DE FORMULARIO ANUAL (documentada, no un bug):
# _collect_annual_points() toma SOLO los hechos con form que empieza por un
# prefijo anual (ver ANNUAL_FORM_PREFIXES = "10-K" domestico o "20-F" de foreign
# private issuer, ambos con sus enmiendas /A); los 10-Q (domestico) y 6-K
# (extranjero) son parciales de 3/6/9 meses y mezclarlos inflaria o duplicaria
# flujos anuales, por eso se excluyen a proposito. Consecuencia: un emisor cuyo
# companyfacts NO expone NINGUNA serie anual (ni 10-K ni 20-F) queda sin series
# anuales -> build_fmp_shaped_payload() devuelve None -> el simbolo NO se siembra
# desde EDGAR. Caso real verificado sobre el cache: XOM / Exxon Mobil, cuyo
# companyfacts trae SOLO 10-Q (n<=4 puntos, sin cierre anual): ningun parser de
# anuales puede cubrirlo, se resuelve enriqueciendo desde FMP como fallback o
# leyendo el filing completo (fuera del alcance del screening quota-free).
# Referencia: commits 9062307 y el soporte 20-F (CHKP) agregado 2026-09-09;
# SESSION_LOG 2026-09-09.
EDGAR_COMPANYFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cache", "edgar",
)


# Formulaciones ANUALES aceptadas para el corte "as originally reported" en
# _collect_annual_points(). startswith() cubre tambien las enmiendas (/A):
#   "10-K" -> anual domestico (10-K, 10-K/A)
#   "20-F" -> anual de foreign private issuer (20-F, 20-F/A): Check Point (CHKP),
#             emisor extranjero que NUNCA filed 10-K pero si expone sus cierres
#             anuales FY en 20-F con los mismos tags us-gaap.
# Se excluyen a proposito los parciales "10-Q" (domestico trimestral) y "6-K"
# (el equivalente extranjero del 10-Q): mezclarlos inflaria/duplicaria flujos
# anuales. Invariante de dominio: un emisor usa UN solo regimen (10-K o 20-F,
# nunca ambos), por eso anadir "20-F" no altera a los domesticos ya cubiertos
# -> riesgo de regresion cero sobre los simbolos que hoy funcionan con 10-K.
ANNUAL_FORM_PREFIXES: Tuple[str, ...] = ("10-K", "20-F")


# Cada campo FMP mapea a: (tags XBRL candidatos, unidad, tipo, statement)
#   unidad : "USD" o "shares"
#   tipo   : "flow"  (flujo, duracion -> punto anual 10-K)
#            "instant" (balance, snapshot a fecha end)
#   statement: "income" | "balance" | "cash"
EDGAR_MAP: Dict[str, Tuple[Tuple[str, ...], str, str, str]] = {
    # ----------------------------- income -----------------------------
    "revenue": (
        ("RevenueFromContractWithCustomerExcludingAssessedTax",
         "RevenueFromContractWithCustomerIncludingAssessedTax",
         "SalesRevenueNet", "Revenues"), "USD", "flow", "income"),
    "grossProfit": (("GrossProfit",), "USD", "flow", "income"),
    "operatingIncome": (("OperatingIncomeLoss",), "USD", "flow", "income"),
    "incomeBeforeTax": (
        ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterests",
         "IncomeLossFromContinuingOperationsBeforeIncomeTaxExpense"), "USD", "flow", "income"),
    "incomeTaxExpense": (("IncomeTaxExpenseBenefit",), "USD", "flow", "income"),
    "netIncome": (("NetIncomeLoss",), "USD", "flow", "income"),
    "epsdiluted": (("EarningsPerShareDiluted",), "USD", "flow", "income"),
    "eps": (("EarningsPerShareBasic",), "USD", "flow", "income"),
    "weightedAverageShsOutDil": (
        ("WeightedAverageNumberOfDilutedSharesOutstanding",), "shares", "flow", "income"),
    "weightedAverageShsOut": (
        ("WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
         "WeightedAverageNumberOfSharesOutstandingBasic"), "shares", "flow", "income"),
    "sharesOutstanding": (
        ("EntityCommonStockSharesOutstanding",), "shares", "instant", "income"),
    "sellingGeneralAndAdministrativeExpense": (
        ("SellingGeneralAndAdministrativeExpense",
         "GeneralAndAdministrativeExpense", "OperatingExpenses"), "USD", "flow", "income"),

    # ----------------------------- balance ----------------------------
    "totalAssets": (("Assets",), "USD", "instant", "balance"),
    "totalCurrentAssets": (("AssetsCurrent",), "USD", "instant", "balance"),
    "cashAndCashEquivalents": (
        ("CashAndCashEquivalentsAtCarryingValue",
         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"), "USD", "instant", "balance"),
    "shortTermInvestments": (("ShortTermInvestments",), "USD", "instant", "balance"),
    "totalCurrentLiabilities": (("LiabilitiesCurrent",), "USD", "instant", "balance"),
    "longTermDebt": (("LongTermDebtNoncurrent", "LongTermDebt"), "USD", "instant", "balance"),
    "longTermDebtCurrent": (
        ("LongTermDebtCurrent", "CurrentPortionOfLongTermDebt"), "USD", "instant", "balance"),
    "shortTermBorrowings": (
        ("ShortTermBorrowings", "CommercialPaper"), "USD", "instant", "balance"),
    "totalLiabilities": (("Liabilities",), "USD", "instant", "balance"),
    "totalShareholderEquity": (
        ("StockholdersEquity",
         "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        "USD", "instant", "balance"),
    "retainedEarnings": (
        ("RetainedEarnings", "RetainedEarningsAccumulatedDeficit"), "USD", "instant", "balance"),
    "propertyPlantEquipmentNet": (("PropertyPlantAndEquipmentNet",), "USD", "instant", "balance"),
    "netReceivables": (
        ("ReceivablesNetCurrent", "AccountsReceivableNetCurrent", "ReceivablesNet"),
        "USD", "instant", "balance"),

    # ------------------------------ cash ------------------------------
    "operatingCashFlow": (
        ("NetCashProvidedByUsedInOperatingActivities",
         "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
        "USD", "flow", "cash"),
    "capitalExpenditure": (
        ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
        "USD", "flow", "cash"),
    "freeCashFlow": (("FreeCashFlow",), "USD", "flow", "cash"),
    "commonStockRepurchased": (("PaymentsForRepurchaseOfCommonStock",), "USD", "flow", "cash"),
    "dividendsPaid": (
        ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"), "USD", "flow", "cash"),
    "depreciationAndAmortization": (
        ("DepreciationDepletionAndAmortization", "DepreciationAndAmortization"),
        "USD", "flow", "cash"),
}

# Componentes para derivar totalDebt (suma de lo presente).
_TOTAL_DEBT_PARTS = ("longTermDebt", "longTermDebtCurrent", "shortTermBorrowings")


def load_edgar_companyfacts(symbol: str, edgar_dir=None) -> Optional[Dict]:
    """Lee {SYMBOL}_companyfacts.json desde edgar_dir (default:
    data/cache/edgar). None si no existe/esta roto."""
    if edgar_dir is None:
        edgar_dir = EDGAR_COMPANYFACTS_DIR
    p = Path(edgar_dir) / f"{symbol.upper()}_companyfacts.json"
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def _collect_annual_points(tags: Tuple[str, ...], unit: str,
                           us_gaap: Dict, dei: Dict) -> List[Dict]:
    """Puntos anuales (form 10-K domestico o 20-F extranjero) de TODOS los tags
    candidatos, dedup por (start,end) conservando el ultimo `filed` (enmiendas
    ganan).

    Filtra a proposito SOLO por los prefijos anuales ANNUAL_FORM_PREFIXES
    ("10-K", "20-F"): los 10-Q y los 6-K son periodos parciales y contaminarian
    los flujos anuales. Por eso un emisor sin NINGUN hecho anual en su
    companyfacts (caso real: XOM, que solo expone 10-Q) produce lista vacia aca
    y, en cascada, build_fmp_shaped_payload() -> None. No es un error de parsing,
    es un limite del dato (ver LIMITACION DE FORMULARIO ANUAL arriba).
    """
    pts: List[Dict] = []
    for tag in tags:
        for src in (us_gaap, dei):
            node = src.get(tag)
            if not node:
                continue
            for u, vals in node.get("units", {}).items():
                if unit == "USD" and u != "USD":
                    continue
                if unit == "shares" and "shares" not in u.lower():
                    continue
                pts.extend(vals)
    annual = [p for p in pts if str(p.get("form", "")).startswith(ANNUAL_FORM_PREFIXES)]
    by_period: Dict[Tuple[Any, Any], Dict] = {}
    for p in annual:
        # Hechos instantaneos (ej. EntityCommonStockSharesOutstanding) vienen
        # sin `start` en EDGAR: usamos `end` como ancla de periodo.
        start = p.get("start") or p.get("end")
        end = p.get("end") or p.get("start")
        if start is None or end is None:
            continue
        key = (start, end)
        cur = by_period.get(key)
        if cur is None or (p.get("filed") or "") > (cur.get("filed") or ""):
            by_period[key] = p
    return list(by_period.values())


def _fiscal_year(p: Dict) -> Optional[int]:
    """Ano fiscal: prefiere `frame` (CY2023), luego fp=='FY'/'end'."""
    frame = (p.get("frame") or "").upper()
    if frame.startswith("CY"):
        try:
            return int(frame[2:])
        except ValueError:
            pass
    end = p.get("end")
    if end:
        try:
            return int(str(end)[:4])
        except ValueError:
            pass
    return None


def _annual_by_year(points: List[Dict]) -> Dict[int, float]:
    """{ano_fiscal: valor} conservando el ultimo filed por ano (desempate)."""
    best: Dict[int, Tuple[str, float]] = {}
    for p in points:
        yr = _fiscal_year(p)
        if yr is None or p.get("val") is None:
            continue
        f = p.get("filed") or ""
        if yr not in best or f > best[yr][0]:
            best[yr] = (f, float(p["val"]))
    return {yr: v for yr, (_, v) in best.items()}


def build_fmp_shaped_payload(symbol: str, facts: Dict,
                            limit: int = 6) -> Optional[Dict]:
    """Construye el payload estilo FMP desde companyfacts. None si no hay
    suficientes datos para armar las 3 listas de statements.

    None es el resultado ESPERADO para emisores cuyo companyfacts no expone
    NINGUNA serie anual (ni 10-K domestico ni 20-F extranjero), solo parciales
    10-Q/6-K (caso real verificado: XOM / Exxon Mobil). Ver la LIMITACION DE
    FORMULARIO ANUAL documentada arriba y SESSION_LOG 2026-09-09.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})

    series: Dict[str, Dict[int, float]] = {}
    for field, (tags, unit, _kind, _stmt) in EDGAR_MAP.items():
        pts = _collect_annual_points(tags, unit, us_gaap, dei)
        by_year = _annual_by_year(pts)
        if by_year:
            series[field] = by_year

    if not series:
        return None

    years = sorted({y for s in series.values() for y in s}, reverse=True)[:limit]
    if not years:
        return None

    def make_rows(fields: List[str]) -> List[Dict]:
        rows: List[Dict] = []
        for y in years:
            row: Dict[str, Any] = {"calendarYear": str(y), "period": "FY"}
            for f in fields:
                if f in series and y in series[f]:
                    row[f] = series[f][y]
            if len(row) > 2:  # calendarYear + period + >=1 campo real
                rows.append(row)
        return rows

    income = make_rows([f for f, (_t, _u, _k, s) in EDGAR_MAP.items() if s == "income"])
    balance = make_rows([f for f, (_t, _u, _k, s) in EDGAR_MAP.items() if s == "balance"])
    cash = make_rows([f for f, (_t, _u, _k, s) in EDGAR_MAP.items() if s == "cash"])

    # totalDebt derivado (suma de componentes presentes) en cada fila de balance.
    for row in balance:
        parts = [row[c] for c in _TOTAL_DEBT_PARTS if row.get(c) is not None]
        if parts:
            row["totalDebt"] = sum(parts)

    if not income or not balance or not cash:
        return None

    profile = {
        "companyName": facts.get("entityName") or symbol.upper(),
        "symbol": symbol.upper(),
    }
    return {
        "symbol": symbol.upper(),
        "ingested_at": None,  # lo setea el llamador (ingest_symbol)
        "income_statement": income,
        "balance_sheet": balance,
        "cash_flow": cash,
        "profile": profile,
        "price_target_consensus": None,
        "_data_source": "edgar_primary",
    }
