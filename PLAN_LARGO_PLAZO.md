# Plan de largo plazo — para Cline y OpenCode, trabajo autónomo

> Igual que `ORDENES_MODULOS.md`: cada bloque es autocontenido, dice qué leer y qué no.
> Regla de oro sigue vigente: un solo escritor por tarea. Nada de esto toca el motor
> de producción — todo vive en `backend/scripts/` + docs, con revert automático si
> no cumple.

**Actualizado: 2026-08-17.** Estado verificado contra ROADMAP.md, trial_registry.json, y artefactos en data/cache/.

## Estado de partida (verificado hoy, no asumir nada más)

- **Suite actual: 241 tests pasando** (no 216 ni 70/70).
- **Tarea A (Triple Barrier)** y **Tarea C (Lead-lag)**: CERRADAS con artefactos.
- **Tarea B (FinBERT) PASO 1**: HECHO. `earnings_sentiment.py` + CLI + 25 tests. Backfill inicial 24 filings. PASO 2 (trial) bloqueado hasta 8 trimestres × 30 símbolos.
- **Instrumento M1-M8 completo**: todos los módulos implementados, faltan trials que los usen.
- **ADX t=+2.31 nominal**: único factor con señal positiva. §25 (2026-08-17, Cline) lo probó en
  walk-forward OOS por ventana → **NO CUMPLE** (W1 +0.79 / W2 +1.54 / W3 +1.47, 0/3 cruzan
  Bonferroni-9 2.77). Queda **marginal-no-robusto con evidencia OOS, CERRADO como candidato a
  "bueno"**. No retomar sin evidencia nueva.
- **La línea "macro-como-compuerta" queda CERRADA.** Se probó dos veces y no sostiene. No retomar sin evidencia nueva.
- `AGENTS.md` de este repo tiene la doctrina de equipo — leerlo si es sesión nueva.
- **Problema estructural reconocido**: el proyecto tiene criterios claros para refutar, pero no para aceptar "bueno". El trial M2 (abstención calibrada) es el primero que responde "¿debería el motor callarse cuando no hay señal?" con evidencia existente.

## Regla no negociable para las tres tareas de abajo

Cada una termina en un **trial que corre contra datos reales**. Todas deben:
1. Pre-registrarse en `PLAN_MEJORA_MATEMATICA.md` (próxima sección libre — verificar
   el número más alto con `grep -o '§[0-9]*' PLAN_MEJORA_MATEMATICA.md | sort -u | tail -1`)
   **ANTES** de correr el script. Metodología + criterio de éxito/fracaso fijados por
   escrito antes de ver un resultado.
2. Confirmar `n_trials` y familia contra el ledger real:
   `cd backend && .venv/bin/python -c "from app.core.trial_registry import consumed_budget, current_threshold; print(consumed_budget('motor_signal'), current_threshold('motor_signal'))"`
   — no asumir el número, leerlo.
3. Si NO CUMPLE: se documenta con su artefacto (`data/cache/`, timestamp) y se revierte
   (el script se puede dejar, pero no se integra nada al motor).
4. Registrar el trial en el ledger (`app/core/trial_registry.py: register_trial(...)`)
   al cerrar, con su veredicto.

---

## Tarea A — Trial de abstención calibrada M2 (OpenCode)

**ESTADO**: 🟡 EN CURSO — pre-registro listo, esperando corrida

```
PROBLEMA ESTRUCTURAL: El proyecto tiene criterios claros para refutar (DSR, Bonferroni,
pre-registro), pero no definió qué cuenta como "bueno" para decidir operar. Cada trial
termina en NO CUMPLE, y eso está bien — pero ADX quedó en tierra de nadie (t=+2.31
nominal, único factor positivo).

M2 (conformal.py) YA ESTÁ CONSTRUIDO: 16 tests, métrica vpp_bajo_abstencion, Split
Conformal Prediction con garantía de cobertura. Lo que falta es el TRIAL que lo
pruebe contra el baseline real.

HIPÓTESIS: El motor debería abstenerse (no operar) cuando la señal es débil. Un
instrumento que se abstiene el 80% del tiempo y acierta el 20% restante es un ÉXITO,
no un fracaso — mejora el VPP de lo que sí opera.

TAREA:
1. Pre-registro YA HECHO en PLAN_MEJORA_MATEMATICA.md §24 (nueva sección).
2. Construir backend/scripts/trial_m2_abstention.py:
   - Cargar baseline_clean_20260811_150643_trades.parquet (los 286 trades del baseline).
   - Para cada trade, obtener el score que tenía en el momento de entrada (usar
     la lógica existente de signal_engine o predictive_engine — NO reinventar).
   - Calibrar ConformalAbstentionEngine sobre W1 (2020-2021), predecir W2/W3.
   - Métrica primaria: vpp_bajo_abstencion (predicciones que NO se abstuvieron vs
     outcomes reales). Secundaria: cobertura empírica del intervalo 90%.
3. CRITERIO DE ÉXITO (pre-registrado):
   - vpp_bajo_abstencion > baseline_vpp (el VPP de operar todo sin filtro).
   - Cobertura empírica dentro de ±5pp del nominal 90%.
   - Familia "motor_signal", n_trials=9 (el siguiente en el ledger).
4. Correr, documentar veredicto con artefacto, registrar en ledger.

REGLAS: Python 3.9, NO tocar conformal.py ni el motor, solo scripts/ nuevo.
Artefacto en data/cache/trial_m2_abstention_YYYYMMDD_HHMMSS.txt.
```

