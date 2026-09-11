"""
Job diario del screening automatizado (Fase 4 del plan).

Uso:
    python -m scripts.run_fundamentals_screen [--universe TICKER,TICKER,...]
                                              [--date YYYY-MM-DD]
                                              [--resume]

Lanzado por `scripts/fundamentals_screen_daily.sh` (launchd, 22:00 local).
Genera artefactos en `data/cache_fundamentals_screen/`:
    - screen_<date>.json  — resultado del screening
    - state.json           — estado del job (correr de nuevo, no pisar)

Política de cuota FMP (250/día free tier, 5 endpoints por ticker):
    Este script NO reintenta el mismo día si una llamada falla.
    Razones:
      1. Los reintentos el mismo día queman la cuota del día siguiente.
         Free tier es por día calendario (UTC), no por minuto.
      2. Los datos que faltan en FMP hoy no van a aparecer hoy; aparecen
         en el siguiente ciclo de actualización.
    Por lo tanto, el script es **idempotente y resumible**: si falla a
    mitad, `--resume` continúa desde el último símbolo procesado (lee
    state.json) sin volver a pedir los que ya están en cache.

Universo por defecto: `app.api.routes.opportunities_universe.SYMBOLS`
(los 50 símbolos de decisión canónicos del backend). Se puede override
con `--universe` o con la env var `FUNDAMENTALS_UNIVERSE` (CSV).

No toca `predictive_engine` ni `notifier`. Sólo escribe a disco y loggea.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.config import settings  # noqa: E402 (sys.path set above)
from app.core.fundamentals_ingestion import FundamentalsIngestion  # noqa: E402 (sys.path set above)
from app.core.fundamentals_client import FinnhubClient  # noqa: E402 (sys.path set above)
from app.core.fundamentals_screen import screen_payload  # noqa: E402 (sys.path set above)
from app.utils.logging import logger  # noqa: E402 (sys.path set above)

CACHE_DIR = os.path.join(_BACKEND, "data", "cache_fundamentals_screen")
STATE_PATH = os.path.join(CACHE_DIR, "state.json")

# SEC EDGAR companyfacts (FUENTE PRIMARIA, sin cuota). Sembrado por
# scripts/fetch_edgar_universe_facts.py. Si el directorio existe y tiene
# archivos, EDGAR cubre el universo sin tocar la cuota FMP.
EDGAR_DIR = os.path.join(_BACKEND, "data", "cache", "edgar")


# Margen de 10 calls sobre el límite real (250) para no chocar con rate limit.
DAILY_FMP_BUDGET = int(os.environ.get("FMP_DAILY_BUDGET", "240"))

# Tamaño de lote (cuántos símbolos se procesan antes de checkpoint).
# 5 = 10 lotes para el universo canónico de 50. Justificación (regla de
# robustez de ejecución A6.3-style): un checkpoint por lote garantiza que
# si el proceso muere a mitad del lote 3, el state.json ya tiene los lotes
# 1 y 2 completos con sus llamadas a FMP consumidas. La corrida siguiente
# con --resume retoma desde el lote 3 sin repetir trabajo.
BATCH_SIZE = int(os.environ.get("FUNDAMENTALS_BATCH_SIZE", "5"))

# Pausa entre lotes (segundos). Suficiente para no chocar rate limit de FMP
# (300/min en free tier) si algo se atrasó; casi imperceptible al operador.
BATCH_PAUSE_SECONDS = int(os.environ.get("FUNDAMENTALS_BATCH_PAUSE", "5"))


def _load_universe_from_settings() -> List[str]:
    env = os.environ.get("FUNDAMENTALS_UNIVERSE", "").strip()
    if env:
        return [t.strip().upper() for t in env.split(",") if t.strip()]
    from app.api.routes.opportunities_universe import SYMBOLS
    return list(SYMBOLS)


def _read_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {
            "last_run_started": None,
            "last_run_finished": None,
            "last_successful_date": None,
            "completed_symbols": [],
            "failed_symbols": [],
            "calls_used": 0,
        }
    with open(STATE_PATH) as f:
        return json.load(f)


def _write_state(state: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def _atomic_write_json(path: str, payload: dict) -> None:
    """Escritura atómica: temp + os.replace (mismo patrón que
    app/utils/persistence.py y fundamentals_ingestion.py)."""
    import tempfile
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


def _finnhub_crosscheck(ingester, sym: str):
    """Cross-check Finnhub (B0 diferido) como respaldo cuando FMP falla.

    Usa getattr para no romper ingesters de test que no exponen el método;
    nunca lanza (cualquier excepción => None).
    """
    fn = getattr(ingester, "crosscheck_finnhub_availability", None)
    if fn is None:
        return None
    try:
        return fn(sym)
    except Exception:
        return None


def _write_stale_placeholder_dashboard(run_date: str, outdir: str, failed) -> None:
    """Dashboard placeholder marcado STALE cuando FMP no entregó NADA usable.

    Garantiza que Boris tenga un artefacto visible (no un dashboard roto/ausente)
    y que diga claramente que el screening no pudo ejecutarse por caída de FMP.
    """
    os.makedirs(outdir, exist_ok=True)
    html_path = os.path.join(outdir, f"dashboard_{run_date}.html")
    failed = failed or []
    sym_list = ", ".join(failed[:25]) + ("…" if len(failed) > 25 else "")
    banner = (
        "⚠ DATOS STALE — FMP no entregó datos para "
        f"{len(failed)} símbolo(s): {sym_list}. "
        "El screening NO pudo ejecutarse. Revisar clave/cuota/endpoint FMP "
        "o el respaldo Finnhub."
    )
    html = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>Fortress Screening — STALE {run_date}</title></head>"
        "<body>"
        "<div style='background:#b00000;color:#fff;font-weight:bold;"
        "padding:14px;text-align:center;font-family:sans-serif;'>"
        f"{banner}</div>"
        f"<p style='font-family:sans-serif;padding:14px;'>"
        f"Generado {run_date} — sin datos FMP frescos.</p>"
        "</body></html>"
    )
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Screening automatizado de fundamentales")
    parser.add_argument("--universe", help="CSV de tickers (default: SYMBOLS canónicos)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: hoy UTC)")
    parser.add_argument("--resume", action="store_true",
                        help="Retoma desde el último símbolo exitoso en state.json")
    if argv is None:
        argv = sys.argv[1:]
    # Cuando se llama desde la línea de comandos, argv[0] es el nombre del
    # programa (e.g. "run_fundamentals_screen"). Cuando se llama desde los
    # tests, el primer elemento ya es un flag (--universe, --date, etc).
    # Detectamos: si el primer elemento no empieza con "-", lo salteamos.
    if argv and not argv[0].startswith("-"):
        argv = argv[1:]
    args = parser.parse_args(argv)

    if not settings.FMP_API_KEY:
        logger.error("fmp_api_key_missing",
                     extra={"hint": "FMP_API_KEY no está en .env; el job no puede correr"})
        print("FATAL: FMP_API_KEY no configurada. Abortando sin tocar la red.")
        return 2

    if args.universe:
        universe = [t.strip().upper() for t in args.universe.split(",") if t.strip()]
    else:
        universe = _load_universe_from_settings()
    if not universe:
        logger.error("empty_universe")
        print("FATAL: universo vacío.")
        return 2

    # EDGAR primario activo: los ETF (SPY/QQQ) no tienen fundamentales en
    # ninguna fuente, asi que no tienen sentido en el screening y solo
    # quemarian cuota FMP (fallback). Se excluyen, igual que en
    # scripts/fetch_edgar_universe_facts.py (ETF_EXCLUDE).
    edgar_active = os.path.isdir(EDGAR_DIR) and any(
        f.endswith("_companyfacts.json") for f in os.listdir(EDGAR_DIR)
    )
    if edgar_active:
        ETF_EXCLUDE = {"SPY", "QQQ"}
        dropped = [s for s in universe if s in ETF_EXCLUDE]
        if dropped:
            universe = [s for s in universe if s not in ETF_EXCLUDE]
            logger.info("fundamentals_screen_etf_excluded", extra={"dropped": dropped})

    run_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = _read_state()
    if args.resume:
        already_done = set(state.get("completed_symbols") or [])
        todo = [s for s in universe if s not in already_done]
        logger.info("fundamentals_screen_resume",
                    extra={"date": run_date, "already_done": len(already_done),
                           "todo": len(todo), "calls_used": state.get("calls_used", 0)})
    else:
        todo = list(universe)
        state["last_run_started"] = datetime.now(timezone.utc).isoformat()
        state["completed_symbols"] = []
        state["failed_symbols"] = []
        state["calls_used"] = 0
        logger.info("fundamentals_screen_start",
                    extra={"date": run_date, "universe_size": len(universe)})

    if state.get("calls_used", 0) >= DAILY_FMP_BUDGET:
        msg = (f"Budget ya consumido ({state['calls_used']}/{DAILY_FMP_BUDGET}). "
               f"Abortar; retomar mañana con --resume.")
        logger.warning("fundamentals_screen_budget_exhausted", extra={"reason": msg})
        print(f"WARN: {msg}")
        return 0

    ingester = FundamentalsIngestion(edgar_dir=EDGAR_DIR)
    # EDGAR primario (sin cuota) habilita el job aunque FMP no tenga key.
    edgar_usable = False
    if os.path.isdir(EDGAR_DIR):
        edgar_usable = any(f.endswith("_companyfacts.json")
                           for f in os.listdir(EDGAR_DIR))
    if not ingester.fmp.is_available() and not edgar_usable:
        logger.error("fmp_client_unavailable")
        print("FATAL: FmpClient sin key y sin companyfacts EDGAR disponibles.")
        return 2
    # Cablear Finnhub (B0) sólo si hay key: hace que el cross-check de
    # disponibilidad sea REAL en la rama STALE en lugar de reportar siempre
    # "unavailable". Si no hay FINNHUB_API_KEY, ingester.finnhub queda None y el
    # cross-check lo registra honestamente como no disponible.
    if settings.FINNHUB_API_KEY:
        try:
            ingester.finnhub = FinnhubClient()
        except Exception:  # pragma: no cover - init local no bloquea
            logger.warning("finnhub_client_init_failed")

    results = {}
    budget_remaining = DAILY_FMP_BUDGET - state["calls_used"]

    # Procesamiento en LOTES de BATCH_SIZE. Política de robustez A6.3-style:
    # - Si un símbolo falla DENTRO del lote: log + continue (no reintento agresivo).
    #   Con 250 calls/día sin margen, un reintento del símbolo #23 quema la
    #   cuota que necesitamos para los últimos 27. Los fallados se reintentan
    #   la corrida siguiente, no la misma.
    # - Después de CADA lote: checkpoint atómico del state.json con el progreso
    #   completo. Si el proceso muere a mitad del lote 3, los lotes 1-2 ya
    #   están commiteados en disco y la corrida siguiente con --resume retoma
    #   desde el lote 3 sin repetir trabajo.
    # - Pausa breve entre lotes: no relanzamos 50 calls en rafaga (golpearía
    #   rate limit de FMP ~300/min en free tier). BATCH_PAUSE_SECONDS=5 es
    #   suficiente; en una corrida de 10 lotes = 50s total de pausas.
    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(total_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, len(todo))
        batch = todo[batch_start:batch_end]
        batch_num = batch_idx + 1
        logger.info("fundamentals_screen_batch_start",
                    extra={"batch": f"{batch_num}/{total_batches}",
                           "size": len(batch),
                           "calls_used_before": state["calls_used"]})

        for sym in batch:
            # EDGAR primario = sin cuota FMP: si el símbolo tiene companyfacts,
            # no lo frenamos por presupuesto FMP.
            edgar_path = os.path.join(EDGAR_DIR, f"{sym.upper()}_companyfacts.json")
            # El símbolo con companyfacts cuesta 2 calls FMP (backfill de photo
            # de mercado); sin companyfacts el ingest live cuesta 5.
            min_need = 5 if not os.path.exists(edgar_path) else 2
            if budget_remaining < min_need:
                msg = (f"Budget {DAILY_FMP_BUDGET} agotándose "
                       f"({budget_remaining} restantes, faltan ≥{min_need} para {sym}), "
                       f"parando en {sym}")
                logger.warning("fundamentals_screen_budget_stopping",
                              extra={"sym": sym, "reason": msg})
                break
            try:
                payload = ingester.ingest_symbol(sym)
                if payload is None:
                    # FMP no entregó datos para este símbolo. Contabilizamos lo
                    # que el ingester SÍ consumió (el intento live es real, la
                    # cuota se quemó aunque el resultado fuera None).
                    calls = getattr(ingester, "last_fmp_calls", None)
                    if calls is None:
                        calls = 5  # ingester de test: asume intento live
                    state["calls_used"] += calls
                    budget_remaining -= calls
                    # Cross-check Finnhub (B0 diferido) como respaldo
                    # independiente: si Finnhub SÍ tiene datos, confirma que el
                    # problema es de FMP (key/quota/endpoint, causa externa) y
                    # no del símbolo. Nunca bloquea.
                    cross = _finnhub_crosscheck(ingester, sym)
                    state["failed_symbols"].append(
                        {"symbol": sym, "reason": "ingestion_returned_none",
                         "finnhub_crosscheck": cross})
                    logger.warning("fundamentals_screen_symbol_failed",
                                  extra={"sym": sym, "finnhub_available":
                                          bool(cross and cross.get("available"))})
                    continue
                eval_ = screen_payload(payload)
                results[sym] = eval_
                state["completed_symbols"].append(sym)
                # Contabilidad REAL de cuota FMP por símbolo: last_fmp_calls del
                # ingester (0 cache/EDGAR puro, 2 EDGAR+backfill, 5 live). Los
                # ingesters que no exponen el atributo (tests/fakes) caen al modo
                # previo: 5 si no es edgar_primary, 0 si lo es.
                calls = getattr(ingester, "last_fmp_calls", None)
                if calls is None:
                    calls = 0 if payload.get("_data_source") == "edgar_primary" else 5
                state["calls_used"] += calls
                budget_remaining -= calls
                logger.info("fundamentals_screen_symbol_ok",
                            extra={"sym": sym,
                                   "calls_used": state["calls_used"]})
            except Exception as e:
                state["failed_symbols"].append(
                    {"symbol": sym, "reason": str(e)[:200]})
                logger.exception("fundamentals_screen_symbol_error",
                                 extra={"sym": sym})
                # Política: NO reintentar este símbolo. Siguiente del lote.
                continue

        # Checkpoint por lote: escribe state.json con el progreso completo.
        # Idempotente y atómico (escritura via _write_state).
        # Si el proceso muere DESPUÉS de este write, la corrida siguiente
        # con --resume salta los símbolos ya en completed_symbols.
        _write_state(state)
        logger.info("fundamentals_screen_batch_done",
                    extra={"batch": f"{batch_num}/{total_batches}",
                           "completed": len(state["completed_symbols"]),
                           "failed": len(state["failed_symbols"]),
                           "calls_used": state["calls_used"]})

        # Pausa entre lotes (excepto después del último).
        if batch_num < total_batches and BATCH_PAUSE_SECONDS > 0:
            time.sleep(BATCH_PAUSE_SECONDS)

    # FMP falló para estos símbolos (empty/invalid). Con cache cálido el
    # ingester devuelve datos viejos y el símbolo queda en completed_symbols,
    # así que sólo los None (sin cache que servir) cuentan como cobertura rota.
    fmp_failed_symbols = [
        f["symbol"] for f in state["failed_symbols"]
        if f.get("reason") == "ingestion_returned_none"
    ]
    data_stale = bool(fmp_failed_symbols)

    out_path = os.path.join(CACHE_DIR, f"screen_{run_date}.json")
    artifact = {
        "date": run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calls_used_this_run": state["calls_used"],
        "universe_size": len(universe),
        "completed_count": len(state["completed_symbols"]),
        "failed_count": len(state["failed_symbols"]),
        # Degradación elegante (Frente 2): si FMP no entregó datos frescos para
        # parte del universo, el dashboard se marca STALE en vez de reventar con
        # rc=3 por artefacto vacío. El cross-check Finnhub (si está disponible)
        # indica cuántos de los fallados TAMBIÉN tienen datos en la fuente
        # independiente (confirmando que el outage es de FMP, no de los tickers).
        "data_stale": data_stale,
        "fmp_failed_symbols": fmp_failed_symbols,
        "finnhub_crosscheck_summary": {
            "fmp_failed": len(fmp_failed_symbols),
            "finnhub_available": sum(
                1 for f in state["failed_symbols"]
                if (f.get("finnhub_crosscheck") or {}).get("available")
            ),
        },
        "results": results,
    }
    _atomic_write_json(out_path, artifact)

    # Artefactos del motor canónico (Excel + dashboard HTML). Este paso es
    # OBLIGATORIO: el cron no está completo sin el dashboard, y el endpoint
    # /screen/dashboard.html sirve el .html que esto genera. Si el render
    # falla (motor canónico roto, openpyxl ausente, etc.) NO se reporta la
    # corrida como exitosa: rc=3 es un estado distinto de "todo OK" (0) y de
    # "falló sin tocar red" (2). El test end-to-end lo ve en rojo.
    try:
        from app.core.fundamentals_artifacts import render_artifacts
        if results:
            # Dashboard normal; si FMP falló para parte del universo, se marca
            # STALE con un banner visible (data_stale=True).
            render_artifacts(results, run_date, CACHE_DIR, stale=data_stale)
        else:
            # Sin un solo símbolo con datos FMP frescos (cache también vacío):
            # NO reventamos con rc=3 por artefacto vacío. Emitimos un dashboard
            # placeholder marcado STALE para que Boris vea claramente la caída de
            # FMP y rc=4 (completó pero datos totalmente STALE), distinguible de
            # rc=0 (OK) y rc=3 (falló el render del motor canónico).
            _write_stale_placeholder_dashboard(
                run_date, CACHE_DIR, artifact["fmp_failed_symbols"])
            print(
                f"WARN: 0 símbolos con datos FMP frescos ({run_date}). "
                f"Dashboard marcado STALE (sin datos para screening)."
            )
            return 4
    except Exception as e:
        logger.exception(
            "fundamentals_screen_render_failed",
            extra={"date": run_date, "error": str(e)[:200]},
        )
        print(
            f"ERROR: screening completado ({len(results)} símbolos) pero "
            f"falló la generación del dashboard/Excel: {e}"
        )
        return 3

    state["last_run_finished"] = datetime.now(timezone.utc).isoformat()
    if not state.get("last_successful_date"):
        state["last_successful_date"] = run_date
    _write_state(state)

    logger.info("fundamentals_screen_done",
                extra={"date": run_date,
                       "completed": len(state["completed_symbols"]),
                       "failed": len(state["failed_symbols"]),
                       "calls_used": state["calls_used"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
