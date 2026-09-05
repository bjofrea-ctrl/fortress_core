# COMPARACIÓN DE FUENTES DE DATOS — Confiabilidad para backtest

**Fecha**: 2026-09-03 · **Autor**: OpenCode (worktree `test-opencode-orca`) · **Alcance**: solo lectura/análisis. No se tocó ledger, pre-registro, ni código. Los caches NO se modificaron (las descargas de verificación corrieron solo en memoria).

**Pregunta de Boris**: ¿son confiables las 4 fuentes (yfinance diario, Alpaca intradía, Finnhub y FMP fundamentales) tal cual están para backtest, o los trials pasados podrían estar contaminados por mala calidad de dato? ¿Hace falta el harness de reconciliación cruzada (idea GLM, no implementada)?

**Respuesta corta**: yfinance NO es confiable tal cual está — pero no (solo) por el reajuste retroactivo que sospechabas, sino por un defecto mayor encontrado durante esta verificación: **38 barras diarias completas de OTROS símbolos están pegadas en 29 parquets del cache** (retornos diarios falsos de ±20% a +623%), congeladas ahí desde el 24-ago. Los trials con ventana estándar W3 (hasta 2026-08-04) NO consumieron barras contaminadas; el daño está latente para cualquier análisis que corra desde hoy con "todo el cache". **El harness de reconciliación no es opcional: es urgente**, y mientras no exista, ningún backtest debería cruzar el tramo 2026-08-24 → 2026-09-02 sin saneo previo.

---

## 1. Resumen ejecutivo — veredicto por fuente

| Fuente | Uso | ¿Confiable para backtest tal cual? | Defectos verificados (evidencia §) |
|---|---|---|---|
| **yfinance** (diario, 102 símbolos) | OHLCV 2015→hoy, motor de señales, todos los trials | **NO** | (a) Reajuste retroactivo confirmado (§2) · (b) **Contaminación cruzada: 38 barras de otros símbolos en 29 archivos** (§3) · (c) Mosaico interno de bases: 7 archivos con 2 bases mezcladas (§4) · (d) 64 huecos in-range jamás reparados (§6) |
| **Splits/corporate actions** | ídem | **SÍ** (ya verificado H5.1) | Cita ROADMAP, sin repetición (§5) |
| **Alpaca intradía** (IEX, 1-min, 7 símbolos) | Colector nuevo, medición de costos paper | **PARCIAL** — precio sí, volumen NO | Precio cierre 1-min vs consolidado: mediana <7bp (§7.2). Volumen IEX = 1.5–3.8% del consolidado (§7.1). Retención ~7 días sin backfill (§7.3) |
| **Finnhub** (fundamentals) | Cruce opcional no-bloqueante | **NO EVALUABLE** | Nunca produjo datos: cache inexistente, mapeo FIELD_MAP nunca validado contra key real (§8) |
| **FMP** (fundamentals) | Fuente primaria incondicional | **NO EVALUABLE** | Cache de ingesta: 0 archivos. Screening 2026-09-02: 102/102 FAILED. Hoy: HTTP 429 "Limit Reach" (§8) |

**Conclusión harness**: hace falta, sí — pero **la especificación cambió** respecto de la idea original de GLM (reconciliación *entre* fuentes). El defecto más grave no es divergencia entre fuentes: es **corrupción dentro de una sola fuente** (yfinance) congelada por el diseño append-only del cache. El harness mínimo debe validar el cache contra una descarga fresca del propio yfinance (detección de contaminación + mosaico + huecos), además del cross-check Finnhub↔FMP cuando FMP tenga datos (§10).

---

## 2. yfinance — Hallazgo 1: reajuste retroactivo CONFIRMADO (el hallazgo de Boris era correcto)

### 2.1 Método

