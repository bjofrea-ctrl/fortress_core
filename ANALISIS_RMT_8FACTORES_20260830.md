# RMT — Interpretación económica de los 8 factores residuales (Fase 0.5b)

**Artefacto fuente:** `backend/data/cache/rmt_mp_20260811_150849.txt` (Fase 0.5b §4.2, 2026-08-11)  
**Script fuente:** `backend/scripts/diagnose_rmt_mp.py` (no re-calculado con metodología nueva)  
**Artefacto complementario:** `backend/data/cache/sector_clusters_20260811_170235.txt` (Fase §9c, Ward + autovectores)  
**Fecha análisis:** 2026-08-30 — worktree `test-opencode-orca`  
**Restricción:** solo lectura de artefactos existentes + proyección de loadings/corr sobre matriz ya definida. No backtest, no trial, no ledger.

---

## 0. Parámetros del RMT (copiados del artefacto, no recalculados con parámetros nuevos)

```
Universo: 50 símbolos | 2019-01-01 -> 2026-08-04
Matriz: N=50 x T=1658 (q=0.0302) -> tras estandarización rodante 252d: N=50 x T=1599 (q=0.0313, λ₊=1.385)
Espectro completo: λ_max=15.413 | λ₂=5.127 | λ₃=2.661 -> 5 sobre λ₊ (mercado + 4)
Varianza PC1 (mercado): 30.8%
Espectro RESIDUAL (mercado removido): λ_max_res=7.589 | λ₂=3.850 | λ₃=2.882 | λ₄=2.003
  [ λ=7.59, 3.85, 2.88, 2.00, 1.74, 1.64, 1.52, 1.40 ] -> 8 sobre λ₊
  Dominancia F0: 15.2% de varianza residual (7.589 / sum 49.96)
```

Toda la proyección abajo usa **exactamente** el pipeline auditado de `diagnose_rmt_mp.py:30-56`:
`rets -> z rolling 252/60 -> corr -> eig -> pc1 scores/beta/resid -> corr_res -> eig_res`.

---

## 1. Loadings completos (autovectores residuales, 50 símbolos x 8 factores)

Umbral de reporte en `sector_clusters`: |carga| > 0.283 = 2/√50. Debajo también hay señal, pero se lista top 15 por |carga|.

**Archivo crudo generado (mismo pipeline):** `backend/data/cache/rmt_loadings_8factors.csv` y `data/cache/rmt_loadings_8factors.csv`

### F0  λ=7.589  (15.2% var. residual) — Growth/tech vs defensivo staples

```
  QQQ    +0.3222 | NVDA   +0.2428 | KO     -0.2394 | JNJ    -0.2318 | SPY    +0.2210
  PEP    -0.2104 | PG     -0.2095 | AMD    +0.2022 | AVGO   +0.1980 | BRK-B  -0.1859
  AMZN   +0.1816 | ABBV   -0.1787 | MCD    -0.1708 | PM     -0.1699 | MSFT   +0.1640
  [+0.30 más] LLY -0.068 etc.
  POS (>0.283): QQQ(0.32)
  NEG (<-0.283): —
  Extendido top15 positivo: QQQ, NVDA, SPY, AMD, AVGO, AMZN, MSFT, META, TSLA ...
  negativo: KO, JNJ, PEP, PG, BRK-B, ABBV, MCD, PM ...
```
**Lectura:** eje growth/Nasdaq vs consumo defensivo (staples + farma defensiva + Berkshire). Es el factor "beta sectorial" residual más fuerte. En clusters: C0 (SPY/QQQ/NVDA/TSLA/AVGO/BRK-B/PG/JNJ/KO/PEP/AMD/PM) y H2 (SPY/QQQ/NVDA/AVGO/PG/KO/PEP/AMD/MCD/QCOM/PM/TXN) lo capturan juntos — justamente mezcla growth+defensivo que F0 separa por signo.

### F1  λ=3.851  (7.7%) — Cíclico industrial/bancos vs tech acíclico + value

