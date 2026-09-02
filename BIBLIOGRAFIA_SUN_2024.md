# Bibliografía — Red de participantes del mercado (Sun, 2024) + redes mercado 2023–2025

**Fecha:** 2026-09-02  
**Worktree:** `test-opencode-orca`  
**Autor de la búsqueda:** agente bibliográfico (muse-spark-1.2)  
**Herramientas usadas:** `websearch` (Bing/Exa), `webfetch`/lectura de highlights, barrido arXiv/SSRN/ScienceDirect. Sin acceso a Scopus/WoS de pago.  
**Criterio de búsqueda:** variantes `market participant network` / `investor network` / `trading network model` + `Sun` + `2024`, más extensiones `investor network GNN 2024`, `Sun correlation network stock`, `Sun systemic risk interbank network`, `Sun hypergraph stock 2023`. Ventana objetivo 2024 ±1 año (2023–2025) para complementos.  
**Advertencia — ambigüedad del apellido Sun:** "Sun" es apellido extremadamente común (>30 investigadores activos en finanzas/redes con ese apellido: Zhongtian Sun, Yuxin Sun, Tao Sun, Xu Sun, Li-Hsien Sun, Bo Sun, Xiaotong Sun, Yongjiao Sun, etc.). Ningún hit con el trinomio exacto *autor=Sun AND año=2024 AND título/abstract="market participant network" modelando relaciones entre participantes* con coincidencia 1:1. **Resultado principal: búsqueda negativa documentada** (ver §1). No se fuerza una atribución. Se reportan los candidatos más cercanos con filiación y DOI verificados para que el lector juzgue.

> **Contrato del hito:** solo lectura/escritura del `.md`, sin tocar código ni ledger. Git status al cierre: solo este archivo como untracked (ver §7).

---

## 1. Paper principal buscado — veredicto: NO ENCONTRADO con coincidencia exacta

**Objetivo original:** paper de Sun, 2024, que "modela red de relaciones entre participantes del mercado".

**Búsqueda ejecutada (trazabilidad completa en §6):** 14 queries `websearch` tipo `deep` + lectura de highlights/previews de ~60 candidatos (arXiv, SSRN, ScienceDirect, Nature, SpringerLink). Variantes probadas: `market participant network Sun 2024`, `investor network Sun 2024 GNN`, `trading network model Sun 2024 participants relations`, `Sun 2024 correlation network stock RMT`, `Sun 2024 financial network systemic risk`, `Zhongtian Sun hypergraph 2024`, `Xu Sun interbank 2024`, `Tao Sun tail risk network 2024`.

**Hallazgos por familia Sun:**

| Sun evaluado | Año | Tema real | ¿Coincide con "red de participantes 2024"? |
|---|---|---|---|
| **Zhongtian Sun** (Durham/Kent, PhD Durham 2024) | 2023 (journal 2023-10, tesis 2024-01) | `MONEY` — hipergrafo + GCN para predicción de movimiento de precio con info industria/fondos | **Parcial:** sí modela red entre empresas/participantes (industria, fondos), pero nodo=empresa no persona, y año journal=2023 no 2024. Es el candidato Sun más cercano a "red + mercado". |
| **Tao Sun** (Lingnan U.) | 2024-01 SSRN | Systemic Risk of SIFIs: Tail Risk Network | No: red entre instituciones sistémicas vía tail-risk, no "participant network" general. |
| **Xu Sun** (U. Florida, coautor Capponi–Yao) | 2020 (MOOR), preprints 2016/2019 | Dynamic Interbank Network, Mean Field Games | No: interbancario, no 2024. |
| **Li-Hsien Sun** (NCU Taiwan) | 2016–2019 arXiv | Systemic Risk and Interbank Lending (Feller/CIR) | No. |
| **Bo Sun** (CUFE Beijing) | 2025 | SEIQRS epidemic model sobre red interbancaria 36 bancos chinos | No: 2025 y foco epidémico. |
| **Yuxin Sun** (LSEG Quant Surveillance, ex-QUB) | — | Microestructura, OHLCV features | No hay paper 2024 de red de participantes. |
| **Yongjiao Sun et al.** | 2024 (Expert Syst. Appl.) | Social network node pricing via graph autoencoder (data marketplaces) | No: pricing de nodos en marketplaces de datos, no mercado financiero. |
| **Ning Sun / otros** | — | Trading network / matching (Sun & Yang 2006 es referencia clásica de substitutability, citada por Schlegel 2022) | Histórico, no 2024. |

