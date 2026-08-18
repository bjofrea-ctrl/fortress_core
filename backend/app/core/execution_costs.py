"""M4 — Costos medidos (DISENO_INSTRUMENTO.md §7, módulo M4).

MOTIVO: cada veredicto de "no sobrevive los costos" de este proyecto depende de una
constante ASUMIDA (0.10% comisión + 0.05% slippage por lado, `settings.COST_PER_SIDE`),
nunca medida. El caso §18.2 encontró señal real (bruto +0.000149/día, t-NW +1.01) que
murió contra un costo hedged asumido de 0.63%/trade. Ese "no tradeable" es una división
entre un número medido y uno inventado.

Este módulo mide el costo real con Alpaca PAPER TRADING (API gratis, sin capital real):
    slippage por orden = (fill - decision) / decision
donde *decision* es el precio justo antes de mandar la orden (último trade) y *fill* el
precio promedio real de ejecución. Se persiste en SQLite y se resume al contrato de
salida que consume el resto del proyecto.

REGLAS NO NEGOCIABLES (heredadas de ORDENES_MODULOS.md M4):
  - PAPER TRADING únicamente. Jamás una orden en cuenta live. El base_url APUNTA a
    paper-api.alpaca.markets SIEMPRE; cambiarlo a api.alpaca.markets es romper esto.
  - Credenciales vía variables de entorno / settings, nunca en código ni en el chat.

DISEÑO PARA TESTEABILIDAD (obligación del contrato M4): la medición se inyecta un
cliente con dos métodos (`last_trade_price` / `submit_market_order`) para poder testear
con un fake, sin pegar a la red. `AlpacaPaperClient` es la implementación HTTP real.
"""
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import requests

DEFAULT_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
# Los datos de mercado NO viven en el host de trading (paper-api): están en
# data.alpaca.markets. Pedir el último trade al host de trading da 404
# (crash de la ronda viva de 2026-08-18). Son hosts distintos que usan las
# mismas credenciales. El dato es de solo lectura; nunca toca una cuenta live.
DEFAULT_MARKET_DATA_BASE_URL = "https://data.alpaca.markets"
DEFAULT_TIMEOUT_SECONDS = 15.0


class ConfigurationError(RuntimeError):
    """Falta configuración (credenciales paper) para instanciar el cliente de medición."""


