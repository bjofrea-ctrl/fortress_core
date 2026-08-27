# Plan de auditoría independiente — para GLM (fx)

Pegar esto completo en la sesión de `fx` que corre fuera de Orca (la gratuita).
Objetivo: encontrar brechas o ángulos que el equipo interno (Claude Code +
OpenCode + Kilo + Cline) no vio — no repetir lo ya hecho.

## Regla de entrada (obligatoria, sin excepción)

Antes de proponer CUALQUIER hallazgo o brecha, leé completos:
1. `ONBOARDING.md` — reglas no negociables del proyecto.
2. `ROADMAP.md` — tabla maestra de todo lo cerrado y abierto.
3. `backend/data/trial_registry.json` — el ledger real de los 26+ trials
   corridos, con veredicto de cada uno.

Cualquier brecha que propongas, ANTES de presentarla, cruzala contra estos
tres archivos. Si algo similar ya se probó y cerró (aunque sea con otro
nombre o método), decilo explícitamente — no lo escondas ni lo repitas como
si fuera nuevo. Esta regla existe porque dos auditorías externas anteriores
en este proyecto propusieron líneas ya cerradas y refutadas, y tuvieron que
corregirse cuando se les mostró la evidencia. No repitas ese error.

## Lo que YA se auditó bien (no repetir)

Una auditoría externa previa (vos mismo, sesión anterior) ya cubrió a fondo,
con cita de línea de código real:
- `backtest_engine.py` (DSR, PBO, walk-forward, execution lag, bootstrap CI)
- `signal_engine.py` (factores, pesos, gates)
- `adaptive_risk.py` (sizing, stops, thresholds)
- `regime_gate.py` (M3, walk-forward regime)
- `conformal.py` (M2, abstención calibrada)
- `DISENO_INSTRUMENTO.md`

Esa auditoría dijo explícitamente qué NO cubrió — arrancá por ahí.

## Frentes a auditar (los que faltan)

### 1. Los 30 archivos restantes de `backend/app/core/` no leídos antes

Cuál es el inventario real: `ls backend/app/core/*.py` y comparalo contra
lo ya auditado arriba. De lo que falta, priorizá lo que mueve dinero o
decisiones reales del motor (no utilidades triviales).

### 2. Los routers de la API (`backend/app/api/routes/`)

Nunca se auditaron con el mismo rigor que el motor. Buscá: validación de
inputs, manejo de errores, endpoints que podrían devolver datos sin
validar/calibrar como si fueran señales reales (viola la regla no
negociable #4 de ONBOARDING.md).

### 3. Riesgo metodológico de segmentación de familias del ledger

`trial_registry.py` divide los trials en familias (`signal_diagnosis`,
`motor_signal`, etc.), cada una con su propio umbral Bonferroni. Pregunta
que nadie hizo todavía: ¿esa segmentación es metodológicamente correcta, o
es una forma (aunque no intencional) de resetear la vara de significancia
al mover un trial a una familia "nueva"? Si dos familias miden
esencialmente el mismo tipo de hipótesis, deberían compartir presupuesto de
error. Auditar la lógica de asignación de familia en cada trial del
ledger — ¿hay algún caso donde el mismo tipo de pregunta se hizo dos veces
bajo familias distintas, evitando así la corrección acumulada?

### 4. Sesgo de supervivencia y calidad de datos del universo de 50 símbolos

`fetch_universe_data.py` / `NEW_UNIVERSE`: ¿el universo de 50 símbolos es
el universo VIGENTE hoy, o es el universo que existía y sobrevivió hasta
hoy? Si es lo segundo, hay sesgo de supervivencia (las empresas que
quebraron o se deslistaron en el período no están, inflando el retorno
promedio observado). Verificar cómo se construyó la lista y si contempla
esto.

### 5. Corporate actions (splits, dividendos, spin-offs)

¿Los datos de `yfinance` que usa el proyecto están ajustados correctamente
por splits y dividendos en TODO el histórico 2015-2026? Un split no
ajustado correctamente contamina retornos y stops (ATR, position_stop) con
saltos artificiales de precio.

### 6. Elección de las ventanas W1/W2/W3

Las tres ventanas walk-forward (2020-2021, 2022-2023, 2024-2026) son fijas
en casi todos los trials del proyecto. Pregunta: ¿esas fronteras exactas se
eligieron por alguna razón de mercado (ej. cambios de régimen documentados)
o son arbitrarias? Si son arbitrarias, ¿el resultado de algún trial cambia
si se corren las mismas pruebas con fronteras desplazadas ±1 mes (sensibi-
lidad a la elección de ventana)? No hace falta correr nada — es una
pregunta de diseño para señalar, no una auditoría de código.

### 7. Modelo de costos más allá de qty=1/10/50

La curva de costos medida (Tarea D) cubre tamaños 1/10/50 acciones. El
motor real opera con capital de $25,000 — ¿los tamaños de posición típicos
del motor caen dentro de ese rango medido, o algunos trades son más
grandes y quedan fuera de la curva medida (impacto de mercado no
capturado)?

### 8. Frontend y despliegue — superficie no auditada por el equipo interno

El dashboard corre permanente en producción (`:3000`) con datos que
alimentan decisiones. Auditar: ¿hay algún camino donde el frontend muestre
un número sin el caveat/badge de honestidad correspondiente? ¿El manejo de
errores de red deja alguna vista en un estado engañoso (ej. mostrando el
último dato cacheado sin indicar que está stale)?

## Formato de salida (mismo que la auditoría anterior, que funcionó bien)

- FODA o lista de hallazgos, cada uno con archivo:línea citado.
- Sección explícita "lo que no pude verificar" — sin inventar certeza donde
  no la hay.
- Para cada hallazgo, indicar si es (a) bug de código, (b) brecha de
  investigación que necesitaría pre-registro nuevo, o (c) decisión de
  producto — no mezclarlos.
- NO proponer que se ejecute nada — solo reportar. Cualquier trial nuevo
  necesita pre-registro y decisión explícita de Boris, sin excepción.
