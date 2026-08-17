# Resumen de trabajos completados — 2026-08-17

## Estado de las tres tareas asignadas

| Tarea | Agente | Veredicto | Artefacto |
|-------|--------|-----------|-----------|
| **A — M2 abstención calibrada** | OpenCode | **NO CUMPLE** | `trial17_m2_abstencion_20260817_104452.txt` |
| **B — ADX walk-forward** | Cline | **NO CUMPLE** | `trial_adx_walkforward_20260817_103916.txt` |
| **C — Indicadores semanales** | Command Code | **NO CUMPLE** | `weekly_indicators_20260817_105918.txt` |

---

## Tarea A — Trial M2 abstención calibrada

**Hipótesis**: El motor debería abstenerse (no operar) cuando la señal es débil. Un instrumento que se abstiene el 80% del tiempo y acierta el 20% restante mejora el VPP de lo que sí opera.

**Metodología**: Split Conformal Prediction sobre los 286 trades del baseline, walk-forward W2/W3, métrica primaria `vpp_bajo_abstencion`.

**Resultado**:

| Ventana | VPP_baseline | VPP_M2 | n_operados | tasa_abstención | cobertura | Veredicto |
|---------|--------------|--------|------------|-----------------|-----------|-----------|
| W2 2022-2023 | 0.4694 | 0.4043 | 47 | 4.08% | 0.7755 | **NO INTERPRETABLE** (cobertura fuera de rango) |
| W3 2024-2026 | 0.5798 | 0.6000 | 100 | 15.97% | 0.8908 | **NO CUMPLE** (p=0.4347 > 0.025) |

**Conclusión**: La abstención calibrada NO mejora el VPP del motor. La cobertura empírica de W2 falló (0.78 vs 0.90 nominal), lo que indica que la calibración de conformal prediction no es estable con los datos disponibles. W3 tuvo cobertura correcta pero el VPP_M2 no superó significativamente al baseline.

**Implicación**: El motor no debe callarse basado en este instrumento. La hipótesis de "abstenerse cuando no hay señal" queda descartada con evidencia.

---

## Tarea B — ADX walk-forward como candidato a "bueno"

**Hipótesis**: ADX tiene t=+2.31 nominal (único factor con señal positiva). Si se robustece en walk-forward OOS, deja de ser marginal.

**Metodología**: Rank IC intra-día por ventana (W1/W2/W3), Bonferroni-9, umbral |t|>2.77 en ≥2/3 ventanas con signo +1.

**Resultado**:

| Ventana | n_días | mean_IC | t | Signo | ¿Cruza 2.77? |
|---------|--------|---------|---|-------|--------------|
| W1 2020-2021 | 53 | +0.0395 | +0.79 | + | No |
| W2 2022-2023 | 20 | +0.1026 | +1.54 | + | No |
| W3 2024-2026 | 53 | +0.0792 | +1.47 | + | No |
| TOTAL (ref) | 151 | +0.0679 | +2.31 | + | — |

**Conclusión**: ADX es **positivo en las 3 ventanas** (signo + consistente), pero **ninguna es significativa en aislamiento**. El t TOTAL +2.31 era el pooling de señal débil repartida, no una señal concentrada. El criterio (señal que se sostenga sola en ≥2/3 ventanas) no se cumple.

**Implicación**: ADX queda como **marginal-no-robusto con evidencia OOS, CERRADO como candidato a "bueno"**. No se integra al motor. No retomar sin evidencia nueva.

---

## Tarea C — Indicadores sobre velas semanales

**Hipótesis**: Indicadores calculados sobre velas semanales tienen menos ruido de microestructura y podrían revelar señal que el ruido diario oculta.

**Metodología**: Resample('W-FRI'), indicadores momentum_20w/rsi_14w/adx_14w, rank IC intra-semana, Bonferroni-8, umbral |t|>2.73 en ≥2/3 ventanas.

**Resultado**:

| Indicador | W1 t | W2 t | W3 t | ¿Cumple? |
|-----------|------|------|------|----------|
| momentum_20w | -0.17 | -0.01 | +0.19 | 0/3 ventanas |
| rsi_14w | -0.08 | -0.44 | +0.14 | 0/3 ventanas |
| adx_14w | +0.31 | +0.16 | +0.33 | 0/3 ventanas |

**Conclusión**: El ruido semanal NO oculta señal. Los indicadores sobre velas semanales tienen el mismo poder predictivo nulo que los diarios. Máximo |t|=0.44, muy por debajo del umbral 2.73.

**Implicación**: Línea cerrada. El baseline diario sigue siendo el único modo de operación documentado.

---

## Estado global del proyecto

- **Suite**: 242 tests pasando
- **Trials motor_signal**: 9 consumidos (umbral Bonferroni 0.99)
- **Trials signal_diagnosis**: 16 consumidos
- **FinBERT**: PASO 1 completo, acumulando earnings (24 filings backfill). PASO 2 (trial) bloqueado hasta 8 trimestres × 30 símbolos.
- **Línea de señal**: CERRADA. Todos los candidatos probados con rigor han sido refutados.
- **Línea de mecánica**: M2 abstención refutada. EVT (#15) fue placebo estructural. El stop de régimen es el mayor destructor de valor pero el contrafáctico (M2 diagnóstico) mostró que está haciendo su trabajo.

---

## Qué sigue

El proyecto ha agotado las hipótesis de señal inmediatas con la infraestructura actual:

1. **FinBERT acumula solo** — cuando tenga 8 trimestres × 30 símbolos, se corre el trial
2. **Nueva hipótesis de señal** requiere o datos nuevos (alt-data, intradía) o ML no lineal (kernel/SVM, alto riesgo de sobreajuste con n=50)
3. **Gestión de riesgo** — TARGET_VOLATILITY existe en config.py sin conectar. La evidencia de §12 (régimen-vs-volatilidad) no cerró.
4. **M4 — Medición viva Alpaca paper** — infraestructura lista, falta cuenta real

**Decisión pendiente del usuario**: ¿seguimos investigando señal con hipótesis más costosas/arriesgadas, o pivotamos a gestión de riesgo/otro universo?
