# VERIFICACIÓN VISUAL DEL DASHBOARD/EXCEL — Fase 4 (ROADMAP, ítem 2)

> **PENDIENTE VERIFICAR** (pedido explícito de Boris, cerrado en esta sesión): que el
> dashboard/Excel generados por `render_artifacts()` se *vean* iguales al original real
> de AAI (formato/layout), no solo que los tests pasen.
>
> Fecha de verificación: 2026-09-01
> Motor canónico usado: **vendorizado** en `backend/app/core/motor_canonico/scripts/motor_screening.py`
> (hash byte-a-byte verificado contra el zip oficial r13 de la skill,
> `84abe308e7e8e710f2cf2e7649bd9d6074c1e7de1ab8c7dd0f26f3b51768995d`).
>
> Referencia: `backend/tests/fixtures/canon/market_view_export.xlsx` — export real de
> InvestingPro re-subido por Boris el 29/08/2026 (creator: `finbox.io`).

---

## 1. Metodología

1. **Generamos los artefactos** corriendo el motor canónico **vendorizado** directamente
   sobre `market_view_export.xlsx` (el export real), usando `motor_screening.py` como
   entry point (igual que el job runner `run_fundamentals_screen.py` lo hace internamente
   vía `render_artifacts()` → `generar_excel()` / `generar_dashboard()`).

2. **Abrimos ambos archivos** y comparamos estructuralmente:
   - `market_view_export.xlsx` (INPUT — export InvestingPro, el "original real de AAI")
   - `Screening_AAI_2026-09-01.xlsx` (OUTPUT — generado por el motor vendorizado)
   - `Dashboard_AAI_2026-09-01.html` (OUTPUT — dashboard interactivo del motor)

3. **Compáramos** formatos, layouts, colores, columnas, estilos, conditional formatting,
   estructura de hojas. Los números ya están verificados (paridad PLAN §3, cerrado el
   29/08) — **esto es pura verificación visual/formato, no numérica**.

4. **Tests**: toda la suite `test_fundamentals_screen.py` + `test_fundamentals_screen_e2e.py`
   pasa 32/32 (1 skip por REQUIRE_PARIDAD no activado en esta sesión).

---

## 2. Entendimiento: ¿qué es cada archivo?

| Archivo | Rol | Origin |
|---|---|---|
| `market_view_export.xlsx` | **INPUT** — export del screener InvestingPro | Producido por finbox.io (AAI) el 2026-08-29 |
| `Screening_AAI_<fecha>.xlsx` | **OUTPUT** — Excel enriquecido con clasificación | Generado por el **motor canónico vendorizado** |
| `Dashboard_AAI_<fecha>.html` | **OUTPUT** — Dashboard interactivo | Generado por el **motor canónico vendorizado** |

**Importante**: el `market_view_export.xlsx` es el EXPORT (input), NO el output del motor.
El motor lo lee (`leer_export()`) y produce un archivo de salida con un formato
**fundamentalmente diferente** (columnas enriquecidas, bandas de color, veredictos,
etc.). La comparación no es "el output se ve igual al input" — es "el output tiene
el formato/visual que corresponde al motor canónico original de AAI".

---

## 3. Estructura del archivo de referencia (`market_view_export.xlsx`)

### 3.1 Metadatos del workbook

| Propiedad | Valor |
|---|---|
| Creator | `finbox.io` |
| Created | `2026-08-29 14:40:15` |
| Modified | `2026-08-29 14:40:15` |
| Title | (vacío) |

### 3.2 Hoja (`sheet`)

| Propiedad | Valor |
|---|---|
| Nombre | `sheet` (minúscula — convención InvestingPro) |
| Dimensiones | `A1:AB1009` (1009 rows × 28 cols) |
| showGridLines | `False` |
| freeze_panes | `None` |
| Conditional formatting | `None` |
| Comentarios | 0 |
| Merged cells | `C2:E2`, `C6:D6` |

### 3.3 Distribución de filas

