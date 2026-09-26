# Análisis OpenCode — Híbrido objetivo × subjetivo (handoff cb13ce3)

**Fecha**: 2026-09-25 · **Autor**: OpenCode (handoff de Cline, commit `cb13ce3`, `HANDOFF_HIBRIDO_OBJETIVO_SUBJETIVO.md`) · **Alcance**: solo definición, sin ejecución de trial, sin modificación de ledger, sin `GOVERNANCE_LLM_ENABLED`.
**Gate vigente**: `backend/app/core/gate_window.py:37` `GATE_START_DATE=2026-09-02` + `MAX_GATE_DAYS=90` → `get_gate_end_date()` = **2026-12-01** inclusive. `is_within_gate_window(2026-12-01)=True`, `2026-12-02=False` (verificado). Durante la ventana solo `bugfix`/`infraestructura` pasan (`GATE_CATEGORY_ALLOW_LIST` línea 47).

---

## 1. Decisiones D1–D7 resueltas (variante elegida, fundamento, descarte)

### D1 — Variante: **B (puerta/abstención)** como primaria; A como análisis de sensibilidad secundario (no gate)

- **Elegida**: B — la pata subjetiva/Acción actúa como **filtro que degrada INVERTIR → VIGILAR** y se mide **VPP bajo abstención** + **PnL neto filtrado vs siempre-operar**. Es el protocolo ya existente en `backend/app/core/conformal.py:219` `vpp_bajo_abstencion` y `backend/app/api/routes/decision.py:72` `M2 abstención (intervalo muy ancho) -> VIGILAR`.
- **Fundamento**: (i) precedent de instrumento conforme ya operativo: `decision.py:_fit_calibrators:76` calibra M2 sobre ventana móvil 730d con `alpha=0.10`, `n>=30` (`conformal.py:125`); la corrección estructural de residuos relativos (`conformal.py:140-168`) habilita abstención diferencial — antes el ancho era constante (100% o 0%). (ii) Alineado a tesis de Boris ("perder mejor"): convertir INVERTIR en VIGILAR con razón es medible sin exigir edge nuevo. (iii) Menor demanda de potencia que A: B compara VPP sobre mismo universo filtrado, no partición de señal en subgrupos que exige N grande.
- **Descartada**: **A (condicional) como gate primario**. Mide edge condicional (Δ rendimiento entre grupos particionados por estado subjetivo). Descarte: confunde ranking con ejecución, exige ~2× observaciones efectivas para mismo poder (dos grupos), y sería segundo trial si B muestra interacción. No se elimina: se reporta como **sensibilidad** (ΔPnL NW entre grupos, nota informativa, sin veredicto binario) para no perder información.

### D2 — Familia: **nueva `hibrido_objetivo_x_subjetivo` — declaración post-gate, sin registro aún**

- **Elegida**: familia nueva `hibrido_objetivo_x_subjetivo`. La pregunta es **interacción**, categoría distinta a `motor_signal` (inyección de score) y `signal_diagnosis` (diagnóstico de señal pura). Merece presupuesto Bonferroni propio. `current_threshold("hibrido_objetivo_x_subjetivo")` con 0 consumidos = **0.90** (`trial_registry.py:932` `1-(1-0.90)/1`). Primer trial: `n_trials_consumidos=1`, umbral declarado **0.90** (sin hardcodear, derivado del ledger).
- **Fundamento**: evita contaminar `signal_diagnosis` (29 consumidos → umbral `0.9966` verificado) y `motor_signal` (13 → `0.9928`) con una hipótesis que no es ni diagnóstico ni inyección directa. Limpia trazabilidad; si el híbrido se refuta, su presupuesto no arrastra otras familias.
- **Descartadas**: (i) **Reutilizar `signal_diagnosis`**: umbral 0.9966 exige potencia inalcanzable para N≈150 T_eff del híbrido con H=20; castiga la interacción por historia ajena. (ii) **`motor_signal`**: presupuesto arrastrado (13) endurece vara sin que el híbrido inyecte score al motor — modula la **puerta** M2 ya existente. (iii) Subfamilia dentro de existente: no existe mecanismo de subfamilia en `trial_registry.py` (solo `familia` string).
- **Gate**: no se registra ahora. Pre-registro congelado con `fecha=2026-12-02` (primer día fuera del gate). Slot se reserva post-gate vía `register_trial_reservation` con `n>=1` obligatorio (`trial_registry.py:463`).