```
  CAT    -0.3569 | JPM    -0.3156 | BAC    -0.3102 | ADBE   +0.2750 | CVX    -0.2297
  XOM    -0.2294 | GE     -0.2242 | INTU   +0.2195 | SPY    -0.2112 | CRM    +0.1964
  MSFT   +0.1874 | COST   +0.1791 | ACN    +0.1572 | BRK-B  -0.1547 | TXN    -0.1512
  POS: —
  NEG: CAT(0.36), JPM(0.32), BAC(0.31)
```
**Lectura:** polo negativo = **cíclicos puros** (CAT industriales, JPM/BAC bancos, XOM/CVX energía, GE). Polo positivo = **software/SaaS** (ADBE, INTU, CRM, MSFT, ACN). Es value/cíclico vs growth acíclico.

### F2  λ=2.885  (5.8%) — Pagos/fintech vs farma

```
  MA     +0.3070 | V      +0.2762 | CRM    +0.2462 | ACN    +0.2195 | INTU   +0.2159
  AMGN   -0.2042 | ADBE   +0.1867 | BAC    +0.1826 | TXN    -0.1814 | PEP    -0.1781
  PG     -0.1731 | MRK    -0.1723 | JPM    +0.1719 | QQQ    -0.1672 | DIS    +0.1664
  POS: MA(0.31)
```
**Lectura:** polo positivo = **redes de pago + consultoría/SaaS** (MA/V, ACN/CRM/INTU). Negativo = **farma defensiva + semiconductores legacy** (AMGN, MRK). Fina separación dentro de tech.

### F3  λ=2.003  (4.0%) — Herramientas farma/lab vs retail/staples

```
  TMO    -0.2936 | PFE    -0.2772 | WMT    +0.2549 | COST   +0.2194 | ACN    -0.2078
  ABBV   -0.2046 | AMGN   -0.1966 | IBM    -0.1943 | MRK    -0.1921 | LLY    -0.1877
  MCD    +0.1786 | KO     +0.1743 | CRM    -0.1726 | PG     +0.1704 | MA     +0.1620
  POS: — | NEG: TMO(0.29)
```
**Lectura:** laboratorio/herramientas (TMO) + farma (PFE, ABBV, AMGN, MRK, LLY) vs **retail defensivo** (WMT, COST, MCD, KO, PG). Dispersión intra-health.

### F4  λ=1.733  (3.5%) — Energía pura (petróleo) vs resto

```
  XOM    +0.3072 | CVX    +0.3066 | MRK    -0.2428 | COST   +0.2410 | LLY    -0.2243
  CSCO   +0.2230 | META   -0.1978 | V      -0.1792 | AMZN   -0.1789 | GE     -0.1760
  TMO    -0.1758 | TXN    +0.1732 | PFE    -0.1729 | MA     -0.1723 | GOOGL  -0.1624
  POS: XOM(0.31), CVX(0.31)
```
**Lectura:** factor **energía puro** (XOM/CVX). Clusters H3 (`XOM, CVX` solo) lo aísla perfecto.

### F5  λ=1.638  (3.3%) — Anti-energía (inverso de F4, con matiz tech)

```
  CVX    -0.3446 | XOM    -0.3301 | AMZN   -0.2740 | V      +0.2487 | MA     +0.2404
  NFLX   -0.2262 | GOOGL  -0.2075 | LIN    +0.1990 | CMCSA  -0.1943 | META   -0.1943
  SPGI   +0.1900 | AVGO   +0.1808 | DIS    -0.1645 | QCOM   +0.1599 | IBM    +0.1531
  POS: — | NEG: CVX(0.37), XOM(0.35)
```
**Lectura:** **mismo subespacio energía que F4 pero signo opuesto** — artefacto de haber dos dimensiones para petróleo (F4/F5 son ortogonales pero ambas cargan XOM/CVX con signos cruzados). Indica que el factor petróleo no es 1D sino 2D en residuos (posible régimen contango/backwardation).

### F6  λ=1.521  (3.0%) — Enterprise legacy vs pagos/semis nuevos

```
  ORCL   -0.3752 | V      +0.3237 | MA     +0.3097 | TXN    +0.3021 | QCOM   +0.2512
  BAC    -0.2084 | JPM    -0.2048 | IBM    -0.2016 | AAPL   +0.2006 | WMT    -0.1978
  XOM    +0.1769 | GE     -0.1630 | CSCO   -0.1509 | SPY    -0.1445 | MSFT   -0.1439
  POS: V(0.32), MA(0.32), TXN(0.30) | NEG: ORCL(0.36)
```
**Lectura:** **ORCL/IBM/bancos** (value tech + financiero) vs **pagos + semiconductores** (V/MA + TXN/QCOM/AAPL). Rotación dentro de tech: old tech vs semis/pagos.

