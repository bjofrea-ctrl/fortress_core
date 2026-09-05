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
     "n_trials_consumidos": int, "umbral_aplicado": str,
     "veredicto": "CUMPLE|NO_CUMPLE",          # solo si status != RESERVED
     "artefacto": "ruta/al/archivo.txt",       # solo si status != RESERVED
     "seccion_doc": "§21.1",
     "status": "RESERVED|COMPLETED|EXPIRED"}   # Track A, 2026-08-26
    + condicional: familia=="re_test" exige ademas {"re_test_de": str} — el id de la
      entrada ya registrada que este re-test re-confirma (garantia H3.1/Brecha re_test,
      aprobada por Boris 2026-08-26).

ESTADOS DE RESERVA (Track A, aprobado por Boris 2026-08-26):
- RESERVED: Boris aprobo el pre-registro. El slot Bonferroni YA SE CUENTA desde
  aca (no al completar) para que dos agentes no doble-gasten la misma familia.
  No tiene veredicto ni artefacto todavia.
- COMPLETED: el trial corrio y tiene veredicto CUMPLE|NO_CUMPLE + artefacto.
- EXPIRED: se reservo y no corrio dentro de RESERVATION_TTL_DAYS dias
  (default 14). El slot se LIBERA (no cuenta presupuesto).
- Backward-compatible: entradas viejas sin campo status se tratan como
  COMPLETED (tienen veredicto: corrieron) — normalizado al leer.
- consumed_budget() cuenta RESERVED(frescas) + COMPLETED. Una reserva expirada
  (efectiva o materializada con expire_stale_reservations()) libera su slot.
- complete_trial() pasa RESERVED->COMPLETED con el veredicto real; falla ruidoso
  si la entrada no esta RESERVED (ni completar algo EXPIRADO ni doble-completar).
- Las reservas NO existen para familia "re_test" (exencion sin slot nuevo:
  nada que reservar).

RECONCILIACION GIT ANTES DE ESCRIBIR (Track A):
Todo escritor (register_trial, register_trial_reservation, complete_trial,
expire_stale_reservations) verifica, antes de tocar disco, que el ledger local
no esta desincronizado del resto del equipo (lección del drift 25-vs-26 del
2026-08-26 entre worktrees):
1. Si el archivo tiene cambios SIN commitear (git status) -> TrialRegistryError
   pidiendo commitear/pull primero: cada escritura deja el ledger commiteado
   o no arranca.
2. Si el blob del archivo en HEAD difiere del blob en `origin/main` (referencia
   CANONICA fija, NO el @{u} del branch — los worktrees de este proyecto no
   configuran tracking, @{u} fallaria en silencio) -> TrialRegistryError
   pidiendo sincronizar.
Ambos chequeos son best-effort: fuera de un repo git (ej. tmp_path en tests)
o si git no esta disponible, no bloquean. Env FORTRESS_ALLOW_LOCAL_LEDGER=1
los saltea (escape documentado, solo para recuperacion manual).

DISCIPLINA EJECUTABLE (Track A, alcance minimo hoy):
validate_umbral_aplicado(preregistro, umbral_aplicado) extrae mecanicamente la
linea "umbral_aplicado:" (o fila de tabla markdown) del pre-registro y compara
normalizada contra lo que se va a registrar. El pre-registro declara el
criterio UNA vez; el ledger no acepta una copia distinta. Un DSL completo de
criterios ejecutables queda documentado como diseño pendiente (PLAN nivel-dios).

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
import re
import subprocess
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

# Umbral base declarado por la disciplina del proyecto: DSR OOS >= 0.90 (criterio
# pre-registrado de todos los trials de motor, p.ej. PLAN_MEJORA_MATEMATICA §0.6.1).
BASE_THRESHOLD = 0.90

# Maximo de entradas re_test que pueden citar al MISMO objetivo. Historial actual:
# maximo 1 por objetivo. Subirlo es una decision de producto, no un dato.
MAX_RETESTS_PER_TARGET = 2

