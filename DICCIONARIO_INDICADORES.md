# Diccionario de indicadores — técnicos y fundamentales

**Qué es esto**: material de referencia, no un backlog de trials. Ningún indicador
de este documento se testea contra el motor solo por estar acá — para eso existe el
protocolo de la [regla añadida en `PLAN_LARGO_PLAZO.md`](PLAN_LARGO_PLAZO.md):
definir qué mide, verificar contra fuente primaria si se lo va a testear en serio, y
recién ahí pre-registrar. Este documento es el punto de partida para esa definición,
no un compromiso de evaluar los ~130 indicadores que contiene.

**Nota de calidad de fuente**: la mayoría de las entradas de abajo vienen de una
síntesis vía Perplexity sobre sitios agregadores (no papers primarios) — a
diferencia de `RESEARCH_PREDICTIVE_INDICATORS.md` (2026-08-05), que sí cita papers
peer-reviewed con effect size documentado para los indicadores que el motor
considera en serio (Momentum 12-1, RSI, MACD, SMA/EMA cross, Bollinger, ADX,
Volumen). Para cualquier indicador de acá que se vaya a pre-registrar de verdad,
repetir el paso de verificación contra fuente primaria (como se hizo con
KAMA/HMA/Supertrend/MACD/Bollinger, ver `PLAN_LARGO_PLAZO.md` Tarea M/N) — no
asumir que lo que sigue ya está verificado al nivel que exige un pre-registro.

Los marcadores `[web:NN]` originales de la respuesta de Perplexity se quitaron: no
resuelven a una URL sin la lista de fuentes numerada que no vino incluida, así que
dejarlos habría sido una cita falsa (parece verificable y no lo es).

---

## PARTE I — Técnicos (precio, tendencia, momentum, volatilidad)

### 1. Precio y tendencia

**Simple Moving Average (SMA)** — Media aritmética del cierre sobre ventana fija n.
Suaviza ruido, introduce retraso; a mayor n, más macro la tendencia. Rol: filtro de
régimen (precio > SMA200), evita operar contra la tendencia dominante.

**Exponential Moving Average (EMA)** — Media con ponderación exponencial decreciente.
Menos lag que SMA, base del MACD. Rol: medida central de impulso, cruces fast/slow.

**Weighted Moving Average (WMA)** — Peso lineal creciente hacia el presente. Más
rápida que SMA, menos que EMA corta. Rol: filtro de tendencia con sensibilidad
moderada.

**Hull Moving Average (HMA)** — Ver definición verificada (Alan Hull, 2005) en
`PLAN_LARGO_PLAZO.md` Tarea M — WMA(2×WMA(n/2)−WMA(n), √n), reduce lag. En cola de
evaluación real.

**Wilder Moving Average** — Suavizado de Welles Wilder, componente interno de
RSI/ATR/ADX. No se usa como señal independiente.

**Adaptive Moving Average (AMA/KAMA)** — Ver definición verificada (Perry Kaufman,
1972/1995) en `PLAN_LARGO_PLAZO.md` Tarea M — usa Efficiency Ratio. En cola.

**Moving Average Envelopes** — Bandas a % fijo sobre/bajo una MA. Soporte/resistencia
dinámica, señal de sobreextensión en penetraciones.

**Moving Average Ribbon / Rainbow MA** — Múltiples MAs de distintos períodos
simultáneas. Diagnóstico visual de régimen multi-horizonte, no trigger mecánico.

**Two/Three MA Crossover** — Cruce de MA rápida sobre lenta. Trend-following clásico,
edge modesto documentado en activos con tendencias largas (ver Brock/Lakonishok/
LeBaron 1992 en `RESEARCH_PREDICTIVE_INDICATORS.md`), lag inevitable.

**MACD** — Ver definición verificada (Gerald Appel, 1977) en `PLAN_LARGO_PLAZO.md`
Tarea N. En cola, con evidencia peer-reviewed ya existente (Chong & Ng 2008).

**MACD Histogram** — Diferencia MACD−señal. Mide aceleración/desaceleración,
timing fino, no factor separado.

**MACD Zero-Lag / MACD Rainbow** — Variantes que buscan reducir lag o exponer
múltiples horizontes. Sin el mismo respaldo que el MACD estándar — mayor riesgo de
sobreajuste si se testean, ninguna en cola.

**Price Rate of Change (ROC) / Momentum Indicator** — % (ROC) o diferencia (Momentum)
de precio vs n períodos atrás. Feature básica de momentum, distinta del "momentum
12-1" (Jegadeesh & Titman 1993) que sí usa el motor — este es el estándar
académicamente más fuerte, no ROC genérico.

**Trend Intensity Index** — Oscilador 0-100 de fuerza de tendencia relativa a una MA.
Filtro cuant de intensidad, no verificado contra fuente académica.