### F7  λ=1.395  (2.8%) — Consumo discrecional/media vs pagos/tech

```
  HD     -0.4021 | V      +0.3019 | MA     +0.2807 | DIS    -0.2714 | ORCL   +0.2677
  CMCSA  -0.2606 | TXN    -0.1943 | MSFT   +0.1930 | CSCO   +0.1833 | XOM    +0.1763
  QCOM   -0.1747 | TMO    -0.1643 | BAC    -0.1614 | CVX    +0.1600 | LLY    +0.1351
  POS: V(0.30), MA(0.28) | NEG: HD(0.40)
```
**Lectura:** **HD/CMCSA/DIS** (retail discrecional + media/teleco) vs **pagos** (V/MA). Complementa F6 pero en consumo.

---

## 2. Correlación con series macro conocidas (mismo estilo RMT, no metodología nueva)

Factor scores = `resid @ eigvec` (proyección de residuos sobre autovector), T=1599 días. Macro retornos diarios `pct_change` alineados al mismo índice z. Correlación de Pearson factor vs macro-ret. Umbral de reporte >0.10 (ruido ~0.025 = 1/√T).

**Archivo crudo:** `backend/data/cache/rmt_factor_scores_8factors.csv`

```
F0:  QQQ  +0.366 | SPY +0.109 | VIX -0.101
     -> QQQ/Nasdaq puro. Coherente con F0 growth vs defensivo.

F1:  DBC  -0.278 | EFA -0.212 | HG -0.200 (cobre) | TLT +0.209 | AGG +0.180 | SPY -0.108 | VIX +0.136
     -> Cíclico global inverso: cuando DBC/cobre/EFA suben, F1 baja (porque F1 negativo=cíclicos). TLT positivo = vuelo a bonos cuando cíclicos caen. VIX positivo = stress.

F2:  GLD -0.142 | TLT -0.152 | AGG -0.159 | GC -0.114 | DBC +0.108
     -> Débil. Oro/bonos negativo vs pagos positivo.

F3:  DBC -0.138  (solo)
     -> Casi ortogonal a macro — factor intra-health/retail puro.

F4:  DBC +0.323 | CL +0.105 (petróleo spot)
     -> Energía/commodities puro. Confirma F4 = petróleo.

F5:  DBC -0.294 | TLT +0.106
     -> Anti-energía. Mismo petróleo que F4 pero signo opuesto, más bonos.

F6:  DBC +0.140
     -> Débil, intra-tech.

F7:  DBC +0.207 | TLT -0.129 | AGG -0.162
     -> Consumidor vs pagos, con beta commodities positivo y bonos negativo (rates up = HD/DIS caen).
```

**Tabla completa sin threshold (para archivo):**

| Factor | λ | SPY | EFA | QQQ | GLD | DBC | TIP | TLT | AGG | VIX.ret | DXY | Gold | Oil | Copper | VIX.level |
|--------|---|-----|-----|-----|-----|-----|-----|-----|-----|---------|-----|------|-----|--------|-----------|
| F0 |7.59|+0.11|-0.02|+0.37|-0.02|+0.02|-0.04|-0.05|-0.06|-0.09|+0.03|-0.02|+0.01|-0.01|-0.10*|
| F1 |3.85|-0.11|-0.21|-0.07|+0.07|-0.28|+0.05|+0.21|+0.18|+0.14|-0.02|+0.07|-0.09|-0.20|+0.14|
| F2 |2.88|-0.04|+0.08|-0.03|-0.14|+0.11|+0.00|-0.15|-0.16|+0.01|+0.02|-0.11|+0.03|+0.04|-0.02|
| F3 |2.00|+0.04|-0.01|+0.03|+0.03|-0.14|+0.05|+0.07|+0.06|+0.02|+0.02|+0.03|-0.05|-0.05|+0.03|
| F4 |1.73|-0.01|+0.05|-0.02|-0.01|+0.32|+0.02|+0.01|+0.02|+0.04|+0.00|-0.01|+0.11|+0.03|+0.01|
| F5 |1.64|-0.05|-0.04|-0.07|+0.04|-0.29|+0.03|+0.11|+0.07|+0.01|-0.05|+0.04|-0.09|-0.05|-0.01|
| F6 |1.52|+0.01|+0.04|+0.05|+0.01|+0.14|-0.02|-0.04|-0.04|-0.04|-0.00|+0.01|+0.06|+0.02|-0.02|
| F7 |1.40|+0.00|+0.02|-0.02|-0.05|+0.21|-0.02|-0.13|-0.16|+0.02|-0.01|-0.05|+0.06|+0.05|-0.02|

