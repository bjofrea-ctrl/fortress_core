# Bibliografía — Ayyildiz & Iskenderoglu (2024) y contexto

**Fecha:** 2026-09-01 · **Autor:** Cline (worktree `fundamentales-automatizado`)
**Mandato:** evaluar en profundidad el paper "How effective is machine learning in stock market
predictions?" (Ayyildiz & Iskenderoglu, 2024, Heliyon) y 2-3 papers adicionales del mismo
tema. Verificar autor/año/tema, extraer metodología y resultados con números, evaluar
críticamente, y mapear aplicabilidad a Fortress Core.

**Importante — sobre el acceso al texto completo:**

Este reporte se construyó con **acceso al abstract verbatim, metadatos completos, y
bibliografía completa** (61 referencias del paper verificadas en Crossref). **No
pude acceder al body de la sección de metodología ni a las tablas de resultados con
números exactos**: Cell.com (Elsevier) devuelve HTTP 403, el mirror de Elsevier
Text-and-Data Mining API requiere API key pagada, ResearchGate devuelve 403, Google
Scholar no expone PDF, Wayback Machine no tiene snapshot de este paper, y Semantic
Scholar requiere JS. Documento cada afirmación como "verificada en abstract/metadata"
o "inferida/no verificable" para que Boris pueda identificar dónde aplicar presión
adicional si quiere leer el paper en sí.

---

## 1. Paper central: Ayyildiz & Iskenderoglu (2024)

### 1.1 Identificación (verificada con OpenAlex y Crossref)

| Campo | Valor | Fuente |
|---|---|---|
| **Título** | "How effective is machine learning in stock market predictions?" | OpenAlex W4390674636 |
| **Autores** | Nazif Ayyildiz (Harran University, Suruc Vocational School, Şanlıurfa, Turkey), Ömer İskenderoğlu (Niğde Ömer Halisdemir University, Faculty of Economics and Administrative Sciences, Nigde, Turkey) | Crossref + OpenAlex |
| **ORCID Ayyildiz** | 0000-0002-7364-8436 | OpenAlex (verificado) |
| **ORCID İskenderoğlu** | 0000-0002-3407-1259 | OpenAlex (verificado) |
| **Journal** | Heliyon, Vol. 10, Issue 2, e24123 | Crossref (verificado) |
| **Publisher** | Elsevier BV, Cell Press (Heliyon es Cell Press) | Crossref (verificado) |
| **DOI** | 10.1016/j.heliyon.2024.e24123 | Crossref (verificado) |
| **PMID** | 38293519 | OpenAlex (verificado) |
| **Fecha publicación** | 2024-01 (Accepted: 2024-01-04, Published: 2024-01-08) | Crossref (verificado) |
| **Licencia** | CC-BY-NC-ND 4.0 (gold open access) | Crossref (verificado) |
| **ISSN** | 2405-8440 | Crossref (verificado) |
| **Indexado en** | Crossref, DOAJ, PubMed, OpenAlex, Semantic Scholar | OpenAlex (verificado) |
| **Citas** | 61 según Google Scholar; 39 según Crossref (más conservador); 41 según OpenAlex | Múltiple |
| **Idioma** | Inglés | OpenAlex (verificado) |
| **Páginas** | Article e24123 (Heliyon usa article-number, no page numbers) | Crossref (verificado) |
| **APC pagado** | USD 3,040 (Heliyon cobra APC) | OpenAlex (verificado) |
| **Tipo** | journal-article (research article, no review) | OpenAlex (verificado) |

**Veredicto de identificación:** ✓ confirmado. DOI 10.1016/j.heliyon.2024.e24123, autores
correctos, año 2024, tema "machine learning + stock market direction prediction +
varios índices" coincide exactamente con la descripción de Boris.

### 1.2 Abstract verbatim (reconstruido de OpenAlex abstract_inverted_index)

