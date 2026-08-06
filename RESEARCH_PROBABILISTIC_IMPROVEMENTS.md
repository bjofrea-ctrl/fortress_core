# 🧮 Fortress Core — Evaluación y Mejoras del Modelo Probabilístico

> **Autor**: Cline (asistente IA) + bjofrea-ctrl  
> **Fecha**: 2026-08-06  
> **Enfoque**: Ingeniería matemática y probabilística estilo Jim Simons (Renaissance Technologies)

---

## 1. Diagnóstico del Modelo Probabilístico Actual

### 1.1 Componentes existentes

| Componente | Archivo | Método actual | Debilidad |
|-----------|---------|---------------|-----------|
| Probabilidad de subida | `predictive_engine.py` | Logística simple `1/(1+exp(-k·score))` | k fijo, no calibrado con datos |
| Clasificación de régimen | `regime_classifier.py` | GaussianHMM (4 estados) | Sin memoria de transición, sin vol estocástica |
| Position sizing | `adaptive_risk.py` | Riesgo fijo 1.5% / ATR | No usa Kelly, no adapta a edge |
| Monte Carlo | `backtest_engine.py` | Bootstrap simple de PnLs | No modela colas gruesas ni autocorrelación |
| Aprendizaje PROFESSOR | `advanced_agents.py` | Brier score + accuracy | No recalibra probabilidades |
| Correlaciones macro | `predictive_engine.py` | Pearson 60d | No captura dependencia de colas |
| Score compuesto | `predictive_engine.py` | Pesos fijos por régimen | No se actualizan con evidencia |
| Backtest | `backtest_engine.py` | In-sample | No walk-forward, no out-of-sample |

### 1.2 Métricas actuales del backtest (2019-2024)

```
Sharpe: 0.366 | Sortino: 0.336 | Max DD: -5.37% | PF: 1.52 | Win rate: 28.7%
```

**Diagnóstico**: El sistema es rentable pero el Sharpe es bajo. El win rate de 28.7% con PF 1.52 indica que las ganancias son grandes pero infrecuentes — típico de estrategias de momentum. El modelo probabilístico necesita calibración y mejoras matemáticas.

---

## 2. Mejoras Probabilísticas — Fórmulas Académicas y Experimentales

### 2.1 Calibración de Probabilidades — Platt Scaling + Isotonic Regression

**Problema**: La logística actual `1/(1+exp(-k·score))` usa k fijo (1.8, 1.5, 1.2) sin calibrar.

**Solución**: Platt scaling con parámetros aprendidos + isotonic regression como fallback.

**Fórmula Platt (Platt, 1999)**:
```
P(y=1|x) = 1 / (1 + exp(A·f(x) + B))
```
Donde A y B se optimizan por máxima verosimilitud sobre datos históricos.

**Fórmula Isotonic (Zadrozny & Elkan, 2002)**:
```
P_calibrado = PAV(f(x))  // Pool Adjacent Violators
```

**Implementación**:
```python
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import CalibratedClassifierCV

# Platt scaling con cross-validation
calibrator = CalibratedClassifierCV(base_estimator, method="sigmoid", cv=5)
# Isotonic como alternativa robusta
calibrator_iso = CalibratedClassifierCV(base_estimator, method="isotonic", cv=5)
```

### 2.2 Bayesian Model Averaging (BMA) — Combinación Óptima de Modelos

**Problema**: El score compuesto usa pesos fijos por régimen.

**Solución**: BMA con pesos posteriores actualizados por evidencia.

**Fórmula BMA (Hoeting et al., 1999)**:
```
P(y|D) = Σ_k P(y|M_k, D) · P(M_k|D)

P(M_k|D) ∝ P(D|M_k) · P(M_k)
         = exp(-BIC_k/2) · P(M_k)
```

**BIC (Schwarz, 1978)**:
```
BIC_k = -2·log(L_k) + k·log(n)
```

**Implementación**: Cada categoría de señal (momentum, reversion, fundamental, macro, sentimiento, volatilidad) es un "modelo" con peso posterior actualizado por su Brier score histórico.

### 2.3 Kelly Criterion Fraccional — Position Sizing Óptimo

**Problema**: El position sizing usa riesgo fijo 1.5% sin considerar el edge.

**Solución**: Kelly fraccional (0.25 Kelly) con estimación de edge.

**Fórmula Kelly (Kelly, 1956)**:
```
f* = (p·b - q) / b

Donde:
  p = probabilidad de ganar
  q = 1 - p
  b = ratio ganancia/pérdida (payoff)
```

