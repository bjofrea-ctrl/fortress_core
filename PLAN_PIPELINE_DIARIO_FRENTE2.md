# Diseño — Pipeline diario de señal→orden papel→ledger (Frente 2, OpenCode)

Estado: BORRADOR DE DISEÑO para revisión de Claude Code (gate §1.1 aplica al commit).
Fecha: 2026-08-25. Autor: Muse Spark (OpenCode). Plan contenedor: `PLAN_MAESTRO_FASE_PRODUCCION.md`.

## 0. Principio rector

La definición de la señal es **CONGELADA**: es exactamente la de
`backend/scripts/validacion_oos_fresca_mom_rsi.py` (validación OOS fresca, 2026-08-22).
Nada se re-optimiza, nada se "mejora": ni pesos, ni umbral, ni gates, ni costos.
El pipeline es **transporte**, no investigación. No consume slots de Bonferroni
(solo Frente 1 investiga).

## 1. Definición congelada (fuente de verdad = código del motor, leído en runtime)

| Parámetro | Valor | Fuente |
|---|---|---|
| Pesos momentum/RSI | `w_mom=0.6642`, `w_rsi=0.3358` | `SignalEngine(regime_classifier=None).factor_weights[0]` — **leído en runtime, NUNCA hardcodeado** (misma fuente que la validación, `signal_engine.py:85-90`) |
| Umbral de entrada | `score >= 0.60` | `ENTRY_THRESHOLD`, `signal_engine.py:58` |
| Score momentum | `((mom_12_1 + 50)/150).clip(0,1)`, NaN→0.5 | ídem |
| Score RSI | `0.8 si 45<rsi14<70 sino 0.4`, NaN→0.5 | banda `(45,70)` |
| Gates duros | `close>ema50>ema200` AND `adx14>=20` AND `40<rsi14<75` AND `volume_ratio>=1.0` | `vectorized_eligible`, líneas 105-111 |
| Excluido explícitamente | SIN regime-gate, SIN BMA, SIN stops/target estructurales, SIN puerta MIN_RR | limitación §7 declarada del script (líneas 430-431) |
| Costos de referencia | 0.0005 + 0.0005 por lado | `settings.COST_PER_SIDE` + slippage |
| Universo | `opportunities_universe.SYMBOLS` (50) | mismo import que la validación |

**Fidelidad mecánica obligatoria**: cada corrida imprime en su artefacto un
`frozen_echo` con los valores leídos en runtime (pesos, umbral, gates, costos,
fecha de decisión, hash corto del commit) para auditar deriva de definición.

## 2. Decisión de diseño #1 — Cadencia: mensual fiel, ejecutada por un cron diario

La validación congelada es un **portafolio mensual**: señal al cierre del último
hábil del mes m → entrada a OPEN del primer hábil de m+1 → salida a CLOSE del
último hábil de m+1. Esa cadencia ES parte de la definición (determina exposición
y costos). Rebalancear diario sería re-escribir la estrategia = prohibido.

Por eso el pipeline corre **diario** (scheduler simple, patrón data_updater) pero
solo **actúa** en dos fases del mes; los demás días es no-op con health-check:

| Fase | Cuándo | Acción |
|---|---|---|
| **EXIT** | Último hábil del mes, ~15:40 ET (antes del close 16:00 ET) | Vender TODAS las posiciones del mes (la salida es mecánica por calendario, no requiere señal) |
| **DECIDE** | Último hábil del mes, ~22:10 local (DESPUÉS del data_updater 22:00 que refresca el cache) | Calcular señal desde el close de hoy → escribir `decision file` atómico |
| **ENTER** | Primer hábil del mes, ~09:35 ET (poco después del open 09:30 ET) | Leer decision file → chequear cuenta/posiciones → comprar los simbolos señalados → registrar entradas en ledger |
| (resto) | cualquier otro día | log de salud (cache fresco?, proceso vivo?), cero órdenes |

Calendario de "primer/último hábil del mes": derivado del **índice del parquet de
SPY del cache** (trae el calendario US real, feriados incluidos). Sin dependencia externa.

Desviaciones menores vs backtest, declaradas: (a) EXIT como market order ~20 min
antes del close en vez de close exacto; (b) ENTER como market order ~5 min después
del open en vez de open exacto. Si Cline agrega `time_in_force="opg"/"loc"` al
cliente, se usan órdenes de subasta (open/closing auction) y la desviación baja a ~cero.

## 3. Decisión de diseño #2 — Cálculo de señal: funciones vectorizadas, NO `generate_signal()`

Se usa `compute_factor_frame(indicators_df)` + `compute_score_series(..., regime_state=0)`
de `app/core/signal_engine.py` sobre cada símbolo (cache parquet + `calculate_all_indicators`,
patrón `load_symbol` del propio script de validación) y se toma la última fila:
`eligible & score>=0.60`. Fidelidad de este camino ya verificada con max|Δ|=0
(checks F2/F3 del propio script de validación).

**NO** se usa `generate_signal()` completa: agrega regime-gate, bloqueo de régimen 3,
puerta `MIN_RR=1.5` y stop/target estructural — cosas que la definición congelada
excluyó explícitamente. Usarla sería cambiar la estrategia silenciosamente.

## 4. Arquitectura (3 piezas nuevas + 1 estado)