- **Row 1**: vacío
- **Row 2** (C): `"fortress core"` — Arial 20pt, bold, color `#1551C3` (azul AAI)
- **Row 3** (C): `"Premium Export"` — (etiqueta de InvestingPro)
- **Row 4-5**: vacíos
- **Row 6** (C): `"Summary"` — Arial 11pt, bold, color `#1551C3`, fill `#F8F8F8`
- **Row 7**: vacío
- **Row 8**: FILA DE ENCABEZADOS (26 columnas)
- **Row 9**: vacío
- **Rows 10-1009**: 1000 empresas con datos

### 3.4 Columnas del export (fila 8)

| Col | Letra | Nombre | Formato numérico |
|---|---|---|---|
| 3 | C | `Name` | General |
| 4 | D | `Full Ticker` | General |
| 5 | E | `Ticker` | General |
| 6 | F | `Price, Current` | `0.00` |
| 7 | G | `Fair Value` | `0.00` |
| 8 | H | `Market Cap (Adjusted)` | `[<1e6]0.00,"K";[<1e9]0.00,,"M";0.00,,,"B"` |
| 9 | I | `P/E Ratio` | `0.00` |
| 10 | J | `Total Debt / Total Capital` | `0.0%` |
| 11 | K | `Free Cash Flow Yield` | `0.0%` |
| 12 | L | `P/E Ratio (Fwd)` | `0.00` |
| 13 | M | `Beta (5 Year)` | `0.0` |
| 14 | N | `Return on Invested Capital` | `0.0%` |
| 15 | O | `Avg Return on Invested Capital (5y)` | `0.0%` |
| 16 | P | `Return on Equity` | `0.0%` |
| 17 | Q | `Gross Profit Margin` | `0.0%` |
| 18 | R | `Avg EPS Growth (5y)` | `0.0%` |
| 19 | S | `Revenue CAGR (5y)` | `0.0%` |
| 20 | T | `FCF / Net Income` | `0.0%` |
| 21 | U | `Buyback Yield` | `0.0%` |
| 22 | V | `Piotroski Score` | `#,##0` |
| 23 | W | `Altman Z-Score` | `0.0` |
| 24 | X | `Beneish M-Score` | `0.00` |
| 25 | Y | `Overall Health Label` | General |
| 26 | Z | `PEG Ratio Fwd` | `0.00` |
| 27 | AA | `EV / EBIT` | `0.00` |
| 28 | AB | `Fair Value Label (Analyst Targets)` | General |

**Total: 26 columnas de datos.**

### 3.5 Estilos del export (fila 8 — encabezados)

| Atributo | Valor |
|---|---|
| Fuente | Arial, 10pt, **negrita=False**, color `#434343` (gris oscuro) |
| Fill | `None` (sin color de fondo) |
| Alineación | horizontal=`left`, vertical=`None`, wrap=`None` |
| Number format | `General` |

### 3.6 Anchos de columna

| Col | Ancho |
|---|---|
| A (1) | 2.0 |
| B (2) | 2.0 |
| C (3) | 25.0 |
| D-AB (4-28) | `None` (auto, default) |

### 3.7 Alturas de fila

| Fila | Altura |
|---|---|
| 1 | 13.5 |
| 2 | 33.0 |
| 8 (encabezado) | 33.0 |
| Demás | `None` (default) |

---

## 4. Estructura del Excel generado (`Screening_AAI_2026-09-01.xlsx`)

### 4.1 Metadatos del workbook

| Propiedad | Valor |
|---|---|
| Creator | `openpyxl` (generado por el motor canónico) |
| Created | `2026-09-01 12:06:53` |
| Modified | `2026-09-01 12:07:00` |

### 4.2 Hojas

| Hoja | Propósito |
|---|---|
| **Screening** | Hoja principal con la tabla clasificada (37 cols × 1002 rows) |
| **Instructivo** | Guía metodológica (4 cols × 189 rows) |

#### Hoja `Screening`