Comparación de **tres momentos** del mismo dato:
- **Snapshot A**: `~/Desktop/fortress_core/data/cache/` (60 parquets, mtime 2026-08-21 21:43, contenido mayormente hasta 2023-12-29 + algunos hasta 2026-08-11).
- **Snapshot B**: `backend/data/cache/` (102 parquets, escritura masiva 2026-09-02 12:10/12:11, contenido hasta 2026-09-01).
- **Snapshot C**: descarga fresca de Yahoo HOY 2026-09-03 (`yf.download` con los mismos parámetros que `data_ingestion.py`, solo en memoria).

No existe comparabilidad por git (los parquets están en `.gitignore:36` `*.parquet` — `git log --all -- "*.parquet"` es vacío) ni por backup (Time Machine ausente; espejo EMPRESA sin parquets). A y B son los únicos snapshots históricos disponibles.

### 2.2 Resultado A vs B (60 símbolos comunes, rango solapado)

| Resultado | Símbolos | Detalle |
|---|---|---|
| **Idénticos** (0 días con diff >1e-6) | **11** | ADBE, AMD, AMZN, BRK-B, DX-Y.NYB, GC=F, GLD, SI=F, TSLA, ^VIX, NFLX — todos **sin dividendos** entre el 21-ago y el 2-sep (o series sin ajuste: FX/futuros/VIX) |
| **Paso proporcional** (toda la historia pasada multiplicada por un factor constante) | **11** | AAPL ×1.000862 · AGG ×1.003483 · AMGN ×1.005844 · CVX ×1.008727 · IBM ×1.007173 · LLY ×1.001433 · TIP ×1.007338 · TLT ×1.004028 · V ×1.001858 · WMT ×1.002394 · XOM ×1.006475 |
| Micro-ruido (±1bp en 63–82% de los días, sin estructura) | 38 | Jitter de re-serialización de Yahoo entre descargas — irrelevante para backtest |

Ejemplo crudo (CVX, tres fechas del rango común):

```
2016-01-04: A=56.3499  B=56.8417  B/A=1.0087270
2020-06-01: A=70.9070  B=71.5258  B/A=1.0087270
2023-12-29: A=132.9515 B=134.1118 B/A=1.0087271
```

El factor 1.008727 coincide con el dividendo de CVX ex-date 2026-08-19 (**$1.78 / ~$206 ≈ 0.86–0.87%**) — idéntico mecanismo en los otros 10 símbolos (AAPL: $0.27 ex 2026-08-10 → 0.086%).

### 2.3 Resultado C vs B (fresco hoy vs cache de ayer)

- **AAPL**: ratio C/B = **0.999138 constante en todos los años (2015→2026)**. El dividendo del 10-ago fue re-ajustado por Yahoo HOY a TODO el historial; el cache B solo lo incorporó en las filas post-2026-08-05. → **El reajuste retroactivo es continuo: cada dividendo nuevo re-escribe el pasado completo en cada descarga.**
- KO/CVX últimas 1-2 barras con ratio ~0.34-0.35: **no es reajuste** — es el hallazgo 2 (§3): esas barras del cache son de otros símbolos.

### 2.4 Implicación para backtest

1. **Reproducibilidad**: dos backtests del mismo símbolo corridos en fechas distintas usan bases de reajuste distintas → los retornos históricos difieren hasta ~0.9%/año acumulado por dividendo (CVX paga ~3.5%/año: un backtest de CVX corrido hoy vs hace 6 meses difiere sistemáticamente en TODO el tramo en proporción a los dividendos cobrados en el medio). Ningún veredicto cuantitativo fino (décimas de Sharpe) es reproducible bit a bit.
2. **Dentro de un solo archivo consistente** el reajuste NO deforma retornos (el factor constante se cancela en el ratio de precios). El problema es cuando el archivo NO es consistente → hallazgo 3 (§4, mosaico).
3. `data_ingestion.py` usa `yf.download(...)` **sin** `auto_adjust` explícito → default `auto_adjust=True` de yfinance 1.2.0 (verificado en el sitio del venv). No es un bug de configuración (H5.1 ya lo cerró); es el comportamiento nativo de la fuente.

---

## 3. yfinance — Hallazgo 2 (NO pedido, MAYOR): contaminación cruzada de barras entre símbolos

