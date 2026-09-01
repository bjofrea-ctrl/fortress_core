"""
Ingesta de datos crudos de fundamentales — Motor de fundamentales automatizado.

Fuente de datos del reemplazo del export manual de InvestingPro
(PLAN_MOTOR_FUNDAMENTALES_AUTOMATIZADO.md, Fase 1). Baja los MISMOS estados
financieros crudos que InvestingPro usa para sus indicadores (income statement,
balance sheet, cash flow, profile, price target consensus) desde una API
legítima (FMP primaria, Finnhub como cruce), con cache incremental y log de
señales distintas por rama.

Patrón de cache incremental: replica el esquema corregido de `data_ingestion.py`
(umbral `>= 1`, señal de log explícita por cada rama: cache miss / cache
vacío-truncado / cache fresco / cache stale → refresh / refresh vacío). La
diferencia clave: aquí el TTL es de 90 días y no de 1 día — los estados
financieros se reportan trimestralmente, no intradía, por lo que refrescarlos a
diario es desperdicio de cuota y falsa frescura.

NUNCA se toca la red en la suite de tests: `FmpClient._fetch` y el cruce Finnhub
se inyectan/mockean. `FMP_API_KEY` / `FINNHUB_API_KEY` viven en .env / settings
— nunca en código ni en el chat.

ADVERTENCIA (cruzar con scripts/verify_finnhub_mapping.py): el FIELD_MAP del
`FinnhubClient` de `fundamentals_client.py` se armó SIN probar contra una key
real. Hasta que eso se verifique NO se confía en su mapeo para medidas
críticas: aquí Finnhub se usa SOLO como cruce de proveniencia/disponibilidad
(`finnhub_crosscheck`) marcado `_cross_unverified=True`. La vía primaria
incondicional es FMP, que ya está establecida y con contrato público.
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests  # única dependencia externa; el resto es stdlib.

from app.config import settings
from app.utils.logging import logger

# caché regenerable (ignorada por .gitignore, como el resto de
# backend/data/cache/**.json). NUNCA trackear estados en vivo.
CACHE_DIR = "data/cache_fundamentals_ingestion"

# Estados financieros son trimestrales: frescura de 90 días. (En contraste con
# data_ingestion.py que baja precios diarios con umbral >=1 día.) Sobrescribible
# por env para tests/fixtures, aunque los fixtures pinchan now().
TTL_DAYS = int(os.environ.get("FUNDAMENTALS_TTL_DAYS", "90"))

# Límite de periodos por statement: los 3 tribunales necesitan t-0 y t-1; 6 deja
# margen para ratios de crecimiento 5y.
FMP_STATEMENT_LIMIT = 6
class FmpClient:
    """Cliente mínimo de Financial Modeling Prep (API v3, free tier).

    Sólo listas de endpoints específicos; los tests pinchan `_fetch`.
    """

    BASE_URL = "https://financialmodelingprep.com/api/v3"

    def __init__(self, api_key: Optional[str] = None):
        # api_key="" explícito NO debe caer al default de Settings (mismo patrón
        # de bug arreglado en NvidiaNIMClient / FinnhubClient: "" or X → X).
        self.api_key = api_key if api_key is not None else settings.FMP_API_KEY
        self.base_url = self.BASE_URL

    def is_available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------- fetch ----------------------------------

    def _fetch(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """GET a la API FMP con manejo de errores → None.

        Punto único de entrada a red: en tests se pincha y NO se toca la red.
        """
        if not self.is_available():
            logger.info("fmp_missing_api_key")
            return None
        final = dict(params or {})
        final["apikey"] = self.api_key
        try:
            r = requests.get(f"{self.base_url}/{endpoint}", params=final, timeout=25)
        except requests.exceptions.Timeout:
            logger.warning("fmp_timeout", extra={"endpoint": endpoint})
            return None
        except requests.exceptions.ConnectionError:
            logger.warning("fmp_connection_error", extra={"endpoint": endpoint})
            return None
        except Exception as e:  # pragma: no cover - red real nunca en tests
            logger.error("fmp_unexpected_error", extra={"endpoint": endpoint, "error": str(e)})
            return None
        if r.status_code == 429:
            logger.warning("fmp_rate_limited", extra={"endpoint": endpoint})
            return None
        if r.status_code != 200:
            logger.warning("fmp_bad_response", extra={"endpoint": endpoint, "status_code": r.status_code})
            return None
        try:
            return r.json()
        except Exception:
            logger.warning("fmp_json_parse_failed", extra={"endpoint": endpoint})
            return None

    # ------------------------------- endpoints --------------------------------

    def income_statement(self, symbol: str, limit: int = FMP_STATEMENT_LIMIT):
        return self._fetch(f"income-statement/{symbol}", {"limit": limit})

    def balance_sheet(self, symbol: str, limit: int = FMP_STATEMENT_LIMIT):
        return self._fetch(f"balance-sheet-statement/{symbol}", {"limit": limit})

    def cash_flow(self, symbol: str, limit: int = FMP_STATEMENT_LIMIT):
        return self._fetch(f"cash-flow-statement/{symbol}", {"limit": limit})

    def profile(self, symbol: str):
        return self._fetch(f"profile/{symbol}")

    def price_target_consensus(self, symbol: str):
        return self._fetch(f"price-target-consensus/{symbol}")

class FundamentalsIngestion:
    """Orquesta la ingesta cruda con cache incremental (TTL 90d) + cruce Finnhub."""

    def __init__(
        self,
        fmp: Optional[FmpClient] = None,
        finnhub=None,  # FinnhubClient (app.core.fundamentals_client) o None
        cache_dir: Optional[str] = None,
    ):
        self.fmp = fmp if fmp is not None else FmpClient()
        self.finnhub = finnhub  # None si no se instanció (sin key / sin uso)
        self.cache_dir = cache_dir if cache_dir is not None else CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

    # ------------------------------ cache helpers ------------------------------

    def _cache_path(self, symbol: str) -> str:
        return f"{self.cache_dir}/{symbol.upper()}.json"

    def _cache_age_days(self, path: str, now: float) -> Optional[float]:
        try:
            return (now - os.path.getmtime(path)) / 86400.0
        except OSError:
            return None

    def needs_refresh(self, symbol: str, now: Optional[float] = None) -> bool:
        """True si no hay cache, o si el cache supera el TTL.

        Umbral `>=`: un cache de exactamente TTL días también se renueva —
        replica la intención legible de data_ingestion (`>=1`), aunque aquí la
        unidad es de días financieros (90).
        """
        now = now if now is not None else time.time()
        path = self._cache_path(symbol)
        if not os.path.exists(path):
            return True
        age = self._cache_age_days(path, now)
        return age is None or age >= TTL_DAYS

    def _read_cache(self, symbol: str) -> Optional[Dict]:
        path = self._cache_path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("fundamentals_cache_read_failed", extra={"symbol": symbol, "error": str(e)})
            return None

    # ------------------------------- ingest -------------------------------

    def ingest_symbol(self, symbol: str, force: bool = False, now: Optional[float] = None) -> Optional[Dict]:
        """Devuelve el paquete crudo del símbolo (cache fresco o ingesta live), o
        None si no se pudo obtener nada. Con `force` ignora el cache.

        Señales de log distintas por rama (esquema corregido de data_ingestion):
        - cache miss → "full ingest"
        - cache vacío/truncado → treat as miss → "full ingest"
        - cache fresco → "cache hit: fresh, no refresh needed"
        - cache stale → refresh live
        - refresh vacío → conserva cache previo marcado (nunca borra datos)
        """
        sym = symbol.upper()
        now = now if now is not None else time.time()
        path = self._cache_path(sym)

        if not force and os.path.exists(path):
            cached = self._read_cache(sym)
            if cached is None:
                # cache corrupto/truncado → tratar como miss, ingesta completa.
                print(f"[fundamentals_ingestion] {sym} cache empty/corrupt, full ingest")
                return self._ingest_live(sym, now, path)
            if not self.needs_refresh(sym, now=now):
                age = self._cache_age_days(path, now)
                print(
                    f"[fundamentals_ingestion] {sym} cache hit: fresh, "
                    f"age {age:.0f}d <= {TTL_DAYS}d, no refresh needed"
                )
                return cached
            # cache stale → refresh live (si falla, conservar cache previo).
            print(
                f"[fundamentals_ingestion] {sym} cache stale: age "
                f"{self._cache_age_days(path, now):.0f}d > {TTL_DAYS}d, refreshing"
            )
            fresh = self._ingest_live(sym, now, path, preserve=cached)
            if fresh is not None:
                fresh["_data_source"] = "live_refresh"
                return fresh
            cached["_data_source"] = "stale_cache"
            return cached
        else:
            print(f"[fundamentals_ingestion] {sym} cache{'' if force else ' miss'}: full ingest")
            return self._ingest_live(sym, now, path)

    def _ingest_live(self, sym: str, now: float, path: str, preserve: Optional[Dict] = None) -> Optional[Dict]:
        """Baja statements+profile+price target de FMP y deposita el paquete en
        cache. Devuelve el paquete o None. Con `preserve` (cache viejo) si la
        ingesta falla avisa y devuelve None para que el llamador conserve previo.
        """
        if not self.fmp.is_available() or not self.fmp.api_key:
            logger.info("fundamentals_refresh_no_fmp_key", extra={"symbol": sym, "preserve": preserve is not None})
            return None

        income = self.fmp.income_statement(sym)
        bal = self.fmp.balance_sheet(sym)
        cash = self.fmp.cash_flow(sym)
        prof = self.fmp.profile(sym)
        pt = self.fmp.price_target_consensus(sym)

        # FMP devuelve listas — vacías ([]) cuando no hay datos del periodo.
        # Validar que las listas núcleo existan Y no estén vacías: si el
        # refresh trae statements vacíos lo tomamos como ingesta fallida y
        # (si hay cache previo) NO sobreescribimos con basura, se conserva.
        if (
            not isinstance(income, list)
            or not isinstance(bal, list)
            or not isinstance(cash, list)
            or not income
            or not bal
            or not cash
        ):
            print(f"[fundamentals_ingestion] {sym} refresh: attempted but FMP returned empty/invalid")
            logger.warning("fundamentals_refresh_attempted_empty", extra={"symbol": sym})
            return None

        payload: Dict[str, Any] = {
            "symbol": sym,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "income_statement": income,
            "balance_sheet": bal,
            "cash_flow": cash,
            "profile": self._first(prof),
            "price_target_consensus": self._first(pt) if isinstance(pt, list) else pt,
            "finnhub_crosscheck": self._finnhub_cross(sym),
            "_data_source": "fmp_live",
        }
        self._write_cache(path, payload)
        print(
            f"[fundamentals_ingestion] {sym} refresh: wrote {len(income)} income rows, "
            f"{len(bal)} balance rows, {len(cash)} cash rows"
        )
        return payload

    @staticmethod
    def _first(data: Any) -> Optional[Any]:
        # FMP devuelve profile / price-target-consensus como listas de 1 item.
        if isinstance(data, list) and data:
            return data[0]
        return data

    def _finnhub_cross(self, sym: str) -> Optional[Dict]:
        """Cruce opcional con Finnhub, nunca bloqueante y siempre no-verificado."""
        if self.finnhub is None or not getattr(self.finnhub, "is_available", lambda: False)():
            return None
        try:
            d = self.finnhub.get_fundamentals(sym)
            if d:
                d["_cross_unverified"] = True
            return d
        except Exception as e:  # pragma: no cover
            logger.warning("finnhub_cross_failed", extra={"symbol": sym, "error": str(e)})
            return None

    @staticmethod
    def _write_cache(path: str, payload: Dict) -> None:
        """Escritura atómica JSON (mismo contrato que utils.persistence):
        temp + os.replace para no dejar el archivo truncado tras un crash."""
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
