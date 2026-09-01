"""
Fase 3 — Los 3 tribunales sobre los datos propios (replica motor canónico).

Reimplementa la lógica de umbrales de `motor_screening.evaluate()` sobre los
datos que produce `FundamentalsIngestion.ingest_symbol()` (Fase 1) +
`fundamentals_scores.compute_scores()` (Fase 2). NO reconstruye diseño
visual: la salida se entrega con la misma estructura que consume
`generar_excel()` / `generar_dashboard()` del motor canónico
(~/claude/skills/aai-screening-acciones/scripts/motor_screening.py).

Fidelidad al motor canónico (validada leyendo el source línea por línea):
- Los 3 lentes de CALIDAD: Greenblatt (ROIC+ROIC 5y), MSCI (ROE+leverage),
  AQR (4 pilares: rentable, crecimiento, solidez, distribución).
- El veredicto PRECIO de 4 jueces: EV/EBIT, upside vs Fair Value, FCF
  Yield, Fair Value Label.
- El veredicto SALUD de 3 señales: Piotroski ≥7, Altman ≥3, Beneish ≤-1.78.
- Los baldes: Deep Dive / Watchlist / Neutral / Descartada con sus
  condiciones exactas (líneas 226-230 del motor canónico).
- Las alertas: Posible trampa de valor, ¿Demasiado barata?, M-Score,
  Altman zona de riesgo, Excelente pero salud débil, Datos insuficientes,
  Mejora débil — en el orden canónico de severidad.

Las 5y que el motor canónico lee (Avg ROIC 5y, Avg EPS Growth 5y, Revenue
CAGR 5y) requieren 5+ años de historia que el free tier de FMP no siempre
provee. Con menos historia se computa lo que se puede y se marca N/D el
resto — coherente con el motor canónico (que las trata como ausentes
sin fallar).
"""

from typing import Any, Dict, List, Optional

from app.core.fundamentals_scores import (
    _g,
    altman_z_score,
    beneish_m_score,
    ev_to_ebit,
    fair_value_label,
    piotroski_f_score,
)

# ============================================================================
# Exclusión sectorial (Financieras / Utilities)
# ============================================================================
# Mismo set que el motor canónico: empresas cuyo apalancamiento, caja o
# múltiplos no se miden con las fórmulas de Piotroski/Altman/Beneish (la deuda
# ES su materia prima, no un riesgo). El canon las marca como
# "Omitida por método" — nosotros también, para paridad bit-a-bit.
# Fuente única: backend/data/sectores_excluidos.csv (regenerable, NO trackeado
# en git como todos los data/cache; pero acá se trackea porque es el contrato
# del método, no estado volátil).

SECTORES_CSV = "data/sectores_excluidos.csv"
_sect_cache: Optional[Dict[str, str]] = None


