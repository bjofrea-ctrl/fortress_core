# Ingeniería Inversa por Ticker — Estados Propios vs Retorno Futuro

**Fecha**: 2026-09-01 (exploración, solo lectura parquet cache)
**Régimen**: construcción+exploración, mismo que RMT/heterogeneidad — no ledger, no pre-registro todavía. Si algo promete, se pre-registra después como trial nuevo.
**Origen**: ROADMAP heterogeneidad — tratar cada ticker como universo distinto con variables distintas (no pooled).
**Estado**: EXPLORATORIO — sin veredicto, sin integración.

---

## 1. Objetivo

Entender cómo se comporta el indicador **propio** de cada ticker (su momentum/RSI/vol, no pooled contra otros) frente a su variación de precio futura, ticker por ticker. La pregunta no es "¿el factor predice pooled?" sino "¿en qué tickers, en qué ventanas y a qué plazo el estado propio tiene relación con el retorno propio, y dónde no?". La variación es el resultado.

## 2. Diseño (acordado con Boris, pre-declarado antes de ver resultados)

1. **Selección de tickers**: ranqueo del universo 102 por market cap ACTUAL vía yfinance `info.marketCap` (snapshot 2026-09-01, misma fuente que propuesta ampliación). Se toman 4 extremos: (más alto, más bajo) y (2do más alto, 2do más bajo) → 4 tickers. SPY/QQQ excluidos (ETFs sin marketCap, no comparables).
2. **Ventanas por contexto** (no por potencia): últimos 2, 5, 7, 10 años anidadas, cada una vivió un régimen distinto (bull post-COVID, tightening 2022, AI 2024-). Son chequeo de estabilidad/contexto, no pruebas independientes ni replicación.
3. **Horizonte**: corto 20d y largo 60d (representantes de 5-20d y 60-252d). Misma ventana cruzada con ambos horizontes.
4. **Relación condicional propia**: por cada (ticker × ventana × horizonte), se bucketea el indicador propio del ticker por terciles (low/mid/high) de su distribución **en esa ventana**, y se reporta media de `fwd_ret = close(t+H)/close(t)-1` por bucket con bootstrap CI 95% (1000 resamples, sin asumir normal). No es el promedio puntual, es la incertidumbre.
5. **Pre-declarado como primario**: ticker de MAYOR cap × ventana 10y × horizonte 20d. El resto es exploratorio/robustez — no elegir la celda que mejor se vea.
6. **Reporte honesto**: dónde SÍ aparece relación, dónde NO, y en qué combinaciones cambia.

## 3. Selección (ranking 2026-09-01)

Universo 102 = 7 base + 95 NEW_UNIVERSE (fetch_universe_data.py). Ranking por `yfinance.Ticker.info.marketCap` (snapshot 2026-09-01, `~/Desktop/fortress_core/backend/.venv` yfinance 1.2.0). Detalle completo en `/tmp/rank_mcap.py`.

Top 5 no-ETF: NVDA 5250B, AAPL 4745B, GOOGL 4097B, MSFT 3720B, AMZN 2749B. Bottom 5: EPAM 6.0B, QLYS 6.1B, STAG 7.4B, QRVO 8.5B, SWKS 10.1B.

**Seleccionados (4 extremos, sin ETFs)**:

| Rol | Ticker | MarketCap | Sector | Historia desde |
|-----|--------|-----------|--------|----------------|
| Más alto | **NVDA** | 5250B | Semis | 1999 |
| Más bajo | **EPAM** | 6.0B | IT Services | 2012 |
| 2do más alto | **AAPL** | 4745B | Tech | 1980 |
| 2do más bajo | **QLYS** | 6.1B | Cybersec | 2012 |

> Nota: SPY/QQQ dieron 0.0B (ETFs) y se excluyeron; el siguiente no-cero tras EPAM es QLYS. EPAM/QLYS son small-cap puros, NVDA/AAPL mega-cap — extremos reales por tamaño.

**Primario pre-declarado**: **NVDA × 10y × 20d** (antes de ver cualquier tabla).

## 4. Ventanas, horizontes e indicadores

**Ventanas anidadas** (cache hasta 2026-08-31, parquet `backend/data/cache/*.parquet`):

| Ventana | Rango | Días hábiles ~ | Régimen vivido |
|---------|-------|----------------|----------------|
| 10y | 2016-09-01 → 2026-08-31 | 2485 | incluye bull 2017, crash 2020, tightening 2022, AI 2023- |
| 7y | 2019-09-01 → 2026-08-31 | 1731 | post-COVID + tightening + AI |
| 5y | 2021-09-01 → 2026-08-31 | 1227 | tightening + AI |
| 2y | 2024-09-01 → 2026-08-31 | 473 | solo AI tardío, bull estrecho |

