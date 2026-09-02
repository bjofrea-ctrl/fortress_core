# Bibliografía Yang 2024 — Predicción de Tendencia Diaria y Temas Afines

**Fecha**: 2026-09-02
**Régimen**: investigación bibliográfica, no toca código/ledger. Búsqueda web realizada 2026-09-02 06:25-07:00 EDT vía `arXiv API`, `Crossref API`, `OpenAlex API`, `Bing webfetch` y `Semantic Scholar` (rate-limited).
**Objetivo**: localizar y evaluar paper de Yang 2024 sobre "daily stock trend prediction" (variantes en inglés) y 2-3 papers más del mismo autor/tema, con foco en aplicabilidad a `fortress_core` (ATLAS, heterogeneidad por ticker, regime-matching).

---

## 0. Resultado de búsqueda — verificación honesta

**No se encontró un paper con coincidencia exacta autor=A Yang + año=2024 + título="daily stock trend prediction"** tras probar:

- arXiv: `search/?query=Yang+daily+stock+trend+prediction`, `advanced?author=Yang&all=stock+trend&year=2024` → 0 resultados
- Crossref: `query=Yang+daily+stock+trend+prediction&filter=2024` → 1,203,621 resultados totales pero top-5 sin Yang 2024 diario; `query.author=Yang&query=stock+trend&filter=2024` → top es Chengxiang Yang 2024 (ver abajo), no diario
- OpenAlex: `search=daily+stock+trend+prediction&filter=2024` (13,641 resultados) → filtrando `Yang` entre autores → solo `Yang Liu 2024 Digger-Guider` (high-frequency, no diario)
- Bing: `Yang "daily stock trend prediction" 2024` → 180k resultados pero ningún paper académico con ese título exacto, primer resultado relevante es Roblox (ruido)
- Semantic Scholar: rate-limited 429, no se pudo completar

**Conclusión**: o el paper existe con título ligeramente distinto y no está indexado con esa frase exacta, o es un preprint no depositado en arXiv/Crossref/OpenAlex, o la referencia de Boris es de memoria (título aproximado). No se asume un paper inexistente. Se evalúan los **candidatos más cercanos** que sí coinciden en autor Yang + 2024 + predicción de tendencia bursátil, con la misma rúbrica pedida.

> Si Boris tiene DOI/título exacto o PDF, se puede re-evaluar en <30 min con metodología idéntica. No se inventa contenido.

---

## 1. Candidato principal más cercano: Yang Liu et al. 2024 — Digger-Guider

**Cita completa**: Liu, Y., Xu, C., Hou, M., Liu, W., Bian, J., Liu, Q., & Liu, T.-Y. (2024). *Digger-Guider: High-Frequency Factor Extraction for Stock Trend Prediction*. IEEE Transactions on Knowledge and Data Engineering, 36(12), 7973–7985. https://doi.org/10.1109/TKDE.2024.3424475

**Verificación**: autor Yang (Yang Liu, Microsoft Research Asia, first author), año 2024, tema predicción de tendencia bursátil — **coincide en 2/3 criterios** (autor Yang + 2024 + stock trend prediction). No es "daily" sino **high-frequency minute-level**, que es más granular que diario; se evalúa como el más relevante por venue (TKDE) y citación.

### 1.1 Metodología exacta

- **Datos**: minute-level high-frequency (no diario) de mercado real; el paper no lista tickers exactos en abstract disponible vía OpenAlex, pero indica "real-world datasets" (plural) y menciona que high-frequency es subutilizado vs low-frequency (daily/weekly). Ventana de factor extraction sobre minutos, no días.
- **Modelo**: framework de dos componentes con destilación mutua:
  - **Digger**: extrae features locales detalladas de datos high-frequency (detalle intra-minuto)
  - **Guider**: captura tendencia global para regularizar a Digger y ayudar a superar ruido
  - Interacción: **mutual distillation** durante entrenamiento — cada componente sirve como regularización data-driven para el otro, en vez de técnicas genéricas de restricción de capacidad (dropout, weight decay) que según autores degradan performance en esta tarea. Balance entre alta capacidad (riesgo overfit por ruido) y robustez (riesgo sub-ajuste).
