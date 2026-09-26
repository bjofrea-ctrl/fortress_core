# Feature: tradingagents-c1-c3 — robustez LLM sin tocar motor

## Objective
Adoptar 3 patrones de TradingAgents en la capa muerta (GOVERNANCE_LLM_ENABLED=false) sin tocar motor validado ni gate: C1 retry/backoff, C2 PROVIDER_REGISTRY, C3 RAG as_of. Cero riesgo para gate 90 días.

## Why
C1: hoy 429 → warning + None, no distingue cuota vs respuesta rara. C2: slugs hardcodeados se descubren a las 2 AM. C3: RAG recupera lecciones sin filtro temporal → look-ahead latente si se reenciende gobernanza sobre ventana histórica. TradingAgents los resolvió bien; copiar patrón es barato y testeable.

## Scope
Solo ~/Work/fortress_core. Archivos: backend/app/core/advanced_agents.py (C1, C2), backend/app/core/knowledge_repo.py (C3), tests. No toca signal_engine, backtest_engine, pipeline, gate_window, trial_registry. Categoría: bugfix/infraestructura (permitida en gate).

## Tasks
- [ ] C1 — NvidiaNIMClient.generate(): llm_max_retries configurable, backoff exponencial con jitter, respeta Retry-After. Test 429→429→200 exige 3 intentos; max_retries=0 reproduce comportamiento actual.
- [ ] C2 — PROVIDER_REGISTRY: tabla nombre→{base_url, settings-key, structured, wire_id} en vez de parsear prefijos. Validación al importar: slug no registrado o proveedor sin key → error temprano. Test registry.
- [ ] C3 — RAGMemorySystem: record_lesson guarda resolution_date, retrieve filtra resolution_date <= as_of. Test lección 2030 no aparece en as_of 2026-01-01.
- [ ] Verificación: ruff, pytest de los 3 módulos, sin tocar gate. Commit work-unit, espejo Engram, sin push sin OK.

## Constraints
- Gate 90 días vigente hasta 2026-12-01: no agregar familia, no correr trial, no encender GOVERNANCE_LLM_ENABLED.
- PAUSE_YAHOO_MASS_DOWNLOAD sigue activa; no mass download.
- Solo lectura de TradingAgents en /tmp/TradingAgents (ya auditado), no copiar código sin atribución.

## Verification
- pytest: test_nim_client (C1), test_provider_registry (C2), test_knowledge_repo (C3)
- Gate: FC1, FC2, etc. no requieren

## Locator
- Repo-relative: odd/tasks/tradingagents-c1-c3.md
- Mirror: Engram odd/tradingagents-c1-c3/tasks
