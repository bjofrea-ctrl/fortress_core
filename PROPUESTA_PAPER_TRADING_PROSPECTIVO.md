# Propuesta — validación prospectiva vía paper trading (Alpaca)

Documento de diseño, no pre-registro de trial. Acordado con Boris (2026-08-25).
Objetivo: no solo respaldar el análisis retrospectivo (backtest, OOS congelada)
sino generar evidencia genuinamente prospectiva — el modelo decide HOY, el
resultado se conoce mañana, cero posibilidad de haber espiado el futuro.

## Por qué esto es distinto de lo que ya se hizo

Tres niveles de prueba, de menos a más convincente:

1. **Backtest retrospectivo**: datos históricos, se sabe cómo terminó.
2. **OOS fresca congelada** (2026-08-22): parámetros fijados ANTES de mirar el
   resultado, pero sobre datos que ya existían.
3. **Prospectiva real (esta propuesta)**: la señal se genera con datos que
   todavía no tienen "futuro" — el resultado literalmente no existe todavía
   cuando se decide. Es la prueba más convincente que existe.

## La analogía que ordena el diseño (Boris, 2026-08-25)

El modelo no predice "va a llover" — predice una probabilidad, como un
pronóstico del clima, condicionada por factores (régimen macro = "temporada/
presión atmosférica"). Un pronóstico no se evalúa por si acertó UN día, se
evalúa viendo si, entre todos los días que dijo "70%", llovió ~70% de las
veces. Esto define cómo se mide todo lo de abajo: por calibración acumulada
en el tiempo, nunca por un resultado puntual.

## Infraestructura ya existente (no arranca de cero)

- **`AlpacaPaperClient`** (`execution_costs.py`): conexión real y probada a
  Alpaca paper trading — `submit_market_order`, `last_trade_price`,
  credenciales ya configuradas. Ya ejecutó 120 órdenes reales (M4).
- **`signal_ledger.py`** (T1.6): tabla que registra una fila por señal
  (entrada, salida, motivo de salida, `pnl_r`) — exactamente lo necesario
  para trackear cada operación de papel.
- **`BayesianOnlineUpdater`**: ya reajusta pesos según `pnl_r` observado por
  régimen — el mecanismo de combinación gradual que esto necesita ya existe,
  solo hay que alimentarlo con datos de papel en vez de solo backtest.
- **`regime_gate.py` (M3)**: ya condiciona por régimen macro — la primera
  fuente real de diversificación entre variantes (Brecha 2, en curso).

## Piezas a construir

### 1. Snapshot de precios 2x/día (observación, NO ejecución intradía)

Lectura de precios en apertura y cierre sobre las posiciones de papel
abiertas — **solo registro**, no cambia cuándo decide el modelo (sigue con
su definición congelada, diaria/mensual). No reabre la discusión de
ejecución intradía que §13 cerró — eso sigue sin tocarse.

### 2. Múltiples variantes GENUINAMENTE diversificadas corriendo en paralelo

No variantes de parámetros del mismo factor (eso ya se probó que no da
diversificación real — PBO 0.47 con 27 vecinos de momentum+RSI, todos
correlacionados). Diversificación real = fuentes de señal distintas:

- Variante A: baseline momentum+RSI (control, siempre activo).
- Variante B: baseline + compuerta M3 (resultado de Brecha 2, cuando cierre).
- Variante C+: candidatas futuras del árbol de decisión (`ARBOL_DECISION_ESTRATEGICO.md`)
  que resulten genuinamente distintas en fuente de señal — universo
  distinto, dato distinto — no antes de que existan.

### 3. Extender `AlpacaPaperClient` con lectura de cuenta/posiciones

Hoy el cliente solo manda órdenes y lee precios. Falta: consultar equity y
posiciones abiertas de la cuenta de papel (endpoints estándar de Alpaca,
`GET /v2/account`, `GET /v2/positions` — no es una capacidad nueva a
descubrir, es agregar dos llamadas al cliente existente).

### 4. Proceso automático diario (mismo patrón que `data_updater`)

Cron/launchd que, cada día hábil: genera la señal congelada por variante,
la manda como orden de papel vía Alpaca, registra en `signal_ledger.py`.

### 5. Cierre mensual + bitácora acumulada

Por variante, cada mes: Sharpe realizado del mes (no % crudo), comparado
contra lo que el backtest predijo para ese período. Bitácora corrida: cuántos
meses "calibró bien" cada variante, y para los meses que no, un diagnóstico
liviano (¿operación puntual mala, o algo sistemático?).

## Regla de combinación — NO "ganador único"

**Nunca elegir la variante con mejor % de un solo período.** Un mes de 3%
puede ser ruido puro (vol mensual ~4.3% con vol anual 15%). La combinación
entre variantes se hace vía `BayesianOnlineUpdater`, ponderando por Sharpe
acumulado en MÚLTIPLES períodos, ajuste gradual — nunca un corte único.

**Criterio de comparación fijado ANTES de mirar datos** (mismo principio que
cualquier pre-registro del proyecto, aunque esto no consuma slot del ledger
por no ser una hipótesis de mercado nueva): cuántos meses mínimos antes de
reponderar, qué margen de Sharpe se considera señal vs ruido, cómo se
pondera la correlación entre variantes al combinar (no solo el Sharpe
individual — dos variantes muy correlacionadas no aportan diversificación
real aunque ambas rindan bien).

## Qué NO es esto

- No es conectar a un broker real. Sigue siendo dinero sintético.
- No reemplaza el árbol de decisión (`ARBOL_DECISION_ESTRATEGICO.md`) — es
  el mecanismo de validación de lo que ese árbol vaya produciendo, corre en
  paralelo, no compite por recursos con la investigación de nuevos caminos.
- No es una promesa de resultado — como con todo lo demás, se mide, y si no
  calibra bien, se documenta como tal, sin forzar una conclusión positiva.

## Siguiente paso

Pendiente definir con Boris: quién construye esto (candidato natural:
OpenCode o Cline, dado el trabajo ya hecho con Alpaca/API), y cuándo arranca
(¿antes o después de que cierre Brecha 2, para tener la Variante B lista
desde el principio?).
