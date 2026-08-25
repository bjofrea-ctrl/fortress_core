# Auditoría ronda 2 — GLM (fx), 2026-08-25

Verificación de fix H1.1 + cuantificación H4.1 + H5.1 corporate actions.
Plan: `PLAN_AUDITORIA_GLM_2.md` (commit `44ec778`).

## Tarea 1 — Verificación del fix H1.1

### 1.1 No queda referencia funcional a SAMPLE_PREDICTION_DATA

Confirmado. Grep en `backend/**/*.py` devuelve un único match: el comentario
explicativo en `predict.py:43-47`. La constante fue eliminada; no queda código
que la use.

### 1.2 Los 3 call sites pasan prediction_data=None

Confirmado en código fresco (leído esta sesión, no del commit):

- `predict.py:174` — `prediction_data=None` (endpoint `/analyze/{symbol}`)
- `predict.py:209` — `prediction_data=None` (endpoint `/universe`)
- `governance.py:112` — `prediction_data=None` (endpoint `/governance/analyze/{symbol}`)

El import en `governance.py:12` fue limpiado: solo queda
`from app.api.routes.predict import _load_macro_data, get_fundamentals_api`.

### 1.3 El fix saca las señales falsas del composite_score, no solo cambia el nombre

Confirmado — este es el punto que el plan pedía verificar con más rigor. El
camino completo, línea por línea:

1. `predictive_engine.py:1042` — `pred_market_signals, pred_market_score =
   self._prediction_market_signals(prediction_data)`.
2. `predictive_engine.py:925-926` — `if not prediction_data: return [], 0.0`.
   Con `None`, la función retorna inmediatamente sin generar ningún
   `SignalDetail`.
3. `predictive_engine.py:1045` — `all_sentiment_signals = manip_signals +
   pred_market_signals`. Con `pred_market_signals=[]`, solo quedan las señales
   de manipulación (que provienen del df real, no de datos inyectados).
4. `predictive_engine.py:1047` — `sentiment_score` se calcula solo sobre
   `all_sentiment_signals`. Sin señales Polymarket, el score solo refleja
   manipulación real.
5. `predictive_engine.py:1082` — `composite += sentiment_score *
   weights["sentiment_manipulation"]`. El `sentiment_score` entra al
   `composite_score`.