---

## Tarea B — ADX walk-forward como candidato a "bueno" (Cline)

**ESTADO**: 🟢 CERRADO (2026-08-17) — NO CUMPLE, trial §25 corrido por Cline

```
PROBLEMA: ADX tiene t=+2.31 nominal, el único factor con señal positiva. No alcanza
para señar robusta bajo Bonferroni-4 (≈2.5), pero tampoco se probó en walk-forward.
Si se robustece en OOS, deja de ser marginal.

HIPÓTESIS: ADX como filtro único (no como parte del gate compuesto actual) podría
tener poder predictivo suficiente para justificar operar cuando adx≥20, abstenerse
cuando no.

TAREA:
1. Leer: backend/scripts/diagnose_rr2_intraday.py (patrón de rank IC intra-día),
   backend/app/core/signal_engine.py (cómo se calcula ADX hoy).
2. Pre-registrar en PLAN_MEJORA_MATEMATICA.md §25:
   - Hipótesis: adx_score (o ADX crudo) como factor único.
   - Ventanas W1/W2/W3, rank IC intra-día, Newey-West.
   - Criterio: |t|>2.77 en ≥2/3 ventanas (Bonferroni-9 por los 3 horizontes).
   - Familia "motor_signal", n_trials=10.
3. Construir backend/scripts/trial_adx_walkforward.py:
   - Para cada símbolo del universo 50, calcular ADX (usar signal_engine o
     implementación directa con el mismo lookback que el existente).
   - Rank IC intra-día entre ADX y fwd_return_20d (y/o Triple Barrier label de M1).
   - Walk-forward: calibrar en W1, testear en W2/W3.
4. Documentar veredicto con artefacto, registrar en ledger.

REGLAS: Python 3.9, NO tocar signal_engine.py sin autorización. Si CUMPLE,
discutir integración con el gate — no hacer solo.
```

---

## Tarea C — Indicadores sobre velas semanales (Command Code)

**ESTADO**: ⚪ NO EMPEZADO — pre-registro pendiente

```
PROBLEMA: Todos los indicadores se calculan sobre barras DIARIAS. Nunca se probó
si una granularidad distinta (semanal) cambia el poder predictivo. Esto NO es cambiar
el horizonte del retorno futuro (eso ya se probó en M1/M1b) — es cambiar el RUIDO
del indicador mismo.

HIPÓTESIS: Indicadores calculados sobre velas semanales tienen menos ruido de
microestructura y podrían revelar señal que el ruido diario oculta.

TAREA:
1. Leer: backend/scripts/diagnose_rr2_intraday.py (patrón de rank IC),
   backend/app/core/signal_engine.py (cómo se calculan momentum/RSI/ADX hoy).
2. Pre-registrar en PLAN_MEJORA_MATEMATICA.md §26:
   - Universo: mismos 50 símbolos.
   - Indicadores: momentum (20 semanas), RSI (14 semanas), ADX (14 semanas).
   - Target: fwd_return_5d (1 semana hacia adelante) y/o Triple Barrier label.
   - Ventanas: re-muestrear W1/W2/W3 a semanas (mismo período, diferente granularidad).
   - Criterio: |t|>2.73 en ≥2/3 ventanas (Bonferroni-8: 3 indicadores × 3 ventanas
     — aunque solo se probando 3, el patrón del proyecto usa Bonferroni conservador).
   - Familia "signal_diagnosis", n_trials apropiado.
3. Construir backend/scripts/diagnose_weekly_indicators.py:
   - Cargar datos OHLCV del universo 50.
   - Resample('W-FRI') para convertir a velas semanales.
   - Calcular momentum/RSI/ADX sobre ESA serie semanal.
   - Rank IC intra-semana (no intra-día) contra retorno de la próxima semana.
4. Documentar veredicto con artefacto, registrar en ledger.

REGLAS: Python 3.9, NO tocar el motor existente. Script diagnóstico nuevo.
Si CUMPLE, discutir integración — no hacer solo.
```

---

## Verificación al cerrar cualquier tarea

`cd backend && .venv/bin/python -m pytest -q` debe seguir en verde (216+ passed)
antes de dar cualquier cosa por cerrada. Actualizar `ROADMAP.md` y `SESSION_LOG.md`.
Ninguna requiere que Claude Code esté presente — son autocontenidas.