```
scripts/daily_signal_pipeline.sh          ← patrón data_updater.sh (set -u, cd backend, venv directo, log append)
backend/scripts/pipeline_daily_signal.py  ← núcleo: --phase {auto,exit,decide,enter,health}, --dry-run
scripts/com.fortresscore.pipeline.plist   ← SOLO en Semana 2 (tras checkpoint); StartCalendarInterval múltiple:
                                             15:40 ET-equivalente local (EXIT), 22:10 local (DECIDE), 09:35 local (ENTER)
data/cache/pipeline_state.json            ← estado atómico (tmp+rename): última fase corrida, ordenes enviadas, fills
data/cache/pipeline_decision_<YYYYMM>.json← decision file (escrito en DECIDE, leído en ENTER)
data/cache/pipeline_run_<ts>.txt/.json    ← artefacto por corrida (patrón del repo, con frozen_echo)
```

**Idempotencia anti-duplicado**: toda orden se envía con `client_order_id =
f"fc-{phase}-{yyyymmdd}-{symbol}"`. Alpaca rechaza duplicados del mismo
client_order_id el mismo día → un re-run del cron (crash, relanzamiento) no abre
posiciones dobles. Antes de enviar, consultar posiciones existentes (extensión
Cline) y saltar símbolos ya tenidos en la fase ENTER.

**Sizing**: presupuesto = equity de la cuenta paper (vía extensión de Cline;
fallback configurado `PAPER_CAPITAL_BUDGET=25000` si el endpoint falla → se marca
en el artefacto como `equity_source:fallback`). Equal-weight:
`qty = floor((equity / n_señalados) / precio_ref)`, precio_ref = close del cache.
Cliente actual es qty-only; soporte notional queda como mejora opcional de Cline.

## 5. Contrato con Cline (coordinación, no duplicación)

Verificado con git (2026-08-25): la extensión de Cline **no existe aún en ningún
commit** (rama `bjofrea-ctrl/test-cline-orca` = ancestro de main; cero cambios en
`execution_costs.py`; grep `v2/account|v2/positions` vacío en main y en su worktree).

Lo que **yo necesito** de su tarea asignada (y que mi lado consumirá tras el
checkpoint con stubs propios):

1. `get_account() -> {"equity": float, "buying_power": float}` — `GET /v2/account`
2. `get_positions() -> [{symbol, qty, ...}]` — `GET /v2/positions`
3. `submit_market_order(..., client_order_id: str = "")` y opcional `time_in_force` param
4. **Ledger parcial**: `signal_ledger` hoy exige `exit_date/exit_reason/pnl_r NOT NULL`
   y solo escribe filas retroactivas vía `barrier_labeling.label_symbol(ledger=)`
   (que en producción nadie usa). Para registrar la ENTRADA en vivo hace falta una
   fila con salida pendiente: propuesta mínima = `record_entry(signal_id, symbol,
   entry_date, entry_price, factors, regime_state)` con columnas de salida NULLables
   + `complete_exit(signal_id, exit_date, exit_reason, pnl_r)`. Es SU pieza asignada
   ("integrar cliente con signal_ledger"); yo adapto mi llamada a lo que él entregue.

Lo que **yo entrego** a él: formato del decision file y del `signal_id`
(`{symbol}__{entry_date_iso}`, convención existente de barrier_labeling) para que
su integración llave con mis filas.

## 6. Checkpoint Semana 1 (obligatorio ANTES de instalar launchd)

Corrida MANUAL de un ciclo completo (puede comprimirse: DECIDE un día + EXIT/ENTER
al día siguiente hábil), con `--dry-run` primero y luego real:

1. `python -m scripts.pipeline_daily_signal --phase decide --dry-run` → artefacto
   con frozen_echo correcto y lista de símbolos plausible (comparar contra
   `/api/advisor/universe` como sanity, no como fuente).
2. `--phase enter` REAL en mercado abierto con 1-3 símbolos → verificar en el
   dashboard de Alpaca paper que las órdenes llenaron (`filled_avg_price` presente).
3. Verificar fila en `signal_ledger` (sqlite3 directa): entrada registrada con
   signal_id correcto, salida pendiente.
4. `--phase exit` REAL → posición cerrada + fila completada con pnl_r.
5. Re-run inmediato de la misma fase → **cero órdenes duplicadas** (prueba del
   client_order_id).
6. Sólo entonces: escribir plist, instalar, modo observación 1-2 semanas (Semana 2).

Criterio de bloqueo: si (3) o (5) fallan, NO se instala nada automático y se
reporta al coordinador.

## 7. Riesgos declarados

- **Sin stops en la definición congelada**: el dinero paper puede perder más por
  símbolo entre closes que en el backtest mensual vectorizado (el backtest tampoco
  tenía stops — es la MISMA limitación §7, ahora con dinero sintético real). Aceptado
  por diseño: fidelidad > confort.
- **DST/husos**: los horarios locales de 15:40/09:35 ET se derivan de la diferencia
  ET↔local del día de corrida (zona del sistema), no hardcodeados; el artefacto
  imprime la conversión usada.
- **Cache estancado**: si el data_updater falló (precedente 2026-08-15/22), DECIDE
  aborta si el parquet más viejo del universo tiene fecha < esperada (check de
  staleness con el índice de SPY).
- **El veredicto de la señal congelada fue NO_CUMPLE** (DSR 0.6077<0.95): esto NO
  es una recomendación de trading — es acumulación prospectiva de evidencia en
  dinero sintético, según el plan maestro. El dashboard debe seguir mostrando el
  badge de honestidad; ninguna señal va a usuario final como recomendación.

## 8. Fuera de alcance (explícito)

Broker real (nunca en este plan), re-optimización de cualquier parámetro, regime
gating, stops, nuevos factores, consumo del ledger de investigación.