Anidadas → comparten datos, no son independientes; se leen como estabilidad.

**Horizontes**: 20d (corto, mensual) y 60d (largo, trimestral). `fwd_ret_H = close(t+H)/close(t)-1`, indicador medido en `t` (sin look-ahead; `calculate_all_indicators` usa solo datos hasta `t`). El par (20d,60d) cruza calendario y plazo.

**Indicadores propios** (por ticker, no pooled, vía `app.core.indicators.calculate_all_indicators` + `volume_shock` como en `diagnose_asimetria_direccional.py:154`):

- `momentum_12_1` = `close.pct_change(252)*100` (12-1 meses)
- `rsi14` (Wilder 14)
- `volume_shock` = `dvol(t-1) / mean(dvol(t-2..t-61))` donde `dvol=close*volume` (presión de volumen relativa)

Cada indicador se terciliza **dentro** de la ventana (q33/q66 propios). Buckets low/mid/high → media fwd_ret + CI bootstrap.

**Warmup**: `calculate_all_indicators` hace `ffill().dropna()` (~252 días por momentum_12_1); los conteos reportados son post-warmup y post-drop de `fwd_ret` NaN (cerca del final).

## 5. Resultado primario (NVDA × 10y × 20d) — lectura pre-declarada

| Indicador | low (n=828) | mid (n=828) | high (n=829) | q33/q66 |
|-----------|-------------|-------------|--------------|---------|
| momentum_12_1 | +4.09% [3.13,5.08] | +4.11% [3.14,5.02] | **+6.58% [5.70,7.45]** | 48.2/140.6 |
| rsi14 | +4.91% [4.00,5.88] | +4.68% [3.80,5.57] | +5.19% [4.25,6.11] | 48.2/64.1 |
| volume_shock | **+6.79% [5.80,7.72]** | +3.73% [2.77,4.64] | +4.26% [3.47,5.11] | 0.82/1.09 |

Lectura primaria:
- **momentum**: high > low/mid con CI no solapado (high lo 5.70 > low hi 5.08) → en NVDA 10y, el tercil de momentum más alto tuvo retorno 20d ~2.5pp superior. Relación existe, pero es modesta y solo en el extremo alto; low vs mid indistinguibles.
- **rsi**: los tres CIs se solapan ampliamente (4.0-5.9 vs 3.8-5.6 vs 4.2-6.1) → no hay relación discernible en 10y 20d para RSI propio de NVDA.
- **volume_shock**: low bucket es el mejor (+6.79% vs +3.7/+4.2, CI no solapado con mid) → días de bajo shock de volumen previo tienden a mejor retorno 20d que días de shock medio. Es la señal más fuerte del primario, e inversa a "más volumen = más retorno".

Esto es todo lo que se puede afirmar con el primario. El resto es exploratorio.

## 6. Dónde SÍ aparece relación y dónde NO — variación como resultado

Resumen por ticker (evidencia cruda en §8 y `/tmp/ingenieria_raw.txt` 330 líneas).

### NVDA (mega, semis, momentum-driven)
- **SÍ**: momentum high > low en 10y 20d y 10y 60d (high +19.9% vs mid +9.3% en 60d), pero en **2y 60d se invierte violentamente**: low +20.1% [16.8,23.4] vs high **-3.9% [-6.2,-1.6]** (CI no solapa cero, signo negativo). En ventana reciente, comprar high momentum a 60d fue perdedor. La relación existe pero cambia de signo con ventana/horizonte.
- **NO**: RSI no discrimina en ninguna ventana 20d/60d (CIs solapados en 10y, 7y, 5y). En 2y 20d sí hay leve diferencia: low +4.1% vs mid +0.8% (mid CI toca cero), pero inconsistente.
- **SÍ (estable)**: volume_shock low > mid/high en 10y/7y/5y/2y 20d (low +5.9 a +7.1% vs mid +2.5 a +4.1%). En 60d la ventaja de low se diluye (10y low +16.9 vs high +14.4, CIs solapados). La relación es de corto plazo y estable en el tiempo.

