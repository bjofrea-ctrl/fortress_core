# Auditoría de diseño — familia `re_test` y Bonferroni (segunda mirada independiente)

**Autor**: Cline · **Fecha**: 2026-08-26 · **Alcance**: integridad del ledger de trials
(`backend/app/core/trial_registry.py`). Documento de análisis — NO implementa código,
NO es pre-registro de trial, NO abre `.pending-merge.md`.

**Contexto**: auditoría externa GLM (H3.1) afirmó que "la familia `re_test` evade
Bonferroni por diseño". Kilo está trabajando la misma hipótesis por separado; este
documento es la segunda mirada independiente para comparar al final.

## 1. Estado verificado contra el artefacto real

- Código: `trial_registry.py` leído completo (137 líneas). Validación de entrada:
  `_validate_entry()` (líneas 71-85); registro: `register_trial()` (97-105);
  presupuesto: `consumed_budget()` (116-122); umbral: `current_threshold()` (125-133).
- Ledger vivo (`backend/data/trial_registry.json`, gitignored): **47 entradas**.
  Presupuesto por familia: motor_signal 12, signal_diagnosis 26, risk 3,
  backtest_costos 3, producto 1, **re_test 0**.
- Entradas con `n_trials_consumidos=0`: exactamente las 2 de re_test del backfill
  (`fase06_retest_sentimiento`, `fase06_retest_fundamentales`, 2026-08-12).

## 2. El historial está limpio; el problema es el DISEÑO

Confirmado: las 2 entradas existentes son legítimas (re-confirman refutaciones ya
registradas, citan el n_trials original correctamente). La evidencia pasada no
muestra abuso. Lo que sigue audita si el código **impide** un abuso futuro.

**Conclusión anticipada: NO lo impide. H3.1 es correcta, con matices.** La evasión
no es que `re_test` "evade Bonferroni" en sí — es que la EXENCIÓN de costo
(`n_trials_consumidos=0`) existe como valor válido global, sin ninguna condición
estructural que la ate a su única justificación legítima.

## 3. Superficie de ataque — descompuesta en 4 fallas independientes

**F1 — Etiqueta auto-declarada sin anclaje.** `_validate_entry()` valida claves,
tipos y veredicto, pero `familia` es cualquier string y `re_test` es solo una entrada
más de `KNOWN_FAMILIES` ("es referencia, no whitelist", dice el propio comentario).
Nada exige que una entrada `re_test` cite CUÁL hallazgo refutado está re-testeando.

**F2 — El cero es válido en CUALQUIER familia.** La validación permite
`n_trials_consumidos >= 0` universalmente. El comentario (líneas 82-83) explica que
el 0 existe *por los re-tests*, pero el código no enforcementa ese vínculo: una
entrada de `motor_signal` con `n_trials_consumidos=0` pasa sin error y jamás endurece
el umbral de esa familia. Este hueco es incluso más grave que el de `re_test`.

**F3 — Sin límite de reinvocación ni identidad del objetivo.** Aunque la etiqueta se
usara de buena fe, nada impide re-testear la misma hipótesis refutada N veces — cada
una gratis. Re-testear muchas veces el mismo nulo y reportar la mejor corrida es
optional stopping clásico. La exención fue pensada para UN ciclo puntual (Fase 0.6);
hoy es un recurso infinito.

**F4 — Umbral deriva solo del consumo declarado.** `current_threshold()` = función de
`consumed_budget(familia)` exclusivamente. Toda la integridad del control de errores
descansa en que los enteros escritos a mano en el JSON sean honestos. El ledger
falla ruidosamente ante JSON corrupto o incompleto (bien), pero calla ante JSON
completo y mal etiquetado.

**Residuo inevitable**: ningún chequeo sobre el JSON puede verificar que el CONTENIDO
de una corrida coincida con su etiqueta — alguien puede registrar como `re_test` un
experimento genuinamente nuevo (misma familia estadística, hipótesis distinta).
Eso es un problema socio-técnico que el código mitiga pero no resuelve (ver §5).

## 4. Garantía propuesta — validación estructural del vínculo re_test ↔ objetivo

Principio rector del módulo: *"un registro corrupto o incompleto falla RUIDOSAMENTE"*.
Extenderlo a: **un registro internamente inconsistente también falla ruidosamente.**
Tres cambios coordinados, todos aditivos, ninguno toca trials históricos.

### 4.1 Campo obligatorio condicional `re_test_de`

