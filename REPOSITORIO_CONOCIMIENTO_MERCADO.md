# Repositorio de conocimiento — análisis de mercado (fortress_core)

Este documento es la base de CONOCIMIENTO (cómo pensar el mercado), distinta de los
documentos de EJECUCIÓN (`ROADMAP.md`, `PLAN_LARGO_PLAZO.md`,
`PLAN_MEJORA_MATEMATICA.md`, que son tareas y trials). Se actualiza cuando aparece un
precepto o definición nuevo, no cuando cierra una tarea.

---

## Parte 0 — Principios fundamentales (leer antes que cualquier indicador)

### Precepto 1 — Un indicador es una herramienta derivada del precio, no una fuente independiente

Un indicador es una fórmula matemática que se aplica al precio (u otros datos de
mercado: volumen, high/low). Su comportamiento **depende** del precio del activo —
no es información nueva ni independiente, es una transformación del mismo dato. Por
construcción, el indicador siempre **reacciona** al precio, nunca lo antecede de
forma causal (aunque distintos indicadores reaccionan con distinto lag).

### Precepto 2 — Se lee el precio primero, el indicador después

El orden de análisis correcto: (1) leer la estructura del precio en sí — tendencia,
rango, soportes/resistencias, velas —, y **recién después** (2) ver cómo reacciona
el indicador a esa estructura. Mirar el indicador aislado del precio pierde el
contexto que le da sentido — es la fórmula reaccionando a algo que no se está
viendo.

### Precepto 3 — La señal está en la relación precio↔indicador, no en el indicador solo

De ahí sale la evaluación de un probable recorte o subida:
- **Confirmación**: precio e indicador se mueven en la misma dirección → refuerza
  la lectura de tendencia.
- **Divergencia**: el precio hace un extremo (nuevo máximo/mínimo) pero el
  indicador NO lo confirma (no hace un extremo equivalente) → señal clásica de
  debilitamiento del movimiento, aviso de posible reversión o pullback.

Ningún indicador "avisa" nada por sí solo — avisa en relación a lo que el precio
está haciendo en simultáneo.

### Precepto 4 — Cada indicador mide UNA cosa, no todo (taxonomía obligatoria antes de usar cualquiera)

Establecido en esta sesión (ver `PLAN_LARGO_PLAZO.md`, corrección de Bollinger)
tras verificar contra fuente primaria cada indicador que el proyecto evalúa:

| Qué mide | Ejemplos | Pregunta correcta a hacerle |
|---|---|---|
| **Dirección/momentum** | Momentum 12-1, RSI, MACD, EMA/KAMA/HMA (medias), Supertrend | ¿Hacia dónde va el precio? — rank IC contra retorno futuro |
| **Régimen/volatilidad** | Bollinger Bands (ancho), ATR (como nivel, no sizing), Keltner | ¿En qué fase de volatilidad está el mercado (tranquila/expansión)? — NO "¿predice retorno?" |
| **Fuerza de tendencia sin dirección** | ADX (crudo) | ¿Hay tendencia o no la hay, sin decir para qué lado? |

Preguntarle a un indicador de régimen "¿predecís el retorno futuro?" es la pregunta
equivocada — no importa cuánto se lo testee, la respuesta no va a ser interpretable
porque no fue diseñado para eso. Verificar SIEMPRE contra el origen/autor del
indicador antes de decidir qué protocolo de test le corresponde — no asumir por
familia ("es una media móvil, va con momentum/RSI") sin confirmar qué mide
realmente el output final.

### Precepto 5 — Todo indicador tiene lag inherente, por ser función del precio pasado

Ningún indicador anticipa el precio sin lag — es matemáticamente imposible si es
una función del precio histórico (media, ratio, oscilador). La diferencia entre un
indicador "rápido" (HMA) y uno "lento" (SMA) es CUÁNTO lag tiene, no si tiene o no.
Esto también implica: un indicador nunca es causa del movimiento de precio, es
consecuencia — cuidado con el lenguaje ("el MACD generó la suba") que invierte la
causalidad real.

### Precepto 8 — No estacionariedad temporal: lo que funciona hoy puede dejar de funcionar, y viceversa