# --------------------------------------------------------------------------- #
# Cliente HTTP de Alpaca PAPER (la única pieza que toca la red).
# --------------------------------------------------------------------------- #
class AlpacaPaperClient:
    """Cliente mínimo de la API REST de Alpaca paper trading.

    Emula los dos métodos que `measure_slippage` necesita. Levanta
    `ConfigurationError` si faltan credenciales — la medición es la única pieza que
    las requiere; el resto del proyecto construye sin ellas.
    """

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        base_url: str = "",
        market_data_base_url: str = "",
        session: Any = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ALPACA_PAPER_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_PAPER_SECRET_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("ALPACA_PAPER_BASE_URL", "")
            or DEFAULT_PAPER_BASE_URL
        )
        self.market_data_base_url = (
            market_data_base_url
            or os.environ.get("ALPACA_MARKET_DATA_BASE_URL", "")
            or DEFAULT_MARKET_DATA_BASE_URL
        )
        if not self.api_key or not self.secret_key:
            raise ConfigurationError(
                "Faltan credenciales paper de Alpaca (ALPACA_PAPER_API_KEY / "
                "ALPACA_PAPER_SECRET_KEY). No se instancia el cliente de medición."
            )
        self._session = session if session is not None else requests.Session()
        self._session.headers.update(
            {
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
            }
        )

    def last_trade_price(self, symbol: str) -> float:
        """Precio del último trade del símbolo — el *precio de decisión* de la medición."""
        resp = self._session.get(
            f"{self.base_url}/v2/last/trade/{symbol}", timeout=DEFAULT_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        return float(resp.json()["trade"]["p"])

    def submit_market_order(self, symbol: str, qty: float, side: str) -> Dict[str, Any]:
        """Manda una orden MARKET de PAPER y devuelve el JSON de la orden ya fillada.

        Para market orders Alpaca devuelve `filled_avg_price` en la respuesta. Si no,
        falla ruidoso (no registrar un fill silenciosamente como None).
        """
        payload = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        resp = self._session.post(
            f"{self.base_url}/v2/orders", json=payload, timeout=DEFAULT_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        order = resp.json()
        if not order.get("filled_avg_price"):
            raise RuntimeError(
                f"Orden {symbol} {side} sin filled_avg_price en la respuesta: "
                f"{order.get('status')}. Revisá el estado de la orden, no lo registres "
                "como fill."
            )
        return order

    def close(self) -> None:
        if self._session is not None:
            self._session.close()


# --------------------------------------------------------------------------- #
# Persistencia SQLite.
# --------------------------------------------------------------------------- #
_SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS measurements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT    NOT NULL,
    symbol        TEXT    NOT NULL,
    side          TEXT    NOT NULL,
    price_decision REAL   NOT NULL,
    price_fill    REAL    NOT NULL,
    slippage      REAL    NOT NULL,
    commission    REAL    NOT NULL,
    size          REAL    NOT NULL
);
"""
_SCHEMA_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_measurements_date ON measurements(date);"
)


class ExecutionCostRecorder:
    """Persistencia en SQLite de las mediciones de slippage.

    Contrato: cada registro es una orden paper con su precio de decisión vs su fill.
    `slippage = (fill - decision) / decision` (firmado, tal como lo define el contrato
    M4; al resumir se usa |slippage| porque el que paga es el motor en ambos lados).
    """

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            db_path = os.environ.get(
                "FORTRESS_COSTS_DB", "./data/cache/execution_costs.db"
            )
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA_TABLE)
        self._conn.execute(_SCHEMA_INDEX)
        self._conn.commit()

    def record(
        self,
        symbol: str,
        side: str,
        date: str,
        price_decision: float,
        price_fill: float,
        commission_frac: float,
        size: float,
    ) -> int:
        slippage = (price_fill - price_decision) / price_decision if price_decision else 0.0
        cur = self._conn.execute(
            "INSERT INTO measurements "
            "(date, symbol, side, price_decision, price_fill, slippage, commission, size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                date,
                symbol,
                side,
                float(price_decision),
                float(price_fill),
                float(slippage),
                float(commission_frac),
                float(size),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def records(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT date, symbol, side, price_decision, price_fill, slippage, "
            "commission, size FROM measurements ORDER BY id"
        ).fetchall()
        return [
            {
                "date": r[0],
                "symbol": r[1],
                "side": r[2],
                "price_decision": r[3],
                "price_fill": r[4],
                "slippage": r[5],
                "commission_frac": r[6],
                "size": r[7],
            }
            for r in rows
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
# --------------------------------------------------------------------------- #
# Conductor de medición + resumen al contrato de salida.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MeasuredOrder:
    """Una orden paper medida: precio de decisión, fill, slippage firmado y comisión."""

    symbol: str
    side: str
    date: str
    price_decision: float
    price_fill: float
    slippage: float
    commission_frac: float
    size: float


def measure_slippage(
    client: Any,
    recorder: ExecutionCostRecorder,
    symbols: List[str],
    qty: float = 1.0,
    side: str = "buy",
) -> List[MeasuredOrder]:
    """Manda una orden market paper por símbolo y registra el slippage real.

    `client` solo necesita `last_trade_price(symbol) -> float` y
    `submit_market_order(symbol, qty, side) -> dict` — así los tests pasan un fake y
    la medición viva usa `AlpacaPaperClient`, sin cambiar el conductor.
    """
    date = datetime.now(timezone.utc).date().isoformat()
    measured: List[MeasuredOrder] = []
    for symbol in symbols:
        decision = client.last_trade_price(symbol)
        order = client.submit_market_order(symbol, qty, side)
        fill = float(order["filled_avg_price"])
        commission_dollars = float(order.get("commission", 0.0) or 0.0)
        notional = fill * qty
        commission_frac = commission_dollars / notional if notional else 0.0
        slippage = (fill - decision) / decision if decision else 0.0
        m = MeasuredOrder(
            symbol=symbol,
            side=side,
            date=date,
            price_decision=decision,
            price_fill=fill,
            slippage=slippage,
            commission_frac=commission_frac,
            size=float(qty),
        )
        recorder.record(
            symbol=m.symbol,
            side=m.side,
            date=m.date,
            price_decision=m.price_decision,
            price_fill=m.price_fill,
            commission_frac=m.commission_frac,
            size=m.size,
        )
        measured.append(m)
    return measured


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resume las mediciones al CONTRATO DE SALIDA de M4 (lo que consume el proyecto):
        {"cost_per_side_medido", "n_ordenes", "slippage_p50", "slippage_p95",
         "comision_media", "ventana"}
    `cost_per_side_medido = mean(|slippage|) + mean(comisión por lado)` — el costo total
    que el motor paga en cada lado (paga por salir tanto como por entrar).
    """
    if not records:
        raise ValueError("No hay mediciones para resumir.")
    abs_slip = np.abs(np.array([r["slippage"] for r in records], dtype=float))
    com = np.array([r["commission_frac"] for r in records], dtype=float)
    dates = [r["date"] for r in records]
    return {
        "cost_per_side_medido": float(np.mean(abs_slip) + np.mean(com)),
        "n_ordenes": len(records),
        "slippage_p50": float(np.median(abs_slip)),
        "slippage_p95": float(np.percentile(abs_slip, 95)),
        "comision_media": float(np.mean(com)),
        "ventana": f"{min(dates)} a {max(dates)}",
    }
