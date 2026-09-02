# AUDITORÍA NIVEL DIOS — fortress_core
**Fecha**: 2026-09-02 · **Autor**: auditoría multi-agente (4 líneas de lectura paralela: ROADMAP+técnica, PLAN_MEJORA_MATEMATICA completo §1–§48.1, frente regime matching reciente, código backend) + verificación directa de hallazgos críticos contra el código.

**Pregunta que responde**: ¿qué separa este proyecto del estándar "nivel dios" de un shop cuantitativo serio (especificidad, sensibilidad, eficiencia, eficacia)?

---

## 1. Veredicto ejecutivo

El **aparato de medición es de percentil alto institucional** — pre-registros en docstrings, ledger Bonferroni máquina-ejecutado con anti-evasión, DSR, PBO/CSCV, Newey-West, embargo, checks de fidelidad que abortan corridas, reverts automáticos. Eso es mejor que la mayoría de la literatura empírica financiera publicada. Pero el resultado neto tras ~48 pruebas formales es **cero señales confirmadas**, y el diagnóstico correcto no es "no hay estructura en el mercado" sino: **la restricción es el diseño muestral, no la ausencia de edge**. EOD + cross-section efectiva ~6 símbolos/fecha + ventanas de 20–53 días da potencia para detectar IC≳0.3, mientras los efectos académicos reales viven en 0.02–0.08. Las únicas dos señales medidas con t>10 (gap-reversion t=−11.29, reversión intradía t≈−19) son **intradía** — exactamente donde la infraestructura no puede operar. El sistema mide donde puede, no donde está el edge.

Además, hay un desdoblamiento producto/investigación: la maquinaria estadística valida `signal_engine.py`, pero la API sirve `predictive_engine.py` (heurístico, pesos a mano, confianza sin calibrar) — el gap más grave entre código e investigación.

## 2. Lo que está a nivel dios (no romper)

