# TASK_KILO_A_OPENCODE_FASE3_20260913 — Asset Favourability por régimen (Kilo → OpenCode)

Fecha: 2026-09-13 12:10 · De: Kilo (orquestador) · Para: OpenCode (análisis de la estrategia de inversiones).
Este ticket CONTINÚA tu plan SDD `institutional-flow-score` (roadmap verificado
de tu sesión: F1 nowcast ✅ mergeada 3be74cd, F2 fingerprint ✅ mergeada
d8e589f/01dde7c, **F3 = ESTA TAREA**, F4 score compuesto, F5 reglas E/S/sizing,
F6 panel advisor).

## Lanzamiento de Fase 3: Asset Favourability por régimen (validar con datos reales)

**Qué es** (de tu propio plan): medir la favorabilidad de activos condicionada
al régimen de mercado — la pieza que conecta el fingerprint institucional (F2)
con la selección de activos. La Fase 4 (score compuesto 0-100) depende de esto.

## Requisitos previos (no negociables, ordenados)

1. **Posicionate**: rama NUEVA desde origin/main actual (`9d64f61`) — tu rama
   `verify/opencode-wip` está absorbida. `git fetch && git checkout -b
   <tu-rama> origin/main` en tu worktree.
2. **DEUDA PRIMERO (30 min)**: pre-registros post-hoc honestos de lo ya
   mergeado (TTL del cache /regime, falla blanda COT/AAII/FRED, historia 180d)
   — tu ticket 20260912 punto 2 lo sigue pidiendo. + B1 throttle si te sobra
   margen.
3. **Pre-registro ANTES de código** para F3 (regla 2 del repo): hipótesis
   medible, fuentes de datos, ventana, criterio IC/gate (mismo estándar que tu
   Phase Gate 2: IC > 0.02, Bonferroni p < 0.0056 — o el que definas, pero
   escrito ANTES), criterio de reversión.
4. **Sin merge**: entregás en tu rama + entrada en ORCHESTRATOR_INBOX.md,
   Kilo verifica (o Claude Code como tercer ojo) y mergea con orden de Boris.

## Guía de diseño (Kilo, desde el contexto del repo)

- **Causalidad estricta** como F2: todo dato ≤ as_of, shift(1)+ffill para
  series externas. Un solo lookahead mata la fase completa.
- **Datos reales**: tu ticket original dice "validar con datos reales" —
  cachea lo que descargues (parquet, como cot_YYYY) y NO re-descargues en cada
  corrida; documenta la cuota/latencia de cada fuente.
- **Universo**: el de `opportunities_universe.SYMBOLS` (102) salvo que tu
  hipótesis pida otro — justificá en el pre-registro.
- **Reutiliza** `regime_nowcast` (F1) para las etiquetas de régimen: no
  reimplementes el HMM.
- **Slow tests**: marca walk-forwards largos con `@pytest.mark.slow` (patrón
  de tu F2, ya respetado por la suite).
- **PLAN_MEJORA_MATEMATICA.md**: si la F3 produce un hallazgo con vocación de
  trial (favorabilidad con IC real), va por el trámite de trial formal —
  nada de "validado" sin pre-registro en ese documento.

## Verificación (Kilo)

- Suite de tu rama verde (incluye tus tests F3 nuevos) + spot-check de
  causalidad (un test que reviente si alguien quita el shift).
- Falsación: al menos un test que falle si la hipótesis se mide con lookahead
  (el clásico "sin shift el IC se infla" — si tu IC gate no lo distingue,
  el gate está roto).
- Claude Code disponible como verificador independiente si el slice es grande.

Entregable: commits por capa en tu rama + entrada inbox + SESSION_LOG.

---

## ORDEN DE IMPLEMENTACIÓN (Boris, 2026-09-13 21:27) — EJECUTAR AHORA

Boris confirma: **implementá la Fase 3 ya** (tu plan de sesión está alineado con
este ticket; el diseño TASK-009/010 que cerraste hoy es el que va). Claude Code
sin créditos: Kilo es tu único verificador — avisá por inbox al terminar.

Ejecutá en ESTE orden, sin saltear:

1. **Rama nueva desde origin/main** (`faaf7f2`): `git fetch && git checkout -b
   feat/f3-asset-favourability origin/main` en tu worktree. Tu rama
   `verify/opencode-wip` está absorbida — no partas de ahí.
2. **Pre-registro F3 ANTES de código** (PRE_REG_F3_ASSET_FAVOURABILITY.md,
   commit separado): tu propio diseño de sesión ya lo define —
   AssetFavourability (TASK-009/010), universo SPY/QQQ/GC=F/TLT/TIP/AGG/DBC/
   ^VIX + 50 stocks, métricas mean/win%/Sharpe/maxDD por (régimen, activo,
   horizonte 21/63/126d), **Gate 3 inmutable: separación best-vs-worst régimen
   >0.5% anualizado por activo**. Escribí ahí también: fuentes de datos y su
   caché, causalidad shift(1)+ffill, OOS holdout 2024-26 intocable, criterio
   de reversión.
3. **Implementación**: reusá `regime_nowcast` (F1) para etiquetas de régimen —
   no reimplementes el HMM. Tests con patrón slow-mark como tu F2. Test de
   falsación anti-lookahead obligatorio (sin shift(1) el IC/gate debe reventar).
4. **Entrega sin merge**: commits por capa en tu rama + entrada
   ORCHESTRATOR_INBOX.md + SESSION_LOG. Kilo verifica y mergea con orden de
   Boris.

## Coordinación (2026-09-14, Kilo orquestador)

- Rige PROTOCOLO_COORDINACION_AGENTES.md (raíz del repo): tu worktree es
  exclusivo, prohibido `git stash` (stack compartido del repo), push solo de
  tus ramas, suites focalizadas durante desarrollo (la completa la corre Kilo
  al verificar). No toques el worktree de Cline ni el de Kilo: leé su código
  vía origin después de fetch.
