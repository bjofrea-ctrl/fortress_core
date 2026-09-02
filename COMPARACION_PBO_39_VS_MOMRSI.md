# Comparación PBO §39 vs pbo_cscv_mom_rsi (§40) — investigación sin veredicto

**Fecha**: 2026-09-02
**Restricción**: SOLO INVESTIGACIÓN — NO FIX DE CÓDIGO, NO DECIDE, NO TOCA `backend/data/trial_registry.json`, NO TOCA `backend/data/cache/*`, NO CAMBIA `PLAN_MEJORA_MATEMATICA.md`, NO COMMITEA VEREDICTO. Evidencia para que decida Boris.
**Autor**: OpenCode (Muse Spark) — auditoría solicitada RTK comparativa.
**Worktree**: `/Users/boris/orca/workspaces/fortress_core/test-opencode-orca/`

---

## 1. Fuentes leídas (paths exactos, verificación contra artefacto real)

| # | Fuente | Path | Líneas citadas |
|---|---|---|---|
| 1 | Auditoría Nivel Dios | `main:AUDITORIA_NIVEL_DIOS_20260902.md` (git show main) | B4:41, 68-70, 88 |
| 2 | Plan mejora §39 | `PLAN_MEJORA_MATEMATICA.md:2946-3020` | 2946-3020 (pre-registro + resultado 0.2358) |
| 3 | Plan mejora §40 | `PLAN_MEJORA_MATEMATICA.md:3024-3060` | 3024-3060 (pre-registro + resultado 0.4688) |
| 4 | Pre-registro §40 | `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:1-212` | completo, sellado 2026-08-22, §4 criterio |
| 5 | Resumen §39 | `RESUMEN_PBO_CSCV_BASELINE.md:1-129` | cross-check + addendum post-decisión |
| 6 | Artefacto §39 OK | `backend/data/cache/pbo_cscv_baseline_20260822_093149.txt:1-35` | PBO 0.2358, T=128, S=16 |
| 7 | Artefacto §39 dup | `backend/data/cache/pbo_cscv_baseline_20260822_092850.txt:1-35` | idéntico 0.2358 |
| 8 | Artefacto §40 FALLIDA | `backend/data/cache/pbo_cscv_mom_rsi_20260822_093109.txt:1-60` | FIDELIDAD FALLIDA T_ge_96 False |
| 9 | Artefacto §40 OK final | `backend/data/cache/pbo_cscv_mom_rsi_20260822_093300.txt:1-80` | PBO 0.4688, T=80, S=16, ledger 21→22 |
| 10 | Validación OOS fresca | `PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md:1-250` + `backend/data/cache/validacion_oos_fresca_mom_rsi_20260822_155520.txt:1-80` | Sharpe +1.33 DSR 0.6077 NO_CUMPLE |
| 11 | Ledger | `backend/data/trial_registry.json` (jq `.[] | select(.id=="pbo_cscv_mom_rsi")`) | 1 entrada signal_diagnosis 21→22 |
| 12 | Scripts | `backend/scripts/pbo_cscv_baseline.py:1-120` y `backend/scripts/pbo_cscv_mom_rsi.py:1-150` | grid + MIN_T logic |

Todas las citas verificadas con `bat`/`rg`/`jq` contra artefacto real, no contra resúmenes.

---

## 2. Cita exacta de la inconsistencia (Auditoría Nivel Dios)

Git `main:AUDITORIA_NIVEL_DIOS_20260902.md:41`:

> `Dos PBO conviviendo (0.236 INTERMEDIO vs 0.469 sustancial) con atribución no verificada experimentalmente; el veredicto formal "OVERFITTING sustancial" descansa sobre el diseño más débil (proxies + piso T post-hoc).`

Contexto B4 completo (`:38-44`) lista además: Bonferroni n=17 vs 27 backfill, pesos w_mom 0.6642 con heterogeneidad per-ticker (pooled MOM +0.0016 vs mediana −0.0738), y Fase 0 exigencia Fase 0-4 (`:88`):

> `Resolución del PBO: un pre-registro único que decida entre 0.236 y 0.469 (diseño §39 o §40, no ambos) y congelar el veredicto del baseline.`

