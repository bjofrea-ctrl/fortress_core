# Órdenes de trabajo por módulo — para agentes en paralelo

> Cada bloque es **autocontenido**: pegalo en una sesión nueva de OpenCode / Cline /
> Command Code y el agente puede trabajar sin leer el proyecto entero. Esa es la razón
> de ser del diseño modular (ver `DISENO_INSTRUMENTO.md` §6): el costo de tokens no
> viene del paralelismo, viene de re-derivar contexto.
>
> **Regla de oro: un solo escritor por módulo.** Nunca dos agentes en el mismo módulo.
> Claude Code consolida e integra al final.

Estado al 2026-08-14:

| Módulo | Dueño | Estado |
|---|---|---|
| M1 Etiquetado por barreras | Claude Code | ✅ hecho (`app/core/barrier_labeling.py`, 17 tests) |
| M2 Instrumento conforme | Claude Code | ✅ **HECHO (2026-08-15)** — `app/core/conformal.py`, 16 tests, cobertura empírica verificada ≈nominal. **NO retomar, ya está.** |
| M3 Compuerta de régimen | Claude Code | ✅ **HECHO (2026-08-15)** — `app/core/regime_gate.py`, walk-forward anti-lookahead, 8 tests. Infraestructura lista; el TRIAL que la use para afirmar algo necesita pre-registro nuevo (no incluido acá). **NO retomar, ya está.** |
| M4 Costos medidos | **Cline** | ✅ **HECHO (2026-08-15)** — `app/core/execution_costs.py`, `scripts/measure_execution_costs.py`, 13 tests, verificado por Claude Code (no solo el reporte): base_url a paper confirmado por test, cero credenciales reales, ruff limpio. **NO retomar, ya está.** Falta la medición viva (necesita cuenta Alpaca paper real). |
| M5 Detector de deriva | **OpenCode** | ✅ **HECHO (2026-08-15)** — `app/core/drift_detector.py`, KS + Bonferroni + concepto (accuracy/correlación) + `recommend_action`, 18 tests, suite completa 193 passed, ruff limpio. **NO retomar, ya está.** |
| M6 Ledger de trials | **Command Code** | ✅ hecho (`app/core/trial_registry.py`, `data/trial_registry.json`, backfill 29 entradas, 15 tests) — hallazgo: backfill 27 consumidos vs 17 citados |
| M7 Pipeline integrado M1+M2+M3 | Claude Code | ✅ **HECHO (2026-08-15)** — `app/core/diagnostic_pipeline.py`, `run_diagnostic_pipeline()`. 10 tests, dos verifican los invariantes reales (separación temporal calibración/predicción; compuerta AND no OR, chequeado sobre la ecuación booleana exacta). **NO retomar, ya está.** |
| M8 Re-verificar código muerto | **Command Code** | 🟡 libre para arrancar (2026-08-15) |

---

## M4 — Costos medidos (Cline)