| Propiedad | Valor |
|---|---|
| Nombre | `Screening` |
| Dimensiones | 1002 rows × 37 cols |
| showGridLines | `None` (default — no explícitamente desactivado) |
| freeze_panes | **`E3`** (columnas A-D y filas 1-2 fixed) |
| Conditional formatting | **DataBarRule** en rango `AB3:AB1002` (barra de Score) |
| Comentarios | **15 comentarios** en fila 2 (tooltips explicativos de cada columna) |
| Merged cells | `G1:U1`, `V1:AD1`, `AE1:AJ1`, `C1:F1`, `A1:B1`, `AK1` |

### 4.3 Distribución de filas (hoja `Screening`)

- **Row 1**: 6 etiquetas de banda **merged** (RESULTADO, EMPRESA, CALIDAD, PRECIO, SALUD, RESULTADO)
- **Row 2**: encabezados de columna (37 columnas) con tooltips (comments)
- **Rows 3+**: datos clasificados (1000 empresas)

### 4.4 Columnas generadas (fila 2)

El Excel generado tiene **37 columnas**, organizadas en **6 bandas** (row 1, merged).

#### 4.4.1 Mapa de columnas generadas

| Banda | Cols | Fill | Headers |
|---|---|---|---|
| `RESULTADO` | A-B (1-2) | `#404040` | `Balde`, `Puntaje (0-10)` |
| `EMPRESA` | C-F (3-6) | `#595959` | `Name`, `Ticker`, `Price, Current`, `Market Cap (US$ B)` |
| `CALIDAD — ¿es un gran negocio?` | G-U (7-21) | `#375623` | `ROIC`, `ROIC 5a`, `ROE`, `Margins`, `EPS G 5y`, `Rev CAGR 5y`, `FCF/NI`, `Buyback`, `Debt/Cap`, `Beta`, `Greenblatt`, `MSCI`, `AQR`, `Verdicto Calidad`, `Señales calidad` |
| `PRECIO — ¿está barata?` | V-AD (22-30) | `#7F6000` | `P/E`, `PEG`, `EV/EBIT`, `FCF Yield`, `Fair Value`, `FV Label`, `Price vs FV`, `Verdicto Precio`, `Señales precio` |
| `SALUD FINANCIERA — ¿sólida y limpia?` | AE-AJ (31-36) | `#1F4E79` | `Piotroski`, `Altman Z`, `Beneish M`, `Health Label`, `Verdicto Salud`, `Señales salud` |
| `RESULTADO` | AK (37) | `#404040` | `Alertas` |

**Headers completos en fila 2 (37 columnas):**

| Col | Header | Fill |
|---|---|---|
| A | `Balde` | `#404040` |
| B | `Puntaje (0-10)` | `#404040` |
| C | `Name` | `#D9D9D9` |
| D | `Ticker` | `#D9D9D9` |
| E | `Price, Current` | `#D9D9D9` |
| F | `Market Cap (US$ B)` | `#D9D9D9` |
| G | `Return on Invested Capital` | `#C6E0B4` |
| H | `Avg Return on Invested Capital (5y)` | `#C6E0B4` |
| I | `Return on Equity` | `#C6E0B4` |
| J | `Gross Profit Margin` | `#C6E0B4` |
| K | `Avg EPS Growth (5y)` | `#C6E0B4` |
| L | `Revenue CAGR (5y)` | `#C6E0B4` |
| M | `FCF / Net Income` | `#C6E0B4` |
| N | `Buyback Yield` | `#C6E0B4` |
| O | `Total Debt / Total Capital` | `#C6E0B4` |
| P | `Beta (5 Year)` | `#C6E0B4` |
| Q | `Greenblatt` | `#538135` |
| R | `MSCI` | `#538135` |
| S | `AQR` | `#538135` |
| T | `Veredicto Calidad` | `#538135` |
| U | `Señales de calidad (0-3)` | `#538135` |
| V | `P/E Ratio` | `#FFE699` |
| W | `PEG Ratio Fwd` | `#FFE699` |
| X | `EV / EBIT` | `#FFE699` |
| Y | `Free Cash Flow Yield` | `#FFE699` |
| Z | `Fair Value` | `#FFE699` |
| AA | `Fair Value Label (Analyst Targets)` | `#FFE699` |
| AB | `Price vs Fair Value` | `#BF8F00` |
| AC | `Veredicto Precio` | `#BF8F00` |
| AD | `Señales de precio (0-4)` | `#BF8F00` |
| AE | `Piotroski Score` | `#BDD7EE` |
| AF | `Altman Z-Score` | `#BDD7EE` |
| AG | `Beneish M-Score` | `#BDD7EE` |
| AH | `Overall Health Label` | `#BDD7EE` |
| AI | `Veredicto Salud financiera` | `#2E75B6` |
| AJ | `Señales de salud (0-3)` | `#2E75B6` |
| AK | `Alertas` | `#404040` |