Durante la verificación del punto 1 apareieron retornos diarios imposibles (±20% a +623% en large-caps). La causa no es reajuste: son **barras OHLCV completas de otros símbolos escritas en archivos equivocados**.

### 3.1 Evidencia cruda — las 38 barras confirmadas

Criterio de confirmación: la barra del cache matchea en **Open, High, Low, Close (<0.1%) Y Volume (<1%)** a la barra real de OTRO símbolo ese mismo día (descarga fresca de hoy como referencia). Coincidencia de Close solo no cuenta (141 barras quedaron en "coincidencia casual" — son base stale del mosaico con precios redondos parecidos).

| Fecha | Símbolo contaminado | Barra real que contiene |
|---|---|---|
| 2026-08-24 | INTU | GE |
| 2026-08-24 | LIN | IBM |
| 2026-08-24 | QCOM | LIN |
| 2026-08-25 | INTU | GE |
| 2026-08-25 | LIN | IBM |
| 2026-08-25 | QCOM | LIN |
| 2026-08-26 | AMGN | CAT |
| 2026-08-26 | CAT | TXN |
| 2026-08-26 | CMCSA | PM |
| 2026-08-26 | DIS | CMCSA |
| 2026-08-26 | GE | QCOM |
| 2026-08-26 | INTU | GE |
| 2026-08-26 | LIN | IBM |
| 2026-08-26 | PM | INTU |
| 2026-08-26 | QCOM | LIN |
| 2026-08-26 | TXN | DIS |
| 2026-08-31 | ABBV | JNJ |
| 2026-08-31 | BAC | ABBV |
| 2026-08-31 | COST | PG |
| 2026-08-31 | CRM | MRK |
| 2026-08-31 | HD | COST |
| 2026-08-31 | JNJ | HD |
| 2026-08-31 | KO | CRM |
| 2026-08-31 | MA | XOM |
| 2026-08-31 | MRK | BAC |
| 2026-08-31 | ORCL | MA |
| 2026-08-31 | PG | ORCL |
| 2026-08-31 | XOM | UNH |
| 2026-09-01 | ACN | CSCO |
| 2026-09-01 | ADBE | KO |
| 2026-09-01 | CRM | COST |
| 2026-09-01 | CSCO | CVX |
| 2026-09-01 | CVX | TMO |
| 2026-09-01 | IBM | MCD |
| 2026-09-01 | KO | CRM |
| 2026-09-01 | LIN | IBM |
| 2026-09-01 | MCD | ACN |
| 2026-09-01 | TMO | NFLX |

3 clusters: **24-26/ago** (16 barras), **31/ago** (12), **1/sep** (10). La estructura en cadena (KO←CRM, CRM←COST, COST←PG, PG←ORCL, ORCL←MA, MA←XOM, XOM←UNH...) es consistente con responses desplazadas entre requests consecutivos del updater — el mecanismo interno exacto del lado Yahoo/CDN no es probable desde acá; lo observable y verificable es qué entró y cuándo.

### 3.2 Daño cuantificado

Cada barra contaminada genera hasta 2 retornos diarios falsos (el día contaminado y el siguiente, al volver al precio real). Retornos falsos medidos en el cache (ejemplos crudos):

```
CMCSA 2026-08-26  +622.9%   (Close 26.85 -> 194.10 = barra de PM)
BAC   2026-08-31  +311.5%   (62.32 -> 256.42 = barra de ABBV)
CRM   2026-09-01  +536.1%   (147.76 -> 939.96 = barra de COST)
COST  2026-09-01  +547.7%
KO    2026-08-31  +187.2%   (89.66 -> 257.54 = barra de CRM)
XOM   2026-08-31  +148.5% / 2026-09-01 -57.7%
... (~50 retornos falsos >±20% en total)
```

**Cualquier señal que consuma retornos (momentum, vol, IC, labeling, ATR, sizing) queda invalidada en esos 29 símbolos si su ventana cruza el tramo 24-ago → 1-sep.** El motor de señales del backend (y el pipeline diario del advisor) leen estos parquets hoy.