```
Trabajás en /Users/boris/Desktop/fortress_core. Leé backend/app/core/barrier_labeling.py
(solo el bloque de constantes) y nada más del proyecto: no hace falta.

PROBLEMA: cada veredicto de "no sobrevive los costos" de este proyecto depende de una
constante ASUMIDA (0.10% comisión + 0.05% slippage por lado), hardcodeada dentro de cada
script de backtest y sin centralizar. Nunca se midió. El caso §18.2 encontró señal real
(bruto +0.000149/día, t-NW +1.01) que murió contra un costo hedged asumido de 0.63%/trade.
Ese "no tradeable" es una división entre un número medido y uno inventado.

TAREA:
1. Centralizar la constante de costos en backend/app/config.py como COST_PER_SIDE
   (default 0.0015), con docstring que diga que es un valor ASUMIDO pendiente de medición.
2. Construir backend/app/core/execution_costs.py con un cliente de Alpaca PAPER TRADING
   (API gratis, sin capital real) cuyo ÚNICO propósito es MEDIR, no operar:
   - registrar precio de decisión (el close que gatilló) vs precio de fill real
   - calcular slippage por orden = (fill - decision) / decision
   - persistir en SQLite: fecha, símbolo, lado, precio_decision, precio_fill, slippage,
     comisión, tamaño
3. Un script backend/scripts/measure_execution_costs.py que mande N órdenes paper sobre
   el universo (SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA + NEW_UNIVERSE de
   scripts/fetch_universe_data.py) y deje un artefacto con timestamp en backend/data/cache/.
4. Tests en backend/tests/test_execution_costs.py — mockeá la API, no pegues a la red
   en los tests.

CONTRATO DE SALIDA (esto es lo que consume el resto del proyecto):
   {"cost_per_side_medido": float, "n_ordenes": int, "slippage_p50": float,
    "slippage_p95": float, "comision_media": float, "ventana": "YYYY-MM-DD a YYYY-MM-DD"}

REGLAS NO NEGOCIABLES:
- PAPER TRADING únicamente. Jamás capital real. Jamás una orden en cuenta live.
- Las credenciales van en variables de entorno, NUNCA en código ni en el chat.
  Si aparece un secreto en la conversación, asumilo comprometido y pedí rotación.
- No commitear ni pushear sin autorización explícita de Boris en la conversación.
- Correr tests: cd backend && .venv/bin/python -m pytest tests/test_execution_costs.py
  (desde la raíz del repo pytest se cuelga: la config vive en backend/pytest.ini)
- Python 3.9 real. No uses sintaxis 3.10+ (nada de `X | Y` en type hints).

NO HAGAS: no toques el motor, ni los agentes, ni la investigación. Solo estos archivos.
```

---

## M5 — Detector de deriva (OpenCode)

```
Trabajás en /Users/boris/Desktop/fortress_core. No necesitás leer el proyecto entero:
solo backend/app/core/barrier_labeling.py para entender el formato de etiquetas.

PROBLEMA: el motor y sus modelos se entrenaron/midieron sobre historia. Si el mercado
cambia de comportamiento, siguen operando con un mapa viejo y nadie se entera. Hoy no
existe ninguna detección de deriva en el repo (verificado: 0 apariciones).

TAREA: construir backend/app/core/drift_detector.py con dos detecciones independientes:

1. DERIVA DE FEATURES (cambió la distribución de las entradas):
   - test de Kolmogorov-Smirnov de dos muestras por cada feature, ventana histórica vs
     ventana reciente (scipy.stats.ks_2samp)
   - devolver por feature: estadístico KS, p-valor, si hay deriva, severidad
   - CRÍTICO: si testeás K features, corregí por comparaciones múltiples (Bonferroni
     sobre K). Este proyecto es estricto con eso — un p<0.05 sin corregir sobre 20
     features no es un hallazgo, es ruido.

2. DERIVA DE CONCEPTO (se rompió la relación entrada→resultado):
   - comparar accuracy y correlación predicción-vs-resultado entre ventana histórica y
     reciente
   - marcar deriva si la accuracy cae más de 10 puntos, o la correlación más de 0.15

3. Una función recommend_action(feature_drift, concept_drift) -> str que devuelva la
   acción sugerida, sin ejecutarla nunca.

CONTRATO DE SALIDA:
   {"feature_drift": {nombre: {"ks": float, "p_value": float, "drift": bool,
                               "severidad": "LOW|MEDIUM|HIGH"}},
    "concept_drift": {"accuracy_hist": float, "accuracy_reciente": float,
                      "caida": float, "drift": bool, "severidad": str},
    "accion_recomendada": str}

TESTS OBLIGATORIOS en backend/tests/test_drift_detector.py:
- con dos muestras de la MISMA distribución -> NO debe detectar deriva (falso positivo)
- con dos distribuciones claramente distintas -> SÍ debe detectarla
- con muestras chicas (n<30) -> debe abstenerse, no afirmar
- la corrección de Bonferroni debe estar testeada explícitamente

REGLAS:
- Python 3.9 real. Nada de sintaxis 3.10+.
- Solo numpy/pandas/scipy (ya están en requirements).
- El detector REPORTA, nunca actúa: no re-entrena, no apaga nada, no toca el motor.
- Correr: cd backend && .venv/bin/python -m pytest tests/test_drift_detector.py
- No commitear ni pushear sin autorización explícita de Boris.

NO HAGAS: no toques el motor, la investigación, ni los agentes.
```

---

