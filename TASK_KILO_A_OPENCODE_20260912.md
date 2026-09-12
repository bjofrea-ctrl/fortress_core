# TASK_KILO_A_OPENCODE_20260912 — Análisis estratégico + cola técnica (Kilo → OpenCode)

Fecha: 2026-09-11 (noche) · De: Kilo (orquestador) · Para: OpenCode (análisis de la estrategia de inversiones).
Verificación/merge: Kilo orquesta; Boris aprueba merges a main.

## Estado de tu cola (verificado por Kilo, 2026-09-12 17:20 — ACTUALIZACIÓN FINAL)

1. **Tu WIP de 3 capas fue RESCATADO, commiteado por capas y MERGEADO a main**
   (01dde7c): 3be74cd (RegimeNowcaster 30 tests + endpoint /api/advisor/regime)
   y d8e589f (institutional_fingerprint Phase 2 COT/AAII/FRED 20 tests,
   termómetro absorbido). Rebase sobre main resuelto por Kilo (tu advisor.py
   base era pre-SWR — conflicto de imports trivial). Suite post-merge 95/95.
   Tu rama verify/opencode-wip está absorbida en main — **para tu próxima
   tarea: rama nueva desde main actual.**
2. **DEUDA DE PRE-REGISTRO (tu primera tarea)**: lo rescatado llegó a main sin
   los documentos de pre-registro que la casa exige (TTLs de cache del
   endpoint /regime, fuentes externas y comportamiento de falla blanda).
   Escribí PRE_REG post-hoc HONESTO (marcado como tal) cubriendo: TTL del
   cache de régimen, qué pasa si COT/AAII/FRED falla cada uno, límite de
   historia 180d. Los tests ya existen — el documento es lo que falta.
3. **B1 throttle** (ticket TASK_KILO_A_OPENCODE_20260906.md): WARNING >70%,
   sleep escalonado >85% — sigue pendiente, es corto.
4. **Hipótesis ciclo institucional → trial formal** vía
   PLAN_MEJORA_MATEMATICA.md + ledger si querés llevarla a veredicto.
5. NOTA de infra: volumen EMPRESA se desmontó — espejo git pendiente de
   sincronizar cuando se remonte (Kilo tiene el bundle).

## Prioridad estratégica (tu dominio: análisis de la estrategia de inversiones)

**(ACTUALIZACIÓN 2026-09-12 16:30 — Kilo verificó tu WIP acumulado)**: 362 líneas
sin commitear en advisor.py+tests (endpoint `/regime` + nowcast) + 2 módulos
nuevos untracked (regime_nowcast.py, institutional_fingerprint.py — Phase 2
fingerprint COT/AAII/FRED, 9 variables causales) + thermometer.py. Tests
corridos por Kilo: 50/50 (nowcast+fingerprint) y 31/31 advisor. **El trabajo es
bueno — el problema es de proceso**, y se agrava: tu rama está **behind 39** de
origin/main y tu advisor.py base NO tiene el SWR que Kilo mergeó en su rama
(cuando eso llegue a main vas a re-merge sobre un archivo que cambió +149
líneas tuyas). **Hazlo AHORA en este orden**:

1. `git fetch origin && git rebase origin/main` (o rama nueva desde main).
   Conflictos esperados en advisor.py: tu base es pre-SWR.
2. Commitea POR CAPA con entrada SESSION_LOG: (a) termómetro + endpoint,
   (b) regime_nowcast + endpoint /regime, (c) institutional_fingerprint.
   Cada uno con su pre-registro si falta (TTLs de cache, fuentes externas,
   falla blanda — los tests ya existen, falta el documento).
3. Luego B1 throttle (ticket viejo) y la hipótesis del ciclo institucional
   a trial formal vía PLAN_MEJORA_MATEMATICA.md si querés llevarla más lejos.

El trabajo viejo sigue válido:

1. **Commitear el WIP del termómetro + los 2 ANALISIS_*.md** con entrada
   SESSION_LOG — la visibilidad es parte de la entrega.
2. **Si el termómetro va a producción** (endpoint nuevo): pre-registro ANTES de
   seguir tocando código — TTLs de cache (6h parquet), fuentes externas (CNN
   F&G, GDELT), falla blanda — criterios medibles de qué pasa cuando cada
   fuente falla. El endpoint toca advisor.py: coordiná con Kilo antes de
   editar (main acaba de recibir SWR en /universe — mismo archivo).
3. **B1 throttle** — cierre de ticket viejo, rápido.
4. La hipótesis del ciclo institucional, si querés llevarla a trial formal:
   pre-registro en PLAN_MEJORA_MATEMATICA.md + ledger de trials como todo
   trial (regla 2 del repo). Nada de señal "validada" sin ese trámite.

## Reglas intactas

- Pre-registro ANTES de código para cambios con criterio de aceptación.
- Sin merge a main sin orden explícita de Boris (vía Kilo).
- advisor.py es territorio compartido con Kilo ahora (SWR): avisá antes de tocar.
