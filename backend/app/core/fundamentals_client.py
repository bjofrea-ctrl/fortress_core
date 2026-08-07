"""
Cliente Finnhub para fundamentales reales, reemplazando los 6 tickers
hardcodeados en SAMPLE_FUNDAMENTALS (predict.py). Requiere FINNHUB_API_KEY
en .env — plan gratuito (60 llamadas/min) en https://finnhub.io/register.

ADVERTENCIA: el mapeo de FIELD_MAP se hizo con la documentación pública de
GET /stock/metric?metric=all, SIN poder probarlo contra una key real en este
entorno (sin acceso a internet). Correr scripts/verify_finnhub_mapping.py
con una key válida antes de confiar en la calibración de las señales
fundamentales — los campos marcados "revisar" son los menos seguros.
"""
import json
import os
import time
from typing import Dict, Optional

import requests

from app.config import settings
from app.utils.logging import logger
from app.utils.persistence import atomic_write_json

CACHE_DIR = "data/cache_fundamentals"
CACHE_TTL_SECONDS = 24 * 3600  # los fundamentales no cambian intradía

# campo interno (usado por PredictiveEngine._fundamental_signals) -> campo
# de la respuesta de Finnhub. None = sin equivalente directo conocido.
FIELD_MAP = {
    "pe_ratio": "peExclExtraTTM",
    "pb_ratio": "pbAnnual",
    "ev_ebitda": "currentEv/freeCashFlowTTM",  # aproximado — revisar
    "roe": "roeTTM",
    "roa": "roaTTM",
    "debt_equity": "totalDebt/totalEquityAnnual",
    "fcf_yield": "fcfMarginTTM",  # aproximado — revisar
    "div_yield": "currentDividendYieldTTM",
    "eps_growth": "epsGrowthTTMYoy",
    "gross_margin": "grossMarginTTM",
    "peg": "pegRatio",  # puede no venir en el free tier — revisar
    "current_ratio": "currentRatioAnnual",
    "asset_turnover": "assetTurnoverTTM",
    "book_value_growth": "bookValueShareGrowth5Y",  # aproximado — revisar
    "sue_score": None,  # sin equivalente directo en Finnhub
}


class FinnhubClient:
    def __init__(self, api_key: Optional[str] = None):
        # api_key="" explícito no debe caer al default de Settings (mismo
        # bug encontrado y arreglado en NvidiaNIMClient — "" or X da X).
        self.api_key = api_key if api_key is not None else settings.FINNHUB_API_KEY
        self.base_url = "https://finnhub.io/api/v1"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _cache_path(self, symbol: str) -> str:
        return f"{CACHE_DIR}/{symbol.upper()}.json"

    def _read_cache(self, symbol: str) -> Optional[Dict]:
        path = self._cache_path(symbol)
        if not os.path.exists(path):
            return None
        if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("finnhub_cache_read_failed", extra={"symbol": symbol, "error": str(e)})
            return None

    def get_fundamentals(self, symbol: str, use_cache: bool = True) -> Optional[Dict]:
        """Fundamentales reales de Finnhub, o None si no hay key / falla la llamada / no hay datos."""
        if not self.is_available():
            return None

        if use_cache:
            cached = self._read_cache(symbol)
            if cached is not None:
                return cached

        raw = self._fetch_raw(symbol)
        if not raw:
            return None

        mapped = {}
        for internal_field, finnhub_field in FIELD_MAP.items():
            if finnhub_field is None:
                continue
            value = raw.get(finnhub_field)
            if value is not None:
                mapped[internal_field] = value

        if not mapped:
            logger.warning("finnhub_no_mapped_fields", extra={"symbol": symbol})
            return None

        mapped["_data_source"] = "finnhub_live"
        if use_cache:
            os.makedirs(CACHE_DIR, exist_ok=True)
            atomic_write_json(self._cache_path(symbol), mapped)
        return mapped

    def _fetch_raw(self, symbol: str) -> Optional[Dict]:
        try:
            r = requests.get(
                f"{self.base_url}/stock/metric",
                params={"symbol": symbol.upper(), "metric": "all", "token": self.api_key},
                timeout=15,
            )
        except requests.exceptions.Timeout:
            logger.warning("finnhub_timeout", extra={"symbol": symbol})
            return None
        except requests.exceptions.ConnectionError:
            logger.warning("finnhub_connection_error", extra={"symbol": symbol})
            return None
        except Exception as e:
            logger.error("finnhub_unexpected_error", extra={"symbol": symbol, "error": str(e)})
            return None

        if r.status_code == 429:
            logger.warning("finnhub_rate_limited", extra={"symbol": symbol})
            return None
        if r.status_code != 200:
            logger.warning("finnhub_bad_response", extra={"symbol": symbol, "status_code": r.status_code})
            return None

        try:
            return r.json().get("metric", {})
        except Exception as e:
            logger.warning("finnhub_json_parse_failed", extra={"symbol": symbol, "error": str(e)})
            return None