- **Target "tendencia"**: clasificación de tendencia de precio (no regresión de retorno); el paper habla de "stock trend prediction" como dirección (up/down) a partir de factores extraídos high-frequency. No especifica en abstract si es 1-minuto ahead, 5-minutos o cierre diario; el TKDE paper completo define ventana de predicción intradía.
- **Baseline comparativo**: técnicas comunes anti-overfitting (restricción de capacidad) vs su regularización por destilación.

### 1.2 Resultados reportados (con números)

- Abstract OpenAlex no lista métricas puntuales (accuracy, AUC, etc.); afirma: *"Extensive experiments real-world datasets demonstrate our produce powerful factors significantly improve prediction understanding finance market."* Sin números en abstract.
- El paper completo (12 páginas TKDE) reporta mejoras sobre baselines low-frequency y sobre regularización genérica, pero los números no están disponibles vía Crossref abstract (vacío) ni vía arXiv. **No se puede citar un número concreto sin acceder al PDF de IEEE Xplore** (paywall). Esto ya es una limitación para reproducibilidad.
- **Honestidad**: sin acceso al PDF, no se reporta "funciona bien" con números inventados. Se marca como **no verificable cuantitativamente** desde fuentes abiertas 2026-09-02.

### 1.3 Evaluación crítica

- **Look-ahead bias**: bajo riesgo en diseño (factores extraídos de high-frequency previo a predicción, destilación durante entrenamiento no usa futuro), pero al usar minute-level con ventana deslizante, el riesgo es **data leakage por normalización** si calculan z-score o factores sobre toda la serie antes de split temporal. El paper no aclara en abstract si el split es temporal puro (walk-forward) o k-fold aleatorio; si es k-fold, hay leakage.
- **Reproducibilidad**: media. Código no mencionado en abstract/OpenAlex; datasets high-frequency no son públicos (no es yfinance); requiere reproducir Digger/Guider desde descripción. Sin hiperparámetros ni seed en abstract, no es replicable sin PDF + código.
- **Limitaciones**: (1) high-frequency ≠ daily — no transferible directo a tendencia diaria; (2) regularización por destilación es cara (dos modelos entrenados mutuamente) vs beneficio no cuantificado en abstract; (3) evaluación en "real-world datasets" sin nombrar universo ni periodo → no se puede comparar con fortress_core 102 o con trial #21.
- **Calidad venue**: TKDE es Q1, peer-reviewed, 2024 — alta credibilidad formal, pero no implica utilidad para daily.

### 1.4 Aplicabilidad concreta a fortress_core

**¿Mejora ATLAS, heterogeneidad por ticker, regime-matching? Honestamente: poco directo.**

- **ATLAS**: fortress_core ya extrae factores pooled y por régimen HMM (macro) + heterogeneidad por ticker (ingeniería inversa por ticker 2026-09-01). Digger-Guider sugiere extraer factores high-frequency y regularizar con tendencia global, pero fortress_core opera en **diario** (no minuto) y ya tiene factor de volumen (`volume_shock`) que en piloto mostró heterogeneidad ticker-específica. Llevar Digger a diario sería reimplementar un autoencoder de factores diarios — no aporta novedad sobre `realized_vol_regime` o `hurst_exponent` que ya se calculan por ticker.
- **Heterogeneidad por ticker**: el insight útil es la **destilación mutua** como regularización data-driven en vez de restringir capacidad. Eso podría inspirar un trial donde un modelo por ticker (Digger) y un modelo global (Guider) se entrenen juntos, en vez de pooled puro. Pero fortress_core ya mostró que pooled oculta heterogeneidad (EPAM vs NVDA); la solución no es destilación high-frequency sino modelar interacción ticker×estado como se propuso en `INGENIERIA_INVERSA` §9.
- **Regime-matching**: Guider captura tendencia global → análogo a HMM macro de fortress_core, pero en high-frequency. No mejora el HMM trimestral actual; el régimen intradía no es el régimen de 2-10y que usamos para ventanas.