# Track A (2026-08-26): estados del ciclo de vida de una entrada.
STATUS_RESERVED = "RESERVED"    # Boris aprobo el pre-registro; slot contado, trial sin correr
STATUS_COMPLETED = "COMPLETED"  # corrio; veredicto + artefacto presentes
STATUS_EXPIRED = "EXPIRED"      # reserva vencida sin correr; slot liberado
STATUS_DEFAULT = STATUS_COMPLETED  # backward-compat: entradas viejas sin status

# Dias que vive una reserva sin correr antes de considerarse expirada. Pasado el
# plazo el slot se libera (deja de contar en consumed_budget). Default acordado
# con Boris en Track A: 14 dias corridos desde la fecha de la reserva.
RESERVATION_TTL_DAYS = 14

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
    """Lee el JSON y devuelve la lista de entradas, validando la forma general.

    Track A: las entradas sin campo status (previas a los estados de reserva)
    se normalizan a COMPLETED — tienen veredicto, corrieron. La normalizacion
    se hace sobre copia y es idempotente; el archivo solo se materializa
    normalizado en la proxima escritura.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise TrialRegistryError(f"registro corrupto (JSON invalido): {path} — {exc}") from exc
    if not isinstance(data, list):
        raise TrialRegistryError(f"registro corrupto: raiz debe ser una lista, no {type(data).__name__}")
    normalized = []
    for entry in data:
        entry = dict(entry)
        entry.setdefault("status", STATUS_DEFAULT)
        normalized.append(entry)
    for entry in normalized:
        _validate_entry(entry)
    _validate_cross_entries(normalized)
    return normalized


def _parse_fecha(value) -> date:
    """Convierte 'YYYY-MM-DD' a date. Falla ruidoso ante cualquier otra cosa."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise TrialRegistryError(
            f"fecha invalida: {value!r} — formato esperado YYYY-MM-DD"
        ) from exc


def effective_status(entry: dict, today: Optional[date] = None) -> str:
    """Estado EFECTIVO de una entrada (Track A).

    Una entrada RESERVED cuya fecha de reserva es anterior a
    RESERVATION_TTL_DAYS dias es EXPIRADA aunque el campo diga RESERVED:
    el conteo de presupuesto la trata como expirada sin necesidad de
    reescribir el archivo en cada lectura. La materializacion fisica del
    estado EXPIRED queda a cargo de expire_stale_reservations().
    """
    stored = entry.get("status", STATUS_DEFAULT)
    if stored not in (STATUS_RESERVED, STATUS_COMPLETED, STATUS_EXPIRED):
        raise TrialRegistryError(
            f"status desconocido: {stored!r} — valido: "
            f"{(STATUS_RESERVED, STATUS_COMPLETED, STATUS_EXPIRED)}"
        )
    if stored == STATUS_RESERVED:
        ref = today or date.today()
        if _parse_fecha(entry["fecha"]) + timedelta(days=RESERVATION_TTL_DAYS) < ref:
            return STATUS_EXPIRED
    return stored


