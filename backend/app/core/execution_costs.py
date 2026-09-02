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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import requests

from app.config import settings

DEFAULT_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
# Los datos de mercado NO viven en el host de trading (paper-api): están en
# data.alpaca.markets. Pedir el último trade al host de trading da 404
# (crash de la ronda viva de 2026-08-18). Son hosts distintos que usan las
# mismas credenciales. El dato es de solo lectura; nunca toca una cuenta live.
DEFAULT_MARKET_DATA_BASE_URL = "https://data.alpaca.markets"
DEFAULT_TIMEOUT_SECONDS = 15.0
# Las market orders paper NO vuelven con status filled en el HTTP response:
# nacen pending_new y la API las fillea en 1-10s (verificado en vivo 2026-08-18
# contra SPY: respuesta enviada como pending_new, filled 6s después). Hay que
# esperar el estado, no el envío.
TERMINAL_UNFILLED = ("rejected", "canceled", "expired")


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
        # Precedencia: arg constructor > env var runtime > settings/.env.
        # Una env var puesta en el momento debe pisar el default del .env
        # commiteado; el orden anterior (settings antes que env) rompía tests
        # que hacen monkeypatch.setenv para simular credencial distinta.
        self.api_key = api_key or os.environ.get("ALPACA_PAPER_API_KEY", "") or settings.ALPACA_PAPER_API_KEY
        self.secret_key = secret_key or os.environ.get("ALPACA_PAPER_SECRET_KEY", "") or settings.ALPACA_PAPER_SECRET_KEY
        self.base_url = (
            base_url
            or os.environ.get("ALPACA_PAPER_BASE_URL", "")
            or settings.ALPACA_PAPER_BASE_URL
            or DEFAULT_PAPER_BASE_URL
        )
        # ALPACA_MARKET_DATA_BASE_URL no está en Settings (solo paper base),
        # se lee de env con fallback al default de datos.
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

    @staticmethod
    def _alpaca_symbol(symbol: str) -> str:
        """Traduce la convención interna del motor (BRK-B) a la de Alpaca (BRK.B).

        La API de datos rechaza el formato con guion con 400; en el motor el
        universo vive con guion (yahoo/parquet), así que la traducción es solo
        en el borde HTTP — las mediciones persisten con el símbolo interno.
        """
        return symbol.replace("-", ".")

    def last_trade_price(self, symbol: str) -> float:
        """Precio del último trade del símbolo — el *precio de decisión* de la medición.

        Vive en el host de DATOS (data.alpaca.markets), no en el de trading:
        endpoint `/v2/stocks/{symbol}/trades/latest`. Mismo esquema de auth y misma
        forma de respuesta ({"symbol", "trade": {"p"}}).
        """
        resp = self._session.get(
            f"{self.market_data_base_url}/v2/stocks/{self._alpaca_symbol(symbol)}/trades/latest",
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return float(resp.json()["trade"]["p"])

    def get_account(self) -> Dict[str, Any]:
        """Snapshot de la cuenta paper: `GET /v2/account`.

        Devuelve el JSON estándar de Alpaca (cash, equity, buying_power,
        long_market_value, pattern_day_trader, status, etc.). Es la fuente para
        el pipeline diario (cuánto hay para posicionar / exposición total).
        """
        resp = self._session.get(
            f"{self.base_url}/v2/account", timeout=DEFAULT_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        return resp.json()

    def get_positions(self) -> List[Dict[str, Any]]:
        """Posiciones abiertas paper: `GET /v2/positions`.

        Devuelve una lista por símbolo con qty, avg_entry_price, current_price,
        market_value, unrealized_pl, etc. (símbolos con guion BRK-B ya traducidos
        al formato interno). Base para reconciliar el `signal_ledger` contra el
        estado real del paper y para cerrar posiciones con el precio actual.
        """
        resp = self._session.get(
            f"{self.base_url}/v2/positions", timeout=DEFAULT_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        positions = resp.json()
        out = []
        for pos in positions or []:
            row = dict(pos)
            row["symbol"] = row.get("symbol", "").replace(".", "-")
            out.append(row)
        return out

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Min",
        start: str = "",
        end: str = "",
        limit: int = 10000,
        feed: str = "iex",
        adjustment: str = "raw",
    ) -> List[Dict[str, Any]]:
        """Barras OHLCV 1-min (o timeframe genérico) — solo lectura, sin costo extra.

        Host de DATOS (data.alpaca.markets), endpoint
        `GET /v2/stocks/{symbol}/bars?timeframe=1Min&start=...&end=...`.
        `start`/`end` en RFC3339 UTC (ej. 2024-01-01T00:00:00Z). Paginada vía
        `next_page_token` hasta agotar. `feed=iex` es gratis en paper; `sip`
        requiere suscripción. Traduce BRK-B → BRK.B solo en el borde HTTP.

        Usado por el colector intradía I3 (acumulación 1-min) — no toca trading.
        """
        params: Dict[str, Any] = {
            "timeframe": timeframe,
            "limit": limit,
            "adjustment": adjustment,
            "feed": feed,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        bars: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            if page_token:
                params["page_token"] = page_token
            resp = self._session.get(
                f"{self.market_data_base_url}/v2/stocks/{self._alpaca_symbol(symbol)}/bars",
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            payload = resp.json()
            chunk = payload.get("bars") or []
            bars.extend(chunk)
            page_token = payload.get("next_page_token")
            if not page_token:
                break
            if len(chunk) == 0:
                break
        return bars

    def submit_market_order(self, symbol: str, qty: float, side: str) -> Dict[str, Any]:
        """Manda una orden MARKET de PAPER y devuelve el JSON de la orden ya fillada.

        Alpaca no devuelve el fill en el HTTP response: nace como `pending_new`
        y pasa a `filled` (o a un estado terminal unfilled) unos segundos después,
        así que se espera haciendo polling al GET de la orden. La medición exige
        un fill real; registrar uno que no llegó contaminaría el número.
        """
        payload = {
            "symbol": self._alpaca_symbol(symbol),
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
        deadline = time.monotonic() + 30.0
        while order.get("status") != "filled":
            status = order.get("status")
            if status in TERMINAL_UNFILLED:
                raise RuntimeError(
                    f"Orden {symbol} {side} terminó {status} sin fill: no se registra."
                )
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Orden {symbol} {side} sin fill tras 30s (estado={status}): "
                    "no se registra. Revisá la orden manualmente."
                )
            time.sleep(1.0)
            resp = self._session.get(
                f"{self.base_url}/v2/orders/{order['id']}",
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            order = resp.json()
        if not order.get("filled_avg_price"):
            raise RuntimeError(
                f"Orden {symbol} {side} con status filled pero sin filled_avg_price."
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
