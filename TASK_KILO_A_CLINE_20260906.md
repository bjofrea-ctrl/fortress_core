# TASK PARA CLINE — de Kilo (orquestador, autorizado por Boris 2026-09-06)

Tu worktree: fundamentales-automatizado. Trabaja SOLO aquí, no en main.
Categoría trial_registry de ambos tickets: bugfix/infraestructura (gate-legal).
NO pushear ni mergear — Kilo verifica y mergea.

## TU TICKET 1 — M4: blindar A0 contra destrucción del cache (URGENTE)

**Archivo**: `backend/app/core/cache_integrity.py` (y/o donde `data_ingestion.py`
llama al modo full-redownload).

**Problema verificado por la re-auditoría externa**: `repair_full_redownload`
valida solo que la descarga fresca no venga VACÍA y entonces sobreescribe el
parquet completo. Si yfinance devuelve datos corruptos frescos (barras cruzadas,
retornos anómalos), el harness destruiría el cache BUENO. El remedio se
convierte en la enfermedad.

**Fix exigido (mínimo, sin tocar nada más del archivo)**:
1. Antes de escribir el parquet reparado, correr el MISMO conjunto de
   validaciones de integridad sobre el dataframe fresco (retornos anómalos,
   contaminación cruzada, huecos vs calendario NYSE — las funciones ya existen
   en el módulo).
2. Si el fresco FALLA la validación → NO sobreescribir. Conservar el cache
   existente y registrar la razón (p.ej. `"cache existente conservado; descarga
   fresca inválida: <detalle>"`).

**Test nuevo** (en `backend/tests/test_cache_integrity.py` o donde vivan los
tuyos): siembra un cache válido + una descarga fresca corrupta → el cache BUENO
sobrevive y el fallo queda registrado.

## TU TICKET 2 — M3: blindar el ritual de cierre de sesión

**Problema**: SESSION_LOG.md quedó sin entradas del 03 al 06-sep (violación del
ritual de ONBOARDING — ya flaggeado por la re-auditoría externa). "El rastro
que no se escribe no existe para el próximo agente."

**Entregables**:
1. Chequeo mecanizado: un warning visible (en el latido o un script ligero)
   si SESSION_LOG.md no tiene entrada en las últimas 48h.
2. Entrada de catch-up en SESSION_LOG.md documentando lo del 04-06 sep que
   falta (tus commits B4/B5/B8 + nota de que Kilo mergeó A2/B8/C1 el 06-09).

## Contexto para que no te pises con nadie

- Kilo YA mergeó a main (o está terminando de hacerlo): tu c057031 (B8) vía
  cherry-pick, tu c602a30 (B5) y 2d3c888 (B4) también. Tu 55606a3 (A2) fue
  DESCARTADO — su parser (a) usa un regex con timestamp-T que no existe en el
  pipeline_diario.log real (verificado por Kilo contra el log); la A2 vigente
  es la consolidación de Kilo (formato real + bloques inicio/fin + reconciler
  diario 22:10).
- Las 7 líneas reconcile falsas del log de producción YA fueron limpiadas.
- Al terminar tus tickets: commit en TU rama + avisar a Boris. Kilo verifica
  con suite y mergea.
