"""A0 — Runner del harness de integridad del cache (CLI).

Uso (desde backend/, el venv real):
    .venv/bin/python -m scripts.cache_integrity_run [--cache-dir data/cache]
        [--json OUT.json] [--full]

Por símbolo del universo (102): flags de sanidad (parte 1), reconciliación
cache vs descarga fresca con detección de contaminación/mosaico/huecos y
reparación dirigida (parte 2), y snapshot del estado (parte 3).

--full: además reusa las descargas frescas de TODOS los símbolos para el
cross-check de contaminación (la barra contaminada matchea la barra real
del otro símbolo — identifica el origen). Sin --full, cada símbolo solo
se compara contra su propia descarga fresca (la divergencia basta para
disparar la re-descarga; el origen es informativo).

Salida: resumen por stdout + JSON con el reporte completo de cada símbolo
(artefacto de la corrida para el ledger/log).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402
from app.core.cache_integrity import (  # noqa: E402
    _market_days_present_in_cache,
    _norm,
    _universe_symbols,
    reconcile_symbol,
    snapshot_hash,
)


def main():
    parser = argparse.ArgumentParser(description="Harness de integridad del cache (A0)")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--json", default=None, help="ruta del artefacto JSON de la corrida")
    parser.add_argument("--full", action="store_true",
                        help="cross-check de contaminación con frescos de todos los símbolos")
    parser.add_argument("--symbols", nargs="*", default=None,
                        help="subconjunto (default: universo 102)")
    parser.add_argument("--start", default="2015-01-01")
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else _universe_symbols()
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    known = _market_days_present_in_cache(args.cache_dir, symbols)

    fresh_by_symbol = {}
    reports = []
    n_contam = n_mosaic = n_gaps = n_flags_hard = 0

    def downloader(ticker, start=None, end=None, progress=False):
        """Una sola descarga fresca por símbolo: la hace el runner, la
        cachea para el cross-check --full, y reconcile_symbol la reusa."""
        if ticker not in fresh_by_symbol:
            try:
                got = yf.download(ticker, start=start or args.start,
                                 end=end or pd.Timestamp.today().strftime("%Y-%m-%d"),
                                 progress=False)
            except Exception as exc:  # noqa: BLE001 — un símbolo roto no tumba la corrida
                print(f"[cache_integrity_run] {ticker} descarga fresca ERROR: {exc}")
                return pd.DataFrame()
            if got is not None and len(got):
                fresh_by_symbol[ticker] = _norm(got)
            else:
                return pd.DataFrame()
        return fresh_by_symbol[ticker].copy()

    for i, symbol in enumerate(symbols, 1):
        others = fresh_by_symbol if args.full else {}
        report = reconcile_symbol(
            symbol, args.cache_dir, downloader,
            start=args.start, end=end,
            other_symbols_fresh=others,
            known_trading_days=known,
        )
        reports.append(report)
        n_contam += len(report["contamination"])
        n_mosaic += len(report["mosaic"])
        n_gaps += len(report["gaps"])
        n_flags_hard += sum(1 for f in report["flags_returns"] if f["level"] == "hard")
        estado = []
        if report["contamination"]:
            estado.append(f"CONTAMINACION={len(report['contamination'])}")
        if report["mosaic"]:
            estado.append(f"MOSAICO={len(report['mosaic'])}")
        if report["gaps"]:
            estado.append(f"HUECOS={len(report['gaps'])}")
        if not estado:
            estado.append("OK")
        print(f"[{i}/{len(symbols)}] {symbol}: {' '.join(estado)}")

    remaining_gaps = sum(len(r.get("final_gaps", [])) for r in reports)
    remaining_hard = sum(
        1 for r in reports for f in r.get("final_flags", []) if f["level"] == "hard"
    )
    # hard-flags que persisten tras la re-descarga = movimientos REALES
    # (earnings) verificados contra fresco: no son defecto del cache.
    unverified = sum(
        1 for r in reports
        if "descarga fresca vacía" in " ".join(r.get("actions", []))
    )
    print()
    print(f"== Resumen A0 sobre {len(symbols)} símbolos ==")
    print(f"contaminaciones confirmadas: {n_contam}")
    print(f"seams de mosaico:            {n_mosaic}")
    print(f"huecos intermedios:          {n_gaps}")
    print(f"hard-flags de retorno:       {n_flags_hard} "
          f"(restantes {remaining_hard} = movimientos reales verificados vs fresco)")
    print(f"símbolos sin verificación (descarga fresca vacía): {unverified}")
    print(f"huecos RESTANTES tras reparar: {remaining_gaps}")

    artifact = {
        "ts": pd.Timestamp.now().isoformat(),
        "n_symbols": len(symbols),
        "cache_manifest": snapshot_hash(args.cache_dir, symbols),
        "reports": reports,
        "summary": {
            "contamination": n_contam,
            "mosaic": n_mosaic,
            "gaps": n_gaps,
            "hard_flags": n_flags_hard,
            "remaining_gaps": remaining_gaps,
            "remaining_hard_flags": remaining_hard,
        },
    }
    out = args.json or os.path.join("data", "cache_integrity_run.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"artefacto: {out}")
    # rc=1 solo si quedó DEFECTO sin reparar: huecos restantes o contaminación.
    # Hard-flags restantes son movimientos reales (verificados contra la
    # descarga fresca del propio símbolo) — un earnings de ±26% no es día sucio.
    return 1 if (remaining_gaps or n_contam) else 0


if __name__ == "__main__":
    sys.exit(main())
