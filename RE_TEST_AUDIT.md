# A3/H3.1 — Auditoría de integridad: familia `re_test` y evasión de Bonferroni

**Tipo:** Auditoría de integridad (no trial de mercado).
**Fecha:** 2026-08-26.
**Estado:** Propuesta para revisión con Boris — NO implementar todavía.

---

## 1. Vulnerabilidad resumida

La familia `re_test` puede evadir la corrección de Bonferroni **por diseño actual del código**, no por abuso del historial. El historial existente es limpio (2 entradas legítimas), pero nada en el código impide que una entrada futura se etiquete `re_test` sin ser realmente un re-test de algo ya refutado, y no hay límite a cuántas veces se invoca la familia.

Consecuencia: un agente podría registrar infinitos `re_test` consumiendo 0 budget, cada uno juzgado contra el umbral original (más fácil), sin que el umbral de la familia original se endurezca. Esto anula la corrección de Bonferroni.

---

## 2. Análisis de causa raíz

### 2.1 Contrato actual (`_validate_entry`, línea 71-85)

La validación es **uniforme para todas las familias**: requiere 9 campos, veredicto ∈ {CUMPLE, NO_CUMPLE}, `n_trials_consumidos >= 0`. No hay lógica específica de familia.

Lo único que distingue a `re_test` es un comentario (línea 82-83): "0 es valido: los re-tests de variables ya refutadas". Pero ese comentario **no se aplica como regla** — es solo documentación. Cualquier familia puede registrar `n_trials_consumidos=0` y sería válido.

### 2.2 Registro (`register_trial`, línea 97-105)

Solo verifica unicidad de `id` y validez de forma. No hay:
- Referencia al trial original que se re-testea.
- Verificación de que el original existe y fue refutado.
- Límite de re-tests por trial original.

### 2.3 Presupuesto (`consumed_budget` / current_threshold)

```python
consumed_budget("re_test")  # siempre 0, porque todos tienen n_trials_consumidos=0
current_threshold("re_test")  # siempre 0.90 (BASE_THRESHOLD), NUNCA se endurece
```

El mecanismo de evasión:
1. Trial original en `motor_signal` consume slot → umbral sube.
2. Re-test se registra como `re_test` con `n_trials_consumidos=0` → **no consume slot en `motor_signal`**.
3. El re-test se juzga contra el umbral original (más fácil, ej. n_trials=17).
4. Siguiente trial en `motor_signal` enfrenta un umbral artificialmente bajo.
5. Repetible infinitamente: cada nuevo `re_test` es "gratis" y no penaliza.

### 2.4 El historial existente es limpio (verificado)

| id | original implícito | veredicto original | n_trials_consumidos | ¿Legítimo? |
|---|---|---|---|---|
| `fase06_retest_sentimiento` | `trial_08_sentimiento` | NO_CUMPLE | 0 | Sí — confirma refutación #8 |
| `fase06_retest_fundamentales` | `trial_09_fundamentales` | NO_CUMPLE | 0 | Sí — confirma refutación |

Ambas referencian el trial original en el campo `hipotesis` (texto libre) y citan `n_trials=17` correcto. Pero **esa referencia es convención humana, no código**. Nada impide que la próxima entrada `re_test` invente un original que no existe, o que re-testee algo que CUMPLE.

---

## 3. Propuesta de garantías

### Principio rector

Preservar el diseño: un re-test es "gratis" porque confirma una refutación, no explora hipótesis nueva. Pero acotarlo estructuralmente para que no sea un agujero negro de Bonferroni.

### Garantía 1 — Referencia obligatoria y verificable (ALTA PRIORIDAD)

Agregar campo `original_id` al contrato. Regla:

- **Obligatorio** cuando `familia == "re_test"`, **prohibido** en otras familias.
- Debe referenciar un `id` existente en el ledger.
- El original debe tener `veredicto == "NO_CUMPLE"` (solo se re-testea lo refutado).
- El original **no puede ser otro `re_test`** (no cadenas de re-tests).

Implementación: nueva validación en `_validate_entry` (o función dedicada `_validate_re_test`) que reciba el ledger completo para verificar la referencia.

### Garantía 2 — Tope duro de re-tests por trial original (ALTA PRIORIDAD)

Límite: **máximo 2 re-tests por `original_id`**.

