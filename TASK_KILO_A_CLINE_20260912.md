# TASK_KILO_A_CLINE_20260912 — Cola priorizada del dashboard (Kilo → Cline)

Fecha: 2026-09-11 (noche) · De: Kilo (orquestador) · Para: Cline (dashboard, frontend y backend de punta a punta).
Verificación/merge de TODO lo que siga: Kilo orquesta; Boris aprueba merges a main.

## Estado de tu cola (verificado por Kilo, 2026-09-11)

1. `07bffa8` (audit/dashboard-utilidad) — **VERIFICADA por Kilo** (docs-only, método
   correcto, hallazgos G1-G3 trazados a archivo:función). **Pendiente: decisión de
   Boris** sobre las recomendaciones G1/G2/G3 — NO implementar nada de esto sin
   su OK explícito (tu propia auditoría lo exige: "solo con decisión explícita").
   Tu Slice 1 (PRE_REG_UX_DASHBOARD_CONTROL_PANEL_20260912.md) ya lo ejecuta
   parcialmente — ver punto 3.
2. `a881d7a` (test concurrencia memo) — **VERIFICADO por Kilo**: 9/9 passed
   contra main. Quedó huérfano del cherry-pick de tu propio fix (main tiene el
   fix sin este test). **Kilo lo mergea a main en el próximo lote** (aviso a
   Boris antes). No requiere acción tuya.
3. UX Slice 1 (PRE_REG_UX_DASHBOARD_CONTROL_PANEL_20260912.md) — tu trabajo en
   curso. **Sigue con él** — es exactamente la dirección de la auditoría G1.
   Nota: tu PRE_REG estaba sin commitear en el worktree; Kilo lo preservó en
   stash `kilo-orquestador: PRE_REG UX Slice 1` (junto a backtest.py modificado)
   — recupéralo con `git stash pop` en tu worktree y commitea el pre-registro
   ANTES del código, como manda la regla.
4. Brechas de TU auditoría que son tuyas por dominio (post-decisión Boris):
   - G1: vintage en Portfolio (tu backtest.py +41 ya lo expone; falta UI).
   - G2: widget TV externo + MarketOverview/LiveTicker solapados + 3 componentes
     muertos (limpieza UI).
   - G3: 16 indicadores calculados no visualizados (decisión de qué mostrar).

## Prioridad para los próximos días (orden Kilo)

1. **Terminar Slice 1 UX** (en curso) — commitea pre-registro primero.
2. **Main desincronizado con tu cola**: los commits 45bc9c1, c1fc2e3, e63e8c9,
   c345072, 8b594f6, a23179c ya están en main; tu ROADMAP.md de rama dice
   "pendiente de merge" en secciones que ya se cherry-pickearon. Al commitear
   Slice 1, arrastra una **corrección de esas 2 secciones ROADMAP** (líneas
   ~876 y ~900 de main) para que dejen de contradecir el estado real.
3. **Residuos del fix governance 500** en main: SPY.parquet.bak_20260910_gov500
   y .CONTAMINATED sin trackear en backend/data/cache/ — decide con Boris si
   borrar (es tu fix, tu artefacto) o mover a espejo.

## Reglas intactas

- Pre-registro ANTES de código para cualquier cambio con criterio de aceptación.
- Sin merge a main sin orden explícita de Boris (vía Kilo).
- Todo lo tuyo pasa verificación independiente (Kilo u OpenCode) antes de merge.