### 3.3 Smoking gun del mecanismo en el log del updater

`scripts/data_updater.log` — backfills que pidieron **2015** y devolvieron filas fechadas **hoy** (27 casos):

```
1604: [data_ingestion] PM backfill: refreshed 1 rows (2026-08-26 -> 2026-08-26, cache now 2015-01-02 -> 2026-08-26)
       (PM venía de: backfill: gap 1d (cache 2015-01-02 > start 2015-01-01), attempting download 2015-01-01 -> 2015-01-02)
1609: CMCSA backfill: refreshed 1 rows (2026-08-26 -> ...)
1614: DIS  backfill: refreshed 1 rows (2026-08-26 -> ...)
1619: TXN  backfill: refreshed 1 rows (2026-08-26 -> ...)
1624: CAT  backfill: refreshed 1 rows (2026-08-26 -> ...)
3907: XOM  backfill: refreshed 1 rows (2026-08-31 -> ...)
3980: MA   backfill: refreshed 1 rows (2026-08-31 -> ...)
```

Un `yf.download(ticker, start="2015-01-01", end="2015-01-02")` devolvió una barra fechada 2026-08-26 con el OHLCV de otro símbolo. La barra pasa el dedup por índice (`data_ingestion.py:68,109` — `new_rows = old[~old.index.isin(df.index)]`: la fecha "hoy" no existe en el cache que llega hasta ayer) y queda concatenada para siempre.

### 3.4 Por qué el cache la congela y jamás la repara

`data_ingestion.py` es **append-only**: el refresh solo pide desde `last_date` (línea 99) y concatena filas nuevas (116); nunca re-descarga ni re-escribe filas viejas. Una vez escrita, la barra contaminada es indeleble: los runs siguientes piden solo el extremo derecho. Además las 38 barras quedaron además congeladas en la re-descarga masiva del 2-sep 12:10 (los parquets se regeneraron desde un Yahoo que ya servía la data mala, o se conservaron los mosaicos — mtimes 12:10/12:11 con contenido contaminado verificado).

---

## 4. yfinance — Hallazgo 3: mosaico interno (bases de reajuste mezcladas DENTRO de un mismo archivo)

Consecuencia local de §2 + append-only: las filas viejas quedan en la base de reajuste del día que se descargaron; las filas nuevas en la de hoy. Medido como plateaus del ratio cache/fresco-hoy (2024→hoy, runs ≥10 días):

| Símbolo | Seams (fecha donde cambia la base) | Niveles ratio cache/fresco |
|---|---|---|
| AAPL | 2026-08-05 | 1.00086 → 1.0 |
| CVX | 2026-08-17, 2026-09-01 | 1.00873 → 1.0 → 2.845 (el 2.845 es la barra contaminada §3, no base) |
| IBM | 2026-08-10, 2026-09-01 | 1.00717 → 1.0 → 1.128 (ídem, contaminación) |
| LLY | 2026-08-10 | 1.00143 → 1.0 |
| MSFT | 2026-08-17 | 1.00188 → 1.0 |
| V | 2026-08-10 | 1.00186 → 1.0 |
| WMT | 2026-08-17 | 1.00239 → 1.0 |

**95/102 archivos son homogéneos** (1 sola base — porque fueron re-descargados completos el 1-2/septiembre, o no tienen dividendos recientes). Los 7 mosaicos introducen **un retorno diario falso del tamaño del dividendo** en la fecha del seam (AAPL: +0.086% artificial el 2026-08-05; WMT: +0.24%; CVX: +0.87% el 17-ago). Pequeño pero sistemático, y **exactamente en fechas que los trials W3 (corte 2026-08-04) no tocan — por un margen de 1 a 13 días**.

Detalle factual llamativo: el seam de AAPL es 2026-08-05 y el corte W3 estándar de los trials es 2026-08-04. Un día de diferencia.

---

## 5. Splits / corporate actions — cita del hallazgo existente (H5.1, no repetido)