**Otros papers 2024 con "investor/market network" pero autor ≠ Sun** (potencial confusión): `Investment network and stock's systemic risk contribution` (China, SciDirect 2024-04, sin Sun); `Institutional Investor Information Networks and Stock Price Synchronicity` (Xu–Du–Cheng–Zhang 2024-06); `Do manager networks affect capital markets` (Wang & Cao 2024); `Cryptocurrency co-investment network` (EPJ Data Science 2024-02); `Decentralized pure exchange on networks` (Springer 2024-08); todos sin autor Sun.

**Conclusión honesta:** con las herramientas web disponibles **no existe evidencia de un paper único, indexado y accesible que cumpla simultáneamente Autor=Sun AND Año=2024 AND Título/tema="market participant / investor / trading network model" con red entre participantes del mercado en sentido estricto.** Si el referente proviene de una cita informal, nota de lectura o memoria, es probable que sea (a) Zhongtian Sun 2023/2024 tesis+paper `MONEY`, desplazado un año, (b) una confusión con Sun & Yang (2006) + literatura 2024 que lo cita, o (c) un preprint aún no indexado. **No se inventa un paper.** Se documenta la búsqueda negativa con queries y se ofrecen los 3 sustitutos más útiles para fortress_core (mismo tema, ventana 2023–2025, con código/dataset cuando existe).

---

## 2. Fichas de papers evaluados

### Ficha A — Candidato Sun más cercano (desplazado a 2023/tesis 2024)

**Referencia completa:** Sun, Zhongtian; Harit, Anoushka; Cristea, Alexandra I.; Wang, Jingyun; Lió, Pietro (2023). *MONEY: Ensemble learning for stock price movement prediction via a convolutional network with adversarial hypergraph model.* AI Open, 4, 165–174. Tesis doctoral asociada: Sun, Zhongtian (2024). *Robustness, Heterogeneity and Structure Capturing for Graph Representation Learning and its Application* (Durham University, e-thesis 15307, cap. 5 reproduce MONEY).  
**DOI / link:** `10.1016/j.aiopen.2023.10.002` · https://doi.org/10.1016/j.aiopen.2023.10.002 · tesis https://etheses.dur.ac.uk/15307/ · repo Durham Worktribe https://durham-repository.worktribe.com/output/2118511  
**Código/dataset:** no hay repo oficial enlazado en el paper; dataset descrito como China A-share 2013–2019 provisto por ref. [36] (TuShare + industria + tenencias de fondos). Reimplementable (GCN+GRU+TA+HGCN+adv), pero no "clone-and-run".

| Dimensión | Contenido |
|---|---|
| **Metodología exacta — participantes y relaciones** | Participantes = empresas listadas (nodos). Relaciones: (i) **parwise** vía GCN sobre grafo industria (mismo sector → arista) + correlación de precio; (ii) **grupo** vía **hipergrafo** donde cada hiper-arista = industria o fondo que agrupa varias empresas (co-tenencia). Pipeline novedoso: **GCN primero → GRU + temporal attention → HGCN → ensemble voting**. Adversarial training (perturbaciones FGSM sobre embeddings antes de la capa final) para estocasticidad. Definición de participantes es **firma-céntrica**, no inversor individual. |
| **Datos para construir la red** | Precios diarios OHLC + sector (industria) + tenencias de fondos mutuos (co-holding). Ventana de lookback 5/10/20 días. Clasificación 3 clases: rise (>+0.55% vs t-1), fall (<-0.50%), steady. Costes de transacción incorporados en el umbral. |
| **Modelo sobre la red** | GCN (pairwise), hypergraph convolution (HGCN) para difusión grupo, GRU para temporal, attention temporal, ensemble de dos modelos (A con GCN, B sin GCN + adversarial) por votación. Pérdida cross-entropy + adversarial loss. |
| **Resultados con números** | Supera SOTA consistentemente en accuracy/precision/recall/F1. Ablación (ventana 10 días): GCN aporta **+3.14% total en 4 métricas (+1.03% F1)** vs sin GCN (A vs B); GCN-antes-de-RNN vs RNN-antes-de-GCN: **+5.11% total (+1.49% en 3 métricas)** (A vs E). Adversarial + HGCN mejora robustez; ensemble final es mejor en recall/F1. **Bear market:** MONEY es significativamente más estable que HGTAN y baselines (figura de drawdown cualitativa + tabla rentabilidad). Métricas absolutas dependen de ventana; paper reporta tablas por 5/10/20 días (no un solo número agregado). No hay Sharpe/IR del portfolio, solo clasificación. |
| **Evaluación crítica** | **Fortalezas:** idea limpia (pairwise + group no son redundantes), orden GCN→RNN bien argumentado y ablacionado, adversarial sensato para ruido financiero, ensemble simple. **Debilidades:** dataset China A-share 2013–2019 no es US large-cap de fortress_core (50 tickers US 2019–2026); thresholds 0.55%/0.50% ad-hoc; sin purga/embargo temporal explícito → riesgo de leakage por lookback y por hiperaristas que usan holdings del mismo periodo; sin test de significancia (Diebold-Mariano/Deflated Sharpe); sin análisis de turnover/costes más allá del umbral; sin repo → replicabilidad media. **Replicabilidad:** media (arquitectura descrita, pero sin hiperparámetros completos ni código). **Overfitting/leakage:** moderado-alto si se replica tal cual sin walk-forward purged. **Costo:** GCN+HGCN+GRU entrenable en GPU modesta (<1h por ventana en dataset ~3k stocks), pero hipergrafo escala con nº de fondos. |
| **Aplicabilidad a fortress_core** | **Complemento, no alternativa al RMT.** Nodos son empresas, no participantes humanos, pero la **idea hipergrafo industria+fondo** es directamente mapeable a nuestro universo 50 US: hiper-arista industria (GICS) y hiper-arista "co-tenencia institucional" (13F) o "co-cobertura por analistas". Podría **enriquecer los 8 factores residuales** con una capa de red antes/después del factor model. No reemplaza el filtrado MP (λ₊=1.385) porque ataca otro eje (estructura de covarianza explícita vs filtrado espectral). Piloto sin ledger viable: construir hipergrafo GICS+ETF holdings y probar GCN→RNN sobre residuos RMT en validación purgada. Ver §5. |

