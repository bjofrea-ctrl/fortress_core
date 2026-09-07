from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.config import settings

# Valor semilla del registro de parámetros versionado (T1.5). NO eliminar:
# se inserta en config_history la primera vez que corre _ensure_schema()
# (changed_by="initial_estimate") y queda como fallback/default para
# fechas anteriores al registro. Los call sites se migran a
# get_regime_thresholds() uno por uno; mientras tanto, importar la
# constante directo sigue funcionando.
REGIME_THRESHOLDS = {
    0: {"position_stop": 0.05, "portfolio_stop": 0.05, "max_exposure": 1.00, "cooldown_days": 5},
    1: {"position_stop": 0.07, "portfolio_stop": 0.07, "max_exposure": 0.70, "cooldown_days": 5},
    2: {"position_stop": 0.08, "portfolio_stop": 0.10, "max_exposure": 0.40, "cooldown_days": 10},
    3: {"position_stop": 0.03, "portfolio_stop": 0.03, "max_exposure": 0.20, "cooldown_days": 15},
}

# B8 (PRE_REGISTRO_WINRATE_RR_SIZING_CAP_20260906.md) §2b: fracción conservadora de
# Kelly aplicada como techo de crecimiento de risk_per_trade. 1/4 Kelly es el default
# del ticket ("Kelly/4, parametrizable"). Nunca se usa el Kelly completo: el edge
# real medido por measure_realized_edge (2a) es chico e incierto hoy.
DEFAULT_KELLY_FRACTION = 0.25

# Default conservador cuando 2a devuelve "n insuficiente" o el edge medido no es
# positivo: nos quedamos con el RISK_PER_TRADE de producción ya probado (1.5%),
# NO con el Kelly optimista de la simulación Monte Carlo (que compondría a un CAGR
# absurdo). El cap se combina (mínimo) con el max_exposure del régimen.

# Singleton lazy del ConfigRegistry (import adentro de la función para
# evitar el ciclo de import con config_registry, que importa REGIME_THRESHOLDS).
_REGISTRY = None


def get_regime_thresholds(regime_state: int, at_date: Optional[datetime] = None) -> dict:
    """Lee los umbrales de riesgo del ConfigRegistry con reconstrucción
    point-in-time (T1.5): el valor devuelto es el vigente en 'at_date', no
    el de hoy. REGIME_THRESHOLDS queda como seed del registro y como
    fallback para fechas anteriores a la creación de la tabla."""
    global _REGISTRY
    if _REGISTRY is None:
        from app.core.config_registry import ConfigRegistry

        _REGISTRY = ConfigRegistry()

    ts = at_date or datetime.now(timezone.utc)
    fallback = REGIME_THRESHOLDS.get(regime_state, REGIME_THRESHOLDS[0])
    return {
        "position_stop": _REGISTRY.get_at(
            f"risk.regime.{regime_state}.position_stop", ts, default=fallback["position_stop"]
        ),
        "portfolio_stop": _REGISTRY.get_at(
            f"risk.regime.{regime_state}.portfolio_stop", ts, default=fallback["portfolio_stop"]
        ),
        "max_exposure": _REGISTRY.get_at(
            f"risk.regime.{regime_state}.max_exposure", ts, default=fallback["max_exposure"]
        ),
        "cooldown_days": _REGISTRY.get_at(
            f"risk.regime.{regime_state}.cooldown_days", ts, default=fallback["cooldown_days"]
        ),
    }


@dataclass
class RiskState:
    equity_peak: float
    entry_reference: Dict[str, float] = field(default_factory=dict)
    highest_price: Dict[str, float] = field(default_factory=dict)
    positions: Dict[str, int] = field(default_factory=dict)
    partial_done: Dict[str, bool] = field(default_factory=dict)
    cooldown_until: Optional[datetime] = None
    risk_events: List[Dict] = field(default_factory=list)
    current_regime: int = 0
    current_date: Optional[datetime] = None


