#!/usr/bin/env python3
"""verify_fmp_cause_live.py — Diagnóstico en vivo de por qué fundamentals_screen
produce resultados vacíos (rc=3 / STALE dashboard).

NO imprime valores de secretos: sólo booleans de disponibilidad y status HTTP
de red (probe con la API key pública 'demo', que no es secreto).

Uso (desde backend/):
    python scripts/verify_fmp_cause_live.py

Salida: dict VERDICT con la causa probable y si Fase 2 (Finnhub-as-primary)
estaría justificada. Este script es el artefacto de verificación del Frente 2
(hallazgo: FMP 510/510 vacío desde 04/09).
"""
import os
import sys
import json
import requests

# Hacer importable el paquete app/ sin importar settings con side-effects raros.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.config import settings  # noqa: E402
from app.core.fundamentals_ingestion import FundamentalsIngestion  # noqa: E402
from app.core.fundamentals_client import FinnhubClient  # noqa: E402


def _net_status(url: str) -> int:
    try:
        r = requests.get(url, timeout=8)
        return r.status_code
    except Exception:
        return -1


def main() -> int:
    fmp_key = bool(settings.FMP_API_KEY)
    finnhub_key = bool(settings.FINNHUB_API_KEY)

    # Red: probe con demo key (pública, NO secreto) para confirmar alcance de FMP/Finnhub.
    fmp_net_demo = _net_status("https://financialmodelingprep.com/stable/quote/AAPL?apikey=demo")
    finnhub_net_demo = _net_status("https://finnhub.io/api/v1/quote?symbol=AAPL&token=demo")

    # Ingesta real con la config actual (sin cliente Finnhub cableado, igual que en prod).
    ingester = FundamentalsIngestion()
    finnhub_client_wired = ingester.finnhub is not None
    sample = ingester.ingest_symbol("AAPL")  # usa cache si existe y es fresco
    sample_none = sample is None
    cross = ingester.crosscheck_finnhub_availability("AAPL")

    # ¿Estaría disponible Finnhub si la key existiera? (sin cablearlo al ingestor)
    finnhub_client_available = FinnhubClient().is_available()

    # --- Probe CON LA KEY REAL (sólo registramos el STATUS HTTP, nunca el valor) ---
    # Esto distingue 401 (key inválida) de 429 (cuota agotada) de 5xx (outage) de 200 (ok).
    fmp_real_status = None
    if fmp_key:
        try:
            r = requests.get(
                f"{ingester.fmp.base_url}/quote/AAPL",
                params={"apikey": ingester.fmp.api_key},
                timeout=10,
            )
            fmp_real_status = r.status_code
        except Exception:
            fmp_real_status = -1
    finnhub_real_status = None
    if finnhub_key:
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": "AAPL", "token": settings.FINNHUB_API_KEY},
                timeout=10,
            )
            finnhub_real_status = r.status_code
        except Exception:
            finnhub_real_status = -1

    verdict = {
        "fmp_api_key_present": fmp_key,
        "finnhub_api_key_present": finnhub_key,
        "fmp_network_status_demo": fmp_net_demo,
        "finnhub_network_status_demo": finnhub_net_demo,
        "fmp_real_status_with_key": fmp_real_status,
        "finnhub_real_status_with_key": finnhub_real_status,
        "fmp_client_available": ingester.fmp.is_available(),
        "finnhub_client_wired_into_ingestor": finnhub_client_wired,
        "finnhub_client_available_if_key_present": finnhub_client_available,
        "sample_ingest_AAPL_is_none": sample_none,
        "sample_crosscheck": cross,
        "cause": None,
        "phase2_finnhub_as_primary_warranted": False,
        "recommendation": None,
    }

    # Diagnóstico de causa (ordenado de más a menos probable dado el patrón 510/510).
    if not fmp_key:
        verdict["cause"] = (
            "FMP_API_KEY ausente/vacío en .env -> _ingest_live devuelve None para TODOS "
            "los simbolos -> results vacío -> rc=3/STALE. Patrón 510/510 uniforme = credencial "
            "faltante, NO outage de FMP (un outage no afectaria los 510 a la vez)."
        )
    elif fmp_real_status == 429:
        verdict["cause"] = (
            "FMP devuelve 429 (rate-limited) CON la key real. Causa de 510/510 vacío: el free "
            "tier de FMP es 250 llamadas/dia, pero el screening de 510 simbolos x 5 endpoints "
            "(income/balance/cash_flow/profile/price_target) = 2550 llamadas por corrida -> la "
            "cuota diaria se agota casi de inmediato. Como el cache TTL es 90d y la PRIMER corrida "
            "ya falla por 429, el cache NUNCA se puebla -> deadlock de cold-start: cada corrida "
            "reintenta los 510 frescos y vuelve a agotar cuota. NO es outage de FMP ni key inválida."
        )
    elif fmp_real_status == 401:
        verdict["cause"] = "FMP 401 con key real -> key inválida/expirada."
    elif fmp_real_status and fmp_real_status >= 500:
        verdict["cause"] = f"FMP responde {fmp_real_status} -> outage del endpoint FMP."
    elif fmp_real_status == -1:
        verdict["cause"] = "Sin red hacia FMP con la key real -> revisar conectividad/proxy."
    else:
        verdict["cause"] = (
            f"FMP status {fmp_real_status} con key real; la ingesta devolvió "
            f"{'vacío' if sample_none else 'datos'} -> revisar otro origen del vacío."
        )

    verdict["recommendation"] = (
        "CAUSA = cuota FMP agotada (429), no outage ni key rota. Soluciones reales (no Fase 2): "
        "(1) Reducir el universo a <=~40-50 simbolos/dia para entrar en el free tier 250/dia, o "
        "distribuir los 510 en varios dias usando state.json + --resume (ya implementado). "
        "(2) Subir el plan FMP (paid) si se quiere el universo completo diario. "
        "(3) El cache de 90d ya evita refetch; el problema es solo el cold-start inicial. "
        "Fase 2 (Finnhub-as-primary) NO amerita: Finnhub da ratios, no los statements que consume "
        "compute_scores(); y Finnhub aca no tiene key. El cross-check Finnhub queda como respaldo "
        "de disponibilidad si se provee FINNHUB_API_KEY."
    )

    print(json.dumps(verdict, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
