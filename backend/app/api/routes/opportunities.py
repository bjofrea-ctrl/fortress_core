"""API routes para oportunidades actuales (Pieza 1 del proyecto de sugerencias).

GET /api/opportunities/today — candidatos de HOY (datos reales, no backtest):
- El MISMO gate y score de generate_signal (signal_engine.py), sin top-5:
  muestra todos los que pasan gate completo + score >= 0.6.
- Cada candidato con su razón: factores crudos, gates cumplidos, plan de
  salida completo (parcial/trailing/técnica/régimen), win_prob calibrado
  (Platt, el número real sin maquillar), y pares de cola ALTO entre los
  candidatos del día (CopulaRiskAnalyzer — "estas N se mueven juntas").
- Header con régimen actual y blocked_reason (régimen 3 = DEFLATION ->
  entradas bloqueadas por diseño, la lista vacía se explica sola).
- Track record real de sugerencias emitidas (suggestions_store).
"""
import datetime
import time
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from app.core.backtest_engine import BacktestEngine
from app.core.data_ingestion import download_data, load_universe
from app.core.market_sentiment import fetch_aaii
from app.core.probabilistic_engine import CopulaRiskAnalyzer, ProbabilityCalibrator
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.adaptive_risk import REGIME_THRESHOLDS
from app.core.signal_engine import SignalEngine
from app.core.suggestions_store import (
    evaluate_pending, get_track_record, record_suggestions,
)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
           "BRK-B", "LLY", "AVGO", "JPM", "XOM", "UNH", "V", "MA",
           "PG", "COST", "JNJ", "WMT", "HD", "NFLX", "ABBV", "BAC",
           "CVX", "KO", "PEP", "MRK", "CRM", "ORCL", "ADBE", "WFC",
           "MCD", "CSCO", "ACN", "ABT", "TMO", "LIN", "PM", "TXN",
           "IBM", "GE", "AMGN", "CAT", "GS"]
MARKET_TICKERS = ["SPY", "EFA", "QQQ", "GLD", "DBC", "TIP", "TLT", "AGG", "^VIX"]
HISTORY_START = "2019-01-01"
DATA_START = "2015-01-01"
MIN_SCORE = 0.6
TAIL_WINDOW_DAYS = 252


def _load_market_data():
    return load_universe(MARKET_TICKERS, DATA_START, "2026-08-11")


def _load_price_data():
    return load_universe(SYMBOLS, HISTORY_START, "2026-08-11")


def _fit_regime(market_data) -> dict:
    clf = GlobalRegimeClassifier()
    clf.fit(market_data)
    return clf.predict_current_regime(market_data)


def _fit_calibrator(price_data, today) -> ProbabilityCalibrator:
    """Mismo pipeline que el backtest: replay histórico de señales + outcomes
    a 20d, ventana móvil de ~2 años (igual que el refit walk-forward)."""
    engine = BacktestEngine(initial_capital=25000)
    indicators_cache = {s: df for s, df in price_data.items() if len(df) > 220}
    refit_start = today - pd.Timedelta(days=730)
    scores, outcomes = engine._build_calibration_dataset(
        indicators_cache, today, update_bayesian=False, train_start_date=refit_start
    )
    calibrator = ProbabilityCalibrator(method="platt")
    if len(scores) >= 20:
        calibrator.fit(scores, outcomes)
    return calibrator


def _load_sentiment_map(trading_dates) -> dict:
    """AAII bull-bear con alineación anti-lookahead (valor publicado antes de
    hoy, shift(1)). Sin dato -> {} (el endpoint degrada a ranking por score)."""
    try:
        aaii = fetch_aaii()
        if aaii is None or len(aaii) == 0:
            return {}
        cutoff = pd.Timestamp.now().normalize()
        valid = aaii[aaii.index < cutoff]
        if valid.empty:
            return {}
        joined = pd.concat([valid, pd.Series(1.0, index=trading_dates)], axis=1).sort_index().iloc[:, 0]
        shifted = joined.shift(1).ffill().reindex(trading_dates)
        return {ts: float(v) for ts, v in shifted.items() if pd.notna(v)}
    except Exception:
        return {}


def _exit_plan(regime_state: int) -> dict:
    """Los 4 mecanismos de salida del motor (adaptive_risk.py), con la
    condición exacta de cada uno, para que el humano vea el plan completo."""
    pos_stop = REGIME_THRESHOLDS.get(regime_state, REGIME_THRESHOLDS[0])["position_stop"]
    return {
        "partial_tp": {
            "trigger": "precio >= entrada + 2*ATR",
            "action": "vender 50% de la posición (una sola vez, fix trial #10)",
        },
        "trailing_stop": {
            "trigger": "máximo > entrada + 1.5*ATR y precio <= máximo - 2*ATR",
            "action": "cerrar la posición restante",
        },
        "technical": {
            "trigger": "ADX < 20 o (close < EMA20 < EMA50)",
            "action": "cerrar la posición restante",
        },
        "regime_stop": {
            "trigger": f"pérdida desde entrada <= -{pos_stop:.0%}",
            "action": "cerrar la posición (stop de régimen)",
        },
    }