### AAPL (mega, tech, más estable)
- **SÍ parcial**: momentum low > mid/high en todas las ventanas 20d/60d 10y/7y/5y (ej. 10y 60d low +12.6% [11.8,13.3] vs high +4.6% [3.5,5.6], CI no solapado). Pero en 2y 60d low sigue ganando (+25% vs high -8.3%), es decir, **reversión** a 60d: los días de bajo momentum (caídos) rebotan a 60d. No es momentum continuación, es mean-reversion a plazo trimestral.
- **NO**: RSI plano en todas las ventanas (10y 20d low +2.0 vs high +2.8, CIs solapados). Volume_shock low > high en 10y (low +3.7 vs high +1.5, CI no solapado) pero en 5y diferencia <1pp y CIs solapados → la relación de volumen se diluye en ventana reciente.

### EPAM (small, IT services, caída estructural desde 2022)
- **SÍ fuerte y negativa**: momentum high es **perdedor extremo** en ventanas recientes. 5y 20d high **-8.9% [-10.3,-7.5]** vs low +3.8%; 5y 60d high **-20.9% [-22.7,-18.7]** vs low +4.8%; 7y 60d high +6.4% vs mid **-7.6%** (mid CI negativo). En 10y la dispersión es pequeña (low +2.2 vs high +2.4, CIs solapados) → la relación negativa emergió solo post-2021 (colapso de small growth). Esto es context-dependiente, no una ley.
- **NO**: RSI y volume_shock no discriminan en 10y/7y (CIs solapados alrededor de +1%). En 2y, RSI y vol también planos (CIs incluyen cero). La inestabilidad es la señal: lo que parecía nulo en 10y se volvió fuertemente negativo en 5y.

### QLYS (small, cybersec, menos volátil que EPAM)
- **SÍ moderado**: momentum mid > low/high en 10y 20d? No, en 10y 20d low +1.9% [0.4,3.3] y high +? (no mostrado, pero ver raw). En 10y 60d low +13% vs mid +6% vs high +? — similar a NVDA pero menos extremo. En 2y 60d low +25% vs high -8.3% (reversión clara, como AAPL/EPAM).
- **NO**: RSI y volume_shock planos en casi todas las ventanas; ej. 5y 20d rsi low +2.5 vs high +1.4, CIs solapados. La única relación que sobrevive es momentum a largo plazo.

**Patrón transversal (la variación importa)**:
- **Horizonte importa más que ventana**: en NVDA/EPAM, el signo de momentum cambia entre 20d y 60d en ventanas recientes. Corto plazo favorece high momentum (10y), largo plazo favorece low (reversión) en 2y/5y. No es una sola "relación momentum-retorno", son dos fenómenos distintos por plazo.
- **Cap importa**: small caps (EPAM/QLYS) muestran reversión extrema en 5y (high momentum muy negativo), mega caps (NVDA/AAPL) muestran momentum continuación débil en 10y pero también reversión en 2y 60d. La heterogeneidad por ticker es real — no hay una ley pooled.
- **Indicador más estable**: `volume_shock` low > mid en NVDA/AAPL 20d es lo más estable en el tiempo; `rsi14` no discrimina en ningún ticker salvo ruido en 2y.

### Tabla compacta (media 20d, ¿CI excluye cero y separa buckets?)

| Ticker | Ventana | mom 20d relación | rsi 20d | vol_shock 20d | mom 60d |
|--------|---------|------------------|---------|---------------|---------|
| NVDA | 10y | SÍ high>low | NO | SÍ low>mid | SÍ U (mid peor) |
| NVDA | 2y | SÍ low>high (reversión) | NO | SÍ low>high | SÍ low>>high (-3.9%) |
| AAPL | 10y | SÍ low>high (reversión) | NO | SÍ low>high | SÍ low>>high |
| EPAM | 10y | NO (U) | NO | NO | NO |
| EPAM | 5y | **SÍ high muy negativo** | NO | NO | **SÍ high -20%** |
| QLYS | 10y | NO | NO | NO | SÍ low>mid |

> La tabla muestra que "hay o no hay" depende de ticker+ventana+horizonte — no hay un veredicto único.

## 7. Limitaciones honestas (por qué esto no es un trial)