1. **Disciplina de pre-registro y ledger** (`trial_registry.py`): presupuesto Bonferroni máquina-legible, estados con TTL, anti-evasión de re-tests, reconciliación git antes de escribir, fallo ruidoso ante corrupción. Sin equivalente en proyectos retail.
2. **Backtest engine honesto**: lag de ejecución 1d (bug T0.2 encontrado y arreglado), costos commission+slippage en ambos lados, Kelly fraccionado 0.25 con caps, walk-forward real del HMM y del calibrador Platt, embargo de horizon en WalkForwardValidator, DSR con skew/kurtosis reales, bootstrap de bloques seeded.
3. **Cultura de corrección auditada en línea**: 5 tandas de auto-corrección documentadas (lookahead del panel → 260/378 fechas cambiaron de régimen; IC pooled → intra-día NW; trials placebo #15/#16 detectados como SIN MEDIR; IC≠PnL ×2; PBO de proceso 0.469 admitido en contra del propio motor).
4. **Falsificación limpia**: 48+ hipótesis refutadas con artefacto citado, cero falsas promociones, FDR/BH retroactiva k=0.
5. **Operación**: launchd completo (datos, API, dashboard, pipeline 3×/día, backups sin `--delete`, disk health nacido del incidente real de los 95GB).

## 3. Brechas priorizadas hacia nivel dios

### B0 — Contabilidad del paper trading contaminada (código, crítico, verificado)
`paper_trading.py:114-119`: `reconcile_open_positions` cierra órdenes huérfanas con `pnl_r=float(row["pnl_r"] or 0.0)` — para una orden abierta `pnl_r` es NULL por diseño, así que graba **0.0 en lugar de calcular `(cp − open_fill_price)/open_fill_price`**. Contamina la métrica primaria exactamente en el caso de fills perdidos. Además `close_order` usa precio de decisión, no fill real; sin manejo de fills parciales ni rechazos.

### B1 — Motor no validado expuesto como producto (código, crítico, verificado)
`predictive_engine.py` (1.264 líneas, pesos `REGIME_WEIGHTS` fijados a mano) alimenta `/predict`, `/advisor`, `/decision`, `/opportunities` con `confidence` y probabilidades ad-hoc (`_probability_from_score`) sin calibrador ni conformal. Ningún trial lo valida. Un consumidor no puede distinguir qué motor hay detrás. El dashboard muestra VPP 0.875 con n=8 y 0.737 con n=19 como "GANANCIA_PROYECTADA" — estadísticamente vacío con n<30.

### B2 — El diseño muestral no puede confirmar nada (metodológico, la brecha de fondo)
- Potencia estructural: IC detectable ≳0.3 vs efectos reales 0.02–0.08 → la mayoría de "refutados" son **no-decididos por subpotencia** (el proyecto lo admite en §27/§48, el lenguaje "refutado" no siempre lo distingue).
- Gate DSR≥0.90→0.99 jamás cruzado por nada, incluido el baseline: infalible para descartar, casi imposible para confirmar con T=30 meses y muestras chicas.
- Las señales más robustas medidas son intradía; infraestructura EOD las filtra de antemano.

### B3 — Sesgos estructurales nunca corregidos (metodológico)
- **Supervivencia/selección**: universo 50 large-caps de HOY retroaplicado a 2019 (membresía con precios actuales). Reconocido como "limitación heredada", nunca corregido con constituyentes point-in-time.
- **Costos**: 0.15%/lado asumido inflado ~8× contaminó meses de descarte; el medido (0.019%) es piso paper.
- **Snooping ex-post medido, ex-ante no prevenido**: DSR se alimenta con n=12–28 pero el número efectivo de ensayos sobre el mismo histórico 2019–2026 es >40 (los diagnósticos exploratorios no consumen slot). No hay holdout reservado.

### B4 — Inconsistencias internas sin resolver (metodológico)
- **Dos PBO conviviendo** (0.236 INTERMEDIO vs 0.469 sustancial) con atribución no verificada experimentalmente; el veredicto formal "OVERFITTING sustancial" descansa sobre el diseño más débil (proxies + piso T post-hoc).
- Presupuesto Bonferroni citado como n=17 en secciones tempranas; el backfill contó 27.
- Pesos del motor (w_mom 0.6642) derivados de IC pooled 2019–2024 con gate; re-medición 2015–2026 sin gate da pooled MOM +0.0016 y **mediana por ticker −0.0738 (signo invertido)**. La heterogeneidad per-ticker es real (vol_ann 3.4×) y convive sin resolución con pesos globales.
- `expected_sharpe.json` (0.3838 mensual) fija el benchmark de monitoreo live derivado de una validación que **NO_CUMPLE** su propio DSR.

### B5 — Frente actual (regime matching) con evidencia que no sobrevive su propio estándar
- 3 pilotos secuenciales (NVDA → multiticker → growth3) **sin pre-registro ni corrección** sobre la misma matriz congelada — 28 comparaciones implícitas, mientras la institución exige pre-registro para todo trial. Auto-inconsistencia.
- n=10 análogos no-iid en 3 clusters (un evento 2017 domina), z-score con μ/σ full-sample (leakage), L2 sin ponderar ignora correlaciones SPY-QQQ ρ~0.9, confusor momentum idio sin controlar, replicación growth3 ya refutó la hipótesis growth/high-beta in-sample.
- Correlaciones en análogos contradictorias entre pilotos (NVDA–TSLA +0.32 vs +0.05; MSFT–KO +0.28 vs −0.65) sin reconciliar.
- El valor real de la línea es la **arquitectura de graduación en dos capas** y la cuantificación de heterogeneidad — no la señal de matching macro.

### B6 — Identificabilidad y reproducibilidad (código)
- `regime_classifier.py:51-76` `_align_states`: estados HMM no identificables entre refits trimestrales → GOLDILOCKS↔REFLATION pueden voltearse entre refits, inyectando no-estacionariedad en el gating.
- `backtest_engine.py:697`: bootstrap Monte Carlo sin seed (no reproducible; el de bloques sí lo es).
- Dataset de calibración replayado con régimen 0 fijo para todos los regímenes (`backtest_engine.py:56-62`).
- Definición congelada de señal duplicada en 3+ lugares (signal_engine, validacion_oos, pipeline_daily_signal) sin contrato compartido; checks F2/F3 solo corren en scripts, no en producción.
- 97 scripts con utilidades copiadas (load_symbol, DSR, bootstrap) en vez de importar de core → divergencia silenciosa.

### B7 — Operación sin loop cerrado
- Updater de precios caído una semana sin detectarse (2026-08-15→22).
- `drift_detector.py` M5 existe, testeado, sin consumidor; conformal recalibra por TTL (5 min), no por deriva.
- Sin reconciliación automática backtest↔paper (planificada como paso 4c); sin alertas activas (daily_notify no instalado).

## 4. FODA

| **Fortalezas** | **Debilidades** |
|---|---|
| Aparato estadístico institucional (pre-registro, ledger Bonferroni anti-evasión, DSR, PBO/CSCV, NW, embargo, fidelidad mecánica) | Potencia muestral estructuralmente insuficiente (IC detectable ≳0.3 vs efectos 0.02–0.08) |
| Backtest engine honesto (lag, costos, Kelly, walk-forward, bootstrap seeded en bloques) | Motor heurístico no validado sirviendo producción por API; contabilidad pnl_r con bug |
| 48+ refutaciones limpias, cero falsas promociones, cultura de corrección auditada | Universo con sesgo de supervivencia; snooping ex-ante sin prevenir; dos PBO sin resolver |
| Operación automatizada y resiliente (launchd, backups, disk health) | HMM sin identificabilidad entre refits; duplicación de la definición congelada |
| Documentación trazable a artefacto en cada veredicto | Sin infraestructura intradía aunque el edge medido vive ahí; sin holdout reservado |

| **Oportunidades** | **Amenazas** |
|---|---|
| Intradía vía LEAN (parqueado, recuperable con `docker pull`) — únicos t>10 del proyecto | Quemar el único histórico 2019–2026 por reiteración sin holdout |
| Universo 100–150 líquidos → potencia ×2–3 y slot #21 | Teoría de refutación-teatro: gate DSR 0.99 vuelve el proceso incapaz de confirmar nada |
| Constituyentes point-in-time del S&P (dato barato) → matar supervivencia | Coordinación multi-agente frágil (commits no hechos reportados como hechos; producción rota por sesiones paralelas) |
| Paper trading vivo 3×/día → libro de costos/slippage real acumulándose gratis | Fuente única de datos (yfinance, delay, sin intradía) |
| Heterogeneidad per-ticker medida como línea de investigación genuina (pesos jerárquicos) | Burnout del fundador (60% del pre-mortem) si el ciclo no produce algo operable |

## 5. Plan de implementación

**Fase 0 — Corrección inmediata** (sin ceremonia, 1–2 sesiones; es "construir", no veredicto):
1. Fix `paper_trading.py`: pnl_r real en reconciliación, cierre por fill real, manejo de fill parcial/rechazo. + tests.
2. Seed fija en `backtest_engine.py:697`.
3. Etiquetado honesto de la API: `/predict`-family con campo `motor: "heuristico_no_validado"` en la respuesta; eliminar o calibrar `confidence`; dashboard: umbral de n≥30 para mostrar VPP proyectado.
4. Resolución del PBO: un pre-registro único que decida entre 0.236 y 0.469 (diseño §39 o §40, no ambos) y congelar el veredicto del baseline.

**Fase 1 — Integridad del aparato** (~1 semana):
5. Contrato compartido de señal congelada (módulo único; checks F2/F3 corriendo también en el pipeline de producción).
6. Identificabilidad HMM (ordenar estados por convención fija, p.ej. por media de vol; verificar estabilidad entre refits con test).
7. Consolidación de utilidades: scripts importan de core (empieza por DSR/bootstrap/load_symbol, los 3 más copiados).
8. Ledger de exploración: los diagnósticos sin slot cuentan en un `n_exploratorio` que alimenta el n_eff del DSR — snooping ex-ante visible.

**Fase 2 — Diseño muestral** (la brecha decisiva):
9. Universo point-in-time (constituyentes históricos; dato accesible).
10. Expandir universo a 100–150 líquidos (potencia ×2–3, habilita slot #21).
11. Holdout reservado: congelar últimos ~12 meses como SAGRADO (ni un diagnóstico) + acumulación prospectiva del paper trading como OOS verdadero.
12. Graduación formal de regime matching ANTES de más pilotos: z-score rolling, features per-ticker (como dice `DISENO_REGIME_MATCHING_20260901.md`; los pilotos se desviaron del diseño), Mahalanobis, corrección por conteo real, y UN pre-registro con OOS fresco post-2026-08.

**Fase 3 — Donde está el edge**:
13. Retomar LEAN (o stack liviano intradía) para testear gap-reversion y reversión intradía con costos reales — las únicas señales con t>10 jamás medidas.
14. Loop cerrado: reconciliación automática backtest↔paper, `drift_detector` conectado al conformal, alertas activadas.
15. Libro de costos vivo: cada fill paper acumula slippage real por símbolo/tamaño → reemplaza el supuesto 0.05% con serie propia.

## 6. Recomendación fundada

Fase 0 ahora mismo (son bugs, no decisiones). **La apuesta estratégica es Fase 2**: sin potencia muestral ni holdout, cada trial futuro es ruido caro. Si hay que elegir un solo frente: universidad→universo ampliado + holdout, porque multiplica el valor de TODO lo demás. Fase 3 es la única vía a una señal operable real si el edge está intradía como la evidencia interna indica. Regime matching queda en pausa de pilotos hasta tener su pre-registro de graduación — seguir pilotando sin corrección sobre la misma matriz es exactamente el patrón que el ledger fue construido para impedir.