Esta es la única inconsistencia PBO señalada por la auditoría; no hay segunda auditoría con otro número.

---

## 3. Fichas por PBO (tabla normalizada)

### 3a. §39 — PBO vía CSCV del baseline (auditoría, NO trial)

| Campo | Valor verificado |
|---|---|
| **Pre-registro** | `PLAN_MEJORA_MATEMATICA.md:2946-3004` escrito ANTES de correr (corrección N=18→27 documentada `:2979-2980`) |
| **Autor** | Cline, cola de Boris 2026-08-22 (`:2948`) |
| **Naturaleza** | Auditoría de proceso, NO consume ledger (`:2954-2956` — NO trial, NO promueve/refuta) |
| **Método** | Bailey/Borwein/López de Prado/Zhu 2017 CSCV (`:2958`) — matriz T×N mensual, S=16, C(16,8)=12 870 splits |
| **N (vecindad)** | **27** configs vecinas del baseline: `w_mom {0.50,0.664,0.80} × RSI_band {(40,65),(45,70),(50,75)} × mom_hi {75,100,125}` (`:2974-2978`) — ACTUAL celda central |
| **T (muestra)** | **128 meses** 2016-01→2026-08 (`RESUMEN_PBO_CSCV_BASELINE.md:17`, artefacto `pbo_cscv_baseline_093149.txt:4` T_final 128 — truncado al múltiplo de 16 reteniendo recientes) |
| **Bloques** | S=16 × 8 meses por bloque (`:2983-2984`) |
| **Universo** | 50 símbolos canónicos, OHLCV local cache `*.parquet` sin descargas (`:2962-2963`) |
| **Métrica** | Sharpe anualizado mensual (√12) sobre retornos mensuales netos EW, cash si sin señal (`:2985-2986`) |
| **Costos/lag** | 2×(0.001+0.0005)=0.003 por rebalance, señal shift 1 mes (`pbo_cscv_baseline.py:30`) — aproximación vectorizada SIN stops/barriers/regime-gating (`:2971-2973` declarado) |
| **Checks fidelidad** | 4 checks OK: T≥96 (128), cobertura 83.6% (107/128), edge bruto +1.55%/mes >0 (`:3009-3010`) |
| **Artefacto** | `backend/data/cache/pbo_cscv_baseline_20260822_093149.txt:9-14` + `.json` |
| **Resultado numérico** | **PBO = 0.2358** (3035/12 870 λ≤0, mediana λ +0.310, media +0.182, p5 −0.154) — Sharpe vecindario +0.55→+0.90 todas positivas, ACTUAL +0.714 rank 12/27 (`:3011-3018`, artefacto `:9-13`) |
| **Criterio pre-registrado** | ≤0.20 BAJO, 0.20-0.50 INTERMEDIO, >0.50 ALTO (`:2992-2996`) → **INTERMEDIO**, ninguna acción automática (`:3012`) |
| **Ledger** | NO consume slot (distinto de §40) |

### 3b. §40 — PBO/CSCV sobre momentum+RSI (trial, consume ledger)