Ya verificado y cerrado (ROADMAP.md:632, auditoría GLM 2026-08-25): **4 splits reales** (AAPL 4:1, NVDA 10:1, GOOGL 20:1, AVGO 10:1) sin saltos de precio, parquets sin columna "Adj Close" confirmando `auto_adjust=True` (default yfinance 1.2.0) — **no es un bug**. Esta tarea no repite esa verificación; los resultados de §2-§4 son consistentes con ella (el mecanismo auto_adjust es el que produce el reajuste retroactivo de dividendos).

---

## 6. Huecos reales en el cache de 102 símbolos (punto 5 del pedido)

Método: calendario de referencia = SPY (2933 días, 2015-01-02 → 2026-09-01); hueco = fecha del rango propio del símbolo presente en SPY pero ausente en el parquet. Sin relleno artificial (verificado: 0 `ffill/bfill/interpolate/fillna` en `data_ingestion.py`) — bien, como se había constatado hoy.

| Métrica | Valor |
|---|---|
| Símbolos del universo 102 con parquet | 102/102 (USB y VZ NO faltan: no están en el universo declarado — confusión inicial mía con una lista hardcodeada; el universo real es NEW_UNIVERSE 95 + 7 BASE) |
| **Símbolos con ≥1 hueco in-range** | **57/102** |
| **Total de huecos** | **64** |
| Cluster 1: 2026-08-28 (viernes, día de mercado — verificado en SPY) | **50 símbolos** × 1 hueco (todo el bloque expandido de sept: AKAM, ALGN, AMAT, AXP, BIIB, BLK, BR, CDNS, CHKP, CHTR, DE, DLR, DRI, DXCM, EBAY, EPAM, EQIX, ETN, FCX, FFIV, ISRG, LRCX, MAR, MPWR, NEM, OKE, PANW, PH, PLD, PTC, QLYS, QRVO, RCL, REGN, SBUX, SCHW, SLB, SNPS, STAG, SWKS, TMUS, TYL, UNP, UPS, VEEV, VLO, WELL, WM, XEL, ZTS) |
| Cluster 2: 2026-08-24 y 2026-08-25 (lunes/martes, días de mercado) | 7 símbolos × 2 huecos: AMGN, CAT, CMCSA, DIS, GE, PM, TXN |
| Futuros/FX (holidays de futuros ≠ equities) | DX-Y.NYB, GC=F, HG=F, SI=F: 3 c/u; CL=F: 2 |

Yahoo **sirve hoy** esas fechas (verificado con descarga fresca de AKAM/AMAT/AMGN: el 24, 25 y 28-ago están presentes). El hueco se produjo en el momento de la descarga original (returns vacíos silenciosos de yfinance esos días para esos símbolos) y **el diseño append-only jamás los repara**: el refresh solo pide desde `last_date` — una fecha intermedia perdida no se vuelve a pedir nunca (línea 99 de `data_ingestion.py`). Nota: el hueco 24-25/ago en esos 7 símbolos es la antesala del cluster de contaminación del 26-ago (§3): el updater del 26 pidió "desde 2026-08-21" y recibió la barra contaminada del 26.

---

## 7. Alpaca intradía (feed IEX) — punto 4 del pedido

Colector: `collect_intraday_1min.py:59` — `get_bars(..., timeframe="1Min", feed="iex", adjustment="raw")`, 7 símbolos BASE, append + dedup por timestamp, launchd cada 30 min. Estado: 7 parquets, 2026-08-26 → 2026-09-03, ~2 400-2 500 barras c/u.

### 7.1 Volumen IEX vs consolidado (medido, no asumido)

Suma de volumen 1-min IEX por día ÷ Volumen diario Yahoo (consolidado), 5 días solapados por símbolo:

| Símbolo | min | mediana | max |
|---|---|---|---|
| SPY | 0.031 | 0.034 | 0.038 |
| AAPL | 0.024 | 0.030 | 0.033 |
| AMZN | 0.028 | 0.032 | 0.035 |
| GOOGL | 0.018 | 0.028 | 0.037 |
| MSFT | 0.020 | 0.023 | 0.035 |
| NVDA | 0.022 | 0.026 | 0.029 |
| QQQ | 0.013 | 0.015 | 0.017 |