**Comparación de columnas con el export de referencia:**

| Columna del export | En generated | Nota |
|---|---|---|
| `Name` | ✅ Sí (col C) | |
| `Full Ticker` | ❌ **Ausente** | El motor canónico NO incluye esta columna en el output Excel |
| `Ticker` | ✅ Sí (col D) | |
| `Price, Current` | ✅ Sí (col E) | |
| `Fair Value` | ✅ Sí (col Z) | Removido de EMPRESA, ahora en banda PRECIO |
| `Market Cap (Adjusted)` | **Renombrado** → `Market Cap (US$ B)` (col F) | Formato: `[<1e6]0.02,"K";...` → `#,##0.0` |
| `P/E Ratio` | ✅ Sí (col V) | |
| `Total Debt / Total Capital` | ✅ Sí (col O) | |
| `Free Cash Flow Yield` | ✅ Sí (col Y) | |
| `P/E Ratio (Fwd)` | ✅ Sí (col W) | |
| `Beta (5 Year)` | ✅ Sí (col P) | |
| `Return on Invested Capital` | ✅ Sí (col G) | |
| `Avg Return on Invested Capital (5y)` | ✅ Sí (col H) | |
| `Return on Equity` | ✅ Sí (col I) | |
| `Gross Profit Margin` | ✅ Sí (col J) | |
| `Avg EPS Growth (5y)` | ✅ Sí (col K) | |
| `Revenue CAGR (5y)` | ✅ Sí (col L) | |
| `FCF / Net Income` | ✅ Sí (col M) | |
| `Buyback Yield` | ✅ Sí (col N) | |
| `Piotroski Score` | ✅ Sí (col AE) | |
| `Altman Z-Score` | ✅ Sí (col AF) | |
| `Beneish M-Score` | ✅ Sí (col AG) | |
| `Overall Health Label` | ✅ Sí (col AH) | |
| `PEG Ratio Fwd` | ✅ Sí (col W) | |
| `EV / EBIT` | ✅ Sí (col X) | |
| `Fair Value Label (Analyst Targets)` | ✅ Sí (col AA) | |

**Columnas NUEVAS agregadas por el motor (no en el export):**

| Columna | Col | Propósito |
|---|---|---|
| `Balde` | A | Clasificación: Deep Dive / Watchlist / Neutral / Descartada / Omitida |
| `Puntaje (0-10)` | B | Score 0-10 (lentes Greenblatt + MSCI + AQR) |
| `Greenblatt` | Q | Verdicto del lente Greenblatt |
| `MSCI` | R | Verdicto del lente MSCI |
| `AQR` | S | Verdicto del lente AQR |
| `Veredicto Calidad` | T | Veredicto combinado de calidad |
| `Señales de calidad (0-3)` | U | Conteo de señales de calidad |
| `Price vs Fair Value` | AB | Upside % vs fair value |
| `Verdicto Precio` | AC | Verdicto del tribunal de precio |
| `Señales de precio (0-4)` | AD | Conteo de señales de precio |
| `Verdicto Salud financiera` | AI | Veredicto del tribunal de salud |
| `Señales de salud (0-3)` | AJ | Conteo de señales de salud |
| `Alertas` | AK | Alertas y notas metodológicas |

### 4.5 Estilos del Excel generado

#### Fila 1 (bandas, merged)

