# Auditoría de mecánica — áreas nunca evaluadas (2026-08-13)

> Segunda auditoría, complementaria a `AUDITORIA_TECNICA.md` (código/infra) y a
> `PLAN_MEJORA_MATEMATICA.md` (señales). Pregunta: ¿qué áreas del sistema NO se
> evaluaron nunca, y cuáles podrían mover la rentabilidad?
>
> Contexto: 17 secciones de investigación de SEÑAL (§1-§19) refutaron prácticamente
> todo. Esta auditoría deja de mirar "qué comprar" y mira **la mecánica**: cuándo se
> sale, cuánto tiempo se sostiene, cuánto capital se usa, y si el filtro de entrada
> es razonable. Todo verificado contra datos reales del backtest, no desde memoria.

---

## Hallazgo 0 (operativo, urgente) — el trial #15 EVT murió sin terminar

El proceso `trial_evt_stops.py` (PID 75882) **ya no existe** y su artefacto
`trial15_evt_stops_20260813_161033.txt` quedó cortado en "Corriendo baseline..."
(14 líneas, sin veredicto). El log no tiene traceback ni error — terminación
silenciosa tras ~18 min de CPU. **No hay resultado de §20; hay que re-correrlo.**
Sugerencia: lanzarlo con `nohup` + redirección persistente y un `echo` de heartbeat
cada ventana, para distinguir "murió" de "sigue corriendo" sin ambigüedad.

---

## Hallazgo 1 — Las reglas de SALIDA nunca se validaron, y destruyen más valor del que el sistema genera

Datos reales del baseline oficial (`baseline_clean_20260811_150643_trades.parquet`,
286 operaciones):

| razón de salida | n | PnL medio | **PnL total** | días (mediana) |
|---|---|---|---|---|
| **REGIME_STOP_HIT** | 41 | **−$143.10** | **−$5,867** | 10 |
| PORTFOLIO_REGIME_STOP | 22 | +$12.46 | +$274 | 1 |
| TECHNICAL | 91 | +$11.11 | +$1,011 | 11 |
| TRAILING_STOP | 61 | +$47.80 | +$2,916 | 29 |
| PARTIAL_TP | 71 | +$63.59 | +$4,515 | 7 |
| **TOTAL** | 286 | | **+$2,849** | 11 |

**El stop de régimen resta −$5,867 mientras el sistema entero gana +$2,849.** Es,
por lejos, el mayor destructor de valor del motor — más del doble de la ganancia
total.

Y sus umbrales nunca se validaron: `REGIME_THRESHOLDS` en `adaptive_risk.py:7-12`
fija `position_stop` en 0.05/0.07/0.08/0.03 según régimen — números elegidos a
mano, nunca sometidos a DSR ni a walk-forward. Lo mismo vale para el resto de la
mecánica de salida: PARTIAL_TP a `2.0×ATR`, activación del trailing a `1.5×ATR`,
trailing a `2.0×ATR`, salida técnica `adx<20 or (close<ema20<ema50)`
(`adaptive_risk.py:113-141`). Todas constantes hardcodeadas sin evidencia.

**Advertencia honesta**: −$5,867 NO significa "quitando el stop ganamos $5,867
más". El stop cierra posiciones que podrían haber empeorado. El contrafáctico
("¿qué habría pasado si se sostenían?") requiere simulación, y optimizar umbrales
sobre los mismos datos es la trampa de sobreajuste clásica. Por eso el plan de
abajo lo trata con el mismo protocolo que todo lo demás: pre-registro +
walk-forward + DSR.

---

## Hallazgo 2 — Desajuste de horizonte: investigamos a 20 días, operamos a 11

**Toda** la investigación de señal usa `HORIZON = 20` (verificado en
`diagnose_rr2_intraday.py`, `diagnose_ma200_clusters.py`,
`diagnose_regime_volatility.py`, `diagnose_donchian_intraday.py`,
`diagnose_rr2_subperiodos.py`, `diagnose_ma200_beta_control.py`). Pero el motor
real no sostiene 20 días:

- Tenencia **mediana: 11 días**; media 15.2
- **49.0%** de las operaciones cierran en **≤10 días**
- Sólo **25.5%** llegan a durar ≥20 días