## M6 — Ledger de trials (Command Code)

```
Trabajás en /Users/boris/Desktop/fortress_core. Leé SOLO estos dos archivos:
PLAN_MEJORA_MATEMATICA.md y RESUMEN_VALIDACION_VARIABLES.md. No hace falta nada más.

PROBLEMA: este proyecto corrige por comparaciones múltiples (Bonferroni) y lleva la
cuenta de trials A MANO. El propio ROADMAP.md admite la ambigüedad: "Confirmar el
n_trials exacto contra el historial de artefactos antes de fijarlo — no asumir el
número". Con más hipótesis por probar, el conteo a mano se rompe y se empieza a
encontrar señal por pura suerte estadística.

TAREA: construir el registro máquina-legible de trials.

1. backend/app/core/trial_registry.py — lectura/escritura de data/trial_registry.json
   Una entrada por trial pre-registrado:
   {"id": str, "fecha": "YYYY-MM-DD", "familia": str, "hipotesis": str,
    "n_trials_consumidos": int, "umbral_aplicado": str, "veredicto": "CUMPLE|NO_CUMPLE",
    "artefacto": "ruta/al/archivo.txt", "seccion_doc": "§21.1"}

2. Funciones: register_trial(), trials_by_family(), consumed_budget(familia) -> int,
   current_threshold(familia) -> float (el umbral Bonferroni vigente dado lo consumido).

3. BACKFILL: extraé del historial de PLAN_MEJORA_MATEMATICA.md y
   RESUMEN_VALIDACION_VARIABLES.md todos los trials ya corridos (#8 sentimiento,
   #9 fundamentales, #10 partial_tp fix, #11 universo 50, #12 efficiency ratio,
   #13 ridge_3f, §13 gap-reversion, §18.1/§18.2 C6, §19 EVT, §21/§21.1 horizontes,
   Fase 0.6...). Cargalos al registro con su veredicto y su artefacto.

4. backend/scripts/audit_trial_budget.py: imprime el estado del presupuesto por familia
   y AVISA si un trial nuevo excedería el umbral declarado.

ENTREGABLE CLAVE — el hallazgo puede ser el desacuerdo:
   Si tu conteo del backfill NO coincide con los números citados en los documentos
   (por ejemplo n_trials=17), NO lo ajustes para que cuadre. Reportá la diferencia con
   la evidencia de dónde sale cada número. Ese desacuerdo es en sí mismo el resultado
   más valioso de este módulo.

TESTS en backend/tests/test_trial_registry.py:
- registrar y releer conserva los datos
- consumed_budget cuenta correctamente por familia
- current_threshold se endurece a medida que sube el consumo
- un registro corrupto o incompleto falla ruidosamente, no en silencio

REGLAS:
- Python 3.9 real. Nada de sintaxis 3.10+.
- Correr: cd backend && .venv/bin/python -m pytest tests/test_trial_registry.py
- No commitear ni pushear sin autorización explícita de Boris.

NO HAGAS: no corras ningún trial nuevo, no toques el motor, no modifiques los .md de
investigación — solo LEELOS para el backfill.
```

---

## M7 — Pipeline integrado M1+M2+M3 (Command Code)