def _build_opportunities(price_data, sentiment_map, regime_state, today) -> list:
    engine = BacktestEngine(initial_capital=25000)
    signal_engine = SignalEngine(engine.regime_classifier)
    calibrator = _fit_calibrator(price_data, today)

    opportunities = []
    for symbol, df in price_data.items():
        if len(df) < 220:
            continue
        sig = signal_engine.generate_signal(df, symbol, regime_state)
        if sig is None:
            continue
        if sig["score"] < MIN_SCORE:
            continue

        latest = df.iloc[-1]
        win_prob = float(calibrator.predict(np.array([sig["score"]]))[0]) if calibrator else None

        g2 = None
        if sentiment_map:
            g2_series = signal_engine.compute_g2_rank_scores(df, sentiment_map)
            if len(g2_series) and pd.notna(g2_series.iloc[-1]):
                g2 = float(g2_series.iloc[-1])

        ind = sig["indicators"]
        opportunities.append({
            "symbol": symbol,
            "score": round(float(sig["score"]), 4),
            "win_prob": round(win_prob, 4) if win_prob is not None else None,
            "factors": {k: round(float(v), 4) for k, v in sig["factors"].items()},
            "gates": {
                "trend_ok": bool(ind["close"] > ind["ema50"] > ind["ema200"]),
                "adx": round(ind["adx14"], 2),
                "rsi": round(ind["rsi14"], 2),
                "volume_ratio": round(ind["volume_ratio"], 2),
            },
            "entry_price": round(float(sig["entry_price"]), 2),
            "stop_loss": round(float(sig["stop_loss"]), 2),
            "take_profit": round(float(sig["take_profit"]), 2),
            "payoff_ratio": round(float(sig["payoff_ratio"]), 2),
            "atr": round(float(sig["atr"]), 2),
            "g2_score": g2,
            "exit_plan": _exit_plan(regime_state),
        })

    # Ranking: G2 (sentimiento) si existe, si no score puro — mismo orden
    # que rank_signals en el backtest.
    opportunities.sort(
        key=lambda o: o["g2_score"] if o["g2_score"] is not None else o["score"],
        reverse=True,
    )
    return opportunities


def _tail_concentration(price_data, symbols: list) -> dict:
    """Dependencia de cola ALTA entre los candidatos de HOY (ventana 252d).
    Si 2+ candidatos comparten pares ALTO, el dashboard alerta que se
    mueven juntas — el sizing por activo (Kelly) no lo ve (misma razón que
    analyze_portfolio_tail_risk en el backtest)."""
    if len(symbols) < 2:
        return {"alerts": [], "n_pairs_analyzed": 0}
    analyzer = CopulaRiskAnalyzer()
    returns = {}
    for sym in symbols:
        df = price_data.get(sym)
        if df is None:
            continue
        ret = df["close"].tail(TAIL_WINDOW_DAYS).pct_change().dropna()
        if len(ret) >= 30:
            returns[sym] = ret

    high_pairs = []
    syms = list(returns.keys())
    for i, a in enumerate(syms):
        for b in syms[i + 1:]:
            common = returns[a].index.intersection(returns[b].index)
            if len(common) < 30:
                continue
            r = analyzer.analyze_pair(
                returns[a].loc[common].values, returns[b].loc[common].values, a, b
            )
            if "error" not in r and r["risk_level"] == "ALTO":
                high_pairs.append({
                    "pair": f"{a}-{b}",
                    "tail_dependence_lower": r["tail_dependence_lower"],
                    "tail_dependence_upper": r["tail_dependence_upper"],
                })
    return {"alerts": high_pairs, "n_pairs_analyzed": len(syms) * (len(syms) - 1) // 2}


@router.get("/today")
async def opportunities_today():
    """Oportunidades de HOY con razón completa, plan de salida, win_prob
    calibrado y concentración de cola entre candidatos. Sin top-5: muestra
    todos los que pasan el gate + score >= 0.6."""
    try:
        market_data = _load_market_data()
        price_data = _load_price_data()
        today = pd.Timestamp.now().normalize()

        regime = _fit_regime(market_data)
        regime_state = int(regime["state"])

        ref_symbol = max(price_data, key=lambda s: len(price_data[s]))
        sentiment_map = _load_sentiment_map(price_data[ref_symbol].index)
        opportunities = _build_opportunities(price_data, sentiment_map, regime_state, today)

        evaluation = evaluate_pending(price_data)

        blocked_reason = None
        if regime_state == 3:
            blocked_reason = (
                "Régimen de mercado DEFLATION (estado 3): el motor bloquea "
                "entradas nuevas por diseño — la lista vacía es la decisión, "
                "no un fallo."
            )

        concentration = _tail_concentration(
            price_data, [o["symbol"] for o in opportunities]
        )

        suggestions = [
            {"symbol": o["symbol"], "date": today, "score": o["score"], "win_prob": o["win_prob"]}
            for o in opportunities
        ]
        added = record_suggestions(suggestions, str(today.date()))

        return {
            "as_of": today.date().isoformat(),
            "regime": {
                "state": regime_state,
                "name": regime["state_name"],
                "confidence": round(float(regime.get("confidence", 0.0)), 4),
            },
            "blocked_reason": blocked_reason,
            "min_score": MIN_SCORE,
            "opportunities": opportunities,
            "concentration": concentration,
            "track_record": get_track_record(),
            "suggestions_recorded_today": added,
            "evaluation": evaluation,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando oportunidades: {str(e)}")
