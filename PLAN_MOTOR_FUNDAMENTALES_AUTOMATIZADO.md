# Plan — Motor de fundamentales automatizado (reemplazo del export manual de AAI)

Arquitectura acordada con Boris (2026-08-27). Proyecto nuevo, en paralelo a lo que
Kilo y OpenCode ya vienen haciendo — rama/worktree propia, cero archivos compartidos
hasta la integración final. Nada de esto consume presupuesto Bonferroni (es
infraestructura, no investigación de trading) ni toca `signal_engine.py`.

## Motivación

La skill `aai-screening-acciones` depende de un export manual (.xlsx) del screener de
InvestingPro — Boris es el cuello de botella obligatorio de cada corrida. Este plan
construye una fuente de datos y un motor de cálculo PROPIOS, para que el screening
corra solo, sin exportar nada nunca más.

## Principio rector — no reemplazamos InvestingPro, reconstruimos las fórmulas

Piotroski F-Score (2000), Altman Z-Score (1968) y Beneish M-Score (1999) son papers
académicos publicados — InvestingPro los CALCULA a partir de estados financieros, no
los inventó. La estrategia es: bajar los mismos estados financieros crudos de una
fuente con API legítima (nunca scraping de una plataforma paga — riesgo real de baneo
de cuenta, no solo cosmético) y calcular las mismas fórmulas con código propio,
testeado y verificado.

**Fuentes de datos elegidas** (verificadas reales 2026-08-27, no citas sin chequear):
- **Financial Modeling Prep (FMP)** — primaria. 250 llamadas/día gratis, cobertura de
  income statement / balance sheet / cash flow / price targets de analistas.
- **Finnhub** — respaldo y cruce (60 llamadas/minuto gratis, sin tope diario). Mismo
  patrón que ya usa el proyecto en `execution_costs.py`: nunca una sola fuente sin
  verificar contra otra.
- Requiere `FMP_API_KEY` y `FINNHUB_API_KEY` — variables de entorno, nunca en código
  ni en el chat. Boris las obtiene registrándose gratis en cada servicio.

## Fases

### Fase 1 — Ingesta de datos crudos

- Módulo nuevo `backend/app/core/fundamentals_ingestion.py`: cliente FMP (income
  statement, balance sheet, cash flow, profile, price target consensus) + cliente
  Finnhub como respaldo/cruce, mismo patrón de cache incremental que
  `data_ingestion.py` (con el umbral correcto esta vez — no repetir el bug de los
  7 días).
- Tests contra fixtures (nunca red real en la suite, mismo estándar del proyecto).

### Fase 2 — Reimplementar las 3 fórmulas + EV/EBIT + Fair Value propio

- Módulo `backend/app/core/fundamentals_scores.py`: Piotroski F-Score, Altman
  Z-Score, Beneish M-Score, EV/EBIT (EV = market cap + deuda total − caja), y una
  versión propia de "Fair Value Label" (bargain/undervalued/overvalued) basada en
  upside vs. consenso de analistas.
- **Test de validación obligatorio antes de dar la fase por cerrada**: correr cada
  fórmula contra un caso público conocido (ej. un Altman Z-Score ya publicado de una
  empresa real) y verificar que el número coincide — no alcanza con que "compile".

### Fase 3 — Reimplementar el motor de 3 tribunales

- El criterio de CALIDAD → SALUD FINANCIERA → PRECIO ya está documentado en texto
  plano en `~/.claude/skills/aai-screening-acciones/SKILL.md` y en el código de
  `motor_screening.py` — no es una caja negra. Reimplementar la misma lógica de
  umbrales sobre los datos propios de Fase 1+2.
- Verificación cruzada: correr ambos motores (el original de AAI sobre un export
  manual, y el nuevo sobre las mismas empresas vía API) y confirmar que clasifican
  igual antes de confiar en el nuevo.

### Fase 4 — Integración 🟢 CERRADA (2026-08-29, commit `67109a6`)

- Endpoint nuevo en el backend (solo lectura) que expone el resultado del screening
  automático: `/api/fundamentals/screen/latest`, `/screen/dashboard.html`,
  `/screen/export.xlsx`, `/screen/state`. Todos sirven artefactos de disco.
- Cron diario (`scripts/fundamentals_screen_daily.sh` + `.plist` 22:30 local),
  versionado en repo. Sigue el patrón de `data_updater.sh`.
- **Generación real de artefactos**: `fundamentals_artifacts.py` llama
  `motor.generar_excel()` y `motor.generar_dashboard()` del motor canónico
  vendorizado (`motor_canonico/scripts/motor_screening.py`, hash `84abe308...`
  byte-a-byte del skill r13). El job runner devuelve rc=3 si el render falla.
- **Tests e2e** (4 tests): corren el job completo contra fixtures FMP y verifican
  que produce `screen_<date>.json`, `dashboard_<date>.html`,
  `Screening_AAI_<date>.xlsx`. Si el job no genera el HTML, fallan en rojo.
- **Fixture de paridad estable**: `_CANON_XLSX` apunta a
  `backend/tests/fixtures/canon/market_view_export.xlsx` (no `~/Downloads`).
  Skip ruidoso con `REQUIRE_PARIDAD=1` como gate de merge. Referencia hermana en
  `test_fundamentals_ingestion.py` actualizada al mismo path.
- **`.gitignore`**: `fixtures/canon/` (1.28MB) y `cache_fundamentals_screen/`
  excluidos (artefactos regenerables).
- Verificado: 44 passed, 1 skipped. Endpoints sirven artefactos via async call.
- **Lo NO probado en vivo**: job contra FMP real (requiere API key, no está en el
  repo por diseño). Con clave ficticia FMP rechaza → rc=2 limpio.

## Aislamiento — cero colisión con Kilo/OpenCode

Rama/worktree dedicada (`feature/fundamentales-automatizado` o equivalente), archivos
nuevos exclusivamente (`fundamentals_ingestion.py`, `fundamentals_scores.py`, tests
propios) — no se toca nada de lo que Kilo (A6.3) ni OpenCode (pipeline diario) están
tocando ahora mismo. Se integra a `main` recién cuando las 4 fases estén cerradas y
verificadas, no antes.

## Gate de aprobación (vigente, sin cambios)

Mismo protocolo que el resto del proyecto (`PLAN_HANDOVER_48H.md` §1.1): preparar
completo, `.pending-merge.md`, aprobación de Claude Code antes del commit final a
`main`.

## Qué NO cambia

- No reemplaza la skill `aai-screening-acciones` — sigue existiendo para uso manual/
  otros contextos (Claude.ai, otras cuentas). Esto es una fuente adicional para
  `fortress_core` específicamente.
- No consume presupuesto Bonferroni — es infraestructura, no un trial de
  investigación.
- Ningún trial de investigación nuevo sin pre-registro (ONBOARDING.md #1) — esto no
  aplica acá porque no hay reclamo estadístico de edge, es reconstrucción de fórmulas
  públicas ya validadas académicamente.
- No se conecta a broker real ni cambia nada de la ejecución de órdenes.

## Sin fecha de cierre fija

Boris confirmó que no hay apuro — se cierra fase por fase, con verificación real
entre cada una, no se apura ninguna fase para "terminar rápido".
