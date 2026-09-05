"""
Ventana del gate de 60 días + allow-list de categorías permitidas (A7).

PLAN_REMEDIO_BRECHAS_20260903.md §A7 — el `trial_registry.py` rechaza
pre-registros con fecha dentro de la ventana del gate, salvo categoría
allow-list explícita (`bugfix` / `infraestructura`), citando la Regla 1
de ONBOARDING.md ("Ningún trial de motor sin criterio pre-registrado":
el umbral, la corrección por comparaciones múltiples y el criterio de
éxito/fracaso se escriben ANTES de correr, no mirando el resultado).
Un agente que intente un trial "inocente" durante el gate choca contra
código, no contra documento.

La ventana del gate se define como:
  [GATE_START_DATE, GATE_END_DATE]
con GATE_START_DATE = 2026-09-02 (per plan §0 — arranque del contador) y
GATE_END_DATE = GATE_START_DATE + MAX_GATE_DAYS. Cuando exista
`data/clean_days.json` con racha >= 60, el caller puede sobreescribir el
end via la env var FORTRESS_GATE_END (YYYY-MM-DD). El escape total
(válido solo para emergencias declaradas) es FORTRESS_ALLOW_GATE_TRIAL=1.

Las categorías permitidas durante el gate están pinneadas por el plan:
  - "bugfix"        — corrige algo roto, no prueba una hipótesis nueva
  - "infraestructura" — tooling, observabilidad, contabilidad (lo que la
                       definición del gate explícitamente permite)

Cualquier otra categoría (incluida la ausencia) bloquea el registro.
"""
import datetime as _dt
import os
from typing import FrozenSet, Optional

# ----------------------------------------------------------------------------
# Constantes de la ventana del gate (PLAN_REMEDIO_BRECHAS_20260903 §0 + §A7)
# ----------------------------------------------------------------------------

# Arranque del contador de días limpios: 2026-09-02 (per plan §0).
GATE_START_DATE: _dt.date = _dt.date(2026, 9, 2)

# Tope absoluto: el plan dice 60 días pero permite extender hasta ~90 para
# imprevistos. Hardcodear el cap evita que un end-date ausente cuelgue el
# bloqueo para siempre.
MAX_GATE_DAYS: int = 90

# Allow-list cerrada de categorías permitidas durante el gate. Cualquier
# otra cosa (incluida la ausencia de `categoria`) bloquea el registro.
# Coherente con el plan §A7: solo bugfix/infraestructura pasan.
GATE_CATEGORY_ALLOW_LIST: FrozenSet[str] = frozenset({"bugfix", "infraestructura"})

# Escape documentado: emergencias declaradas. Mismo patrón que
# `FORTRESS_ALLOW_LOCAL_LEDGER` en trial_registry.py:350.
GATE_TRIAL_ESCAPE_ENV = "FORTRESS_ALLOW_GATE_TRIAL"

# Override del end-date desde el exterior (p.ej. cuando clean_days.json
# declare racha >= 60 y Boris quiera cerrar la ventana antes del cap).
GATE_END_OVERRIDE_ENV = "FORTRESS_GATE_END"


def _today(today: Optional[_dt.date] = None) -> _dt.date:
    return today or _dt.date.today()


def get_gate_end_date(today: Optional[_dt.date] = None) -> _dt.date:
    """Devuelve el end-date efectivo del gate.

    Prioridad:
      1. env var FORTRESS_GATE_END (YYYY-MM-DD) si parsea.
      2. GATE_START_DATE + MAX_GATE_DAYS (cap duro).

    Si el override produce una fecha ANTERIOR a GATE_START_DATE, se ignora
    silenciosamente y se usa el cap (no abrimos una ventana negativa)."""
    end_str = os.environ.get(GATE_END_OVERRIDE_ENV)
    if end_str:
        try:
            override = _dt.date.fromisoformat(end_str)
            if override >= GATE_START_DATE:
                return override
        except ValueError:
            pass  # formato inválido -> fallback al cap
    return GATE_START_DATE + _dt.timedelta(days=MAX_GATE_DAYS)


def is_within_gate_window(fecha: _dt.date, today: Optional[_dt.date] = None) -> bool:
    """True si `fecha` cae DENTRO de la ventana del gate (inclusivo en
    ambos extremos). El caller es responsable de pasar fechas válidas;
    `_parse_fecha` del trial_registry ya garantiza formato."""
    _ = _today(today)  # placeholder para futura lógica de "fecha futura"
    return GATE_START_DATE <= fecha <= get_gate_end_date()


def is_allowed_during_gate(categoria: Optional[str]) -> bool:
    """True si la categoría está en el allow-list cerrado."""
    if not categoria:
        return False
    return categoria.strip().lower() in GATE_CATEGORY_ALLOW_LIST


def escape_active() -> bool:
    """True si el operador activó el escape explícito (emergencia declarada)."""
    return bool(os.environ.get(GATE_TRIAL_ESCAPE_ENV))


def gate_window_str() -> str:
    """String humano-legible de la ventana del gate (para mensajes de error)."""
    end = get_gate_end_date()
    return f"{GATE_START_DATE.isoformat()}..{end.isoformat()}"


def assert_allowed_during_gate(
    fecha: _dt.date, categoria: Optional[str], trial_id: str = "",
) -> None:
    """Lanza `PermissionError` si el trial cae dentro de la ventana del gate
    sin categoría allow-list. El caller (trial_registry) lo convierte a
    `TrialRegistryError` con el mensaje final.

    Importante: este helper NO hace la lógica del ledger — solo evalúa
    si la combinación (fecha, categoria) está permitida. La validación de
    forma (campos requeridos, duplicados, etc.) sigue en trial_registry.
    """
    if escape_active():
        return  # escape explícito: respetar al operador
    if not is_within_gate_window(fecha):
        return  # fuera de la ventana: no aplica la restricción
    # Dentro de la ventana. La categoría debe estar en el allow-list.
    if is_allowed_during_gate(categoria):
        return
    # Bloqueo.
    from app.core.trial_registry import TrialRegistryError  # import local: evita ciclo
    categoria_repr = repr(categoria) if categoria is not None else "<ausente>"
    raise TrialRegistryError(
        f"GATE_BLOQUEADO: el trial {trial_id!r} cae dentro de la ventana del gate "
        f"({gate_window_str()}) con categoria={categoria_repr}, fuera del allow-list "
        f"({sorted(GATE_CATEGORY_ALLOW_LIST)}). "
        f"Regla 1 de ONBOARDING.md: 'Ningún trial de motor sin criterio "
        f"pre-registrado' (umbral, corrección y criterio de éxito se escriben ANTES "
        f"de correr, no mirando el resultado) — durante el gate solo se permite "
        f"registrar trials de bugfix/infraestructura (categoria explicita en la "
        f"entrada). Trials de hipótesis nuevas, producto o re_test deben esperar al "
        f"post-gate. Para emergencias declaradas: export {GATE_TRIAL_ESCAPE_ENV}=1."
    )