Confirma el rango ~1.5-3.8% (la cifra "2-3%" de DISENO_COLECTOR_INTRADIA.md §4 es correcta como orden de magnitud; QQQ queda incluso abajo).

### 7.2 Calidad de PRECIO IEX (lo que el feed gratis sí da bien)

Último close 1-min (16:59 ET) vs Close diario consolidado:

| Símbolo | mediana | max |
|---|---|---|
| AAPL | 0.037% | 0.092% |
| AMZN | 0.016% | 0.041% |
| GOOGL | 0.008% | 0.053% |
| MSFT | 0.027% | 0.067% |
| NVDA | 0.009% | 0.138% |
| QQQ | 0.067% | 0.181% |
| SPY | 0.035% | 0.049% |

**Precio: utilizable** (mediana < 7bp; el max 0.18% de QQQ es consistente con la última barra siendo el auction print del consolidado vs el último trade IEX). Sin contaminación detectada en 17 000+ barras (1 solo outlier NVDA: barra aislada 12:25 UTC del 27-ago con 100 shares — thin print IEX, no corrupción).

### 7.3 Implicaciones para el colector nuevo

1. **Precio intradía OK como proxy**; **volumen NO representativo**: el `volume` y `vwap` guardados son IEX-only. Cualquier feature de volumen (participation, volume-profile, VWAP como referencia de ejecución) está sesgada por diseño. Para la medición de costos paper está bien: Alpaca paper ejecuta contra el mismo feed IEX, así que el fill simulado y el precio observado son coherentes entre sí.
2. **Sin NBBO/spread real**: IEX no es el libro consolidado; nada de microestructura de spread.
3. **Retención ~7 días** (DISENO_COLECTOR §4): si el colector cae > 7 días, hueco irrecuperable — la ventana 2026-08-26→hoy ya es TODO el histórico disponible. No existe backfill intradía en free.
4. Para un backtest intradía futuro: requiere SIP (de pago, 1 línea: `feed="sip"`) o aceptar el sesgo documentado.

---

## 8. Finnhub vs FMP — punto 3 del pedido: la comparación NO SE PUEDE HACER con datos existentes

### 8.1 Estado real de los datos (verificado hoy)

| Artefacto | Estado |
|---|---|
| `backend/data/cache_fundamentals/` (FinnhubClient) | **No existe el directorio** — Finnhub nunca devolvió datos con key real |
| `backend/data/cache_fundamentals_ingestion/` (FMP) | **Existe, 0 archivos** — la ingesta nunca descargó nada |
| `cache_fundamentals_screen/state.json` (2026-09-02) | `completed: 0, failed: 102, calls_used: 0`, razón `ingestion_returned_none` en los 102 |
| `screen_2026-09-02.json` | `universe_size: 102, completed_count: 0, failed_count: 102` |
| Keys en `backend/.env` (mtime 30-ago 18:56) | `FINNHUB_API_KEY` len=40, `FMP_API_KEY` len=32 — **sí están presentes** (el screening falló con keys presentes, no ausentes) |

**No existe ni UN número solapado entre Finnhub y FMP para comparar.** La pregunta "¿dan los mismos números?" no tiene respuesta empírica posible: no hay datos.

### 8.2 Verificación en vivo (hoy 2026-09-03, cuota mínima: 3 símbolos × (1 Finnhub + 5 FMP))

- **Finnhub: HTTP 200, datos correctos** — `stock/metric?metric=all`: AAPL peTTM 34.36 / pbAnnual 50.98 / roeTTM 137.2 / epsGrowthTTMYoy 32.6 · MSFT peTTM 27.58 · KO peTTM 26.26. El endpoint y la key funcionan.
- **FMP: HTTP 429 "Limit Reach. Please upgrade your plan"** en los 15 intentos, incluso tras espera — cuota diaria del free tier agotada (no throttle transitorio). El screening de ayer consumió 0 calls (`calls_used: 0`), así que la cuota se quemó por otro lado o el límite es de plan.

