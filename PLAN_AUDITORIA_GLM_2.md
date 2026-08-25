# Plan de auditoría — ronda 2, para GLM (fx)

Pegar completo en la sesión de `fx`. Objetivo: cerrar el loop de la ronda
anterior (verificar el fix de H1.1) y cuantificar los dos hallazgos
metodológicos que quedaron sin medir.

## Regla de entrada (igual que la ronda 1)

Leé `ROADMAP.md` (buscá la fila "SAMPLE_PREDICTION_DATA" cerca del final,
commit `33d8914`) antes de empezar — ya se corrigió H1.1 de tu auditoría
anterior. No lo reportes de nuevo como abierto; tu tarea acá es verificar
que el fix esté completo y correcto.

## Tarea 1 — Verificar el fix de H1.1 (independiente, no confiar en el commit)

Revisá `backend/app/api/routes/predict.py` y `backend/app/api/routes/governance.py`:
1. Confirmá que no queda ninguna referencia funcional a `SAMPLE_PREDICTION_DATA`
   (un comentario explicativo está bien, código que la use no).
2. Confirmá que los 3 call sites (`predict.py` ×2, `governance.py` ×1) pasan
   `prediction_data=None`.
3. Leé `predictive_engine.py` alrededor de la función que consume
   `prediction_data` (donde generaba los `SignalDetail` "Polymarket: ...") y
   confirmá que con `None` esa función devuelve `[], 0.0` sin generar señales
   fantasma — es decir, que el fix realmente saca las señales falsas del
   `composite_score`, no solo cambia el nombre de la variable.
4. Buscá si hay algún OTRO punto de entrada al motor (además de los 3 routers)
   que pueda seguir pasando datos hardcodeados sin marcar — mirá si hay algo
   parecido con otros parámetros de `engine.analyze()` (no solo
   `prediction_data`) que tampoco tenga marcador de origen tipo `_data_source`.

## Tarea 2 — Cuantificar H4.1 (sesgo de supervivencia del universo)

No hace falta correr ningún trial — es una medición descriptiva del dataset,
no una hipótesis de mercado.

1. Leé `backend/scripts/fetch_universe_data.py` completo — la lista NEW_UNIVERSE
   y cómo se construyó.
2. Preguntá: ¿hay algún registro (docstring, commit, comentario) de CUÁNDO se
   fijó esta lista de 43 símbolos? Si el corte fue "hoy" (2026), y el
   backtest corre desde 2015, cuantificá: ¿cuántos de estos 43 símbolos NO
   cotizaban públicamente en 2015 (IPOs posteriores)? Con eso solo ya hay una
   cota inferior del sesgo — esos símbolos no podían estar en un universo
   armado honestamente en 2015.
3. Si podés acceder a los parquet en `backend/data/cache/*.parquet`, verificá
   la fecha de inicio real de cada símbolo (primer dato disponible) — un
   símbolo cuyo primer dato es posterior a 2015-01-01 confirma que es un caso
   de sesgo (no existía cotizando cuando el backtest "empieza" a operarlo).
4. Reportá el conteo exacto: N de 50 símbolos con primer dato posterior a
   2015-01-01, y la fecha de IPO/listado si la conocés de fuentes públicas
   (no inventes — si no la sabés, decí "no verificado").

## Tarea 3 — H5.1: corporate actions (la que no pudiste chequear la vez pasada)

Esta vez intentá lo que el plan anterior pedía y no pudiste por bloqueo de
terminal:
1. `pip show yfinance` (o revisar `requirements.txt`/`requirements-dev.txt`
   directamente si el comando no anda) para la versión instalada.
2. Elegí 2-3 símbolos con splits conocidos y públicos en el rango 2015-2026
   (ejemplos reales: AAPL split 4:1 el 2020-08-31, NVDA split 10:1 el
   2024-06-10, GOOGL split 20:1 el 2022-07-18 — verificá vos mismo si estos
   símbolos están en el universo del proyecto antes de usarlos). Leé el
   parquet correspondiente en `backend/data/cache/` alrededor de esa fecha
   exacta y verificá si hay un salto de precio no ajustado (ej. AAPL
   cotizando ~$500 el día antes del split y ~$127 el día después, sin
   continuidad, sería la señal de que NO está ajustado).
3. Reportá con el número real del precio de cierre el día antes y el día
   después de cada split que puedas verificar.

## Formato de salida

Mismo que la ronda anterior: hallazgo con archivo:línea o dato concreto,
sección "lo que no pude verificar" honesta, sin proponer que se ejecute
nada — solo reportar. Cualquier trial nuevo necesita pre-registro y decisión
explícita de Boris.
