# PRE-REGISTRO — PBO/CSCV baseline momentum+RSI con lag-0 (open(m)→close(m))

**Fecha de pre-registro**: 2026-09-03
**Estado**: 🟡 PRE-REGISTRADO — **NO EJECUTADO** (reservado para post-gate)
**Autor**: Cline (ticket A8 del plan `PLAN_REMEDIO_BRECHAS_20260903.md`)
**Categoría**: `bugfix` (per A8 — re-medición de hipótesis existente con metodología corregida, no trial nuevo de señal)
**Familia**: `signal_diagnosis` (misma que §39; consume 1 slot del ledger al ejecutar post-gate)
**Umbral_aplicado** (canónico para el ledger, A7): `PBO <= 0.20 CUMPLE (bucket BAJO), 0.20 < PBO <= 0.50 INTERMEDIO (CUMPLE consistencia), PBO > 0.50 NO_CUMPLE (alerta ROADMAP) — re-medición lag=0 vs §39 lag=1`
**Referencia**: ONBOARDING.md reglas #1–#3 — este documento se escribe ANTES de correr; no se edita después de ver el resultado.
**Ticket**: `PLAN_REMEDIO_BRECHAS_20260903.md` §A8

---

## 0. Por qué este pre-registro existe (contexto A8)

El PBO=0.2358 vigente en `PLAN_MEJORA_MATEMATICA.md §39` se calculó con el
default de ejecución `EXECUTION_LAG_DAYS=1` (`backend/app/core/backtest_engine.py:646`),
que rebalancea en `close[m-1]→close[m]`: la señal del mes m se ejecuta en el
cierre del mes siguiente. Esa convención es conservadora para el edge del
baseline (evita mirar el cierre del propio mes de la señal), pero **no es la
convención estándar de la literatura de PBO** (Bailey, Borwein, López de
Prado & Zhu 2014–2017), que usa `open(m)→close(m)`: rebalanceo intra-mes al
apertura tras la señal.

La diferencia es de grado, no de naturaleza: el PBO vigente mide overfitting
de proceso asumiendo cierre-a-cierre; este pre-registro mide el mismo
overfitting asumiendo apertura-a-cierre intra-mes. Si el ranking IS→OOS es
robusto al cambio de convención, el PBO debería caer en el mismo bucket
(0.20–0.50, INTERMEDIO). Si cambia de bucket, hay un sesgo de metodología
que la convención actual estaba ocultando.

**Limitación declarada en `PLAN_MEJORA_MATEMATICA.md §40.1` (nueva, escrita
en este mismo ticket):** "el PBO=0.2358 vigente fue calculado con
`EXECUTION_LAG_DAYS=1` (close[m-1]→close[m]); la re-corrida con `open(m)→close(m)`
queda pre-registrada como categoría `bugfix` post-gate — la declaración
consta en `PRE_REGISTRO_PBO_BASELINE_LAG0_20260903.md`".

**NO se ejecuta durante el gate** (per A8, `PLAN_REMEDIO_BRECHAS_20260903.md`
§A8): el re-run es una **medición de hipótesis existente**, no un bug de
producción. La cuenta del contador de días limpios (A2/Cline) sigue sin
verificar esta re-corrida.

---

## 1. Hipótesis

**H0 (nula)**: el PBO vigente (0.2358, INTERMEDIO) **es artefacto de la
convención de lag**: con `open(m)→close(m)` (convención estándar PBO),
el PBO cae a bucket **BAJO** (≤0.20) o **ALTO** (>0.50) — i.e. la
re-corrida cambia la lectura del proceso selectivo.

**H1 (alternativa)**: el PBO con `open(m)→close(m)` también cae en
bucket **INTERMEDIO** (0.20–0.50) — el overfitting de proceso es de grado
(constante bajo la convención), no de bucket.

> **Pre-declarado**: el resultado NO se usa para revocar ni promover el
> baseline (mismo principio que §39: PBO mide proceso, no señal). Si el
> PBO cambia de bucket, se documenta y se cita en cualquier evaluación
> futura; si se mantiene en INTERMEDIO, no se hace nada (resultado
> consistente con la lectura vigente).

---

## 2. Método (idéntico a §39, salvo el lag)

Re-corrida del script `backend/scripts/pbo_cscv_baseline.py` con
`EXECUTION_LAG_DAYS=0` forzado en el motor (override del default 1).
Todos los demás parámetros idénticos a §39:

- **Matriz M** (T meses × N configuraciones): retorno mensual neto del
  portafolio equal-weight reconstruido vectorialmente a partir del
  mismo motor de reglas. Universo 50 canónico, snapshot fin de mes,
  elegibilidad = gates EXACTOS del motor (`close>ema50>ema200`,
  `adx14≥20`, `rsi14∈(40,75)`, `volume_ratio≥1.0`), score ≥0.6, costo
  2×(0.001+0.0005) por rebalanceo. Mismo alcance declarado que §39
  (aproximación vectorizada SIN stops/barriers/regime-gating).
