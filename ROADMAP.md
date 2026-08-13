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

## Plan de implementación consolidado (2026-08-12) — para ejecutar en tandas

El usuario pidió cerrar todo lo pendiente, no sólo lo más urgente. Se secuencia en tandas
chicas en vez de un cambio gigante — mismo criterio de todo el proyecto: verificar entre
pasos, no acumular riesgo. Cada tanda termina con `pytest` completo + commit + este documento
actualizado antes de pasar a la siguiente.

**Modo de trabajo — "fallo, arreglo y sigo" aplica con un límite claro**:
- ✅ Aplica sin pedir permiso: bugs de código normales que aparezcan haciendo estas tandas
  (un import roto, un test que falla por un detalle menor, un typo) — arreglarlos y continuar.
- ❌ NO aplica a nada que toque el motor/investigación (Tanda D): ahí un fallo no se
  "arregla y sigue", se documenta con su artefacto y se decide — la regla no-negociable
  #1 y #3 de `ONBOARDING.md` (pre-registro antes de correr, revert si no cumple el criterio)
  sigue vigente sin excepción. "Arreglar rápido" y "criterio pre-registrado" son cosas
  distintas — no mezclar.

### Tanda A — Código, P1 restante ✅ (cerrada 2026-08-12, commit `a56e516`)
1. ✅ Alinear versión de Python: `backend/Dockerfile` fijado a `python:3.9-slim` (igual que
   el `.venv` real, 3.9.6; todas las deps soportan 3.9).
2. ✅ `README.md`: sacada la mención de Redis, corregida la versión (3.9), documentados los
   27 endpoints reales (tabla completa, 8 routers + `/health`).
3. ✅ Docstrings de Controller/Judge en `advanced_agents.py` corregidos — ahora dicen
   "lógica determinista — no usa LLM" (el flujo de gobernanza sí usa NIM en la tríada,
   pero estos dos agentes son pura lógica).
   Verificación: `pytest` desde `backend/` → 80 passed, 11.58s. Nota: correr pytest desde
   la raíz del repo se cuelga (config en `backend/pytest.ini`); invocación canónica:
   `cd backend && .venv/bin/python -m pytest`.

### Tanda B — Seguridad recién detectada ✅ (cerrada 2026-08-12, commit `217eb51`)
4. ✅ Backup específico de `fortress.db` agregado a `scripts/auto_backup.sh` (función
   `backup_db()`) y `scripts/backup.sh` (paso 6.5): `sqlite3 .backup` (seguro con
   escrituras concurrentes) → `/Volumes/EMPRESA/fortress_core_backups/db/`, retención
   de 20 snapshots.
5. ✅ Rate limit en memoria (sin Redis, el stack no lo tiene) en
   `backend/app/api/rate_limit.py`: ventana deslizante por IP (10 llamadas/60s, default),
   `X-Forwarded-For` aware, log de uso + 429 al exceder. Aplicado a
   `predict/analyze/{symbol}` y `governance/analyze/{symbol}` (los dos GET sin auth que
   disparan LLM real). Tests: `tests/test_rate_limit.py` (4).
   Extras detectados al pasar: `backend/data/` (estado de runtime) ignorado en .gitignore.
   Verificación: `pytest` → 84 passed, 11.07s.

### Tanda C — Código, P2 ✅ (cerrada 2026-08-12, commit `6ae0770`)
6. ✅ Verificado con grep, sin remover: `ProbabilisticEngine` (wrapper) y
   `KellyPositionSizer` SOLO los usa `scripts/test_probabilistic.py` (smoke script de
   desarrollo); `RiskParityAllocator` SOLO `scripts/test_system.py`. No son código
   muerto en sentido estricto → no se tocaron. El módulo `probabilistic_engine.py`
   se queda (backtest_engine, signal_engine y opportunities importan 6 clases útiles
   de ahí: CopulaRiskAnalyzer, ProbabilityCalibrator, BayesianOnlineUpdater, etc.).
7. ✅ `prompt_engine.py` ELIMINADO (659 líneas). `HardinessChecker` (lo único en uso,
   en `triad_agents.py`) movido intacto a `app/core/hardiness.py`; también se eliminó
   `scripts/test_prompt_engine.py` (probaba código muerto) y se portó su cobertura a
   `tests/test_hardiness.py` (7 tests). **Bug latente encontrado y documentado**: el
   assert de alucinación del script viejo NUNCA pudo pasar — `detect_hallucination`
   solo matchea formato "clave: valor", no texto libre.