Una estrategia o indicador que mide edge hoy puede perderlo mañana, y uno sin edge
hoy puede empezar a tenerlo después. No es una posibilidad remota — es un fenómeno
documentado en la literatura (McLean & Pontiff, 2016, *"Does Academic Research
Destroy Stock Return Predictability?"*, *Journal of Finance*: factores publicados
pierden ~⅓ de su retorno post-publicación, por crowding — más capital persiguiendo
la misma señal la erosiona) y consistente con los cambios de régimen macro que el
propio proyecto ya mapea (GOLDILOCKS/DEFLATION/STAGFLATION vía `regime_gate.py`).

**Consecuencia práctica — esto es lo que operacionaliza el precepto, no una idea
abstracta**: el proyecto YA construyó `app/core/drift_detector.py` (M5, KS +
Bonferroni + detección de concepto, 18 tests) — pero **verificado ahora: no está
conectado a ningún path en vivo** (`advisor.py`, `signal_engine.py`) — existe,
tiene tests, y no monitorea nada en producción todavía. Momentum y RSI (los dos
factores validados) podrían estar decayendo ahora mismo y el sistema no se
enteraría. Conectar M5 al monitoreo continuo de esos dos factores es una tarea
real y barata (el módulo ya existe) — más urgente que sumar indicadores nuevos.

### Precepto 9 — Las estrategias deben ser flexibles y rotar; la no-estacionariedad también existe a granularidad fina

No es solo "el régimen macro cambia mes a mes" — la actividad de mercado varía
incluso dentro del mismo día. Patrón bien documentado en microestructura (Admati &
Pfleiderer, 1988, y literatura posterior): volumen y volatilidad forman una curva
en U durante la rueda — alta actividad en la apertura, un "valle" al mediodía, alta
actividad de nuevo al cierre. Un indicador o timing que funciona bien cerca del
cierre no necesariamente funciona igual a media mañana.

**Caveat honesto de aplicabilidad**: el motor de fortress_core opera con señal
diaria (EOD) y holds de ~20 ruedas — esta granularidad intradía HOY no es
directamente accionable para la señal misma. Donde sí podría aplicar es en el
**timing de ejecución de la orden** dentro del día (algo que Tarea D/M4 ya rozó al
medir costos de ejecución) — pero explotar esto de verdad sería una línea de
investigación nueva, con su propio pre-registro y datos intradía, no una extensión
gratis de lo que ya existe. No confundir "es un patrón real" con "ya lo estamos
usando" — no lo estamos usando.

La idea de "rotar entre estrategias según la condición" ya tiene su mecanismo
construido y sin usar: `regime_gate.py` (M3) — ver Precepto 6 y Parte 2. Es el
mismo punto repetido: la infraestructura para adaptarse existe, lo que falta es el
trial que la conecte a una decisión real.

### Precepto 6 — Un indicador sirve según el momento y condición de mercado, no de forma universal

La eficacia de un indicador NO es constante en el tiempo — depende del régimen
(tendencia vs rango, alta vs baja volatilidad, macro). Un indicador puede no tener
edge medido en pooled/promedio y sí tenerlo condicionado a un régimen específico
(o viceversa: tener edge promedio que en realidad viene de un solo régimen y es
nulo en los demás). **Consecuencia práctica**: ningún indicador se descarta por
analogía con otro que falló en un test distinto (pooled/pasado) sin antes probarlo
condicionado por régimen — es exactamente el error que se corrigió en esta sesión al
proponer descartar KAMA/HMA/MACD/Supertrend sin testearlos primero.

### Precepto 7 — Fundamentar antes de testear, evidencia antes que intuición

Antes de diseñar el test estadístico de cualquier indicador: (1) buscar quién lo
inventó y qué mide conceptualmente contra fuente primaria/académica, (2) revisar si
`RESEARCH_PREDICTIVE_INDICATORS.md` ya lo cubre con effect size documentado, (3)
recién ahí pre-registrar el test. Nunca aplicar por default el protocolo de
momentum/RSI a un indicador nuevo sin este paso.

---

## Parte 1 — Diccionario de indicadores

El catálogo completo (definición, características, rol predictivo, origen
verificado contra fuente primaria para los que están en evaluación activa) vive en
[`DICCIONARIO_INDICADORES.md`](DICCIONARIO_INDICADORES.md) — técnicos (precio,
tendencia, momentum, osciladores, volatilidad) y fundamentales (valoración,
rentabilidad, crecimiento, apalancamiento, liquidez, eficiencia, riesgo/retorno).