def _validate_entry(entry: dict, today: Optional[date] = None) -> None:
    """Valida que una entrada tenga todas las claves y tipos del contrato.

    Validez POR ENTRADA (sin mirar el resto del registro). Los vinculos cruzados
    de la familia re_test se validan aparte en _validate_cross_entries().
    Track A: la presencia de veredicto/artefacto depende del status —
    una reserva abierta (RESERVED) o vencida (EXPIRED) NO los tiene.
    """
    if not isinstance(entry, dict):
        raise TrialRegistryError(f"entrada invalida: no es un dict: {entry!r}")
    required = ("id", "fecha", "familia", "hipotesis", "n_trials_consumidos",
                "umbral_aplicado", "seccion_doc")
    missing = [k for k in required if k not in entry]
    if missing:
        raise TrialRegistryError(f"entrada incompleta, faltan: {missing} — {entry!r}")
    status = entry.get("status", STATUS_DEFAULT)
    if status not in (STATUS_RESERVED, STATUS_COMPLETED, STATUS_EXPIRED):
        raise TrialRegistryError(f"status invalido: {status!r}")
    _parse_fecha(entry["fecha"])  # falla ruidoso si no es YYYY-MM-DD
    if status in (STATUS_RESERVED, STATUS_EXPIRED):
        for campo_prohibido in ("veredicto", "artefacto"):
            if campo_prohibido in entry:
                raise TrialRegistryError(
                    f"entrada {status} no puede llevar '{campo_prohibido}' "
                    f"(el trial todavia no corrio) — {entry!r}"
                )
    else:  # COMPLETED: el veredicto y el artefacto NO son opcionales
        if entry["veredicto"] not in ("CUMPLE", "NO_CUMPLE"):
            raise TrialRegistryError(
                f"veredicto invalido para entrada COMPLETED: {entry['veredicto']!r} — {entry!r}"
            )
        if not str(entry.get("artefacto", "")).strip():
            raise TrialRegistryError(
                f"entrada COMPLETED sin artefacto (la evidencia no es opcional) — {entry!r}"
            )
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
    # Track A: una reserva consume slot Bonferroni por definicion. Sin slot nuevo
    # (re_test) no hay nada que reservar, y n=1 es el piso de una reserva real.
    if status == STATUS_RESERVED:
        if entry["familia"] == "re_test":
            raise TrialRegistryError(
                "reserva ilegal en familia 're_test': la exencion no reserva slot "
                "(no hay presupuesto que bloquear)"
            )
        if entry["n_trials_consumidos"] < 1:
            raise TrialRegistryError(
                f"reserva con n_trials_consumidos={entry['n_trials_consumidos']} — "
                "una reserva ES un slot consumido: n>=1 obligatorio"
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


def _run_git(args: List[str], cwd: str):
    """Corre un subcomando git; None si git no esta disponible/rompio por entorno."""
    try:
        return subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_reconciliation_error(path: str) -> None:
    """Track A: falla ruidoso si el ledger local esta desincronizado del equipo.

    Dos chequeos, ambos best-effort (fuera de un repo git no bloquean):
    1. cambios SIN commitear en el archivo -> commitear/pusar primero;
    2. el blob DEL ARCHIVO difiere del de `origin/main` — referencia CANÓNICA
       fija. NO usa @{u} (upstream del branch): los worktrees de este proyecto
       no configuran tracking, asi que @{u} falla y el chequeo muere en
       silencio — exactamente el escenario del drift 25-vs-26. Solo depende de
       que exista el remote 'origin', que si existe en todos los worktrees.
    Escape manual documentado: FORTRESS_ALLOW_LOCAL_LEDGER=1.
    """
    if os.environ.get("FORTRESS_ALLOW_LOCAL_LEDGER"):
        return
    target = os.path.abspath(path)
    cwd = os.path.dirname(target) or "."
    top = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if top is None or top.returncode != 0:
        return  # tmp_path en tests, o git ausente: sin chequeo posible
    rel = os.path.relpath(target, top.stdout.strip())
    st = _run_git(["status", "--porcelain", "--", rel], cwd)
    if st is not None and st.returncode == 0 and st.stdout.strip():
        raise TrialRegistryError(
            f"LEDGER DESINCRONIZADO: '{rel}' tiene cambios sin commitear "
            f"({st.stdout.strip()!r}). Cada escritura del ledger arranca de un "
            "estado commiteado: commit/pull antes de registrar."
        )
    # 2. referencia canónica: origin/main (no depende de upstream del branch)
    _run_git(["fetch", "-q", "origin"], cwd)  # best-effort: offline no bloquea
    head_blob = _run_git(["rev-parse", f"HEAD:{rel}"], cwd)
    main_blob = _run_git(["rev-parse", f"origin/main:{rel}"], cwd)
    if (head_blob is None or main_blob is None
            or head_blob.returncode != 0 or main_blob.returncode != 0):
        return  # archivo todavia no trackeado en origin/main, o sin remote origin
    if head_blob.stdout.strip() != main_blob.stdout.strip():
        raise TrialRegistryError(
            f"LEDGER DESINCRONIZADO: '{rel}' difiere entre HEAD y origin/main "
            "(commits locales sin push, u origin/main con entradas nuevas sin pull). "
            "Sincronizar antes de escribir para no pisar reservas/completados "
            "de otros agentes."
        )


def _attach_cache_snapshot_if_absent(entry: dict) -> dict:
    """A0: congela el hash del cache en el pre-registro si no viene ya congelado.

    La especificacion (PLAN_REMEDIO §A0 parte 3 + COMPARACION §10.2 punto 3)
    pide que TODO pre-registro registre el hash del cache que consume (o copia
    congelada). Si la entrada ya trae 'cache_manifest_sha256' se respeta. Falla
    blando: sin pandas/pyarrow (tests aislados del ledger) registra sin
    snapshot — el ledger no puede dejar de funcionar por el cache.
    """
    if "cache_manifest_sha256" in entry:
        return entry
    try:
        from app.core.cache_integrity import attach_cache_snapshot

        here = os.path.dirname(os.path.abspath(__file__))  # backend/app/core/
        backend_root = os.path.normpath(os.path.join(here, "..", ".."))
        return attach_cache_snapshot(entry, os.path.join(backend_root, "data", "cache"))
    except Exception:  # noqa: BLE001 — fail-blando documentado arriba
        return entry


def register_trial(entry: dict, path: Optional[str] = None, check_git: bool = True) -> None:
    """Agrega una entrada al registro. Lanza TrialRegistryError si el id ya existe
    o si la entrada (o el registro resultante) viola las garantias de integridad:
    validez por entrada + vinculos cruzados re_test, ANTES de escribir en disco.

    Track A: entradas sin status explicito se registran COMPLETED (registro
    post-hoc con veredicto). Para reservar un slot ANTES de correr el trial,
    usar register_trial_reservation().

    A0 (cache integrity): si la entrada no trae snapshot del cache, se adjunta
    automaticamente (attach_cache_snapshot: hash SHA-256 del manifiesto de los
    parquets del universo que el trial consume — defensa contra el reajuste
    retroactivo de yfinance, COMPARACION_FUENTES_DATOS §10.2 punto 3). Si la
    entrada ya trae 'cache_manifest_sha256' se respeta (el caller ya congelo
    su propio snapshot). Falla blando: sin el modulo de cache disponible
    (p.ej. entorno de test sin pandas), registra sin snapshot.

    A7 (PLAN_REMEDIO_BRECHAS_20260903 §A7): si la fecha cae dentro de la
    ventana del gate, la entrada debe llevar `categoria` allow-list
    (`bugfix` / `infraestructura`). El escape explicito es la env var
    `FORTRESS_ALLOW_GATE_TRIAL=1` (emergencias declaradas).
    """
    path = path or _default_path()
    entry = dict(entry)
    entry.setdefault("status", STATUS_COMPLETED)
    entry = _attach_cache_snapshot_if_absent(entry)
    if check_git:
        _git_reconciliation_error(path)
    # A7: gate window check ANTES de validar forma — un trial que no pasa
    # el gate no merece ni un check de entry. Skip el helper si el caller
    # no quiere el check (passa `check_git=False`... no, ese flag es para
    # git; para el gate usamos un flag separado si hace falta, pero por
    # ahora la regla es uniforme: TODA escritura respeta el gate).
    _gate_window_check(entry)
    entries = _load_raw(path)
    if any(e["id"] == entry["id"] for e in entries):
        raise TrialRegistryError(f"id duplicado: {entry['id']}")
    _validate_entry(entry)
    entries.append(entry)
    _validate_cross_entries(entries)
    _write(path, entries)


def register_trial_reservation(
    entry: dict, path: Optional[str] = None,
    preregistro: Optional[str] = None, check_git: bool = True,
) -> None:
    """Track A — crea una entrada RESERVED: Boris aprobo el pre-registro.

    El slot Bonferroni se cuenta DESDE ACA (no al completar): dos agentes no
    pueden doble-gastar la misma familia aunque corran en paralelo. La entrada
    no lleva veredicto ni artefacto (el trial todavia no corrio).

    preregistro (opcional pero recomendado): texto del pre-registro markdown
    aprobado (o ruta a un archivo .md). Se extrae mecanicamente su
    'umbral_aplicado' y se compara contra el de la entrada — si difieren, NO
    se registra (disciplina ejecutable minima).

    A7: misma regla que `register_trial` — la fecha del trial no puede caer
    dentro de la ventana del gate sin categoria allow-list.
    """
    path = path or _default_path()
    entry = dict(entry)
    if "status" in entry and entry["status"] != STATUS_RESERVED:
        raise TrialRegistryError(
            f"register_trial_reservation exige status RESERVED (o ausente), recibio "
            f"{entry['status']!r} — para un trial ya corrido usar register_trial()"
        )
    entry["status"] = STATUS_RESERVED
    entry = _attach_cache_snapshot_if_absent(entry)
    if preregistro is not None:
        contenido = preregistro
        if "\n" not in preregistro and os.path.isfile(preregistro):
            with open(preregistro, "r", encoding="utf-8") as fh:
                contenido = fh.read()
        validate_umbral_aplicado(contenido, str(entry["umbral_aplicado"]))
    if check_git:
        _git_reconciliation_error(path)
    # A7: gate window check (idéntico al de register_trial).
    _gate_window_check(entry)
    entries = _load_raw(path)
    if any(e["id"] == entry["id"] for e in entries):
        raise TrialRegistryError(f"id duplicado: {entry['id']}")
    _validate_entry(entry)
    entries.append(entry)
    _validate_cross_entries(entries)
    _write(path, entries)


def _gate_window_check(entry: dict) -> None:
    """A7: helper que invoca el check de la ventana del gate sobre la entrada.

    Lanza `TrialRegistryError` con mensaje citando la Regla 1 de
    ONBOARDING.md si la fecha cae dentro de la ventana y la categoria no
    está en el allow-list (o el escape FORTRESS_ALLOW_GATE_TRIAL está
    apagado)."""
    # Import local: evita ciclo de imports (gate_window importa trial_registry).
    from app.core.gate_window import assert_allowed_during_gate
    fecha = _parse_fecha(entry["fecha"])
    categoria = entry.get("categoria")
    trial_id = str(entry.get("id", ""))
    assert_allowed_during_gate(fecha, categoria, trial_id=trial_id)


def complete_trial(
    trial_id: str, veredicto: str, artefacto: str,
    path: Optional[str] = None, check_git: bool = True,
) -> dict:
    """Track A — pasa una reserva RESERVED a COMPLETED con el veredicto real.

    Falla ruidoso si: el id no existe; la entrada no esta efectivamente
    RESERVED (ya completa, o reserva expirada — una expirada libero su slot,
    completarla atras contaria el mismo intento dos veces); o el veredicto
    no es CUMPLE|NO_CUMPLE. Devuelve la entrada completada.
    """
    path = path or _default_path()
    if veredicto not in ("CUMPLE", "NO_CUMPLE"):
        raise TrialRegistryError(f"veredicto invalido: {veredicto!r} — solo CUMPLE|NO_CUMPLE")
    if not str(artefacto).strip():
        raise TrialRegistryError("artefacto vacio — sin evidencia no hay veredicto")
    if check_git:
        _git_reconciliation_error(path)
    entries = _load_raw(path)
    encontradas = [e for e in entries if e["id"] == trial_id]
    if not encontradas:
        raise TrialRegistryError(f"id inexistente: {trial_id} — no se puede completar")
    e = encontradas[0]
    stored = e.get("status", STATUS_DEFAULT)
    eff = effective_status(e)
    if eff != STATUS_RESERVED:
        detalle = {
            STATUS_COMPLETED: "el trial ya fue completado (no hay doble veredicto)",
            STATUS_EXPIRED: (
                f"la reserva expiro (TTL {RESERVATION_TTL_DAYS} dias) y su slot "
                "fue liberado — reservar de nuevo con un slot fresco"
            ),
        }.get(eff, "estado incompatible")
        raise TrialRegistryError(
            f"'{trial_id}' esta en estado {stored!r} (efectivo: {eff!r}): {detalle}"
        )
    e["veredicto"] = veredicto
    e["artefacto"] = artefacto
    e["status"] = STATUS_COMPLETED
    e["fecha_completado"] = date.today().isoformat()
    _validate_entry(e)
    _validate_cross_entries(entries)
    _write(path, entries)
    return e


def expire_stale_reservations(
    path: Optional[str] = None, check_git: bool = True, today: Optional[date] = None,
) -> int:
    """Track A — materializa en disco las RESERVED vencidas como EXPIRED.

    La lectura (consumed_budget/current_threshold) ya las trata como expiradas
    via effective_status(); esto deja el estado fisico consistente.
    Devuelve cuantas reservas materializo (0 si ninguna)."""
    path = path or _default_path()
    ref = today or date.today()
    if check_git:
        _git_reconciliation_error(path)
    entries = _load_raw(path)
    vencidas = 0
    for e in entries:
        if e.get("status", STATUS_DEFAULT) == STATUS_RESERVED \
                and effective_status(e, today=ref) == STATUS_EXPIRED:
            e["status"] = STATUS_EXPIRED
            e["fecha_expiracion"] = ref.isoformat()
            vencidas += 1
            _validate_entry(e)
    if vencidas:
        _validate_cross_entries(entries)
        _write(path, entries)
    return vencidas


# ---------- Track A: disciplina ejecutable minima ----------
_UMBRAL_LINE_RE = re.compile(r"umbral[\s_-]*aplicado", re.IGNORECASE)


def _clean_umbral_cell(raw: str) -> str:
    value = raw.strip().strip("`").strip('"').strip("'").strip("*").strip()
    return value.rstrip(".").strip()


def extract_umbral_aplicado(preregistro: str) -> str:
    """Extrae mecanicamente el umbral_aplicado declarado en un pre-registro.

    Acepta las dos formas que ya usa el proyecto:
      - linea clave-valor: 'umbral_aplicado: "..."' (tras ':' todo es valor);
      - fila de tabla markdown: | umbral_aplicado (registro) | <valor> |
        (valor = celda siguiente a la que contiene el label).
    Lanza TrialRegistryError si ninguna linea lo declara: un pre-registro sin
    criterio extraible no se puede verificar contra el registro.
    """
    for line in preregistro.splitlines():
        match = _UMBRAL_LINE_RE.search(line)
        if not match:
            continue
        if ":" in line:
            candidato = line.split(":", 1)[1]
        elif line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            idx = next((i for i, c in enumerate(cells) if _UMBRAL_LINE_RE.search(c)), None)
            if idx is None or idx + 1 >= len(cells):
                continue
            candidato = cells[idx + 1]
        else:
            candidato = line[match.end():]
        candidato = _clean_umbral_cell(candidato)
        if candidato:
            return candidato
    raise TrialRegistryError(
        "el pre-registro no declara un umbral_aplicado extrai­ble "
        "(seccion criterio de exito): no se puede verificar lo registrado "
        "contra lo pre-registrado"
    )


def _normalize_umbral_text(value: str) -> str:
    lowered = value.lower().replace("`", "").replace('"', "").replace("'", "")
    return re.sub(r"\s+", " ", lowered).strip().rstrip(".")


def validate_umbral_aplicado(preregistro: str, umbral_aplicado: str) -> str:
    """Chequea que lo que se va a registrar coincida mecanicamente con el
    pre-registro (comparacion normalizada). Devuelve el valor extrai­do."""
    declarado = extract_umbral_aplicado(preregistro)
    if _normalize_umbral_text(declarado) != _normalize_umbral_text(umbral_aplicado):
        raise TrialRegistryError(
            "DISCIPLINA EJECUTABLE VIOLADA: el umbral_aplicado a registrar no "
            "coincide con el pre-registro.\n"
            f"  pre-registrado: {declarado!r}\n"
            f"  a registrar:    {umbral_aplicado!r}\n"
            "Corregir la entrada O el documento (documento antes de correr => "
            "nuevo pre-registro, no edicion retroactiva)."
        )
    return declarado


def trials_by_family(path: Optional[str] = None) -> Dict[str, List[dict]]:
    """Devuelve las entradas agrupadas por familia (orden de aparicion)."""
    grouped: Dict[str, List[dict]] = {}
    for entry in _load_raw(path or _default_path()):
        grouped.setdefault(entry["familia"], []).append(entry)
    return grouped


def consumed_budget(familia: str, path: Optional[str] = None,
                    today: Optional[date] = None) -> int:
    """Cuantos slots de la familia ya se consumieron (Track A).

    Cuentan RESERVED vigentes (el slot se ocupa al reservar, no al correr)
    y COMPLETED. NO cuentan las expiradas (efectivas o materializadas):
    el slot de una reserva vencida se libera. Entradas legacy sin status
    se normalizaron a COMPLETED al leer.
    """
    return sum(
        e["n_trials_consumidos"]
        for e in _load_raw(path or _default_path())
        if e["familia"] == familia
        and effective_status(e, today=today) in (STATUS_RESERVED, STATUS_COMPLETED)
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


def verify_trial_cache_snapshot(trial_id: str, path: Optional[str] = None,
                                cache_dir: Optional[str] = None) -> dict:
    """A0: verifica si el cache ACTUAL sigue siendo el del pre-registro.

    Recalcula el manifiesto del cache y lo compara contra el sha256 guardado
    en la entrada del trial. Devuelve:
      {"trial_id", "match": bool, "checked": bool}
    checked=False significa que la entrada no tiene snapshot (previa a A0)
    o que el cache no esta disponible — sin veredicto de integridad.
    """
    entries = _load_raw(path or _default_path())
    found = [e for e in entries if e["id"] == trial_id]
    if not found:
        raise TrialRegistryError(f"id inexistente: {trial_id}")
    recorded = found[0].get("cache_manifest_sha256")
    if not recorded:
        return {"trial_id": trial_id, "match": False, "checked": False}
    try:
        from app.core.cache_integrity import snapshot_hash

        if cache_dir is None:
            here = os.path.dirname(os.path.abspath(__file__))
            cache_dir = os.path.normpath(os.path.join(here, "..", "..", "data", "cache"))
        import hashlib
        import json as _json

        manifest = snapshot_hash(cache_dir)
        present = [v for v in manifest.values() if not v.get("missing")]
        if not present:
            # cache vacío/inexistente: sin datos no hay veredicto de integridad
            return {"trial_id": trial_id, "match": False, "checked": False}
        current = hashlib.sha256(
            _json.dumps(manifest, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {"trial_id": trial_id, "match": current == recorded, "checked": True}
    except Exception:  # noqa: BLE001 — sin cache disponible no hay veredicto
        return {"trial_id": trial_id, "match": False, "checked": False}
