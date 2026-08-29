"""
API routes — screening de fundamentales automatizado (Fase 4 del plan).

GET /api/fundamentals/screen/latest   — resultado del último screening diario
GET /api/fundamentals/screen?date=YYYY-MM-DD — screening de un día puntual
GET /api/fundamentals/screen/dashboard.html — HTML estático del dashboard
                                              (para embeber en iframe)
GET /api/fundamentals/screen/state    — estado del job (última corrida, cuotas,
                                        símbolos fallidos, próximos a refrescar)

Estructura del directorio de artefactos (generado por el cron
`scripts/fundamentals_screen_daily.sh`):
    data/cache_fundamentals_screen/
        screen_<date>.json          # resultado completo de un día
        dashboard_<date>.html       # HTML del motor canónico (generar_dashboard)
        state.json                   # estado del job (no pisar)

El cron corre a las 22:00 (mismo horario que dataupdater, mercado US ya
cerrado y FMP ya actualizado). Genera los artefactos; los endpoints los
leen. El endpoint NO toca la red — siempre lee de disco.

Política de cuota FMP (250/día free tier, 5 endpoints por ticker):
    Si el job falla a mitad, se guarda el progreso parcial y se retoma al
    día siguiente desde donde quedó. NO se reintenta el mismo día — eso
    quemaría la cuota del día siguiente y los reintentos tienen收益 cero
    (los datos no van a aparecer en el mismo día en FMP).

Convención de estilo: copiada de `app/api/routes/market.py` y `ranking.py`
(APIRouter + HTTPException, sin auth — los endpoints de solo-lectura
existentes tampoco la tienen).
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/fundamentals", tags=["fundamentals"])

# Regex de validación de fecha YYYY-MM-DD. Usada por get_screen_by_date
# como defensa adicional (FastAPI ya valida via Query(pattern=...)) y por
# los tests que llaman la función directo con asyncio.run sin TestClient.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Ubicación de los artefactos generados por el cron. Path absoluto calculado
# desde el archivo del router (no relativo al cwd — launchd no setea cwd
# del repo, y los routers se importan desde cualquier cwd).
_THIS = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.abspath(
    os.path.join(_THIS, "..", "..", "..", "data", "cache_fundamentals_screen")
)


def _artifact_path(date: str, name: str) -> str:
    return os.path.join(_CACHE_DIR, f"{name}_{date}.json")


def _list_available_dates() -> List[str]:
    """Devuelve las fechas disponibles en disco, ordenadas desc."""
    if not os.path.isdir(_CACHE_DIR):
        return []
    dates = set()
    for f in os.listdir(_CACHE_DIR):
        for prefix in ("screen_", "dashboard_"):
            if f.startswith(prefix):
                stem = f[len(prefix):]
                for ext in (".json", ".html"):
                    if stem.endswith(ext):
                        dates.add(stem[:-len(ext)])
                        break
                break
    return sorted(dates, reverse=True)


@router.get("/screen/latest")
async def get_screen_latest() -> Dict[str, Any]:
    """Devuelve el resultado del último screening diario disponible en disco.

    Si no hay ningún screening (cron nunca corrió o falló todas las veces),
    devuelve 503 con un mensaje accionable — el dashboard distingue
    "no hay datos" de "datos viejos".
    """
    dates = _list_available_dates()
    if not dates:
        raise HTTPException(
            status_code=503,
            detail="No hay screenings disponibles. El job diario aún no corrió "
                   "(o todas las corridas fallaron). Revisá scripts/fundamentals_screen_daily.log",
        )
    latest = dates[0]
    path = _artifact_path(latest, "screen")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=500,
            detail=f"Listado de fechas inconsistente: {latest} no tiene artefacto",
        )
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo {path}: {e}")


@router.get("/screen")
async def get_screen_by_date(date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")) -> Dict[str, Any]:
    """Devuelve el screening de una fecha puntual (YYYY-MM-DD).

    La validación del formato se hace en dos lugares:
    - `pattern=` en FastAPI valida antes de invocar la función (devuelve
      422 al cliente si la fecha no matchea).
    - El if al inicio es defensa adicional para tests que llaman la
      función directo con asyncio.run (sin TestClient). Garantiza que
      la función rechace fechas inválidas con el MISMO HTTPException
      que vería un cliente HTTP.
    """
    if not _DATE_RE.fullmatch(date or ""):
        raise HTTPException(
            status_code=422,
            detail=f"Formato de fecha inválido: {date!r}. Esperado YYYY-MM-DD.",
        )
    path = _artifact_path(date, "screen")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"No hay screening para {date}. Fechas disponibles: {_list_available_dates()[:5]}",
        )
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo {path}: {e}")


@router.get("/screen/dashboard.html", response_class=None)
async def get_dashboard_html(
    date: Optional[str] = None,  # type: ignore[assignment]
) -> Any:
    """Sirve el HTML estático del dashboard para embeber en iframe.

    Decisión de diseño PENDIENTE (esperando Boris): ¿se genera en el cron o
    on-demand? El esqueleto asume que el cron lo genera. Si en la práctica
    se quiere on-demand, este endpoint se conecta al motor canónico
    (~/claude/skills/aai-screening-acciones/scripts/motor_screening.py
    generar_dashboard) y agrega un import nuevo.

    El parámetro `date` es opcional (default: último disponible). No se
    valida con Query(pattern) porque la fecha con formato inválido no
    rompe la lógica (sólo devuelve 404 porque el archivo no existe).
    """
    if date is not None and not _DATE_RE.fullmatch(date):
        raise HTTPException(
            status_code=422,
            detail=f"Formato de fecha inválido: {date!r}. Esperado YYYY-MM-DD.",
        )
    if date is None:
        dates = _list_available_dates()
        if not dates:
            raise HTTPException(status_code=503, detail="No hay dashboard disponible todavía.")
        date = dates[0]
    path = _artifact_path(date, "dashboard").replace(".json", ".html")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"No hay dashboard HTML para {date}. El cron debe haberlo generado.",
        )
    from fastapi.responses import HTMLResponse
    with open(path) as f:
        return HTMLResponse(f.read())


@router.get("/screen/state")
async def get_state() -> Dict[str, Any]:
    """Estado del job: última corrida exitosa, símbolos pendientes/fallidos,
    cuota usada. Útil para el dashboard y para el operador."""
    path = os.path.join(_CACHE_DIR, "state.json")
    if not os.path.exists(path):
        return {
            "status": "never_run",
            "message": "El job nunca corrió. Lanzá scripts/fundamentals_screen_daily.sh "
                       "manualmente o esperá al cron de las 22:00.",
        }
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo {path}: {e}")
    return sorted(dates, reverse=True)