**Kelly fraccional (Thorp, 2006)**:
```
f_frac = 0.25 · f*  // 25% Kelly para reducir varianza
```

**Con estimación de edge del PROFESSOR**:
```
edge = accuracy_historica - 0.5
f* = edge / (b + 1)
```

### 2.4 Hidden Markov Model con Volatilidad Estocástica (SV-HMM)

**Problema**: El GaussianHMM actual no modela la volatilidad estocástica.

**Solución**: Modelo de Markov Switching con volatilidad GARCH(1,1) en cada estado.

**Fórmula GARCH(1,1) (Bollerslev, 1986)**:
```
σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
```

**Markov Switching (Hamilton, 1989)**:
```
r_t | S_t = μ_{S_t} + ε_t,  ε_t ~ N(0, σ²_{S_t})
P(S_t = j | S_{t-1} = i) = p_ij
```

**Implementación**: Usar `hmmlearn` con `GaussianHMM` pero con features de volatilidad realizada + GARCH residuales.

### 2.5 Cópulas para Dependencia de Colas

**Problema**: Pearson correlation no captura dependencia en colas (crisis).

**Solución**: Cópulas de Clayton y Gumbel para dependencia asimétrica.

**Fórmula Cópula de Clayton (Clayton, 1978)**:
```
C_θ(u,v) = (u^(-θ) + v^(-θ) - 1)^(-1/θ)
```

**Fórmula Cópula de Gumbel (Gumbel, 1960)**:
```
C_θ(u,v) = exp(-[(-ln u)^θ + (-ln v)^θ]^(1/θ))
```

**Tail dependence**:
```
λ_L = 2^(-1/θ)  // Clayton: dependencia de cola inferior
λ_U = 2 - 2^(1/θ)  // Gumbel: dependencia de cola superior
```

**Implementación**: Calcular cópulas entre DXY-Oro, SPY-VIX, etc. para detectar riesgo de cola.

### 2.6 Monte Carlo con Cópulas y Colas Gruesas

**Problema**: El bootstrap simple no modela colas gruesas.

**Solución**: Simulación con distribución t-Student multivariada + cópula.

**Fórmula t-Student multivariada**:
```
X = μ + (√(ν/W)) · Z,  Z ~ N(0, Σ),  W ~ χ²_ν
```

**VaR con Cornish-Fisher (Cornish & Fisher, 1937)**:
```
VaR_α = μ + σ · (z_α + (z_α² - 1)·S/6 + (z_α³ - 3·z_α)·K/24 - (2·z_α³ - 5·z_α)·S²/36)
```

**Expected Shortfall (Acerbi & Tasche, 2002)**:
```
ES_α = E[X | X ≤ VaR_α]
```

### 2.7 Walk-Forward Validation

**Problema**: El backtest es in-sample.

**Solución**: Walk-forward con ventanas de entrenamiento y test.

**Fórmula**:
```
Para cada ventana i:
  Train: [t_i, t_i + train_window]
  Test:  [t_i + train_window, t_i + train_window + test_window]
  Recalibrar pesos y umbrales en train, evaluar en test
```

### 2.8 Ensemble Learning — Stacking de Modelos

**Problema**: Un solo score compuesto.

**Solución**: Stacking con Gradient Boosting + Random Forest + Logistic Regression.

**Fórmula Stacking (Wolpert, 1992)**:
```
y_pred = Σ_k w_k · f_k(x)  // Meta-modelo sobre predicciones base
```

### 2.9 Bayesian Online Learning — Actualización Continua

**Problema**: Los pesos no se actualizan con nueva evidencia.

**Solución**: Actualización Bayesiana online de pesos.

**Fórmula (Bayes, 1763)**:
```
P(θ|D) ∝ P(D|θ) · P(θ)

Posterior ∝ Likelihood × Prior
```

**Conjugate prior para Bernoulli (Beta-Binomial)**:
```
α_new = α_old + éxitos
β_new = β_old + fracasos
P(θ|D) = Beta(α_new, β_new)
```

### 2.10 Information Coefficient (IC) y Rank IC

**Problema**: No se mide la calidad predictiva de cada señal.

**Solución**: IC y Rank IC para evaluar cada indicador.

**Fórmula IC (Grinold & Kahn, 2000)**:
```
IC = corr(signal_t, return_{t+1})
```

**Rank IC**:
```
RankIC = Spearman(signal_t, return_{t+1})
```

**ICIR (Information Coefficient Information Ratio)**:
```
ICIR = mean(IC) / std(IC)
```

---

