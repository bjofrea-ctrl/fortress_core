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
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sqlite3
from typing import Any, Dict, List

import numpy as np
import requests

DEFAULT_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
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
        session: Any = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ALPACA_PAPER_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_PAPER_SECRET_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("ALPACA_PAPER_BASE_URL", "")
            or DEFAULT_PAPER_BASE_URL
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