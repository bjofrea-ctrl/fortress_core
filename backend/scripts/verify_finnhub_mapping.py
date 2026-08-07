"""
Corré esto UNA VEZ que tengas FINNHUB_API_KEY configurada en .env, para
confirmar que FIELD_MAP (app/core/fundamentals_client.py) apunta a los
nombres de campo correctos de la respuesta real de Finnhub — se armó sin
poder probarlo contra una key real.

Uso: .venv/bin/python scripts/verify_finnhub_mapping.py AAPL
"""
import json
import sys

from app.core.fundamentals_client import FinnhubClient, FIELD_MAP


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    client = FinnhubClient()

    if not client.is_available():
        print("FINNHUB_API_KEY no está configurada en .env — no hay nada que verificar todavía.")
        return

    raw = client._fetch_raw(symbol)
    if not raw:
        print(f"La llamada a Finnhub para {symbol} no devolvió datos. Revisá la key o el rate limit.")
        return

    print(f"=== Campos crudos que devolvió Finnhub para {symbol} (primeros 40) ===")
    for k in list(raw.keys())[:40]:
        print(f"  {k}: {raw[k]}")

    print(f"\n=== Resultado del mapeo actual (FIELD_MAP) ===")
    mapped = client.get_fundamentals(symbol, use_cache=False)
    print(json.dumps(mapped, indent=2))

    print(f"\n=== Campos de FIELD_MAP que NO se encontraron en la respuesta ===")
    for internal, finnhub_field in FIELD_MAP.items():
        if finnhub_field is not None and finnhub_field not in raw:
            print(f"  {internal} -> '{finnhub_field}' (no está en la respuesta — hay que corregir el mapeo)")


if __name__ == "__main__":
    main()
