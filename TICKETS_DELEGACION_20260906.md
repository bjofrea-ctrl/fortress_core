# TICKETS DELEGADOS — 2026-09-06 (orquestador: Kilo)

Orquestación de merges aprobada por Boris (2026-09-06 ~19:00). Reglas del
PLAN_48H vigentes: ejecutor ≠ verificador, suite completa antes de cada
veredicto, working tree de cada agente queda limpio tras su ticket.

Asignación sin superposición de archivos:

## CLINE — M4 + M3 (rama: fundamentales-automatizado)

### M4: re-validación en A0 antes de sobreescribir cache (URGENTE, 2 líneas)
- **Dónde**: `backend/app/core/cache_integrity.py`, función
  `repair_full_redownload` (o su equivalente en `data_ingestion.py` donde se
  escribe el parquet reparado).
- **Qué**: hoy el modo "full re-download" valida solo que la descarga fresca
  no venga VACÍA y entonces sobreescribe el parquet. Si yfinance devuelve
  datos corruptos frescos, el harness destruiría el cache bueno — el remedio
  convirtiéndose en la enfermedad.
- **Fix exigido**: antes de `os.replace(...)`, correr el MISMO conjunto de
  validaciones de `cache_integrity` sobre el dataframe fresco (retornos
  anómalos, contaminación cruzada, huecos vs calendario NYSE). Si el fresco
  FALLA la validación: NO sobreescribir, registrar el fallo y conservar el
  cache existente (mensaje claro: "cache existente conservado; descarga
  fresca inválida").
- **Test**: uno que siembre un cache válido + una descarga fresca corrupta →
  el cache bueno SOBREVIVE. Categoría trial_registry: `bugfix` (gate-legal).
- NO tocar nada más del archivo — solo la rama de full-redownload.

### M3: blindar el ritual de cierre de sesión
- **Qué**: SESSION_LOG.md quedó sin entradas 03→06 sep (violación del ritual
  de ONBOARDING, ya señalado por la re-auditoría externa). Dos entregables:
  1. Regla mecanizada: un hook/chequeo (conftest o script del latido) que
     si `SESSION_LOG.md` no tiene entrada en las últimas 48h, imprima un
     WARNING visible en la salida del updater/latido.
  2. Entrada de catch-up en SESSION_LOG.md documentando los cierres
     04→06 sep que faltan (tus commits B4/B5/B8 + los merges de hoy de Kilo).
- NO es trial (infraestructura/documentación).

### Al terminar
- Commit en tu rama (categoría bugfix/infraestructura). NO pushear.
- Avisar a Boris; Kilo verifica con suite y mergea.

## OPENCODE — B6 hang + B1 throttle (rama: test-opencode-orca)

### B6: el "hang" de tus golden tests está DIAGNOSTICADO (no es bug tuyo)
- **Causa raíz** (verificada por Kilo con -v + kill): el archivo completo
  cuelga solo en `TestGolden60DayUniverse::test_60_days_universe_bit_identical`
  — el único `@pytest.mark.slow` (60 días × 30 símbolos = ~1800 evaluaciones
  con SignalEngine completo). Los otros 16 tests pasan en ~18s. NO hay
  deadlock: es tiempo de cómputo legítimo (estimo 5-15 min).
- **Fix pedido (pequeño, no cambia matemática)**:
  1. Registrar el marker `slow` en `pytest.ini` (`markers = slow: ...`).
  2. Documentar en el docstring del test el tiempo esperado.
  3. NO marcarlo skip: es LA verificación de equivalencia dorada de B6.
     Si en tu hardware tarda >15 min, medirlo y documentar el número.
- Categoría: infraestructura (gate-legal).

### B1: throttle observacional del monitor de rate Alpaca
- **Dónde**: el monitor que hoy solo "imprime resumen al final".
- **Qué**: agregar WARNING visible si el uso supera 70% del límite (200/min)
  en la ventana, y un throttle simple (sleep escalonado) si supera 85%.
  Hoy no hay riesgo (30 req), pero escala mal para el 1/12.
- Categoría: infraestructura (gate-legal). Post-merge de hoy.

### Al terminar
- Commit en tu rama. NO pushear. Avisar a Boris; Kilo verifica y mergea.

## Estado de merges de hoy (para que nadie pise)

- Kilo ya mergeó/está mergeando: test-kilo-orca (A2 consolidado + reconciler
  diario 22:10), B4+B5+B8 de fundamentales-automatizado (SIN 55606a3 — A2 de
  Cline descartado: su parser (a) usa un regex con timestamp-T que no existe
  en el log real; verificado por Kilo contra pipeline_diario.log), C1 docs
  de gate-c1-diciembre.
- Las 7 líneas reconcile falsas del pipeline_diario.log real YA fueron
  eliminadas por Kilo (eran contaminación del test de pytest pre-fix;
  backup en /tmp/pipeline_diario.log.bak_*).
- La 3ª implementación A2 (sin commitear en el repo real) fue descartada
  (backup /tmp/a2_obsoleta_backup).
