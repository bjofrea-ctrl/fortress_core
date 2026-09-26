# PRE-REGISTRO — Híbrido objetivo × subjetivo: ¿la pata Acción (COT) condiciona el resultado del motor?

**Fecha de pre-registro**: 2026-09-25 (congelado) · **Fecha de registro en ledger**: 2026-12-02 (primer día post-gate, `gate_window.py:37` GATE 2026-09-02..2026-12-01)
**Estado**: 🔵 CONGELADO — NO EJECUTADO (documento para aprobación de Boris, no se corre ni se registra hasta post-gate)
**Autor**: OpenCode — análisis del handoff `HANDOFF_HIBRIDO_OBJETIVO_SUBJETIVO.md` (commit `cb13ce3`, Cline 2026-09-25)
**Gate vigente**: `MAX_GATE_DAYS=90` → `2026-12-01` inclusive; este trial es `investigación` (no `bugfix`/`infraestructura`) → registro solo fuera de ventana (`trial_registry.py:755` `_gate_window_check`).

> Regla 1 ONBOARDING.md: umbral, corrección Bonferroni y criterio se escriben ANTES de correr. Este archivo NO se edita tras ver el número. `validate_umbral_aplicado` (`trial_registry.py:891`) lo verifica mecánicamente.

---

## 1. Hipótesis (una sola, falsable)

**Pregunta medible** (handoff §3): ¿el resultado del motor objetivo (PnL neto a H, lag=1, costos reales) cambia de forma estadísticamente significativa según el estado de la pata Acción medido point-in-time el mismo día?

- **H0 (nula)**: el estado COT del día t (point-in-time, `shift(1)+ffill`, `market_sentiment.py:276`) **no condiciona** el resultado del motor: `E[PnL|filtro] = E[PnL|siempre-operar]` y `VPP_filtrado = VPP_baseline` (diferencia = ruido).
- **H1 (alternativa — falsable)**: filtrar por estado COT **mejora** el resultado: el instrumento que solo opera cuando la pata Acción acompaña tiene **VPP mayor** y **PnL neto mayor** que el baseline que opera siempre, de forma significativa tras corrección por comparaciones múltiples.

