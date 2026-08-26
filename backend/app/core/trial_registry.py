"""M6 — Ledger de trials (ORDENES_MODULOS.md, M6).

PROBLEMA: este proyecto corrige por comparaciones multiples (Bonferroni) y lleva la
cuenta de trials A MANO. El propio ROADMAP.md admite la ambiguedad: "Confirmar el
n_trials exacto contra el historial de artefactos antes de fijarlo - no asumir el
numero". Con mas hipotesis por probar, el conteo a mano se rompe y se empieza a
encontrar señal por pura suerte estadistica.

Este modulo es el registro maquina-legible de trials: una entrada por trial
pre-registrado, con su familia, su umbral y su veredicto. De ahi salen los numeros
que la disciplina del proyecto exige fijar ANTES de correr (ONBOARDING.md regla 1).

CONTRATO DE SALIDA (una entrada por trial):
    {"id": str, "fecha": "YYYY-MM-DD", "familia": str, "hipotesis": str,
     "n_trials_consumidos": int, "umbral_aplicado": str, "veredicto": "CUMPLE|NO_CUMPLE",
     "artefacto": "ruta/al/archivo.txt", "seccion_doc": "§21.1"}
    + condicional: familia=="re_test" exige ademas {"re_test_de": str} — el id de la
      entrada ya registrada que este re-test re-confirma (garantia H3.1/Brecha re_test,
      aprobada por Boris 2026-08-26).

REGLAS:
- Python 3.9 real. Nada de sintaxis 3.10+ (nada de `X | Y` en type hints).
- Un registro corrupto o incompleto falla RUIDOSAMENTE, no en silencio: la disciplina
  del proyecto exige que un conteo equivocado sea un error, no un default.
- Un registro INTERNAMENTE INCONSISTENTE tambien falla ruidosamente (garantias anti-
  evasion Bonferroni de la familia re_test):
  * n_trials_consumidos=0 SOLO es legal en la familia "re_test" (el cero es una
    exencion tipificada, no un valor libre).
  * toda entrada "re_test" cita su objetivo con "re_test_de": id EXISTENTE y ANTERIOR
    en el registro, con veredicto NO_CUMPLE y familia de investigacion (nunca
    "producto" ni otro "re_test" — no hay cadenas de segunda derivacion).
  * tope de MAX_RETESTS_PER_TARGET re-tests por objetivo: la tercera tirada del mismo
    dado exige decision explicita (subir la constante en el codigo, visible en diff).
- El registro es la fuente de verdad del presupuesto por familia. `consumed_budget`
  y `current_threshold` se derivan de las entradas, nunca se hardcodean.
"""
import json
import os
from typing import Dict, List, Optional

# Umbral base declarado por la disciplina del proyecto: DSR OOS >= 0.90 (criterio
# pre-registrado de todos los trials de motor, p.ej. PLAN_MEJORA_MATEMATICA §0.6.1).
BASE_THRESHOLD = 0.90

# Maximo de entradas re_test que pueden citar al MISMO objetivo. Historial actual:
# maximo 1 por objetivo. Subirlo es una decision de producto, no un dato.
MAX_RETESTS_PER_TARGET = 2

# Familias de investigacion sobre las que un re_test puede apoyarse (los objetivos
# legitimos de un re-test son hallazgos refutados de investigacion). "producto" y
# "re_test" quedan fuera: sin re-test de decisiones de producto y sin cadenas.
RESEARCH_FAMILIES = (
    "motor_signal",
    "signal_diagnosis",
    "risk",
    "backtest_costos",
)

# Familias conocidas del proyecto (del historial). Una familia nueva se registra
# con register_trial() sin tocar esta lista: es referencia, no whitelist.
KNOWN_FAMILIES = (
    "motor_signal",      # trials de motor: inyeccion de una variable/score y medicion DSR OOS
    "signal_diagnosis",  # diagnosticos de señal: rank IC intra-dia, RMT, horizontes, sub-periodos
    "risk",              # gestion de riesgo: regimen vs volatilidad, EVT, stops
    "backtest_costos",   # backtests con costos reales de un hallazgo (gap, C6)
    "producto",          # decisiones de producto/arquitectura con evidencia (rama W2)
    "re_test",           # re-tests de variables ya refutadas (Fase 0.6) — NO consumen slot nuevo
)