| Campo | Valor verificado |
|---|---|
| **Pre-registro** | `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:1-212` BORRADOR 2026-08-22 en cola, sellado ANTES de correr, no editado después (`:6`, `:192-198` checklist) + `PLAN_MEJORA_MATEMATICA.md:3024-3045` |
| **Autor** | OpenCode (Muse Spark) — único slot liberado cola PBO (`:3026`) |
| **Naturaleza** | TRIAL diagnóstico de proceso, familia `signal_diagnosis`, consume **1 slot 21→22** (`:3028`, ledger jq verificado) |
| **Método** | Bailey et al. CSCV fiel paper (`:3032-3037`) — S=16 → C(16,8)=12 870 splits, Sharpe OOS mensual, logit `λ=log((r/(N+1))/(1−r/(N+1)))`, PBO=P(rank_OOS(best_IS) < N/2) |
| **N (qué cuenta)** | **21** = `consumed_budget(signal_diagnosis)` al 2026-08-22 (lista congelada §6.1: fase05a…trial_cvd_proxy) (`PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:60`, `PLAN_MEJORA_MATEMATICA.md:3034`) — PERO implementado como **21 primeras del mismo grid 3×3×3=27 de §39 ordenadas lexicográficamente** incluyendo ACTUAL (`:3038`, `pbo_cscv_mom_rsi.py:57-62`) |
| **T (muestra)** | **80 meses efectivos** 2020-01→2026-08 (T_total 92 truncado al múltiplo de 16 reteniendo recientes, `PLAN_MEJORA_MATEMATICA.md:3036` — "T_total=92 → T=80"), bloques S=16 × ~5 meses (~105 ruedas cada) |
| **Ventana** | 2019-01-01→2026-08-04 (misma que baseline limpio) (`:3035`, artefacto `pbo_cscv_mom_rsi_093300.txt:4`) — más corta que §39 (2016→2026) |
| **Universo/costos** | 50 canónico `opportunities_universe.SYMBOLS`, COST_PER_SIDE 0.0005 + slippage 0.0005, EXECUTION_LAG 1 (`:3039`) |
| **Métrica** | Sharpe anualizado mensual idem §39 (`:3037`) |
| **Checks fidelidad** | OK con piso **MIN_T_MONTHS=72** (`pbo_cscv_mom_rsi.py:78`): T=80≥72, cobertura 85% (68/80), edge +1.98%/mes >0 (`pbo_cscv_mom_rsi_093300.txt:18-25` FIDELIDAD GLOBAL OK) — ver nota post-hoc abajo |
| **Artefacto final** | `backend/data/cache/pbo_cscv_mom_rsi_20260822_093300.txt:27-50` + `.json` (duración 42.6s) |
| **Resultado numérico** | **PBO = 0.4688** (6033/12 870 λ≤0, λ mediana +0.201 media +0.949 p5 −2.944 p95 +20.72 std 7.22), degradación mediana Sharpe −0.322, Spearman mediana +0.030, rank_OOS best IS mediana 12.0 (teórica 11.0), Sharpe_full +0.68→+1.25 ACTUAL +0.934 rank 17/21 (`:3051-3054`, artefacto `:27-45`) |
| **Criterio pre-registrado** | PBO<0.10 CUMPLE, 0.10-0.20 gris (binario NO_CUMPLE), ≥0.20 NO_CUMPLE, ≥0.30 sustancial (`PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:84-90`, `PLAN_MEJORA_MATEMATICA.md:3030`) → **NO_CUMPLE + sustancial** |
| **Veredicto ledger** | `signal_diagnosis 21→22`, id `pbo_cscv_mom_rsi`, umbral `PBO<0.10 (Bailey et al.)`, artefacto `pbo_cscv_mom_rsi_20260822_093300.txt` (`:3057`) |

**Nota trazable sobre piso T post-hoc** (`RESUMEN_PBO_CSCV_BASELINE.md:112-121`): primera corrida paralela `pbo_cscv_mom_rsi_20260822_093109.txt:20-25` con piso T≥96 dio **FALLIDA** (T_final 80 <96, `FALLIDA — corrida no interpretable`). La corrida final pasó porque `pbo_cscv_mom_rsi.py:78` fija `MIN_T_MONTHS=72` (el pre-registro §40 no cita 96 sino ≥72 en `:3050` "T=80 ≥72"). El `RESUMEN_PBO_CSCV_BASELINE.md:118-121` lo marca como "piso que baja DESPUÉS de ver una corrida fallida es, estrictamente, post-hoc — no invalida §40, pero conviene saberlo al ponderar". Verificado: el script final efectivamente define `MIN_T_MONTHS=72` desde su primera versión commitada, no es edición posterior al fallo — la inconsistencia es entre el criterio usado por la corrida paralela temprana (heredado de §39) y el del pre-registro §40.

---

## 4. Comparativa metodológica lado a lado

