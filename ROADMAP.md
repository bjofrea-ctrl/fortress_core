# Roadmap — fortress_core

Documento vivo que centraliza TODO lo que quedó abierto, en todas las áreas — no sólo
matemática/investigación. Existe porque el rigor que se aplicó a la validación estadística
nunca se declaró explícitamente para el resto del proyecto, y eso no puede depender de que
alguien se acuerde de pedirlo cada vez.

**Cómo se usa**: al empezar cualquier sesión de trabajo (con cualquier herramienta — Claude
Code, Cline, OpenCode), leer este documento primero. Al cerrar, actualizarlo antes de cerrar
— marcar lo que se cerró, agregar lo que apareció nuevo. Ningún ítem se da por cerrado sin
marcarlo acá, aunque se haya resuelto "de pasada" en otra conversación.

Última actualización: 2026-08-19.

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
16. ✅ §18.1 C6 (MA200 fade) — backtest con costos reales (2026-08-13) — pre-registrado
    en `PLAN_MEJORA_MATEMATICA.md §18.1`, corrido (`backtest_c6_costs.py`, artefacto
    `backtest_c6_costs_20260813_135830.txt`): **NO CUMPLE**. Panel verificado fiel a §16
    (3703 filas, Pearson IC −0.1582, Spearman −0.1129 — idénticos al artefacto de §16).
    LS (gate): bruto −0.000019/día (t-NW −0.07), NETO −0.000228/día (t-NW **−0.88**),
    Sharpe −0.27, 45.5% días positivos, 2661 días con posición. SO (info): neto −0.000758
    (t-NW −2.92). Diagnóstico: `E[sign×fwd] = +0.00017` — en 7 años alcistas dist>0 la
    mayor parte del tiempo, el fade está short casi siempre y paga el drift del mercado;
    el hallazgo vive en exceso de mercado (§18, t=−2.87), no en nivel → la mecánica LS
    cruda no lo capitaliza. §18 queda CERRADO: C6 es hallazgo académico, mismo destino
    que gap-reversion. Baseline universo 50 sigue siendo el único modo de operación
    documentado. **Tanda D completa.** Siguiente frente: Fase 1 EVT o Fase 2
    Kalman+GP-BO (decisión del usuario).
17. ✅ §18.2 C6 HEDGEADO (market-neutral por beta) — INTENTO FINAL (2026-08-13) —
    pre-registrado en `PLAN_MEJORA_MATEMATICA.md §18.2` (regla de parada del usuario:
    sin tercera variante), corrido (`backtest_c6_hedge.py`, artefacto
    `backtest_c6_hedge_20260813_154313.txt`): **NO CUMPLE → §18 CERRADO DEFINITIVO.**
    Betas pre-muestra 2015-2018 (|β| medio 1.11), check de integridad ok (n=3703,
    Pearson −0.1582, Spearman −0.1129, P(dist>0)=0.744). LS-HEDGE bruto **+0.000149/día**
    (t-NW +1.01 — el hedge neutralizó el drift, pasó de −0.000019 crudo), NETO
    −0.000292 (t-NW −1.97). La señal existe en exceso de mercado pero es más chica
    que sus propios costos (+0.30% bruto/trade vs 0.63% hedged): real, no tradeable.
    C6 = hallazgo académico, línea MA200 CERRADA. Baseline universo 50 = único modo
    de operación documentado. Tanda D + línea C6 completas.
18. ✅ Fase 1 EVT — diagnóstico de colas universo 50 (2026-08-13) — pre-registrado en
    `PLAN_MEJORA_MATEMATICA.md §19`, corrido (`diagnose_evt_tails.py`, artefacto
    `evt_tails_20260813_155237.txt`): **PASA el gate**. GPD/POT sobre retornos
    estandarizados EWMA (λ=0.94; arch/GARCH no instalado — limitación declarada):
    ξ>0 significativo en 28/50 (56%), excesos bajo VaR-normal ≥1.5% en 47/50 (94%,
    promedio 1.95% vs 1% esperado); VaR99-GPD ≈ 3.0 z vs 2.326 normal (ratio medio
    1.26 — la regla gaussiana subestima el VaR 99% en ~26%); GPD calibra (excesos
    reales 0.98% ≈ 1%). Implicación: la regla de stop 2×ATR está sistemáticamente
    subdimensionada contra el riesgo de cola → **siguiente paso: pre-registro del
    trial de stops EVT del motor** (mismas ventanas W1-W3, DSR≥0.90, n_trials+1;
    **debe ser walk-forward** — ξ/VaR-GPD re-estimado periódicamente, no el ajuste
    fijo de muestra completa de §19 aplicado retroactivo a W1, eso sería lookahead
    del mismo tipo que §3.1. Confirmar el n_trials exacto contra el historial de
    artefactos antes de fijarlo — no asumir el número).
