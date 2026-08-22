# Resumen — §39: PBO vía CSCV del baseline momentum+RSI

Fecha: 2026-08-22 · Pre-registro en `PLAN_MEJORA_MATEMATICA.md` §39 (escrito ANTES de
correr; corrección de rótulo N=18→N=27 documentada ahí mismo, la grilla enumerada nunca
cambió). Auditoría de proceso al estilo §35 — NO consume slot del ledger.

## Pregunta

¿El score momentum+RSI del motor (el ÚNICO factor que sobrevivió 38 trials) es un
artefacto de selección entre las configuraciones vecinas que se pudieron haber elegido?
El PBO=0.5 de §11 Fase 3 fue sobre la familia ridge y PREVIO al lock del baseline — no
aplicaba al vigente. Esta es la prueba que faltaba para decir "esto no es overfitting de
proceso" con el mismo rigor que se le exige a todo lo demás.

## Método (Bailey/Borwein/López de Prado/Zhu 2017)

- Matriz M: 128 meses (2016-01→2026-08) × 27 configuraciones. Portafolio equal-weight
  mensual reconstruido vectorialmente con los gates EXACTOS del motor (`close>ema50>ema200`,
  `adx≥20`, `rsi∈(40,75)`, `vol_ratio≥1`, `score≥0.6`), costos 2×(0.001+0.0005) por
  rebalance, cash si no hay señales.
- **Aproximación declarada**: sin stops/barriers/regime-gating — mide el EDGE del score,
  no el backtest completo del motor.
- Familia: pesos {0.50, **0.664**, 0.80} × banda RSI {(40,65), **(45,70)**, (50,75)} ×
  techo momentum {75, **100**, 125}. ACTUAL = celda central.
- CSCV: S=16 bloques de 8 meses, C(16,8)=12.870 combinaciones, estadística = Sharpe
  anualizado mensual, PBO = P(rank OOS de la mejor-IS ≤ mediana).

## Resultados

| Métrica | Valor |
|---|---|
| Checks de fidelidad | OK ×4 (T=128≥96; cobertura 83.6% meses con señal ≥30%; edge bruto +1.55%/mes >0) |
| **PBO** | **0.2358** (3035/12.870 combos λ≤0) |
| λ | media +0.182 · mediana +0.310 · p5 −0.154 · p95 +0.310 |
| Sharpe full-período, vecindario | TODAS las 27 configs positivas: +0.55 → +0.90 |
| Config ACTUAL | Sharpe +0.714, **rank 12/27** |

## Veredicto (bucket pre-registrado)

**INTERMEDIO (PBO 0.236, umbral "bajo" ≤0.20 apenas superado). Documentado; Tarea O y P
deben citarlo. Ninguna acción automática.**

Lectura en tres capas, de la más a la menos favorable:

1. **El edge es robusto al vecindario de diseño.** Las 27 perturbaciones plausibles del
   baseline dan Sharpe positivo (+0.55..+0.90). No existe una "configuración mala
   escondida": el riesgo de selección es de GRADO (cuánto alpha queda), no de EXISTENCIA
   (si hay algo). Esto es lo más importante y es una buena noticia.
2. **Contra el cherry-picking explícito**: la config elegida rankea 12/27 — no fue el
   máximo in-sample del vecindario (el máximo habría sido techo 75, +0.901). Quien eligió
   estos parámetros no estaba optimizando contra este dataset.
3. **Pero la estabilidad IS→OOS es moderada**: en ~24% de los splits CSCV, la mejor
   config in-sample cae debajo de la mediana out-of-sample. Con 27 configs correlacionadas,
   elegir la mejor-IS tiene valor predictivo limitado — consistente con la tabla de
   DSR/N_eff de Boris: el efectivo por correlación es mucho menor que el nominal, y el
   umbral real de promoción (DSR≥0.90 walk-forward) ya descuenta esto.

## Implicancias operativas