- **Familia de configuraciones (N=27)**: misma grilla 3×3×3 del §39
  con ACTUAL=celda central (w=0.664/45-70/100).
- **CSCV**: S=16 bloques contiguos, T truncado al múltiplo de 16
  reteniendo meses recientes, C(16,8)=12.870 splits, Sharpe anualizado
  sobre retornos mensuales, logit λ por combinación.
- **PBO** = fracción de combinaciones con λ≤0.
- **Diferencia ÚNICA vs §39**: `EXECUTION_LAG_DAYS=0` (open-to-close
  intra-mes en vez de close-to-close inter-mes). En el motor real eso
  significa que la señal del mes m se ejecuta en la **apertura** del
  mismo mes m (en la práctica, primera rueda post-señal) en vez de
  la apertura del mes m+1.

**Costos**: mismos `COST_PER_SIDE=0.0005` + slippage `0.0005` (vigentes).
**Determinista**: seed 42, `random_state=42` donde aplique.

---

## 3. Criterio pre-registrado (mismo que §39)

| PBO con `open(m)→close(m)` | Lectura | Acción |
|---|---|---|
| ≤ 0.20 | Riesgo de sobreajuste BAJO | Coincide con H1; el PBO vigente era artefacto de lag, baseline más robusto de lo que se creía |
| 0.20–0.50 | INTERMEDIO | Coincide con H1; resultado consistente con §39, ninguna acción |
| > 0.50 | ALTO | Discrepa con H1; el PBO vigente subestimaba el overfitting por la convención close-to-close, alerta al ROADMAP |

**Veredicto binario para ledger**: CUMPLE si PBO≤0.20 (mejora respecto al
vigente), NO_CUMPLE si PBO>0.20 (no mejora, mantenemos la cautela vigente).
El cambio de bucket se documenta pero no se usa para revocar el baseline
— mismo principio que §39.

---

## 4. Checks de fidelidad (mismos que §39 + 1 nuevo)

1. La config ACTUAL debe estar presente como fila y su Sharpe
   full-período reportado.
2. T final ≥ 96 meses.
3. Cobertura: ≥30% de meses con ≥1 señal en la config actual.
4. Signo del edge: retorno medio mensual de la config ACTUAL positivo
   sin costos.
5. **NUEVO (A8)**: el override `EXECUTION_LAG_DAYS=0` debe estar
   explícitamente declarado en el log del script (`grep "EXECUTION_LAG_DAYS=0"`
   en la corrida). Si el script usó el default 1 por accidente, el
   artefacto es inválido y se descarta.

---

## 5. Artefacto

- Path: `backend/data/cache/pbo_cscv_baseline_lag0_<ts>.txt` (+json).
- Script: `backend/scripts/pbo_cscv_baseline.py` con el override
  `EXECUTION_LAG_DAYS=0` por env var (`LAG_DAYS=0` antes de la corrida)
  o por patch local al script (declarado en el artefacto).
- Comparación: tabla lado-a-lado §39 (lag=1) vs este re-run (lag=0):
  PBO, bucket, λ mediana, ranking config ACTUAL.
- Ledger: cuando se ejecute post-gate, reservar con
  `register_trial_reservation(id="pbo_cscv_baseline_lag0", familia="signal_diagnosis",
  n_trials_consumidos=1, categoria="bugfix", ...)`. El check del
  `trial_registry` (A7) acepta `bugfix` durante el gate solo si
  el escape `FORTRESS_ALLOW_GATE_TRIAL=1` está activo — Boris lo
  activa al cierre del gate si decide ejecutar este re-run.

---

## 6. Idempotencia y prohibición durante el gate

- **NO se ejecuta durante el gate** (per A8, ticket literal). El
  script `pbo_cscv_baseline.py` no debe correr con `LAG_DAYS=0`
  entre 2026-09-02 y `clean_days.json` con racha ≥60 (o
  `GATE_START_DATE + 90 días` como cap, lo que llegue antes).
- Si por error un agente corre el script con `LAG_DAYS=0` durante
  el gate, el artefacto generado se descarta: la racha de días
  limpios no se ve afectada (PBO no es métrica del gate), pero
  el script debe loggear `GATE_VIOLATION` y Boris decide si el
  re-run cuenta para el post-gate o se descarta por
  contaminación temporal.
- **Este pre-registro queda sellado** (no se edita post-resultado,
  ONBOARDING regla #1). Si la ejecución post-gate produce un
  hallazgo que requiere redefinir la familia de configuraciones,
  eso es un **pre-registro NUEVO** con id distinto, no una
  edición retroactiva de este.

---

## 7. Próximo paso (post-gate)

Cuando `clean_days.json` declare racha ≥60 (o `GATE_START_DATE + 90 días`
como cap), Boris evalúa si ejecuta este re-run. La ejecución toma el
mismo día ~30-60 minutos que §39 (vectorización CSCV con S=16). El slot
del ledger está pre-aprobado aquí; el `register_trial_reservation` se
hace en el momento de ejecución, no antes (consistente con Track A:
la reserva ocupa el slot, pero el veredicto se completa después).

---