8. ✅ Tests de integración para 6 de los 7 routers sin cobertura (governance y
   opportunities ya la tenían): `test_backtest_api.py` (8), `test_market_api.py` (6),
   `test_live_api.py` (4), `test_predict_api.py` (6), `test_risk_api.py` (2),
   `test_system_api.py` (2) — patrón del repo: `asyncio.run` directo + monkeypatch,
   sin httpx. **Bug real encontrado y arreglado**: el muestreo de
   `/api/backtest/equity-curve` con `step = len//300` no muestreaba nada entre 300 y
   599 puntos; ahora `ceil(len/300)`.
9. ✅ CI en `.github/workflows/ci.yml`: jobs `lint` (ruff) y `test` (pytest) en cada
   push/PR, Python 3.9. `ruff.toml` en raíz: target py39, `select = [E4,E7,E9,F,I,W]`
   (E501 fuera a propósito: las líneas largas del repo son contenido académico/prompts,
   no código). Autofix inicial: 117 violaciones corregidas + 14 manuales (semicolons,
   `== True` → `.is_(True)`, vars ambiguas `l` → `lesson`, vars sin uso → `_`).
   `ruff==0.16.2` agregado a requirements-dev. Lint: 0 errores. pytest: 119 passed.

### Tanda D — Investigación (en paralelo a A/B/C, no bloquea ni bloquea código)
10. ✅ §13.1 gap-reversion: backtest con costos reales (2026-08-12) — pre-registrado en
    `PLAN_MEJORA_MATEMATICA.md §13.1`, corrido (`backtest_gap_costs.py`, artefacto
    `backtest_gap_costs_20260812_173951.txt`): **NO CUMPLE**. Retorno bruto medio diario
    del fade EW ≈0 (t-NW −0.20) — la significancia del IC (t=−11.29) no se traduce en
    retorno promedio ni antes de costos; neto (0.30%/trade) t-NW **−11.53**. §13 queda
    CERRADO: gap-reversion es hallazgo académico, no capturable. Ejecución intradía se
    descarta definitivamente con esta infraestructura.
11. ✅ §12 régimen-vs-volatilidad — CERRADO como pista sin acción (2026-08-12, decisión
    del usuario): no se conecta TARGET_VOLATILITY, no se reducen estados HMM, no se
    espera más historia. Si se retoma, es con pre-registro nuevo y razón nueva.
12. ✅ Fase 0.6 — re-test sentimiento/fundamentales contra panel limpio + universo 50
    (2026-08-12): **NO CUMPLE para ambas variantes (0/3 ventanas cada una)**. Artefacto
    `fase06_retest_20260812_175055.txt`, pre-registro `PLAN_MEJORA_MATEMATICA §0.6.1`.
    DSR: V1 = 0.041/0.002/0.225 (W1/W2/W3), FUND = 0.121/0.004/0.330 vs baseline 0.071/
    0.028/0.173. Refutación #8/#9 CONFIRMADA con ejecución arreglada y universo 50.
    Limitación declarada: cobertura EDGAR 5/50 (10%) diluye la pata FUND. La única
    variable con cobertura completa (AAII) es más débil que baseline en 2/3 ventanas.
    Baseline post-fix universo 50: único modo de operación documentado.
13. ✅ Investigación académica/foros de trading cuántico externa (2026-08-12) — informe
    completo en `RESEARCH_EXTERNA_CRITICA.md`: TradingAgents/FinCon validan el patrón
    multi-agente LLM (nuestra variante determinista es la defensa al fallo TradeTrap);
    Barber-Odean 2000 + Taiwan 2008 + survival 44/24/15% confirman risk-mgmt-first y
    no-over-trading como únicas reglas con evidencia; trading cuántico: cerrado como
    no-relevante para 50 símbolos (híbrido NISQ solo aporta en miles de activos).
14. ✅ §15 rank IC por sub-período (2026-08-12) — motivado por el hallazgo NY Fed
    (overnight drift real, desvanecido post-2021). Momentum/RSI/ADX: sin quiebre de
    régimen, sin señal Bonferroni-robusta ni antes ni después de 2022. No es que algo
    se rompiera — nunca hubo señal robusta en ningún momento de la muestra.