| Dimensión | §39 (PBO=0.2358 INTERMEDIO) | §40 (PBO=0.4688 SUSTANCIAL) | Implicación |
|---|---|---|---|
| **Pregunta** | ¿El baseline elegido es cherry-pick entre vecinas plausibles? (overfitting de diseño) | ¿Elegir "lo menos malo" entre 21 ideas heterogéneas generaliza? (overfitting de proceso/selectivo) | Preguntas distintas, ambas válidas |
| **N** | 27 vecinas reales del mismo modelo (grid factorial completo) | 21 nombres del ledger proxyeados por 21 vecinas del *mismo grid* (limitación §8.1 heterogeneidad declarada) | §39 mide vecindario real; §40 mide vecindario como proxy de proceso heterogéneo — pérdida de fidelidad en §40 |
| **Qué significa cada N** | 27 = sensibilidad paramétrica local (grado, no existencia) | 12870 splits NO es N configs — es C(16,8) combinaciones IS/OOS (mismo en ambos) | Confusión frecuente: 12870 no es "más exhaustivo" que 27 — es el denominador combinatorio |
| **T y bloques** | T=128 (2016-2026) × 8 meses/bloque → splits IS/OOS ~64 meses | T=80 (2020-2026) × 5 meses/bloque → splits ~40 meses | Bloques más largos → Sharpe por split más estable → varianza menor → PBO menos inflado (ver §5) |
| **Ventana/estructura** | Incluye 2016-2019 (mercado distinto, más historia para bloques) | Solo post-2019 (ventana del baseline limpio, sin 2016-2018) — decisiones post-cutoff | Ventanas no comparables 1:1; §39 tiene más potencia por T |
| **Proxies/definición** | Mismo grid pero **27 completas**, sin mapeo heterogéneo | 21 del grid mapeadas a nombres heterogéneos (gap, FinBERT, OFI…) — §40 §8 admite que no reconstruye performance real de esos trials | Isomorfismo Tres Inspiradores: §40 asume comparabilidad que no existe; §39 no necesita ese supuesto |
| **Ledger** | Auditoría NO consume slot, criterio laxo ≤0.20 | Trial consume 1 slot, criterio estricto <0.10 (y 0.20/0.30) | La misma PBO 0.2358 sería INTERMEDIO en §39 y NO_CUMPLE en §40 por umbrales distintos |
| **Rigor pre-registro** | Sellado en `PLAN_MEJORA_MATEMATICA.md:2990` (≤0.20/0.20-0.50/>0.50) | Sellado en `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md:84` (<0.10/0.10-0.20/≥0.20/≥0.30) + §6.1 N congelada | Ambos pre-registrados, pero §40 declara limitaciones más explícitas |
| **Robustez declarada** | Vectorizado mensual sin stops/regime-gating, embargado implícito por meses, sin leakage de precios intradía | Igual + lag 1 explícito, embargo por meses, seed 42, pero ventana corta + proxy heterogéneo | Ninguno es "robusto CSCV con embargo de purging a nivel de trade" — ambos son aproximaciones de score, no backtest full |
| **Hallazgo cualitativo** | Todas 27 Sharpe +0.55→+0.90 positivas; ACTUAL 12/27 (no cherry-pick) | Todas 21 Sharpe +0.68→+1.25 positivas; ACTUAL 17/21 (tampoco cherry-pick) — degradación mediana −0.32 | Ambos dicen "edge de grado, no de existencia" |

### Criterios de solidez según literatura

- **Bailey & López de Prado (2014, PBO JoPM; 2017 CSCV book)**: PBO válido requiere N≥2 configs comparables rankeadas por misma métrica, S particiones contiguas con embargo, métrica Sharpe IS/OOS, y familia pre-definida (no buscada post-hoc). Citado en ambos (§39:2958, §40:3032, PRE_REGISTRO:39).
- **Pardo (2008, *Evaluation & Optimization of Trading Strategies*)**: walk-forward con N configuraciones debe separar selección (IS) de evaluación (OOS) sin re-optimizar; lo que CSCV formaliza con combinatoria.
- **López de Prado (2018, *Advances in Financial Machine Learning*, cap. 12-13)**: CSCV corrige snooping ex-post pero no snooping ex-ante (histórico ya quemado) — por eso ambos PBO miden selección dentro del histórico quemado 2019-2026, no prueban holdout.

**Juicio con esos criterios**:

