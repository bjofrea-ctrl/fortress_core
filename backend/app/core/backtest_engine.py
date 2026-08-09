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
    FatTailMonteCarlo, CopulaRiskAnalyzer,
)

CALIBRATION_HORIZON_DAYS = 20  # ~1 mes hábil, alineado a "short_term_1_30d"
CALIBRATION_STRIDE_DAYS = 5    # semanal, misma cadencia que el rebalanceo real
REGIME_REFIT_STRIDE_DAYS = 63  # ~trimestral: antes el HMM se fiteaba una sola vez y nunca más
CALIBRATOR_REFIT_STRIDE_DAYS = 63    # misma cadencia trimestral, mismo motivo
CALIBRATOR_ROLLING_WINDOW_DAYS = 730  # ~2 años calendario, similar al train_window de WalkForwardValidator


class BacktestEngine:
    def __init__(self, initial_capital: float = 25000.0):
        self.initial_capital = initial_capital
        self.regime_classifier = GlobalRegimeClassifier()
        self.bayesian_updater = BayesianOnlineUpdater()
        self.signal_engine = SignalEngine(self.regime_classifier, bayesian_updater=self.bayesian_updater)

    def _build_calibration_dataset(
        self, indicators_cache: Dict[str, pd.DataFrame], train_end_date: datetime,
        update_bayesian: bool = True, train_start_date: datetime = None,
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

        update_bayesian=False evita ese warm-start — necesario para refits
        periódicos del calibrador (walk-forward real): si se repitiera el
        warm-start en cada refit, la evidencia de los primeros años se
        re-contaría cada vez que la ventana se expande, sesgando el
        posterior Bayesiano hacia la historia temprana en vez de aprender
        online de verdad.
        """
        scores, outcomes = [], []
        priors = self.signal_engine.factor_weights[0]
        for symbol, df in indicators_cache.items():
            train_df = df[df.index < train_end_date]
            if train_start_date is not None:
                train_df = train_df[train_df.index >= train_start_date]
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

                if update_bayesian:
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

    def analyze_portfolio_tail_risk(
        self, price_data: Dict[str, pd.DataFrame], start_date: datetime, end_date: datetime,
    ) -> Dict:
        """
        Dependencia de cola (cópulas Clayton/Gumbel) entre TODOS los pares
        de símbolos operados en el backtest — no macro genérico, que usa
        nombres de clave (DXY/gold/silver) que no coinciden con los tickers
        reales que pasa run_backtest.py. Esto es lo que de verdad importa
        para el riesgo de cartera: si dos posiciones simultáneas se caen
        juntas en la cola, el position sizing por activo (Kelly) no lo ve,
        porque Kelly es de un solo activo a la vez.
        """
        analyzer = CopulaRiskAnalyzer()
        symbols = list(price_data.keys())
        pairs = {}
        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i + 1:]:
                df_a = price_data[sym_a]
                df_b = price_data[sym_b]
                window_a = df_a[(df_a.index >= start_date) & (df_a.index <= end_date)]
                window_b = df_b[(df_b.index >= start_date) & (df_b.index <= end_date)]
                ret_a = window_a["close"].pct_change().dropna()
                ret_b = window_b["close"].pct_change().dropna()
                common_idx = ret_a.index.intersection(ret_b.index)
                if len(common_idx) < 30:
                    continue
                result = analyzer.analyze_pair(
                    ret_a.loc[common_idx].values, ret_b.loc[common_idx].values, sym_a, sym_b
                )
                if "error" not in result:
                    pairs[f"{sym_a}_{sym_b}"] = result

        if not pairs:
            return {"error": "Datos insuficientes para análisis de cópulas"}

        high_risk_pairs = [p for p, r in pairs.items() if r["risk_level"] == "ALTO"]
        return {
            "pairs": pairs,
            "high_tail_risk_pairs": high_risk_pairs,
            "n_pairs_analyzed": len(pairs),
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
        last_regime_refit = start_date
        last_calibrator_refit = start_date

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
                if (date - last_calibrator_refit).days >= CALIBRATOR_REFIT_STRIDE_DAYS:
                    # Walk-forward real del calibrador: antes se fiteaba una
                    # sola vez antes de start_date y nunca más -mismo bug que
                    # tenía el HMM-. Ventana móvil (no expansiva) de ~2 años
                    # para no reprocesar toda la historia en cada refit, y
                    # update_bayesian=False para no re-contar evidencia
                    # temprana en el BayesianOnlineUpdater.
                    refit_start = date - pd.Timedelta(days=CALIBRATOR_ROLLING_WINDOW_DAYS)
                    new_scores, new_outcomes = self._build_calibration_dataset(
                        indicators_cache, date, update_bayesian=False, train_start_date=refit_start
                    )
                    if len(new_scores) >= 20:
                        calibrator.fit(new_scores, new_outcomes)
                    last_calibrator_refit = date

                if (date - last_regime_refit).days >= REGIME_REFIT_STRIDE_DAYS:
                    # Walk-forward real: reentrena con la ventana expansiva
                    # hasta 'date' en vez de usar para siempre el fit hecho
                    # antes de start_date.
                    try:
                        self.regime_classifier.fit({s: df[df.index < date] for s, df in market_data.items()})
                        last_regime_refit = date
                    except ValueError:
                        pass  # ventana insuficiente todavía, seguir con el modelo anterior

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
            "monte_carlo": self.monte_carlo_simulation(trades, equity_curve=equity_curve),
            "signal_quality": self.validate_signal_quality(indicators_cache, start_date, end_date),
            "portfolio_tail_risk": self.analyze_portfolio_tail_risk(price_data, start_date, end_date),
        }

    # Deflated Sharpe (Bailey & López de Prado): n_trials debe reflejar
    # cuántas variantes de la estrategia se compararon antes de quedarse con
    # ésta -no un número mágico-. Contando las corridas completas de
    # backtest efectivamente comparadas en esta sesión sobre este mismo
    # pipeline (signal_engine + backtest_engine): (1) baseline momentum+
    # technical fijo, (2) +Kelly+calibración Platt, (3) +BMA Bayesiano,
    # (4) +score técnico reponderado por IC medido, (5) +walk-forward real
    # del HMM de régimen. Actualizar este número si se prueban más variantes.
    DEFAULT_N_TRIALS = 5

    def calculate_metrics(self, equity_curve: List[Dict], trades: List[Dict],
                          n_trials: int = DEFAULT_N_TRIALS) -> Dict:
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

        # Deflated Sharpe (Bailey & López de Prado 2014): debe calcularse en
        # la frecuencia nativa de 'returns' (diaria), no con el Sharpe ya
        # anualizado — mezclar ambos invalidaba el z-score y hacía que
        # n_trials casi no afectara el resultado (auditado y confirmado:
        # saturaba en ~1.0 para cualquier n_trials con backtests de varios
        # cientos de días). SR_0 debe escalarse por sr_std (el error
        # estándar del estimador), no dividirse por sqrt(T) de nuevo.
        gamma = 0.5772156649
        e_max_sr = ((1 - gamma) * norm.ppf(1 - 1 / n_trials) + gamma * norm.ppf(1 - 1 / (n_trials * np.e)))
        sr_daily = returns.mean() / returns.std() if returns.std() > 0 else 0
        if len(returns) > 1:
            sr_std = np.sqrt((1 + 0.5 * sr_daily ** 2) / (len(returns) - 1))
            sr_0 = sr_std * e_max_sr
            deflated_sharpe = float(norm.cdf((sr_daily - sr_0) / sr_std))
        else:
            deflated_sharpe = 0.0

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
            "deflated_sharpe_n_trials": n_trials,
        }

    def monte_carlo_simulation(self, trades: List[Dict], equity_curve: List[Dict] = None,
                               n_sims: int = 1000) -> Dict:
        """
        Combina dos Monte Carlo distintos, no uno reemplaza al otro:
        - bootstrap: resamplea el PNL de los trades ya ocurridos (testea
          sensibilidad al ORDEN de los trades, con la magnitud ya observada).
        - fat_tail: simula retornos DIARIOS con t-Student (colas más gruesas
          que la normal) y da VaR/ES vía Cornish-Fisher — testea la
          MAGNITUD de escenarios que todavía no se observaron en el backtest.
        """
        pnls = [t["pnl"] for t in trades]
        bootstrap = {}
        if pnls:
            results = [np.sum(np.random.choice(pnls, size=len(pnls), replace=True)) for _ in range(n_sims)]
            bootstrap = {
                "mean": float(np.mean(results)),
                "p5": float(np.percentile(results, 5)),
                "p95": float(np.percentile(results, 95)),
                "prob_loss": float(np.mean(np.array(results) < 0)),
            }

        fat_tail = {}
        if equity_curve:
            df = pd.DataFrame(equity_curve).set_index("date")
            returns = df["equity"].pct_change().dropna().values
            if len(returns) >= 20:
                fat_tail = FatTailMonteCarlo(n_sims=n_sims).monte_carlo_metrics(
                    returns, initial_equity=self.initial_capital
                )

        return {"bootstrap": bootstrap, "fat_tail": fat_tail}