Resumen de los que el motor usa o está evaluando activamente hoy:

| Indicador | Mide (Precepto 4) | Estado en el motor |
|---|---|---|
| Momentum 12-1 | Dirección | **En producción** — único factor con IC medido fuerte (Jegadeesh & Titman 1993) |
| RSI | Dirección | **En producción** — segundo factor con IC medido (Wilder 1978) |
| EMA (trend gate) | Dirección | **En producción** — gate mecánico (close>EMA50>EMA200) |
| ADX | Fuerza de tendencia (sin dirección) | Gate mecánico (≥20); refutado como señal escalar (§25) |
| ATR | — (sizing, no señal) | **En producción** — dimensiona stops (2×/4×ATR) |
| KAMA, HMA, Supertrend | Dirección | En evaluación (Tarea M), condicionado por régimen |
| MACD | Dirección | En evaluación (Tarea N), condicionado por régimen |
| Bollinger (ancho) | Régimen/volatilidad | En evaluación (Tarea N) — protocolo de régimen, no dirección |

---

## Parte 2 — Lecciones empíricas del proyecto (evidencia ya obtenida, no repetir sin motivo)

Ver `PLAN_MEJORA_MATEMATICA.md §6-§11` (2026-08-11) para el detalle completo —
resumen aplicable a cualquier análisis futuro:

- **La combinación/mezcla de factores vía regularización (ridge) ya se probó** —
  momentum+RSI+macro_composite combinados: el IC mejoró (+0.0156, ICIR 0.78) pero
  el gate real (DSR ≥0.90, costos, sizing) lo refutó 0/3. Un IC mejor NO garantiza
  que se traduzca en resultado neto operable — separar siempre "¿el número sube?"
  de "¿sobrevive costos y mecánica real?".
- **Las tres ramas de arquitectura de producto ya se testearon**: selección
  individual de 50 símbolos (muerta), rotación sectorial/cluster vía RMT (muerta,
  aunque la estructura de co-movimiento existe — no es lo mismo que predictibilidad),
  timing sobre basket único vía ADX (muerto, Trial #14). Ninguna sobrevivió con la
  arquitectura de factores usada hasta ahora.
- **Ninguna de esas pruebas condicionó por régimen** (Precepto 6) — testearon pooled
  o por ventana de tiempo completa, no "¿funciona el factor SOLO cuando el régimen
  es X?". Esa pregunta sigue genuinamente abierta para todos los factores, viejos y
  nuevos — es la línea de investigación activa hoy (Tarea M/N + `regime_gate.py`/M3).
- **El costo real medido (§33, validado contra JoF 2025) es 0.05%/lado** — cualquier
  análisis de rentabilidad neta parte de ese número, no del 0.15% viejo.
- **Sentimiento retail (AAII) como señal contrarian — refutado RETROSPECTIVAMENTE,
  dos veces** (§28 y su re-test, `PLAN_MEJORA_MATEMATICA.md` líneas 2126/2686):
  primera medición dio signo contrario al esperado por la hipótesis (W2 t=+2.94,
  contrarian predice negativo), segunda medición (vara más justa) t=+1.18, tampoco
  significativo. El retail sí subrinde por sesgos de comportamiento documentados
  (Barber-Odean 2000, Taiwán 2008 — ya citados en `RESEARCH_EXTERNA_CRITICA.md`),
  pero el intento más directo de explotar eso como señal de timing ya falló acá con
  datos históricos.
  **Condición de Boris (2026-08-20) sobre cómo re-abrir esto**: no re-testear
  retrospectivamente pegado al backtest — eso ya se hizo, dos veces, con el mismo
  resultado. Si se retoma, es con **evaluación PROSPECTIVA**: monitorear la
  relación AAII↔retorno hacia adelante, sobre datos que todavía no existen al
  momento de pre-registrar, no sobre una ventana histórica ya vista. Es un estándar
  más alto que el backtest (cero riesgo de data-mining porque el dato no existía
  cuando se formuló la hipótesis) — no un atajo para reabrir sin evidencia nueva.
  No pre-registrar esto como trial hasta tener el mecanismo de monitoreo prospectivo
  (ej. wired a `drift_detector.py`/M5, ver Precepto 8) listo para correr hacia
  adelante, no hacia atrás.