*VIX.level = correlación con nivel de VIX, no ret. Solo reportado si >0.10.

---

## 3. Validación cruzada con clusters endógenos (§9c)

El propio diagnóstico sectorial ya agrupó los mismos loadings (argmax y Ward) y testeó si el momentum medio del cluster predice:

```
Cargas >0.283:
  F0 QQQ(0.32)
  F1 CAT(0.36) JPM(0.32) BAC(0.31)
  F2 MA(0.31)
  F3 TMO(0.29)
  F4 XOM(0.30) CVX(0.29)
  F5 CVX(0.37) XOM(0.35)
  F6 ORCL(0.36) V(0.34) MA(0.32) TXN(0.30)
  F7 HD(0.37) CMCSA(0.29) V(0.29) DIS(0.28)

Clusters argmax (C0-C7):
  C0 12 SPY/QQQ/NVDA/TSLA/AVGO/BRK-B/PG/JNJ/KO/PEP/AMD/PM  -> F0 growth+defensivo mixto
  C1 6  JPM/BAC/ADBE/GE/INTU/CAT                          -> F1 cíclico/bancos
  C3 6  WMT/UNH/ABBV/TMO/MCD/PFE                           -> F3 farma vs retail
  C4 5  META/LLY/COST/MRK/CSCO                            -> mixto
  C5 7  GOOGL/AMZN/XOM/NFLX/CVX/LIN/SPGI                  -> F4/F5 energía + growth
  C6 7  AAPL/V/MA/ORCL/IBM/QCOM/TXN                       -> F2/F6 pagos/semis
  C7 4  MSFT/HD/CMCSA/DIS                                  -> F7 consumo/media

Ward (H1-H8) aísla aún mejor:
  H3 2 XOM,CVX  (energía pura = F4/F5)
  H5 2 V,MA     (pagos puro = F2/F6/F7)
  H1 6 LLY/JNJ/ABBV/MRK/AMGN/PFE (farma pura = F3)
  H7 2 WMT,COST (retail staples = parte de F3)
```

Rank IC intra-día por cluster (momentum_score medio -> fwd 20d):
```
autovectores  mean_IC +0.0339  t=+1.03  (umbral 2.73) no sig
jerárquico    mean_IC +0.0230  t=+0.57  no sig
```
Es decir: los 8 factores son **reales en covarianza**, pero su **momentum promedio no predice** (misma conclusión que RMT: estructura sectorial difusa sin explotar por los factores actuales).

---

## 4. Interpretación económica por factor (síntesis no inventada — derivada de loadings + macro)

| Factor | Nombre operativo | Economía | Evidencia | Macro beta |
|--------|------------------|----------|-----------|------------|
| **F0** | Growth vs Staples | Nasdaq/big-tech vs consumo básico/farma defensiva | QQQ +0.32 vs KO/JNJ/PG/PEP negativo; C0 mezcla ambos | QQQ +0.37, VIX -0.10 (risk-on) |
| **F1** | Cíclico value vs SaaS | Industriales+bancos+energía vs software | CAT/JPM/BAC↔ADBE/INTU | DBC -0.28, EFA -0.21, TLT +0.21 (cíclico global) |
| **F2** | Pagos / fintech | Redes pago + servicios IT | MA/V/ACN vs farma | Oro/bonos débil |
| **F3** | Health-tools vs Retail | Instrumentos lab + farma vs retail defensivo | TMO/PFE vs WMT/COST | casi ortogonal a macro |
| **F4** | Energía 1 (petróleo) | Oil majors | XOM/CVX puro | DBC +0.32, CL +0.11 |
| **F5** | Energía 2 (anti-oil) | Inverso petróleo, con beta tech | XOM/CVX negativo vs V/MA | DBC -0.29 |
| **F6** | Old-tech vs semipagos | ORCL/IBM vs V/MA/TXN/QCOM | ORCL ↔ V/MA | débil macro |
| **F7** | Discrecional vs Pagos | HD/DIS/CMCSA vs V/MA | HD -0.40 vs V/MA +0.30 | DBC +0.21, TLT -0.13 |