Cuando `familia == "re_test"`, la entrada debe incluir `re_test_de: <id>` apuntando
a OTRA entrada ya registrada. Sin el campo → `TrialRegistryError`. Como
`_validate_entry()` es stateless por entrada, el chequeo de existencia va en
`register_trial()` (que ya carga todas las entradas) y como invariante cruzado en
la carga completa (`_load_raw`), para que también falle ruidosamente un registro
corrupto a mano (no solo vía API de registro).

Condiciones sobre el objetivo referenciado:

1. **Existe** en el ledger (sin forward-references).
2. **Su veredicto es NO_CUMPLE** — la justificación económica de la exención es
   "re-confirmar barato una REFUTACIÓN" (§6.1 RESUMEN, Fase 0.6). Re-testear algo
   que dio CUMPLE es investigación nueva: mismo riesgo de p-hacking que cualquier
   trial nuevo, debe pagar slot en su familia.
3. **Pertenece a una familia de investigación** (las cuatro primeras de
   KNOWN_FAMILIES). No se permite re-test de `producto` ni de otro `re_test`
   (cadenas de segunda derivación sin presupuesto, directamente prohibidas).

### 4.2 Tope de exenciones por objetivo

Máximo 2 entradas `re_test` por cada `re_test_de` (constante nombrada,
`MAX_RETESTS_PER_TARGET = 2`). Más de 2 no es "confirmación adicional": es la
tercera tirada del mismo dado. Si algún día hiciera falta más, el camino correcto
es decidirlo explícitamente subiendo la constante — la decisión queda visible en el
diff, no implícita en datos.

Alternativa considerada y descartada: cobrar slot fraccionado por re-test (0.33,
etc.) — rompe el contrato de enteros del campo y complica la aritmética del umbral;
además no cierra F2. Descartado.

### 4.3 Invariante inversa: el cero SOLO es legal en `re_test`

En `_validate_entry()`: si `n_trials_consumidos == 0` y `familia != "re_test"` →
error. Esto cierra F2, el hueco hermano: sin esta regla, quien quiera evadir
Bonferroni no necesita ni la etiqueta re_test — escribe cero directo en cualquier
familia. Con ella, toda exención queda obligadamente tipificada, vinculada,
limitada y contable.

### 4.4 Contabilidad visible de exenciones

El reporte de estado del registry agrega línea de auditoría: cuántas exenciones
activas hay (`familia=re_test`), contra cuáles objetivos, stock restante por
objetivo. Hoy: 2 exenciones / 2 objetivos distintos / stock ilimitado → tras la
garantía: stock 0 nuevos sin decisión explícita. Una exención invisible en el
reporte es una exención que nadie audita.

## 5. Qué NO propongo (y por qué)

1. **Whitelist cerrada de familias** — contradice el diseño explícito del módulo
   ("referencia, no whitelist") y agrega fricción a cada familia nueva sin cerrar
   nada: el abuso usa etiquetas ya conocidas.
2. **Recalcular thresholds desde artefactos** (contar corridas desde archivos de
   cache): fuerte en teoría, frágil en práctica — las convenciones de nombres de
   artefactos cambiaron varias veces y la fuente de verdad del módulo siempre fue
   el JSON. Mantengo el JSON como fuente y hago sus invariantes estructurales.
3. **Eliminar la familia/exención**: sobre-corrección. Los 2 usos históricos fueron
   metodológicamente correctos y "verificar barato una refutación vieja con datos
   nuevos" tiene valor real de proceso. El objetivo es que sea escasa, trazable y
   acotada — no prohibida.
4. **Backfill migratorio**: las 2 entradas existentes necesitarían agregar
   `re_test_de`; los objetivos existen en el ledger (los trials originales de
   sentimiento y fundamentales, ambos NO_CUMPLE) → backfill trivial y compatible
   hacia atrás. Pero eso es implementación — fuera de este documento.

## 6. Veredicto y alcance para comparar con Kilo

- **H3.1: CONFIRMADA** — la familia `re_test` puede evadir Bonferroni por diseño,
  pero el vector de máxima gravedad real es F2 (cero válido en cualquier familia),
  no la etiqueta en sí. Un fix que solo endurezca `re_test` sin cerrar F2 deja la
  puerta principal abierta.
- **Garantía mínima que lo cierra**: §4.1 + §4.2 + §4.3 juntas — vínculo exigido,
  exenciones acotadas por objetivo, cero legal solo bajo ese vínculo, todo fallando
  ruidosamente. Categoría del trabajo: validación de integridad de registro, directa,
  SIN pre-registro (no consume Bonferroni ni afirma nada empírico sobre el mercado) —
  misma categoría que Brecha 5 y la sincronización de AUDITORIA_TECNICA.

