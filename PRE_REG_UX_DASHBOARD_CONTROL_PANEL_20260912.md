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