class TrialRegistryError(Exception):
    """Error de integridad del registro. Se lanza en lugar de callar un dato roto."""


def _default_path() -> str:
    """Ruta por defecto del registro: backend/data/trial_registry.json (gitignored)."""
    here = os.path.dirname(os.path.abspath(__file__))  # backend/app/core/
    return os.path.normpath(os.path.join(here, "..", "..", "data", "trial_registry.json"))


def _load_raw(path: str) -> List[dict]:
    """Lee el JSON y devuelve la lista de entradas, validando la forma general."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise TrialRegistryError(f"registro corrupto (JSON invalido): {path} — {exc}") from exc
    if not isinstance(data, list):
        raise TrialRegistryError(f"registro corrupto: raiz debe ser una lista, no {type(data).__name__}")
    for entry in data:
        _validate_entry(entry)
    _validate_cross_entries(data)
    return data


def _validate_entry(entry: dict) -> None:
    """Valida que una entrada tenga todas las claves y tipos del contrato.

    Validez POR ENTRADA (sin mirar el resto del registro). Los vinculos cruzados
    de la familia re_test se validan aparte en _validate_cross_entries().
    """
    if not isinstance(entry, dict):
        raise TrialRegistryError(f"entrada invalida: no es un dict: {entry!r}")
    required = ("id", "fecha", "familia", "hipotesis", "n_trials_consumidos",
                "umbral_aplicado", "veredicto", "artefacto", "seccion_doc")
    missing = [k for k in required if k not in entry]
    if missing:
        raise TrialRegistryError(f"entrada incompleta, faltan: {missing} — {entry!r}")
    if entry["veredicto"] not in ("CUMPLE", "NO_CUMPLE"):
        raise TrialRegistryError(f"veredicto invalido: {entry['veredicto']!r} — {entry!r}")
    if not isinstance(entry["n_trials_consumidos"], int) or entry["n_trials_consumidos"] < 0:
        raise TrialRegistryError(f"n_trials_consumidos invalido: {entry['n_trials_consumidos']!r} — {entry!r}")
    # Garantia 3 (cierra F2): el cero es una EXENCION tipificada de los re-tests
    # (Fase 0.6), no un valor libre. Sin esta regla, evadir Bonferroni no requiere
    # ni la etiqueta re_test: basta escribir cero en cualquier familia.
    if entry["n_trials_consumidos"] == 0 and entry["familia"] != "re_test":
        raise TrialRegistryError(
            f"n_trials_consumidos=0 solo es legal en familia 're_test' "
            f"(exencion Fase 0.6), no en '{entry['familia']}' — {entry!r}"
        )
    # Garantia 1a: una entrada re_test SIN objetivo declarado no pasa — la exencion
    # exige anclaje a un hallazgo ya refutado.
    if entry["familia"] == "re_test":
        target = entry.get("re_test_de")
        if not isinstance(target, str) or not target.strip():
            raise TrialRegistryError(
                f"entrada 're_test' sin 're_test_de' valido (id del hallazgo "
                f"NO_CUMPLE que re-confirma) — {entry!r}"
            )


def _validate_cross_entries(entries: List[dict]) -> None:
    """Invariante cruzado del registro completo sobre los vinculos re_test.

    Falla ruidosamente si:
    - un re_test cita un id que no existe O que aparece DESPUES en el registro
      (sin referencias hacia adelante: el objetivo debe estar ya registrado);
    - el objetivo no tiene veredicto NO_CUMPLE (la exencion existe para
      re-confirmar REFUTACIONES barato — re-testear un CUMPLE es investigacion
      nueva y paga slot en su propia familia);
    - el objetivo no es de familia de investigacion (nunca 'producto', nunca otro
      're_test' — prohibidas las cadenas de segunda derivacion sin presupuesto);
    - se supera MAX_RETESTS_PER_TARGET re-tests contra el mismo objetivo.
    """
    ids_antes: Dict[str, int] = {}
    conteo_por_objetivo: Dict[str, int] = {}
    for idx, entry in enumerate(entries):
        if entry["familia"] == "re_test":
            target_id = entry["re_test_de"]
            if target_id == entry["id"]:
                raise TrialRegistryError(
                    f"re_test '{entry['id']}' no puede citarse a si mismo como objetivo"
                )
            if target_id not in ids_antes:
                raise TrialRegistryError(
                    f"re_test '{entry['id']}' cita re_test_de='{target_id}' inexistente o "
                    f"posterior en el registro — el objetivo debe ser una entrada ya registrada"
                )
            target = entries[ids_antes[target_id]]
            if target["veredicto"] != "NO_CUMPLE":
                raise TrialRegistryError(
                    f"re_test '{entry['id']}' apunta a '{target_id}' con veredicto "
                    f"{target['veredicto']!r} — solo se permite re-test de hallazgos NO_CUMPLE"
                )
            if target["familia"] not in RESEARCH_FAMILIES:
                raise TrialRegistryError(
                    f"re_test '{entry['id']}' apunta a '{target_id}' de familia "
                    f"'{target['familia']}' — objetivo debe ser de familia de "
                    f"investigación {RESEARCH_FAMILIES} (no 'producto', no cadenas re_test)"
                )
            conteo_por_objetivo[target_id] = conteo_por_objetivo.get(target_id, 0) + 1
            if conteo_por_objetivo[target_id] > MAX_RETESTS_PER_TARGET:
                raise TrialRegistryError(
                    f"tope MAX_RETESTS_PER_TARGET={MAX_RETESTS_PER_TARGET} excedido para "
                    f"'{target_id}' (intento #{conteo_por_objetivo[target_id]} desde "
                    f"'{entry['id']}') — subir el tope es una decisión explícita de producto"
                )
        # TODO id (de cualquier familia) queda disponible como objetivo para las
        # entradas SIGUIENTES — pero un re_test solo es objetivo legitimo si pasa
        # el filtro RESEARCH_FAMILIES del consumidor, así que las cadenas fallan
        # por familia, no por existencia.
        ids_antes[entry["id"]] = idx


def _write(path: str, entries: List[dict]) -> None:
    """Escribe el registro de forma atomica (temp + rename) para no dejar JSON a medias."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def register_trial(entry: dict, path: Optional[str] = None) -> None:
    """Agrega una entrada al registro. Lanza TrialRegistryError si el id ya existe
    o si la entrada (o el registro resultante) viola las garantias de integridad:
    validez por entrada + vinculos cruzados re_test, ANTES de escribir en disco."""
    path = path or _default_path()
    entries = _load_raw(path)
    if any(e["id"] == entry["id"] for e in entries):
        raise TrialRegistryError(f"id duplicado: {entry['id']}")
    _validate_entry(entry)
    entries.append(entry)
    _validate_cross_entries(entries)
    _write(path, entries)


