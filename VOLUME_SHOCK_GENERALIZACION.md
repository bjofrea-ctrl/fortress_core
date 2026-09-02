# Extensión Volume Shock — ¿Se generaliza el patrón NVDA?

**Fecha**: 2026-09-01 (extensión del piloto, solo lectura parquet)
**Régimen**: mismo que `INGENIERIA_INVERSA_POR_TICKER.md` — solo lectura `backend/data/cache/*.parquet`, no ledger, no pre-registro. Mismo método (terciles propios, bootstrap CI) pero foco en un solo indicador.
**Pregunta**: el hallazgo más fuerte del piloto fue `volume_shock` en NVDA (bajo shock → mejor retorno 20d, estable en 4 ventanas). ¿Se repite en los otros 3 tickers del piloto (AAPL, EPAM, QLYS) o es ruido específico de NVDA?

---

## 1. Método (idéntico al piloto)

- **Tickers**: mismos 4 extremos por marketCap actual (snapshot 2026-09-01, §3 piloto): NVDA 5250B (max), EPAM 6.0B (min), AAPL 4745B (2do max), QLYS 6.1B (2do min). SPY/QQQ excluidos (ETFs).
- **Ventanas anidadas**: 10y 2016-09-01→2026-08-31, 7y 2019-09-01→, 5y 2021-09-01→, 2y 2024-09-01→ (mismas que piloto, comparten datos, chequeo de estabilidad no replicación).
- **Horizontes**: 20d (corto, mensual) y 60d (largo, trimestral) — `fwd_ret_H = close(t+H)/close(t)-1`.
- **Indicador único**: `volume_shock = dvol(t-1) / mean(dvol(t-2..t-61))` donde `dvol=close*volume` (presión relativa de volumen, idéntico a `diagnose_asimetria_direccional.py:154`). Calculado por ticker, sin pooled.
- **Bucketeo**: terciles propios por ventana (q33/q66). Buckets low/mid/high con n≈ 828 en 10y, 577 en 7y, 409 en 5y, 158 en 2y (20d); similar para 60d. Media por bucket + CI95% bootstrap (1000 resamples, seed 42). Diferencia low-high con CI de la diferencia (SÍ = CI no incluye 0).
- **Script**: `/tmp/volume_shock_light.py` (rsi/momentum removidos para ligereza, mismo `volume_shock`), raw `/tmp/volume_shock_light_raw.txt` (133 líneas).

No se miró pooled, no se optimizó corte, no se eligió ventana/horizonte post-hoc.

## 2. Resultado crudo (volume_shock, media fwd_ret por bucket, CI95%)

### 20d (corto)

| Ticker | 10y low→high (mean% 20d) | 10y diff L-H | 7y diff | 5y diff | 2y diff |
|--------|--------------------------|--------------|---------|---------|---------|
| **NVDA** | low **+6.79** [5.80,7.72] > mid +3.73 > high +4.26 | **+2.52 [1.22,3.78] SÍ** low>high | **+2.82 [1.23,4.34] SÍ** | **+2.66 [0.73,4.59] SÍ** | **+4.93 [2.75,7.14] SÍ** |
| **AAPL** | low **+3.70** [3.21,4.19] > mid +1.81 > high +1.54 | **+2.16 [1.42,2.93] SÍ** | **+1.77 [0.90,2.65] SÍ** | **+1.14 [0.22,2.22] SÍ** | -0.24 [-1.82,1.37] **NO** |
| **EPAM** | low +1.00 [-0.03,1.99] ≈ high +1.68 → | -0.68 [-1.85,0.54] **NO** | +0.05 [-1.72,1.77] **NO** | +1.03 [-1.12,3.18] **NO** | **+3.45 [0.07,6.46] SÍ** |
| **QLYS** | low +1.13 [0.49,1.83] < high **+2.68** [1.83,3.43] | **-1.55 [-2.58,-0.56] SÍ high>low** | **-3.28 [-4.53,-2.01] SÍ** | **-2.64 [-4.18,-1.04] SÍ** | **-3.62 [-6.75,-0.74] SÍ** |

### 60d (largo)

| Ticker | 10y diff L-H | 7y | 5y | 2y | Patrón |
|--------|--------------|----|----|----|--------|
| **NVDA** | +2.48 [-0.02,4.84] **NO** | +0.58 [-2.08,3.73] NO | +0.42 [-3.47,4.18] NO | +3.83 [-0.62,8.55] NO | **solo 20d es SÍ, 60d se diluye** |
| **AAPL** | **+5.76 [4.44,7.11] SÍ** | **+4.66 [3.08,6.49] SÍ** | **+2.74 [1.11,4.37] SÍ** | +2.57 [-0.03,5.26] NO | **SÍ en 10y/7y/5y, NO en 2y** |
| **EPAM** | -1.61 [-3.68,0.49] NO | -0.62 [-3.42,2.33] NO | **+4.10 [0.89,7.42] SÍ** (¡pero low -4% vs high -8%! ambos negativos) | +3.02 [-2.62,8.28] NO | **ruido, solo un SÍ en contexto bajista general** |
| **QLYS** | -0.32 [-2.10,1.47] NO | -1.96 [-4.12,0.49] NO | -0.18 [-3.18,2.70] NO | -1.20 [-8.16,5.38] NO | **NO en ningún 60d** |

