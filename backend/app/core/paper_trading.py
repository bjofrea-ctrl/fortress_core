"""
Conector de EJECUCIÓN/REGISTRO de PAPER TRADING (Frente 2, Semana 1).

Une `AlpacaPaperClient` (execution_costs.py) con `SignalLedger` (T1.6): cada
orden de papel que manda el pipeline diario genera una fila REAL en el ledger —
entrada al abrir (status='open'), salida + pnl_r al cerrar (status='closed').

NO toca el motor de decisión ni signal_engine.py: este módulo solo toma una
decisión YA tomada (symbol/qty/side) y la ejecuta+registra contra el paper.

Diseño CLAVE para coordinar con OpenCode sin pisarse: el conector recibe el
cliente y el ledger INYECTADOS. Así el pipeline diario de OpenCode puede usar
este mismo módulo pasándole el cliente real, y los tests lo ejercitan con
fakes sin pegar a la red. Verificación del checkpoint: correr manualmente y
confirmar que la orden se ejecuta y el ledger registra (open -> closed).

pnl_r se define como retorno simple por acción del papel: (close-open)/open.
"""
from typing import Any, Dict, Optional

from app.core.execution_costs import AlpacaPaperClient
from app.core.signal_ledger import SignalLedger


class PaperTrader:
    """Ejecuta órdenes de papel y las registra en el signal_ledger."""

    def __init__(self, client: AlpacaPaperClient, ledger: SignalLedger):
        self.client = client
        self.ledger = ledger

    def open_paper_order(
        self,
        signal_id: str,
        symbol: str,
        qty: float,
        side: str = "buy",
        entry_date: str = "",
        factors: Optional[Dict[str, Any]] = None,
        regime_state: int = 0,
    ) -> Dict[str, Any]:
        """Ejecuta una orden MARKET de papel y abre la fila en el ledger.

        Devuelve el JSON de la orden (ya fillada, `submit_market_order` espera
        el fill). El `filled_avg_price` queda como open_fill_price en la fila.
        """
        order = self.client.submit_market_order(symbol, qty, side)
        fill_price = float(order["filled_avg_price"])
        if not entry_date:
            entry_date = order.get("submitted_at", order.get("created_at", "")) or ""
            entry_date = entry_date[:10]
        self.ledger.open_order(
            signal_id=signal_id,
            symbol=symbol,
            entry_date=entry_date,
            qty=qty,
            open_fill_price=fill_price,
            factors=factors,
            regime_state=regime_state,
        )
        return order

    def close_paper_order(
        self,
        signal_id: str,
        symbol: str,
        qty: float,
        exit_date: str,
        exit_reason: str,
        close_price: Optional[float] = None,
    ) -> float:
        """Cierra una orden abierta: calcula pnl_r y completa la fila.

        Si no se pasa close_price, lo toma del último trade (precio de decisión).
        Devuelve el pnl_r registrado.
        """
        open_row = self._open_row(signal_id)
        if open_row is None:
            raise ValueError(f"no hay orden abierta con signal_id={signal_id}")
        open_price = open_row["open_fill_price"]
        if close_price is None:
            close_price = self.client.last_trade_price(symbol)
        close_price = float(close_price)
        pnl_r = (close_price - open_price) / open_price if open_price else 0.0
        self.ledger.close_order(
            signal_id=signal_id,
            exit_date=exit_date,
            exit_reason=exit_reason,
            pnl_r=pnl_r,
            close_fill_price=close_price,
        )
        return pnl_r

    def reconcile_open_positions(self, exit_date: str, exit_reason: str = "RECONCILE") -> int:
        """Cierra contra la posición real del paper las órdenes que ya no existen.

        Corsé de honestidad con el checkpoint: si una orden abierta en el ledger
        no figura en `GET /positions`, su fill real se fue (posiblemente ya
        cerrada) y se registra el cierre contable espurio. Devuelve cuántas se
        reconciliaron. No lanza si no hay posiciones.
        """
        positions = {p["symbol"]: p for p in self.client.get_positions()}
        abiertas = self.ledger.open_orders()
        cerradas = 0
        for row in abiertas:
            sym = row["symbol"]
            if sym in positions:
                continue
            # la posición ya no está: cierre contable con el precio actual de mercado
            try:
                cp = self.client.last_trade_price(sym)
            except Exception:
                cp = None
            self.ledger.close_order(
                signal_id=row["signal_id"],
                exit_date=exit_date,
                exit_reason=exit_reason,
                pnl_r=float(row["pnl_r"] or 0.0),
                close_fill_price=cp,
            )
            cerradas += 1
        return cerradas

    def _open_row(self, signal_id: str) -> Optional[Dict[str, Any]]:
        for row in self.ledger.open_orders():
            if row["signal_id"] == signal_id:
                return row
        return None

    def account_snapshot(self) -> Dict[str, Any]:
        """Snapshot de la cuenta paper (cash/equity/buying_power)."""
        return self.client.get_account()