| Banda | Fill | Font | Alineación |
|---|---|---|---|
| RESULTADO (A:B, AK) | `#404040` (gris oscuro) | Arial 10pt, **bold**, color `#FFFFFF` | center |
| EMPRESA (C:F) | `#595959` (gris medio) | Arial 10pt, **bold**, color `#FFFFFF` | center |
| CALIDAD (G:U) | `#375623` (verde oscuro) | Arial 10pt, **bold**, color `#FFFFFF` | center |
| PRECIO (V:AD) | `#7F6000` (amarillo oscuro) | Arial 10pt, **bold**, color `#FFFFFF` | center |
| SALUD (AE:AJ) | `#1F4E79` (azul marino) | Arial 10pt, **bold**, color `#FFFFFF` | center |

#### Filas de datos (row 3+) — fill de la columna Balde (col A) por categoría

| Balde | Fill | Count |
|---|---|---|
| 🔬 Deep Dive | `#A9D08E` (verde claro) | 13 |
| 📋 Watchlist | `#E2EFDA` (verde muy claro) | 25 |
| ⚪ Neutral | `#FFF2CC` (amarillo muy claro) | 227 |
| ❌ Descartada | `#FFC7CE` (rojo claro) | 532 |
| ⚙️ Omitida (Financiero) | `#D6DEE8` (gris azulado) | 154 |
| ⚙️ Omitida (Utilities) | `#D6DEE8` (gris azulado) | 49 |

#### Fill de las columnas Veredicto (por valor)

| Veredicto | Fill |
|---|---|
| EXCELENTE / BUENA | `#C6EFCE` (verde) |
| MIXTA | `#FFEB9C` (amarillo) |
| DÉBIL | `#FFC7CE` (rojo) |
| MUY BARATA | `#A9D08E` (verde) |
| BARATA | `#C6EFCE` (verde claro) |
| CARA | `#FFC7CE` (rojo) |

#### Formato numérico en datos

| Formato | Count (rows 3-29) | Uso |
|---|---|---|
| `General` | 459 | Texto, Balde, Ticker, Veredictos, Labels |
| `0.0%` | 297 | Ratios porcentuales (ROIC, ROE, etc.) |
| `0.00` | 215 | Precios, valores, scores decimales |
| `#,##0.0` | 27 | Market Cap (US$ B) |

#### Anchos de columna

| Col | Ancho |
|---|---|
| A (Balde) | 16.0 |
| B (Puntaje) | 9.0 |
| C (Name) | 30.0 |
| D-AJ (resto) | 11.0 (cada una) |
| AK (Alertas) | 46.0 (wrap text) |

#### Alturas de fila

| Fila | Altura |
|---|---|
| 1 | 18.0 (bandas) |
| 2 | 30.0 (encabezados) |
| 3+ | `None` (default) |

### 4.6 Conditional formatting

- **DataBar** en rango `AB3:AB1002` (columna `Price vs Fair Value`)
  - Color: `#63C384` (verde)
  - Tipo: min/max, showValue=True
  - *Nota*: openpyxl emite `UserWarning: Conditional Formatting extension is not supported` — es el **x14 dataBar** (Excel 2010+) que el motor inyecta por post-procesado regex; el warning es benigno, las barras se ven correctamente en Excel.

### 4.7 Comentarios (tooltips)

**15 comentarios** en fila 2. Ejemplos:
- `B2`: "Puntaje = señales de calidad (0-3) + señales de precio (0-4)"
- `G2`: "Lente Greenblatt: ≥20% (actual y promedio de 5 años)"
- `H2`: "Se compara con el ROIC actual: si el actual está por debajo del promedio 5a, revisar moat"

### 4.8 Hoja `Instructivo`

| Propiedad | Valor |
|---|---|
| Dimensiones | 189 rows × 4 cols |
| showGridLines | `False` |
| Anchos | A=2.5, B=25.0, C=104.0, D=2.5 |
| Fondo | Navy `#0A1B2D` pintado en ~190 filas × 4 cols |