- El baseline queda **parado con esta evidencia adicional**: no se revoca nada, no se
  cambia ningún parámetro (mover al techo 75 "porque da más Sharpe" sería exactamente el
  cherry-picking post-hoc que esta prueba descalifica — prohibido sin trial propio).
- **Tarea O (Frog-in-the-Pan) y Tarea P (regime gating)**: citar §39 — el proceso
  selectivo tiene riesgo intermedio documentado; cualquier mejora nueva debe demostrarse
  CONTRA este baseline ya auditado, con walk-forward DSR≥0.90 como siempre.
- Limitaciones declaradas: aproximación vectorizada mensual (sin stops ni regime-gating),
  familia acotada a 27 configs del vecindario inmediato (no cubre, ej., lookbacks
  alternativos de momentum), PBO sensible a S y a la definición de la familia. Un PBO
  sobre el motor COMPLETO requeriría ~27 backtests full de 77-120 min cada uno — no justificado hoy.

## Archivos

- `backend/scripts/pbo_cscv_baseline.py` — implementación (ruff limpio)
- `backend/data/cache/pbo_cscv_baseline_20260822_092850.txt` + `.json` — artefacto crudo
- `PLAN_MEJORA_MATEMATICA.md` §39 — pre-registro + resultado

## Cross-check: colisión con la corrida paralela de OpenCode (2026-08-22 ~09:31)

Mientras esta auditoría corría, OpenCode ejecutó SU propio PBO sobre la misma pregunta
(`pbo_cscv_mom_rsi_20260822_093109.txt`, pre-registro propio sellado 09:16). Estado de
las dos mediciones:

| | Cline §39 | OpenCode |
|---|---|---|
| Familia | 27 configs vecinas del baseline | 21 "trials del ledger" **proxyeados** por el mismo tipo de grid |
| Ventana / bloques | 2016-2026, 16 bloques de 8 meses | 2019-2026, 16 bloques de 5 meses |
| Checks de fidelidad | OK ×4 | **FALLIDA por puerta propia** (T_final=80 < 96 → "no interpretable como PBO válido") |
| PBO | 0.236 → INTERMEDIO | 0.469 → "NO_CUMPLE / overfitting" (veredicto emitido pese a la falla) |

Evaluación (Cline, con evidencia):

1. La corrida de OpenCode está **invalidada por su propia regla pre-registrada** (el
   artefacto lo dice textualmente) — su headline NO_CUMPLE no debe aceptarse ni
   registrarse en el ledger mientras la puerta diga FALLIDA.
2. Su diseño además arrastra la limitación §8.1 declarada por OpenCode: los 21 nombres
   del ledger (FinBERT, OFI, CVD, gap-reversion...) son familias DISTINTAS, y fueron
   asignadas a parametrizaciones momentum/RSI del grid — eso no reconstruye el
   performance real de esos trials, mide ruido de ranking entre proxies casi idénticos.
3. La brecha numérica 0.47 vs 0.24 se explica principalmente por tamaño de bloque
   (splits IS/OOS de ~40 vs ~64 meses → Sharpe por split mucho más ruidoso → PBO
   inflado) más la diferencia de ventana. Es la misma dirección que la limitación §2
   que el propio doc de OpenCode declara.
4. Lectura integrada honesta: ambas corridas dicen lo mismo cualitativo — **seleccionar
   la mejor config in-sample dentro de un vecindario correlacionado tiene valor
   predictivo moderado/bajo** — y ninguna revoca la existencia del edge (en mi familia,
   las 27 configs dan Sharpe positivo; en la de OpenCode, las 21 también, +0.63..+1.25).

**Recomendación a Boris**: tomar §39 (esta auditoría, válida según sus checks) como la
medición de proceso vigente — INTERMEDIO, sin acción automática. No consumir el slot de
ledger 21→22 con una corrida auto-invalidada. Si algún día se quiere el PBO "de los 21
trials reales", exige reconstruir cada trial con `backtest_engine.run` (pesado: horas de
CPU por corrida completa) — hoy no está justificado por ninguna decisión pendiente.