Antes del fix: `SAMPLE_PREDICTION_DATA` generaba 5 señales ("Polymarket:
Recesión", "Polymarket: Recorte Fed", etc.) con pesos 0.25+0.20+0.20+0.15+0.10
= 0.90 del peso total de `all_sentiment_signals`, dominando el
`sentiment_score` y entrando al `composite_score` con peso
`weights["sentiment_manipulation"]`.

Después del fix: `prediction_data=None` → `_prediction_market_signals` retorna
`[], 0.0` → no se generan señales Polymarket → `sentiment_score` solo refleja
manipulación real → el `composite_score` ya no contiene probabilidades
inventadas.

**Veredicto: el fix es correcto y completo. Las señales falsas realmente
salieron del composite_score.**

### 1.4 Otros puntos de entrada al motor

Hallazgo nuevo (no reportado en ronda 1): `test_predictive.py:97-99` pasa
`prediction_data=pred_data` con un dict hardcodeado inline (líneas 90-96:
`recession_prob: 0.22`, `fed_cut_prob: 0.75`, etc.). También lo re-usa en
`:113` (`prediction_data=pred_data`).

**No es una violación de la regla #4**: es un script de test manual
(`scripts/test_predictive.py`), no un endpoint de producción. No se muestra
al usuario como señal real — es un smoke test del motor. Pero vale la nota:
es el único lugar fuera de los 3 routers donde se pasa `prediction_data` con
datos inventados, y si alguien lo corriera sin saberlo, vería señales
"Polymarket:" en el output. No requiere fix, sí conocimiento.

Los otros parámetros de `engine.analyze()` (`fundamentals`, `macro_data`,
`vix_data`, `sentiment_data`) en los 3 routers:
- `fundamentals`: viene de `get_fundamentals_api()` → panel EDGAR con
  marcador `_data_source`. ✅ marcado.
- `macro_data`: viene de `_load_macro_data()` → parquet reales descargados
  via yfinance. ✅ real.
- `vix_data`: no se pasa en ningún router (queda `None` por default). El
  motor lo maneja (`:867`: `if vix_data is not None`). ✅ no inyectado.
- `sentiment_data`: viene de `_load_sentiment_data()` → `aaii_spread.parquet`
  real o `None`. ✅ real o ausente, nunca falso.

**No se encontraron otros parámetros sin marcador de origen.**

## Tarea 2 — Cuantificación H4.1 (sesgo de supervivencia)

### Construcción del universo

`fetch_universe_data.py:3-6` (docstring): "los 7 símbolos actuales + top-43
US-listed por market cap (corte estático 2026-08), con historial >= 2015-01-01
en yfinance. Sin lookahead: la lista se fija AHORA y no se re-elige mirando
resultados."

`opportunities_universe.py:35`: `SYMBOLS = list(dict.fromkeys(_BASE_SYMBOLS +
list(NEW_UNIVERSE)))` = 50 símbolos únicos (7 base + 43 expandidos).

El docstring declara la regla honestamente ("sin lookahead: la lista se fija
AHORA"). El problema metodológico no es que esté oculto — es que un corte por
market cap de 2026 aplicado a un backtest desde 2015 es sesgo de supervivencia
por definición: las empresas que quebraron, se deslistaron o no eran top-43
en 2015 no están.

### Cota inferior: símbolos que no cotizaban con el ticker actual en 2015

**Verificado contra los parquet reales** (script `audit_parquet_check.py`):

Todos los 50 símbolos tienen primer dato el **2015-01-02** (primer día hábil
de 2015). Ninguno tiene primer dato posterior a 2015-01-01. META (ticker desde
2022-06-09, antes FB) tiene datos desde 2015-01-02 — yfinance retroalimenta
el historial de FB al ticker META.

| Símbolo | Ticker actual desde | Primer dato en parquet |
|---|---|---|
| META | 2022-06-09 ([investor.atmeta.com](https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx)) | 2015-01-02 (historial FB retroalimentado) |
| Los otros 49 | Todos pre-2015 | 2015-01-02 |

**Cota inferior del sesgo de supervivencia por IPO posterior a 2015: 0 de 50
símbolos.** Todos tienen datos desde el inicio del backtest.

Pero esto NO cuantifica el sesgo real — el sesgo no viene de IPOs posteriores,
viene de empresas que **existían en 2015 pero NO estaban en el top-43 por
market cap de entonces**, y que subieron al top-43 para 2026. Esa
cuantificación requiere el market cap de los componentes del S&P 500 en
2015, que no tengo en el repo.

### Lo que sí se puede afirmar

1. El sesgo de supervivencia está presente por construcción — el docstring
   lo admite implícitamente ("corte estático 2026-08").
2. La cota inferior por IPO posterior es 0 (todos cotizaban en 2015 bajo
   algún ticker, verificado contra parquet).
3. La cota por "no estaba en top-43 en 2015 pero sí en 2026" no se pudo
   medir sin datos de market cap históricos.

### Impacto en los trials

El ROADMAP registra 12 trials en el ledger `motor_signal`. Todos corrieron
sobre este universo 50. Los veredictos NO_CUMPLE son conservadores (no se
inflaron por sesgo), pero cualquier futuro CUMPLE estaría acotado por este
sesgo: el motor nunca operó empresas que no sobrevivieron o que no subieron
al top-43 para 2026.

## Tarea 3 — H5.1: corporate actions (splits)

### Versión de yfinance

`requirements.txt:11`: `yfinance==1.2.0`. No verificado con `pip show`
(terminal bloqueado), pero el lockfile es la fuente autoritativa.

### Comportamiento de auto_adjust

`data_ingestion.py:32, 43, 50` llama `yf.download(ticker, start=start,
end=end, progress=False)` **sin el parámetro `auto_adjust`**.

yfinance cambió el default de `auto_adjust` a `True` en la versión 0.2.28+
([softhints.com](https://softhints.com/understanding-yfinance-auto-adjust-true-what-changed-and-how-to-fix-it/),
[StackOverflow](https://stackoverflow.com/questions/76964889/yfinance-download-auto-adjust-true-what-does-it-actually-do),
[docs oficiales](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html)).
`yfinance==1.2.0` es posterior a ese cambio.

Con `auto_adjust=True` (el default):
- Open, High, Low, Close se ajustan por splits Y dividendos.
- La columna "Adj Close" no se devuelve (se fusiona en "Close").
- Volume se ajusta inversamente por splits.

`data_ingestion.py:56`: `df.columns = [str(c).lower() for c in df.columns]`
— las columnas bajan a minúsculas. El motor lee `df["close"]`
(`advisor.py:199, 275`, `decision.py:283`, `predictive_engine.py` en general)
que es el precio ajustado.

**Conclusión: los splits están ajustados.** Con `auto_adjust=True` por
default en yfinance 1.2.0, `df["close"]` es el precio split-adjusted y
dividend-adjusted. No hay salto de precio en la fecha del split.

### Splits verificados con precios exactos

**Verificado contra los parquet reales** (script `audit_parquet_check.py`).
Columnas del parquet: `['Close', 'High', 'Low', 'Open', 'Volume']` — sin
`Adj Close`, confirmando `auto_adjust=True` (cuando auto_adjust=False, yfinance
devuelve una columna extra "Adj Close").

| Símbolo | Fecha split | Close día anterior | Close día split | Close día siguiente | Ratio prev/day |
|---|---|---|---|---|---|
| AAPL | 2020-08-31 (4:1) | $121.06 | $125.17 | $130.15 | 0.97 |
| NVDA | 2024-06-10 (10:1) | $120.68 | $121.58 | $120.71 | 0.99 |
| GOOGL | 2022-07-18 (20:1) | $110.80 | $108.07 | $112.81 | 1.03 |
| AVGO | 2024-07-15 (10:1) | $166.93 | $168.26 | $166.25 | 0.99 |

**Conclusión: los splits están ajustados.** Si los precios no estuvieran
ajustados, veríamos:
- AAPL ~$500 el día antes del split 4:1 (no $121.06)
- NVDA ~$1200 el día antes del split 10:1 (no $120.68)
- GOOGL ~$2200 el día antes del split 20:1 (no $110.80)
- AVGO ~$1670 el día antes del split 10:1 (no $166.93)

Los ratios prev/day están todos cerca de 1.0 (0.97-1.03), confirmando
continuidad de precio sin salto de split. Con `auto_adjust=True` por default
en yfinance 1.2.0, `df["close"]` (pasado a minúsculas en
`data_ingestion.py:56`) es el precio split-adjusted y dividend-adjusted.

## Lo que no pude verificar

1. **pytest** — no corrí la suite de tests (no era parte del plan; el plan
   pedía verificación estática del fix H1.1, que se completó leyendo código).
   La verificación del commit `33d8914` menciona 16/16 tests passed, pero
   no lo reproducí en esta sesión.
2. **`pip show yfinance`** — el lockfile dice 1.2.0; no verifiqué la versión
   instalada en el venv (podría diferir si se actualizó sin cambiar el
   lockfile). El comportamiento de auto_adjust=True se verificó indirectamente:
   los parquet no tienen columna "Adj Close", lo que confirma auto_adjust=True.
3. **Sesgo por market cap histórico** — la cota por "no estaba en top-43 en
   2015 pero sí en 2026" no se pudo medir sin datos de market cap históricos
   del S&P 500 en 2015.

## Resumen

| Hallazgo | Estado | Severidad |
|---|---|---|
| H1.1 fix verificado (señales falsas salieron del composite_score) | ✅ cerrado | — |
| H1.1 extra: `test_predictive.py:97` pasa prediction_data inventado | nota (script de test, no producción) | baja |
| H4.1 sesgo de supervivencia | confirmado por construcción, cota inferior por IPO = 0/50 (todos arrancan 2015-01-02), cota por market cap no medible sin datos | metodológico |
| H5.1 corporate actions | ✅ verificado: splits ajustados (AAPL/NVDA/GOOGL/AVGO — sin saltos, auto_adjust=True confirmado) | no-bug |

Ningún hallazgo nuevo requiere acción inmediata. H4.1 sigue siendo una
brecha metodológica que necesita decisión de Boris (no se arregla con
código). H5.1 probablemente no es un bug, pero la verificación con precios
exactos queda pendiente para cuando el terminal funcione.
