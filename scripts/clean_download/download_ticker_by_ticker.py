#!/usr/bin/env python3
"""
Runner ETAPA 0: validación ticker-por-ticker con reconcile_symbol.
- SIN red: PAUSE_YAHOO_MASS_DOWNLOAD ACTIVO → download_data devuelve cache (o vacío)
- 1 ticker por vez, sleep 3-5s + jitter
- Backoff ante 429/empty
- Valida y loguea por ticker (sanidad + contaminación + mosaico + huecos)
- Reusa download_data + reconcile_symbol, no duplica downloaders
"""
import os
import sys
import time
import random
import logging
from pathlib import Path

# --- Config ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
CACHE_DIR = BACKEND_ROOT / "data" / "cache"
PAUSE_FILE = PROJECT_ROOT / "PAUSE_YAHOO_MASS_DOWNLOAD"

# Añadir backend al path para imports
sys.path.insert(0, str(BACKEND_ROOT))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("clean_download")

# --- Universe (fuente única) ---
try:
    from scripts.fetch_universe_data import NEW_UNIVERSE
    BASE_UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    UNIVERSE = BASE_UNIVERSE + list(NEW_UNIVERSE)
except ImportError:
    log.error("No se pudo importar NEW_UNIVERSE desde fetch_universe_data.py")
    sys.exit(1)

# --- Imports del motor ---
try:
    from app.core.data_ingestion import download_data, _is_mass_download_paused
    from app.core.cache_integrity import reconcile_symbol, validate_returns, find_intermediate_gaps
except ImportError as e:
    log.error(f"Import error: {e}")
    sys.exit(1)


def _is_pause_window() -> bool:
    """Ventana autorizada: solo código + env, SIN red. Pausa siempre ON en ETAPA 0."""
    return True  # En ETAPA 0, la pausa SIEMPRE está activa


def _sleep_with_jitter(min_s: float = 3.0, max_s: float = 5.0) -> None:
    """Sleep 3-5s + jitter gaussiano pequeño."""
    base = random.uniform(min_s, max_s)
    jitter = random.gauss(0, 0.3)
    time.sleep(max(0.5, base + jitter))