> Precedente: ridge purgado IC +0.0156 no se tradujo en PnL (trial #13, handoff §6.1). Por eso la métrica primaria es **PnL/VPP**, no IC.

---

## 2. Arquitectura del trial (variante B — puerta)

- **Motor objetivo**: `BacktestEngine.run` + `SignalEngine` con score `w_mom=0.6642,w_rsi=0.3358` congelado, gates `close>ema50>ema200, adx>=20, 40<rsi<75, volume_ratio>=1, score>=0.60` (`signal_engine.py:206-217`), `execution_lag_days=1` (`backtest_engine.py:334`), costos `commission=0.001, slippage=0.0005` (`backtest_engine.py:323`).
- **Instrumento conforme M2**: `ConformalAbstentionEngine(alpha=0.10)` (`conformal.py:95`), calibrado en ventana móvil 730d (`decision.py:83`), `n>=30` (`conformal.py:125`). El contrato de decisión es `decision.py:_state_rule:58` — `INVERTIR` solo si `regime!=3` + `gate` + `win_prob>=0.60` + `M2 no se abstiene`.
- **Filtro Acción (COT)**: estados del día t desde `market_sentiment.py:292` `cot_*_pct = net/OI*100` (4 series: `lev,asset,retail,dealer`). Cada día, el filtro es **binario** por `cot_asset_net_pct` (institucional) como señal primaria: `filtro_activo = cot_asset_net_pct > mediana_expanding_252` (causal, `institutional_fingerprint.py:544` `_expanding_zscore` + `_align_causal:414` `shift(1)+ffill`). Si el filtro no acompaña, el ticket se **degrada** `INVERTIR→VIGILAR` con razón `filtro COT no acompaña` (misma semántica que `M2 abstención`, `decision.py:72`).
- **Sin tocar producción**: inyección por subclase/wrapper del `BacktestEngine` que consulta el panel COT alineado; el motor real no se edita (ONBOARDING regla 3).

---

## 3. Datos — todo ya existente salvo extensión COT (gratis)

| Fuente | Rango pre-registro | Estado |
|---|---|---|
| `data/cache/*.parquet` OHLCV 50 símbolos | 2015-01-01 → 2025-09-01 (`HOLDOUT_CUTOFF_DATE`, `trial_registry.py:104`) | Existente (respeta holdout sellado, `ventana_datos.modo=historico`) |
| COT CFTC `com_fin_txt_{year}.zip` | **2010..2025** (extender `COT_START_YEAR=2019` → 2010, `market_sentiment.py:93`) | Acción pre-trial: re-descargar `cot_2010..2018.parquet`, verificar `COT_MARKET="E-MINI S&P 500"` en años viejos |
| Panel COT alineado | `cot_asset_net_pct` etc. como %OI, `shift(1)+ffill` a trading dates | Derivado, sin lookahead (`market_sentiment.py:276-296`) |
| Cache snapshot | `cache_manifest_sha256` congelado vía `attach_cache_snapshot` (`trial_registry.py:595`) | Obligatorio para reproducibilidad (`cache_integrity.py:snapshot_hash`) |

**No requiere**: GDELT, Finnhub, FMP, Benzinga, APIs pagas. `thermometer.py` no se necesita para D3=Acción.

---

## 4. Parámetros congelados (idénticos al baseline, salvo H)

| Parámetro | Valor | Fuente |
|---|---|---|
| H (horizonte forward PnL) | **20 ruedas** | `CALIBRATION_HORIZON_DAYS=20` (`backtest_engine.py:27`) |
| `execution_lag_days` | 1 | T0.2 fix 2026-08-20 |
| Costos | 0.001 + 0.0005 | `backtest_engine.py:323` |
| Ventana de evaluación | **2010-01-01 → 2025-09-01** (hasta holdout) | Holdout `2025-09-01` inclusive |
| `n_symbols` diseño | 50 (universo canónico) | `fetch_universe_data.NEW_UNIVERSE` |
| `n_trials_consumidos` | **1** | Familia nueva → `consumed_budget=0` → `n=1` |
| `umbral_aplicado` | `VPP_filtrado>VPP_baseline Y PnL_filtrado>PnL_baseline con p<0.05 Bonferroni (n_family=1)` — extraíble como `umbral_aplicado: "VPP_filtrado>VPP_baseline Y PnL_filtrado>PnL_baseline p<0.05 (n_family=1)"` | `trial_registry.py:844` regex |
| `familia` | `hibrido_objetivo_x_subjetivo` | Nueva (ver §6) |
| `seccion_doc` | `PRE_REGISTRO_HIBRIDO_OBJETIVO_X_SUBJETIVO.md §5` | — |

---

## 5. Criterio de éxito / fracaso — PRE-REGISTRADO y explícito

### 5.1 Métricas primarias (gate binario)

Por panel completo 2010-2025 (no sub-ventanas móviles para el gate primario):

| Métrica | Cálculo | Gate |
|---|---|---|
| **VPP_filtrado** vs **VPP_baseline** | `conformal.py:219` `vpp_bajo_abstencion` sobre operados filtrados vs todos operados | `VPP_filtrado > VPP_baseline` con `p<0.05` (test de proporciones NW, `n_family=1`) |
| **PnL neto filtrado** vs baseline | suma `pnl` (`backtest_engine.py:456`) filtrado vs siempre-operar | `mean(PnL_filtrado) > mean(PnL_baseline)` con `t-NW>1.64` (unilateral) y `n_operados>=30`, `tasa_abstencion<=0.80` |

| Resultado | Veredicto | Interpretación |
|---|---|---|
| Ambas métricas superan su gate con `n_operados>=30` y `abstención<=0.80` | **CUMPLE** | La pata Acción condiciona el resultado: el filtro COT mejora el motor. Justifica mantener el caño COT y considerar el filtro en `decision.py`. |
| Una o ninguna supera el gate | **NO_CUMPLE** | No hay evidencia de interacción: la pata Acción no mejora el motor (resultado útil — filtra o no filtra, ambas sirven, handoff §3). |
| `n_operados<30` o `abstención>0.80` en filtrado | **NO_CUMPLE** (nota: muestra insuficiente) | Diseño sin poder en ese régimen; no se promueve. |

> **NO_CUMPLE es útil** (handoff §3): cualquiera de las dos respuestas guía producto (mantener o descartar el filtro).

### 5.2 Métricas secundarias (informativas, no gate)

- Sensibilidad A (condicional): particionar días por estado COT (`cot_asset_net_pct` terciles) y reportar ΔPnL entre terciles con t-NW — sin veredicto.
- Sensibilidad `cot_lev_net_pct` y `cot_retail_net_pct` como filtros alternativos — sin veredicto.
- Cobertura empírica M2 (`conformal.py:202` `empirical_coverage` debe ≈0.90) — diagnóstico.

### 5.3 Umbral aplicado extraíble (para `validate_umbral_aplicado`)

```
umbral_aplicado: "VPP_filtrado>VPP_baseline Y PnL_filtrado>PnL_baseline p<0.05 (n_family=1, H=20, lag=1)"
```

---

## 6. Familia y presupuesto

| | Valor |
|---|---|
| Familia | `hibrido_objetivo_x_subjetivo` (nueva) |
| Consumido actual | **0** (no existe en `trial_registry.json` al 2026-09-25 — 51 entradas: 29 `signal_diagnosis`, 13 `motor_signal`, etc.) |
| `current_threshold` para este trial | **0.90** = `1-(1-0.90)/1` (`trial_registry.py:932`) |
| `n_trials_consumidos` | **1** (0→1) |
| `threshold` post-corrida (siguiente trial misma familia) | **0.95** = `1-0.10/2` |
| Si este trial usa `n_family=2` (Acción+Expectativa futuras) | umbral futuro `0.9666` (no aplica a este trial) |

Justificación familia nueva: pregunta de **interacción** — no es inyección `motor_signal` ni diagnóstico `signal_diagnosis` puro. Evita contaminar umbrales históricos (0.9966 y 0.9928) con hipótesis de naturaleza distinta.

---

## 7. Potencia / MDE (B5, `trial_registry.py:344` + `scripts/mde_power.py`)

Declaración `diseno_mde` para `_mde_check:344` (JSON en la entrada del ledger):

```json
"diseno_mde": {"n_symbols":50,"T_dates":3780,"horizon_days":20,"n_family":1,"autocorr":{"1":0.2},"ic_std":null,"effect_plausible":0.10}
```

- `ic_std = 1/sqrt(49)=0.1428` (`mde_power.py:ic_null_std`)
- `T_eff = 3780/20 / (1+2*0.2) ≈ 135` (horizonte + autocorr NW)
- `alpha_corr = 0.05/1 = 0.05`, `z=1.644`, `se=0.1428/sqrt(135)=0.0123`
- **`MDE_IC = 0.020`** (con `autocorr 0`, `MDE=0.017`; verificado con `fortress_clean_dl_venv` — `mde_ic(50,3780,20,1)`=0.0171) → **ejecutable** (0.020 < 0.10)
- Si viento en contra (`T=1500` solo 2019-2025, `MDE≈0.027-0.032`) sigue ejecutable. Si `MDE>0.10` el ledger lo marca `INEJECUTABLE` (`STATUS_INEJECUTABLE:135`, `n_consumidos=0`, no cuenta como refutación).

---

## 8. Ventana de datos y holdout (B4)

```json
"ventana_datos": {"modo":"historico","hasta":"2025-09-01"}
```

- `HOLDOUT_CUTOFF_DATE=2025-09-01` (`trial_registry.py:104`) — todo post-corte es OOS sagrado para C1 de diciembre y paper prospectivo (`HOLDOUT_PAPER_MODE`). Este trial **nunca lo toca**. `_holdout_check:310` lo bloquea por escritura si el texto del pre-registro declara rango que cruza el corte.

---

## 9. Artefacto, script y ledger — rutas congeladas

| Ítem | Ruta / llamada |
|---|---|
| Script | `backend/scripts/trial_hibrido_objetivo_x_subjetivo.py` — wrapper `BacktestEngine` con panel COT alineado (`shift(1)+ffill`), aplica filtro `cot_asset_pct>mediana_252` degradando `INVERTIR→VIGILAR`, escribe VPP+PnL comparativo |
| Ejecución | `cd backend && ../fortress_clean_dl_venv/bin/python -m scripts.trial_hibrido_objetivo_x_subjetivo` — **UNA sola vez, post 2026-12-02**, sin re-corridas |
| Artefacto | `backend/data/cache/trial_hibrido_objetivo_x_subjetivo_<YYYYMMDD_HHMMSS>.txt` + `.json` (VPP, PnL, t-NW, `n_operados`, `tasa_abstencion`, `MDE`, `cache_manifest_sha256`) |
| Ledger (llamada real post-gate) | `register_trial_reservation({id:"hibrido_objetivo_x_subjetivo_v1", fecha:"2026-12-02", familia:"hibrido_objetivo_x_subjetivo", hipotesis:"Filtro COT asset_net%OI > mediana_252 mejora VPP y PnL neto del motor a H=20 lag=1 vs baseline siempre-operar", n_trials_consumidos:1, umbral_aplicado:"VPP_filtrado>VPP_baseline Y PnL_filtrado>PnL_baseline p<0.05 (n_family=1, H=20, lag=1)", seccion_doc:"PRE_REGISTRO_HIBRIDO_OBJETIVO_X_SUBJETIVO.md §5", ventana_datos:{"modo":"historico","hasta":"2025-09-01"}, diseno_mde:{...}}, preregistro="<este archivo>")` → luego `complete_trial(id, veredicto, artefacto)` |
| Determinismo | `seed=42` para `circular_block_bootstrap_ci` (`backtest_engine.py:753`); `data/cache` congelado por `cache_manifest_sha256` |

---

## 10. Qué NO hace este trial (deliberadamente)

- No toca `signal_engine.py` / `backtest_engine.py` en producción (inyección por subclase).
- No inyecta COT como factor del score (no `G2/G3`); solo modula la **puerta**.
- No enciende `GOVERNANCE_LLM_ENABLED` (A9 apagó la tríada por falta de justificación medida — `PLAN_MEJORA_MATEMATICA §A9` — se re-enciende solo si un trial la valida).
- No agrega familia al ledger hasta 2026-12-02; no corre backtest hasta entonces.
- No revivirá Finnhub ni pagará feeds.

---

## 11. Riesgos declarados ANTES de correr

1. **COT es semanal, no diario**: `build_sentiment_frame` interpola con `ffill` — el estado persiste 5 días. El filtro cambia poco; ΔPnL puede ser pequeño.
2. **E-MINI no es el universo 50**: COT mide posicionamiento S&P, no single-names. La interacción es a nivel mercado, no stock-picking — efecto esperado modesto.
3. **Regimen 3 bloquea**: `decision.py:61` `DEFLATION` fuerza `NO_INVERTIR` antes del filtro — en esos días el filtro no aporta.
4. **MDE optimista si autocorr subestimada**: con `rho_1=0.4`, MDE sube a ~0.025 — sigue ejecutable pero con margen menor.

---

## 12. Checklist de no-ejecución

- [x] Este archivo se creó **sin correr backtest**, sin `register_trial*`, sin `GOVERNANCE_LLM_ENABLED`.
- [x] Criterio §5, H=20, lag=1, umbral `0.90` via `current_threshold` y MDE `0.017-0.020` congelados — no se cambian al ver el número.
- [x] COT 2010-2025, `shift(1)+ffill` causal, `ventana_datos` ≤ `2025-09-01` (holdout) sellados.
- [x] Familia `hibrido_objetivo_x_subjetivo` declarada post-gate 2026-12-02; no se tocó `trial_registry.json`.
- [ ] **Al ejecutar (SOLO post 2026-12-02 con aprobación de Boris)**: extender COT 2010..2018 → `register_trial_reservation` → correr una vez → artefacto → `complete_trial` → `ROADMAP.md`.

---

*Fin del pre-registro — congelado 2026-09-25, ejecución bloqueada por gate hasta 2026-12-02. Próxima edición solo para apéndice de resultados.*
