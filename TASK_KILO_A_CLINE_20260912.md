# TASK_KILO_A_CLINE_20260912 — Cola priorizada del dashboard (Kilo → Cline)

Fecha: 2026-09-11 (noche) · De: Kilo (orquestador) · Para: Cline (dashboard, frontend y backend de punta a punta).
Verificación/merge de TODO lo que siga: Kilo orquesta; Boris aprueba merges a main.

## Estado de tu cola (verificado por Kilo, 2026-09-12 17:20 — ACTUALIZACIÓN FINAL)

1. **Slice 1 G1 COMPLETO y MERGEADO a main** (f207e91): tu efbfdd4 (vintage
   meta) + 15b2b62 (KPICards) + el MesaView G1-2 que dejaste sin commitear
   (Kilo lo commiteó como 2e6a258 tras verificar tsc limpio). Suite post-merge
   95/95. Tu rama ux/dashboard-control-panel está absorbida — parte de rama
   nueva desde main para lo que sigue.
2. **G2 (limpieza UI) es tu PRÓXIMA TAREA** — aprobado por Boris: widget TV
   externo + MarketOverview/LiveTicker solapados + 3 componentes muertos.
   Pre-registro antes, como siempre. Verifica contra
   AUDITORIA_DASHBOARD_UTILIDAD_20260911.md §G2.
3. **G3 (16 indicadores no visualizados)** después de G2: proponé el
   subconjunto a mostrar con justificación de utilidad — Kilo/Boris validan
   antes de implementar (es decisión de diseño, no limpieza).
4. NOTA de infra: volumen EMPRESA se desmontó — el espejo git quedó a la
   espera. Si lo ves montado, avisá a Kilo (no lo sincronices vos: hay bundle
   pendiente de aplicar).

## Prioridad para los próximos días (orden Kilo)

0. **(ACTUALIZACIÓN 2026-09-12 13:30)** — **Boris APROBÓ las recomendaciones
   G1/G2/G3** de tu auditoría. El freno "solo con decisión explícita" está
   levantado: las tres van a implementación. Sugerencia de orden por riesgo
   (Kilo): G1 primero (vintage en Portfolio + factors con lector vivo — tu
   backtest.py ya expone meta{vintage}), G2 después (limpieza de widget TV +
   componentes muertos — riesgo UI bajo), G3 al final (16 indicadores no
   visualizados — decisión de diseño sobre QUÉ mostrar, proponé el subconjunto
   y Kilo/Boris validamos). Pre-registro antes de cada slice como siempre.
   NOTA OpenCode: la auditoría, el test de concurrencia memo (9be137f) y tu B6
   (5127c68) ya están mergeados a main por Kilo — rebaseá antes de partir de
   main. Claude Code está disponible como verificador independiente si Kilo
   necesita tercer ojo en slices grandes.

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