def _load_sectores() -> Dict[str, str]:
    """Carga {ticker: sector} desde el CSV. Comentarios (#) y header se ignoran.
    Cachea en memoria: el CSV se lee una sola vez por proceso."""
    global _sect_cache
    if _sect_cache is not None:
        return _sect_cache
    s: Dict[str, str] = {}
    try:
        with open(SECTORES_CSV, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("ticker,"):
                    continue
                parts = line.split(",")
                if len(parts) >= 3:
                    s[parts[0].strip()] = parts[-1].strip()
    except OSError as e:
        # No abortamos: el motor canónico aborta si el archivo falta. Acá
        # preferimos seguir (sin exclusion) y loguear; el operador lo nota
        # en la revisión. Razonamiento: en CI el archivo siempre está.
        import logging
        logging.getLogger("fortress").warning(
            "sectoral_exclusion_unavailable",
            extra={"path": SECTORES_CSV, "error": str(e)},
        )
    _sect_cache = s
    return s


# ============================================================================
# Helpers de ratios 5y
# ============================================================================

def _avg_ratio(income_list, balance_list, kind, periods=5):
    """Media simple de un ratio sobre los últimos N periodos. kind soporta:
    - "roic": nopat / invested_capital. Devuelve None si <2 periodos.
    Devuelve None si no hay historia suficiente (motor canónico los trata N/D).
    """
    if not income_list or not balance_list:
        return None
    n = min(periods, len(income_list), len(balance_list))
    if n < 2:
        return None
    values = []
    for i in range(n):
        inc = income_list[i]
        bal = balance_list[i]
        if kind == "roic":
            ebit = _g(inc, "operatingIncome", "ebit")
            ibt = _g(inc, "incomeBeforeTax")
            tax = _g(inc, "incomeTaxExpense")
            tax_rate = (tax / ibt) if ibt > 0 else 0.21
            nopat = ebit * (1 - tax_rate)
            ic = _g(bal, "investedCapital", "totalCapital")
            if ic <= 0:
                d = _g(bal, "totalDebt", "longTermDebt")
                e = _g(bal, "totalShareholderEquity")
                ic = d + e
            if ic > 0 and ebit:
                values.append(nopat / ic)
    return (sum(values) / len(values)) if values else None


def _avg_eps_growth(income_list, periods=5):
    """Crecimiento anual promedio de EPS sobre N años. None si <2 periodos."""
    if not income_list or len(income_list) < 2:
        return None
    eps_values = [_g(i, "eps", "epsdiluted") for i in income_list[:periods]]
    eps_values = [e for e in eps_values if e is not None and e != 0]
    if len(eps_values) < 2:
        return None
    # Media geométrica del crecimiento (más fiel a "5y CAGR" que la simple).
    # Fórmula: (final/inicial)^(1/n) - 1
    n = len(eps_values) - 1
    if eps_values[-1] <= 0 or eps_values[0] <= 0:
        return None
    try:
        cagr = (eps_values[-1] / eps_values[0]) ** (1.0 / n) - 1.0
        return cagr
    except (ZeroDivisionError, ValueError):
        return None


def _revenue_cagr(income_list, periods=5):
    """Revenue CAGR sobre N años (geométrica). None si <2 periodos."""
    if not income_list or len(income_list) < 2:
        return None
    rev_values = [_g(i, "revenue") for i in income_list[:periods]]
    rev_values = [r for r in rev_values if r is not None and r > 0]
    if len(rev_values) < 2:
        return None
    n = len(rev_values) - 1
    try:
        return (rev_values[-1] / rev_values[0]) ** (1.0 / n) - 1.0
    except (ZeroDivisionError, ValueError):
        return None


def compute_indicators(
    income_list: List[Dict],
    balance_list: List[Dict],
    cf_list: List[Dict],
    profile: Optional[Dict] = None,
    pt: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Devuelve los ratios que el motor canónico lee del export de InvestingPro,
    calculados a partir de los estados financieros crudos de Fase 1. Devuelve
    siempre todas las claves (con None si no hay datos) — mismo contrato que
    `num(row, h)` del motor canónico: ausente se trata como None, no se inventa.
    Convenciones: ratios de calidad (ROIC, ROE, etc.) en DECIMAL (0.208 = 20.8%);
    los umbrales (>=20, >=15) del motor canónico asumen esa convención.
    """
    profile = profile or {}
    pt = pt or {}

    income = income_list[0] if len(income_list) >= 1 else None
    income_prev = income_list[1] if len(income_list) >= 2 else None
    balance = balance_list[0] if len(balance_list) >= 1 else None
    balance_prev = balance_list[1] if len(balance_list) >= 2 else None
    cf = cf_list[0] if len(cf_list) >= 1 else None
    cf_prev = cf_list[1] if len(cf_list) >= 2 else None

    market_cap = _g(profile, "marketCap", "mktCap")
    price = _g(profile, "price")
    target = _g(pt, "targetConsensus", "targetMean")
    beta = _g(profile, "beta")

    # ROIC = NOPAT / invested_capital
    invested_capital = _g(balance, "investedCapital", "totalCapital")
    if invested_capital <= 0 and balance:
        debt = _g(balance, "totalDebt", "longTermDebt")
        equity = _g(balance, "totalShareholderEquity")
        if debt > 0 and equity > 0:
            invested_capital = debt + equity
    ebit = _g(income, "operatingIncome", "ebit") if income else 0
    tax_rate = 0.21
    if income:
        ibt = _g(income, "incomeBeforeTax")
        tax_exp = _g(income, "incomeTaxExpense")
        if ibt > 0 and tax_exp > 0:
            tax_rate = tax_exp / ibt
    nopat = ebit * (1 - tax_rate) if ebit else 0
    roic = (nopat / invested_capital) if invested_capital > 0 else None

    roic_5y = _avg_ratio(income_list, balance_list, "roic", periods=5)

    equity = _g(balance, "totalShareholderEquity") if balance else 0
    net_income = _g(income, "netIncome") if income else 0
    roe = (net_income / equity) if equity > 0 else None

    revenue = _g(income, "revenue") if income else 0
    gross_profit = _g(income, "grossProfit") if income else 0
    gross_margin = (gross_profit / revenue) if revenue > 0 else None

    eps_growth_5y = _avg_eps_growth(income_list, periods=5)
    rev_cagr_5y = _revenue_cagr(income_list, periods=5)

    # Salud
    total_debt = _g(balance, "totalDebt", "longTermDebt") if balance else 0
    total_capital = total_debt + equity
    debt_to_capital = (total_debt / total_capital) if total_capital > 0 else None

    fcf = _g(cf, "freeCashFlow") if cf else 0
    fcf_to_ni = (fcf / net_income) if net_income != 0 else None

    # FMP devuelve commonStockRepurchased como negativo (cash outflow). Le
    # quitamos el signo para que el buyback yield sea positivo cuando recompra.
    buyback = -_g(cf, "commonStockRepurchased") if cf else 0
    buyback_yield = (buyback / market_cap) if market_cap > 0 else None

    # Precio
    fcf_yield = (fcf / market_cap) if market_cap > 0 else None
    upside = ((target - price) / price) if (price and target and price > 0) else None
    fv_label = fair_value_label(price, target)
    ev_ebit = ev_to_ebit(income, balance, market_cap=market_cap) if market_cap else None

    # P/E (lo calculamos a partir de los datos crudos para consistencia con el
    # resto del orquestador; el motor canónico lo lee del export).
    pe_ratio = None
    peg_ratio_fwd = None
    sh_dil = _g(income, "weightedAverageShsOutDil") if income else 0
    if sh_dil > 0 and price > 0 and net_income > 0:
        pe_ratio = price / (net_income / sh_dil)

    name = (profile.get("companyName") or "") if profile else ""
    ticker = (profile.get("symbol") or "") if profile else ""
    full_ticker = ""
    if profile:
        if profile.get("exchange") and profile.get("symbol"):
            full_ticker = f"{profile['exchange']}:{profile['symbol']}"
        elif profile.get("isin"):
            full_ticker = profile["isin"]

    return {
        "name": name,
        "ticker": ticker,
        "full_ticker": full_ticker,
        "price": price if price and price > 0 else None,
        "roic": roic, "roic_5y": roic_5y, "roe": roe,
        "gross_margin": gross_margin,
        "eps_growth_5y": eps_growth_5y, "rev_cagr_5y": rev_cagr_5y,
        "fcf_to_ni": fcf_to_ni, "debt_to_capital": debt_to_capital,
        "buyback_yield": buyback_yield, "fcf_yield": fcf_yield,
        "ev_to_ebit": ev_ebit, "fair_value": target, "upside": upside,
        "fair_value_label": fv_label,
        "piotroski_f_score": piotroski_f_score(income, income_prev, balance, balance_prev, cf, cf_prev),
        "altman_z_score": altman_z_score(income, balance, market_cap=market_cap) if market_cap else None,
        "beneish_m_score": beneish_m_score(income, income_prev, balance, balance_prev, cf),
        "market_cap": market_cap, "beta": beta,
        "pe_ratio": pe_ratio, "peg_ratio_fwd": peg_ratio_fwd,
    }


ORDEN_ALERTAS = [
    "Datos insuficientes", "Altman zona de riesgo", "M-Score",
    "Posible trampa de valor", "Excelente pero salud débil",
    "¿Demasiado barata?", "Mejora débil",
]


def _to_pct(x):
    if x is None:
        return None
    if not isinstance(x, (int, float)):
        return None
    return x * 100.0


def screen(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """Replica de motor_screening.evaluate() (líneas 178-239 del motor canónico).
    Devuelve la misma estructura que `generar_excel()` consume sin cambios."""
    roic = _to_pct(indicators.get("roic"))
    roic_5y = _to_pct(indicators.get("roic_5y"))
    roe = _to_pct(indicators.get("roe"))
    gm = _to_pct(indicators.get("gross_margin"))
    fcfy = _to_pct(indicators.get("fcf_yield"))
    epsg = _to_pct(indicators.get("eps_growth_5y"))
    revg = _to_pct(indicators.get("rev_cagr_5y"))
    bb = _to_pct(indicators.get("buyback_yield"))
    dc = _to_pct(indicators.get("debt_to_capital"))
    fcfni = indicators.get("fcf_to_ni")
    evebit = indicators.get("ev_to_ebit")
    fv = indicators.get("fair_value")
    m = indicators.get("beneish_m_score")
    pio = indicators.get("piotroski_f_score")
    alt = indicators.get("altman_z_score")
    upside = indicators.get("upside")
    lbl = (indicators.get("fair_value_label") or "").lower() if indicators.get("fair_value_label") else ""

    # Lente 1 — Greenblatt
    if roic is None and roic_5y is None:
        L1 = "N/D"
    elif roic is not None and roic_5y is not None:
        L1 = "Sí" if (roic >= 20 and roic_5y >= 20) else ("No" if (roic < 10 or roic_5y < 10) else "Medio")
    else:
        v = roic if roic is not None else roic_5y
        L1 = "Medio" if v >= 20 else ("No" if v < 10 else "Medio")

    # Lente 2 — MSCI
    lev = (dc is not None and dc > 60) or (dc is None and alt is not None and alt < 1.81)
    if roe is None:
        L3 = "N/D"
    elif roe >= 15 and not lev:
        L3 = "Sí"
    elif roe < 10 or lev:
        L3 = "No"
    else:
        L3 = "Medio"

    # Lente 3 — AQR (4 pilares; RENTABLE nunca marca ✗)
    conv = (fcfni is not None and fcfni >= 0.8 and fcfy is not None and fcfy > 0)
    rent = "v" if sum([
        roe is not None and roe >= 15,
        gm is not None and gm >= 40,
        conv,
    ]) >= 2 else "i"
    if epsg is None and revg is None:
        cre = "i"
    elif epsg is not None and revg is not None:
        cre = "v" if (epsg > 0 and revg > 0) else ("x" if (epsg < 0 or revg < 0) else "i")
    else:
        g = epsg if epsg is not None else revg
        cre = "v" if g > 0 else ("x" if g < 0 else "i")
    if alt is None:
        seg = "i"
    elif alt >= 3:
        seg = "v"
    elif alt < 1.81:
        seg = "x"
    else:
        # Zona gris (1.81 <= alt < 3): el motor canónico mira el "Overall
        # Health Label" de InvestingPro (great/good/fair/weak). Si la salud
        # NO es positiva, el pilar SEG no cuenta (cae a 'i'). Si no hay
        # health_label, mantenemos el comportamiento conservador (v) para
        # no perder empresas por falta de data.
        hl = indicators.get("health_label")
        if hl and str(hl).strip().lower() in ("good", "great", "excellent"):
            seg = "v"
        elif hl:
            seg = "i"  # 'fair', 'weak', u otro → no aporta señal
        else:
            seg = "v"  # sin health_label: asume positivo (conservador)
    if bb is None:
        pay = "i"
    elif bb >= 0:
        pay = "v"
    elif bb < -2:
        pay = "x"
    else:
        pay = "i"
    pil = [rent, cre, seg, pay]
    L4 = "Sí" if (pil.count("v") >= 3 and pil.count("x") == 0) else ("No" if pil.count("x") >= 2 else "Medio")

    lentes = [L1, L3, L4]
    n_cal = lentes.count("Sí")
    cal = "EXCELENTE" if n_cal == 3 else ("BUENA" if n_cal == 2 else "DÉBIL")


    # TRIBUNAL PRECIO: 4 jueces
    n_val = sum([
        evebit is not None and 0 < evebit <= 10,
        upside is not None and upside >= 0.20,
        fcfy is not None and fcfy >= 4,
        lbl in ("bargain", "undervalued"),
    ])
    v_c = sum([
        upside is not None and upside <= -0.10,
        evebit is not None and (evebit >= 20 or evebit < 0),
        fcfy is not None and fcfy <= 2,
        lbl == "overvalued",
    ])
    if v_c >= 2 and v_c > n_val:
        precio = "CARA"
    elif n_val >= 3 and n_val > v_c:
        precio = "MUY BARATA"
    elif n_val == 2 and n_val > v_c:
        precio = "BARATA"
    else:
        precio = "MIXTA"

    # TRIBUNAL SALUD: 3 señales
    n_sal = sum([
        pio is not None and pio >= 7,
        alt is not None and alt >= 3,
        m is not None and m <= -1.78,
    ])
    salud = "DÉBIL" if ((alt is not None and alt < 1.81) or n_sal <= 1) else ("EXCELENTE" if n_sal == 3 else "MIXTA")

    # BALDE + ALERTAS (líneas 222-239 del motor canónico, replicado)
    core = [roic, roic_5y, roe, gm, epsg, revg, fcfni, bb, evebit, fcfy, fv, pio]
    insuf = sum(1 for x in core if x is None) >= 5
    trampa = (cal == "DÉBIL" and precio in ("MUY BARATA", "BARATA"))
    if insuf:
        balde = "Descartada"
    elif cal == "EXCELENTE" and salud != "DÉBIL" and precio in ("MUY BARATA", "BARATA"):
        balde = "Deep Dive"
    elif cal == "EXCELENTE" and salud != "DÉBIL":
        balde = "Watchlist"
    elif cal in ("EXCELENTE", "BUENA"):
        balde = "Neutral"
    else:
        balde = "Descartada"

    al = []
    if trampa:
        al.append("Posible trampa de valor")
    if cal == "EXCELENTE" and ((upside is not None and upside >= 0.40) or n_val >= 3):
        al.append("¿Demasiado barata?")
    if m is not None and m > -1.78:
        al.append("M-Score")
    if cal == "EXCELENTE" and pio is not None and pio <= 3:
        al.append("Mejora débil")
    if alt is not None and alt < 1.81:
        al.append("Altman zona de riesgo")
    if cal == "EXCELENTE" and salud == "DÉBIL":
        al.append("Excelente pero salud débil")
    if insuf:
        al.append("Datos insuficientes")
    al.sort(key=lambda x: ORDEN_ALERTAS.index(x) if x in ORDEN_ALERTAS else 99)

    # Celdas rojas/ámbar (reglas idénticas a motor canónico líneas 240-256)
    reds = set()
    amb = set()
    if roic is not None and roic < 10:
        reds.add("roic")
    if roic_5y is not None and roic_5y < 10:
        reds.add("roic_5y")
    if roe is not None and roe < 10:
        reds.add("roe")
    if epsg is not None and epsg < 0:
        reds.add("eps_growth_5y")
    if revg is not None and revg < 0:
        reds.add("rev_cagr_5y")
    if fcfni is not None and not conv and (fcfni < 0.8 or (fcfy is not None and fcfy <= 0)):
        reds.add("fcf_to_ni")
    if bb is not None and bb < -2:
        reds.add("buyback_yield")
    if dc is not None and dc > 60:
        reds.add("debt_to_capital")
    if pio is not None and pio <= 3:
        reds.add("piotroski_f_score")
    if alt is not None:
        if alt < 1.81:
            reds.add("altman_z_score")
        elif alt < 3:
            amb.add("altman_z_score")
    if m is not None and m > -1.78:
        amb.add("beneish_m_score")
    if fcfy is not None and fcfy <= 2:
        reds.add("fcf_yield")
    if evebit is not None and (evebit >= 20 or evebit < 0):
        reds.add("ev_to_ebit")

    return {
        "balde": balde,
        "punt": n_cal + n_val + n_sal,
        "L": lentes,
        "cal": cal, "n_cal": n_cal,
        "precio": precio, "n_val": n_val, "v_c": v_c,
        "upside": upside,
        "salud": salud, "n_sal": n_sal,
        "alertas": " · ".join(al[:3]) if al else "—",
        "reds": reds, "amb": amb,
        "up_red": upside is not None and upside <= -0.10,
    }


# ============================================================================
# Orquestador: screen_payload(payload) → produce el dict que
# `generar_excel()` / `generar_dashboard()` del motor canónico consumen
# (estructura de motor_screening.evaluate() líneas 256-264 + los indicadores
# que el motor lee del row del export).
# ============================================================================

def screen_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Toma el payload de Fase 1 (FMP) + opcionalmente de Fase 2, calcula
    los indicadores y aplica los 3 tribunales. Devuelve un dict con la misma
    forma que produce `motor_screening.evaluate()` más los indicadores.
    Listo para que `generar_excel(filas, hmap, evals, orden, ...)` lo consuma
    sin tocar nada del diseño visual del motor canónico.

    Exclusión sectorial: si el ticker está en la lista de Financieras/Utilities
    (misma lista que el motor canónico), devuelve una estructura de "Omitida
    por método" con `balde="Omitida"` y un campo `sectx` con el sector. El motor
    canónico lo renderiza en una categoría separada de la pantalla principal.
    """
    income_list = payload.get("income_statement") or []
    balance_list = payload.get("balance_sheet") or []
    cf_list = payload.get("cash_flow") or []
    profile = payload.get("profile") or {}
    pt = payload.get("price_target_consensus") or {}

    # Exclusión sectorial (mismo set que motor canónico líneas 92-124).
    # El ticker puede venir del payload, del profile, o del name; usamos la
    # primera fuente disponible.
    ticker = (
        payload.get("ticker")
        or profile.get("symbol")
        or profile.get("ticker")
        or ""
    ).strip().upper()
    if ticker:
        sect = _load_sectores().get(ticker)
        if sect:
            indicators = compute_indicators(income_list, balance_list, cf_list, profile, pt)
            return {**indicators, "balde": "Omitida", "sectx": sect, "punt": 0,
                    "L": ["N/D", "N/D", "N/D"], "cal": "N/D", "n_cal": 0,
                    "precio": "N/D", "n_val": 0, "v_c": 0, "upside": None,
                    "salud": "N/D", "n_sal": 0, "alertas": f"Sector {sect} — este método no lo mide bien; analizar aparte",
                    "reds": set(), "amb": set(), "up_red": False}

    indicators = compute_indicators(income_list, balance_list, cf_list, profile, pt)
    eval_ = screen(indicators)

    return {**indicators, **eval_}