n por bucket: 10y ~828, 7y ~577, 5y ~409, 2y ~158 (20d); 60d ~815/564/396/144. q33/q66 propios: NVDA 0.815/1.090 (10y) → 0.841/1.028 (2y); EPAM 0.730/1.082 → 0.720/1.065; etc. (distribuciones estables).

Raw completo: `/tmp/volume_shock_light_raw.txt` (133 líneas, 32 combos).

## 3. Veredicto honesto: ¿se repite?

**No — es ticker-específico, no generalizable.**

- **NVDA (primario)**: único con **low>high SÍ en 4/4 ventanas 20d** y de forma monótona (low siempre el mejor). Patrón estable y direccionalmente consistente. En 60d no hay señal (4/4 NO) — el efecto es de corto plazo.
- **AAPL (mega, similar cap a NVDA)**: **parcialmente replica** NVDA en 20d: SÍ en 10y/7y/5y, pero **falla en 2y** (la ventana más reciente, la que más importa para trading actual). En 60d replica mejor (SÍ 10y/7y/5y) pero también falla en 2y. Esto sugiere que incluso entre mega-caps, la estabilidad no es total.
- **EPAM (small)**: **no replica** en 20d (3/4 NO, solo 2y SÍ con CI justo en el borde 0.07). En 60d 3/4 NO. Cuando es SÍ (5y 60d, 2y 20d) el contexto es mercado bajista (medias negativas en los tres buckets), no una ventaja de low-volume.
- **QLYS (small, 2do min)**: **patrón opuesto**: high>low SÍ en 4/4 ventanas 20d (high mejor que low de forma consistente, p <0.01). Es decir, en QLYS el alto shock de volumen predice mejor retorno 20d — exactamente lo contrario a NVDA. En 60d no hay señal (4/4 NO).

Si volume_shock fuera una señal general, esperaríamos low>high SÍ en al menos 3/4 tickers y 3/4 ventanas. Observado: NVDA 4/4, AAPL 3/4, EPAM 1/4, QLYS 0/4 en la dirección NVDA (y 4/4 en dirección opuesta). La tasa de replicación direccional es 1/3 (solo AAPL parcialmente).

**Interpretación útil**: el hallazgo del piloto es **ruido específico de NVDA (y parcialmente AAPL)**, no una ley cross-sectional. Dos hipótesis no excluyentes:
1. **Cap/liquidez**: NVDA/AAPL son mega-caps con volumen profundo; bajo shock puede indicar consolidación antes de breakout. En small caps (EPAM/QLYS) el alto shock puede indicar capitulación o noticia que sí predice rebote (QLYS high>low).
2. **Régimen ticker-específico**: EPAM cayó -80% desde 2021; su volume_shock está contaminado por distribución bimodal de volumen en caída. NVDA subió +1000% en 10y; su low-volume es en tendencia alcista.

En ambos casos, la variación es el resultado — no se puede pooled.

## 4. Limitaciones (mismas que piloto, más foco)

- **N pequeño en 2y**: 158 por bucket → CI ancho ±1.5pp (20d) y ±4pp (60d). Un SÍ/NO puede flippear con 20 días más de datos. No hay potencia para afirmar "no hay efecto" en 2y.
- **Terciles arbitrarios y univariado**: se eligió q33/q66 sin buscar óptimo; no hay control por momentum/RSI ni por régimen de mercado. La señal de volume_shock puede estar confundida con volatilidad.
- **Horizontes fijos**: 20d y 60d son representantes de 5-20d y 60-252d; 5d o 252d podrían dar otra foto. No se exploraron para no multiplicar celdas.
- **Snapshot marketCap**: ranking 2026-09-01 no es el cap en 2016-2019; EPAM era mid-cap en 2019, no siempre min.
- **Nested windows**: comparten datos; la "estabilidad" de NVDA en 4 ventanas está inflada por solape (10y contiene 7y etc.).
- **Costos ignorados**: retornos brutos, sin comisión 0.10%/lado ni slippage; la ventaja low>high de NVDA +2.5pp en 20d se come rápido con turnover alto.

## 5. Qué sigue

- **No pre-registrar volume_shock como señal general**. Si se quisiera perseguir, pre-registrar **por ticker** (ej. "NVDA low volume_shock → long 20d") con ventana/horizonte fijos, y correr una sola vez en datos no vistos (post-2026-08-31) — no pooled.
- **Más profundidad si interesa NVDA**: descomponer volume_shock en `dvol` vs `price` (¿es volumen o precio el driver?), o cruzar con `rsi` (¿low vol + low rsi es mejor?).
- **No tocar ledger/slot 29** hasta pre-registro nuevo con aprobación.

---

**Artefactos**: este archivo, `/tmp/volume_shock_light.py`, `/tmp/volume_shock_light_raw.txt` (133 líneas, 4×4×2 diffs), `INGENIERIA_INVERSA_POR_TICKER.md` (piloto). Solo lectura parquet.
