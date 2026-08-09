# PLAN — Variable Principal de Régimen: Sentimiento Inversor (v4)

**Fecha**: 2026-08-09
**Estado**: Diseño aprobado por el usuario (tesis reformulada) — pendiente ola 2 y tests H1-H6
**Dueño de la variable**: Agente CONTRARIAN (`triad_agents.py`)

---

## 1. La tesis (mecanismo que debe validar el sistema)

El sistema financiero (instituciones) maneja las alzas y bajas del precio de la bolsa. La
variable central que lo gobierna es el **sentimiento del inversor minorista**:

1. **Sentimiento NEGATIVO (miedo)** → la gente no compra → el sistema financiero compra
   barato → **la bolsa sube**. En sentimiento bajo de compra se alcanzan máximos históricos
   del S&P 500.
2. **Sentimiento POSITIVO (euforia)** → todos quieren comprar → el sistema financiero
   vende caro a la multitud → **la bolsa cae**, para luego recomprar más barato y repetir.
3. **La liquidez NO es la causa de la subida.** Es la condición habilitadora: cuando el
   sistema quiere que la gente compre, se asegura de que haya liquidez (la gente puede
   comprar porque tiene dinero disponible, no porque "la bolsa sube por liquidez").
4. **La velocidad es la firma de la intención:**
   - Movimientos **rápidos** → quieren generar emoción: entusiasmo (subidas) o miedo (bajadas).
   - Movimientos **lentos y persistentes**, especialmente subidas → quieren pasar
     desapercibidos (acumulación silenciosa).
5. **Consecuencia operativa**: el agente CONTRARIAN le da valor a esta variable y
   **cuestiona las demás variables del sistema contra ella** (si el sentimiento está en
   extremo, momentum/RSI/ER mienten).

---

## 2. Variables del plan

| Var | Nombre | Fuente | Estado |
|-----|--------|--------|--------|
| **V1** | **Sentimiento inversor directo** (PRINCIPAL) | AAII bull−bear spread, NAAIM exposure, put/call ratio CBOE | **Pendiente (ola 2)** |
| V2 | Posiciones adoptadas EN FUNCIÓN del sentimiento | CFTC COT: NonRept (retail), Lev_Money (specs), Asset_Mgr, Dealer | Datos listos (ola 1) |
| V3 | Liquidez como condición habilitadora | FRED: WALCL, RRPONTSYD, WRESBAL | Datos listos (ola 1) |
| V4 | Velocidad (rápido/lento) | Kaufman ER10/20/60 + \|leg_ret\| | Medido (Fase V4) |

**Relación clave V1↔V2**: los inversores adoptan posiciones en función de su sentimiento.
El test H2 mide esa consistencia: cuando el sentimiento (V1) sube, ¿el retail (V2) compra?
Si no, la narrativa sentimiento→posición no se sostiene y hay que revisarla.

---

## 3. Hipótesis medibles y tests

| # | Hipótesis | Test | Datos |
|---|-----------|------|-------|
| **H1** | IC(sentimiento, retorno futuro) NEGATIVO: sentimiento alto → cae; bajo → sube | IC univariado V1 vs ret 5/20/60d + terciles | ola 2 |
| **H2** | Consistencia: sentimiento alto → retail COT comprado | Correlación V1 con cot_retail_net_pct (misma semana) | ola 2 + ola 1 |
| **H3** | Distribución retardada: la caída ocurre DESPUÉS del pico de sentimiento | Retorno 20/60d tras extremos de V1 (tercil alto vs bajo) | ola 2 |
| **H4** | Liquidez como condición: el efecto H1 se POTENCIA cuando hay liquidez | 2×2 sentimiento × liquidez (celda sent_bajo × liq_alta debe ser la mejor) | ola 2 + ola 1 |
| **H5** | Velocidad: subida lenta y persistente + sentimiento bajo → continúa (acumulación); subida rápida + sentimiento alto → cae (distribución) | 2×2 sentimiento × ER (o \|leg_ret\|) | ola 2 + Fase V4 |
| **H6** | Cuestionamiento: en buckets de sentimiento extremo, momentum/RSI/ER cambian de signo o pierden potencia | IC condicional de momentum/rsi/er por bucket de V1 | ola 2 |

**Regla de significancia**: |IC| > 2/√n, consistencia entre horizontes, y rank_ic en la
misma dirección. Los datos mandan: si una hipótesis de la narrativa falla, se documenta
y se descarta — no se fuerza.

---

## 4. Implementación

### Ola 2 — Fuentes de sentimiento directo (V1)
- **AAII** (sentimiento semanal de inversores individuales): bull/bear neutral → spread.
- **NAAIM** (exposición de gestores): 0-100 → desviación de la media.
- **Put/call ratio** CBOE (opciones): nivel y cambio.
- Implementación en `backend/app/core/market_sentiment.py` con el mismo patrón:
  anti-lookahead (`shift(1)` + `ffill` sobre fechas de trading), cache parquet, doble
  transporte HTTP (requests + curl_cffi).

### Integración — Variable de régimen
- Nueva capa `sentiment_regime` sobre `REGIME_WEIGHTS` (`predictive_engine.py:1021`):
  - Sentimiento en extremo → V1 gana peso de régimen; las demás variables se **cuestionan**
    (multiplicador o inversión según H6).
  - Subidas lentas y persistentes (ER bajo) con sentimiento bajo → confirmar continuidad.
  - Subidas rápidas (ER alto) con sentimiento alto → señal de distribución → inclinar bear.
- Reglas nuevas en `ContrarianAgent` (`triad_agents.py:268`): el agente lee V1 como su
  variable principal y condiciona su voto a los extremos de sentimiento.

### Validación
- `pytest` completo tras integración.
- OOS: datos 2025-2026 si la fuente lo permite.
- Docs: `PLAN_SENTIMIENTO.md` + entrada en `SESSION_LOG.md`.

---

## 5. Orden de ejecución

1. **Ola 2**: fetch AAII + NAAIM + put/call → `diagnose_sentiment_ic.py` extendido con V1.
2. **Tests H1-H4**: IC directo de sentimiento, consistencia con COT, distribución retardada, liquidez como condición.
3. **Test H5**: interacción sentimiento × velocidad (usa ER ya medido).
4. **Test H6**: IC condicional de momentum/rsi/er por bucket de sentimiento → define el "cuestionamiento".
5. **Integración**: `sentiment_regime` en `predictive_engine.py` + reglas en `ContrarianAgent`.
6. **Cierre**: `pytest`, OOS si aplica, `SESSION_LOG.md`.

---

## 6. Estado de datos (ola 1, ya medido)

| Medición | Resultado | Nota |
|----------|-----------|------|
| COT retail (NonRept) 60d | IC +0.1069*** | Posición, NO sentimiento — no es evidencia contra la tesis |
| COT asset managers 60d | IC -0.0890*** | Dirección contraria a retail |
| walcl_growth_w 60d | IC +0.0633* / rank_ic -0.0167 | Frágil |
| H6 2×2 (liquidez × retail COT) 60d | liq_alta × ret_alta = +0.0983 | La celda "euforia + liquidez" sube — inconsistente con H4/H6 narrativa, requiere V1 real para dirimir |

> **Importante**: los resultados de ola 1 miden POSICIONES sin el sentimiento directo.
> La tesis completa solo puede confirmarse o refutarse con V1 (AAII/NAAIM/put-call) y los
> tests H1-H6. El COT NonRept de 2026-08-04 ya está descartado por el bug de alineación
> (fix: `sort_index()` en `_align`).