```
Trabajás en /Users/boris/Desktop/fortress_core. Leé SOLO las firmas públicas de estos
tres archivos (ya construidos y con tests propios — no los toques, no los reescribas):
- backend/app/core/barrier_labeling.py: label_symbol(df, regimes=None, max_horizon=60,
  cost_per_side=0.0015) -> DataFrame con columnas date/exit_reason/ret_net/label/...
- backend/app/core/conformal.py: ConformalAbstentionEngine(alpha=0.10).calibrate(scores,
  outcomes) -> ConformalCalibration; .predict(score) -> ConformalPrediction(point_estimate,
  lower, upper, interval_width, abstenerse, razon)
- backend/app/core/regime_gate.py: WalkForwardRegimeGate(favorable_states, recalib_every=63,
  min_history=756).label_series(price_data) -> (Series bool indexada por fecha, diagnóstico)

PROBLEMA: los tres módulos existen y cada uno tiene sus propios tests, pero hoy quien
quiera usarlos tiene que cablearlos a mano — llamar M1, después separar calibración de
predicción para M2, después cruzar con M3. Eso es exactamente lo que
DISENO_INSTRUMENTO.md prometió evitar: "Fortress como instrumento diagnóstico
calibrado", UN instrumento, no tres piezas sueltas.

TAREA: construir backend/app/core/diagnostic_pipeline.py con una función/clase que
componga los tres, en este orden:

1. Recibe: price_data (dict símbolo->DataFrame con close/atr14), un score por
   (símbolo, fecha) ya calculado por quien llama (este pipeline NO genera scores,
   los consume — mismo principio que M2), y opcionalmente regimes/favorable_states
   para activar la compuerta M3.
2. Corre M1 (label_symbol) por símbolo para obtener las etiquetas reales (ret_net,
   barrera, label).
3. Split calibración/predicción ESTRICTO por fecha (nunca por símbolo mezclado, nunca
   con fuga temporal — la calibración de M2 debe usar SOLO fechas anteriores a las
   que predice). Calibra el ConformalAbstentionEngine con scores+outcomes de
   calibración, predice sobre el resto.
4. Si se pasó favorable_states: corre M3 y cruza — una fecha solo "opera" si el
   instrumento conforme NO se abstiene Y la compuerta de régimen dice operar=True.
   Sin favorable_states: el gate no aplica (todo pasa el filtro de M3 = operar=True).
5. Devuelve un resultado único: por cada (símbolo, fecha) evaluada, si se operó o no
   y por qué (razón de M2 y/o de M3), más el resumen agregado usando
   `vpp_bajo_abstencion` de conformal.py como métrica primaria (no Sharpe — ver
   DISENO_INSTRUMENTO.md §8).

ESTO NO ES UN TRIAL: no corras esto contra el universo real de 50 símbolos ni saques
conclusiones sobre si el motor mejora — eso necesita pre-registro nuevo (regla #1/#2
de ONBOARDING.md) y es decisión de Boris, no de este módulo. Este pipeline es
infraestructura de conexión, se construye libre y sin ceremonia; probalo con datos
sintéticos (como hacen los tests de M1/M2/M3), no con el panel real.

TESTS en backend/tests/test_diagnostic_pipeline.py:
- el pipeline sin favorable_states da el mismo resultado que M1+M2 solos (M3 no filtra
  nada si no se activa)
- con favorable_states, una fecha con régimen desfavorable NUNCA opera aunque M2 no
  se abstenga (la compuerta gana, es un AND, no un OR)
- calibración y predicción nunca comparten fechas (test explícito de la separación
  temporal — es la propiedad más fácil de romper por accidente)
- el resumen agregado (vpp_bajo_abstencion) coincide con recalcularlo a mano sobre
  el mismo resultado

REGLAS:
- Python 3.9 real. Nada de sintaxis 3.10+.
- NO modifiques barrier_labeling.py, conformal.py, ni regime_gate.py — son de Claude
  Code, tienen sus propios tests, se consumen tal cual están.
- Correr: cd backend && .venv/bin/python -m pytest tests/test_diagnostic_pipeline.py
- No commitear ni pushear sin autorización explícita de Boris.

NO HAGAS: no toques M4 (Cline) ni M5 (OpenCode) — ni sus archivos ni su alcance. No
corras nada contra datos reales del universo de 50 símbolos.
```

---

## Integración (Claude Code)

Cuando los tres entreguen, Claude Code consolida:

1. **Verificar contra el artefacto real**, no contra el autoreporte del agente: correr
   sus tests, leer el diff completo, abrir los artefactos generados.
2. **Chequear los contratos**: que la salida de cada módulo sea exactamente la declarada
   acá. Si un módulo necesitó contexto que no estaba en su orden, el contrato estaba mal
   definido — se corrige el contrato, no se parcha el código.
3. **Cablear**: M4 reemplaza `DEFAULT_COST_PER_SIDE` en `barrier_labeling.py` por el
   costo medido. M5 consume las etiquetas de M1. M6 gobierna el umbral de todo trial
   nuevo, incluido el primer veredicto de M2.
4. **Suite completa** (`cd backend && .venv/bin/python -m pytest`) + actualizar
   `ROADMAP.md` y `SESSION_LOG.md`.