19. ⚪ Diferido — kernel methods/SVM, ML no lineal, datos alternativos/NLP de
    sentimiento (2026-08-14, decisión del usuario). Investigación externa (Perplexity,
    verificada parcialmente — mezcla contenido sólido con al menos una cifra de
    rendimiento sin fuente confiable, mismo patrón que medallion-pub) mapeó el stack
    probabilístico de fondos comparables (Renaissance/D.E. Shaw/Two Sigma/AQR/
    Citadel/Bridgewater). Cruzado contra lo ya hecho acá: HMM/régimen, PCA/RMT, EVT,
    factores momentum/fundamentales — todo YA probado con nuestro rigor, mayoría
    refutada. Lo que queda sin tocar (kernel/SVM/ML no lineal, alt-data/NLP) no se
    persigue ahora — alto riesgo de sobreajuste con n=50 símbolos/kernel-ML, y
    alt-data es la inversión de infraestructura ya deprioritizada ("no escalar en
    serio"). Se retoma **sólo cuando el plan actual esté agotado**, asumiendo que en
    ese momento el costo (datos/infra) sea aceptable — decisión explícitamente
    pospuesta, no descartada.
20. ⚪ Diferido — indicadores sobre velas SEMANALES re-muestreadas (2026-08-13,
    pedido del usuario, para más adelante). **Distinto de §21/§21.1**: esos
    variaron el horizonte del retorno futuro (5d/10d/60d/125d) sobre indicadores
    calculados con barras DIARIAS. Esto es otra pregunta: re-muestrear OHLC a
    semanal (`resample('W-FRI')`) y recalcular momentum/RSI/ADX/Bollinger/Donchian
    sobre ESA serie semanal — cambia el ruido del indicador mismo, no sólo la
    ventana de evaluación. Mismo protocolo si se retoma: rank IC intra-semana con
    Newey-West, pre-registrado, Bonferroni por cantidad de factores testeados.
    Minutos/horas: no viable — el cache es sólo barras diarias (verificado,
    `AAPL.parquet` espaciado modal 1 día calendario/hábil), y datos intradía ya se
    descartaron con gap-reversion (§13).
21. 🟢 **Trial #15 EVT — CERRADO como inválido por diseño, causa raíz confirmada
    en código (2026-08-15)** — el re-run válido (post-fix EWMA, `trial15_evt_stops_20260814_195828.txt`)
    reportó NO CUMPLE (0/3 ventanas), y tanto OpenCode como Command Code lo verificaron
    contra n por ventana/win_rate del parquet y lo cerraron. **Ese veredicto no es
    utilizable**: no es que el sizing EVT pierda contra el baseline, es que el trial
    **nunca pudo medir la diferencia**.
    **CAUSA RAÍZ (Claude Code, 2026-08-15, confirmada leyendo `backtest_engine.py:439-443`
    y `trial_evt_stops.py`, no solo hipótesis)**: `compute_position_size` recibe SIEMPRE
    `win_prob` y `payoff_ratio` no-`None` desde el motor real → toma la rama Kelly →
    `return int(min(kelly_shares, shares_by_risk, max_shares))`. `kelly_shares` **no
    depende de `stop_distance`** (solo de win_prob/payoff_ratio/price/equity), y es el
    mínimo de los tres en la enorme mayoría de los trades — confirmado numéricamente:
    ejemplo AMD 2019-01-07, shares=60 real vs 2×ATR baseline=$2.84 (13.8% precio) vs
    stop_distance EVT implícito ≈$6.20 (30% precio) — ninguno de los dos coincide con
    lo que shares=60 produciría vía `shares_by_risk`; sí coincide con un `kelly_shares`
    de fracción ~4.9%. Confirmado también que NO es el tope de posición (`max_shares`):
    solo 15.3% de los 281 trades coinciden exacto con el tope, 24.2% con margen ±1 —
    la mayoría de los shares están MUY por debajo del tope, consistente con Kelly
    dominando, no el cap. Y `EVTRiskManager.check_all_stops` nunca se sobreescribe
    (llama a `super()` sin cambios, `trial_evt_stops.py:140-142`) — el cambio EVT SOLO
    podía tocar tamaño de posición, nunca cuándo entra o sale un trade, y ni siquiera
    eso llegó a expresarse por el `min()` con Kelly.
    **Confirmación independiente (Claude Code, 2026-08-15, reconstrucción completa
    de los 281 trades del parquet)**: (a) el término EVT `var_mult×σ_EWMA_día`
    (mediana 0.052, p90 0.091, max 0.266) **NUNCA superó** el floor
    `price×position_stop` ni el `2×ATR` (`evt_term > floor` = 0, `evt_term > 2×ATR` = 0
    sobre 281/281); (b) `max_shares ≤ shares_by_risk` en 281/281 (por álgebra:
    `0.5×E/P > 0.1×E/P` siempre dado el piso 0.03) → `shares_by_risk`, donde vive la
    variable EVT, nunca es binding. El 0/3 ventanas con métricas idénticas a 4
    decimales era la firma de esto: el sistema midiéndose a sí mismo.
    **Ningún n_trials se gasta por esto** — no es un trial nuevo, es la constatación de
    que el trial #15 tal como está pre-registrado en §20 no puede responder la pregunta
    que se hizo. Si se quiere retomar la línea EVT-stops, hace falta un pre-registro
    NUEVO que aísle `shares_by_risk` del `min()` con Kelly (por ejemplo corriendo con
    `fractional_kelly=0` para esta comparación específica) — decisión del usuario, no
    de un agente. **M0 queda CERRADO como "trial inválido, no concluyente"** — distinto
    de "EVT-stops no sirve". Sin bloquear nada más del plan de mecánica.
22. ✅ M1/M1b — auditoría de horizonte COMPLETA (2026-08-13, `PLAN_MEJORA_MATEMATICA.md
    §21/§21.1`): 5d/10d/60d/125d, ninguno significativo bajo Bonferroni-12. Los
    rechazos de señal se refuerzan en los 5 horizontes probados (5d-125d).
23. ✅ **M2 — contrafáctico de las 41 salidas por REGIME_STOP_HIT CERRADO (2026-08-14)**
    — pre-registrado en `AUDITORIA_MECANICA.md` (Fase M2), corrido
    (`diagnose_regime_stop_contrafactual.py`, artefacto
    `regime_stop_contrafactual_20260814_173001.txt`): **el stop está haciendo su
    trabajo**. Puerta de fidelidad: 152 posiciones naturales reproducen el parquet
    exacto. Solo 16/41 (39%) se habrían recuperado; delta total ≈ $0 (real
    −$5,867.12 vs cf −$5,867.15); 13/41 habrían llegado a ABSOLUTE_CEILING con
    pérdidas mucho peores. Per criterio pre-registrado (<50% recuperadas) → M3 NO
    se dispara (sin hipótesis que gaste un slot de n_trials); M4 tampoco. Con esto,
    del plan de mecánica queda solo M0 (el trial EVT en curso).
24. ✅ **M6 — Ledger de trials HECHO (2026-08-14, Command Code)** — `app/core/trial_registry.py`
    (lectura/escritura de `data/trial_registry.json`, `register_trial`/`trials_by_family`/
    `consumed_budget`/`current_threshold` con corrección Bonferroni), backfill de 29
    entradas desde `PLAN_MEJORA_MATEMATICA.md` + `RESUMEN_VALIDACION_VARIABLES.md`
    (`scripts/backfill_trial_registry.py`), auditoría `scripts/audit_trial_budget.py`
    (avisa si un trial nuevo excedería el umbral declarado), 15 tests. **HALLAZGO
    (contrato M6 — el desacuerdo ES el resultado)**: el backfill cuenta **27
    n_trials_consumidos** vs el **n_trials=17** citado en §6/§0.6.1/§20 (diferencia
    +10). El backfill NO se ajustó para cuadrar: 17 = los 13 trials #1-#13 contados
    en §6 + 4 sin slot (fix #10, re-tests Fase 0.6 #8/#9); 27 = los 13 + 8
    hipótesis de motor adicionales registradas (trial #14 basket, trial #15 EVT en
    curso, diagnóstico sectorial, re-evaluación #11.1, gap, sub-períodos, MA200,
    Donchian). El número 17 subestima el presupuesto real. Artefacto:
    `data/cache/trial_registry_backfill_audit_20260814_202751.txt`.

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
| Investigación | Investigación académica/foros de trading cuántico | 🟢 cerrado (2026-08-12) | — | Informe completo en `RESEARCH_EXTERNA_CRITICA.md` (verificado): TradingAgents/FinCon validan el patrón multi-agente LLM; Barber-Odean 2000 + Taiwan 2008 + survival 44/24/15% confirman risk-mgmt-first; trading cuántico cerrado como no-relevante para 50 símbolos |
| Código P0 | Contrato GovernancePanel ↔ backend | 🟢 cerrado (2026-08-12) | — | Frontend consume contrato real (`triad.{bull,bear,contrarian}.score`, `controller.approved`, `judge.verdict|status`); 5 tests de regresión en `test_governance_contract.py` |
| Código P0 | `except:` desnudo + 200 OK con error en body | 🟢 cerrado (2026-08-12) | — | `market.py`/`live.py` ahora levantan HTTPException 500; `except:` acotado a (AttributeError, TypeError, ValueError); 0 patrones restantes en routers |
| Código P0 | Auth mínima global + `SECRET_KEY` que falla si no está seteado | 🟢 cerrado (2026-08-12) | — | `hmac.compare_digest` en `verify_api_key`; Settings valida SECRET_KEY fuera de development (default bloqueado: `test_secret_key_default_blocked_outside_development`). Nota: 25/27 endpoints siguen abiertos POR DECISIÓN (UI pública con repo público) — solo rutas de escritura RAG tienen key; el resto es deliberado mientras la UI sea pública |
| Código P1 | Fechas hardcodeadas de `market.py` (2015-2024) | 🟢 cerrado (2026-08-12) | — | Las 4 rutas ahora usan `download_data(symbol, "2015-01-01")` sin fin fijo (mismo patrón que predict.py/governance.py) — default a hoy. 80/80 tests sin regresión |
| Código P1 | Python 3.11 (Dockerfile) vs 3.9.6 (venv real) | 🟢 cerrado (2026-08-12, commit `a56e516`) | — | Dockerfile fijado a `python:3.9-slim` — alineado con el venv real |
| Código P1 | README desactualizado (Redis, versión, endpoints) | 🟢 cerrado (2026-08-12, commit `a56e516`) | — | README sin Redis, versión 3.9, tabla con los 27 endpoints reales |
| Código P1 | Docstring Controller/Judge dice que usan LLM (no es cierto) | 🟢 cerrado (2026-08-12, commit `a56e516`) | — | Docstrings corregidos a "lógica determinista — no usa LLM" en `advanced_agents.py` |
| Código P2 | Tests de integración governance + 7 routers sin cobertura | 🟢 cerrado (2026-08-12, commit `6ae0770`) | — | Tests de integración para 6 de los 7 routers (test_backtest_api, test_market_api, test_live_api, test_predict_api, test_risk_api, test_system_api); governance y opportunities ya tenían |
| Código P2 | `prompt_engine.py` — 659 líneas muertas con bug adentro | 🟢 cerrado (2026-08-12, commit `6ae0770`) | — | Eliminado; `HardinessChecker` movido a `app/core/hardiness.py` (7 tests); `test_prompt_engine.py` eliminado |
| Código P2 | CI básico (lint + test en push) | 🟢 cerrado (2026-08-12, commit `6ae0770`) | — | `.github/workflows/ci.yml`: jobs lint (ruff) y test (pytest) en cada push/PR, Python 3.9 |
| Frontend | Dashboard completo rediseñado (estilo institucional) | 🟢 cerrado (2026-08-17) | — | Nuevo `Layout.tsx` con paneles colapsables, Header unificado, fix contrato GovernancePanel (triad/controller/judge/professor), URLs hardcodeadas eliminadas en SystemStatus/RiskPanel, index.css modernizado. Build OK (TS sin errores), 242 tests backend pass |
| Frontend | Dashboard institucional consolidado — advisor API + mesas por vista + Exit Thesis Monitor (Kilo Code) | 🟢 cerrado (2026-08-17) | Verificación visual del navegador HECHA (2026-08-19) — ver nota final | Consolidación del rebuild de Claude Code + plan Kilo sobre `frontend/` (sin rama aparte). Backend: router `/api/advisor` (universe/symbol/theses/evidence, solo lectura, reutiliza `_compute_ticket` de decision.py — cero reprogramación del motor) + 21 tests. Frontend: 4 vistas con lazy-loading (Mesa/Detalle/Portfolio/Gobernanza), tokens TradingView exactos (#131722/#1e222d/#26a69a/#ef5350), chart Lightweight Charts con EMA50/200 + zonas mecánicas (entry/stop 2×ATR/target 4×ATR) + widget TradingView secundario con degradación graceful, etiquetas proyectadas §29 pre-registradas (mapeo verificado contra `baseline_clean_20260811_150643_trades.parquet`: ≥0.70→VPP 87.5% n=8; ≥0.65→73.7% n=19; <0.45→RIESGOSA_SIN_APOYO sin afirmar pérdida), Exit Thesis Monitor (`decision_theses.json` atómico: se sale cuando se pierde la tesis), Evidence Footer vivo desde trial_registry, badge de honestidad global, chip de staleness (>2 ruedas), API URL vía VITE_API_URL. Code splitting: bundle principal 624 kB → 152 kB. Acceptance: 263 tests backend, ruff limpio en archivos nuevos, tsc+build OK, endpoints crudos verificados en vivo (universe 44 símbolos régimen 2, CVX detalle 400 barras EMAs consistentes con gates, AAPL fundamentals EDGAR, theses, evidence tolerante a umbral str). Campo costo/trade RESUELTO por la Tarea E (2026-08-19) — ver fila propia. **UNIVERSE 44 EXPLICADO (2026-08-19, Tarea F)**: el endpoint iteraba `opportunities.SYMBOLS`, lista curada HARDCODED de 44 (distinta del universo 50 de investigación) — **NO era bug**, era duplicación manual. **FIX APLICADO (2026-08-19, decisión de Boris "los 50")**: módulo canónico `app/api/routes/opportunities_universe.py` deriva SYMBOLS desde `scripts/fetch_universe_data.NEW_UNIVERSE` (fuente única) + 7 base = **50** con dedup y fallback; opportunities/decision/advisor conectados vía re-exportación. Verificado en vivo: `/api/advisor/universe` → **50 states** (AMD/CMCSA/DIS/INTU/META/PFE/QCOM/SPGI/TSLA presentes, ABT/GS/WFC fuera), régimen STAGFLATION sin cambio, suite 271 passed. **VERIFICACIÓN VISUAL DEL NAVEGADOR (2026-08-19, Tarea G, OpenCode)**: stack levantado (uvicorn :8000 + vite :3000) y 4 vistas inspeccionadas vía Chrome headless + CDP (DOM renderizado post-fetch + logs de consola). Mesa/Portfolio/Gobernanza cargan sin errores de consola; Detalle renderiza chart Lightweight Charts (canvas, EMA50/200) + Zonas mecánicas + M2 + Plan de salida 4 mecanismos (partial tp/trailing/technical/regime stop) con datos reales; CostField visible en todas las vistas con datos reales: `COSTO REAL/LADO: 0.017% · n=156 · q1: 0.019% · q10: 0.013% · q50: 0.004%`; badge honestidad + chip staleness presentes. **HALLAZGO (no bloqueante, backend — NO arreglado en esta tarea)**: `/api/advisor/AAPL` tarda ~80s (vs MSFT 2.8s) porque `_compute_ticket` intenta descargar de Yahoo símbolos fantasma (`$BASELINE_CLEAN_..._EVENTS`, `$COT_2019`, etc.) que dan timeout de red ~1s c/u — es costo de arranque/cache fría del endpoint de detalle, no del frontend; el chart aparece al completar. Propuesta de fix (no aplicada): cachear/saltar esos símbolos en la descarga de precios del ticket. Ver SESSION_LOG. **TAREA F (2026-08-19, Kilo Code) — DIAGNÓSTICO universe 44 vs 50**: NO es bug. El endpoint usa `opportunities.SYMBOLS` (44, lista curada hardcoded), NO el "universo 50" (BASE_SYMBOLS 7 + NEW_UNIVERSE 43 de `fetch_universe_data.py`/`measure_execution_costs.py`) que usan los trials de investigación. Verificado empíricamente: los 44 de SYMBOLS pasan el filtro `len(df)>200` de `load_universe` (0 descartados) → el endpoint devuelve los 44 definidos. Diferencia de listas: en 50-no-44 = [AMD, CMCSA, DIS, INTU, META, PFE, QCOM, SPGI, TSLA]; en 44-no-50 = [ABT, GS, WFC]. Artefacto: `data/cache/diagnostico_universo_20260819_174613.txt`. Acción (no aplicada, es diagnóstico): si se quiere cubrir los 50, cambiar `opportunities.SYMBOLS` al universo 50; si no, documentar 44 como universo de decisión intencional. |
| Producto | `signal_engine.py` comentario/cita falsa sobre ADX | 🟢 cerrado (2026-08-16, commit `243e19f`) | — | Comentarios corregidos en `signal_engine.py` (líneas 16-25 y 51-59): afirmaban "adx mostró IC negativo" cuando el artefacto corregido (§0.5a, `rr2_intraday_20260811_150741.txt`) mide **IC +0.0679, t=+2.31 nominal — POSITIVO, único factor con señal nominal**, marginal no robusto bajo Bonferroni-4 (≈2.5). La cita repetía la auditoría pooled vieja (metodología descartada). Verificado: suite completa 216 passed |
| Producto | LEAN/QuantConnect | ⚪ parqueado, uso futuro pretendido (2026-08-14) | Datos ampliados si crece el universo, o ejecución real si hay señal validada | Imagen Docker (42.5GB) borrada del disco local por espacio — recuperable gratis con `docker pull` cuando se retome. No tocar hasta que aparezca uno de los dos disparadores |
| Producto | Conexión a broker real | 🔴 bloqueada, correctamente | Validar edge neto de costos primero (§13) | No avanzar hasta cerrar investigación. **Insumo listo para cuando se desbloquee** (§33.1, PLAN_MEJORA_MATEMATICA.md, evidencia JoF 2025 verificada): ranking de brokers por calidad de ejecución medida — TD Ameritrade (7.2bps RT) y Fidelity (19.7bps) en el extremo bueno; IBKR Lite/Pro (44-46bps) en el extremo malo; Alpaca/Schwab no estudiados directamente, Schwab con indicios de estar en el grupo bueno. No repetir esta investigación cuando llegue el momento |
| Seguridad | **`fortress.db` (SQLite local) nunca se respalda** | 🟢 cerrado (2026-08-12, commit `217eb51`) | — | `backup_db()` en `auto_backup.sh` + paso 6.5 en `backup.sh` (`sqlite3 .backup` → `/Volumes/EMPRESA/fortress_core_backups/db/`, retención 20). Verificado: snapshots cada ~10 min en disco externo, launchd instalado |
| Seguridad | GET endpoints sin auth que disparan LLM real (costo/abuso) | 🟢 mitigado (2026-08-12, commit `217eb51`) | — | Rate limit en memoria (10 llamadas/60s por IP) aplicado vía `RateLimitDependency` en `routes/predict.py` y `routes/governance.py`. Sin auth completa por decisión (UI pública); el rate limit acota el abuso de costo. Test: `test_rate_limit.py` |
| Código P2 | Código muerto adicional (`ProbabilisticEngine` wrapper, `KellyPositionSizer`, `RiskParityAllocator`) | 🟢 **ELIMINADO (2026-08-15, Claude Code)** | — | Verificado por M8 (Command Code, solo documental), decisión y ejecución de Claude Code. `KellyPositionSizer` y `ProbabilisticEngine` borrados de `probabilistic_engine.py` (quedan las 6 clases vivas: ProbabilityCalibrator, SignalQualityMetrics, BayesianOnlineUpdater, FatTailMonteCarlo, CopulaRiskAnalyzer, WalkForwardValidator — secciones renumeradas 1-6). `risk_parity.py` eliminado completo (archivo entero muerto). Los 2 smoke scripts NO se borraron enteros (a diferencia de `prompt_engine.py` en Tanda C) — mezclaban código vivo y muerto: se recortó solo `test_kelly`/`test_integrated` de `test_probabilistic.py` y `test_risk_parity` de `test_system.py`, conservando la cobertura smoke de lo que sigue vivo. Verificado grep repo-wide (0 referencias restantes salvo el propio docstring explicativo), ambos scripts corridos end-to-end tras el recorte, suite completa 206 passed, ruff limpio. |
| Instrumento | M1 — Etiquetado por barreras | 🟢 hecho (2026-08-14) | — | `app/core/barrier_labeling.py`, replica las 4 barreras reales de `adaptive_risk.py` en orden de prioridad; 17 tests de fidelidad (no cobertura). Ver `DISENO_INSTRUMENTO.md` |
| Instrumento | M2 — Instrumento conforme (abstención calibrada) | 🟢 hecho (2026-08-15) | — | `app/core/conformal.py`, Split Conformal Prediction, 16 tests (cobertura empírica ≈nominal verificada). Métrica primaria `vpp_bajo_abstencion`, no Sharpe |
| Instrumento | M3 — Compuerta de régimen | 🟢 hecho (2026-08-15) | — | `app/core/regime_gate.py`, walk-forward con assert anti-lookahead, 8 tests. Infraestructura lista; el TRIAL que pruebe macro IC +0.198 GOLDILOCKS/−0.173 DEFLATION como compuerta sigue sin pre-registrar — decisión del usuario |
| Instrumento | M4 — Costos medidos (Alpaca paper) | 🟢 cerrada la medición viva qty=1 (2026-08-18) | — | `app/core/execution_costs.py` (15 tests), runner corrió y completó tras 3 fixes del cliente Alpaca: (1) el último trade se pide a `data.alpaca.markets/v2/stocks/{sym}/trades/latest` — el viejo endpoint `paper-api.../v2/last/trade/` daba 404 (el crash de 2026-08-18); (2) las órdenes paper no vuelven con fill en la respuesta (nacen `pending_new`) → polling hasta filled con deadline 30s; (3) normalización de símbolos `BRK-B`→`BRK.B` (la API de datos rechaza el guion con 400). **Resultado medido**: 120 órdenes paper (60 buy + 60 sell, los 50 símbolos del universo), `cost_per_side_medido = 0.000189` (≈0.019%), slippage p50=0.000122, p95=0.000519, comisión=0 (paper sin comisión). Artefacto: `data/cache/measure_execution_costs_20260818_134338.txt` + DB `data/cache/execution_costs.db`. **CAVEAT registrado**: es costo de ejecución PAPER — fills instantáneos a último trade sin comisión; la ejecución live real tendrá más slippage y comisión ≠0. Útil como piso inferior medido, no como número final. **COST_PER_SIDE ACTUALIZADO (2026-08-19, §33)**: de 0.0015 asumido a **0.0005** (0.05%/lado) por decisión del usuario — punto medio conservador ~2.6× sobre el piso paper medido; suite 271 passed. **Tarea E (2026-08-19)**: campo de costo real construido en el dashboard sobre esta medición (`/api/costs/current`, solo lectura) — ver fila Tarea E |
| Instrumento | Tarea D — Curva de costo por tamaño qty=10/50 (Ronda 2026-08-19, Kilo Code + OpenCode) | 🟢 cerrada (2026-08-19) | — | Código: `backend/scripts/measure_execution_costs.py` (parametrizado `--qty`) + `execution_costs.py`, 21 tests costs (incl. 6 de Tarea E). **Pre-registro + resultado: PLAN_MEJORA_MATEMATICA §30**. Bloqueo real diagnosticado: el 403 NO era permisos — era `insufficient buying power` (la corrida qty=10 de la mañana entró en 18 símbolos, $81k, cash −$56k, BP 0). Se liquidaron los residuos (paper) → BP $100k y se corrió la medición completa (mercado abierto 12:13–12:14 ET): qty=10 (7 BASE_SYMBOLS buy+sell) y qty=50 (SPY+QQQ buy+sell; AAPL 50 falló por BP → fallback previsto en Enmienda 1). **Curva real (156 órdenes, fórmula contrato M4, size=1 verificado idéntico al artefacto 18/08)**: qty=1 p50 0.000122/p95 0.000519 (n=120); qty=10 p50 0.000116/p95 0.000417 (n=32); qty=50 p50 0.000029/p95 0.000098 (n=4). **VEREDICTO: curva plana/decreciente — impacto de mercado NO medible en rango 1→50; qty=1 es representativo (0.019%/lado)**. `COST_PER_SIDE` actualizado a **0.0005** (2026-08-19, §33, decisión del usuario) — ver fila M4. Endpoint `/api/costs/current` ya expone la curva (sizes 1/10/50) sin cambios de contrato |
| Instrumento | M5 — Detector de deriva | 🟢 hecho (2026-08-15) | — | `app/core/drift_detector.py`, OpenCode, KS+Bonferroni+concepto, 18 tests, abstención con n<30 |
| Instrumento | M6 — Ledger de trials | 🟢 hecho (2026-08-14) | — | `app/core/trial_registry.py` + backfill 29 entradas. Hallazgo: 27 n_trials consumidos vs 17 citados — ver `SESSION_LOG.md` |
| Instrumento | M7 — Pipeline integrado M1+M2+M3 | 🟢 hecho (2026-08-15) | — | `app/core/diagnostic_pipeline.py`, `run_diagnostic_pipeline()`, 10 tests. Instrumento diagnóstico completo (M1-M8) cerrado. Falta el TRIAL pre-registrado que lo use para afirmar algo — decisión del usuario |
| Investigación | Trial #15 EVT — stops EVT walk-forward (M0) | 🟢 cerrado (2026-08-15) | — | NO CUMPLE 0/3 (DSR 0.0649/0.0253/0.1602, artefacto trial15_evt_stops_20260814_195828.txt). Fase 1 EVT cerrada: §19 diagnóstico PASA + §20 trial NO CUMPLE |
| Investigación | §22 Lead-lag entre símbolos (Tarea C, Command Code) | 🟢 cerrado (2026-08-15) | — | NO CUMPLE: 10 pares × 5 lags, ningún par con ≥2 lags consecutivos SIG(+) bajo Bonferroni-50 (|t|>3.48). Hipótesis de lead-lag refutada con la vara más estricta. Artefacto lead_lag_20260816_090220.txt. Registrado en ledger (signal_diagnosis) |
| Investigación | §23 Triple Barrier como target (Tarea A, Cline) | 🟢 cerrado (2026-08-16) | — | NO CUMPLE: re-test de 3 factores refutados (momentum/rsi/adx) contra el label de barrera M1 (en vez de fwd_return_20d), Bonferroni-9 (|t|>2.77). Ningún cruce con signo esperado; máx |t| momentum TOTAL −2.48 (signo −). "Generador vacío" confirmado también contra el target binario que el motor persigue. Artefacto retest_triple_barrier_20260816_091649.txt. Ledger signal_diagnosis n=1 |
| Investigación | §28 Test justo doble — rank IC contra retorno RELATIVO + AAII como timing de fecha (Kilo Code) | 🟢 cerrado — NO CUMPLE (2026-08-17) | — | Motivación del usuario: "es más fácil descartar que aprobar — medir bien, no con la vara fácil". Dos mediciones que nunca se habían hecho: (A) rank IC momentum/rsi/adx vs `fwd_rel = fwd_return_20d − SPY_fwd_20d` (el confusor §6.2 resuelto): 0/3 todos, t casi idénticos a los absolutos → la hipótesis "parecía débil por medir absoluto" REFUTADA con el test correcto; (B) AAII como timing de fecha (constante por fecha, verificado nunique=1 — los tests anteriores lo medían donde no podía variar): contrarian signo −1, 0/3 (W2 t=+2.94 con signo POSITIVO, no re-signable). Bonferroni-12 \|t\|>2.86 pre-registrado, fidelidad §0.5a exacta. RESUMEN §5 ítem cross-sectional: PROPUESTA → PROBADO Y REFUTADO. Artefacto `trial_xsec_relative_20260817_184355.txt`. Ledger signal_diagnosis: 17→18, umbral 0.994737 |
| Investigación | Tarea B PASO 1 — pipeline FinBERT earnings (OpenCode) | 🟢 hecho (2026-08-16) | — | `backend/app/core/earnings_sentiment.py` (store SQLite dedup por accession + fetch SEC EDGAR 8-K 2.02 + FinBERT ProsusAI/finbert, score=prob_pos−prob_neg ponderado por longitud), CLI `scripts/accumulate_earnings_sentiment.py`, 25 tests → suite 241 passed, ruff limpio. Acumulación completa universo 50: 48/48 símbolos, 369 filings, 0 errores (`earnings_sentiment_run_20260817_120713.txt`) |
| Investigación | Tarea B PASO 2 — trial sentimiento earnings (§27, Kilo Code) | 🟢 cerrado — NO CUMPLE (2026-08-17) | — | Contrato de datos (≥8 trimestres × ≥30 símbolos) desbloqueado y verificado. Event study pre-registrado en §27: pendiente HAC rel(SPY)~score por ventana E1/E2/E3, Bonferroni-9 |t|>2.77 signo + → **0/3** (t +0.38/−0.85/−0.08; spearman +0.05/−0.11/+0.03; signo inconsistente). El tono del comunicado 8-K 2.02 no predice retorno relativo a 20 ruedas. Línea cerrada con la evidencia EDGAR-proxy + 2 años + universo 50; acumulación incremental se conserva (no se borra). Artefacto `trial_finbert_eventstudy_20260817_163512.txt`. Ledger signal_diagnosis: 16→17, umbral 0.99444 |
| Investigación | Trial #16 — abstención calibrada M2 contra baseline real (pre-registro §24) | 🟢 cerrado como trial inválido, no concluyente (2026-08-17) | — | Corrido (`trial_m2_abstencion.py`, artefacto trial16_m2_abstencion_20260817_100548.txt): VEREDICTO FORMAL NO_CUMPLE pero **TAUTOLÓGICO** — abstención 100% en ambas ventanas (n_operados=0). HALLAZGO ESTRUCTURAL DE M2: (1) el ancho del intervalo NO depende del score (residuos absolutos + regresión lineal → ancho constante 2q → abstiene todo o nada, incapaz de abstención diferencial); (2) el default `max_interval_width=2×median` es SIEMPRE < 2×cuantil(91.5%) → 100% de abstención garantizada por construcción (reproducción mínima: 28/28). Cobertura empírica en rango (0.84/0.89) — el instrumento está bien calibrado y aun así nunca opera con su default. Los 16 tests no lo detectaron (fijan max_interval_width explícito). Hipótesis SIN MEDIR, no refutada. Ledger motor_signal: 8→9 consumidos. RESUELTO EN CADENA por el #17 (§24.1) |
| Investigación | Trial #17 — re-trial abstención M2 con instrumento CORREGIDO (pre-registro §24.1) | 🟢 cerrado — hipótesis REFUTADA (medida, no tautológica) (2026-08-17) | — | M2 corregido ANTES del trial (residuos relativos + default = p90 del ancho de calibración + test de regresión de abstención diferencial; suite 242 passed). Corrido (`trial_m2_abstencion.py` → trial17_m2_abstencion_20260817_104452.txt): el fix FUNCIONA — abstención ahora discrimina (W2 4.08%, W3 15.97%, no 100%). W2 NO INTERPRETABLE por fidelidad (cobertura 0.7755 fuera de [0.80,0.97]); W3 interpretable (cobertura 0.8908): VPP_M2 0.6000 vs VPP_base 0.5798, p=0.4347 ≫ 0.025 → la abstención NO mejora significativamente el VPP. VEREDICTO NO_CUMPLE → "¿debería el motor callarse cuando no hay señal?" respondida: con win_prob y esta mecánica, NO. Línea de abstención sobre win_prob CERRADA como refutada. Ledger motor_signal: 9→10, umbral próximo 0.9909 |
| Instrumento | M2 — defecto estructural de abstención detectado (2026-08-17) | 🟢 resuelto (2026-08-17) | — | Fix aplicado y verificado por el trial #17: residuos relativos `|outcome−point|/max(|point|, floor)` (ancho escala con el score → abstención diferencial) + default = p90 de los anchos de calibración + test de regresión `test_default_produce_abstencion_diferencial_no_100_ni_0` (exige abstención 1-30% con default y abstendidos = |point| máximos). Suite 242 passed. El instrumento ahora SÍ es capaz de medir — la línea de abstención sobre win_prob quedó refutada por el #17, pero M2 corregido queda disponible para scores futuros (ej. FinBERT) |
| Investigación | §25 Tarea B — ADX walk-forward (PLAN_LARGO_PLAZO, Cline) | 🟢 cerrado (2026-08-17) | — | NO CUMPLE: rank IC intra-día adx_score vs fwd_return_20d por ventana, Bonferroni-9 (|t|>2.77) en ≥2/3 → 0/3 (W1 +0.79, W2 +1.54, W3 +1.47; TOTAL ref +2.31). Señal positiva en las 3 ventanas pero ninguna significativa en aislamiento — el t TOTAL era pooling de señal débil repartida, no robustez OOS. ADX queda marginal-no-robusto con evidencia walk-forward, CERRADO como candidato a "bueno". Test secundario (premia operativa) contexto: positiva pero no sig (máx +1.73). Artefacto trial_adx_walkforward_20260817_103916.txt. Ledger signal_diagnosis: 14→15 |
| Investigación | §26 Tarea C — Indicadores semanales (PLAN_LARGO_PLAZO, Command Code) | 🟢 cerrado (2026-08-17) | — | NO CUMPLE: rank IC intra-semana (Spearman por semana, Newey-West L=1) de momentum_20w, rsi_14w, adx_14w contra fwd_ret_1w, Bonferroni-8 (|t|>2.73) en ≥2/3 ventanas → 0/3 para los 3 indicadores. W1: mom −0.17, rsi −0.08, adx +0.31. W2: mom −0.01, rsi −0.44, adx +0.16. W3: mom +0.19, rsi +0.14, adx +0.33. Máx |t| = 0.44 (rsi W2) — nowhere near significancia. Ruido semanal no oculta señal. Artefacto weekly_indicators_20260817_105918.txt. Ledger signal_diagnosis: 15→16 |
| Investigación | §34 — C6 (MA200 hedged) reabierto bajo costo MEDIDO (Tarea J, OpenCode) | 🟢 cerrado — NO CUMPLE (2026-08-19) | — | Reabrir por evidencia nueva de costos (§33: 0.05%/lado medido vs 0.15% asumido) fue el único motivo legítimo. Pre-registro §34 ANTES de correr; trial formal `motor_signal` (ledger 10→11). Corrido (`backtest_c6_hedge_costo_medido.py`, copia parametrizada de §18.2 con costo 0.0005; artefacto `backtest_c6_hedge_costo_medido_20260819_155509.txt`): **LS-HEDGE NETO +0.000010/día (t-NW +0.07)** — el costo 3× menor SÍ movió el neto de −0.000292 (§18.2) a +0.000010, pero la señal bruta es débil (+0.000157, t-NW +1.07) y ni siquiera el costo real la deja sobrevivir (criterio t-NW ≥ 2.0 NO se cumple). SO-HEDGE informativa: neto −0.000126 (t-NW −0.99). Check integridad: n=3710/Pearson −0.1603/Spearman −0.1148 — desviación menor vs §16 (3703/−0.1582/−0.1129) verificada como refresh de datos (data_updater 17/08), el script ORIGINAL re-corrido da idéntico → mi copia es fiel. **C6 CERRADO DEFINITIVO por segunda vez, ahora contra el costo real medido, sin ambigüedad.** NO se integra al motor. |
| Datos | Pipeline de datos automatizado (cache estaba 5 ruedas desactualizado, todo era manual) | 🟢 cerrado (2026-08-17, Kilo Code) | — | Brecha detectada en auditoría: OHLCV estancado al 8/10 (hoy 8/17) y acumulación FinBERT sin cron. Fix en dos pasos: (1) refresh manual ahora — 50/50 símbolos frescos ≥ 8/14; (2) `scripts/data_updater.sh` + `com.fortresscore.dataupdater.plist` INSTALADO en launchd (22:00 diario, tras cierre US): refresh OHLCV incremental + acumulación FinBERT incremental, log `scripts/data_updater.log`. Probado end-to-end: 50/50 precios, 48/48 símbolos, 0 filings duplicados (dedup OK), suite 242 passed |
| Frontend/Backend | Tarea E — campo de costo real en el dashboard (Ronda 2026-08-19, OpenCode) | 🟢 cerrado (2026-08-19) | — | `backend/app/api/routes/costs.py` NUEVO: `GET /api/costs/current` (solo lectura) lee `execution_costs.db` (registro canónico) y, si no existe/vacía, el artefacto `.txt` más reciente `measure_execution_costs_*` (JSON del RESUMEN); curva por tamaño (`sizes`) ya lista para qty=1/10/50 de la Tarea D. Sin medición → 200 `{"medido": false, "nota"}` — nunca inventa un número. Caveat PAPER siempre en la respuesta. Registrado en `routes/__init__.py` + `main.py`. Frontend: `CostField.tsx` (chip en Layout, visible en todas las vistas) + tipos en `client.ts` + `useExecutionCosts` en `hooks.ts`; tooltip con caveat y p50/p95/n/fecha. Verificado contra el artefacto real: endpoint devuelve `0.00018883729749502882` idéntico al `.txt` de 2026-08-18. 6 tests nuevos (`test_costs_api.py`, mock de db/txt, sin red), suite 271 passed, ruff limpio, tsc+build OK. NO se tocó `advisor.py` (commit 2f6fbeb intacto). Sin commit/push (regla de la ronda) |

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
