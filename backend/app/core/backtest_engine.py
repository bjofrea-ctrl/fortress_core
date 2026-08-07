import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime
from scipy.stats import norm
from app.core.signal_engine import SignalEngine
from app.core.adaptive_risk import AdaptiveRiskManager
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.indicators import calculate_all_indicators
from app.core.probabilistic_engine import ProbabilityCalibrator

CALIBRATION_HORIZON_DAYS = 20  # ~1 mes hábil, alineado a "short_term_1_30d"
CALIBRATION_STRIDE_DAYS = 5    # semanal, misma cadencia que el rebalanceo real


class BacktestEngine:
    def __init__(self, initial_capital: float = 25000.0):
        self.initial_capital = initial_capital
        self.regime_classifier = GlobalRegimeClassifier()
        self.signal_engine = SignalEngine(self.regime_classifier)

    def _build_calibration_dataset(
        self, indicators_cache: Dict[str, pd.DataFrame], train_end_date: datetime
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Replay histórico previo a train_end_date: por cada fecha (cadencia semanal)
        genera la señal que se habría emitido y la etiqueta como win/loss según el
        precio CALIBRATION_HORIZON_DAYS hábiles después. Usa regime_state=0 como
        aproximación (los filtros de entrada no cambian por régimen, salvo el
        bloqueo en régimen 3, que de todos modos no genera señal).
        """
        scores, outcomes = [], []
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
                scores.append(sig["score"])
                outcomes.append(1.0 if future > entry else 0.0)
        return np.array(scores), np.array(outcomes)

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
                        }
                        risk_manager.register_entry(sig["symbol"], sig["entry_price"], shares)

        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "risk_events": risk_manager.state.risk_events,
            "metrics": self.calculate_metrics(equity_curve, trades),
            "monte_carlo": self.monte_carlo_simulation(trades),
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