## 3. Implementación Propuesta — Nuevo Módulo `probabilistic_engine.py`

### 3.1 Arquitectura

```
probabilistic_engine.py
├── ProbabilityCalibrator        # Platt + Isotonic
├── BayesianModelAverager        # BMA con pesos posteriores
├── KellyPositionSizer           # Kelly fraccional
├── StochasticVolatilityHMM      # SV-HMM con GARCH
├── CopulaRiskAnalyzer           # Cópulas Clayton/Gumbel
├── FatTailMonteCarlo            # t-Student + Cornish-Fisher
├── WalkForwardValidator         # Walk-forward validation
├── EnsembleStacker              # Stacking de modelos
├── BayesianOnlineUpdater        # Actualización Bayesiana
└── SignalQualityMetrics         # IC, RankIC, ICIR
```

### 3.2 Integración con el sistema existente

```
predictive_engine.py
    ↓ (score compuesto)
probabilistic_engine.py
    ├── ProbabilityCalibrator → P_calibrada
    ├── BayesianModelAverager → pesos actualizados
    ├── KellyPositionSizer → tamaño de posición
    ├── CopulaRiskAnalyzer → riesgo de cola
    └── SignalQualityMetrics → IC de cada señal
        ↓
advanced_agents.py (PROFESSOR aprende de las métricas)
```

### 3.3 Métricas de evaluación

| Métrica | Fórmula | Objetivo |
|---------|---------|----------|
| Brier Score | `Σ(p_i - y_i)²/n` | Calibración |
| Log Loss | `-Σ(y_i·log(p_i) + (1-y_i)·log(1-p_i))/n` | Calibración |
| Reliability Diagram | `P(y=1|p≈p̂)` vs `p̂` | Calibración visual |
| IC | `corr(signal, return)` | Poder predictivo |
| Rank IC | `Spearman(signal, return)` | Poder predictivo robusto |
| ICIR | `mean(IC)/std(IC)` | Consistencia |
| Deflated Sharpe | Bailey & López de Prado (2014) | Sobreajuste |

---

## 4. Priorización de Implementación

### Fase A — Impacto inmediato (esta sesión)
1. **ProbabilityCalibrator** — Platt + Isotonic (mejora calibración)
2. **KellyPositionSizer** — Kelly fraccional (mejora sizing)
3. **SignalQualityMetrics** — IC/RankIC (mide calidad de señales)
4. **BayesianOnlineUpdater** — Actualización de pesos (aprendizaje continuo)

### Fase B — Mejora significativa
5. **WalkForwardValidator** — Validación out-of-sample
6. **FatTailMonteCarlo** — t-Student + Cornish-Fisher
7. **CopulaRiskAnalyzer** — Dependencia de colas

### Fase C — Avanzado
8. **StochasticVolatilityHMM** — SV-HMM con GARCH
9. **EnsembleStacker** — Stacking de modelos
10. **BayesianModelAverager** — BMA completo

---

## 5. Referencias Académicas

1. **Platt (1999)** — Probabilistic Outputs for Support Vector Machines
2. **Zadrozny & Elkan (2002)** — Transforming Classifier Scores into Accurate Multiclass Probability Estimates
3. **Kelly (1956)** — A New Interpretation of Information Rate
4. **Thorp (2006)** — The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market
5. **Bollerslev (1986)** — Generalized Autoregressive Conditional Heteroskedasticity
6. **Hamilton (1989)** — A New Approach to the Economic Analysis of Nonstationary Time Series
7. **Clayton (1978)** — A Model for Association in Bivariate Life Tables
8. **Gumbel (1960)** — Bivariate Exponential Distributions
9. **Cornish & Fisher (1937)** — Moments and Cumulants in the Specification of Distributions
10. **Acerbi & Tasche (2002)** — On the Coherence of Expected Shortfall
11. **Hoeting et al. (1999)** — Bayesian Model Averaging: A Tutorial
12. **Schwarz (1978)** — Estimating the Dimension of a Model
13. **Wolpert (1992)** — Stacked Generalization
14. **Grinold & Kahn (2000)** — Active Portfolio Management
15. **Bailey & López de Prado (2014)** — The Deflated Sharpe Ratio
16. **López de Prado (2018)** — Advances in Financial Machine Learning
17. **Bishop (2006)** — Pattern Recognition and Machine Learning
18. **Murphy (2012)** — Machine Learning: A Probabilistic Perspective
19. **Gelman et al. (2013)** — Bayesian Data Analysis
20. **Nelsen (2006)** — An Introduction to Copulas