# TASK PARA OPENCODE — de Kilo (orquestador, autorizado por Boris 2026-09-06)

Tu worktree: test-opencode-orca. Trabaja SOLO aquí, no en main.
Categoría trial_registry de ambos tickets: infraestructura (gate-legal).
NO pushear ni mergear — Kilo verifica y mergea.

## TU TICKET 1 — B6: cerrar el diagnóstico del golden test "colgado"

**Ya está diagnosticado por Kilo — NO es bug tuyo, es cómputo legítimo.**
Evidencia (corrida con -v + kill a los 75s): el archivo
`tests/test_signal_contract_golden.py` completo pasa 16/17 tests en ~18s y
se clava SOLO en `TestGolden60DayUniverse::test_60_days_universe_bit_identical`
— el único `@pytest.mark.slow` (60 días × 30 símbolos = ~1800 evaluaciones
con SignalEngine completo). Verificación completa de Kilo: el archivo entero
terminó en **7m35s, 30 passed + 2 skipped** (junto a test_collect_iv_surface).
No hay deadlock.

**Fix pedido (pequeño, no toca matemática ni el test)**:
1. Registrar el marker en `pytest.ini`: `markers = slow: tests de equivalencia dorada largos (>5 min)`.
2. Docstring del test: documentar el tiempo esperado (~6-8 min) para que el
   próximo agente no lo confunda con un hang.
3. NO marcarlo skip NI quitarlo: es LA verificación de equivalencia dorada
   que el plan B6 exige.
4. Opcional si querés ir más sólido: `-m "not slow"` como default en addopts
   + un job/documento que diga cómo correr el slow antes de cada merge que
   toque señal/pipeline (verificación completa ANTES de merge, regla 48H).

## TU TICKET 2 — B1: throttle del monitor de rate de Alpaca

**Problema** (re-auditoría externa): el monitor de rate es puramente
observacional — imprime resumen al final, sin alerta ni throttle. Hoy sin
riesgo (30 req vs 200/min) pero escala mal hacia el 1/12.

**Fix**: WARNING visible si el uso supera 70% del límite en la ventana, y
throttle simple (sleep escalonado) si supera 85%.

## Contexto para que no te pises con nadie

- Kilo está mergeando a main TU B6 (892aeca) + B2 (1670136) ya verificados:
  golden tests completos corrieron 7m35s 30 passed — la verificación que
  faltaba está hecha y documentada.
- Kilo también mergeó A2 consolidado (de su rama, no la tuya) + B4/B5/B8 de
  Cline + C1 docs.
- Al terminar: commit en TU rama + avisar a Boris. Kilo verifica y mergea.
