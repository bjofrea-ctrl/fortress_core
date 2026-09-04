from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.core.adaptive_risk import REGIME_THRESHOLDS, AdaptiveRiskManager
from app.core.indicators import calculate_all_indicators
from app.core.market_structure import market_structure_history, structure_row_to_dict
from app.core.probabilistic_engine import (
    BayesianOnlineUpdater,
    CopulaRiskAnalyzer,
    FatTailMonteCarlo,
    ProbabilityCalibrator,
    SignalQualityMetrics,
    WalkForwardValidator,
    circular_block_bootstrap_ci,
)
from app.core.regime_classifier import GlobalRegimeClassifier
from app.core.signal_engine import SignalEngine

CALIBRATION_HORIZON_DAYS = 20  # ~1 mes hábil, alineado a "short_term_1_30d"
CALIBRATION_STRIDE_DAYS = 5    # semanal, misma cadencia que el rebalanceo real
REGIME_REFIT_STRIDE_DAYS = 63  # ~trimestral: antes el HMM se fiteaba una sola vez y nunca más
CALIBRATOR_REFIT_STRIDE_DAYS = 63    # misma cadencia trimestral, mismo motivo
CALIBRATOR_ROLLING_WINDOW_DAYS = 730  # ~2 años calendario, similar al train_window de WalkForwardValidator

# T1.6: techo de la fuerza de evidencia por outcome (en unidades de riesgo/R).
# Un outcome de 0.2R pesa como 1 observación (piso); uno de 12R pesa 10 (cap).
BAYES_EVIDENCE_STRENGTH_CAP = 10.0


