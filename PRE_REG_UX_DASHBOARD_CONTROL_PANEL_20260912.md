# Pre-registro UX — Dashboard como panel de control de la operativa (Slice 1)

Fecha: 2026-09-12 · Rama: `ux/dashboard-control-panel` (off `main` c345072) · NO merge sin tu OK
Fuente: `AUDITORIA_DASHBOARD_UTILIDAD_20260911.md` (G1-G3).

## Slice 1 — lo que entrego (máximo valor, cero riesgo de dato)

1. **Vintage en Portfolio (G1-1):** `backtest.py` expone `meta{vintage}` DERIVADO del artefacto
   real (ventana equity_curve + símbolos/trades del JSON) — sin inventar nada — y KPICards/EquityCurve
   lo muestran como caption + caveat "investigación, no operativa".
2. **`factors` visibles en la Mesa (G1-2):** el expand de fila muestra los factors del ticket
   (ya viajan en el payload); sigue sin lector nuevo.
3. **Estados vacíos que explican (G2/G3):** Mesa sin INVERTIR, tesis vacías, riesgo sin datos,
   governance en fallback → cada uno dice QUÉ significa y QUÉ acción tomar (no solo "sin datos").
4. **Definiciones inline (Mesa/Detalle):** tooltips en Win prob, Proyección §29, M2, Stop/Target,
   Δ transición y gates — la metodología explicada donde se mira, memorable sin manual.

## Criterios de cierre (medibles, ANTES de correr)

- C1: `/api/backtest/metrics` incluye `meta{vintage}` correcto contra el artefacto real
  (ventana 2019-01-02→2024-11-18, 6 símbolos) verificado con lectura del JSON, no del código.
- C2: regresión backend intacta (`test_backtest_api.py` + job/screen suites verdes — el contrato
  `metrics` existente no cambia, solo se ADICIONA `meta`).
- C3: `vitest run` verde (frontend) + `tsc` limpio; tests existentes de vistas sin editar
  salvo lo mecánico exigido por el provider (regla DASH_TABS).
- C4: verificación visual real del dashboard servido (no solo DOM de test): Mesa/Portfolio con los
  cambios visibles, sin errores de consola.

## Fuera de alcance de este slice (cola explícita)

- Renombrar INVERTIR / cambiar scoring / tocar Gobernanza y Fundamentos (tu regla).
- Borrar componentes muertos (decisión tuya G2-5; requieren tu OK de borrado).
- Unificar MarketOverview/LiveTicker (requiere decisión de layout tuya).

## Estado de cierre (verificado 2026-09-14 sobre la rama, no declarado)

Ítems del slice, en la numeración de ESTE documento (ojo: el handoff del 14 hablaba de
"ítems 3 y 5" con otra numeración — la fuente son los 4 ítems de arriba):

| # | Ítem | Estado | Evidencia |
|---|------|--------|-----------|
| 1 | Vintage en Portfolio (G1-1) | **CERRADO** | `efbfdd4` backend `meta{vintage}` derivado del JSON + `15b2b62` caption/caveat en KPICards |
| 2 | `factors` visibles en la Mesa (G1-2) | **CERRADO** | `2e6a258` barras por factor en la fila expandida de `advisor/MesaView.tsx` |
| 3 | Estados vacíos que explican (G2/G3) | **CERRADO** | `63ad36c` RiskPanel (consultando vs no_data) + `38f49d3` MesaPage (universo vacío / cero INVERTIR con la abstención como señal) |
| 4 | Definiciones inline (Mesa/Detalle) | **CERRADO** | `7c8ff29` tooltips en Win prob, Proyección §29, Dist EMA, Stop, Target, Δ, gates, M2; leyenda de gates visible sin hover; `M2 no calibrado (n < 30)` explícito |

Criterios de cierre:

- **C1 ✅** `meta{vintage}` contra el artefacto real (`backtest_results.json`, ventana
  2019-01-02→2024-12-31, n_trades=303), no contra el código.
- **C2 ✅** `pytest tests/test_backtest_api.py` → **10 passed** (corrido 2026-09-14 en esta
  rama con el venv de `~/Desktop/fortress_core`).
- **C3 ✅** `vitest run` **suite completa: 11 archivos, 66 passed** (incluye los 3 tests nuevos
  de este slice) y `./node_modules/.bin/tsc --noEmit` → **exit 0**.
- **C4 ⏷ proxy técnico hecho, falta verificación visual humana.** `npm run build`
  (`tsc && vite build`) sobre la rama: **909 módulos, exit 0, 14.85s**. Eso prueba que compila
  y empaqueta; NO prueba que se vea bien ni que la consola esté limpia. Falta abrir el
  dashboard servido en navegador — lo hace Boris o un agente con navegador, y hasta no verlo
  este criterio no se marca cerrado.

Ganchos de la rama (para el próximo): `MesaView.tsx` vive en
`frontend/src/components/advisor/` (NO en `views/`); el venv del backend está en el repo
principal, no en el worktree; y `npx tsc` NO resuelve el typescript local — usar
`./node_modules/.bin/tsc` o el exit code queda enmascarado por el pipe.

## Merge: superficie real al 2026-09-14

Medida con `git diff --stat main ux/dashboard-control-panel`: **main ya contiene el contenido
de los ítems 1, 2 y 3-parcial** (vintage en `backtest.py`, `factors` en MesaView, RiskPanel),
aunque los commits de esta rama no son ancestros de `main`. El delta de contenido restante es
chico: `MesaPage.tsx` (+19), `MesaPage.test.tsx` (+32), este PRE-REG, `ROADMAP.md`, y el
**ítem 4, que es aporte nuevo real** — verificado: `main` tiene 1 solo `title=` en MesaView y
el delta rama-vs-main es +91/−21.

→ La decisión de merge/rebase sigue siendo de Boris (**NO merge sin su OK**, regla de este
pre-registro). El rebase sobre `main` (`a5893fe`) ahora es de superficie chica, no de 5 commits
de frontend pesados; el riesgo real está en los ~4400 líneas que `main` adelantó a esta rama.
