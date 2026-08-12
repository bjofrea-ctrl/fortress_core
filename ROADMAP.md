# Roadmap — fortress_core

Documento vivo que centraliza TODO lo que quedó abierto, en todas las áreas — no sólo
matemática/investigación. Existe porque el rigor que se aplicó a la validación estadística
nunca se declaró explícitamente para el resto del proyecto, y eso no puede depender de que
alguien se acuerde de pedirlo cada vez.

**Cómo se usa**: al empezar cualquier sesión de trabajo (con cualquier herramienta — Claude
Code, Cline, OpenCode), leer este documento primero. Al cerrar, actualizarlo antes de cerrar
— marcar lo que se cerró, agregar lo que apareció nuevo. Ningún ítem se da por cerrado sin
marcarlo acá, aunque se haya resuelto "de pasada" en otra conversación.

Última actualización: 2026-08-12.

---

## Gantt — todas las vías abiertas

```mermaid
gantt
    title Roadmap fortress_core — todas las áreas
    dateFormat X
    axisFormat Sesión %d

    section Investigación / matemática
    §13 gap-reversion: backtest con costos reales   :active, gr1, 0, 1d
    §12 régimen-vs-volatilidad: más historia o menos estados HMM :gr2, 0, 2d
    Fase 0.6: re-test sentimiento/fundamentales (panel limpio) :gr3, 0, 1d
    Investigación académica/foros externa (pendiente, nunca hecha) :crit, gr4, 0, 1d

    section Código — P0 (bajo esfuerzo, alto impacto)
    Fix contrato GovernancePanel <-> backend      :done, c1, 0, 1d
    Fix except desnudo + errores como 200 OK      :done, c2, 0, 1d
    Auth mínima + SECRET_KEY que falla si no está :done, c3, 0, 1d

    section Código — P1
    Fechas hardcodeadas de market.py (2015-2024)  :c4, after c3, 1d
    Alinear Python Dockerfile vs venv real        :c5, after c3, 1d
    Corregir README (Redis, versión, endpoints)   :c6, after c3, 1d
    Corregir docstring Controller/Judge (no LLM)  :c7, after c3, 1d

    section Código — P2
    Tests de integración governance + routers     :c8, after c4, 2d
    Decidir destino de prompt_engine.py           :c9, after c4, 1d
    CI básico (lint + test en push)               :c10, after c4, 1d

    section Producto / decisiones pendientes
    Uso real de LEAN/QuantConnect (parqueado, sin objetivo definido) :p1, 0, 1d
    Conexión a broker (bloqueada hasta validar edge neto de costos)  :p2, after gr1, 1d
```

---

## Tabla maestra — todo lo abierto, con dueño y bloqueo

| Área | Ítem | Estado | Bloqueado por | Próxima acción |
|---|---|---|---|---|
| Investigación | §13 gap-reversion: backtest con costos reales | 🟡 en curso | — | Correr backtest con costos 0.15%/lado, dos operaciones/día |
| Investigación | §12 régimen-vs-volatilidad | 🟡 pista sin cerrar | Más historia o menos estados HMM | Decisión: ¿vale la pena esperar más datos? |
| Investigación | Fase 0.6 — re-test sentimiento/fundamentales | ⚪ nunca se hizo | — | Correr contra panel limpio + universo 50 (barato, no consume hipótesis nueva) |
| Investigación | Investigación académica/foros de trading cuántico | 🔴 pendiente, recién detectado | — | Buscar afuera: papers + foros sobre gobernanza multi-agente LLM, risk-mgmt-first para operadores chicos, crítica externa al enfoque |
| Código P0 | Contrato GovernancePanel ↔ backend | 🟢 cerrado (2026-08-12) | — | Frontend consume contrato real (`triad.{bull,bear,contrarian}.score`, `controller.approved`, `judge.verdict|status`); 5 tests de regresión en `test_governance_contract.py` |
| Código P0 | `except:` desnudo + 200 OK con error en body | 🟢 cerrado (2026-08-12) | — | `market.py`/`live.py` ahora levantan HTTPException 500; `except:` acotado a (AttributeError, TypeError, ValueError); 0 patrones restantes en routers |
| Código P0 | Auth mínima global + `SECRET_KEY` que falla si no está seteado | 🟢 cerrado (2026-08-12) | — | `hmac.compare_digest` en `verify_api_key`; Settings valida SECRET_KEY fuera de development (default bloqueado: `test_secret_key_default_blocked_outside_development`). Nota: 25/27 endpoints siguen abiertos POR DECISIÓN (UI pública con repo público) — solo rutas de escritura RAG tienen key; el resto es deliberado mientras la UI sea pública |
| Código P1 | Fechas hardcodeadas de `market.py` (2015-2024) | 🔴 sin empezar | — | Dashboard sirviendo datos de hace año y medio |
| Código P1 | Python 3.11 (Dockerfile) vs 3.9.6 (venv real) | 🔴 sin empezar | — | Alinear una de las dos |
| Código P1 | README desactualizado (Redis, versión, endpoints) | 🔴 sin empezar | — | Reescribir o borrar lo aspiracional |
| Código P1 | Docstring Controller/Judge dice que usan LLM (no es cierto) | 🔴 sin empezar | — | Corregir comentario en `advanced_agents.py` |
| Código P2 | Tests de integración governance + 7 routers sin cobertura | 🔴 sin empezar | — | Empezar por el contrato que ya se sabe roto |
| Código P2 | `prompt_engine.py` — 659 líneas muertas con bug adentro | 🔴 sin empezar | — | Decidir: borrar o integrar de verdad |
| Código P2 | CI básico (lint + test en push) | 🔴 sin empezar | — | Repo público sin ningún check automático |
| Producto | `signal_engine.py` comentario/cita falsa sobre ADX | 🟡 spawneado | — | `task_22ea3f8d` — pendiente de que el usuario lo dispare |
| Producto | LEAN/QuantConnect | ⚪ parqueado | Sin objetivo de producto definido | No tocar hasta decidir para qué sirve concretamente |
| Producto | Conexión a broker real | 🔴 bloqueada, correctamente | Validar edge neto de costos primero (§13) | No avanzar hasta cerrar investigación |

**Leyenda**: 🔴 crítico/sin empezar · 🟡 en curso/parcial · ⚪ parqueado, sin decisión de producto · 🟢 cerrado

---

## Por qué existe este documento

El patrón que se repitió en esta sesión: cada vez que una herramienta (OpenCode, Cline) entregaba
un resultado, había que pedir explícitamente "verificá esto contra el artefacto real" para que
la verificación pasara — nunca ocurría por defecto. Lo mismo con el alcance: el rigor
matemático se mantuvo altísimo durante semanas, pero nadie declaró en ningún momento "che, el
resto del proyecto no está pasando por el mismo filtro" — hasta que se pidió una auditoría
explícita.

Este documento no resuelve eso solo — sigue haciendo falta que alguien (usuario o quien
retome la sesión) lo lea. Pero si se mantiene actualizado, al menos nada se pierde por
descuido: lo que no se cerró queda escrito, no depende de la memoria de una conversación
particular.