class AdaptiveRiskManager:
    def __init__(self, initial_equity: float):
        self.state = RiskState(equity_peak=initial_equity)
        self.ABSOLUTE_CEILING = settings.ABSOLUTE_CEILING
        self.RISK_PER_TRADE = settings.RISK_PER_TRADE
        self.MAX_POSITION_PCT = settings.MAX_POSITION_PCT
        self.VIOLATION_WINDOW_DAYS = settings.VIOLATION_WINDOW_DAYS

    def get_thresholds(self, at_date: Optional[datetime] = None) -> dict:
        """Umbrales del régimen vigente en 'at_date' (o en la fecha del
        backtest en curso, si el manager ya la conoce). Point-in-time: un
        ajuste posterior no altera lo que este manager ve para fechas
        pasadas (T1.5)."""
        date = at_date or self.state.current_date
        return get_regime_thresholds(self.state.current_regime, at_date=date)

    def update_regime(self, regime_state: int) -> None:
        self.state.current_regime = regime_state

    def update_peak(self, equity: float) -> None:
        self.state.equity_peak = max(self.state.equity_peak, equity)

    def drawdown_from_peak(self, equity: float) -> float:
        return (equity - self.state.equity_peak) / self.state.equity_peak

    def loss_from_entry(self, symbol: str, price: float) -> float:
        entry = self.state.entry_reference.get(symbol)
        return 0.0 if entry is None else (price - entry) / entry

    def compute_position_size(
        self,
        equity: float,
        price: float,
        atr: float,
        win_prob: Optional[float] = None,
        payoff_ratio: Optional[float] = None,
        fractional_kelly: float = 0.25,
        symbol: Optional[str] = None,
        measured_win_rate: Optional[float] = None,
        measured_reward_risk: Optional[float] = None,
    ) -> int:
        if atr <= 0 or price <= 0:
            return 0
        thresholds = self.get_thresholds()
        stop_distance = max(2.0 * atr, price * thresholds["position_stop"])

        # B8 §2b: acotar el riesgo por trade con el techo Kelly+régimen del edge
        # REAL medido en 2a. Si no se pasa edge medido, se queda en RISK_PER_TRADE
        # (comportamiento original; no se reemplaza nada).
        risk_per_trade = self.RISK_PER_TRADE
        if measured_win_rate is not None or measured_reward_risk is not None:
            risk_per_trade = self.effective_risk_per_trade(
                measured_win_rate, measured_reward_risk,
                regime_state=self.state.current_regime,
                kelly_fraction=fractional_kelly,
            )
        shares_by_risk = (equity * risk_per_trade) / stop_distance
        max_shares = (equity * self.MAX_POSITION_PCT) / price

        if win_prob is not None and payoff_ratio is not None:
            p = min(max(win_prob, 0.01), 0.99)
            b = max(payoff_ratio, 0.01)
            kelly = max(0.0, (p * b - (1 - p)) / b) * fractional_kelly
            if kelly > 0:
                kelly_shares = (equity * kelly) / price
                return int(min(kelly_shares, shares_by_risk, max_shares))

        return int(min(shares_by_risk, max_shares))

    def risk_per_trade_cap(
        self,
        win_rate: Optional[float],
        reward_risk: Optional[float],
        regime_state: Optional[int] = None,
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    ) -> float:
        """Techo de riesgo por trade (fracción de equity) según el edge REAL medido.

        B8 §2b: el cap = min(Kelly fraccionario, max_exposure del régimen). No
        reemplaza compute_position_size ni el max_exposure del régimen; los ACOTA
        más cuando el edge medido lo justifica.

        Parámetros:
          - win_rate / reward_risk: medidos por measure_realized_edge (2a). None
            significa que 2a dijo "n insuficiente".
          - regime_state: régimen; si None usa el régimen vigente del manager.
          - kelly_fraction: fracción conservadora de Kelly (default 1/4, parametrizable).

        Si el edge es insuficiente o no positivo: devuelve el default conservador
        documentado = min(RISK_PER_TRADE de producción, max_exposure del régimen).
        NUNCA aplica un Kelly negativo a ciegas.
        """
        regime = regime_state if regime_state is not None else self.state.current_regime
        regime_max_exposure = get_regime_thresholds(regime).get("max_exposure", 1.0)

        # Edge insuficiente / inválido => default conservador (jamás Kelly de simulación).
        if (
            win_rate is None
            or reward_risk is None
            or reward_risk <= 0
            or not (0.0 < win_rate < 1.0)
        ):
            return min(self.RISK_PER_TRADE, regime_max_exposure)

        kelly_full = max(0.0, win_rate * reward_risk - (1 - win_rate)) / reward_risk
        # Kelly no positivo => no hay edge que justifique crecer el riesgo: default
        # conservador (jamás 0 a ciegas, que equivaldría a "no operar nunca").
        if kelly_full <= 0:
            return min(self.RISK_PER_TRADE, regime_max_exposure)
        fractional_kelly = kelly_full * kelly_fraction
        return min(fractional_kelly, regime_max_exposure)

    def effective_risk_per_trade(
        self,
        win_rate: Optional[float],
        reward_risk: Optional[float],
        regime_state: Optional[int] = None,
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    ) -> float:
        """Riesgo por trade efectivo = min(RISK_PER_TRADE fijo, techo Kelly+régimen).

        B8 §2b: el 1% fijo (RISK_PER_TRADE) solía compondar sin límite superior de
        crecimiento; ahora queda acotado por el techo. Si el edge medido es fuerte,
        el techo es alto y rige el fijo; si es débil, el techo baja y acota el
        crecimiento. Si 2a dijo "n insuficiente", el default conservador ya es el
        RISK_PER_TRADE de producción.
        """
        return min(
            self.RISK_PER_TRADE,
            self.risk_per_trade_cap(win_rate, reward_risk, regime_state, kelly_fraction),
        )

    def check_all_stops(
        self,
        equity: float,
        current_prices: Dict[str, float],
        atrs: Dict[str, float],
        date: datetime
    ) -> List[Tuple[str, str]]:
        to_close = []
        self.state.current_date = date
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

            if atr_val and (price - entry) >= 2.0 * atr_val and not self.state.partial_done.get(symbol, False):
                self.state.partial_done[symbol] = True
                to_close.append((symbol, "PARTIAL_TP"))

            high = self.state.highest_price.get(symbol, entry)
            self.state.highest_price[symbol] = max(high, price)
            if atr_val and (self.state.highest_price[symbol] - entry) > 1.5 * atr_val:
                trailing = self.state.highest_price[symbol] - 2.0 * atr_val
                if price <= trailing:
                    to_close.append((symbol, "TRAILING_STOP"))

        dd = self.drawdown_from_peak(equity)
        if dd <= -self.ABSOLUTE_CEILING:
            if self.state.positions:
                for symbol in list(self.state.positions.keys()):
                    to_close.append((symbol, "PORTFOLIO_CEILING_BREACH"))
                self._log(date, "CRITICAL", None, f"CEILING cartera: {dd:.2%}", "TOTAL_LIQUIDATION", True)
                self.trigger_cooldown(date)
        elif dd <= -thresholds["portfolio_stop"]:
            if self.state.positions:
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
        self.state.partial_done[symbol] = False
        self.state.positions[symbol] = self.state.positions.get(symbol, 0) + shares

    def register_exit(self, symbol: str, shares_to_exit: int) -> None:
        remaining = self.state.positions.get(symbol, 0) - shares_to_exit
        if remaining <= 0:
            self.state.entry_reference.pop(symbol, None)
            self.state.highest_price.pop(symbol, None)
            self.state.partial_done.pop(symbol, None)
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
        thresholds = self.get_thresholds(at_date=current_date)
        self.state.cooldown_until = current_date + timedelta(days=thresholds["cooldown_days"])

    def get_risk_report(self, equity: float, current_date: datetime) -> Dict:
        dd = self.drawdown_from_peak(equity)
        thresholds = self.get_thresholds(at_date=current_date)
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
