"""
Cálculo de puntajes fundamentales — Motor de fundamentales automatizado.

Reimplementa con código propio las 4 fórmulas que el motor canónico de AAI
(~/claude/skills/aai-screening-acciones/scripts/motor_screening.py) toma COMO
DADAS de InvestingPro: Piotroski F-Score (2000), Altman Z-Score (1968),
Beneish M-Score (1999) y EV/EBIT, más una versión propia de Fair Value Label
basada en upside vs consenso de analistas. La estrategia del proyecto es
reconstruir las fórmulas sobre los estados financieros crudos que baja Fase 1
(FMP / Finnhub), no scraping de una plataforma paga.

Fidelidad al motor canónico: las funciones son PURAS, sin I/O. Reciben
estructuras de datos tipadas (un periodo de income/balance/cash flow) y
devuelven números. La interpretación contra umbrales, los 3 tribunales
(calidad / salud / precio) y los baldes finales se arman en Fase 3 sobre
esta superficie — no acá.

Validadciones obligatorias antes de dar Fase 2 por cerrada (PLAN
§2 - test de validación):
- cada fórmula corre contra un caso público conocido y se compara número
  exacto contra cifra ya publicada. No alcanza con que "compile".
- FMP devuelve listas con varios periodos: la convención es t-0 (más reciente)
  y t-1 (el anterior). Las funciones que necesitan comparar 2 periodos
  reciben ambos explícitamente para no asumir nada.
"""

from typing import Any, Dict, Optional

# ============================================================================
# Helpers de extracción robusta de campos FMP
# ============================================================================
# FMP devuelve dicts por periodo con nombres que varian entre endpoints y
# versiones; los helpers toman el primer valor presente en la lista de
# candidatos (mismos nombres canónicos de FMP, ordenados por probabilidad).

def _g(d: Optional[Dict], *keys: str, default: float = 0.0) -> float:
    """Lee la primera clave presente en d; None/'' o valor no numérico → default."""
    if not d:
        return default
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return default


# ============================================================================
# PIOTROSKI F-SCORE (Piotroski 2000)
# ============================================================================
# 9 señales binarias (0/1) sobre cambios t-0 vs t-1 en rentabilidad, solidez
# y eficiencia operativa. Sobre el motor canónico de AAI es uno de los 3
# scores del TRIBUNAL SALUD: ≥7 cuenta como señal; ≤3 marca alerta.

def piotroski_f_score(
    income: Optional[Dict],
    income_prev: Optional[Dict],
    balance: Optional[Dict],
    balance_prev: Optional[Dict],
    cash_flow: Optional[Dict],
    cash_flow_prev: Optional[Dict],
) -> Optional[int]:
    """Devuelve el F-Score (0-9) o None si no hay datos suficientes.

    Las 9 señales (paper original):
      1. ROA positivo (NI_t / TA_t)                          (rentabilidad)
      2. CFO positivo (CFO_t > 0)                           (rentabilidad)
      3. ΔROA > 0 (ROA_t - ROA_t-1)                         (rentabilidad)
      4. Accrual: CFO_t > NI_t                              (calidad earnings)
      5. ΔLeverage ≤ 0 (longTermDebt/TA baja o igual)       (solidez)
      6. ΔLiquidity > 0 (Current Ratio sube)                (solidez)
      7. No equity issuance (shares dil no suben)           (solidez)
      8. ΔGross Margin > 0 (GM_t - GM_t-1)                  (eficiencia)
      9. ΔAsset Turnover > 0 (Sales_t/TA_t - Sales_t-1/TA_t-1) (eficiencia)
    """
    if not income or not balance or not cash_flow:
        return None
    if not income_prev or not balance_prev or not cash_flow_prev:
        return None

    ta_t = _g(balance, "totalAssets")
    ta_t1 = _g(balance_prev, "totalAssets")
    if ta_t <= 0 or ta_t1 <= 0:
        return None

    ni_t = _g(income, "netIncome")
    ni_t1 = _g(income_prev, "netIncome")
    cfo_t = _g(cash_flow, "operatingCashFlow")

    # 1) ROA positivo
    s1 = 1 if ni_t / ta_t > 0 else 0
    # 2) CFO positivo
    s2 = 1 if cfo_t > 0 else 0
    # 3) ΔROA > 0
    s3 = 1 if (ni_t / ta_t) > (ni_t1 / ta_t1) else 0
    # 4) Accrual: CFO > NI (ganancias de calidad)
    s4 = 1 if cfo_t > ni_t else 0

    # 5) ΔLeverage ≤ 0 (deuda/activos baja o estable)
    debt_t = _g(balance, "longTermDebt", "totalDebt")
    debt_t1 = _g(balance_prev, "longTermDebt", "totalDebt")
    lev_t = debt_t / ta_t
    lev_t1 = debt_t1 / ta_t1
    s5 = 1 if lev_t <= lev_t1 else 0

    # 6) ΔLiquidity > 0 (current ratio sube)
    cur_t = _g(balance, "totalCurrentAssets") / max(_g(balance, "totalCurrentLiabilities"), 1e-9)
    cur_t1 = _g(balance_prev, "totalCurrentAssets") / max(_g(balance_prev, "totalCurrentLiabilities"), 1e-9)
    s6 = 1 if cur_t > cur_t1 else 0

    # 7) No equity issuance (shares dil no suben)
    sh_t = _g(income, "weightedAverageShsOutDil", "weightedAverageShsOut", "sharesOutstanding")
    sh_t1 = _g(income_prev, "weightedAverageShsOutDil", "weightedAverageShsOut", "sharesOutstanding")
    s7 = 1 if sh_t <= sh_t1 else 0

    # 8) ΔGross Margin > 0
    rev_t = _g(income, "revenue")
    rev_t1 = _g(income_prev, "revenue")
    gp_t = _g(income, "grossProfit")
    gp_t1 = _g(income_prev, "grossProfit")
    gm_t = gp_t / rev_t if rev_t else 0
    gm_t1 = gp_t1 / rev_t1 if rev_t1 else 0
    s8 = 1 if gm_t > gm_t1 else 0

    # 9) ΔAsset Turnover > 0
    at_t = rev_t / ta_t
    at_t1 = rev_t1 / ta_t1
    s9 = 1 if at_t > at_t1 else 0

    return s1 + s2 + s3 + s4 + s5 + s6 + s7 + s8 + s9