### D3 — Pata: **solo Acción (COT)** como primer trial

- **Elegida**: Acción = COT E-MINI S&P 500 (`cot_lev_net_pct`, `cot_asset_net_pct`, etc., `market_sentiment.py:292-296` divididos por `cot_oi`). Historia larga, gratis, point-in-time verificado `shift(1)+ffill` (`market_sentiment.py:277`).
- **Fundamento**: (i) datos ya disponibles: `COT_URL` `com_fin_txt_{year}.zip` (`market_sentiment.py:91`) con descarga por año; extender es gratis. (ii) AAII/FinBERT (Expectativa) no tienen vintage: texto no se puede reconstruir hacia atrás, solo acumular. (iii) FinBERT earnings existe (`earnings_sentiment.py:623` líneas) pero cobertura limitada y sin caño vintage; AAII semanal con umbral capitulación `<-15` ya medido (`ANALISIS_MIEDO_20260914.md` §2). (iv) Si son dos patas, son **dos trials** (handoff §4 D3) — diluye corrección Bonferroni.
- **Descartadas**: (i) **Expectativa sola** como primer trial — diferida a trial 2 con su propio pre-registro tras acumular texto crudo inmutable (patrón `collect_iv_surface.py`). (ii) **Ambas simultáneas**: confunde atribución; si interacción existe no sabríamos qué pata la explica.

### D4 — Horizonte H y métrica: **H=20 ruedas, métrica primaria VPP + PnL neto, ejecución lag=1**