Es decir: medimos si los factores predicen el retorno a 20 días, mientras el motor
cierra la mitad de sus posiciones antes de los 10. **El IC que medimos no
corresponde al horizonte en el que el sistema realmente opera.**

Esto es metodológicamente serio y nunca se cuestionó. No invalida los rechazos
anteriores (un factor sin señal a 20d podría no tenerla tampoco a 10d), pero
significa que **nunca miramos el horizonte correcto**. Es barato de corregir:
reusa el panel existente, sólo cambia el target.

---

## Hallazgo 3 — Sólo se despliega 13.4% del capital (diagnosticado, nunca accionado)

`capital_usage_20260811_074928.txt` (sub-trial §9.3, informe sin decisión posterior):

- Uso de capital: **media 13.4%**, mediana 11.4%, máximo 37.4%
- **69.6% de los días con menos del 10% desplegado**; 0% de días sobre 50%
- Posiciones simultáneas: media 1.14, mediana 1 (tope: 5)
- Días con ≥1 señal del gate: 41.6%
- **El tope de 5 posiciones nunca recortó nada**: 0 señales perdidas en las 3 ventanas

Implicación mecánica directa: con 13.4% desplegado, un edge que rindiera 20% anual
sobre el capital invertido se traduce en ~2.7% sobre el capital total. **La
dilución mecánica es enorme y no viene de la señal, viene del diseño.**

Matiz importante: subir el despliegue amplifica lo que haya — y hoy no hay edge
verificado, así que amplificaría pérdidas igual que ganancias. **Esto se acciona
DESPUÉS de establecer que hay algo, no antes.**

---

## Hallazgo 4 — El gate de entrada nunca se validó como conjunto