# ============================================================================
# ALTMAN Z-SCORE (Altman 1968)
# ============================================================================
# Fórmula original para empresas manufactureras privadas (no financieras):
#   Z = 1.2·A + 1.4·B + 3.3·C + 0.6·D + 1.0·E
#   A = Working Capital / Total Assets
#   B = Retained Earnings / Total Assets
#   C = EBIT / Total Assets
#   D = Market Cap / Total Liabilities
#   E = Sales / Total Assets
# Zonas canónicas: >2.99 = "safe", 1.81-2.99 = "grey", <1.81 = "distress".
# (Variantes Z' para privados y Z'' para no-manufactureras existen pero el
# motor canónico de AAI trabaja con la fórmula original.)
# El motor de AAI usa la zona <1.81 como "salud DÉBIL automática".

def altman_z_score(
    income: Optional[Dict],
    balance: Optional[Dict],
    market_cap: Optional[float] = None,
    use_market_cap: bool = True,
) -> Optional[float]:
    """Devuelve el Z-Score o None si falta algún insumo esencial.

    `market_cap` es la capitalización de mercado al cierre (no book value).
    `use_market_cap=False` usa total liabilities (libro) en D, que es la
    fórmula para empresas SIN cotización pública. Default True (caso AAI).
    """
    if not income or not balance:
        return None

    ta = _g(balance, "totalAssets")
    if ta <= 0:
        return None

    # A: Working Capital / TA
    ca = _g(balance, "totalCurrentAssets")
    cl = _g(balance, "totalCurrentLiabilities")
    wc = ca - cl
    a = wc / ta

    # B: Retained Earnings / TA
    re = _g(balance, "retainedEarnings")
    b = re / ta

    # C: EBIT / TA  (FMP: operatingIncome = EBIT, en algunos nombres)
    ebit = _g(income, "operatingIncome", "ebit", "ebitda")
    c = ebit / ta

    # D: Market cap (default) o TL (sin cotización) / TL
    tl = _g(balance, "totalLiabilities")
    if tl <= 0:
        return None
    if use_market_cap:
        if market_cap is None or market_cap <= 0:
            return None
        d = market_cap / tl
    else:
        book_eq = _g(balance, "totalShareholderEquity")
        if book_eq <= 0:
            return None
        d = book_eq / tl

    # E: Sales / TA
    sales = _g(income, "revenue")
    e = sales / ta

    return 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e