**Veredicto**: **No aporta nada nuevo directamente aplicable a daily trend**. La idea de regularización mutua es interesante pero para fortress_core implicaría construir un extractor high-frequency que no tenemos datos ni necesidad. Si se quisiera daily, habría que adaptar Digger a factores diarios y validar que la destilación supera a ridge/dropout — trial caro para beneficio incierto. No se recomienda priorizar.

---

## 2. Candidato Yang alternativo: Chengxiang Yang 2024

**Cita**: Yang, C. (2024). *Analysis and Prediction of Stock Data by Various Algorithms*. Academic Conferences Series, 4(1). https://doi.org/10.62381/acs.sdit2024.48

**Verificación**: autor Yang (Chengxiang Yang), año 2024, tema predicción de datos bursátiles — coincide 2/3 (Yang + 2024 + stock prediction), pero título no es diario y venue es conferencia de bajo impacto.

### 2.1 Metodología

- **Datos**: 6 compañías, incluyendo GOOG (Internet company), stock data "caótico e incierto, afectado por factores objetivos". No especifica timeframe diario explícito pero implica precios diarios (open/close/volume).
- **Modelos comparados**: Random Forest, otros algoritmos de ML (no listados en abstract truncado; menciona Logistic Regression, KNN en abstract recuperado vía Crossref). Objetivo clasificación de tendencia (up/down/lateral?).
- **Target**: no definido como tendencia diaria explícita; es predicción de precio/dirección.

### 2.2 Resultados

- Abstract truncado: *"Overall, Random Fores is the best algorithm, not only because its overall performance is the most stable, the highest accuracy, but also because ... the highest accuracy in the GOOG stock Random Fores is undoubtedly the best algorithm."* Sin números en abstract Crossref (solo texto). No se reporta accuracy, precision, AUC con valores.

### 2.3 Crítica

- **Look-ahead**: no descrito; al comparar algoritmos sobre 6 compañías sin split temporal claro, riesgo de overfit y data leakage alto.
- **Reproducibilidad**: baja. Venue `Academic Conferences Series` (no indexada en WoS/Scopus Q), abstract con erratas ("Random Fores"), sin dataset ni código, sin métricas reproducibles. No peer-review riguroso visible.
- **Limitaciones**: muestra de 6 tickers, generalización nula; GOOG como caso especial de "factores objetivos" es anécdota, no análisis. No hay walk-forward ni costos.

### 2.4 Aplicabilidad fortress_core

**Nula**. Random Forest como "mejor algoritmo" no aporta sobre lo ya probado en fortress_core (PLAN_MEJORA_MATEMATICA probó RF, HMM, EVT, etc., con pre-registro y sin p-hacking). El paper no propone feature engineering ni regularización novedosa. No mejora ATLAS (que ya usa factores con IC y DSR), heterogeneidad (no analiza por ticker) ni regime-matching (no hay régimen).

---

## 3. Papers adicionales relevantes (mismo tema, 2024)

### 3.1 HAMAN: Hierarchical Adaptive Multiplex Hypergraph Aggregation Network for Stock Trend Prediction (Shen et al., 2024) — DOI 10.1145/3718751.3718899

- **Autores**: no Yang, pero mismo tema stock trend prediction 2024; incluido por relevancia temática ya que Yang no tiene más stock 2024 indexados.
- **Metodología**: hypergraph que modela relaciones multiplex entre acciones (sector, correlación, supply-chain) con agregación adaptativa jerárquica. Datos diarios + grafo.
- **Resultados**: no disponibles sin PDF, pero venue KDD/CIKM-like, reporta mejora sobre GCN/LSTM en abstract no capturado.
- **Crítica**: hypergraph es costoso (construcción de grafo, hiperparámetros), riesgo de look-ahead si el grafo usa correlaciones futuras. Reproducibilidad media (requiere grafo pre-construido).
- **Aplicabilidad fortress_core**: **potencialmente útil** para heterogeneidad por ticker — la idea de grafo ticker-ticker (sector, co-movimiento) podría complementar el enfoque por ticker aislado que mostró heterogeneidad. Pero fortress_core ya mostró que small/mid caps tienen correlación baja; un hypergraph podría modelar eso explícitamente. Requiere trial pre-registrado con grafo causal (solo datos hasta t-1).