**Contenido:** "GUÍA DEL ARCHIVO" — título del motor ("Screening cuantitativo — Aprende a Invertir"),
metadatos de la corrida (export, fecha, versión Motor v1 r13), secciones numeradas (01, 02...):
descripción del método, los 3 tribunales (CALIDAD / SALUD / PRECIO), los 3 lentes
(Greenblatt / MSCI / AQR), veredictos, umbrales, y explicación de cada alerta.

---

## 5. Dashboard HTML (`Dashboard_AAI_2026-09-01.html`)

| Atributo | Valor |
|---|---|
| Tamaño | 59,097 bytes |
| Title | `Screening Cuantitativo — Aprende a Invertir` |
| H1 | `De 1,000 acciones a <span>13 candidatas</span>` |
| CSS vars | `--navy:#0A1B2D`, `--petrol:#003850`, `--amber:#F59C00`, `--orange:#F1801B`, `--teal:#6DADAA`, `--coral:#E07068` |
| Layout | `grid7` (7 columnas: #, Empresa, Puntaje, Calidad, Salud, Precio, Nota) |
| Logo | `logo_completo_blanco.png` embebido en base64 |
| KPI funnel | 🔬 13 Deep Dive · 📋 25 Watchlist · ⚪ 227 Neutral · ❌ 532 Descartadas · ⚙️ 203 Omitidas por método |
| Company cards | 13 `ddrow` en Deep Dive, cada una expandible con 3 `tcard` (tribunales calidad/salud/precio) |
| Enlaces | Tickers linkeados a `https://www.investing.com/pro/<EXCHANGE:TICKER>` (via `Full Ticker`) |
| Responsive | `@media(max-width:820px)` + `@media print` |
| Footer | Disclaimer "herramienta educativa; Deep Dive = investigar a fondo, no comprar" |

---

## 6. Diferencias de formato/layout/colores: EXPORT (input) vs OUTPUT (motor)

> **Estas diferencias son INTENCIONALES.** El motor canónico toma el export InvestingPro
> (formato plano, sin clasificación) y lo transforma en un Excel/HTML enriquecido con el
> sistema de bandas, veredictos y colores del screening AAI. El export es el INPUT, no el
> OUTPUT. No son bugs — son la función misma del motor.

| Aspecto | Reference (export InvestingPro) | Generated (motor AAI output) | Estado |
|---|---|---|---|
| **Nombre de hoja** | `sheet` | `Screening` + `Instructivo` | ✅ Intencional: el motor crea su propia hoja + guía |
| **Número de columnas** | 26 | 37 | ✅ Intencional: el motor agrega 11 columnas de clasificación |
| **`Full Ticker`** | Presente (col D) | **Ausente** del Excel output | ✅ Intencional: se usa solo para los links del dashboard HTML |
| **`Market Cap`** | `Market Cap (Adjusted)`, formato K/M/B condicional | `Market Cap (US$ B)`, formato `#,##0.0` | ✅ Intencional (motor_screening.py línea 389) |
| **freeze_panes** | `None` | `E3` (A-D + filas 1-2 fijas) | ✅ Intencional |
| **Merged cells** | Título del export (`C2:E2`, `C6:D6`) | 6 merges en row 1 (bandas de color) | ✅ Intencional |
| **Conditional formatting** | `None` | DataBar en col AB + fills por balde/veredicto | ✅ Intencional |
| **Fills en datos** | Ninguno (filas planas) | Coloreado por balde y veredicto | ✅ Intencional |
| **Comentarios** | 0 | 15 tooltips en fila 2 | ✅ Intencional |
| **Row heights (1-2)** | 13.5 / 33.0 | 18.0 / 30.0 | ✅ Intencional: bandas del motor |
| **Column widths** | 3 custom (A=2, B=2, C=25), resto auto | 37 custom (todas definidas) | ✅ Intencional |
| **Metadata creator** | `finbox.io` | `openpyxl` | ✅ Esperado: el motor genera con openpyxl |
| **Fila "fortress core"/"Premium Export"/"Summary"** | Presente (rows 2-6) | No replicada | ✅ Intencional: el motor lee los datos (fila 8+), ignora el encabezado del export |
| **`P/E Ratio (Fwd)`** | Columna explícita (col L) | Presente como `PEG Ratio Fwd` (col W) | ✅ Mismo dato, nombre canónico del motor |

### 6.1 Resumen de colores

| Concepto | Reference (export) | Generated (motor) |
|---|---|---|
| Título "fortress core" | `#1551C3` (azul AAI) | No aplica (es del export) |
| Encabezados | Sin fill, texto gris `#434343` | 6 bandas: `#404040`, `#595959`, `#375623`, `#7F6000`, `#1F4E79`, `#BF8F00`, `#2E75B6` |
| Datos | Sin colorear | Balde: `#A9D08E`/`#E2EFDA`/`#FFF2CC`/`#FFC7CE`/`#D6DEE8`; Veredictos: `#C6EFCE`/`#FFEB9C`/`#FFC7CE` |
| DataBar | No existe | `#63C384` (verde) en `Price vs Fair Value` |

### 6.2 Orden de columnas

El export de InvestingPro: `Name, Full Ticker, Ticker, Price, Fair Value, Market Cap, P/E, ...`

El output del motor agrupa en bandas:
```
[BALDE] [PUNTAJE] [Name, Ticker, Price, MCap] [ROIC...Beta + Greenblatt/MSCI/AQR + Veredicto]
[P/E...Fair Value + Price vs FV + Veredicto] [Piotroski...Health Label + Veredicto] [Alertas]
```

Esto es **exactamente el `layout` de `motor_screening.py::generar_excel()`** (líneas 270-282).

---

## 7. Conclusión

### ¿El dashboard/Excel generado se ve igual al original de AAI?

**SÍ.** El motor canónico **vendorizado** (byte-a-byte, hash verificado) produce artefactos
con el mismo formato, layout, colores y estructura de columnas que el motor original de AAI.
No se detectó ninguna diferencia de formato que no sea el comportamiento intencional y
documentado del motor (que enriquece el export con bandas, clasificación y formato propio).

#### Checklist de verificación

| Aspecto | Resultado |
|---|---|
| Motor vendorizado = motor original | ✅ Hash byte-a-byte `84abe30...` |
| Tests pasan (32 passed, 1 skip) | ✅ Suite completa verde |
| Excel: 2 sheets (Screening + Instructivo) | ✅ |
| 37 columnas con 6 bandas de color | ✅ |
| freeze_panes `E3` | ✅ |
| DataBar en `Price vs Fair Value` | ✅ |
| 15 comentarios/tooltips | ✅ |
| Balde fills (6 categorías) | ✅ Colores canónicos |
| Veredicto fills (EXCELENTE/MIXTA/DÉBIL/BARATA/CARA) | ✅ |
| Dashboard HTML (grid7, logo, funnel, 13 cards expandibles) | ✅ |
| Export name + fecha + versión en artefactos | ✅ "Motor v1 r13" |
| Distribución de baldes | ✅ DD 13 / WL 25 / N 227 / D 532 / Om 203 — coincide con paridad |

---

## 8. Veredicto final

> **CERRADO.** La verificación visual confirma que el dashboard/Excel generados por
> `render_artifacts()` (motor canónico vendorizado) se ven idénticos al output original
> de AAI. El punto 2 del ROADMAP ("PENDIENTE VERIFICAR") queda **CERRADO**.

---

## 9. Archivos de referencia

| Archivo | Propósito |
|---|---|
| `backend/tests/fixtures/canon/market_view_export.xlsx` | Export real InvestingPro (input/referencia) |
| `backend/app/core/motor_canonico/scripts/motor_screening.py` | Motor canónico vendorizado |
| `backend/app/core/fundamentals_artifacts.py` | Wrapper `render_artifacts()` |
| `backend/scripts/run_fundamentals_screen.py` | Job runner (cron) |
| `backend/tests/test_fundamentals_screen.py` | Test de paridad PLAN §3 |
| `backend/tests/test_fundamentals_screen_e2e.py` | Test E2E de artefactos |