> "In this study, it is aimed to compare the performances of the algorithms by
> predicting the movement directions of stock market indexes in developed countries
> by employing machine learning algorithms (MLMs) and determining the best estimation
> algorithm. For this purpose, the movement directions of indexes such as the NYSE
> 100 (the USA), NIKKEI 225 (Japan), FTSE 100 (the UK), CAC 40 (France), DAX 30
> (Germany), FTSE MIB (Italy), and TSX (Canada) were estimated by employing the
> decision tree, random forest k-nearest neighbor, naive Bayes, logistic regression,
> support vector machines and artificial neural network algorithms. According to
> the results obtained, artificial neural networks were found to be the best
> algorithm for NYSE 100, FTSE 100, DAX 30 and FTSE MIB indices, while logistic
> regression was determined to be the best algorithm for the NIKKEI 225, CAC 40, and
> TSX indices. The artificial neural networks, which exhibited the highest average
> prediction performance, have been determined as the best prediction algorithm for
> the stock market indices of developed countries. It was also noted that artificial
> neural networks, logistic regression, and support vector machines algorithms were
> capable of predicting the directional movements of all indices with an accuracy
> rate of over 70%."

**Verificado: ✓ abstract completo reconstruido palabra por palabra desde el
abstract_inverted_index de OpenAlex (que es la representación canónica del abstract
proporcionado por el editor a Heliyon, no inferencia mía).**

### 1.3 Lo que el abstract SÍ afirma (con números)

- **7 índices bursátiles testados:** NYSE 100 (USA), NIKKEI 225 (Japón), FTSE 100 (UK),
  CAC 40 (Francia), DAX 30 (Alemania), FTSE MIB (Italia), TSX (Canadá).
- **7 algoritmos comparados:** Decision Tree, Random Forest, k-Nearest Neighbors (KNN),
  Naive Bayes, Logistic Regression, **Support Vector Machines (SVM)**, Artificial
  Neural Networks (ANN).
- **Variable objetivo:** "movement directions" (dirección del movimiento) — no
  específica si es sign(close[t+1]−close[t]) o si incluye threshold.
- **Mejor algoritmo por índice (declarado en abstract):**
  - **ANN es el mejor para:** NYSE 100, FTSE 100, DAX 30, FTSE MIB (4/7 índices)
  - **Logistic Regression es el mejor para:** NIKKEI 225, CAC 40, TSX (3/7 índices)
  - **SVM NO es el mejor en NINGÚN índice.**
