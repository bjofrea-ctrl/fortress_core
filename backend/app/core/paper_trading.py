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
import sys
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

        Manejo explícito de fills parciales y rechazos: si la orden se llena
        parcialmente (filled_qty != qty) se loguea el desbalance y se registra
        la cantidad realmente fillada; si es rechazada/cancelada/expirada,
        `submit_market_order` levanta RuntimeError y acá se loguea como
        REJECTED antes de propagar — no queda silencioso.
        """
        try:
            order = self.client.submit_market_order(symbol, qty, side)
        except RuntimeError as exc:
            # Rechazo / cancelación / timeout — marcar explícitamente, no silencioso
            msg = str(exc)
            is_reject = any(k in msg.lower() for k in ("rejected", "canceled", "cancelled", "expired", "sin fill"))
            tag = "REJECTED" if is_reject else "ERROR"
            print(f"[paper_trading] open {symbol} {side} qty={qty} {tag}: {exc}", file=sys.stderr)
            raise
        # Fill parcial: Alpaca devuelve filled_qty; si difiere de qty, es parcial
        try:
            filled_qty_raw = order.get("filled_qty", order.get("qty", qty))
            filled_qty = float(filled_qty_raw) if filled_qty_raw is not None else float(qty)
            if abs(filled_qty - float(qty)) > 1e-9:
                print(
                    f"[paper_trading] open {symbol} fill parcial: filled_qty={filled_qty} vs qty={qty} "
                    f"status={order.get('status')}",
                    file=sys.stderr,
                )
                qty = filled_qty  # registrar lo realmente fillado
        except Exception as exc:  # noqa: BLE001
            print(f"[paper_trading] open {symbol} chequeo parcial falló: {exc}", file=sys.stderr)
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

        Si `close_price` se pasa, se usa como precio de fill real (ej. el
        `filled_avg_price` de la orden de cierre ya ejecutada). Si no se pasa,
        se usa `last_trade_price(symbol)` como *aproximación* del precio de
        decisión, no del fill — el fill real puede diferir por slippage,
        comisión y latencia de ejecución; la aproximación subestima el costo
        real y solo se usa cuando no hay fill disponible (ej. cierre manual
        sin orden, o reconcile). Por eso el docstring documenta la
        aproximación: no hay orden de cierre con fill en este punto.

        Manejo de parciales/rechazos: si el cierre se hace vía orden real
        (cuando `close_price` viene de un fill), el llamante debe haber
        manejado el parcial/rechazo al obtener ese fill; acá se loguea si
        `close_price` es None y el fallback a last_trade falla.

        Devuelve el pnl_r registrado.
        """
        open_row = self._open_row(signal_id)
        if open_row is None:
            raise ValueError(f"no hay orden abierta con signal_id={signal_id}")
        open_price = open_row["open_fill_price"]
        # Si hay precio de fill real pasado, usarlo; si no, aproximar con last_trade
        used_approx = False
        if close_price is None:
            try:
                close_price = self.client.last_trade_price(symbol)
                used_approx = True
            except Exception as exc:  # noqa: BLE001
                print(f"[paper_trading] close {symbol} no hay precio de mercado: {exc}", file=sys.stderr)
                raise
            print(
                f"[paper_trading] close {symbol} usando last_trade_price como aproximación "
                f"(no fill real) close={close_price} open={open_price}",
                file=sys.stderr,
            )
        else:
            # close_price viene del caller — asumido fill real si se pasó explícito
            print(f"[paper_trading] close {symbol} usando close_price provisto (asumido fill real) {close_price}", file=sys.stderr)
        close_price = float(close_price)
        # Manejo de rechazo lógico: si close_price es None o 0 y no hay open_price
        if not open_price:
            print(f"[paper_trading] close {symbol} open_fill_price faltante, pnl 0.0", file=sys.stderr)
            pnl_r = 0.0
        else:
            pnl_r = (close_price - float(open_price)) / float(open_price) if float(open_price) else 0.0
        # Si se usó aproximación, dejar rastro en exit_reason
        if used_approx and "APPROX" not in exit_reason:
            exit_reason = f"{exit_reason} (APPROX last_trade)"
        # Detectar fill parcial en cierre si qty difiere del open (no hay order fill_qty aquí,
        # pero si el qty de cierre != qty abierta, es parcial)
        try:
            open_qty = float(open_row.get("qty", qty))
            if abs(float(qty) - open_qty) > 1e-9:
                print(
                    f"[paper_trading] close {symbol} qty parcial: close_qty={qty} open_qty={open_qty}",
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[paper_trading] close {symbol} chequeo qty falló: {exc}", file=sys.stderr)
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
        cerrada) y se registra el cierre contable. Devuelve cuántas se
        reconciliaron. No lanza si no hay posiciones.

        Cálculo de pnl_r: (precio_actual - open_fill_price) / open_fill_price
        usando el último precio de mercado disponible. Solo cae a 0.0 si
        genuinamente no hay precio (last_trade falla) o no hay open_fill_price,
        logueando por qué.
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
            except Exception as exc:  # noqa: BLE001
                cp = None
                print(f"[paper_trading] reconcile {sym} no hay precio de mercado: {exc}", file=sys.stderr)
            # Calcular pnl real, no pisar con 0.0
            open_price = row.get("open_fill_price")
            if cp is not None and open_price is not None and float(open_price) != 0:
                try:
                    pnl_r = (float(cp) - float(open_price)) / float(open_price)
                except Exception as exc:  # noqa: BLE001
                    pnl_r = 0.0
                    print(f"[paper_trading] reconcile {sym} pnl calc falló: {exc} cp={cp} open={open_price}", file=sys.stderr)
            else:
                pnl_r = 0.0
                if cp is None:
                    print(f"[paper_trading] reconcile {sym} pnl_fallback 0.0: sin precio actual", file=sys.stderr)
                elif open_price is None or float(open_price) == 0:
                    print(f"[paper_trading] reconcile {sym} pnl_fallback 0.0: open_fill_price faltante/cero {open_price}", file=sys.stderr)
            self.ledger.close_order(
                signal_id=row["signal_id"],
                exit_date=exit_date,
                exit_reason=exit_reason,
                pnl_r=pnl_r,
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
