"""Acumulador de sentimiento de earnings calls — Tarea B del plan de largo plazo, PASO 1.

METODOLOGÍA (documentada — es la base del trial del PASO 2):
  - FUENTE: SEC EDGAR, formulario 8-K item 2.02 (comunicado de prensa oficial
    de la gerencia, point-in-time). No se usa Seeking Alpha (ToS restrictivos)
    ni transcripciones de terceros (regla del proyecto: no scrapear fuentes
    dudosas).
  - LIMITACIÓN: el 8-K item 2.02 es el COMUNICADO de prensa, NO la
    transcripción verbatim del earnings call. El tono del comunicado es una
    proxy del tono del call (sin preguntas y respuestas). Si el trial del
    PASO 2 sale nulo, esto es parte de la explicación posible.
  - MODELO: FinBERT (ProsusAI/finbert, HuggingFace) — clasificación
    positive/negative/neutral por chunk. score = prob_pos - prob_neg en
    [-1, +1]; el neutral queda implícito en ~0.
  - CHUNKING: el comunicado excede los 512 tokens de BERT → se divide por
    oraciones con longitud objetivo ~1800 chars (~380 tokens).
  - AGREGACIÓN: promedio ponderado por longitud de chunk:
    score = sum(score_i * len_i) / sum(len_i).
  - ACUMULACIÓN: backfill de los últimos ~8 8-Ks 2.02 por símbolo (≈8
    trimestres reales ya publicados) y luego incremental: las accession ya
    guardadas en SQLite (UNIQUE) no se re-procesan. Los ETFs (SPY/QQQ/…) se
    excluyen: no tienen earnings calls.

USO:
    .venv/bin/python scripts/accumulate_earnings_sentiment.py
    .venv/bin/python scripts/accumulate_earnings_sentiment.py --symbols AAPL NVDA
    .venv/bin/python scripts/accumulate_earnings_sentiment.py --count 12 --limit 5

ESTE SCRIPT NO CORRE EL TRIAL del PASO 2 (bloqueado por datos: se necesita
≥8 trimestres acumulados para ≥30 símbolos — "no simular datos").
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.earnings_sentiment import (  # noqa: E402
    DEFAULT_DB_PATH,
    EarningsSentimentStore,
    accumulate_earnings_sentiment,
)
from scripts.fetch_universe_data import NEW_UNIVERSE  # noqa: E402

UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] + list(NEW_UNIVERSE)

RUN_ARTIFACT_PREFIX = "data/cache/earnings_sentiment_run_"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=None,
                        help="Símbolos extra (además del universo) o subconjunto a procesar.")
    parser.add_argument("--count", type=int, default=8,
                        help="Cuántos 8-Ks 2.02 por símbolo (default 8 ≈ 8 trimestres).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limitar el universo a los primeros N símbolos (pruebas).")
    parser.add_argument("--db", default=os.environ.get("FORTRESS_SENTIMENT_DB", DEFAULT_DB_PATH),
                        help="Ruta de la base SQLite.")
    args = parser.parse_args()

    symbols = UNIVERSE
    if args.limit is not None:
        symbols = symbols[: args.limit]
    if args.symbols:
        symbols = list(args.symbols)

    store = EarningsSentimentStore(args.db)
    try:
        summary = accumulate_earnings_sentiment(
            symbols, store, count=args.count, log=lambda m: print(m, flush=True)
        )
    finally:
        store.close()

    lines = [
        "=" * 60,
        f"Corrida {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"Universo: {len(symbols)} símbolos ({summary['symbols']} con earnings, "
        f"{len(summary['etf_excluded'])} ETF excluidos: {', '.join(summary['etf_excluded'])})",
        f"Símbolos procesados: {len(summary['processed'])} — {', '.join(sorted(summary['processed']))}",
        f"8-Ks nuevos: {summary['new_filings']}",
        f"Total en store: {summary['total_in_store']}",
    ]
    if summary["errors"]:
        lines.append(f"ERRORES ({len(summary['errors'])}):")
        lines += [f"  {s}: {e}" for s, e in summary["errors"].items()]
    else:
        lines.append("ERRORES: ninguno")
    lines.append("=" * 60)
    report = "\n".join(lines)
    print("\n" + report, flush=True)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact = RUN_ARTIFACT_PREFIX + stamp + ".txt"
    with open(artifact, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    print(f"Resumen: {artifact}", flush=True)

    if summary["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