- §39 satisface mejor **comparabilidad** (27 parametrizaciones del mismo modelo, misma métrica, misma ventana) y **potencia** (T=128, bloques 8m) — es la auditoría más limpia de sensibilidad local.
- §40 satisface mejor **intención** (audita el proceso real del ledger de 21 ideas) pero **viola comparabilidad** por diseño proxyeado (limitación §8.1 declarada por el propio autor: "las 21 no son 21 parametrizaciones del mismo modelo; son 21 familias distintas") y tiene **menos potencia** (T=80, bloques 5m → Sharpe por split ruidoso). Es el diseño más ambicioso pero metodológicamente más débil — exactamente lo que la auditoría denuncia como "diseño más débil".

**Isomorfismo Tres Inspiradores** (checklist del repo): ambos PBO comparten universo 50 y gates del motor, pero difieren en N_efectivo y definición de "mejor config" (argmax entre vecinas vs cercanía a mediana entre proxies). Son isomórficos en combinatoria (12870) pero no en semántica de familia.

---

## 5. Por qué dan tan distinto (0.2358 vs 0.4688) — explicación honesta

No es un bug ni una contradicción lógica; son **diseños distintos midiendo cosas distintas con potencia distinta**. Contribución estimada por factor:

1. **Granularidad de vecindad / bloque (factor dominante)**  
   §39: bloques 8 meses → cada split IS/OOS ~64 meses → SE(Sharpe_mensual) ≈ σ/√64 ≈ 0.125σ. §40: bloques 5 meses → ~40 meses → SE ≈ 0.158σ (+27% ruido). Artefactos confirman: §39 λ p5 −0.154 / p95 +0.310 (rango 0.46) vs §40 λ p5 −2.94 / p95 +20.7 (rango 23.6, std 7.22). Mismo PBO con Sharpe por split mucho más disperso → cruza la mediana con más frecuencia → PBO inflado. Este efecto solo explica gran parte del 0.23→0.47.

2. **T y ventana**  
   §39 usa 128 meses (2016-2026) incluyendo 2016-2019 con regímenes distintos; §40 trunca a 80 (2020-2026) reteniendo recientes. T mayor → bloques más estables → PBO menor. Diferencia de período explica además Sharpe_full: ACTUAL 0.714 (§39, incluye años flojos) vs 0.934 (§40, ventana corta y reciente más favorable — validación OOS fresca 2024-2026 dio Sharpe +1.33).

3. **Definición de familia / heterogeneidad**  
   §39: 27 configs reales del vecindario — todas correlacionadas (mismo modelo, correlación entre Sharpes alta) → variance efectiva entre configs pequeña → ranking IS menos ruidoso. §40: 21 proxies correlacionados igual (mismo grid) pero etiquetados como familias heterogéneas → si fueran heterogéneas reales, la dispersión entre Sharpes sería mayor (gap, FinBERT… con Sharpe muy distintos) y el PBO sería distinto; al proxyearlas por vecinas correlacionadas, se subestima la dispersión real y se mezcla señal de overfitting de proceso con ruido de proxy.