### 8.3 Riesgos de diseño (lo que SÍ se puede afirmar)

1. **FMP es "primaria incondicional" y Finnhub NO es fallback** (`fundamentals_ingestion.py:26-27,284-295` — cruce opcional `_cross_unverified`, nunca bloqueante). Un 429 de FMP = cero fundamentales para todo el universo, que es exactamente lo que pasó el 2-sep.
2. **Desborde de cuota estructural**: un barrido completo del universo 102 son 102 × 5 endpoints = **510 calls > 250/día del free tier**. El cron nocturno de fundamentales no puede completar una pasada ni en el mejor día.
3. **El mapeo Finnhub nunca fue validado contra datos reales** (`fundamentals_client.py:6-10`; 4 de 15 campos del FIELD_MAP marcados "aproximado — revisar"; `verify_finnhub_mapping.py` existe pero nunca corrió — no hay artefacto de salida).
4. **Ningún trial pasado consumió fundamentales de FMP/Finnhub**: el motor de señales usa precios + EDGAR (el `get_fundamentals` sample hardcodeado de 6 tickers es de la ruta advisor, no de los trials de research, verificado con `rg` en `backend/scripts/`). **Los veredictos pasados NO están contaminados por estas dos fuentes** — simplemente nunca entraron al pipeline de backtest.

---

## 9. Impacto en trials pasados — ¿hubo contaminación de veredictos?

Cruzando cada análisis con las fechas de los 3 clusters de contaminación (24-26/ago, 31/ago, 1/sep) y los seams de mosaico (5-17/ago):

| Análisis (fecha corrida) | Ventana de datos consumida | ¿Consumió barras contaminadas? |
|---|---|---|
| RMT 8 factores (30-ago) | hasta 2026-08-04 | **NO** |
| Trial #21 asimetría (30-ago) | W3 hasta 2026-08-04 | **NO** |
| Screening palas A6.3 (28-ago) | W3 hasta 2026-08-04 | **NO** |
| PBO/CSCV §39 (22-ago) | hasta 2026-08-04 | **NO** |
| FDR Tarea L (19-ago) | t-stats existentes | **NO** |
| Diagnóstico heterogeneidad (1-sep) | cache hasta 2026-08-14 | **NO** |
| Ingeniería inversa por ticker (1-sep) | hasta 2026-08-31; tickers NVDA/EPAM/AAPL/QLYS | **NO** (ninguno de los 29 contaminados; AAPL es mosaico seam 5-ago → 1 retorno deformado +0.086% dentro de ventana 2y — despreciable para terciles de momentum pero no cero) |
| MAPEO_ESTADOS_HMM (2-sep) | hasta 2026-08-31; 9 tickers macro (SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG/^VIX) | **NO** (ninguno de los 29; nota: EFA/DBC/TIP/AGG stale hasta 2026-08-17 — incompletos, no corruptos) |
| **Pipeline diario, advisor, próximos trials** | **"todo el cache" desde hoy** | **SÍ — 29 series contienen barras falsas; 7 con seams; todo análisis que cruce 24-ago→1-sep queda invalidado en esos símbolos** |

**Conclusión: ningún veredicto registrado del ledger consumió barras contaminadas confirmadas.** La ventana W3 estándar (corte 2026-08-04) terminó 20 días antes del primer cluster. Es suerte calendárica, no diseño — el próximo trial que use el cache completo ya no la tiene.

El cache del worktree `test-kilo-orca` (donde corrió A6.3) tiene su propia contaminación (5 barras falsas el 21-ago en NFLX +490%, ORCL +309%, TSLA +59%, CRM, TMO) — pero el screening palas leyó precios hasta 2026-08-04, así que tampoco la consumió.

---

## 10. Veredicto final y especificación del harness

### 10.1 Por fuente