---

### Ficha B — Mejor paper 2024 para dialogar con nuestro RMT (no Sun, pero tema idéntico)

**Referencia:** Achitouv, Ixandra (2024). *Inferring financial stock returns correlation from complex network analysis.* arXiv:2407.20380 (29 Jul 2024) + extensión *Signal inference ... phase-ordering kinetics* arXiv:2409.19711 (mismo corpus S&P500 2019–2024, repo https://github.com/Eleo22/RN-Finance).  
**Link:** https://arxiv.org/abs/2407.20380 · https://arxiv.org/abs/2409.19711  
**Código/dataset:** **sí** — repo RN-Finance + datos Yahoo Finance S&P500 (485 stocks, 1258 días 2019-01-01→2024-01-01). Replicable.

| Dimensión | Contenido |
|---|---|
| **Metodología** | Parte del **mismo punto que nuestro RMT**: matriz de correlación de retornos log diarios estandarizados, espectro vs Marchenko-Pastur. Donde nosotros filtramos 5 factores >λ₊ y luego 8 residuales, ellos **separan explícitamente "market modes" vs "noise"** vía eigendecomp y **reconstruyen la correlación con simulación de Geometric Brownian Motion (GBM) correlacionada por propiedades de red**. Red de stocks construida a partir de correlaciones filtradas → métricas: **eigenvector centrality, clustering coefficient, comunidades Louvain**. Simulan GBM: `S^L_t` (correlacionada por Louvain) + `S^M_t` (correlacionada por top centralidad/modes) con `S_t = w·S^L_t + (1-w)·S^M_t`. Comparan espectro simulado vs MP y vs espectro empírico. Segundo paper (2409.19711) añade teoría de campo estocástico (Langevin) para **umbral de detección dentro del bulk** donde PCA falla. |
| **Datos** | S&P500, 485 stocks con historia completa 2019–2024, 1258 cierres Yahoo. Muy cercano a nuestro universo 50 (2019–2026, T=1658→1599 tras rolling 252d). |
| **Modelo sobre la red** | No GNN: GBM correlacionado + centralidad/clustering/Louvain como hiperparámetros de correlación. Enfoque "generativo-explicativo", no predictivo puro. Percolación implícita en umbral MP; centralidad explícita. |
| **Resultados con números** | n_market=12 (criterio top 3% eigenvector centrality + PageRank, λ_market ≥ λ_MP). λ_market reportado: [203.87, 27.13, 21.99, 9.88, 7.63, 5.7, 5.41, 4.79, 4.13, 3.92, 3.82, 3.39, 3.08] — el mayor es orden de magnitud > λ_max MP, análogo a nuestro λ_max=15.4 pero escalado por N=485 vs N=50. **Cualitativo clave:** GBM con solo dos fuentes (market modes + comunidades) **reproduce rasgos del espectro empírico** que MP solo no explica (eigenvalues dentro del bulk pero no sobre la curva). **Aplicación portfolio:** Markowitz con matriz de correlación "market GBM" **supera al Markowitz histórico hasta +50% de retorno en rebalanceo corto (dT ≤ 84 días)**. En dT largos la ventaja se diluye. Segundo paper: tiempo de correlación cae 1–2 órdenes de magnitud al inyectar correlación real vs Wishart puro → detección de señal dentro del bulk. |
| **Evaluación crítica** | **Fortalezas:** diálogo directo con RMT (mismo lenguaje λ₊, MP rescalado, mercado removido), aporta **interpretación** de modos colectivos vía red (qué stocks son hubs), código y datos abiertos, idea de simular correlación vía red es barata y auditable. **Debilidades:** GBM es modelo pobre para retornos (sin vol clustering, sin colas pesadas; Heston/GARCH sería mejor, lo admiten); selección de 12 market modes vía centralidad es heurística (top 3% arbitrario); backtest Markowitz sin costes, sin net exposure constraints, sin test de significancia; no hay GNN moderno, por lo que no compite en predictivo puro. **Replicabilidad:** alta (repo + Yahoo). **Overfitting:** bajo en lo descriptivo, medio en el backtest (in-sample para calibrar w y n_market). **Costo:** trivial (minutos en laptop). |
| **Aplicabilidad a fortress_core** | **Complemento ideal al RMT ya corrido.** Nuestros 8 factores residuales (λ=7.59…1.40 > λ₊=1.385) son análogos a sus market modes residuales. Su método permite **etiquetar qué tickers son hubs** (centralidad) y **qué comunidades Louvain** explican cada factor — exactamente lo que nuestro §3 (clusters C0–C7, H1–H8) hace de forma Ward/argmax, pero con fundamento de red. Piloto sin ledger inmediato: reproducir su pipeline sobre nuestros 50 tickers (correlación → red → Louvain/centralidad → GBM simulado) y comparar espectro simulado vs nuestro espectro residual. Si la simulación reproduce λ=7.59/3.85/…, ganamos interpretabilidad sin tocar el ledger. Luego, testear Markowitz con matriz filtrada por red vs por RMT puro en walk-forward purgado. Ver §5. |

---

### Ficha C — Graph predictivo 2024 con métricas fuertes y dataset analista (no Sun)

**Referencia:** Gorduza, Dragos; Kong, Yaxuan; Dong, Xiaowen; Zohren, Stefan (2024). *Extracting Alpha from Financial Analyst Networks.* arXiv:2410.20597 (27 Oct 2024) + ICAIF '24 (ACM).  
**Link:** https://arxiv.org/abs/2410.20597 · https://doi.org/10.1145/3677052.3698630  
**Código/dataset:** dataset I/B/E/S analyst coverage (co-cobertura = peso arista = nº analistas que cubren ambas firmas), features precio/momentum por firma. Repo no enlazado en preprint (contactar autores); red reproducible desde I/B/E/S o Eikon/Refinitiv.

| Dimensión | Contenido |
|---|---|
| **Metodología** | Red donde **nodos=firmas, arista=analistas en común** (red de atención/información). No es red de participantes humanos directa, pero **proxy de red de atención entre participantes** (analistas como brokers de información). Modelo: **Graph Attention Network (GAT) multi-capa** que aprende a ponderar vecinos en task node-level forecasting (momentum spillover). Compara vs GCN, vs NN sin grafo, vs matriz analista estática (weighted average), vs MACD, vs market long-only. Ablaciones: GAT_corr (red por correlación), GAT_industries (red por industria). |
| **Datos** | US equities, ventana 18 años (incluye crisis 2008), features diarios por firma + matriz analista anual/trimestral. Portfolio long-short decil basado en predicción. |
| **Modelo sobre la red** | GAT (attention sobre aristas), no percolación. Atención permite que la fuerza de la relación analista se adapte en tiempo real (vs peso estático). |
| **Resultados con números** | **GAT-analyst: 29.44% anualizado, Sharpe 4.06, vol 7%, maxDD -6%, MDD 1% del tiempo (2 meses).** Comparativas: NN Sharpe 1.753 / -6.42% DD; MACD 0.672 / -35%; Analyst Matrix (media ponderada estática) 1.83% / Sharpe 0.069 / MDD 51% (peor); Market long-only 6.89% / 0.411 / -39.4%. Ablaciones: GAT_corr Sharpe ~similar pero correlación retornos con GAT-analyst =0.65 (señal distinta); GAT_industries peor. **Costes:** a 2bp todos salvo GAT-analyst/corr/1_layer se vuelven Sharpe negativo; a 5bp todos negativos (GAT-analyst aún mejor que MACD a 0bp). Turnover model-based ~77% vs model-free ~40%. Correlación GAT-analyst vs mercado = **-0.21** (diversificante). |
| **Evaluación crítica** | **Fortalezas:** métricas completas (ret, Sharpe, vol, DD, turnover, correlación, robustez a costes), horizonte largo (18y), ablations que aíslan valor de la red analista vs correlación vs industria, idea económica sólida (atención limitada + difusión lenta de info). **Debilidades:** Sharpe 4.06 es **extremadamente alto** y sugiere (a) universo favorable, (b) sin slippage real, (c) posible look-ahead en construcción de red analista (¿usa cobertura del mismo año que predice?), (d) sin test de significancia múltiple (Deflated Sharpe, PBO). Dataset I/B/E/S es pago y con survivorship bias si no se maneja bien. **Replicabilidad:** media (paper bien descrito, pero sin repo y con dato pago). **Overfitting:** medio-alto para trading real por turnover 77% y sensibilidad a costes (a 5bp Sharpe negativo). **Costo:** entrenamiento GAT modesto, pero backtest 18y con GAT multi-hop es costoso. |
| **Aplicabilidad a fortress_core** | **Red de participantes "de segundo orden"**: en vez de modelar inversores directamente (que no tenemos), modela **canal de atención entre firmas** mediado por analistas, que es observable sin ledger de órdenes. Para fortress_core (50 large-cap US con cobertura analista densa), **construir red analista es factible** (I/B/E/S o incluso scraping de cobertura) y podría generar **señal de momentum spillover** ortogonal a nuestros 8 factores RMT (que son contemporáneos, no predictivos, y su momentum t=1.03 no fue significativo). Complemento natural: usar GAT sobre residuos RMT como features nodales. Piloto sin ledger: construir matriz co-cobertura analista sobre 50 tickers y replicar GAT-analyst simplificado con validación walk-forward purgada (ver §5). |

---

### Ficha D — Paper estructural 2025 útil para entender "trading network" (no Sun, bonus)

**Referencia:** Wu, Xian (2025). *Trading Graph Neural Network (TGNN).* arXiv:2504.07923 (10 Apr 2025).  
**Link:** https://arxiv.org/abs/2504.07923  
**Idea en una línea:** estimación **estructural** (no solo predictiva) del impacto de features de activo, dealer y relación sobre precios en **redes OTC/dealer** con cualquier topología, combinando Simulated Method of Moments + GNN. Supera regresiones con centralidad en redes dispersas (sesgo documentado por Cai 2022). Permite heterogeneidad de bargaining power por par de dealers. Aplicable a bonos, interbancario, crypto P2P. **Relevancia para fortress_core:** si alguna vez modelamos red de dealers/market makers o de contrapartes (no solo correlación de retornos), TGNN da marco estructural con parámetros interpretables (holding cost, bargaining power) vs GAT puramente predictivo. Costo computacional mayor (mapeo de contracción iterativo + SMM). Sin código público a la fecha.

---

## 3. Comparativa RMT (fortress_core) vs Red de participantes

**Nuestro RMT (artefacto `ANALISIS_RMT_8FACTORES_20260830.md`):** N=50, T=1658→1599 (q=0.0313), MP λ₊=1.385, **5 factores >λ₊ en matriz completa (λ_max=15.41 explica 30.8% var, mercado), 8 factores residuales >λ₊ tras remover PC1 (λ_res =7.59,3.85,2.88,2.00,1.74,1.64,1.52,1.40). Loadings 50×8 ya computados, 49.2% var residual / 33.9% var total. Clusters Ward H3 (XOM/CVX), H5 (V/MA) etc. correlacionan con factores. Test momentum sobre factores: t=1.03/0.57 no significativo → estructura existe pero no es explotable con momentum simple.**

| Criterio | RMT (estado actual fortress_core) | Red de participantes (Sun/MONEY/Achitouv/Gorduza/TGNN) | Veredicto para fortress_core |
|---|---|---|---|
| **Qué modela** | Covarianza de retornos estandarizados (rolling 252d), espectro vs ruido MP | Relaciones explícitas: co-tenencia, co-cobertura analista, industria, dealer-dealer | **Complemento**: RMT filtra ruido espectral; red explica *por qué* hay factores (canal económico). |
| **Nodos / aristas** | Implícitos (matriz 50×50) | Explícitos: empresa-empresa, analista-analista, fondo-fondo, dealer-dealer | Red añade interpretabilidad (hubs, comunidades) que RMT solo sugiere vía loadings. |
| **Supuestos** | Retornos iid para MP, ventana larga, estandarización | Grafo/hipergrafo con features auxiliares (industria, holdings, cobertura) | Red introduce supuestos de construcción de aristas (thresholds, ventana) → nuevo hiperparámetro. |
| **Señal predictiva probada** | No: momentum sobre 8 factores no significativo (IC t<1.1) | MONEY: clasificación 3 clases con F1 mejor que SOTA; Gorduza: Sharpe 4.06 (pero con costes cae); Achitouv: +50% cartera Markowitz filtrada por red (corto plazo) | **Red no es automáticamente mejor**: necesita walk-forward puro para creer Sharpe/IR. RMT es más conservador (describe, no promete alpha). |
| **Replicabilidad / costo** | **Alta**, ya corrido, artefactos `rmt_mp_*.txt`, `rmt_loadings_8factors.csv`, script `diagnose_rmt_mp.py:30-56` | Media-alta (Achitouv con repo, MONEY sin repo, Gorduza con dato pago) | RMT ya es baseline gratis; red requiere construir grafo y validar sin leakage. |
| **Riesgo de overfitting / leakage** | Bajo (filtrado espectral, sin look-ahead más allá de rolling) | Medio-alto (hiperaristas con holdings contemporáneos, atención GAT que puede memorizar) | **Red debe usarse con purga/embargo** y embargo de holdings (usar solo t-1). |
| **Costo computacional** | O(N³) eig 50×50 trivial (<1s) | GCN/HGCN/GAT ~ O(E) por época, entrenable en minutos-horas | Red es más cara pero no prohibitiva para N=50. |
| **Dato requerido** | Solo precios (ya tenemos) | Precios + GICS + 13F holdings o I/B/E/S cobertura (requiere compra o scraping) | **Trade-off**: RMT = solo precio; red = dato externo. |
| **¿Alternativa, complemento o mejora?** | **Base** | **Complemento** (y potencial mejora si la red explica los 8 factores residuales mejor que PCA puro). No sustituye el filtrado MP; se apila encima: RMT filtra → red interpreta/predice sobre residuos. | **No es alternativa pura**; es **complemento con opción a mejora** si en piloto purgado la matriz filtrada por red supera a la filtrada por RMT en Sharpe neto de costes. |

**Trade-offs honestos:**
- Si solo queremos **describir** covarianza: RMT basta (ya lo tenemos, λ₊=1.385, 8 factores).
- Si queremos **interpretar** por qué F0=QQQ vs KO/JNJ o F4=XOM/CVX: red (Louvain/centralidad de Achitouv, hipergrafo industria de MONEY) da nombres y canales.
- Si queremos **predecir**: RMT solo no predice (momentum IC no significativo); red sí promete predictivo pero con mayor riesgo de overfitting y dato pago. Requiere validación con PBO/CSCV y costes.

---

## 4. Conclusión honesta y próximos pasos (sin ledger)

**Conclusión:**
1. **No se encontró paper único "Sun 2024 market participant network"** con coincidencia autor/año/tema 1:1 verificable en fuentes abiertas. Se documenta búsqueda negativa con 14 queries y tabla de Suns descartados. La referencia más cercana con autor Sun es **Zhongtian Sun — MONEY (AI Open 2023, tesis Durham 2024)**, desplazado un año y con nodo=empresa no inversor, pero metodológicamente es red de mercado con GNN/hipergrafo y adversarial.
2. **Los 3 papers más útiles para fortress_core en la misma familia (redes + mercado, 2023–2025) son:** (a) **Achitouv 2024 (RMT+red, con código)** — diálogo directo con nuestro RMT y piloto más barato; (b) **MONEY/Zhongtian Sun 2023/2024** — hipergrafo industria+fondo, idea trasladable a GICS+13F; (c) **Gorduza et al. 2024 (analyst GAT, Sharpe 4.06)** — proxy de red de participantes vía atención, con métricas completas pero dato pago y Sharpe a validar.
3. **Frente a nuestro RMT (50 tickers → 8 factores residuales >λ₊, loadings 50×8):** la red **no es alternativa que invalide el RMT**, es **complemento interpretativo** y **potencial mejora predictiva** si se usa sobre residuos filtrados por MP. Ninguno de los papers aporta evidencia de que una red reemplace el filtrado espectral; todos lo usan o lo asumen.
4. **Ningún paper resuelve el problema de fortress_core tal cual** (50 US large-cap, 2019–2026, régimen VIX, momentum heterogéneo). Todos usan universos mayores (China A-share, S&P500 485, 18y US) y ventanas distintas. Extrapolar Sharpe/IR sin revalidación local sería mala ciencia.

**Próximos pasos — piloto sin ledger (cuando se autorice, NO ahora):**

1. **Piloto Achitouv-replica (1–2 días, sin dato externo):** sobre `backend/data/cache/rmt_mp_*.txt` + `rmt_loadings_8factors.csv`, reconstruir red de correlación residual (threshold o MST), calcular eigenvector centrality / clustering / Louvain, simular GBM correlacionado (w Louvain vs market modes) y comparar espectro simulado vs λ_res=7.59…1.40. Métrica: distancia RMSE entre espectros + etiquetado de hubs por factor. **Sin trading, solo descriptivo.** Si reproduce estructura, ganamos interpretación de F0–F7.

2. **Piloto hipergrafo GICS+ETF (3–5 días, dato público):** construir hipergrafo donde hiper-arista = sector GICS o ETF (SPY, QQQ, XLE, etc.) + co-tenencia 13F simplificada (top holders de los 50). Implementar pipeline MONEY simplificado (GCN→GRU→HGCN) sobre **residuos RMT** (no precios crudos) con validación walk-forward purgada (embargo 20d, mismo que PBO/CSCV). Benchmark: RMT puro vs RMT+red en clasificación 3 clases (rise/steady/fall) y en Markowitz con matriz filtrada. **Sin ledger, solo research.**

3. **Piloto analista (opcional, si hay acceso I/B/E/S o proxy):** construir matriz co-cobertura analista para los 50 tickers (peso = nº analistas en común último año) y entrenar GAT 2-capas sobre features de momentum residual + red analista. Validación con costes 0/2/5bp como en Gorduza. Si Sharpe neto <1.5 o correlación con RMT >0.6, descartar.

4. **Criterio de éxito pre-registrado (antes de correr):** mejora de **F1 +1.5%** o **Sharpe neto +0.3** vs baseline RMT en OOS purgado, con test Diebold-Mariano o Deflated Sharpe p<0.05, y turnover <100%. Si no se cumple, revertir (doctrina ONBOARDING: rigor solo sobre veredicto).

**No avanzar al piloto expandido hasta autorización explícita** — este hito termina con el `.md`.

---

## 5. Trazabilidad — queries, fuentes y artefactos

**Queries websearch ejecutadas (deep, 10 hits c/u):**
1. `Sun 2024 market participant network model`
2. `investor network Sun 2024 graph neural network market`
3. `trading network model Sun 2024 participants relations`
4. `arXiv Sun 2024 investor network graph neural network stock`
5. `Yi Sun OR Xin Sun 2024 investor network trading network market microstructure`
6. `site:arxiv.org Sun 2024 network participants market participant`
7. `arXiv Sun 2024 correlation network stock market random matrix`
8. `Sun 2024 correlation network stock market GNN investor trading`
9. `Sun 2024 financial network systemic risk interbank trading network model`
10. `Zhongtian Sun 2024 hypergraph stock prediction MONEY`
11. `Sun Y 2024 network market participants GNN percolation centrality`
12. `Sun 2024 network market participants GNN percolation centrality` (reintento)
13. `Sun 2024 financial network systemic risk` (variante)
14. Exploración adicional sobre `Achitouv 2024`, `Wu TGNN 2025`, `Gorduza analyst 2024` para fichas complementarias.

**Fuentes primarias consultadas (con highlights leídos):**
- arXiv:2407.20380 (Achitouv), 2409.19711 (k Kinetics), 2410.20597 (Gorduza), 2504.07923 (Wu TGNN), 2402.06633 (MDGNN Qian), 2401.01846 (DGDNN), 2404.07223 (PfoTGNRec), cond-mat/0401300 (Mantegna review), physics/0505074 (Kwapien), 0709.2209 (Eom et al. RMT+MST)
- ScienceDirect: `Investment network and systemic risk` (2024-04), `Sun LBF 2024 graph autoencoder` (Expert Syst Appl)
- SSRN: `Tao Sun tail risk network` (4711146), `Baltakys et al. investor GNN` (4163635), `Xuchu Sun microstructure` (5046683)
- Springer: `Applied Network Science 2024-08 business network`, `EPJ Data Science crypto co-investment 2024-02`, `Decentralized pure exchange on networks 2024-08`
- Durham e-thesis 15307 (Zhongtian Sun 2024), AI Open 4 (MONEY 2023), ACM ICAIF'24 (Gorduza)
- LinkedIn / scholar para desambiguación de Suns (Yuxin Sun quant-ohlcv-features, Yi Sun, Xin Sun, Yongjiao Sun)

**Artefactos fortress_core verificados (solo lectura):**
- `ANALISIS_RMT_8FACTORES_20260830.md` (50×8 loadings, λ₊=1.385, 8 factores >λ₊, clusters Ward)
- `backend/data/cache/rmt_mp_20260811_150849.txt`, `rmt_loadings_8factors.csv`, `rmt_factor_scores_8factors.csv`, `sector_clusters_20260811_170235.txt`, `diagnose_rmt_mp.py:30-56`

**Reproducibilidad de este informe:** todo DOI/arXiv es verificable; búsquedas son re-ejecutables; no se usó LLM para inventar referencias. Si un paper Sun 2024 exacto existe fuera de índices abiertos (conferencia cerrada, working paper no indexado), no fue hallable con estas herramientas y se declara como tal.

---

## 6. Referencias completas (formato cita)

- Sun, Z., Harit, A., Cristea, A. I., Wang, J., & Lió, P. (2023). MONEY: Ensemble learning for stock price movement prediction via a convolutional network with adversarial hypergraph model. *AI Open*, 4, 165–174. https://doi.org/10.1016/j.aiopen.2023.10.002
- Sun, Z. (2024). *Robustness, Heterogeneity and Structure Capturing for Graph Representation Learning and its Application* (Doctoral thesis, Durham University). https://etheses.dur.ac.uk/15307/
- Achitouv, I. (2024). Inferring financial stock returns correlation from complex network analysis. *arXiv:2407.20380*. https://arxiv.org/abs/2407.20380 — code: https://github.com/Eleo22/RN-Finance
- Achitouv, I. et al. (2024). Signal inference in financial stock return correlations through phase-ordering kinetics in the quenched regime. *arXiv:2409.19711*. https://arxiv.org/abs/2409.19711
- Gorduza, D., Kong, Y., Dong, X., & Zohren, S. (2024). Extracting Alpha from Financial Analyst Networks. *arXiv:2410.20597*; *Proc. ACM ICAIF '24*. https://arxiv.org/abs/2410.20597 — doi:10.1145/3677052.3698630
- Wu, X. (2025). Trading Graph Neural Network. *arXiv:2504.07923*. https://arxiv.org/abs/2504.07923
- Qian, H. et al. (2024). MDGNN: Multi-Relational Dynamic Graph Neural Network. *AAAI 2024*. https://doi.org/10.1609/aaai.v38i13.29381 — arXiv:2402.06633
- Capponi, A., Sun, X., & Yao, D. D. (2020). A Dynamic Network Model of Interbank Lending. *Mathematics of Operations Research*. https://doi.org/10.1287/moor.2019.1025 (Xu Sun — 2020, no 2024)
- Sun, T. (2024). Systemic Risk of SIFIs in the Post-2008 Era: A Tail Risk Network Approach. *SSRN 4711146*. https://doi.org/10.2139/ssrn.4711146
- Wang, Y. & Cao, C. (2024). Do manager networks affect capital market efficiency? *Business Research* https://doi.org/10.1016/j.bir.2024.02.011
- Xu, Z. et al. (2024). Institutional Investor Information Networks and Stock Price Synchronicity. *Emerging Markets Finance and Trade* https://doi.org/10.1080/1540496x.2024.2354803

---

## 7. Verificación git y cierre de hito

```bash
# Ejecutado 2026-09-02:
rtk git status --short
# Esperado:  ?? BIBLIOGRAFIA_SUN_2024.md   (solo este archivo untracked)
# No se modificó código, ledger ni artefactos RMT.
```

**Estado del hito:** ✅ **Completo — investigación bibliográfica entregada.** No se avanza al piloto expandido hasta autorización. Hallazgo guardado en engram `boris` si relevante (ver memoria).

*Fin del informe — 2026-09-02.*