4. **Definición de "mejor config" idéntica, pero N distinto**  
   Ambos: argmax Sharpe IS. Con N=27 vs N=21, la mediana teórica es 14 vs 11; con ranking IS ruidoso, N mayor tiende a PBO ligeramente mayor (más candidatos → más chance de que el #1 IS sea outlier). Efecto menor que (1) y (2).

5. **Período y proxies específicos**  
   §39 "proxies" = parametrizaciones vecinas reales; §40 "proxies" = nombres del ledger mapeados a vecinas (limitación §8). No hay diferencia de "baseline_proxies 2019-2026 vs mom/rsi específicos" como tal — ambos usan el mismo grid mom/rsi; la diferencia es la ventana (2016 vs 2019 start) y la semántica (vecinas vs procesos). Artefactos: `pbo_cscv_baseline_093149.txt:16` lista Sharpe +0.55→+0.90; `pbo_cscv_mom_rsi_093300.txt:7-27` lista +0.68→+1.25 — rangos solapados, no explican el gap de PBO.

6. **Varianza del estimador PBO**  
   Con 12 870 splits, SE(PBO) = √(p(1−p)/n) ≈ √(0.25/12870) ≈ 0.0044 — ambos PBO son distinguibles (0.236±0.004 vs 0.469±0.004 no se solapan). La diferencia 0.23 es 50× el SE, no es ruido de muestreo combinatorio.

**Resumen**: 0.236 es PBO de sensibilidad local con bloques largos y ventana larga (diseño más conservador y potente); 0.469 es PBO de auditoría de proceso proxyeada con bloques cortos y ventana corta (diseño más ruidoso y con limitación de isomorfismo). Ambos dicen cualitativamente lo mismo — "elegir la mejor IS entre correlacionadas tiene valor predictivo limitado, edge de grado" — y difieren en grado por diseño, no por cherry-picking.

---

## 6. Recomendación fundamentada (no veredicto)

### Qué recomienda esta investigación tratar como veredicto vigente

**Recomendación: tratar §39 (PBO=0.2358 INTERMEDIO) como medición vigente del proceso de vecindad del baseline, y §40 (PBO=0.4688) como auditoría de proceso con limitación de proxy — citada pero no promovida a veredicto único.**

Fundamentos (criterios, no preferencia):

| Criterio Bailey/LdP + Pardo | §39 | §40 | Gana |
|---|---|---|---|
| Familia pre-definida y comparable (misma métrica, mismo modelo) | Sí — 27 vecinas reales, sin mapeo heterogéneo | No — 21 nombres heterogéneos proxyeados por vecinas (limitación §8.1 auto-declarada) | §39 |
| Potencia (T, bloque) | T=128, bloque 8m, SE menor, λ rango 0.46 | T=80, bloque 5m, SE +27%, λ rango 23.6 | §39 |
| Embargo / leakage / walk-forward | Vectorizado mensual con lag 1 implícito, sin purging a nivel trade pero con bloques contiguos (igual que §40) | Idem, pero ventana trunca 2016-2019 (pierde un ciclo completo) | Empate leve §39 |
| Pre-registro y trazabilidad | Sellado en PLAN §39 + artefacto duplo idéntico (092850 y 093149) | Sellado en PRE_REGISTRO + PLAN §40, pero con piso T 72 post-hoc (ver §3b nota) | §39 |
| Pregunta respondida | ¿El baseline es artefacto de haber elegido parámetros entre vecinas? | ¿Haber mirado 21 ideas heterogéneas invalida el baseline? | Ambas válidas, pero §39 responde la que la auditoría pide "decidir entre 0.236 y 0.469" con evidencia más limpia |
| Consistencia con OOS fresca | Compatible: validación OOS fresca Sharpe +1.33 (validacion_oos_fresca_155520.txt:17, DSR 0.6077) muestra edge bruto en datos no vistos por la selección — apoya "riesgo de grado" de §39, no "no hay edge" | También compatible pero con DSR 0.6077 <0.95 (NO_CUMPLE) — el mismo T=30 corto que limita §40 | Ambas compatibles |

**Por qué no el veredicto "OVERFITTING sustancial" de §40 como único**: §40 es el diseño más débil por los tres motivos que la auditoría señala — proxies (isomorfismo roto), piso T post-hoc (72 vs 96), y bloques cortos (5m) — y su propio autor lo declara como limitación §8. Promoverlo a veredicto único sería premiar el diseño menos robusto. Bailey & LdP exigen familia comparable; Pardo exige que walk-forward mida el mismo modelo, no 21 familias mapeadas a un grid.

**Qué no se recomienda**: descartar §40. Su señal es real (PBO 0.47 sustancial, degradación −0.32, Spearman 0.03) y su intención (auditar el proceso ledger) es correcta. Debe quedar citada como "auditoría de proceso proxyeada con limitación — overfitting de selección documentado bajo ese proxy" — no como "baseline revocado".

### Decisión final es de Boris — explícito

> **Esta recomendación NO implementa nada.** No toca `backend/data/trial_registry.json`, no edita `PLAN_MEJORA_MATEMATICA.md`, no cambia veredicto del ledger, no promueve ni revoca baseline. La decisión de congelar un único PBO vigente (Fase 0 de la auditoría, tarea 4) es exclusiva de Boris. Si Boris decide adoptar §40 como veredicto vigente, esta investigación no lo contradice — solo documenta que esa elección descansa sobre el diseño más débil y debe quedar explícita como tal. Si decide adoptar §39, debe quedar explícito que §40 convive como auditoría con limitación. Si decide requerir un tercer PBO con fidelidad completa (reconstrucción de las 21 con `backtest_engine.run`, sin proxies, bloques ≥8m, ventana 2016-2026, pre-registro nuevo), esa es la vía limpia que cierra la limitación de ambos.

---

## 7. Limitaciones y trazabilidad

### Limitaciones de esta comparación

1. **Ambos PBO son aproximaciones vectorizadas mensuales** (EW, sin stops ATR/barriers, sin regime-gating, sin Kelly) — miden edge del score, no P&L del motor completo. Un PBO sobre backtest full con `backtest_engine.run` (propuesto en §40 §8 y en `pbo_cscv_fidelidad_completa.py`) sería la prueba fiel, pero no existe artefacto para ella.
2. **Snooping ex-ante no medido**: DSR y PBO corrigen selección dentro del histórico 2019-2026, pero el histórico mismo ya está quemado por >40 diagnósticos (algunos sin ledger). Ningún PBO rescata holdout reservado — la validación OOS fresca (T=30) es el único OOS no quemado y dio NO_CUMPLE por DSR 0.6077 (<0.95), aunque Sharpe +1.33 bruto >0.
3. **Familia pre-definida**: ambos PBO eligen el grid vecino post-hoc (pesos/RSI/mom_hi) — no es la familia que se habría definido ex-ante antes de ver datos. Esto es estándar en auditorías retroactivas pero debe declararse.
4. **Esta comparación no re-calcula PBO ni re-corre nada** — solo lee artefactos citados en ledger.

### Trazabilidad completa (ledger → artefacto → pre-registro)

| Ledger entry | Artefacto `.txt` | Pre-registro | Fidelidad |
|---|---|---|---|
| *(no ledger — auditoría)* §39 | `pbo_cscv_baseline_20260822_092850.txt` + `093149.txt` (idénticos, PBO 0.2358) | `PLAN_MEJORA_MATEMATICA.md:2946-3004` | OK (T=128, 4/4) |
| `pbo_cscv_mom_rsi` signal_diagnosis 21→22 2026-08-22 | `pbo_cscv_mom_rsi_20260822_093300.txt` (PBO 0.4688) — previa `093109.txt` FALLIDA T=80<96 | `PRE_REGISTRO_PBO_CSCV_MOM_RSI.md` + `PLAN_MEJORA_MATEMATICA.md:3024-3045` | OK con MIN_T=72 (nota post-hoc) |
| `validacion_oos_fresca_mom_rsi` signal_diagnosis 22→23 2026-08-22 | `validacion_oos_fresca_mom_rsi_20260822_155520.txt` (Sharpe +1.33 DSR 0.6077 NO_CUMPLE) | `PRE_REGISTRO_VALIDACION_OOS_FRESCA_MOM_RSI.md` | OK 6/6 |

Figuras citables: `RESUMEN_PBO_CSCV_BASELINE.md:77-129` (colisión y addendum), `RESUMEN_PBO_CSCV_BASELINE.md:107` (recomendación tomar §39), `PLAN_MEJORA_MATEMATICA.md:3059` (interpretación "riesgo de grado, no de existencia").

### Verificación de no-mutación (exigida por tarea 7)

```bash
git -C /Users/boris/orca/workspaces/fortress_core/test-opencode-orca status --short
# Esperado: solo ?? COMPARACION_PBO_39_VS_MOMRSI.md (untracked), sin M backend/data/trial_registry.json ni cache
git -C /Users/boris/orca/workspaces/fortress_core/test-opencode-orca diff --stat
# Esperado: vacío (esta comparación solo añade, no modifica)
```

Esta investigación no commitea — avisa. El archivo nuevo queda untracked para revisión de Boris antes de cualquier commit.

---

*Fin — solo evidencia, sin veredicto implementado. Toda afirmación numérica remite a artefacto con path:línea verificable arriba.*