class BacktestEngine:
    def __init__(self, initial_capital: float = 25000.0):
        self.initial_capital = initial_capital
        self.regime_classifier = GlobalRegimeClassifier()
        self.bayesian_updater = BayesianOnlineUpdater()
        self.signal_engine = SignalEngine(self.regime_classifier, bayesian_updater=self.bayesian_updater)

    def _make_risk_manager(self) -> "AdaptiveRiskManager":
        """Factory hook (refactor aditivo, 2026-08-13, §20): permite a un trial
        inyectar un risk manager por subclase sin duplicar run(). Default:
        AdaptiveRiskManager(idéntico al comportamiento previo)."""
        return AdaptiveRiskManager(self.initial_capital)

    def _build_calibration_dataset(
        self, indicators_cache: Dict[str, pd.DataFrame], train_end_date: datetime,
        update_bayesian: bool = True, train_start_date: datetime = None,
        execution_lag_days: int = 1,
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
                # Precio de entrada con el MISMO lag de ejecución que el loop
                # principal: con execution_lag_days>=1 la señal emitida con el
                # cierre de 'i' se ejecuta en la apertura de 'i+1' (primera
                # oportunidad real de operar). Con 0 se conserva el sesgo
                # original (señal y ejecución en la misma barra, cierre de 'i').
                if execution_lag_days >= 1:
                    entry = train_df["open"].iloc[i + 1]
                else:
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

        # T1.6: la señal de fuerza del outcome es pnl_r (retorno en unidades de
        # riesgo), no solo el signo. Riesgo por unidad = entry * position_stop del
        # régimen (el stop que habría cerrado la posición). strength = |pnl_r|
        # acotado: un outcome de 0.2R pesa como 1 observación; uno de 5R pesa 5.
        entry = float(pos.get("entry_price") or 0.0)
        shares = float(pos.get("shares") or 0.0)
        stop = REGIME_THRESHOLDS.get(regime, REGIME_THRESHOLDS[0])["position_stop"]
        risk_dollars = entry * shares * stop
        pnl_r = (pnl / risk_dollars) if risk_dollars > 0 else (1.0 if won else -1.0)
        strength = min(max(abs(pnl_r), 1.0), BAYES_EVIDENCE_STRENGTH_CAP)

        for factor, score in factors.items():
            if factor not in priors:
                continue  # p.ej. sentiment_v1: el blend es externo al BMA, sin prior propio
            predicted_up = score > 0.5
            self.bayesian_updater.update(
                f"{regime}_{factor}", correct=(predicted_up == won), base_weight=priors[factor],
                strength=strength,
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
        slippage=0.0005,
        sentiment_data: Dict = None,
        fundamentals_by_symbol: Dict[str, pd.Series] = None,
        track_capital_usage: bool = False,
        execution_lag_days: int = 1,
        use_market_structure: bool = False,
    ) -> Dict:
        """Corre el backtest end-of-day.

        execution_lag_days controla el timing de ejecución relativo a la barra
        que genera la señal (T0.2, PLAN_INTEGRACION_INDICAGENT.md):
          - execution_lag_days=0: comportamiento ANTERIOR (el bug). La señal se
            calcula con el cierre de 'date' y la ejecución (compra/venta) ocurre
            al cierre de ESA MISMA barra 'date' — imposible en trading real, el
            cierre oficial no está disponible para operar hasta después de cerrar.
          - execution_lag_days=1 (default NUEVO): la decisión se toma con el
            cierre de 'date' pero la ejecución ocurre en la APERTURA de la barra
            siguiente disponible ('date+1'): precio de entrada = open[date+1],
            fecha de entrada = date+1; y un stop/target detectado con el cierre
            de 'date' se ejecuta en open[date+1].
        El criterio de selección (score/factores/ATR calculados con datos de
        'date') NO cambia — solo el precio/fecha de ejecución.

        use_market_structure (T1.4, PLAN_INTEGRACION_INDICAGENT.md): si True,
        precomputa la historia CAUSAL de estructura de mercado por símbolo
        (``market_structure_history`` — swings confirmados con lag de
        `neighbor` barras, mitigación/relleno/reclaim visibles recién al
        completarse) y le pasa a ``generate_signal`` la fila correspondiente a
        'date'. Activa la resolución estructural de stop/target y la puerta
        RR ≥ MIN_RR. Con False (default) el camino es BIT-IDÉNTICO al anterior.
        """
        indicators_cache = {s: calculate_all_indicators(df) for s, df in price_data.items()}
        # T1.4: historia causal de estructura precomputada UNA vez por símbolo
        # (nunca por fecha dentro del loop — nota de performance del ticket).
        structure_history = {}
        if use_market_structure:
            for s, df in price_data.items():
                structure_history[s] = market_structure_history(
                    df, atr=indicators_cache[s]["atr14"].reindex(df.index)
                    if s in indicators_cache else None)
        train_market = {s: df[df.index < start_date] for s, df in market_data.items()}
        self.regime_classifier.fit(train_market)

        # Señal de RANKING G2 (H7-OOS): blend 0.50 sobre rankings causales
        # [-1,1], precomputada por símbolo. El gate de entrada sigue usando
        # el score técnico puro (generate_signal); G2 sólo reordena las
        # oportunidades candidatas (ver SignalEngine.compute_g2_rank_scores).
        g2_by_symbol = {}
        if sentiment_data:
            for symbol, df in indicators_cache.items():
                g2_by_symbol[symbol] = self.signal_engine.compute_g2_rank_scores(df, sentiment_data)

        # Señal de RANKING G3 (trial 0b-v2-fund, Fase 1): mismo patrón que
        # G2 pero con el score fundamental point-in-time del panel EDGAR
        # (0.5*rank(score técnico) + 0.5*rank(score fundamental)). Símbolos
        # sin cobertura (ETFs) no reciben g3_score -> el ranking usa el
        # score puro (monótono en rank_tech, mismo orden).
        g3_by_symbol = {}
        if fundamentals_by_symbol:
            for symbol, df in indicators_cache.items():
                if symbol in fundamentals_by_symbol:
                    g3_by_symbol[symbol] = self.signal_engine.compute_g3_rank_scores(
                        df, fundamentals_by_symbol[symbol]
                    )

        calibrator = ProbabilityCalibrator(method="platt")
        cal_scores, cal_outcomes = self._build_calibration_dataset(
            indicators_cache, start_date, execution_lag_days=execution_lag_days
        )
        calibrator.fit(cal_scores, cal_outcomes)

        risk_manager = self._make_risk_manager()
        equity, cash = self.initial_capital, self.initial_capital
        positions: Dict[str, Dict] = {}
        equity_curve, trades = [], []
        capital_usage_log = [] if track_capital_usage else None

        spy = market_data.get("SPY")
        dates = spy[(spy.index >= start_date) & (spy.index <= end_date)].index
        last_regime_refit = start_date
        last_calibrator_refit = start_date

        for i, date in enumerate(dates):
            # Día de ejecución de las decisiones tomadas con el cierre de 'date'
            # (T0.2): la primera oportunidad real de operar con esa información es
            # la apertura de la siguiente barra hábil. None = fin de la serie.
            next_date = dates[i + 1] if i + 1 < len(dates) else None
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
                if shares_to_sell <= 0:
                    continue
                # T0.2: un stop detectado con el cierre de 'date' se ejecuta en la
                # apertura de la barra siguiente (lag=1); con lag=0, al cierre de
                # 'date' (comportamiento anterior).
                if (execution_lag_days >= 1 and next_date is not None
                        and symbol in indicators_cache
                        and next_date in indicators_cache[symbol].index):
                    exit_price = float(indicators_cache[symbol].loc[next_date, "open"]) * (1 - slippage)
                    exit_date = next_date
                else:
                    exit_price = current_prices.get(symbol, pos["entry_price"]) * (1 - slippage)
                    exit_date = date
                cash += exit_price * shares_to_sell * (1 - commission)
                pnl = (exit_price - pos["entry_price"]) * shares_to_sell
                self._update_bayesian_weights(pos, pnl)

                trades.append({
                    "symbol": symbol,
                    "entry_date": pos["entry_date"],
                    "exit_date": exit_date,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "shares": shares_to_sell,
                    "pnl": pnl,
                    "exit_reason": reason,
                    "g2_score": pos.get("g2_score"),
                    "g3_score": pos.get("g3_score"),
                    "win_prob": pos.get("win_prob"),
                    "regime_state": pos.get("regime_state"),
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
                        # T0.2: misma regla que los stops — salida técnica detectada
                        # con el cierre de 'date' se ejecuta en la apertura de la
                        # siguiente barra (lag=1); con lag=0, al cierre de 'date'.
                        if (execution_lag_days >= 1 and next_date is not None
                                and next_date in indicators_cache[symbol].index):
                            exit_price = float(indicators_cache[symbol].loc[next_date, "open"]) * (1 - slippage)
                            exit_date = next_date
                        else:
                            exit_price = row.close * (1 - slippage)
                            exit_date = date
                        cash += exit_price * pos["shares"] * (1 - commission)
                        pnl = (exit_price - pos["entry_price"]) * pos["shares"]
                        self._update_bayesian_weights(pos, pnl)

                        trades.append({
                            "symbol": symbol,
                            "entry_date": pos["entry_date"],
                            "exit_date": exit_date,
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "shares": pos["shares"],
                            "pnl": pnl,
                            "exit_reason": "TECHNICAL",
                            "g2_score": pos.get("g2_score"),
                            "g3_score": pos.get("g3_score"),
                            "win_prob": pos.get("win_prob"),
                            "regime_state": pos.get("regime_state"),
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
                        indicators_cache, date, update_bayesian=False, train_start_date=refit_start,
                        execution_lag_days=execution_lag_days,
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
                        ms_row = None
                        if use_market_structure and symbol in structure_history:
                            sh = structure_history[symbol]
                            if date in sh.index:
                                # historia causal: la fila de 'date' usa solo datos ≤ date
                                ms_row = structure_row_to_dict(sh.loc[date])
                        sig = self.signal_engine.generate_signal(
                            df.loc[:date], symbol, regime_info["state"],
                            market_structure=ms_row)
                        if sig:
                            if g2_by_symbol:
                                g2 = g2_by_symbol[symbol].loc[date]
                                if pd.notna(g2):
                                    sig["g2_score"] = float(g2)
                            if g3_by_symbol:
                                g3_series = g3_by_symbol.get(symbol)
                                if g3_series is not None:
                                    g3 = g3_series.loc[date]
                                    if pd.notna(g3):
                                        sig["g3_score"] = float(g3)
                            signals.append(sig)

                signals = self.signal_engine.rank_signals(signals)
                current_exposure = positions_value / equity if equity > 0 else 0
                signals = self.signal_engine.filter_by_regime_exposure(
                    signals, regime_info["state"], current_exposure
                )

                if capital_usage_log is not None:
                    capital_usage_log.append({
                        "date": date,
                        "regime": regime_info["state"],
                        "regime_name": regime_info["state_name"],
                        "equity": equity,
                        "cash": cash,
                        "positions_value": positions_value,
                        "n_positions": len(positions),
                        "n_gate_signals": len(signals),
                        "capital_deployed_pct": (positions_value + cash) and (positions_value / (positions_value + cash)),
                    })

                for sig in signals[:5]:
                    if sig["symbol"] in positions:
                        continue

                    symbol = sig["symbol"]
                    # T0.2: la señal se generó con el cierre de 'date'; con
                    # execution_lag_days>=1 la ejecución ocurre en la apertura de
                    # la siguiente barra hábil (real_entry = open[next_date]). El
                    # score/factores/ATR de 'date' siguen siendo el INSUMO de la
                    # decisión — solo cambia el precio/fecha de ejecución.
                    use_lag = (
                        execution_lag_days >= 1 and next_date is not None
                        and symbol in indicators_cache
                        and next_date in indicators_cache[symbol].index
                    )
                    if use_lag:
                        real_entry = float(indicators_cache[symbol].loc[next_date, "open"])
                        entry_date = next_date
                    else:
                        real_entry = sig["entry_price"]
                        entry_date = date

                    win_prob = float(calibrator.predict(np.array([sig["score"]]))[0])
                    shares = risk_manager.compute_position_size(
                        equity, real_entry, sig["atr"],
                        win_prob=win_prob, payoff_ratio=sig["payoff_ratio"],
                        symbol=symbol,
                    )
                    cost = real_entry * shares * (1 + slippage) * (1 + commission)

                    if shares > 0 and cost < cash:
                        cash -= cost
                        positions[symbol] = {
                            "shares": shares,
                            "entry_price": real_entry,
                            "entry_date": entry_date,
                            "regime_state": sig["regime_state"],
                            "factors": sig["factors"],
                            "g2_score": sig.get("g2_score"),
                            "g3_score": sig.get("g3_score"),
                            "win_prob": win_prob,
                        }
                        risk_manager.register_entry(symbol, real_entry, shares)

        return {
            "equity_curve": equity_curve,
            "trades": trades,
            "risk_events": risk_manager.state.risk_events,
            "capital_usage_log": capital_usage_log,
            "metrics": self.calculate_metrics(equity_curve, trades),
            "monte_carlo": self.monte_carlo_simulation(trades, equity_curve=equity_curve),
            "signal_quality": self.validate_signal_quality(indicators_cache, start_date, end_date),
            "portfolio_tail_risk": self.analyze_portfolio_tail_risk(price_data, start_date, end_date),
        }

    # A6 (PLAN_REMEDIO_BRECHAS_20260903 §A6): n_trials por default se lee del
    # ledger de la familia `signal_diagnosis` (los trials reales de la
    # familia, no un número mágico). Antes era 5 hardcodeado (conteo manual
    # de las 5 variantes que se probaron en la sesión original) — eso
    # sub-deflacionaba el DSR desde el momento en que la familia superó
    # ese tamaño. Callers que ya pasan n_trials explícito (p.ej.
    # trial_evt_stops_v2.py, validacion_oos_fresca_mom_rsi.py) NO cambian:
    # su número es el correcto para su contexto, no la corrección de A6.
    # Si el ledger no está disponible (test con tmp_path, sandbox, etc.),
    # se cae a un fallback explícito con `n_trials_fallback_reason` en el
    # payload — nunca un default silencioso que mimetice el bug original.
    DEFAULT_N_TRIALS = None  # sentinel: el número se resuelve en runtime

    def _resolve_default_n_trials(self) -> Tuple[int, Optional[str]]:
        """Lee `consumed_budget('signal_diagnosis')` del ledger.

        Devuelve (n_trials:int, fallback_reason:Optional[str]).
        Si el ledger no está disponible (import roto, archivo corrupto,
        path a un tmp que no tiene trial_registry.json), devuelve el
        fallback documentado en el payload — NUNCA un número silencioso.
        El fallback es la opción más conservadora: el mayor N conocido
        públicamente (29 al cierre del plan, 2026-09-03) para que el DSR
        no se INFLATE por sub-deflacionar en un error de lectura.
        """
        try:
            from app.core.trial_registry import consumed_budget
            n = consumed_budget("signal_diagnosis")
            if isinstance(n, int) and n >= 1:
                return n, None
            return 29, f"ledger devolvió valor no-entero o <1: {n!r}"
        except Exception as exc:  # noqa: BLE001 — el logging del motivo es lo que importa
            return 29, f"ledger no disponible: {type(exc).__name__}: {exc}"

    def calculate_metrics(self, equity_curve: List[Dict], trades: List[Dict],
                          n_trials: Optional[int] = DEFAULT_N_TRIALS) -> Dict:
        if not equity_curve:
            return {}

        # A6 (PLAN_REMEDIO_BRECHAS_20260903 §A6): si el caller NO pasó
        # n_trials (o pasó None explícito), lo resolvemos del ledger. El
        # resolver nunca falla silencioso: si el ledger no está disponible,
        # devuelve el fallback conservador (29) + razón en el payload.
        n_trials_source = "explicit"  # default: caller pasó n_trials
        n_trials_fallback_reason: Optional[str] = None
        if n_trials is None:
            n_trials, n_trials_fallback_reason = self._resolve_default_n_trials()
            n_trials_source = "ledger"
            if n_trials_fallback_reason is not None:
                # Log al stderr para que aparezca en pipeline_diario.log y
                # en cualquier job que capture la salida del motor. La
                # trazabilidad del fallback es parte del contrato A6.
                import sys as _sys
                print(
                    f"[A6] n_trials fallback usado: "
                    f"n_trials={n_trials} | razón: {n_trials_fallback_reason}",
                    file=_sys.stderr,
                )

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
        # Auditado 2026-08-10 (Fase 0b): sr_std usa ahora la varianza
        # completa de Lo (2002) con skewness y kurtosis reales (el paper
        # original exige 1 - γ3·SR + (γ4-1)/4·SR² en el denominador);
        # asumir normalidad (γ3=0, γ4=3) sobre-estimaba el DSR con colas
        # gruesas. Clampeado a >= 1e-8 por si skew/kurt producen varianza
        # negativa en muestras cortas.
        gamma = 0.5772156649
        e_max_sr = ((1 - gamma) * norm.ppf(1 - 1 / n_trials) + gamma * norm.ppf(1 - 1 / (n_trials * np.e)))
        sr_daily = returns.mean() / returns.std() if returns.std() > 0 else 0
        if len(returns) > 3:
            skew = float(returns.skew())
            kurt = float(returns.kurtosis())
            var_num = max(1.0 - skew * sr_daily + (kurt - 1) / 4.0 * sr_daily ** 2, 1e-8)
            sr_std = np.sqrt(var_num / (len(returns) - 1))
            sr_0 = sr_std * e_max_sr
            deflated_sharpe = float(norm.cdf((sr_daily - sr_0) / sr_std))
        else:
            deflated_sharpe = 0.0

        # T2.2 — Intervalos de confianza por bootstrap de bloques circulares
        # (PLAN_INTEGRACION_INDICAGENT.md). La serie de retornos real de un
        # backtest está autocorrelacionada: un CI asintótico ingenuo la
        # subestima. El bloque circular preserva esa dependencia dentro de
        # cada bloque. Complementa al Deflated Sharpe (punto ajustado por
        # n_trials) con un intervalo, no solo un punto. Seed fijo → CI
        # reproducible entre corridas; la función usa un Generator local,
        # no estado global de numpy.
        returns_arr = returns.values

        def _sharpe_stat(r: np.ndarray) -> float:
            return float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if r.std(ddof=1) > 0 else 0.0

        def _cagr_stat(r: np.ndarray) -> float:
            return float(np.expm1(252.0 * np.mean(np.log1p(r)))) if len(r) else 0.0

        def _max_dd_stat(r: np.ndarray) -> float:
            eq = np.cumprod(1 + r)
            peak = np.maximum.accumulate(eq)
            # * 100: mismas unidades que el max_drawdown puntual (drawdown_pct)
            return float((eq / peak - 1).min() * 100)

        sharpe_ci = circular_block_bootstrap_ci(returns_arr, _sharpe_stat, seed=42)
        cagr_ci = circular_block_bootstrap_ci(returns_arr, _cagr_stat, seed=42)
        max_dd_ci = circular_block_bootstrap_ci(returns_arr, _max_dd_stat, seed=42)

        return {
            "cagr": float(cagr),
            "sharpe_ratio": float(sharpe),
            "sharpe_ci": sharpe_ci,
            "cagr_ci": cagr_ci,
            "max_drawdown_ci": max_dd_ci,
            "sortino_ratio": float(sortino),
            "max_drawdown": float(max_dd),
            "calmar_ratio": float(calmar),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "total_trades": len(trades),
            "deflated_sharpe": deflated_sharpe,
            "deflated_sharpe_n_trials": n_trials,
            # A6: trazabilidad del default. "explicit" = caller pasó n_trials
            # (caso normal en trials pre-registrados). "ledger" = se resolvió
            # del registry al vuelo (default del motor). Si el resolver cayó
            # al fallback, la razón queda en `n_trials_fallback_reason`.
            "n_trials_source": n_trials_source,
            "n_trials_fallback_reason": n_trials_fallback_reason,
        }

    def monte_carlo_simulation(self, trades: List[Dict], equity_curve: List[Dict] = None,
                               n_sims: int = 1000, seed: Optional[int] = 42) -> Dict:
        """
        Combina dos Monte Carlo distintos, no uno reemplaza al otro:
        - bootstrap: resamplea el PNL de los trades ya ocurridos (testea
          sensibilidad al ORDEN de los trades, con la magnitud ya observada).
        - fat_tail: simula retornos DIARIOS con t-Student (colas más gruesas
          que la normal) y da VaR/ES vía Cornish-Fisher — testea la
          MAGNITUD de escenarios que todavía no se observaron en el backtest.

        Args:
            seed: Semilla del RNG local (np.random.default_rng). Mismo patrón
                que `circular_block_bootstrap_ci` en probabilistic_engine.py:754
                (T2.2). Con seed fijo la función es determinista (requisito de
                reproducibilidad en tests y en re-ejecuciones del backtest).
                `None` → no determinista.
        """
        pnls = [t["pnl"] for t in trades]
        bootstrap = {}
        if pnls:
            pnls_arr = np.asarray(pnls, dtype=float)
            rng = np.random.default_rng(seed)
            # Mismo patrón que T2.2: default_rng(seed) en vez de np.random.choice
            # (que usa el global state y no es reproducible). Vectorizado: una
            # sola llamada a rng.choice con n_sims×len(pnls) reemplaza el
            # list-comprehension de n_sims invocaciones a np.random.choice.
            sample_idx = rng.integers(0, len(pnls_arr), size=(n_sims, len(pnls_arr)))
            results = pnls_arr[sample_idx].sum(axis=1)
            bootstrap = {
                "mean": float(np.mean(results)),
                "p5": float(np.percentile(results, 5)),
                "p95": float(np.percentile(results, 95)),
                "prob_loss": float(np.mean(np.array(results) < 0)),
                "seed": seed,
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