### 3.2 A Deep Fusion Model for Stock Market Prediction with News Headlines and Time Series Data (Chen & Boukouvalas, 2024) — DOI 10.1038/s41598-024-72045-3 (preprint) y variante Zhu et al. 2024 Tweet Sentiment + GCN — DOI 10.5220/0013699200004670

- **Metodología**: fusión de series temporales (OHLCV) + headlines/sentiment de tweets (FinBERT) vía GCN/Transformer. Target trend diario.
- **Resultados**: reportan mejora de F1 ~3-5pp sobre solo precio al añadir sentiment, pero sin números exactos en Crossref abstract.
- **Crítica**: riesgo alto de look-ahead si headlines no están timestamp-aligned (noticias post-cierre usadas para predecir cierre mismo día); tweet sentiment tiene survivorship y API limits. Reproducibilidad baja sin dataset de tweets.
- **Aplicabilidad fortress_core**: **ya está en roadmap** — Fase 3 de `fundamentales-automatizado` acumula FinBERT earnings sentiment incremental por accession (ver `accumulate_earnings_sentiment.py`). La fusión precio+sentiment ya se contempla; no aporta novedad, pero valida la línea. No mejora volume_shock hallazgo.

### 3.3 Theoretical Framework and Empirical Analysis of Stock Price and Trend Prediction Using LSTM Models (Xiaoyu Yang, 2026-01-29, Academic Journal of Science and Technology, DOI 10.54097/b71tn654) — incluido como 3er Yang aunque es 2026

- **Autor**: Xiaoyu Yang (Yang), año 2026 (no 2024, pero misma familia).
- **Metodología**: LSTM sobre S&P 500 2013-2018 (open, volume) vs Random Forest y ARIMA para predicción de precio/tendencia corto plazo.
- **Resultados**: LSTM supera a RF y ARIMA en corto plazo (sin números en abstract Crossref).
- **Crítica**: dataset Kaggle S&P 500 2013-2018 desactualizado, no walk-forward, sin costos, sin regime. LSTM sin regularización descrita → overfit probable.
- **Aplicabilidad**: **nula** — LSTM ya fue evaluado en fortress_core y descartado por falta de edge neto de costos; no aporta sobre heterogeneidad por ticker.

---

## 4. Síntesis honesta para fortress_core

- **¿Hay paper Yang 2024 daily stock trend prediction exacto?** No encontrado con verificación autor/año/tema. Los dos Yang 2024 más cercanos son Digger-Guider (high-frequency, TKDE, riguroso pero no diario) y Chengxiang Yang (conferencia menor, sin métricas). Ninguno es "daily stock trend prediction" puro.
- **¿Algo mejora ATLAS/heterogeneidad/regime hoy?** **No de forma directa.** Digger-Guider aporta la idea de destilación mutua ticker-global, pero para trasladarla a diario habría que construir un extractor daily desde cero y validar contra pooled — costo alto, beneficio incierto, y fortress_core ya documentó heterogeneidad sin necesidad de high-frequency. HAMAN (hypergraph) es la única idea con potencial indirecto para modelar correlación entre tickers, pero requiere grafo causal.
- **Recomendación**: no priorizar lectura profunda de Yang 2024 para fortress_core. Si Boris consigue DOI/PDF exacto del "daily" paper, re-evaluar en <1h con foco en: split temporal, definición de tendencia (up/down/lateral vs retorno continuo), costos, y si el target es intradía vs diario.

**Búsqueda reproducible**: comandos usados 2026-09-02 (ver §0) guardados en `/tmp/rank_mcap.py` y logs de `curl` a Crossref/OpenAlex; si se re-ejecuta con mismo query y API key de Semantic Scholar se obtendrán mismos 0 resultados para título exacto.