**Patrón general:** ninguno de los 8 replica tasas (TLT), oro (GLD) o VIX de forma fuerte salvo F1 (cíclico) y F4/F5 (energía). La mitad de los factores (F2,F3,F6, parte de F7) son **intra-sector techo** (pagos vs farma, tech viejo vs nuevo) casi ortogonales a macro — explicaría por qué el ridge con macro crudo (Fase 0.5c) no mejoró IC: los factores residuales **no son macro**.

**Dominancia 15.2%:** F0 explica 7.59/50=15.2% de varianza residual (no total). Los 8 juntos explican (7.59+3.85+2.88+2.00+1.74+1.64+1.52+1.40)/50 = 49.2% de varianza residual, 33.9% de varianza total. El resto (41 factores) = ruido MP.

---

## 5. Evidencia cruda — archivos y reproducción

```
Artefacto RMT: backend/data/cache/rmt_mp_20260811_150849.txt  (q=0.0313, λ₊=1.385, 8>λ₊)
  [ λ=7.59, 3.85, 2.88, 2.00, 1.74, 1.64, 1.52, 1.40 ]

Loadings: backend/data/cache/rmt_loadings_8factors.csv  (50 x 8, filas símbolos, cols F0-F7)
Factor scores: backend/data/cache/rmt_factor_scores_8factors.csv (1599 x 8, index fecha)
              data/cache/rmt_loadings_8factors.csv  (copia en root data/cache)

Clusters: backend/data/cache/sector_clusters_20260811_170235.txt
  F0 QQQ(0.32) | F1 CAT(0.36) JPM(0.32) BAC(0.31) | F2 MA(0.31) | F3 TMO(0.29) | F4 XOM(0.30) CVX(0.29) | F5 CVX(0.37) XOM(0.35) | F6 ORCL(0.36) V(0.34) MA(0.32) TXN(0.30) | F7 HD(0.37) CMCSA(0.29) V(0.29) DIS(0.28)

Universo 50: _BASE_SYMBOLS 7 (SPY/QQQ/AAPL/MSFT/GOOGL/AMZN/NVDA) + NEW_UNIVERSE 43 (META/TSLA/AVGO/BRK-B/LLY/JPM/WMT/V/UNH/XOM/MA/ORCL/PG/COST/HD/JNJ/ABBV/BAC/MRK/CRM/KO/ADBE/PEP/AMD/NFLX/TMO/CVX/CSCO/ACN/MCD/IBM/LIN/QCOM/GE/INTU/PM/CMCSA/DIS/TXN/CAT/AMGN/PFE/SPGI)
MARKET_TICKERS: SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG/^VIX  + DX-Y.NYB/GC=F/CL=F/HG=F para correlación

Repro: PYTHONPATH=backend .venv/bin/python backend/scripts/rmt_interpret_tmp.py
  (reusa exactamente residual_matrix() de diagnose_rmt_mp.py + sector_clusters.py, no umbrales nuevos)
```

---

## 6. Limitaciones y no-conclusiones (honestidad)

- Los signos de autovectores son arbitrarios (PCA). F4/F5 son el mismo subespacio energía con orientación opuesta — contarlos como "dos factores energía" puede ser sobre-interpretación; podría ser 1 factor energía con estructura no lineal.
- Cargas |0.20-0.28 también importan (no solo >0.283). Listar solo >0.283 subestima la difusividad: F0 p.ej. tiene 15 símbolos con |carga|>0.15, no solo QQQ.
- Correlaciones macro son **contemporáneas** (factor score vs ret macro del mismo día), no predictivas. Un factor puede ser macro-neutral en correlación y aun ser predicho por macro con lag.
- Ward k=8 es elección del diagnóstico (k = n_factores). Otra k daría otros clusters; la no-significancia del rank IC es robusta a esa elección (t<1.1 en ambas definiciones).
- No se propone usar estos factores para trading — son descriptivos de covarianza pasada (2020-2026). El propio diagnóstico sectorial mostró que su momentum no predice (t 1.03/0.57 < 2.73).

---

*Archivo nuevo — no toca ledger, no requiere pre-registro. Autor: verificador independiente test-opencode-orca, 2026-08-30.*