def trials_by_family(path: Optional[str] = None) -> Dict[str, List[dict]]:
    """Devuelve las entradas agrupadas por familia (orden de aparicion)."""
    grouped: Dict[str, List[dict]] = {}
    for entry in _load_raw(path or _default_path()):
        grouped.setdefault(entry["familia"], []).append(entry)
    return grouped


def consumed_budget(familia: str, path: Optional[str] = None) -> int:
    """Cuantos trials de la familia ya se consumieron (suma de n_trials_consumidos)."""
    return sum(
        e["n_trials_consumidos"]
        for e in _load_raw(path or _default_path())
        if e["familia"] == familia
    )


def current_threshold(familia: str, path: Optional[str] = None) -> float:
    """Umbral Bonferroni vigente de la familia, dado lo ya consumido.

    Correccion estandar del proyecto (ONBOARDING.md regla 1): umbral = 1 - (1-BASE)/n
    con n = trials consumidos + 1 (el trial nuevo). Con un solo trial queda 0.90 —
    el criterio de siempre — y se endurece a medida que sube el consumo.
    """
    n = consumed_budget(familia, path) + 1
    return 1.0 - (1.0 - BASE_THRESHOLD) / n


def all_trials(path: Optional[str] = None) -> List[dict]:
    """Todas las entradas en orden de aparicion."""
    return _load_raw(path or _default_path())
