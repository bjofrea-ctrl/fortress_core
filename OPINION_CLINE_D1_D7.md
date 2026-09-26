# Opinión de Cline sobre D1-D7 — insumo para OpenCode (Boris decide)

> **Qué es esto**: mi opinión fundada sobre las 7 decisiones abiertas de
> `HANDOFF_HIBRIDO_OBJETIVO_SUBJETIVO.md` §4, escrita **antes** de que OpenCode fije nada, para
> que la contraste en vez de heredarla. **Qué no es**: una decisión. Reparto de roles acordado
> con Boris (2026-09-25): OpenCode orquesta/analiza/audita, Cline opina, **Boris decide**.
> Autor: Cline, pane `w2:p3`, 2026-09-25.

## Declaración de sesgo propio (leer antes que mis opiniones)

Yo escribí el handoff, y mi framing favorece la variante "abstención" porque es la que el repo
ya tiene construida. **Si OpenCode llega a la conclusión opuesta con fundamento, su lectura
vale más que la mía** — auditarme es parte de su rol, y el sesgo a declarar es este.

## Mi opinión, decisión por decisión

| # | Mi opinión | Fundamento (verificado) |
|---|---|---|
| **D1** | **B — puerta/abstención** | (a) Precedente propio: M2 ya fue **corregido** para producir abstención diferencial (trial #17 exige 1-30% de abstención y abstendidos = \|point\| máximos). (b) Mide la métrica primaria de la casa (VPP bajo abstención), no una inventada. (c) **No exige que la pata objetiva tenga edge** — y hoy no lo tiene (DSR 0.6077). La variante A (condicional) parte una señal débil en dos grupos y pierde potencia justo donde ya falta |
| **D2** | **Familia nueva, declarada como tal, Y reportar además el número pooled** | El umbral y `consumed_budget` son **por familia** (`trial_registry.py:915/932`): una familia nueva arranca en n=1 → la vara es más baja. Eso **debe quedar escrito ANTES** o es family shopping, no pre-registro. Declarar la familia nueva con su razón (la interacción es una clase distinta) **y** reportar el DSR bajo el presupuesto pooled como número secundario es la versión honesta de las dos cosas |
| **D3** | **Acción (COT) como pata primaria**; AAII secundaria; FinBERT última | COT: responde literalmente la pregunta de Boris ("¿ya lo compraron?"), tiene **historia larga gratis** (descarga por año) y **no está refutado como pata** acá. AAII: historia desde 1987 (potencia de sobra) pero **refutado como factor solo** (trial #8) — legítimo como término de interacción, más débil como primera apuesta. FinBERT: 369 filings / 2 años → potencia demasiado baja para partir en grupos |
| **D4** | **H = 20 ruedas primario, 5 días secundario**, ambos declarados | 20 ruedas es el precedente de la casa (replay de calibración en `decision.py::_fit_calibrators`). Declarar los dos evita la tentación de elegir el horizonte después de ver el resultado |
| **D5** | **Sí, extender COT hacia atrás y agregar refresco** | `COT_START_YEAR=2019` (`market_sentiment.py:93`) es una constante, no un límite de la CFTC: el patrón de URL sirve años anteriores. Y el cache estaba **stale al 2026-08-04** — sin refresco, la pata se degrada sola |
| **D6** | **Reservar ahora, pero DESPUÉS de D7** | Reservar es legal pre-gate (A8 es el precedente). Pero una reserva consume slot (n≥1), así que no se reserva lo que todavía no se sabe si es ejecutable |
| **D7** | **Hacerla PRIMERO, antes de escribir el resto** | Si la potencia no alcanza para detectar un efecto del tamaño que importa, el veredicto correcto es **INEJECUTABLE** y eso **no consume nada** (`consumed_budget` no cuenta INEJECUTABLE — B5). Calcular el MDE antes ahorra escribir un pre-registro entero para un trial que no se puede correr |

## Dos cosas que agrego y no estaban en el handoff

**A1 — La cantidad de familias es un parámetro libre del sistema.** Que el umbral sea por
familia significa que **crear una familia nueva baja la vara**. No lo digo para bloquear D2: lo
digo porque es una propiedad estructural del ledger que **Boris debería conocer al arbitrar**.
Un agente honesto la declara; el sistema no la impide. (Verificable: `consumed_budget` y
`current_threshold` reciben `familia` como argumento.)

**A2 — Trampa a evitar: "miremos el split primero".** Es tentador mirar la tabla descriptiva
(n, PnL medio, hit-rate por grupo) *antes* de decidir el criterio, y eso es p-hacking con otro
nombre. Mi opinión: la tabla descriptiva **es obligatoria como salida del trial**, y se declara
**dentro** del pre-registro, no antes.

## Lo que le pido a OpenCode

1. **Contrastar, no adherir.** Si alguna de estas opiniones es débil, decirlo con `file:line` —
   sobre todo D1, donde mi sesgo es más fuerte.
2. **No heredar mis números.** Verificar `consumed_budget`/`current_threshold` reales de la
   familia elegida en vez de citar lo que escribí.
3. **Dejar el umbral vigente calculado, no copiado.** `current_threshold(familia)` lo deriva de
   las entradas; si el resultado difiere de lo que alguien citó en un doc, **gana el ledger**.
