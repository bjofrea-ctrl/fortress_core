"""
Fase 1 — construye el panel point-in-time de ratios fundamentales desde EDGAR.

Para cada símbolo: los company facts de SEC traen cada dato con su fecha de
filing REAL (el día en que la empresa lo publicó) — point-in-time sin
lookahead, mejor que el +45 días aproximado de Morningstar.

Flujos (revenue, net income, EBITDA, FCF, dividends): TTM (trailing 12 months)
por fecha de filing para eliminar estacionalidad trimestral. Balance e
instantáneos: último valor conocido a esa fecha. Ratios con precio: se
calculan con el precio de cierre local del día de trading siguiente al filing.

sue_score NO es derivable de EDGAR (requiere expectativas de consenso de
analistas) -> queda NaN y se excluye del diagnóstico con nota explícita.

Output: data/cache/fundamentals_panel.parquet (por fecha de trading, por
símbolo, 15 columnas de ratio).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.data_ingestion import load_universe

EDGAR_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "edgar"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "fundamentals_panel.parquet"

# Universo operativo del proyecto (50 canónicos menos SPY/QQQ ETFs, que no
# tienen fundamentales en EDGAR). Extensión Fase 0 de A5 (§47) para cubrir
# todo el universo en vez de los 5 originales.
try:
    from app.api.routes.opportunities_universe import SYMBOLS as _ALL_SYMBOLS

    SYMBOLS = [s for s in _ALL_SYMBOLS if s not in ("SPY", "QQQ")]
except Exception:  # pragma: no cover - fallback a los 5 originales
    SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
LOOKBACK_START = "2015-01-01"

# Tags US-GAAP (con fallbacks) -> (nombre canónico, es flujo TTM).
# Se COMBINAN todos los tags de un mismo ratio (pre/post ASC 606: las
# empresas cambiaron de SalesRevenueNet a RevenueFromContract...): unión
# de puntos, dedup por periodo, último filing gana.
FLOW_TAGS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueNet", "Revenues"),
    "net_income": ("NetIncomeLoss",),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterests"),
    "da": ("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet"),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"),
    "dividends": ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
}
INSTANT_TAGS = {
    "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt_lt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "debt_st": ("LongTermDebtCurrent", "CurrentPortionOfLongTermDebt"),
    "eps_diluted": ("EarningsPerShareDiluted",),
}
DEI_TAGS = {"shares": ("EntityCommonStockSharesOutstanding",)}

# Tags que también pueden venir como duración anual en 10-K; para TTM solo
# usamos puntos de duración <= 120 días (trimestrales) para sumar 4.
QUARTER_MAX_DAYS = 120


def _tag_points(tags) -> list:
    """Puntos de un ratio combinando TODOS sus tags candidatos (unión)."""
    facts = json.load(open(EDGAR_DIR / f"{SYMBOL}_companyfacts.json"))
    us_gaap = facts["facts"].get("us-gaap", {})
    dei = facts["facts"].get("dei", {})
    out = []
    for tag in tags:
        for d in (us_gaap, dei):
            if tag in d:
                units = d[tag]["units"]
                for u, pts in units.items():
                    if "USD" in u or "shares" in u.lower():
                        out.extend(pts)
    return out


def _dedup_last(points: list) -> list:
    """Por (start, end) mantener la versión con filed más reciente."""
    by_period = {}
    for p in points:
        key = (p.get("start"), p.get("end"))
        if key[0] is None or key[1] is None:
            continue
        cur = by_period.get(key)
        if cur is None or p.get("filed", "") > cur.get("filed", ""):
            by_period[key] = p
    return list(by_period.values())


def _ttm_series(points: list) -> pd.Series:
    """Serie TTM por fecha de filing, robusta a mezcla de 10-Q/10-K.

    Para cada filing: E = último period-end reportado. Si existe un punto
    anual (duración > 300d) que termina en E, el TTM ES ese punto. Si no,
    suma los puntos trimestrales (<= 120d) cuyo end cae en (E-365, E];
    si hay 4, TTM = suma. Así no hay doble conteo (anual+trimestres) ni
    ventanas parciales con sesgo entre símbolos.
    """
    pts = [p for p in _dedup_last(points) if p.get("start") and p.get("end")]
    if not pts:
        return pd.Series(dtype=float)
    df = pd.DataFrame(pts)
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    df["dur"] = (df["end"] - pd.to_datetime(df["start"])).dt.days
    df = df.sort_values("end")
    rows = []
    ends = df["end"].drop_duplicates().sort_values()
    for e in ends:
        win = df[(df["end"] > e - pd.Timedelta(days=370)) & (df["end"] <= e)]
        if len(win) == 0:
            continue
        annual = win[win["dur"] > 300]
        if len(annual) > 0:
            a = annual.sort_values("end").iloc[-1]
            rows.append({"filed": a["filed"], "value": float(a["val"])})
            continue
        quarters = win[win["dur"] <= 120]
        if len(quarters) >= 4:
            last4 = quarters.tail(4)
            filed = last4["filed"].max()
            rows.append({"filed": filed, "value": float(last4["val"].sum())})
    if not rows:
        return pd.Series(dtype=float)
    s = pd.DataFrame(rows).set_index("filed")["value"].sort_index()
    return s[~s.index.duplicated(keep="last")]


def _instant_series(points: list) -> pd.Series:
    """Serie instantánea por fecha de filing: último valor conocido."""
    pts = [p for p in points if p.get("end") and p.get("filed")]
    if not pts:
        return pd.Series(dtype=float)
    df = pd.DataFrame(pts)
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    df = df[df["filed"] >= df["end"] - pd.Timedelta(days=90)]
    df = df.sort_values(["end", "filed"]).drop_duplicates(subset=["end"], keep="last")
    s = pd.Series(df["val"].to_numpy(), index=df["filed"]).sort_index()
    return s[~s.index.duplicated(keep="last")]


def build_symbol_series() -> pd.DataFrame:
    """Serie de ratios crudos (filing-date index) por símbolo."""
    global SYMBOL
    frames = {}
    for symbol in SYMBOLS:
        SYMBOL = symbol
        flows, instants = {}, {}
        for name, tags in FLOW_TAGS.items():
            s = _ttm_series(_tag_points(tags))
            if len(s) > 10:
                flows[name] = s
        for name, tags in INSTANT_TAGS.items():
            s = _instant_series(_tag_points(tags))
            if len(s) > 10:
                instants[name] = s
        for name, tags in DEI_TAGS.items():
            s = _instant_series(_tag_points(tags))
            if len(s) > 10:
                instants[name] = s

        idx = sorted(set().union(*(s.index for s in flows.values()), *(s.index for s in instants.values())))
        idx = pd.DatetimeIndex(sorted(set(idx)))
        f = pd.DataFrame(index=idx)
        for name, s in flows.items():
            f[name] = s.reindex(f.index)
        for name, s in instants.items():
            f[name] = s.reindex(f.index)
        f = f.sort_index().ffill()
        f["symbol"] = symbol
        frames[symbol] = f
    return pd.concat(frames.values())


def _next_trading_prices(price_data: dict) -> dict:
    """Precio de cierre en el primer día de trading >= filing date."""
    return {s: df["close"] for s, df in price_data.items()}


def compute_ratios(filing_frame: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """Ratios finales por día de trading: el último filing conocido se aplica
    al día de trading siguiente; ratios con precio usan el close local."""
    out = []
    for symbol in SYMBOLS:
        sub = filing_frame[filing_frame["symbol"] == symbol].drop(columns="symbol").dropna(how="all")
        close = prices[symbol]
        entries = []
        for filed_ts, row in sub.iterrows():
            px_series = close[close.index >= filed_ts]
            if len(px_series) == 0:
                continue
            price = float(px_series.iloc[0])
            date = px_series.index[0]
            equity = row.get("equity", np.nan)
            assets = row.get("assets", np.nan)
            liab = row.get("liabilities", np.nan)
            shares = row.get("shares", np.nan)
            mktcap = price * shares if shares and shares > 0 else np.nan

            revenue = row.get("revenue", np.nan)
            eps_ttm = row.get("eps_diluted", np.nan) if pd.notna(row.get("eps_diluted")) else (row.get("net_income", np.nan) / shares if shares else np.nan)
            pe = price / eps_ttm if eps_ttm and eps_ttm > 0 else np.nan
            pb = price / (equity / shares) if shares and equity and equity > 0 and shares > 0 else np.nan
            debt = (row.get("debt_lt", 0) or 0) + (row.get("debt_st", 0) or 0)
            cash = row.get("cash", np.nan)
            ebitda = (row.get("operating_income", np.nan) or 0) + (row.get("da", np.nan) or 0)
            ev = (mktcap if pd.notna(mktcap) else 0) + debt - (cash if pd.notna(cash) else 0)
            ev_ebitda = ev / ebitda if ebitda and ebitda > 0 else np.nan
            roe = row.get("net_income", np.nan) / equity if equity and equity > 0 else np.nan
            roa = row.get("net_income", np.nan) / assets if assets and assets > 0 else np.nan
            de = debt / equity if equity and equity > 0 else np.nan
            fcf = (row.get("cfo", np.nan) or 0) - (row.get("capex", np.nan) or 0)
            fcf_yield = fcf / mktcap if pd.notna(mktcap) and mktcap > 0 else np.nan
            div_yield = row.get("dividends", np.nan) / mktcap if pd.notna(mktcap) and mktcap > 0 else np.nan
            eps_growth = np.nan
            gm = row.get("gross_profit", np.nan) / revenue if revenue and revenue > 0 else np.nan
            peg = pe / eps_growth if False else np.nan  # requiere eps_growth
            cr = row.get("current_assets", np.nan) / row.get("current_liabilities", np.nan) if row.get("current_liabilities", 0) else np.nan
            at = revenue / assets if assets and assets > 0 else np.nan

            entries.append({
                "date": date, "symbol": symbol,
                "pe_ratio": pe, "pb_ratio": pb, "ev_ebitda": ev_ebitda,
                "roe": roe, "roa": roa, "debt_equity": de,
                "fcf_yield": fcf_yield, "div_yield": div_yield,
                "eps_growth": eps_growth, "gross_margin": gm, "peg": peg,
                "current_ratio": cr, "asset_turnover": at,
                "book_value_growth": np.nan, "sue_score": np.nan,
                "eps_ttm": eps_ttm, "mktcap": mktcap, "equity": equity,
            })
        e = pd.DataFrame(entries)
        if len(e) == 0:
            continue
        e = e.drop_duplicates(subset=["date"], keep="last").set_index("date")
        out.append(e)
    return pd.concat(out)


def main():
    print("Construyendo series de filing por símbolo...")
    filing_frame = build_symbol_series()
    print(f"Filings totales: {len(filing_frame)}")

    print("Cargando precios locales...")
    price_data = load_universe(SYMBOLS, LOOKBACK_START, None)
    prices = _next_trading_prices(price_data)

    print("Computando ratios point-in-time...")
    panel = compute_ratios(filing_frame, prices)

    # Expandir a panel DIARIO por símbolo: el último filing conocido se
    # forward-fillea a cada día de trading (semántica del motor).
    daily = []
    for symbol in SYMBOLS:
        sub = panel[panel["symbol"] == symbol].drop(columns="symbol")
        if len(sub) == 0:
            continue
        sub = sub[~sub.index.duplicated(keep="last")]
        idx = prices[symbol].index
        if idx.name != "date":
            idx = idx.rename("date")
        sub = sub.reindex(idx).ffill()
        sub["symbol"] = symbol
        daily.append(sub)
    panel = pd.concat(daily)
    panel.index = panel.index.rename("date")

    # book_value_growth / eps_growth / peg: YoY directo (shift 252d) sobre
    # serie diaria ffill — el rolling mean del pct_change diario mezclaba
    # ceros (días sin filing) con saltos y sesgaba los niveles.
    panel = panel.reset_index().rename(columns={"index": "date"})
    for symbol in SYMBOLS:
        sub_mask = panel["symbol"] == symbol
        for base, target in [("equity", "book_value_growth"), ("eps_ttm", "eps_growth")]:
            col = panel.loc[sub_mask, base]
            if col.notna().sum() < 100:
                continue
            growth = (col / col.shift(252) - 1) * 100
            panel.loc[sub_mask, target] = growth.values
        pe = panel.loc[sub_mask, "pe_ratio"]
        growth = panel.loc[sub_mask, "eps_growth"]
        panel.loc[sub_mask, "peg"] = (pe / growth).values

    keep = ["date", "symbol", "pe_ratio", "pb_ratio", "ev_ebitda", "roe", "roa",
            "debt_equity", "fcf_yield", "div_yield", "eps_growth", "eps_ttm", "gross_margin",
            "peg", "current_ratio", "asset_turnover", "book_value_growth", "sue_score"]
    panel = panel[keep].set_index(["date", "symbol"])
    panel = panel[~panel.index.duplicated(keep="last")]
    panel.to_parquet(OUT_PATH)
    print(f"Panel diario guardado: {OUT_PATH} ({len(panel)} filas)")
    print(panel.describe().round(3).to_string())


if __name__ == "__main__":
    main()