# ============================================================================
# BENEISH M-SCORE (Beneish 1999)
# ============================================================================
# Detector de manipulación contable con 8 variables. Corte estándar: M ≤ -1.78
# = "no manipulador" (señal de salud en el motor de AAI); M > -1.78 = alerta.
#   DSRI = (Receivables_t/Sales_t) / (Receivables_t-1/Sales_t-1)
#   GMI  = GrossMargin_t-1 / GrossMargin_t  (>1 = margen cae = alerta)
#   AQ   = (1 - (CA_t+Cash_t)/TA_t) / (1 - (CA_t-1+Cash_t-1)/TA_t-1)
#   SGI  = Sales_t / Sales_t-1
#   DEPI = (Depreciation_t-1 / (Depreciation_t-1+PPE_t-1)) /
#          (Depreciation_t / (Depreciation_t+PPE_t))
#   SGAI = (SGA_t/Sales_t) / (SGA_t-1/Sales_t-1)
#   LVGI = Leverage_t / Leverage_t-1
#   TATA = (NI_t - CFO_t) / TA_t
# M = -4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQ + 0.892·SGI
#       + 0.115·DEPI - 0.172·SGAI + 4.679·TATA - 0.327·LVGI

def beneish_m_score(
    income: Optional[Dict],
    income_prev: Optional[Dict],
    balance: Optional[Dict],
    balance_prev: Optional[Dict],
    cash_flow: Optional[Dict],
) -> Optional[float]:
    """Devuelve el M-Score o None si faltan datos para alguna variable."""
    if not income or not income_prev or not balance or not balance_prev or not cash_flow:
        return None

    ta_t = _g(balance, "totalAssets")
    ta_t1 = _g(balance_prev, "totalAssets")
    if ta_t <= 0 or ta_t1 <= 0:
        return None

    sales_t = _g(income, "revenue")
    sales_t1 = _g(income_prev, "revenue")
    if sales_t1 <= 0:
        return None

    # DSRI
    rec_t = _g(balance, "netReceivables", "totalReceivables")
    rec_t1 = _g(balance_prev, "netReceivables", "totalReceivables")
    dsri = (rec_t / sales_t) / (rec_t1 / sales_t1) if rec_t1 > 0 else 1.0

    # GMI (>1 = margen cae = alerta)
    gp_t = _g(income, "grossProfit")
    gp_t1 = _g(income_prev, "grossProfit")
    gm_t = gp_t / sales_t
    gm_t1 = gp_t1 / sales_t1
    if gm_t <= 0:
        return None
    gmi = gm_t1 / gm_t

    # AQ (Asset Quality)
    ca_t = _g(balance, "totalCurrentAssets")
    ca_t1 = _g(balance_prev, "totalCurrentAssets")
    cash_t = _g(balance, "cashAndCashEquivalents", "cashAndShortTermInvestments")
    cash_t1 = _g(balance_prev, "cashAndCashEquivalents", "cashAndShortTermInvestments")
    aq_t = 1.0 - (ca_t + cash_t) / ta_t
    aq_t1 = 1.0 - (ca_t1 + cash_t1) / ta_t1
    aq = aq_t / aq_t1 if aq_t1 != 0 else 1.0

    # SGI (Sales Growth Index)
    sgi = sales_t / sales_t1

    # DEPI (Depreciation Index) — si no hay PPE, lo dejamos en 1 (neutro)
    dep_t = _g(cash_flow, "depreciationAndAmortization")
    dep_t1 = _g(cash_flow, "depreciationAndAmortization", default=0)  # idealmente prev CF
    ppe_t = _g(balance, "propertyPlantEquipmentNet", "propertyPlantAndEquipmentNet", "netPPE")
    ppe_t1 = _g(balance_prev, "propertyPlantEquipmentNet", "propertyPlantAndEquipmentNet", "netPPE")
    if ppe_t is not None and ppe_t1 is not None and ppe_t > 0 and ppe_t1 > 0 and dep_t is not None and dep_t1 is not None and dep_t > 0 and dep_t1 > 0:
        depi = (dep_t1 / (dep_t1 + ppe_t1)) / (dep_t / (dep_t + ppe_t))
    else:
        depi = 1.0  # sin datos suficientes, no aporta señal

    # SGAI (SG&A Index)
    sga_t = _g(income, "sellingGeneralAndAdministrativeExpense", "operatingExpenses")
    sga_t1 = _g(income_prev, "sellingGeneralAndAdministrativeExpense", "operatingExpenses")
    if sales_t > 0 and sales_t1 > 0 and sga_t1 > 0:
        sgai = (sga_t / sales_t) / (sga_t1 / sales_t1)
    else:
        sgai = 1.0

    # LVGI (Leverage Index)
    tl_t = _g(balance, "totalLiabilities")
    tl_t1 = _g(balance_prev, "totalLiabilities")
    lev_t = tl_t / ta_t
    lev_t1 = tl_t1 / ta_t1
    lvgi = lev_t / lev_t1 if lev_t1 > 0 else 1.0

    # TATA (Total Accruals to Total Assets)
    ni_t = _g(income, "netIncome")
    cfo_t = _g(cash_flow, "operatingCashFlow")
    tata = (ni_t - cfo_t) / ta_t

    m = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aq
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )
    return m