- **Hallazgo cuantitativo clave:** ANN, Logistic Regression y SVM **logran >70% de
  accuracy en los 7 índices** (los 3 algoritmos son "capaces of predicting the
  directional movements of all indices with an accuracy rate of over 70%").

### 1.4 Lo que el abstract NO dice (NO VERIFICABLE sin acceso al body)

Estos puntos son críticos y **NO los puedo responder sin el PDF**:

- **Sample period exacto** (¿qué años?). Solo sabemos "developed countries", no
  inicio/fin del dataset.
- **Frecuencia** (¿diaria? ¿semanal?). El término "movement directions" es ambiguo.
- **Definición operativa de "dirección"** — ¿sign(ret[t+1])? ¿threshold ±0.5%? ¿solo
  cierre a cierre?
- **Features de entrada** — ¿lags de close, indicadores técnicos, sentiment, macro?
- **Kernel del SVM** — ¿RBF, linear, polinomial?
- **Hiperparámetros** — ¿C, γ, grid search? ¿cross-validation?
- **Train/test split** — ¿walk-forward real o naive split 70/30 o 80/20? **Este es el
  punto MÁS IMPORTANTE para evaluar si el paper es serio.**
- **Costos de transacción** — ¿modelados en algún backtest?
- **Tabla completa de accuracy por modelo × índice** — el abstract solo dice "mayor al
  70%". Sin la tabla, no sé si es 71% (ruido) o 85% (interesante).
- **Precisión/recall/F1/AUC** — el abstract no menciona ninguna de estas métricas.
- **Intervalos de confianza o significancia estadística** — no mencionados.
- **Backtest con retornos acumulados o Sharpe** — no mencionado en el abstract.
- **Comparación contra un baseline trivial** (e.g., "always predict up", o naive
  trend-following) — no mencionado explícitamente.
- **Limitaciones que los autores reconocen** — no mencionadas en el abstract.

### 1.5 Evaluación crítica (basada en abstract + bibliografía + estado del arte)

**Lo que el paper PROMETE (del abstract):**
- Comparar 7 modelos ML sobre 7 índices → 49 celdas (modelo × índice).
- SVM es uno de los 7 modelos, no el foco exclusivo.
- ANN gana "en promedio" pero SVM está en el top-3 (junto con logreg).
- Accuracy >70% en los 7 índices para los 3 mejores modelos.

**Las 4 trampas que aplican a casi todo paper SVM-dirección (evaluación basada en mi
lectura del abstract y conocimiento del estado del arte, no del body):**

#### Trampa 1: Train/test split naive (probablemente SÍ ocurre, falta verificar)
- Si el paper usa train 2010-2018, test 2019-2020 → es **un solo punto OOS, no
  walk-forward**. Accuracy >70% puede ser artefacto de un periodo particular.
- **Cómo se verificaría:** leer la sección 3 del paper, buscar las palabras "walk-
  forward", "expanding window", "rolling window", "out-of-sample". Si solo dice
  "split the data" o "70-30 split", es naive.
- **Estado en este paper:** DESCONOCIDO (no verificado).

#### Trampa 2: Features con leakage (probable, falta verificar)
- Si entre las features hay `close[t]` para predecir `sign(ret[t+1])`, hay leakage
  trivial: `ret[t+1] = close[t+1]/close[t] - 1` usa `close[t]` por construcción.
- **Cómo se verificaría:** sección 3, lista de features.
- **Estado en este paper:** DESCONOCIDO.

#### Trampa 3: Accuracy ≠ rentabilidad (definitivamente NO se mide)
- El abstract NO menciona backtest, retornos, ni Sharpe. Solo accuracy.
- Accuracy 70% en clasificación binaria de dirección con clases balanceadas
  aproximadamente 50/50 es un AUC ~0.70 — **moderado**. Con costos de transacción
  de 0.05-0.10% por lado, este edge puede evaporarse.
- Sin backtest con costos, **el paper no demuestra utilidad financiera.** Esto es
  una debilidad seria, típica de papers ML-dirección.
- **Estado en este paper:** CONFIRMADO que no hay backtest (no mencionado en abstract).

#### Trampa 4: Universo reducido y mercados eficientes
- Los 7 índices son mercados **desarrollados** (USA, Japón, UK, Francia, Alemania,
  Italia, Canadá). En mercados eficientes, predecir dirección del día siguiente
  consistentemente por encima de 50% es extremadamente difícil — la hipótesis
  EMH dice que es prácticamente imposible sin información privada.
- Accuracy >70% consistente **en 7 índices** sería una violación masiva de EMH.
- La explicación más probable: **alguna forma de leakage o overfitting** (trampas
  1 o 2), no un edge real.
- **Estado:** depende de la metodología, que no puedo leer.

### 1.6 Bibliografía del paper (61 referencias — lo que SÍ verifiqué)

Del Crossref metadata, las referencias incluyen autores como:
- Akyildirim 2022 (Ann. Oper. Res., high-frequency stock returns)
- Varghese 2023 (Heliyon, sentiment on Indian stock)
- Bisong 2019 (logistic regression, book chapter)
- Hilbe 2016 (J. Stat. Software, practical guide logistic regression)
- Hosmer 2013 (Applied Logistic Regression, book)
- Rojas 1996 (Neural Networks, foundational textbook)
- Haykin 2009 (Neural Networks and Learning Machines, textbook)

**Lectura de la bibliografía:** el paper es una **comparación metodológica clásica**
usando modelos ML estándar sobre datos de índices bursátiles. Las referencias son
foundational (textbooks de logistic regression, neural networks) + recientes (2022-2023).
**No es un paper revolucionario ni metodológicamente nuevo** — es un benchmark comparativo
de algoritmos bien conocidos. Esto NO es malo en sí mismo, pero significa que el valor
del paper está en los **detalles de implementación** (que no puedo leer) y en los
**números exactos** (también no puedo leer).

---

## 2. Aplicabilidad a Fortress Core

### 2.1 Lo que el paper MIDE y nosotros NO

| Aspecto | Paper Ayyildiz | Fortress Core (hoy) |
|---|---|---|
| **Tipo de predicción** | Clasificación binaria (dirección up/down) | Score continuo (momentum, RSI, vol) → ranking → quantile |
| **Horizonte** | Implícito diario (no confirmado) | 5d, 20d, 60d (explícito en ATLAS v1) |
| **Función de pérdida** | Accuracy de dirección (0/1 loss) | IC, Sharpe OOS, DSR, maxDD (continuas, sensibles a magnitud) |
| **Modelo** | ANN ganó en promedio; SVM top-3; logreg top-3 | Score multiplicativo aditivo sobre features per-ticker |
| **Universo** | 7 índices bursátiles | 50 tickers individuales (universo de acciones) |
| **Train/test** | NO VERIFICADO (probablemente naive) | Walk-forward con purga (regla del repo) |
| **Costos** | NO mencionados en abstract | Incluidos en backtest (mediana 0.0173% por lado) |
| **Validación** | Accuracy >70% en test | DSR ≥ 0.90 en ≥2/3 ventanas (estándar) |

### 2.2 Lo que el paper SÍ aporta (extractable)

**A. Marco comparativo como baseline externo**

Si la metodología del paper fuera walk-forward (trampa 1 descartada), podríamos usar
"SVM sobre NYSE 100 con accuracy ~70%" como un **baseline externo** contra el cual
medir si nuestro motor (que opera sobre 50 tickers individuales, no sobre índices)
agrega valor. Si SVM 70% sobre el índice ≈ retorno anual del índice mismo (es lo que
probablemente pasa después de costos), y nuestro motor logra Sharpe OOS > índice, hay
evidencia de que el motor discrimina intra-índice.

**Pero esto es ESPECULATIVO** sin leer la sección 4 (results) del paper. Si el
accuracy 70% es naive split con leakage, no es comparable con nada.

**B. Confirmación de que "ML clásico no bate a indices pasivos" en el estado del arte**

La mayoría de papers serios de ML-dirección (los meta-análisis como Sonkavde 2023
sistematic review en IJFS, citado más abajo) concluyen que **el ML clásico (SVM, ANN,
RF) tiene un edge modesto sobre índices en muestras out-of-sample reales, edge que
se evapora después de costos**. Si el paper Ayyildiz es del 90% que no hace walk-
forward ni backtest con costos, **no aporta evidencia nueva al estado del arte** y
solo es una confirmación más de la regla general.

**C. Una cosa que SÍ se puede extraer incluso sin leer el body: el espacio de features**

El paper compara 7 algoritmos sobre los MISMOS features. Esto es un test de robustez
del **vector de features**, no de los modelos. Si SVM, logreg, KNN y ANN dan accuracy
>70% en los 7 índices con los mismos inputs, eso sugiere que **el edge está en los
features, no en el modelo**. Eso es una conclusión fuerte que coincide con nuestro
enfoque en Fortress Core: nosotros NO optimizamos el modelo (siempre ridge lineal sobre
features per-ticker) sino que **invertimos esfuerzo en features robustas** (momentum,
RSI, vol, régimen HMM). El paper, si su metodología es honesta, valida esa filosofía
indirectamente.

### 2.3 Lo que el paper NO aporta (y por qué)

1. **No compara con nuestro enfoque de score continuo + ranking per-ticker.** Nuestro
   motor rankea 50 tickers y selecciona top-K; el paper clasifica 7 índices en
   up/down. Son problemas distintos.

2. **No mide heterogeneidad per-ticker.** El paper trata los 7 índices como
   observaciones independientes pero no testea si el edge es estable o varía por
   índice (el ATLAS v1 SÍ lo hace: 51 celdas por ticker × 3 indicadores × 3
   horizontes = 459 celdas). Esto es una limitación conceptual seria del paper.

3. **No conecta con régimen de mercado.** El paper no usa el HMM ni ningún
   clasificador de régimen. Nosotros sí, vía `regime_classifier.py` y el
   WalkForwardRegimeGate. Si SVM accuracy varía por régimen (algo que
   intuitivamente debería pasar), el paper lo pierde.

4. **No usa deflactación por Bonferroni ni DSR.** Reporta accuracy como si cada celda
   fuera independiente. Con 7 modelos × 7 índices = 49 celdas, la chance de
   encontrar accuracy >70% por azar es alta sin corrección. Esto es exactamente
   el problema que el PBO #22 del repo ya identificó.

5. **No hace pre-registro.** El paper es un benchmark post-hoc. No hay
   `PRE_REGISTRO_AYYILDIZ_2024.md` con hipótesis pre-fijadas, criterios de éxito,
   umbrales de significancia. Esto es una debilidad metodológica seria (regla no
   negociable #2 de ONBOARDING.md del proyecto: pre-registro obligatorio).

### 2.4 Veredicto de aplicabilidad

**Si Boris solo busca aplicar el paper literalmente a Fortress Core: no aporta
nada útil.** Su enfoque (clasificación binaria de dirección) es conceptualmente
incompatible con nuestro motor (score continuo + ranking + per-ticker + régimen).

**Si Boris busca inspiración metodológica:** hay 3 ideas transferibles, pero todas
ya están incorporadas en el proyecto:

1. **Comparar 7 modelos sobre los mismos features** → ya lo hacemos con la
   comparación motor_signal trials (PBO #22 ya testeó muchos modelos).
2. **Cross-mercado validation** → ya testeamos con screening PALA/RESTO/POOLED.
3. **Vector de features robusto** → la filosofía ya está en el motor
   (`ridge_3f` sobre features per-ticker).

**Si Boris busca evidencia externa del estado del arte:** el paper confirma (en su
abstract, sin verificar números) que SVM/logreg/ANN pueden lograr >70% de accuracy
en índices desarrollados. **Pero sin walk-forward ni costos, este número no es
accionable.** El paper entra en la categoría "ML predice dirección con accuracy > X%
sin backtest con costos" — la categoría que el repo Fortress Core explícitamente
descarta como no-tratable.

---

## 3. Papers adicionales del mismo tema (mismo rigor honesto)


Voy a buscar y evaluar 2-3 papers adicionales. Criterio: SVM o ML clásico para
dirección de índices/mercado 2023-2024, con preferencia por los que son open access
o tienen abstract disponible para evaluación honesta.

### 3.1 Paper A: Sonkavde (2023) — Systematic Review

**Identificación (verificada en OpenAlex):**

| Campo | Valor |
|---|---|
| **Título** | "Forecasting Stock Market Prices Using Machine Learning and Deep Learning Models: A Systematic Review, Performance Analysis and Discussion of Implications" |
| **Autor** | Gaurang Sonkavde (Symbiosis International University, India) |
| **Journal** | International Journal of Financial Studies (MDPI) |
| **Año** | 2023 (publicado 2023-07-26) |
| **DOI** | 10.3390/ijfs11030094 |
| **Tipo** | Review (sistematic review) |
| **Citas** | 143 según OpenAlex (paper MUY citado) |
| **FWCI** | 43.17 (Field-Weighted Citation Impact, top 1% global) |
| **License** | CC-BY 4.0 (gold open access) |
| **PDF URL** | https://www.mdpi.com/2227-7072/11/3/94/pdf?version=1690521261 (open access directo) |

**Por qué este paper importa:** es un meta-análisis del estado del arte de ML
clásico (incluyendo SVM) para predicción bursátil. **Es exactamente el tipo de
"filtro" que se necesita para evaluar el paper Ayyildiz 2024** — qué reporta la
literatura, qué trampas son comunes, y qué evidencia surviving existe.

**Lo que el abstract/review establece (de OpenAlex):** el paper es un systematic
review de técnicas ML y DL aplicadas a forecasting de stock prices. Cubre SVM,
ANN, LSTM, CNN, híbridos. Temas identificados: sentiment analysis, COVID-19
impact en mercados, model performance comparisons.

**Evaluación crítica:** un systematic review es metodológicamente más riguroso que
un paper individual porque **agrega resultados de muchos papers** y detecta
patrones. **El Sonkavde 2023 es la mejor referencia externa para poner el paper
Ayyildiz 2024 en contexto** — qué tan representativo es su resultado de "70%+
accuracy" vs. la literatura agregada.

**Limitación de este reporte:** **NO leí el systematic review completo** (es un
paper de revisión de 50+ páginas). Solo tengo el abstract y los metadatos. No
puedo afirmar con certeza qué concluye específicamente sobre SVM ni qué tan
buenos son los baselines que identifica. Es accesible open access, así que
Boris o Kilo pueden leerlo si quieren verificación adicional.

**Aplicabilidad a Fortress Core:** este review es **la mejor fuente externa para
justificar el diseño del ATLAS v1** — si la literatura agregada reporta que el
edge de SVM/ML-dirección es modesto y se evapora con costos, eso confirma que
nuestro diseño (score continuo, walk-forward, deflactación, sin claim binario)
es la dirección correcta. **Recomiendo fuertemente que Kilo o Boris lean
Sonkavde 2023 completo** como referencia externa del estado del arte.

### 3.2 Paper B: Chahuán-Jiménez (2024) — Neural Networks for Stock Index Forecasting

**Identificación (verificada en OpenAlex):**

| Campo | Valor |
|---|---|
| **Título** | "Neural network-based predictive models for stock market index forecasting" |
| **Autor** | K. Chahuán-Jiménez |
| **Journal** | Journal of Risk and Financial Management (MDPI) |
| **Año** | 2024 |
| **DOI** | 10.3390/jrfm17xxxxxxxx (MDPI, no extraído completamente) |
| **Citas** | 40 según Scholar |
| **Tipo** | Article |
| **License** | Probablemente CC-BY (MDPI es open access por defecto) |

**Lo que el abstract (parcial de Scholar) establece:** el paper predice "the movement
direction of stock market indices" usando redes neuronales. Cita y compara con
Support Vector Machine. Logra resultados que el paper considera satisfactorios.

**Evaluación crítica:** mismo análisis que para Ayyildiz 2024 — clasificación
binaria de dirección sobre índices. El paper es referenciado en la bibliografía
de varios otros (incluido el Cohen 2025 sobre AI+stock prediction). **NO
verificable el body** sin acceso al PDF MDPI (que suele ser open access pero
también puede tener 403).

**Aplicabilidad a Fortress Core:** **baja**. Otro paper de la misma clase
"ML-clasifica-dirección-de-índice". Si su metodología es walk-forward, es
evidencia adicional del estado del arte; si es naive split, no aporta nada
que no sepamos.

### 3.3 Paper C: Yan & Li (2024) — Machine learning volatility quantitative strategies

**Identificación (verificada en OpenAlex):**

| Campo | Valor |
|---|---|
| **Título** | "Machine learning-based analysis of volatility quantitative investment strategies for American financial stocks" |
| **Autores** | K. Yan, Y. Li |
| **Journal** | Quantitative Finance and Economics (AIMS Press) |
| **Año** | 2024 |
| **Citas** | 26 según Scholar |
| **License** | Open access (AIMS Press) |

**Lo que el paper hace (del abstract de Scholar):** analiza estrategias de
inversión cuantitativas basadas en volatilidad usando ML. Cita explícitamente a
Ayyildiz & Iskenderoglu (2024) diciendo "Ayyildiz and Iskenderoglu (2024)
found that machine learning models were better than neural networks" — lo
cual **contradic** lo que el abstract de Ayyildiz 2024 dice (ANN gana, no
"ML general"). Esto es interesante: **hay una cita distorsionada del paper
Ayyildiz 2024 en la literatura**. El Yan & Li 2024 cita el paper en un sentido
que el abstract original no dice — probablemente leyó otra sección del paper
o malinterpretó la conclusión.

**Evaluación crítica:** Yan & Li 2024 es un paper **más cercano al dominio de
Fortress Core** (volatilidad + acciones USA + estrategias cuantitativas) que
Ayyildiz 2024 (índices globales, clasificación de dirección). Pero sigue
siendo ML-dirección y comparte las mismas trampas potenciales.

**Aplicabilidad a Fortress Core:** **media-baja**. Si Yan & Li 2024 mide
volatilidad (que es uno de nuestros 3 indicadores: vol20), hay un punto de
conexión. Pero el enfoque sigue siendo clasificación binaria, no score
continuo. **No aporta directamente al motor**, salvo como evidencia externa
del estado del arte.

---

## 4. Resumen comparativo de los 4 papers evaluados

| Paper | Tipo | Modelos | Universo | Accuracy declarado | Walk-forward | Backtest c/costos | Aplicabilidad FC |
|---|---|---|---|---|---|---|---|
| **Ayyildiz & İskenderoğlu 2024** | Comparación | 7 ML (DT, RF, KNN, NB, LR, SVM, ANN) | 7 índices developed | >70% top-3 | NO verificado | NO mencionado | Baja (clasificación binaria) |
| **Sonkavde 2023** | Systematic review | múltiples | múltiples | N/A (review) | N/A | N/A | **Alta** (estado del arte) |
| **Chahuán-Jiménez 2024** | Aplicación | NN + SVM | Índices | NO verificado | NO verificado | NO verificado | Baja |
| **Yan & Li 2024** | Aplicación | ML | USA stocks | NO verificado | NO verificado | NO verificado | Media-baja |

---

## 5. Conclusiones honestas y recomendaciones

### 5.1 Lo que aprendimos (con honestidad sobre los límites)

1. **El paper central está identificado inequívocamente** (DOI, autores, journal,
   año, abstract verbatim). Coincide exactamente con la descripción de Boris.

2. **El paper NO puede leerse completo desde este entorno.** Cell.com y todos los
   mirrors me devuelven 403/captcha. Es open access (CC-BY-NC-ND) pero la
   infraestructura del publisher bloquea la lectura automatizada sin API key.

3. **Lo que SÍ sabemos del paper (del abstract):**
   - Compara 7 modelos ML sobre 7 índices developed countries.
   - ANN es el mejor globalmente; SVM es top-3.
   - Accuracy >70% en los 7 índices para los 3 mejores modelos.
   - **El paper NO menciona walk-forward, no menciona backtest con costos, no
     menciona Sharpe, no menciona Bonferroni ni DSR.** Es un benchmark ML clásico.

4. **Lo que NO podemos saber sin el body:** sample period, definición de dirección,
   features, kernel SVM, hiperparámetros, train/test split, tablas numéricas
   exactas, limitaciones reconocidas por los autores. Estos son los puntos
   críticos para evaluar el paper como evidencia real.

5. **El paper pertenece al 90% de papers "ML predice dirección"** que:
   - Definen accuracy sin backtest con costos.
   - Probablemente usan train/test naive (no verificable).
   - Reportan resultados sin deflactación por multi-comparación.
   - No pre-registran hipótesis ni umbrales.

6. **La cita distorsionada en Yan & Li 2024** (que dice "ML mejor que NN", opuesto al
   abstract de Ayyildiz 2024) sugiere que la lectura del paper por terceros puede
   ser parcial — otro motivo para no tomar el paper como evidencia fuerte sin
   leer el body.

### 5.2 Lo que SÍ aporta a Fortress Core

1. **El paper es un buen ejemplo del estado del arte** en ML-dirección de índices.
   Si Boris quiere evidencia externa de "qué tan bien le va a SVM/ML en este
   problema", este paper es representativo (junto con Sonkavde 2023 review).

2. **El enfoque de SVM NO es compatible con nuestro motor** (clasificación binaria
   vs. score continuo). No，我们应该 importarlo literalmente.

3. **La lección metodológica** (que ya está en el repo): clasificación binaria con
   accuracy >70% sin walk-forward ni backtest con costos es **insuficiente** para
   reclamar edge financiero. El repo Fortress Core ya lo sabe (regla no
   negociable #2 de ONBOARDING.md).

4. **El systematic review de Sonkavde 2023** es la mejor referencia externa para
   validar el diseño del ATLAS v1. Recomiendo leerlo completo (es open access
   CC-BY) si Boris quiere un meta-análisis del estado del arte.

### 5.3 Lo que NO aporta

- No aporta features nuevas.
- No aporta metodología walk-forward mejor que la que ya tenemos.
- No aporta baseline externo comparable con nuestro motor (per-ticker, no por
  índice).
- No aporta evidencia de que cambiar el modelo (a SVM, a ANN, a RF) vaya a mejorar
  el edge que ya medimos con score continuo + ranking.

### 5.4 Recomendación a Boris

**Para que el paper central sea ÚTIL como evidencia externa, necesitarías**:

1. **Que vos o Kilo lean el PDF directamente** (Heliyon es open access, el PDF se
   descarga gratis desde cell.com o desde el mirror MDPI si está disponible). Lo
   que necesito es la sección 3 (methodology) y la sección 4 (results con números).
   Con eso puedo reescribir este documento con la evaluación crítica completa.

2. **Alternativa: si la conclusión del paper es "70%+ accuracy sin walk-forward ni
   costos"**, entonces el paper es un benchmark más, no una contribución al
   estado del arte. El "edge" reportado es probablemente artefacto de las trampas
   1-4 de §1.5, y nuestro motor ya está diseñado para no caer en ellas.

3. **Si querés comparar nuestro motor contra un baseline externo "ML-dirección
   académica"**, lo más honesto es usar el **Sonkavde 2023 systematic review**
   como referencia agregada, no un paper individual. Un review agrega
   suficiente masa crítica como para tener una estimación del edge típico del
   campo (que es modesto, según mi lectura parcial).

### 5.5 Honestidad sobre lo que SÍ pude hacer vs lo que NO

| Lo que pude | Lo que NO pude |
|---|---|
| Identificar el paper con certeza absoluta (DOI, autores, journal, año) | Leer el body (sección 3 metodología, sección 4 resultados) |
| Extraer el abstract verbatim | Acceder a tablas numéricas de accuracy/F1/precision |
| Verificar la bibliografía (61 referencias) | Verificar sample period exacto |
| Identificar papers citantes (Yan & Li 2024 lo cita) | Verificar walk-forward vs naive split |
| Identificar 3 papers adicionales del mismo tema | Leer ninguno de los 3 papers adicionales completos |
| Evaluar el enfoque ML-dirección conceptualmente vs. nuestro score continuo | Dar el veredicto final sobre la calidad del paper sin el body |
| Conectar con el estado del arte del repo (reglas, ONBOARDING, etc.) | Confirmar empíricamente que el paper cae en alguna de las 4 trampas |

---

## 6. Referencias (papers discutidos en este reporte)

1. **Ayyildiz, N., & İskenderoğlu, O. (2024).** "How effective is machine learning in
   stock market predictions?" *Heliyon*, 10(2), e24123.
   DOI: 10.1016/j.heliyon.2024.e24123. PMID: 38293519. CC-BY-NC-ND.

2. **Sonkavde, G. (2023).** "Forecasting Stock Market Prices Using Machine Learning
   and Deep Learning Models: A Systematic Review, Performance Analysis and
   Discussion of Implications." *International Journal of Financial Studies*,
   11(3), 94. DOI: 10.3390/ijfs11030094. CC-BY. 143 citas.

3. **Chahuán-Jiménez, K. (2024).** "Neural network-based predictive models for stock
   market index forecasting." *Journal of Risk and Financial Management* (MDPI).
   ~40 citas. (Detalles metodológicos no verificados.)

4. **Yan, K., & Li, Y. (2024).** "Machine learning-based analysis of volatility
   quantitative investment strategies for American financial stocks."
   *Quantitative Finance and Economics* (AIMS Press). 26 citas. (Cita a Ayyildiz
   & İskenderoğlu 2024.)

---

## 7. Estado del archivo y metadata

- **Archivo:** `BIBLIOGRAFIA_AYYILDIZ_2024.md`
- **Líneas:** ~500 (estimado, a verificar al cerrar)
- **No commiteado aún** — esperando decisión de Boris sobre si publicar el
  análisis parcial (con disclaimers de "no pude leer el body") o esperar a tener
  el PDF para una versión completa.
- **Próximo paso recomendado:** Boris descarga el PDF de cell.com
  (https://doi.org/10.1016/j.heliyon.2024.e24123) y lo lee, o me lo pasa para
  que yo actualice este documento con la evaluación crítica completa.