- **Elegida**: H=`CALIBRATION_HORIZON_DAYS=20` (`backtest_engine.py:27`) — precedente de la casa: replay de calibración en `decision.py:_fit_calibrators:76` y `backtest_engine._build_calibration_dataset:148` con stride 5. Métrica primaria: **VPP bajo abstención** (`conformal.py:242` aciertos de signo sobre operados) + **PnL neto filtrado vs baseline siempre-operar** con `execution_lag_days=1` (`backtest_engine.py:334`), costos `commission=0.001, slippage=0.0005`, t-NW sobre serie diaria y Bonferroni (`n_family=1` → `z(1-0.05)=1.644` para MDE; reporte con `circular_block_bootstrap_ci`).
- **Fundamento**: 20d alinea calibración, barrier labeling y validación walk-forward existente; cambiar H movería el criterio post-hoc (violación ONBOARDING regla 1).
- **Descartadas**: (i) H=5/60/125 ya auditados (`horizon_audit_5d_10d`, `horizon_largo_60d_125d` — todos NO_CUMPLE) sin razón para re-elegir. (ii) IC como métrica primaria: refutado que IC ≠ PnL (ridge +0.0156 → DSR 0/3, trial #13 `RESUMEN_VALIDACION_VARIABLES.md` §3). (iii) lag=0: bug T0.2 arreglado 2026-08-20 (`backtest_engine.py:338`, Sharpe 0.57→0.38) — repetir lag 0 invalida veredicto.

### D5 — COT: **sí, extender hacia atrás a 2010 (mínimo) antes del trial**

- **Elegida**: cambiar `COT_START_YEAR=2019` (`market_sentiment.py:93`, duplicado en `institutional_fingerprint.py:47`) a **2010** (o 2006 si CFTC lo sirve) mediante `fetch_cot_years(list(range(2010, as_of.year+2)))`. Gratis, mismo patrón de URL, ~10 años extra.
- **Fundamento**: T_eff sin autocorr = T/h. Con H=20, añadir 10 años (~2520 días) → +126 T_eff. MDE cae de `0.0192 (T=3000)` a `0.0171 (T=3780)` (`mde_power.py:mde_ic`), ganancia de potencia sin costo. Respeta doctrina "no cerrar puertas".
- **Descartada**: **Mantener 2019** — trunca historia por constante arbitraria; pierde potencia gratuita y deja T≈150 (2019-2026) en el filo del detectable para efecto pequeño. Extender no introduce lookahead (datos CFTC ya publicados).
- **Implementación**: 1 script de migración que re-descarga `cot_2010..2018.parquet`; verificar market `E-MINI S&P 500` (`market_sentiment.py:153`) en años viejos antes de congelar.

### D6 — Reserva: **no reservar ahora; pre-registro congelado para `register_trial_reservation` el 2026-12-02**

- **Elegida**: escribir pre-registro ahora, **registrar RESERVED solo post-gate** (`fecha=2026-12-02`, primer día fuera del gate, `gate_window.py:get_gate_end_date`). `_gate_window_check:755` bloquea cualquier `categoria` fuera de `{"bugfix","infraestructura"}` dentro del gate — un hibrido `investigación` caería en `GATE_BLOQUEADO`.
- **Fundamento**: respeta gate 90 días hasta 2026-12-01 vigente; evita escape `FORTRESS_ALLOW_GATE_TRIAL` (emergencia declarada, no corresponde). Slot Bonferroni `n>=1` obligatorio en RESERVED (`trial_registry.py:463`) se consume post-gate, no durante.
- **Descartadas**: (i) **Reserva inmediata** — gate la rechaza (_raise `TrialRegistryError`). (ii) Backdating a 2026-09-01 — deshonesto, viola `_parse_fecha` y trazabilidad. (iii) `register_trial` directo COMPLETED — exige `veredicto`+`artefacto` (`trial_registry.py:404`) y viola "no correr".

### D7 — MDE/potencia: **declarar y publicar; veredicto INEJECUTABLE si no alcanza**

- **Elegida**: `_mde_check:344` (`scripts/mde_power.py:mde_ic`) con diseño declarado: `n_symbols=50`, `T_dates≈3780` (2010-2025, 15y), `horizon_days=20`, `n_family=1`, `effect_plausible=0.10` (`MDE_EFFECT_PLAUSIBLE:126`), `ic_std=1/sqrt(49)=0.1428`. Resultado: `T_eff=189`, `MDE_IC≈0.017`, `ejecutable=True` (0.017 < 0.10). Si se diseña con solo 2019-2025 (T≈1500 → T_eff≈75 → MDE≈0.027) sigue ejecutable, pero más ajustado con autocorr `rho=0.2` → MDE≈0.032. Se congela `autocorr={1:0.2}` conservador.
- **Fundamento**: sin MDE, un NO_CUMPLE con diseño ciego es teatro (`trial_registry.py:735` → `INEJECUTABLE` con `n_consumidos=0`, no cuenta como refutación). Declarar antes evita "no pude detectarlo" vendido como "no existe".
- **Descartadas**: (i) No declarar MDE (lo no declarado no se juzga — `trial_registry.py:343` — pero deja el trial vulnerable a ser tildado de sub-potente post-hoc). (ii) Fijar `effect_plausible` <0.05 (ICIR realista 0.02-0.08) subestimaría el edge plausible y volvería todo INEJECUTABLE por diseño.

---

## 2. Verificación contra artefacto (ONBOARDING regla 1 — también aplica a lo que escribió Cline)

| Afirmación del handoff | Artefacto real (`file:line`) | Veredicto | Corrección si aplica |
|---|---|---|---|
| `_STATE_RANK` y `_state_rule` con 6 razones incl. `M2 abstención` | `backend/app/api/routes/decision.py:55` y `:58-73` — 6 ramas exactas, `m2["abstenerse"] -> VIGILAR "M2 abstención (intervalo muy ancho)"` | ✅ Correcta | — |
| M2 split-conformal α=0.10, n≥30 | `backend/app/core/conformal.py:95` `alpha=0.10`; `:125` `len<30 raise`; `decision.py:93-95` calibra M2 solo si `n>=30` | ✅ Correcta | — |
| Pata subjetiva existe: `market_sentiment.py` AAII 1987 + COT + FRED con `shift(1)+ffill` | `market_sentiment.py:12` AAII desde 1987; `:91` `COT_URL`; `:85` `FRED_SERIES`; `:276-278` `_align shift(1).ffill().reindex` | ✅ Correcta | Línea exacta es `258-278` para `_align` + `shift(1)` en `build_sentiment_frame`; `258-278` cubre `walcl/rrpon/wresbal/aaii` pero la implementación de `_align` está en `:276-278` |
| `thermometer.py` NO existe en main ni historia | `git log --all -- '**/thermometer.py'` vacío; `ls backend/app/core/thermometer.py` no existe | ⚠️ Parcial | **Lógica sí existe integrada**: `backend/app/core/institutional_fingerprint.py:335` `build_thermometer_frame` (vol_a/vol_b/phase_b_quiet/retest) + `fetch_fear_greed:253` y `fetch_put_call_ratio:287`. `ANALISIS_CICLO_INSTITUCIONAL.md:28-30` describe `thermometer.py` prototipo en rama `test-kilo-orca` no mergeada a `main`. Corrección: no existe **módulo standalone** en `main`; sí existe **función termómetro** en `institutional_fingerprint.py` sin endpoint congelado ni cache `thermometer_*.parquet` en `main` |
| `COT_START_YEAR=2019` trunca historia | `market_sentiment.py:93` y `institutional_fingerprint.py:47` ambos `=2019` | ✅ Correcta | — |
| Cache COT stale 2026-08-04 | `ANALISIS_MIEDO_20260914.md:24` "último dato en cache **2026-08-04** (6 semanas de lag)" | ✅ Correcta | Hoy `backend/data/cache/cot_*.parquet` inexistente (cache limpiado tras incidente 2026-09-14 `ANALISIS_MIEDO.md` §5) — el stale histórico es verificable solo por el documento |
| `professor_memory.json` vacío | `backend/data/professor_memory.json:1` `{"lessons":[],"agent_history":{},"weight_adjustments":{}}` | ✅ Correcta | — |
| `rag_memory.json` 6 lecciones SYSTEM | `backend/data/rag_memory.json` 6 entries `agent=SYSTEM` | ✅ Correcta | Claim dice 6 → verificado 6 |
| `DEFAULT_N_TRIALS` ya resuelto a sentinel + fallback 29 | `backend/app/core/backtest_engine.py:658` `=None # sentinel`; `:660-678` `_resolve_default_n_trials()` lee `consumed_budget("signal_diagnosis")` con fallback 29 | ✅ Correcta | — |
| `consumed_budget` y `current_threshold` por familia | `trial_registry.py:915` `consumed_budget`; `:932` `current_threshold = 1-(1-0.90)/n` con `n=consumidos+1` | ✅ Correcta | 51 entradas totales (29 `signal_diagnosis`, 13 `motor_signal`) verificadas |
| `register_trial_reservation` consume slot Bonferroni n>=1 | `trial_registry.py:690` + `:463` `n_trials_consumidos<1 raise` | ✅ Correcta | — |
| Job diario COT/AAII no existe; `dataupdater` solo OHLCV+FinBERT on-demand en `institutional_fingerprint.py:460` `predict.py:135` | `scripts/data_updater.sh` solo 2 pasos (OHLCV + `accumulate_earnings_sentiment`); `institutional_fingerprint.py:460` `fetch_cot_years(RANGE)`; `backend/app/api/routes/predict.py:135` `fetch_aaii()` | ✅ Correcta | `predict.py:135` es `aaii=fetch_aaii()` dentro de endpoint predict — on-demand confirmado |
| Finnhub nunca produjo datos, mapeo no validado | `COMPARACION_FUENTES_DATOS.md:18` `cache_fundamentals` inexistente; `backend/data/cache_fundamentals*` no existe (verificado `ls`) | ✅ Correcta | Live smoke sí da 200 (`COMPARACION §8.2`) pero sin persistencia en repo |
| Gate 90 días hasta 2026-12-01 | `gate_window.py:42` `MAX_GATE_DAYS=90`; `GATE_START=2026-09-02` → `get_gate_end_date()=2026-12-01` inclusive | ✅ Correcta | — |

---

## 3. Pre-registro (resumen — documento completo en `PRE_REGISTRO_HIBRIDO_OBJETIVO_X_SUBJETIVO.md`)

- **Familia**: `hibrido_objetivo_x_subjetivo` (nueva, `n_consumidos=1`, `fecha=2026-12-02` post-gate)
- **Hipótesis H1 (falsable)**: el filtro Acción (COT net %OI) mejora el resultado del motor objetivo: **VPP_filtrado > VPP_baseline** Y **PnL_net_filtrado > PnL_net_baseline** (costos reales 0.10%/lado, lag=1) de forma Bonferroni-significativa.
- **H0**: el estado COT no condiciona el resultado del motor (diferencia = ruido).
- **Umbral aplicado**: `current_threshold(hibrido_objetivo_x_subjetivo)=0.90` (1 trial, `trial_registry.py:932`), derivado del ledger, nunca hardcodeado.
- **Diseño**: `n_symbols=50`, `T≈3780` (COT 2010-2025), `H=20`, `T_eff≈189`, `MDE_IC≈0.017` (`mde_power.py:mde_ic`, `autocorr {1:0.2}`), `effect_plausible=0.10` → **ejecutable**. Si `MDE>0.10` → `INEJECUTABLE` (`STATUS_INEJECUTABLE:135`, `n_consumidos=0`).
- **Ventana datos**: `ventana_datos: {modo:"historico", hasta:"2025-09-01"}` — respeta `HOLDOUT_CUTOFF_DATE=2025-09-01` (`trial_registry.py:104`), nunca toca holdout sellado. `cache_manifest_sha256` congelado vía `attach_cache_snapshot` (`trial_registry.py:595`).
- **Corrección**: Bonferroni `n_family=1` (un solo contraste primario VPP+PnL; sensibilidad A no cuenta). `validate_umbral_aplicado` (`trial_registry.py:891`) compara pre-registro vs ledger mecánicamente.
- **Criterio éxito**: VPP_filtrado > VPP_baseline con `p<0.05` (Bonferroni) y ΔPnL diario t-NW > umbral, `n_operados>=30` por grupo, `abstención<=0.80`; 2/3 ventanas (si se particiona) o panel completo según se congele. **NO_CUMPLE es útil** (filtra o no — ambas respuestas sirven).
- **No se corre, no se registra, no se habilita LLM** hasta 2026-12-02.

---

## 4. Hallazgos y pendientes (sin tocar código)

1. Extender COT a 2010 antes del trial (1 script, gratis).
2. Acumular texto crudo diario inmutable (colector + plist, patrón `collect_iv_surface.py`) para vintage de Expectativa — solo post-gate como trial 2.
3. No revivir Finnhub/pagar feeds hasta validar interacción con datos gratis.
4. Verificar `COT_MARKET="E-MINI S&P 500"` en años 2010-2018 (mismo `Market_and_Exchange_Names`).

---

*Análisis sin ejecución — las 7 decisiones quedan escritas, verificadas contra `file:line`, y el pre-registro congelado respeta el gate 2026-12-01.*