1. **yfinance diario — NO confiable tal cual está para backtest.** Cuatro defectos verificados (§2 reajuste, §3 contaminación, §4 mosaico, §6 huecos). Ninguno invalida los veredictos ya registrados (§9), pero invalida cualquier corrida futura que cruce el tramo 24-ago→1-sep con los 29 símbolos afectados, y degrada la reproducibilidad de todo backtest fino (décimas de Sharpe) por el reajuste continuo.
2. **Splits: confiables** (H5.1, cita).
3. **Alpaca IEX: precio confiable como proxy (mediana < 7bp), volumen NO representativo (1.5-3.8%), retención frágil (7 días).** Para su propósito actual (medición de costos paper contra el mismo feed) está bien. Para backtest intradía de features de volumen, no alcanza sin SIP.
4. **Finnhub: API viva y responde bien; sin datos históricos en el proyecto; mapeo sin validar.** FMP: API viva pero hoy sin cuota; 0 datos producidos; diseño con desborde de cuota estructural (510 > 250 calls/barrido). **Ninguna de las dos contaminó trials pasados** porque nunca entraron al pipeline.

### 10.2 ¿Hace falta el harness de reconciliación? SÍ — urgente, y con esta especificación mínima (derivada de los defectos medidos, no de opinión):

1. **Validador de sanidad de retornos** (barato, intradía-no, corre en segundos): flag de cualquier |retorno diario| > umbral por clase de símbolo (large-cap: 15-20%). **Habría atrapado las 38 barras el día que entraron** (24-ago), antes de congelarse.
2. **Reconciliación cache vs descarga fresca del MISMO yfinance** (muestra diaria rotativa o full): (a) detección de filas cuyo OHLCV matchea otro símbolo → bloqueo + re-descarga del archivo completo; (b) detección de mosaico (plateaus del ratio) → re-descarga completa del archivo; (c) detección de huecos intermedios → re-descarga del tramo. Hoy nada de esto existe: el refresh solo mira el extremo derecho.
3. **Freeze de snapshot por trial**: el pre-registro de cada trial debería registrar el hash del cache que consume (o copia congelada a un directorio del trial). Es la única defensa contra el reajuste retroactivo para reproducibilidad — hoy no existe ni git ni backup de parquets.
4. **Cross-check Finnhub↔FMP** cuando FMP produzca datos: comparar los campos solapados por símbolo/periodo, alertar divergencia sistemática. Hoy no es implementable (no hay datos), pero debe ser parte del harness cuando la ingesta arranque. Antes de eso: resolver el desborde de cuota (universo por mitades en días alternos, o cache 90-días con refresh incremental por rotación) y validar el FIELD_MAP con `verify_finnhub_mapping.py`.

### 10.3 Acción inmediata recomendada (no ejecutada — tarea de diagnóstico)

Antes del próximo trial: **saneo del cache** = re-descarga completa de los 29 símbolos contaminados (+ los 7 mosaicos y los 57 con huecos, o directamente los 102 con verificación post-escritura). El bug de fondo NO está en yfinance solo: está en el append-only de `data_ingestion.py` que congela y nunca repara. Ese es el fix de diseño que el harness del punto 2 formaliza.

---

## 11. Nota de reproducibilidad de este diagnóstico

- Snapshots usados: raíz `data/cache/` (21-ago 21:43) y `backend/data/cache/` (2-sep) — los únicos que existen; sin git (`*.parquet` en `.gitignore`), sin Time Machine, sin parquets en el espejo EMPRESA.
- Descargas de verificación: frescas de hoy 2026-09-03 (~102 símbolos × ventana 2026 + muestras puntuales), corriendo en memoria sin escribir los caches del repo.
- Versiones: yfinance 1.2.0, pandas 2.2.0, pyarrow 15.0.0, curl_cffi 0.13.0, Python 3.9.6 (venv real del backend).
- Scripts de análisis: temporales fuera del repo (`$TMPDIR/opencode/*.py`); los números de este doc salen de esas corridas y son re-ejecutables con los métodos descriptos en cada sección.
