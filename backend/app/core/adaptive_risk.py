from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from app.config import settings

REGIME_THRESHOLDS = {
    0: {"position_stop": 0.05, "portfolio_stop": 0.05, "max_exposure": 1.00, "cooldown_days": 5},
    1: {"position_stop": 0.07, "portfolio_stop": 0.07, "max_exposure": 0.70, "cooldown_days": 5},
    2: {"position_stop": 0.08, "portfolio_stop": 0.10, "max_exposure": 0.40, "cooldown_days": 10},
    3: {"position_stop": 0.03, "portfolio_stop": 0.03, "max_exposure": 0.20, "cooldown_days": 15},
}


@dataclass
class RiskState:
    equity_peak: float
    entry_reference: Dict[str, float] = field(default_factory=dict)
    highest_price: Dict[str, float] = field(default_factory=dict)
    positions: Dict[str, int] = field(default_factory=dict)
    cooldown_until: Optional[datetime] = None
    risk_events: List[Dict] = field(default_factory=list)
    current_regime: int = 0


class AdaptiveRiskManager:
    def __init__(self, initial_equity: float):
        self.state = RiskState(equity_peak=initial_equity)
        self.ABSOLUTE_CEILING = settings.ABSOLUTE_CEILING
        self.RISK_PER_TRADE = settings.RISK_PER_TRADE
        self.MAX_POSITION_PCT = settings.MAX_POSITION_PCT
        self.VIOLATION_WINDOW_DAYS = settings.VIOLATION_WINDOW_DAYS

    def get_thresholds(self) -> dict:
        return REGIME_THRESHOLDS.get(self.state.current_regime, REGIME_THRESHOLDS[0])

    def update_regime(self, regime_state: int) -> None:
        self.state.current_regime = regime_state

    def update_peak(self, equity: float) -> None:
        self.state.equity_peak = max(self.state.equity_peak, equity)

    def drawdown_from_peak(self, equity: float) -> float:
        return (equity - self.state.equity_peak) / self.state.equity_peak

    def loss_from_entry(self, symbol: str, price: float) -> float:
        entry = self.state.entry_reference.get(symbol)
        return 0.0 if entry is None else (price - entry) / entry

    def compute_position_size(self, equity: float, price: float, atr: float) -> int:
        if atr <= 0 or price <= 0:
            return 0
        thresholds = self.get_thresholds()
        stop_distance = max(2.0 * atr, price * thresholds["position_stop"])
        shares_by_risk = (equity * self.RISK_PER_TRADE) / stop_distance
        max_shares = (equity * self.MAX_POSITION_PCT) / price
        return int(min(shares_by_risk, max_shares))

    def check_all_stops(
        self,
        equity: float,
        current_prices: Dict[str, float],
        atrs: Dict[str, float],
        date: datetime
    ) -> List[Tuple[str, str]]:
        to_close = []
        thresholds = self.get_thresholds()

        for symbol, shares in list(self.state.positions.items()):
            if shares <= 0:
                continue
            price = current_prices.get(symbol)
            if price is None:
                continue

            entry = self.state.entry_reference.get(symbol)
            loss = self.loss_from_entry(symbol, price)

            if loss <= -self.ABSOLUTE_CEILING:
                to_close.append((symbol, "ABSOLUTE_CEILING_BREACH"))
                self._log(date, "CRITICAL", symbol, f"CEILING VIOLADO ({loss:.2%})", "LIQUIDATE_ALL", True)
                continue

            if loss <= -thresholds["position_stop"]:
                to_close.append((symbol, "REGIME_STOP_HIT"))
                self._log(date, "HIGH", symbol, f"Stop régimen: {loss:.2%}", "CLOSE_POSITION", False)
                continue

            if entry is None:
                continue

            atr_val = atrs.get(symbol, 0)

            if atr_val and (price - entry) >= 2.0 * atr_val:
                to_close.append((symbol, "PARTIAL_TP"))

            high = self.state.highest_price.get(symbol, entry)
            self.state.highest_price[symbol] = max(high, price)
            if atr_val and (self.state.highest_price[symbol] - entry) > 1.5 * atr_val:
                trailing = self.state.highest_price[symbol] - 2.0 * atr_val
                if price <= trailing:
                    to_close.append((symbol, "TRAILING_STOP"))

        dd = self.drawdown_from_peak(equity)
        if dd <= -self.ABSOLUTE_CEILING:
            for symbol in list(self.state.positions.keys()):
                to_close.append((symbol, "PORTFOLIO_CEILING_BREACH"))
            self._log(date, "CRITICAL", None, f"CEILING cartera: {dd:.2%}", "TOTAL_LIQUIDATION", True)
            self.trigger_cooldown(date)
        elif dd <= -thresholds["portfolio_stop"]:
            for symbol in list(self.state.positions.keys()):
                to_close.append((symbol, "PORTFOLIO_REGIME_STOP"))
            self._log(date, "CRITICAL", None, f"Stop cartera: {dd:.2%}", "PARTIAL_LIQUIDATION_50PCT", True)
            self.trigger_cooldown(date)

        return to_close

    def check_technical_exit(self, adx: float, close: float, ema20: float, ema50: float) -> bool:
        return adx < 20 or (close < ema20 < ema50)

    def register_entry(self, symbol: str, entry_price: float, shares: int) -> None:
        self.state.entry_reference[symbol] = entry_price
        self.state.highest_price[symbol] = entry_price
        self.state.positions[symbol] = self.state.positions.get(symbol, 0) + shares

    def register_exit(self, symbol: str, shares_to_exit: int) -> None:
        remaining = self.state.positions.get(symbol, 0) - shares_to_exit
        if remaining <= 0:
            self.state.entry_reference.pop(symbol, None)
            self.state.highest_price.pop(symbol, None)
            self.state.positions.pop(symbol, None)
        else:
            self.state.positions[symbol] = remaining

    def count_recent_violations(self, current_date: datetime) -> int:
        cutoff = current_date - timedelta(days=self.VIOLATION_WINDOW_DAYS)
        return sum(1 for e in self.state.risk_events if e["is_violation"] and e["date"] >= cutoff)

    def can_open_new_position(self, current_date: datetime) -> bool:
        if self.state.cooldown_until and current_date < self.state.cooldown_until:
            return False
        if self.count_recent_violations(current_date) >= 2:
            return False
        return True

    def trigger_cooldown(self, current_date: datetime) -> None:
        thresholds = self.get_thresholds()
        self.state.cooldown_until = current_date + timedelta(days=thresholds["cooldown_days"])

    def get_risk_report(self, equity: float, current_date: datetime) -> Dict:
        dd = self.drawdown_from_peak(equity)
        thresholds = self.get_thresholds()
        return {
            "current_equity": equity,
            "equity_peak": self.state.equity_peak,
            "current_drawdown": dd,
            "regime": self.state.current_regime,
            "position_stop": thresholds["position_stop"],
            "portfolio_stop": thresholds["portfolio_stop"],
            "absolute_ceiling": self.ABSOLUTE_CEILING,
            "violations_60d": self.count_recent_violations(current_date),
            "cooldown_active": self.state.cooldown_until is not None and current_date < self.state.cooldown_until,
        }

    def _log(self, date, severity, symbol, description, action, is_violation: bool) -> None:
        self.state.risk_events.append({
            "date": date,
            "severity": severity,
            "symbol": symbol,
            "description": description,
            "action_taken": action,
            "is_violation": is_violation,
        })