`RESUMEN_VALIDACION_VARIABLES.md §6.3` ya lo declaraba ("el gate duro nunca se
testeó variable por variable"), pero hay algo más profundo sin testear: el gate
completo (`trend_ok & adx≥20 & rsi∈(40,75) & vol_ratio≥1.0`,
`signal_engine.py:107`) es una conjunción de 4 condiciones que sólo deja pasar
señales el 41.6% de los días, con 1.9 señales de media.

Lo que sí se sabe: el gate CONCENTRA señal (IC de momentum dentro del gate ≫ fuera
— `SESSION_LOG.md:781`). Lo que NO se sabe: si esa concentración compensa el costo
de operar tan poco. Un gate que mejora el IC pero deja el capital parado el 70% del
tiempo puede ser peor que uno más laxo con IC menor. Nunca se comparó.

---

## Plan de implementación

Ordenado por **(costo bajo → alto)** y **(reencuadra lo anterior → construye
encima)**. Todo bajo la disciplina de siempre: pre-registro antes de correr,
walk-forward donde haya calibración, artefacto verificable, revert si no cumple.

### Fase M0 — Re-correr el trial #15 EVT (desbloqueo)
Terminar lo que quedó a medias antes de abrir nada nuevo. Sin cambios de
metodología: el pre-registro de §20 ya está bien (walk-forward, anti-lookahead).
Sólo hace falta ejecución robusta y confirmación de que llegó al final.

### Fase M1 — Auditoría de horizonte ✅ CERRADA (2026-08-13, `PLAN_MEJORA_MATEMATICA.md §21`)

**Resultado: el horizonte NO ocultaba señal.** Ningún factor cruza Bonferroni-6 a 5d
ni a 10d (`horizon_audit_20260813_173648.txt`). El check de fidelidad dio exacto
(max\|dif\|=0 sobre 2069 filas) y la columna 20d reprodujo exactamente §0.5a
(momentum −0.28, rsi +1.38, adx +2.31), confirmando la reimplementación. El
desajuste de horizonte era real como problema metodológico, pero todos los rechazos
previos se refuerzan: los factores no seleccionan en ningún horizonte relevante.
Único dato nominal reportado por honestidad: `rsi_score` a 5d, t=+2.18 — cruza
\|t\|>2 sin corregir, no sobrevive Bonferroni-6.

<details><summary>Especificación original (cumplida)</summary>
Re-correr el diagnóstico de rank IC intra-día a **5d y 10d** además de 20d, sobre
el mismo panel limpio y con el mismo protocolo (Newey-West, Bonferroni por el
número de horizontes × factores). Pre-registrar el criterio antes.

- **Si aparece señal a 5-10d donde no la había a 20d**: es el hallazgo más
  importante del proyecto — significa que medimos en el horizonte equivocado
  todo este tiempo, y varias refutaciones habría que revisarlas.
- **Si no aparece**: cierra la duda de forma definitiva y refuerza todos los
  rechazos anteriores. Ganamos certeza aunque el resultado sea negativo.

Costo: bajo (reusa panel e infraestructura). Riesgo de sobreajuste: bajo (es un
diagnóstico, no un ajuste de parámetros).
</details>

**Ampliación M1b (2026-08-13, `PLAN_MEJORA_MATEMATICA.md §21.1`)**: el usuario
notó que sólo se había variado el horizonte hacia el lado corto — faltaba el lado
largo, con una razón académica real (`momentum_12_1` es Jegadeesh-Titman clásico,
evidencia en tenencias de 3-12 meses). Se testeó 60d y 125d con Bonferroni-12
(la corrección más estricta de todo el proyecto, sobre la familia completa de
horizontes). **Ningún factor pasa.** Auditoría de horizonte COMPLETA: sin señal
entre 1 semana y 6 meses, en ningún punto.

### Fase M2 — Diagnóstico contrafáctico de salidas (no optimización todavía)
Antes de tocar ningún umbral: medir qué habría pasado con las 41 posiciones
cerradas por `REGIME_STOP_HIT` si se hubieran sostenido hasta su salida natural
(técnica o trailing). Es un diagnóstico descriptivo sobre datos ya existentes, sin
parámetros libres que ajustar — no consume slot de `n_trials`.

- Si esas posiciones se habrían recuperado en su mayoría → el stop de régimen está
  demasiado ajustado y hay una hipótesis real que pre-registrar.
- Si habrían empeorado → el stop está haciendo su trabajo y el −$5,867 es el
  precio del seguro, no una fuga. Se cierra el tema.

### Fase M3 — Trial de mecánica de salida (sólo si M2 lo justifica)
Pre-registro formal con slot propio de `n_trials`: variante del risk manager por
subclase (producción intocada, mismo patrón que #13/#15), umbrales de salida
**walk-forward** (nunca calibrados sobre el período que después se evalúa),
ventanas W1-W3, DSR≥0.90 en ≥2/3, revert automático si no cumple.

**Advertencia explícita**: acá es donde el riesgo de sobreajuste es más alto de
todo el proyecto — hay muchos parámetros de salida y pocos datos. Si se testean
varias variantes, corrección por comparaciones múltiples obligatoria y declarada
en el pre-registro.

### Fase M4 — Gate y despliegue de capital (sólo si algo de M1-M3 dio positivo)
Comparar el gate actual contra variantes más laxas, midiendo el trade-off completo
(IC × frecuencia × costos), no sólo el IC. Y recién ahí evaluar subir el despliegue
de capital.

**No se hace antes**: sin un edge establecido, más capital desplegado y más
operaciones sólo amplifican pérdidas y costos — exactamente lo que Barber-Odean
documenta como la causa principal de que los operadores minoristas pierdan
(`RESEARCH_EXTERNA_CRITICA.md §2`).

---

## Nota honesta sobre expectativas

Nada de esto es "encontrar alfa nuevo" — las 17 secciones anteriores agotaron esa
vía con el universo y los datos disponibles. Esto es **arreglar la mecánica que
convierte (o destruye) lo que haya**. Es donde la evidencia dice que hoy se está
perdiendo valor de forma medible: un stop que resta el doble de lo que gana el
sistema, un horizonte de investigación que no coincide con el de operación, y
capital parado el 70% del tiempo.

La mejora realista es de eficiencia, no de descubrimiento. Puede ser significativa
en términos relativos y sigue sin garantizar que el sistema cruce DSR≥0.90 — el
gate de "esto opera solo con plata real" no se mueve.