**Linear Regression (Line/Slope/Intercept), Time Series Forecast** — Recta de mínimos
cuadrados sobre ventana de precio; pendiente = factor de tendencia normalizable por
volatilidad. Uso más como insumo de modelo que señal directa.

**Detrended Price Oscillator (DPO)** — Elimina tendencia (vía MA) para resaltar
ciclos. Timing de reversión, no trend-following.

**Parabolic SAR** — Puntos de stop/reversión iterativos. Herramienta de trailing
stop más que predictor — comparable en rol a Supertrend/ATR trailing, no a un
factor de score.

**Ichimoku Kinko Hyo** — Sistema multi-línea (Tenkan/Kijun/Senkou/Chikou), mapa
integral de régimen. Complejo, sin verificación contra fuente académica.

**Supertrend** — Ver definición verificada (atribuido a Olivier Seban, ~2009, **sin
origen académico**) en `PLAN_LARGO_PLAZO.md` Tarea M. En cola, con el caveat de
menor respaldo que los demás.

**Pivot Points (clásicos, Camarilla, Woodie)** — Niveles desde high/low/close previos.
Zonas de reacción; feature de distancia a nivel, no señal direccional propia.

**Donchian Channel** — Banda de máximo/mínimo de n días. Core de sistemas de
breakout tipo Turtle — el que tiene evidencia histórica más citada de este grupo de
canales.

**Keltner Channel** — Canal EMA ± ATR. Más suave que Bollinger (usa ATR, no
desviación estándar) — mismo tipo de indicador de régimen/volatilidad que Bollinger,
mismo cuidado metodológico si se testea (no es factor direccional).

**High-Low Bands, ZigZag, Darvas Box** — Herramientas estructurales/visuales de
rango y swings. Ninguna es trigger mecánico aislado con evidencia fuerte.

**Smart Money Concepts (SMC): Order Blocks, Fair Value Gaps, BOS/CHoCH, Liquidity
Sweeps** — Detectores de estructura de mercado implementados en
`backend/app/core/market_structure.py` (T1.3, PLAN_INTEGRACION_INDICAGENT.md, 2026-08-20):
zones con estado (nivel top/bottom, mitigada/rellena o no) devueltas como "zona activa
más reciente", no series continuas por barra. **Order Block**: última vela opuesta a un
impulso de ≥3 velas con movimiento ≥0.3%; la zona es el cuerpo de esa vela. **Fair
Value Gap**: desbalance de 3 velas (low[i+1] > high[i-1] o inverso), zona abierta si el
precio no volvió. **BOS/CHoCH**: cierre rompiendo el último swing high/low; CHoCH si
la ruptura va contra la tendencia HH-HL/LH-LL. **Liquidity Sweep**: mecha que perfora
un swing pero cierra adentro (stop hunt), con confirmación de reclaim en 3 barras.
**Estado en el proyecto**: código verificado con 18 tests sintetizados + smoke real
(AAPL 2921 barras, 0.17 s), pero **NO es señal ni está integrado al motor** — para eso
requiere su propio trial pre-registrado con la disciplina del repo (regla no
negociable). Conceptualmente tomado de indicadores SMC de TradingView, sin respaldo peer-reviewed.

### 2. Momentum y osciladores

**RSI** — Ya usado y validado en el motor (IC=0.0322, ver `signal_engine.py`).
Wilder (1978), Chong & Ng (2008) — ⭐⭐⭐⭐ en `RESEARCH_PREDICTIVE_INDICATORS.md`.

**Stochastic Oscillator, Stochastic RSI, Williams %R** — Osciladores de posición
dentro del rango high-low. Muy sensibles, muchas señales — edge discreto, mejor
como confirmación que como factor aislado.

**CCI, Chande Momentum Oscillator, Ultimate Oscillator, TRIX, PMO, Awesome
Oscillator** — Familia de osciladores de momentum con variantes de suavizado.
Ninguno verificado contra paper académico en este proyecto — candidatos de baja
prioridad salvo evidencia nueva.

**Aroon (Up/Down/Oscillator)** — Días desde último máximo/mínimo. Detector de
inicio/fin de tendencia, filtro de régimen.

**ADX / DMI (+DI, −DI)** — Ya evaluado en el motor: gate mecánico (adx≥20), NO
señal (§25 walk-forward, refutado bajo Bonferroni). Wilder (1978), Kaminsky & Lo
(2014) — ⭐⭐⭐⭐ en `RESEARCH_PREDICTIVE_INDICATORS.md` como filtro, no como factor.

**Schaff Trend Cycle, Relative Vigor Index, Elder Ray/Impulse System, Force Index,
IMI, Choppiness Index, Psychological Line, VHF, Random Walk Index** — Indicadores
híbridos de tendencia/momentum/régimen, sin verificación en este proyecto.
Choppiness Index y VHF son conceptualmente similares al Efficiency Ratio de Kaufman
(ya en uso vía KAMA, Tarea M) — posible redundancia si se consideran después.