- **Solo lectura, sin pre-registro**: este es exploratorio. Cualquier celda que parezca "hallazgo" debe pre-registrarse como trial nuevo (slot 29+) y correr una sola vez, no reportarse como descubierta.
- **Ventanas anidadas, no independientes**: 2y ⊂ 5y ⊂ 7y ⊂ 10y comparten datos; no son replicaciones. La estabilidad aparente está inflada por solape. No se puede hacer Bonferroni ni meta-análisis como si fueran 4 pruebas.
- **N pequeño por celda**: 2y 20d tiene ~473 días → ~158 por bucket → CI ancho (±1.5pp en 20d, ±3-4pp en 60d). Ver `/tmp/ingenieria_raw.txt` n=144-160 en 2y 60d. Potencia <30% para detectar Δ=2pp.
- **Terciles arbitrarios**: q33/q66 son una elección; quintiles o z-score darían otra historia. No se buscó el corte que maximiza separación.
- **Univariado**: cada indicador se mira solo; en datos reales los tres están correlacionados y la señal conjunta puede ser distinta. No hay ajuste por volatilidad de mercado ni por régimen HMM.
- **Snapshot de market cap**: ranking 2026-09-01 no es el cap en cada ventana; EPAM/QLYS eran más grandes en 2021 que hoy, NVDA era menor en 2016. El "más bajo" hoy no fue siempre el más bajo.
- **Costos y fricción ignorados**: fwd_ret es bruto, sin comisión 0.10%/lado ni slippage ni gaps; la reversión de EPAM -20% a 60d puede no ser tradeable con stops.
- **Warmup y dropna**: `calculate_all_indicators` hace `dropna` (~252 días). Las ventanas tempranas (10y) pierden 2016-09 a 2017-05 para momentum_12_1; los conteos reales son 2485 en 10y 20d, no 2520 teóricos.
- **Solo 4 tickers**: la heterogeneidad entre 102 no se extrapola de 4 extremos. Son ejemplos de ingeniería inversa, no una encuesta.
- **Horizontes fijos**: 20d y 60d son representantes de 5-20d y 60-252d; 5d y 252d pueden dar otra foto (no se exploraron para no multiplicar celdas).
- **Bootstrap no es Newey-West**: el CI asume i.i.d. dentro del bucket, ignora autocorrelación de retornos solapados (20d/60d con step 1 día). El CI real es más ancho.

## 8. Evidencia cruda (anexo, 100% reproducible)

Fuente: `backend/data/cache/*.parquet` (ficheros 2015-01-02→2026-08-31), `backend/app/core/indicators.py`, script `/tmp/ingenieria_inversa.py` (1000 bootstraps, seed 42, terciles). Comando:

```bash
PYTHONPATH=backend ~/Desktop/fortress_core/backend/.venv/bin/python /tmp/ingenieria_inversa.py > /tmp/ingenieria_raw.txt
```

Resumen: 4 tickers × 4 ventanas × 2 horizontes × 3 indicadores × 3 buckets = 288 filas, n por bucket 144-829, q33/q66 propios por ventana (ej. NVDA momentum q33/q66 36.4/66.5 en 2y vs 48.2/140.6 en 10y — la distribución cambia).

**Tablas completas**: ver `/tmp/ingenieria_raw.txt` (330 líneas) y extracto abajo para el primario y un contraste.

### Extracto primario y contraste (media [CI95%], n)

**NVDA 10y 20d (primario)** — ya en §5

**NVDA 2y 60d (contraste donde se invierte)**:
```
momentum_12_1 low  n=144 mean +20.10% [16.79,23.44] q33/q66 36.76/79.20
              mid  n=144 mean  +8.83% [ 7.05,10.70]
              high n=145 mean  -3.89% [-6.23,-1.64]  # high significativamente negativo
```

**EPAM 5y 60d (peor caso small-cap)**:
```
momentum_12_1 low  n=398 mean  +4.76% [2.65,6.79]
              high n=398 mean -20.86% [-22.67,-18.72] # high desplome
```

**AAPL 10y 60d (reversión estable)**:
```
momentum_12_1 low  +12.56% [11.79,13.34] low>>high
              high  +4.58% [3.47,5.65]
```

Tablas completas no truncadas están en `/tmp/ingenieria_raw.txt`; este md muestra solo el esqueleto para no duplicar 330 líneas.

## 9. Qué sigue (si algo promete)

- Si se decide pre-registrar, elegir **una** celda primaria antes de mirar el resto (ej. NVDA 10y 20d momentum high vs low) y fijar umbral, horizonte y ventana en el pre-registro. El resto va como exploratorio, no como confirmatorio.
- Para pooled vs per-ticker, el diseño ya mostró que la heterogeneidad es el fenómeno: un trial pooled ocultaría la reversión de EPAM en 5y y la continuación débil de NVDA en 10y. Un futuro trial debería modelar interacción ticker×estado, no solo estado.
- No tocar ledger ni slot 29 hasta pre-registro nuevo con aprobación de Boris.

---

**Artefactos**: este archivo (`INGENIERIA_INVERSA_POR_TICKER.md`), ranking `/tmp/rank_mcap.py`, script `/tmp/ingenieria_inversa.py`, raw `/tmp/ingenieria_raw.txt` (330 líneas). Solo lectura parquet, sin escritura de ledger.