15. ✅ Fix `.gitignore` (2026-08-12) — la Tanda B excluyó sin querer TODOS los
    artefactos `.txt` de diagnóstico (patrón `data/` sin anclar). Corregido a patrones
    específicos; recuperados los 4 artefactos generados mientras estuvo roto.

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
    Fechas hardcodeadas de market.py (2015-2024)  :done, c4, after c3, 1d
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
| Investigación | §13 gap-reversion: backtest con costos reales | 🟢 cerrado (2026-08-12) | — | NO CUMPLE: bruto ~0 (t-NW −0.20), neto −11.53 → §13 CERRADO (PLAN §13.1, artefacto backtest_gap_costs_20260812_173951.txt) |
| Investigación | §12 régimen-vs-volatilidad | 🟢 cerrado como pista sin acción (2026-08-12) | — | Decisión del usuario: sin TARGET_VOLATILITY, sin reducir HMM, sin esperar historia. Se retoma solo con pre-registro y razón nueva |
| Investigación | Fase 0.6 — re-test sentimiento/fundamentales | 🟢 cerrado (2026-08-12) | — | NO CUMPLE 0/3 ambas variantes (artefacto fase06_retest_20260812_175055.txt): V1 DSR 0.041/0.002/0.225, FUND 0.121/0.004/0.330 vs base 0.071/0.028/0.173 → refutación #8/#9 confirmada con vara arreglada; baseline universo 50 = único modo operativo |
| Investigación | Investigación académica/foros de trading cuántico | 🔴 pendiente, recién detectado | — | Buscar afuera: papers + foros sobre gobernanza multi-agente LLM, risk-mgmt-first para operadores chicos, crítica externa al enfoque |
| Código P0 | Contrato GovernancePanel ↔ backend | 🟢 cerrado (2026-08-12) | — | Frontend consume contrato real (`triad.{bull,bear,contrarian}.score`, `controller.approved`, `judge.verdict|status`); 5 tests de regresión en `test_governance_contract.py` |
| Código P0 | `except:` desnudo + 200 OK con error en body | 🟢 cerrado (2026-08-12) | — | `market.py`/`live.py` ahora levantan HTTPException 500; `except:` acotado a (AttributeError, TypeError, ValueError); 0 patrones restantes en routers |
| Código P0 | Auth mínima global + `SECRET_KEY` que falla si no está seteado | 🟢 cerrado (2026-08-12) | — | `hmac.compare_digest` en `verify_api_key`; Settings valida SECRET_KEY fuera de development (default bloqueado: `test_secret_key_default_blocked_outside_development`). Nota: 25/27 endpoints siguen abiertos POR DECISIÓN (UI pública con repo público) — solo rutas de escritura RAG tienen key; el resto es deliberado mientras la UI sea pública |
| Código P1 | Fechas hardcodeadas de `market.py` (2015-2024) | 🟢 cerrado (2026-08-12) | — | Las 4 rutas ahora usan `download_data(symbol, "2015-01-01")` sin fin fijo (mismo patrón que predict.py/governance.py) — default a hoy. 80/80 tests sin regresión |
| Código P1 | Python 3.11 (Dockerfile) vs 3.9.6 (venv real) | 🔴 sin empezar | — | Alinear una de las dos |
| Código P1 | README desactualizado (Redis, versión, endpoints) | 🔴 sin empezar | — | Reescribir o borrar lo aspiracional |
| Código P1 | Docstring Controller/Judge dice que usan LLM (no es cierto) | 🔴 sin empezar | — | Corregir comentario en `advanced_agents.py` |
| Código P2 | Tests de integración governance + 7 routers sin cobertura | 🔴 sin empezar | — | Empezar por el contrato que ya se sabe roto |
| Código P2 | `prompt_engine.py` — 659 líneas muertas con bug adentro | 🔴 sin empezar | — | Decidir: borrar o integrar de verdad |
| Código P2 | CI básico (lint + test en push) | 🔴 sin empezar | — | Repo público sin ningún check automático |
| Producto | `signal_engine.py` comentario/cita falsa sobre ADX | 🟡 spawneado | — | `task_22ea3f8d` — pendiente de que el usuario lo dispare |
| Producto | LEAN/QuantConnect | ⚪ parqueado | Sin objetivo de producto definido | No tocar hasta decidir para qué sirve concretamente |
| Producto | Conexión a broker real | 🔴 bloqueada, correctamente | Validar edge neto de costos primero (§13) | No avanzar hasta cerrar investigación |
| Seguridad | **`fortress.db` (SQLite local) nunca se respalda** | 🔴 sin empezar | — | `auto_backup.sh`/`backup.sh` excluyen `*.db` explícitamente — si falla el disco, los datos runtime (posiciones, snapshots, eventos de riesgo) no son recuperables de ningún backup. Hallazgo de memoria previa (2026-08-12, auditoría infra), no estaba en AUDITORIA_TECNICA.md |
| Seguridad | GET endpoints sin auth que disparan LLM real (costo/abuso) | 🔴 sin empezar | — | `predict/analyze/{symbol}`, `governance/analyze/{symbol}` — no sólo exponen datos, cualquiera puede gastar tu cuota/costo de NVIDIA NIM sin autenticarse |
| Código P2 | Código muerto adicional sin verificar (`ProbabilisticEngine` wrapper, `KellyPositionSizer` duplicado, `RiskParityAllocator`) | ⚪ sin verificar | — | Viene de memoria del 2026-08-08, anterior a esta investigación — re-chequear si sigue siendo cierto antes de actuar |

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