Justificación:
- 1 re-test alcanza para confirmar una refutación con metodología corregida.
- Un segundo permite un escenario distinto (otro universo, otro período).
- Más de 2 es ruido estadístico disfrazado de confirmación — y abre la puerta a evasión.

Implementación: contar entradas existentes con mismo `original_id` en `register_trial` y rechazar si ya hay 2.

### Garantía 3 — (OPCIONAL) Consumo parcial de budget en familia original

Alternativa más conservadora: que cada `re_test` consuma `n_trials_consumidos=1` en la **familia del original** (no en `re_test`). Así el umbral de `motor_signal` se endurece igual.

**Trade-off:** pierde el incentivo de re-test gratis (confirmar refutaciones es valioso y no debería costar). Recomiendo **no** adoptar esto por ahora; las garantías 1+2 son suficientes y menos disruptivas.

---

## 4. Impacto en el contrato actual

### Campo nuevo

```python
# Para re_test: obligatorio
"original_id": "trial_08_sentimiento"

# Para otras familias: ausente (no en el dict)
```

### Validación nueva (pseudocódigo)

```python
def _validate_re_test(entry, existing_entries):
    if entry["familia"] != "re_test":
        if "original_id" in entry:
            raise TrialRegistryError("original_id solo permitido en familia re_test")
        return

    # re_test: original_id obligatorio
    if "original_id" not in entry:
        raise TrialRegistryError("re_test requiere original_id")

    original = find_by_id(existing_entries, entry["original_id"])
    if original is None:
        raise TrialRegistryError(f"original_id no existe: {entry['original_id']}")
    if original["veredicto"] != "NO_CUMPLE":
        raise TrialRegistryError(f"original no esta refutado: {entry['original_id']}")
    if original["familia"] == "re_test":
        raise TrialRegistryError("no se permite cadena de re-tests")

    # Tope: max 2 re-tests por original
    count = sum(1 for e in existing_entries
                if e["familia"] == "re_test"
                and e.get("original_id") == entry["original_id"])
    if count >= 2:
        raise TrialRegistryError(f"original ya tiene 2 re-tests: {entry['original_id']}")
```

### Migración del historial existente

Las 2 entradas `re_test` actuales NO tienen `original_id`. Opciones:

| Opción | Descripción | Recomendación |
|---|---|---|
| A | Backfill manual: agregar `original_id` a las 2 entradas existentes | **Sí** — son legítimas y el original es inequívoco |
| B | Dejar las existentes como están (grandfather clause), exigir `original_id` solo para nuevas | Alternativa válida, pero deja inconsistencia en el ledger |

Recomiendo **A**: backfill de las 2 entradas existentes con su original (`trial_08_sentimiento` y `trial_09_fundamentales`).

---

## 5. Impacto en tests

Tests nuevos necesarios (sin implementar todavía):

1. `re_test_sin_original_id_falla` — obligatoriedad del campo.
2. `re_test_con_original_inexistente_falla` — verificación de existencia.
3. `re_test_con_original_que_cumple_falla` — solo refutados.
4. `re_test_encadenado_falla` — no cadenas.
5. `re_test_tercer_intento_falla` — tope de 2.
6. `re_test_valido_se_registra` — camino feliz.
7. `original_id_en_otra_familia_falla` — prohibido fuera de re_test.
8. Backfill: las 2 entradas existentes deben seguir pasando validación (o actualizarse primero).

---

## 6. Recomendación

Implementar garantías 1 (referencia verificable) y 2 (tope de 2) juntas. Son ortogonales y ambas necesarias:

- Sin 1: podrías registrar infinitos `re_test` con `original_id` inventado.
- Sin 2: podrías registrar infinitos `re_test` del mismo original legítimo.

La garantía 3 (consumo de budget) la dejo como opción futura si se detecta que el tope de 2 sigue siendo insuficiente.

**NO implementar hasta que Boris revise y apruebe.**

---

## 7. Hallazgos de la auditoría

- **H1:** `_validate_entry` no distingue familias — toda entrada se valida igual.
- **H2:** `n_trials_consumidos=0` es válido para CUALQUIER familia, no solo `re_test`.
- **H3:** `current_threshold("re_test")` es constante (0.90) — nunca se endurece.
- **H4:** No hay campo estructural que vincule un `re_test` con su original.
- **H5:** No hay límite de re-tests por trial original.
- **H6:** El historial actual es limpio, pero la limpieza es por convención, no por código.