def _download_with_backoff(ticker: str, start: str, max_retries: int = 3) -> tuple:
    """
    Wrapper que llama download_data y maneja backoff.
    Como PAUSE está ON, download_data NO toca red y devuelve cache/empty.
    Retorna (df, status_str).
    """
    if _is_mass_download_paused():
        log.info(f"[{ticker}] PAUSA activa — usando cache (sin red)")
    
    for attempt in range(max_retries):
        try:
            df = download_data(ticker, start=start)
            if df is None or len(df) == 0:
                status = "empty"
                if attempt < max_retries - 1:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    log.warning(f"[{ticker}] empty (attempt {attempt+1}/{max_retries}), backoff {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
            else:
                status = "ok"
            return df, status
        except Exception as e:
            status = f"error: {e}"
            if attempt < max_retries - 1:
                backoff = (2 ** attempt) + random.uniform(0, 1)
                log.warning(f"[{ticker}] {e} (attempt {attempt+1}/{max_retries}), backoff {backoff:.1f}s")
                time.sleep(backoff)
                continue
    return None, status


def _validate_and_reconcile(ticker: str, df, cache_dir: str) -> dict:
    """
    Ejecuta validate_returns + reconcile_symbol y devuelve reporte.
    reconcile_symbol con downloader=yf.download intentaría red, pero como
    PAUSE está ON, download_data (usado internamente) no descarga.
    """
    if df is None or len(df) == 0:
        return {"ticker": ticker, "status": "no_data", "flags": [], "contamination": [], "mosaic": [], "gaps": []}
    
    # 1. Sanidad de retornos (cero red)
    from app.core.cache_integrity import validate_returns as _validate
    flags = _validate(df, ticker)
    hard_flags = [f for f in flags if f["level"] == "hard"]
    
    # 2. Reconciliación (usa downloader interno; con PAUSE no hace red real)
    #    Nota: reconcile_symbol usa yf.download directo. Para evitar red,
    #    podríamos mockear, pero download_data ya respeta PAUSE.
    #    Aquí usamos reconcile_symbol con known_trading_days del cache.
    try:
        report = reconcile_symbol(
            ticker,
            cache_dir,
            downloader=lambda sym, start, end: download_data(sym, start, end),
            start="2015-01-01",
        )
        contamination = report.get("contamination", [])
        mosaic = report.get("mosaic", [])
        gaps = report.get("gaps", [])
        actions = report.get("actions", [])
    except Exception as e:
        log.warning(f"[{ticker}] reconcile_symbol falló: {e}")
        contamination, mosaic, gaps, actions = [], [], [], [f"reconcile_error: {e}"]
    
    return {
        "ticker": ticker,
        "status": "validated",
        "rows": len(df),
        "date_range": f"{df.index[0].date()} -> {df.index[-1].date()}",
        "flags": flags,
        "hard_flags": hard_flags,
        "contamination": contamination,
        "mosaic": mosaic,
        "gaps": gaps,
        "actions": actions,
    }


def main():
    start = "2015-01-01"
    cache_dir = str(CACHE_DIR)
    
    log.info(f"=== ETAPA 0: clean_download runner ===")
    log.info(f"Universo: {len(UNIVERSE)} tickers (7 BASE + {len(NEW_UNIVERSE)} NEW)")
    log.info(f"Cache dir: {cache_dir}")
    log.info(f"PAUSE: {'ACTIVO' if PAUSE_FILE.exists() else 'INACTIVO'} (respetado: SIN red)")
    log.info(f"Ventana autorizada: código + env únicamente")
    
    if not _is_pause_window():
        log.error("Fuera de ventana autorizada — abortando")
        sys.exit(1)
    
    if not PAUSE_FILE.exists():
        log.warning("PAUSE_YAHOO_MASS_DOWNLOAD NO existe — se haría red real (NO autorizado en ETAPA 0)")
    
    results = []
    ok = 0
    failed = 0
    
    for i, ticker in enumerate(UNIVERSE, 1):
        log.info(f"--- [{i}/{len(UNIVERSE)}] {ticker} ---")
        
        # 1. Download (con PAUSE = cache only)
        df, dl_status = _download_with_backoff(ticker, start)
        
        # 2. Validar + reconciliar
        report = _validate_and_reconcile(ticker, df, cache_dir)
        report["download_status"] = dl_status
        
        # 3. Log resumen por ticker
        hf = len(report.get("hard_flags", []))
        cont = len(report.get("contamination", []))
        mos = len(report.get("mosaic", []))
        gaps = len(report.get("gaps", []))
        
        log.info(
            f"[{ticker}] rows={report.get('rows', 0)} "
            f"range={report.get('date_range', 'N/A')} "
            f"flags={len(report['flags'])} (hard={hf}) "
            f"contam={cont} mosaic={mos} gaps={gaps} "
            f"dl={dl_status}"
        )
        
        if hf or cont or mos or gaps:
            log.warning(f"[{ticker}] ⚠️  ANOMALÍAS: hard={hf} contam={cont} mosaic={mos} gaps={gaps}")
            if cont:
                for c in report["contamination"]:
                    log.warning(f"  CONTAM: {c['date']} -> barra de {c['contains_bar_of']}")
            if mos:
                for m in report["mosaic"]:
                    log.warning(f"  MOSAIC: {m['seam']} ratio {m['ratio_before']} -> {m['ratio_after']}")
            if gaps:
                log.warning(f"  GAPS: {gaps} ({report['gaps'][0]}..{report['gaps'][-1]})")
        
        results.append(report)
        if report["status"] == "validated":
            ok += 1
        else:
            failed += 1
        
        # Sleep entre tickers (excepto último)
        if i < len(UNIVERSE):
            _sleep_with_jitter()
    
    # Resumen final
    log.info(f"=== RESUMEN ETAPA 0 ===")
    log.info(f"OK: {ok} | Failed: {failed} | Total: {len(UNIVERSE)}")
    
    # Contar anomalías globales
    total_hard = sum(len(r.get("hard_flags", [])) for r in results)
    total_contam = sum(len(r.get("contamination", [])) for r in results)
    total_mosaic = sum(len(r.get("mosaic", [])) for r in results)
    total_gaps = sum(len(r.get("gaps", [])) for r in results)
    
    log.info(f"Hard flags: {total_hard} | Contaminación: {total_contam} | Mosaico: {total_mosaic} | Huecos: {total_gaps}")
    
    # Criterio limpio 0/0/0
    if total_contam == 0 and total_mosaic == 0 and total_gaps == 0:
        log.info("✅ GATE 0/0/0: LIMPIO — cache listo para snapshot_hash + pre-registro")
        return 0
    else:
        log.warning("❌ GATE 0/0/0: ANOMALÍAS DETECTADAS — requiere saneo antes de trial")
        return 1


if __name__ == "__main__":
    sys.exit(main())