# ============================================================================
# EV / EBIT
# ============================================================================
# El motor de AAI usa este múltiplo como uno de los 4 jueces del TRIBUNAL
# PRECIO (≤10 y positivo cuenta a favor, ≥20 o negativo en contra). Aquí se
# computa sobre datos crudos, no sobre el valor que da InvestingPro.
# EV = market cap + deuda total - caja e inversiones corto plazo.

def ev_to_ebit(
    income: Optional[Dict],
    balance: Optional[Dict],
    market_cap: Optional[float],
) -> Optional[float]:
    """Devuelve EV/EBIT (puede ser negativo) o None si falta EBIT o mcap."""
    if not income or not balance or market_cap is None or market_cap <= 0:
        return None
    ebit = _g(income, "operatingIncome", "ebit")
    if ebit is None or ebit == 0:
        return None  # EBIT=0 haría división por cero
    debt = _g(balance, "totalDebt", "longTermDebt")
    cash = _g(balance, "cashAndCashEquivalents")
    sti = _g(balance, "shortTermInvestments")
    ev = market_cap + debt - cash - sti
    return ev / ebit


# ============================================================================
# Fair Value Label propio (basado en upside vs consenso de analistas)
# ============================================================================
# El motor de AAI etiqueta el upside vs Fair Value de InvestingPro en uno de
# los 4 jueces del TRIBUNAL PRECIO ("bargain"/"undervalued" → a favor,
# "overvalued" → en contra). Acá construimos una versión propia usando los
# price targets del consenso de analistas de FMP:
#   upside = (targetConsensus - price) / price
#   upside >= 20%  → "bargain"
#   upside >= 5%   → "undervalued"
#   upside entre -5% y 5% → "fair"
#   upside < -5%   → "overvalued"
# Si no hay precio o target, devuelve None.

def fair_value_label(
    price: Optional[float],
    price_target_consensus: Optional[float],
) -> Optional[str]:
    """Devuelve uno de {bargain, undervalued, fair, overvalued, none}."""
    if price is None or price <= 0 or price_target_consensus is None:
        return None
    upside = (price_target_consensus - price) / price
    if upside >= 0.20:
        return "bargain"
    if upside >= 0.05:
        return "undervalued"
    if upside >= -0.05:
        return "fair"
    return "overvalued"


# ============================================================================
# Orquestador: aplicar las 4 fórmulas + Fair Value a un payload de Fase 1
# ============================================================================
# Estructura esperada: el mismo `payload` que devuelve
# `FundamentalsIngestion.ingest_symbol()` (income_statement, balance_sheet,
# cash_flow, profile, price_target_consensus). Toma t-0 (índice 0) y t-1
# (índice 1) si están disponibles; sin t-1 no se computa Piotroski/Beneish.

def compute_scores(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Devuelve un dict con los 5 puntajes (o None si faltan datos) + el
    market cap (necesario para Z y EV/EBIT) y price (de profile).

    El orquestador es PURO: no toca red ni disco. La función en Fase 3
    llama a compute_scores() sobre cada `ingest_symbol()` del universo.
    """
    income_list = payload.get("income_statement") or []
    bal_list = payload.get("balance_sheet") or []
    cf_list = payload.get("cash_flow") or []

    income = income_list[0] if len(income_list) >= 1 else None
    income_prev = income_list[1] if len(income_list) >= 2 else None
    balance = bal_list[0] if len(bal_list) >= 1 else None
    balance_prev = bal_list[1] if len(bal_list) >= 2 else None
    cf = cf_list[0] if len(cf_list) >= 1 else None
    cf_prev = cf_list[1] if len(cf_list) >= 2 else None

    profile = payload.get("profile") or {}
    pt = payload.get("price_target_consensus") or {}

    market_cap = _g(profile, "marketCap", "mktCap") or None
    price = _g(profile, "price") or None
    target = _g(pt, "targetConsensus", "targetMean") or None

    return {
        "piotroski_f_score": piotroski_f_score(income, income_prev, balance, balance_prev, cf, cf_prev),
        "altman_z_score": altman_z_score(income, balance, market_cap=market_cap),
        "beneish_m_score": beneish_m_score(income, income_prev, balance, balance_prev, cf),
        "ev_to_ebit": ev_to_ebit(income, balance, market_cap=market_cap),
        "fair_value_label": fair_value_label(price, target),
        "_meta": {
            "has_t_minus_1": income_prev is not None and balance_prev is not None,
            "market_cap": market_cap,
            "price": price,
            "price_target_consensus": target,
        },
    }
