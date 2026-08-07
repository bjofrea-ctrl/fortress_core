import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime
from scipy.stats import norm
from app.core.signal_engine import SignalEngine
from app.core.adaptive_risk import AdaptiveRiskManager
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.indicators import calculate_all_indicators
from app.core.probabilistic_engine import (
    ProbabilityCalibrator, BayesianOnlineUpdater, WalkForwardValidator, SignalQualityMetrics,
)

CALIBRATION_HORIZON_DAYS = 20  # ~1 mes hábil, alineado a "short_term_1_30d"
CALIBRATION_STRIDE_DAYS = 5    # semanal, misma cadencia que el rebalanceo real


class BacktestEngine:
    def __init__(self, initial_capital: float = 25000.0):
        self.initial_capital = initial_capital
        self.regime_classifier = GlobalRegimeClassifier()
        self.bayesian_updater = BayesianOnlineUpdater()
        self.signal_engine = SignalEngine(self.regime_classifier, bayesian_updater=self.bayesian_updater)

    def _build_calibration_dataset(
        self, indicators_cache: Dict[str, pd.DataFrame], train_end_date: datetime
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Replay histórico previo a train_end_date: por cada fecha (cadencia semanal)
        genera la señal que se habría emitido y la etiqueta como win/loss según el
        precio CALIBRATION_HORIZON_DAYS hábiles después. Usa regime_state=0 como
        aproximación (los filtros de entrada no cambian por régimen, salvo el
        bloqueo en régimen 3, que de todos modos no genera señal).

        De paso, con el mismo replay hace un warm-start del BayesianOnlineUpdater
        por (régimen=0, factor) para que el BMA no arranque en frío. Los regímenes
        1-3 sólo se calibran online durante el loop principal del backtest, que sí
        usa el régimen real de cada fecha.
        """
        scores, outcomes = [], []
        priors = self.signal_engine.factor_weights[0]
        for symbol, df in indicators_cache.items():
            train_df = df[df.index < train_end_date]
            n = len(train_df)
            if n < 220:
                continue
            for i in range(200, n - CALIBRATION_HORIZON_DAYS, CALIBRATION_STRIDE_DAYS):
                sig = self.signal_engine.generate_signal(train_df.iloc[: i + 1], symbol, regime_state=0)
                if sig is None:
                    continue
                entry = train_df["close"].iloc[i]
                future = train_df["close"].iloc[i + CALIBRATION_HORIZON_DAYS]
                won = future > entry
                scores.append(sig["score"])
                outcomes.append(1.0 if won else 0.0)

                for factor, factor_score in sig["factors"].items():
                    predicted_up = factor_score > 0.5
                    self.bayesian_updater.update(
                        f"0_{factor}", correct=(predicted_up == won), base_weight=priors[factor]
                    )
        return np.array(scores), np.array(outcomes)

    def _update_bayesian_weights(self, pos: Dict, pnl: float) -> None:
        factors = pos.get("factors")
        if not factors:
            return
        regime = pos.get("regime_state", 0)
        won = pnl > 0
        priors = self.signal_engine.factor_weights.get(regime, self.signal_engine.factor_weights[0])
        for factor, score in factors.items():
            predicted_up = score > 0.5
            self.bayesian_updater.update(
                f"{regime}_{factor}", correct=(predicted_up == won), base_weight=priors[factor]
            )

    def validate_signal_quality(
        self, indicators_cache: Dict[str, pd.DataFrame], start_date: datetime, end_date: datetime
    ) -> Dict:
        """
        Diagnóstico walk-forward (IC/RankIC/ICIR) de si el score compuesto
        predice retornos futuros de forma genuina y estable fuera de muestra,
        en vez de confiar en una sola corrida de backtest in-sample. Usa
        regime_state=0 como aproximación uniforme (misma simplificación que
        el resto del pipeline de calibración).

        Restringido a días "eligible" (mismos filtros duros que generate_signal):
        el score nunca se usa para operar fuera de esa población, así que
        medir IC sobre todos los días -incluyendo los que jamás generarían un
        trade real- responde una pregunta distinta a la que importa. Los días
        no elegibles quedan como NaN y WalkForwardValidator/compute_ic ya los
        descarta solo (dropna interno).
        """
        validator = WalkForwardValidator()
        per_symbol = {}
        for symbol, df in indicators_cache.items():
            window = df[(df.index >= start_date) & (df.index <= end_date)].copy()
            if len(window) < validator.train_window + validator.test_window:
                continue
            frame = self.signal_engine.compute_factor_frame(window)
            window["score"] = self.signal_engine.compute_score_series(window, regime_state=0)
            window.loc[~frame["eligible"], "score"] = np.nan
            result = validator.validate(window, signal_col="score", return_col="close",
                                         horizon=CALIBRATION_HORIZON_DAYS)
            if "error" not in result:
                per_symbol[symbol] = result

        if not per_symbol:
            return {"error": "Ventana insuficiente para walk-forward"}

        return {
            "per_symbol": per_symbol,
            "aggregate": {
                "mean_ic": round(float(np.mean([r["mean_ic"] for r in per_symbol.values()])), 4),
                "mean_rank_ic": round(float(np.mean([r["mean_rank_ic"] for r in per_symbol.values()])), 4),
                "mean_icir": round(float(np.mean([r["icir"] for r in per_symbol.values()])), 4),
                "mean_positive_ic_pct": round(float(np.mean([r["positive_ic_pct"] for r in per_symbol.values()])), 4),
                "n_symbols": len(per_symbol),
            },
        }

    def diagnose_factor_ic(
        self, indicators_cache: Dict[str, pd.DataFrame], start_date: datetime, end_date: datetime,
        horizon: int = CALIBRATION_HORIZON_DAYS,
    ) -> Dict:
        """
        IC/RankIC de cada factor por separado (momentum, trend, rsi, adx),
        calculado SOLO sobre días que pasarían el filtro duro de entrada
        (eligible), pooleando todos los símbolos. A diferencia de
        validate_signal_quality (que mide el score compuesto en todos los
        días), esto aísla qué factor individual predice bien -o mal- dentro
        de la población real de candidatos a trade.
        """
        pooled = {"momentum": [], "trend": [], "rsi": [], "adx": []}
        pooled_returns = []
        for symbol, df in indicators_cache.items():
            window = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(window) < horizon + 30:
                continue
            frame = self.signal_engine.compute_factor_frame(window)
            forward_returns = window["close"].shift(-horizon) / window["close"] - 1
            mask = frame["eligible"] & forward_returns.notna()
            if mask.sum() < 20:
                continue
            for factor in pooled:
                pooled[factor].append(frame.loc[mask, factor])
            pooled_returns.append(forward_returns[mask])

        if not pooled_returns:
            return {"error": "Muestra insuficiente en población elegible"}

        all_returns = pd.concat(pooled_returns)
        result = {"n_eligible_days": int(len(all_returns))}
        for factor, series_list in pooled.items():
            factor_series = pd.concat(series_list)
            result[factor] = {
                "ic": round(SignalQualityMetrics.compute_ic(factor_series, all_returns), 4),
                "rank_ic": round(SignalQualityMetrics.compute_rank_ic(factor_series, all_returns), 4),
            }
        return result

    def run(
        self,
        price_data: Dict[str, pd.DataFrame],
        market_data: Dict[str, pd.DataFrame],
        start_date: datetime,
        end_date: datetime,
        commission=0.001,
        slippage=0.0005
    ) -> Dict:
        indicators_cache = {s: calculate_all_indicators(df) for s, df in price_data.items()}
        train_market = {s: df[df.index < start_date] for s, df in market_data.items()}
        self.regime_classifier.fit(train_market)

        calibrator = ProbabilityCalibrator(method="platt")
        cal_scores, cal_outcomes = self._build_calibration_dataset(indicators_cache, start_date)
        calibrator.fit(cal_scores, cal_outcomes)

        risk_manager = AdaptiveRiskManager(self.initial_capital)
        equity, cash = self.initial_capital, self.initial_capital
        positions: Dict[str, Dict] = {}
        equity_curve, trades = [], []

        spy = market_data.get("SPY")
        dates = spy[(spy.index >= start_date) & (spy.index <= end_date)].index

        for date in dates:
            current_prices, atrs = {}, {}
            positions_value = 0

            for symbol, pos in list(positions.items()):
                if symbol in indicators_cache and date in indicators_cache[symbol].index:
                    row = indicators_cache[symbol].loc[date]
                    current_prices[symbol] = row.close
                    atrs[symbol] = row.atr14
                    positions_value += pos["shares"] * row.close

            equity = cash + positions_value
            risk_manager.update_peak(equity)
            equity_curve.append({
                "date": date,
                "equity": equity,
                "drawdown_pct": risk_manager.drawdown_from_peak(equity),
            })

            to_close = risk_manager.check_all_stops(equity, current_prices, atrs, date)
            for symbol, reason in to_close:
                if symbol not in positions:
                    continue

                pos = positions[symbol]
                shares_to_sell = pos["shares"] // 2 if reason == "PARTIAL_TP" else pos["shares"]
                exit_price = current_prices.get(symbol, pos["entry_price"]) * (1 - slippage)
                cash += exit_price * shares_to_sell * (1 - commission)
                pnl = (exit_price - pos["entry_price"]) * shares_to_sell
                self._update_bayesian_weights(pos, pnl)

                trades.append({
                    "symbol": symbol,
                    "entry_date": pos["entry_date"],
                    "exit_date": date,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "shares": shares_to_sell,
                    "pnl": pnl,
                    "exit_reason": reason,
                })

                risk_manager.register_exit(symbol, shares_to_sell)
                pos["shares"] -= shares_to_sell
                if pos["shares"] <= 0:
                    del positions[symbol]

            for symbol in list(positions.keys()):
                if symbol in indicators_cache and date in indicators_cache[symbol].index:
                    row = indicators_cache[symbol].loc[date]
                    if risk_manager.check_technical_exit(row.adx14, row.close, row.ema20, row.ema50):
                        pos = positions[symbol]
                        exit_price = row.close * (1 - slippage)
                        cash += exit_price * pos["shares"] * (1 - commission)
                        pnl = (exit_price - pos["entry_price"]) * pos["shares"]
                        self._update_bayesian_weights(pos, pnl)

                        trades.append({
                            "symbol": symbol,
                            "entry_date": pos["entry_date"],
                            "exit_date": date,
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "shares": pos["shares"],
                            "pnl": pnl,
                            "exit_reason": "TECHNICAL",
                        })

                        risk_manager.register_exit(symbol, pos["shares"])
                        del positions[symbol]

            if date.dayofweek == 0 and risk_manager.can_open_new_position(date):
                regime_info = self.regime_classifier.predict_current_regime(
                    {s: df[df.index <= date] for s, df in market_data.items()}
                )
                risk_manager.update_regime(regime_info["state"])

                signals = []
                for symbol, df in indicators_cache.items():
                    if date in df.index:
                        sig = self.signal_engine.generate_signal(df.loc[:date], symbol, regime_info["state"])
                        if sig:
                            signals.append(sig)

                signals = self.signal_engine.rank_signals(signals)
                current_exposure = positions_value / equity if equity > 0 else 0
                signals = self.signal_engine.filter_by_regime_exposure(
                    signals, regime_info["state"], current_exposure
                )

                for sig in signals[:5]:
                    if sig["symbol"] in positions:
                        continue

                    win_prob = float(calibrator.predict(np.array([sig["score"]]))[0])
                    shares = risk_manager.compute_position_size(
                        equity, sig["entry_price"], sig["atr"],
                        win_prob=win_prob, payoff_ratio=sig["payoff_ratio"],
                    )
                    cost = sig["entry_price"] * shares * (1 + slippage) * (1 + commission)

                    if shares > 0 and cost < cash:
                        cash -= cost
                        positions[sig["symbol"]] = {
                            "shares": shares,
                            "entry_price": sig["entry_price"],
                            "entry_date": date,
                            "regime_state": sig["regime_state"],
                            "factors": sig["factors"],
                        }
                        risk_manager.register_entry(sig["symbol"], sig["entry_price"], shares)

        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "risk_events": risk_manager.state.risk_events,
            "metrics": self.calculate_metrics(equity_curve, trades),
            "monte_carlo": self.monte_carlo_simulation(trades),
            "signal_quality": self.validate_signal_quality(indicators_cache, start_date, end_date),
        }

    def calculate_metrics(self, equity_curve: List[Dict], trades: List[Dict]) -> Dict:
        if not equity_curve:
            return {}

        df = pd.DataFrame(equity_curve).set_index("date")
        returns = df["equity"].pct_change().dropna()
        n_years = max((df.index[-1] - df.index[0]).days / 365.25, 0.01)
        cagr = (df["equity"].iloc[-1] / df["equity"].iloc[0]) ** (1 / n_years) - 1
        sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0

        downside = returns[returns < 0]
        sortino = returns.mean() / downside.std() * np.sqrt(252) if len(downside) and downside.std() > 0 else 0
        max_dd = df["drawdown_pct"].min()
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0

        wins = [t["pnl"] for t in trades if t["pnl"] > 0]
        losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
        win_rate = len(wins) / len(trades) if trades else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float("inf")

        gamma = 0.5772156649
        n_trials = 10
        e_max_sr = ((1 - gamma) * norm.ppf(1 - 1 / n_trials) + gamma * norm.ppf(1 - 1 / (n_trials * np.e)))
        sr_std = np.sqrt((1 + 0.5 * sharpe ** 2) / (len(returns) - 1)) if len(returns) > 1 else 1
        deflated_sharpe = float(
            norm.cdf((sharpe - e_max_sr / np.sqrt(len(returns))) / sr_std)
        ) if len(returns) > 1 else 0.0

        return {
            "cagr": float(cagr),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "max_drawdown": float(max_dd),
            "calmar_ratio": float(calmar),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "total_trades": len(trades),
            "deflated_sharpe": deflated_sharpe,
        }

    def monte_carlo_simulation(self, trades: List[Dict], n_sims: int = 1000) -> Dict:
        pnls = [t["pnl"] for t in trades]
        if not pnls:
            return {}
        results = [np.sum(np.random.choice(pnls, size=len(pnls), replace=True)) for _ in range(n_sims)]
        return {
            "mean": float(np.mean(results)),
            "p5": float(np.percentile(results, 5)),
            "p95": float(np.percentile(results, 95)),
            "prob_loss": float(np.mean(np.array(results) < 0)),
        }