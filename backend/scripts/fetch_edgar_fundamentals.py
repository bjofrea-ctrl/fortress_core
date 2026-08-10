"""
Fase 1 — fetch de company facts XBRL de SEC EDGAR para el universo de acciones.

Descarga data.sec.gov/api/xbrl/companyfacts/<CIK>.json (5 tickers; SPY/QQQ son
ETFs y no tienen fundamentales en ninguna fuente) y los guarda en data/cache/edgar/.

Point-in-time: cada fact trae su fecha de filing real (la fecha en que la
empresa PUBLICÓ el dato) — no hay lookahead. "As originally reported":
los companyfacts de EDGAR conservan el valor del filing original.

Uso: python scripts/fetch_edgar_fundamentals.py
"""
import gzip
import json
import time
import urllib.request
from pathlib import Path

TICKERS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "NVDA": "0001045810",
}

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "edgar"

USER_AGENT = "Fortress Core research contact@fortresscore.local"


def fetch(cik: str, out_path: Path) -> bool:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    try:
        data = json.loads(raw)
    except UnicodeDecodeError:
        data = json.loads(gzip.decompress(raw))
    with open(out_path, "w") as fh:
        json.dump(data, fh)
    return True


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for symbol, cik in TICKERS.items():
        out = CACHE_DIR / f"{symbol}_companyfacts.json"
        if out.exists() and out.stat().st_size > 100_000:
            print(f"{symbol}: cache ya existe ({out.stat().st_size // 1024} KB), skip")
            continue
        fetch(cik, out)
        size_kb = out.stat().st_size // 1024
        print(f"{symbol}: descargado CIK {cik} ({size_kb} KB)")
        time.sleep(0.3)
    print("Listo.")


if __name__ == "__main__":
    main()
