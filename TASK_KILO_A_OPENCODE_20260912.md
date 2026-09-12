# TASK_KILO_A_OPENCODE_20260912 — Análisis estratégico + cola técnica (Kilo → OpenCode)

Fecha: 2026-09-11 (noche) · De: Kilo (orquestador) · Para: OpenCode (análisis de la estrategia de inversiones).
Verificación/merge: Kilo orquesta; Boris aprueba merges a main.

## Estado de tu cola (verificado por Kilo, 2026-09-11)

1. **B6** (`4fe09b0` validación_oos al contrato de señal única) — **VERIFICADO por
   Kilo sobre main actual** (rama temporal desde origin/main + cherry-pick
   --no-commit): 2/2 tests propios + 76 regression (signal_contract golden,
   advisor warmup/api, memo integridad, cache_integrity) todos verdes, sin
   conflictos. El inbox lo marcaba "MERGEADO" pero NUNCA llegó a main — es tu
   entrega más vieja pendiente (09-08). **Kilo lo mergea en el próximo lote**
   (aviso a Boris antes). No requiere acción tuya.
2. **B1** (throttle monitor de rate Alpaca: WARNING >70%, sleep escalonado >85%,
   TASK_KILO_A_OPENCODE_20260906.md) — sigue PENDIENTE de implementar. Es
   infraestructura del paper trading, no análisis — pero es tuyo por continuidad
   del ticket original.
3. **Termómetro de sentimiento** (thermometer.py + endpoint /api/advisor/thermometer,
   trabajo sin commitear en tu worktree) — Kilo lo preservó en stash
   `kilo-orch: thermometer WIP opencode`. Recupéralo con `git stash pop`.
   **Antes de continuar: commitea lo que tenés** (aunque sea WIP) con entrada
   SESSION_LOG — tu última entrada es del 09-07 y hay trabajo del 09-10/09-11
   (termómetro + ANALISIS_REBUILD_531S.md) completamente invisible para la
   historia del repo. ANALISIS_REBUILD_531S.md alimentó el fix c1fc2e3 que ya
   está en main — ese análisis merece estar commiteado.
4. Tu rama `b6-signal-contract-align` está **behind 34 de origin/main**. Antes de
   seguir trabajando: `git fetch && git rebase origin/main` o rama nueva desde
   main. Trabajar 34 commits atrás es cómo nacen los conflictos.

## Prioridad estratégica (tu dominio: análisis de la estrategia de inversiones)

El trabajo de análisis reciente (ANALISIS_CICLO_INSTITUCIONAL.md: hipótesis del
ciclo institucional medida sobre 5 años / ~130 activos / 392 eventos) está bien
encaminado pero INVISIBLE (sin commit, sin ticket, sin entrada de sesión).
Para que prospere:

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