### 3. Volatilidad y bandas

**Average True Range (ATR)** — Ya en uso, para sizing de stops (2×/4×ATR), no como
señal direccional. Uso correcto ya validado por diseño del motor.

**ATR Trailing Stops** — Gestión de salidas basada en ATR, ya presente conceptualmente
en el diseño de stops del motor.

**Bollinger Bands, %B, Bandwidth** — Ver definición verificada (John Bollinger, 1983)
en `PLAN_LARGO_PLAZO.md` Tarea N — régimen de volatilidad, NO dirección. Bollinger
(1992), Lento/Gradojevic/Wright (2007) — ⭐⭐⭐, horizonte óptimo 1-2 semanas (más
corto que fwd_return_20d, ya incorporado al diseño de Tarea N).

**Standard Deviation, Historic Volatility** — Medidas base de volatilidad
estadística. No predicen signo, insumo de modelos de riesgo/sizing.

**Chaikin Volatility, Mass Index, STARC Bands** — Variantes de medición de rango/
volatilidad. Sin verificación académica en este proyecto.

**Prime Number Bands** — Advertencia explícita de la propia búsqueda: "más
curiosidad técnica que estándar de la industria... requiere extrema cautela para no
caer en numerología sin fundamento". Descartado — no entra en ninguna cola.

### 4. Flujo de órdenes y volumen (proxies desde OHLCV puro)

Sección agregada con los planes de integración (PLAN_INTEGRACION_INDICAGENT.md,
2026-08-20, Kilo Code). Estos NO son reales de tick — son PROXIES que aproximan
la dinámica de flujo de órdenes (OFI/CVD) usando solo OHLCV diario, que es lo que
Fortress tiene (yfinance). Las fórmulas son las de indicAgent, adaptadas a barras
diarias vectorizadas.

**Order Flow Imbalance (OFI, proxy)** — Posición del cierre dentro del rango
intradía ponderada por volumen: `(close−low)/(high−low+eps) × volumen`. Cierre
pegado al high con volumen alto → presión compradora; pegado al low → vendedora.
Implementado en `indicators.py::ofi_features` (T1.1): `ofi_raw`, `ofi_ewma_fast`,
`ofi_ewma_slow`, `ofi_spike_z`, `ofi_price_ret_z`, `ofi_divergence`. **Medido
(§37, 2026-08-20): NO_CUMPLE** — rank IC vs fwd_20d 0/3 ventanas
(máx |t| 1.66 TOTAL, NEGATIVO). El proxy de OFI desde OHLCV diario no contiene
información cross-sectional utilizable para retorno a 20 ruedas. Disponible
en `calculate_all_indicators` pero NO integrado al score.

**Cumulative Volume Delta (CVD, proxy)** — Delta de volumen por barra centrado en
cero: `(2·close−high−low)/(high−low+eps) × volumen` (cierre al high → comprador;
al low → vendedor), acumulado en ventana rolling de 20 días. Implementado en
`indicators.py::cvd_features` (T1.2): `cvd_bar_delta`, `cvd_rolling`,
`cvd_slope_5bar`, `cvd_divergence`. **Decisión de diseño documentada**: el original
resetea por sesión intradía; en barras diarias no aplica, se usa acumulación rolling
20d (alineada al horizonte de calibración). **Medido (§38, 2026-08-20): NO_CUMPLE** —
rank IC vs fwd_20d 0/3 ventanas (máx |t| 0.73 TOTAL). Disponible en
`calculate_all_indicators` pero NO integrado al score.

---

## PARTE II — Fundamentales (valoración, rentabilidad, crecimiento, solvencia)

**Contexto importante antes de leer esto**: el proyecto YA testeó una línea de
fundamentales/sentimiento (Fase 0.6, `PLAN_MEJORA_MATEMATICA.md §0.6.1`, cerrada
2026-08-12) — **NO CUMPLE en ambas variantes** (0/3 ventanas), con una limitación
declarada: cobertura EDGAR de solo 5/50 símbolos (10%), que diluye cualquier pata
fundamental. Este diccionario no cambia esa restricción de datos — antes de
pre-registrar cualquier factor fundamental nuevo, resolver primero el problema de
cobertura de datos, o el resultado va a estar limitado por lo mismo que mató a Fase
0.6, no por el indicador elegido.

### 1. Valoración
Market Cap, Enterprise Value (EV), P/E, Forward P/E, Shiller CAPE, P/B, P/Tangible
Book, P/S, EV/EBITDA, EV/EBIT, EV/Sales, P/Cash Flow, P/Free Cash Flow, FCF Yield,
Dividend Yield, Dividend Payout Ratio, Dividend Growth (CAGR), PEG Ratio, P/Operating
Cash Flow.

Los múltiplos de valoración (P/E, P/B, EV/EBITDA, P/FCF, FCF Yield) son los
componentes clásicos del factor **value** (Fama-French), con evidencia académica
real y bien establecida — a diferencia de casi todo lo demás en este documento. Si
se retoma la línea de fundamentales, este es el subgrupo con mejor respaldo previo,
NO el punto de partida más débil como fue el sentimiento/AAII de Fase 0.6.

### 2. Rentabilidad (márgenes y retornos)
Gross/Operating/EBITDA/Net Margin, ROE, ROA, ROIC, ROCE, ROI, OCF Margin, FCF Margin.

ROIC y ROE sostenidos por encima del costo de capital son los componentes centrales
del factor **quality** — también con respaldo académico real (Novy-Marx y otros),
distinto del sentimiento ya refutado.

### 3. Crecimiento
Revenue Growth (YoY/CAGR), EPS Growth, FCF Growth, Dividend Growth, Book Value
Growth, Sales/EPS/FCF CAGR (3-5 años).

### 4. Apalancamiento y solvencia
D/E, Net D/E, Debt/Assets, Net Debt/EBITDA, Interest Coverage, Times Interest
Earned, Debt Service Coverage, Leverage Ratio.

### 5. Liquidez
Current Ratio, Quick Ratio, Cash Ratio, Working Capital Ratio, OCF/Current
Liabilities, DSO, DIO, DPO, Cash Conversion Cycle.

### 6. Eficiencia
Asset/Inventory/Receivables/Payables/Working Capital Turnover, Capex/Revenue, Sales
per Employee, Profit per Employee.

### 7. Riesgo/retorno de mercado
Beta, Alpha (CAPM), Sharpe Ratio, Sortino Ratio, Information Ratio, Tracking Error,
Volatility, Max Drawdown, TSR, Price Momentum (12-1m, 6-1m).

**Nota**: Sharpe/Sortino/Alpha son las métricas que ya gobiernan el protocolo de
veredicto del proyecto (DSR = Sharpe deflactado por multiple testing, Bailey-López
de Prado) — no son candidatos a "testear", son la vara con la que se testea todo lo
demás. Price Momentum 12-1m es literalmente el factor que ya está validado y en
producción (momentum_12_1 en `signal_engine.py`) — Jegadeesh & Titman (1993).

---

## PARTE II — Features de régimen por símbolo (T2.3, `PLAN_INTEGRACION_INDICAGENT.md`)

Implementadas en `backend/app/core/indicators.py` y disponibles en
`calculate_all_indicators` (columnas `hurst_exponent`, `realized_vol_regime`).
Rol declarado: régimen idiosincrático del símbolo, complementario al
`GlobalRegimeClassifier` (que es cross-asset). Diagnóstico de IC exploratorio
(2026-08-21) en `RESUMEN_HURST_VOL_REGIME.md`: **sin edge direccional robusto vs
retornos futuros → NO se promueven a señal/gate**. Uso diagnóstico únicamente.

**Hurst exponent** — Estimador de escalamiento de varianza sobre la trayectoria
(cumsum de retornos log) de cada ventana: `Var(Z[t+τ]−Z[t]) ~ τ^(2H)`, pendiente de
`log(std(Δτ Z))` vs `log(τ)`. Random walk → H≈0.5; persistencia → H>0.5; reversión a
la media → H<0.5. Implementación vectorizada (`sliding_window_view`, O(n·max_lag)),
`window=100`, `max_lag=20`, `min_periods=50`, clip [0,1], sin detrend dentro de la
ventana (quitar la media sesga H hacia abajo en muestras finitas).

**realized_vol_regime** — Proxy simple de régimen de volatilidad (NO un GARCH(1,1);
decisión explícita del plan: solo si el diagnóstico muestra poder predictivo se evalúa
la dependencia `arch`). Ratio `vol(20d) / vol(100d)` (std rolling): >1 vol subiendo,
<1 bajando. Validación de clustering (2026-08-21): captura persistencia de vol en W1
(t=+3.25) pero no en W2/W3 — indicador de CAMBIO de vol, predice el NIVEL de vol futura
solo débilmente.

---

## Cómo usar este documento

No dispara ninguna tarea nueva por sí solo. Cuando se decida evaluar un indicador
de acá (técnico o fundamental): (1) verificar su definición contra fuente primaria
si no está ya verificada arriba, (2) chequear si `RESEARCH_PREDICTIVE_INDICATORS.md`
ya lo cubre con effect size documentado, (3) recién ahí pre-registrar en
`PLAN_MEJORA_MATEMATICA.md` siguiendo el protocolo estándar del proyecto
(walk-forward W1/W2/W3, Bonferroni/BH, DSR, costos netos).
