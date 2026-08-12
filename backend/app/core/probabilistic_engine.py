"""
Motor Probabilístico Avanzado Fortress Core — Fase 3.5

Implementa mejoras matemáticas y probabilísticas estilo Jim Simons:

1. ProbabilityCalibrator — Platt scaling + Isotonic regression
2. KellyPositionSizer — Kelly fraccional con edge del PROFESSOR
3. SignalQualityMetrics — IC, RankIC, ICIR
4. BayesianOnlineUpdater — Actualización Bayesiana de pesos
5. FatTailMonteCarlo — t-Student + Cornish-Fisher VaR/ES
6. CopulaRiskAnalyzer — Cópulas Clayton/Gumbel para dependencia de colas
7. WalkForwardValidator — Validación out-of-sample

Referencias:
- Platt (1999): Probabilistic Outputs for SVMs
- Zadrozny & Elkan (2002): Isotonic Regression
- Kelly (1956): Information Rate
- Thorp (2006): Kelly Criterion
- Bollerslev (1986): GARCH
- Hamilton (1989): Markov Switching
- Clayton (1978), Gumbel (1960): Cópulas
- Cornish & Fisher (1937): VaR ajustado
- Acerbi & Tasche (2002): Expected Shortfall
- Grinold & Kahn (2000): IC/ICIR
- Hoeting et al. (1999): Bayesian Model Averaging
"""
import json
import os
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
from scipy.stats import t as t_dist

# ============================================================
# 1. ProbabilityCalibrator — Platt + Isotonic
# ============================================================

class ProbabilityCalibrator:
    """
    Calibra scores a probabilidades usando Platt scaling y
    isotonic regression. Aprende los parámetros de datos históricos.
    """

    def __init__(self, method: str = "platt", min_prob: float = 0.05, max_prob: float = 0.95):
        self.method = method
        self.min_prob = min_prob
        self.max_prob = max_prob
        self.A = 1.0  # Platt slope
        self.B = 0.0  # Platt intercept
        self.isotonic_x: List[float] = []
        self.isotonic_y: List[float] = []
        self.is_fitted = False

    def fit(self, scores: np.ndarray, outcomes: np.ndarray) -> "ProbabilityCalibrator":
        """
        Ajusta el calibrador con scores y outcomes binarios (0/1).

        Args:
            scores: Array de scores compuestos
            outcomes: Array de outcomes (1 = subió, 0 = bajó)
        """
        scores = np.asarray(scores, dtype=float)
        outcomes = np.asarray(outcomes, dtype=float)

        if len(scores) < 20:
            return self

        if self.method == "platt":
            # Platt scaling: P(y=1|x) = 1/(1+exp(A·f(x)+B))
            # Optimizar A y B por máxima verosimilitud
            def neg_log_likelihood(params):
                A, B = params
                logits = A * scores + B
                probs = 1 / (1 + np.exp(-logits))
                probs = np.clip(probs, 1e-10, 1 - 1e-10)
                return -np.mean(outcomes * np.log(probs) + (1 - outcomes) * np.log(1 - probs))

            result = minimize(
                neg_log_likelihood,
                x0=[1.0, 0.0],
                method="Nelder-Mead",
                options={"maxiter": 1000, "xatol": 1e-6},
            )
            if result.success:
                self.A, self.B = result.x
                self.is_fitted = True

        elif self.method == "isotonic":
            # Isotonic regression (PAV - Pool Adjacent Violators)
            # Ordenar por score
            order = np.argsort(scores)
            sorted_scores = scores[order]
            sorted_outcomes = outcomes[order]

            # PAV algorithm
            x_blocks = []
            y_blocks = []
            for s, o in zip(sorted_scores, sorted_outcomes):
                x_blocks.append([s])
                y_blocks.append([o])
                # Merge violators
                while len(y_blocks) >= 2 and np.mean(y_blocks[-1]) < np.mean(y_blocks[-2]):
                    x_blocks[-2].extend(x_blocks[-1])
                    y_blocks[-2].extend(y_blocks[-1])
                    x_blocks.pop()
                    y_blocks.pop()

            self.isotonic_x = [np.mean(b) for b in x_blocks]
            self.isotonic_y = [np.mean(b) for b in y_blocks]
            self.is_fitted = True

        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        """Convierte scores a probabilidades calibradas."""
        scores = np.asarray(scores, dtype=float)

        if not self.is_fitted:
            # Fallback: logística simple
            probs = 1 / (1 + np.exp(-scores))
        elif self.method == "platt":
            logits = self.A * scores + self.B
            probs = 1 / (1 + np.exp(-logits))
        else:  # isotonic
            probs = np.interp(scores, self.isotonic_x, self.isotonic_y)

        return np.clip(probs, self.min_prob, self.max_prob)

    def save(self, path: str):
        """Guarda el calibrador."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "method": self.method,
            "A": self.A,
            "B": self.B,
            "isotonic_x": self.isotonic_x,
            "isotonic_y": self.isotonic_y,
            "is_fitted": self.is_fitted,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        """Carga el calibrador."""
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            self.method = data.get("method", "platt")
            self.A = data.get("A", 1.0)
            self.B = data.get("B", 0.0)
            self.isotonic_x = data.get("isotonic_x", [])
            self.isotonic_y = data.get("isotonic_y", [])
            self.is_fitted = data.get("is_fitted", False)


# ============================================================
# 2. KellyPositionSizer — Kelly fraccional
# ============================================================

class KellyPositionSizer:
    """
    Calcula el tamaño de posición óptimo usando Kelly fraccional.
    Combina el Kelly clásico con el edge estimado del PROFESSOR.
    """

    def __init__(self, fractional_kelly: float = 0.25, max_position_pct: float = 0.10,
                 risk_per_trade: float = 0.015):
        self.fractional_kelly = fractional_kelly
        self.max_position_pct = max_position_pct
        self.risk_per_trade = risk_per_trade

    def compute_kelly_fraction(self, win_prob: float, payoff_ratio: float) -> float:
        """
        Kelly criterion: f* = (p·b - q) / b

        Args:
            win_prob: Probabilidad de ganar (p)
            payoff_ratio: Ratio ganancia/pérdida (b)
        """
        p = np.clip(win_prob, 0.01, 0.99)
        q = 1 - p
        b = max(payoff_ratio, 0.01)

        f_star = (p * b - q) / b
        return max(0.0, f_star)

    def compute_position_size(self, equity: float, price: float, atr: float,
                              win_prob: float, payoff_ratio: float,
                              edge_estimate: float = 0.0) -> Tuple[int, float]:
        """
        Calcula el tamaño de posición óptimo.

        Args:
            equity: Capital actual
            price: Precio del activo
            atr: ATR (para stop loss)
            win_prob: Probabilidad calibrada de ganar
            payoff_ratio: Ratio ganancia/pérdida esperado
            edge_estimate: Edge estimado por el PROFESSOR (accuracy - 0.5)

        Returns:
            (shares, kelly_fraction)
        """
        if price <= 0 or atr <= 0:
            return 0, 0.0

        # Kelly clásico
        kelly = self.compute_kelly_fraction(win_prob, payoff_ratio)

        # Ajustar con edge del PROFESSOR
        if edge_estimate != 0:
            # Si el PROFESSOR tiene edge positivo, aumentar ligeramente
            # Si tiene edge negativo, reducir
            kelly = kelly * (1 + edge_estimate)

        # Kelly fraccional
        kelly_frac = kelly * self.fractional_kelly

        # Limitar por riesgo por trade
        stop_distance = max(2.0 * atr, price * 0.05)
        shares_by_risk = (equity * self.risk_per_trade) / stop_distance

        # Limitar por posición máxima
        max_shares = (equity * self.max_position_pct) / price

        # Kelly sizing (si kelly_frac > 0)
        if kelly_frac > 0:
            kelly_shares = (equity * kelly_frac) / price
            shares = int(min(kelly_shares, shares_by_risk, max_shares))
        else:
            shares = int(min(shares_by_risk, max_shares))

        return shares, kelly_frac


# ============================================================
# 3. SignalQualityMetrics — IC, RankIC, ICIR
# ============================================================

class SignalQualityMetrics:
    """
    Mide la calidad predictiva de cada señal usando
    Information Coefficient (IC), Rank IC e ICIR.
    """

    @staticmethod
    def compute_ic(signal: pd.Series, forward_returns: pd.Series) -> float:
        """Pearson correlation entre señal y retorno futuro."""
        valid = pd.concat([signal, forward_returns], axis=1).dropna()
        if len(valid) < 20:
            return 0.0
        return float(valid.iloc[:, 0].corr(valid.iloc[:, 1]))

    @staticmethod
    def compute_rank_ic(signal: pd.Series, forward_returns: pd.Series) -> float:
        """Spearman rank correlation."""
        valid = pd.concat([signal, forward_returns], axis=1).dropna()
        if len(valid) < 20:
            return 0.0
        return float(valid.iloc[:, 0].corr(valid.iloc[:, 1], method="spearman"))

    @staticmethod
    def compute_icir(ic_series: pd.Series) -> float:
        """IC Information Ratio: mean(IC)/std(IC)."""
        if len(ic_series) < 5 or ic_series.std() == 0:
            return 0.0
        return float(ic_series.mean() / ic_series.std())

    @staticmethod
    def evaluate_signal(df: pd.DataFrame, signal_col: str, return_col: str,
                        horizon: int = 5) -> Dict:
        """
        Evalúa la calidad de una señal.

        Args:
            df: DataFrame con señal y precios
            signal_col: Columna de la señal
            return_col: Columna de precios (close)
            horizon: Horizonte de retorno futuro en días

        Returns:
            Dict con IC, RankIC, ICIR, y significancia
        """
        if signal_col not in df.columns or return_col not in df.columns:
            return {"ic": 0.0, "rank_ic": 0.0, "icir": 0.0, "n": 0, "significant": False}

        signal = df[signal_col]
        prices = df[return_col]
        forward_returns = prices.shift(-horizon) / prices - 1

        # IC por ventanas de 60 días
        ic_series = []
        for i in range(0, len(df) - 60, 30):
            window_signal = signal.iloc[i:i+60]
            window_returns = forward_returns.iloc[i:i+60]
            ic = SignalQualityMetrics.compute_ic(window_signal, window_returns)
            ic_series.append(ic)

        ic = SignalQualityMetrics.compute_ic(signal, forward_returns)
        rank_ic = SignalQualityMetrics.compute_rank_ic(signal, forward_returns)
        icir = SignalQualityMetrics.compute_icir(pd.Series(ic_series))

        # Significancia: |IC| > 2/sqrt(n)
        n = len(pd.concat([signal, forward_returns], axis=1).dropna())
        threshold = 2 / np.sqrt(n) if n > 0 else 0.1
        significant = abs(ic) > threshold

        return {
            "ic": round(ic, 4),
            "rank_ic": round(rank_ic, 4),
            "icir": round(icir, 4),
            "n": n,
            "significant": significant,
            "threshold": round(threshold, 4),
        }


# ============================================================
# 4. BayesianOnlineUpdater — Actualización Bayesiana
# ============================================================

class BayesianOnlineUpdater:
    """
    Actualiza pesos de señales usando inferencia Bayesiana online.
    Usa prior Beta-Binomial para cada señal.
    """

    def __init__(self, prior_alpha: float = 1.0, prior_beta: float = 1.0):
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.alpha: Dict[str, float] = {}
        self.beta: Dict[str, float] = {}
        self.weights: Dict[str, float] = {}

    def update(self, signal_name: str, correct: bool, base_weight: float = 0.1):
        """
        Actualiza el peso de una señal con nueva evidencia.

        Args:
            signal_name: Nombre de la señal
            correct: Si la señal fue correcta
            base_weight: Peso base de la señal
        """
        if signal_name not in self.alpha:
            self.alpha[signal_name] = self.prior_alpha
            self.beta[signal_name] = self.prior_beta

        if correct:
            self.alpha[signal_name] += 1
        else:
            self.beta[signal_name] += 1

        # Posterior mean: alpha / (alpha + beta)
        posterior_mean = self.alpha[signal_name] / (self.alpha[signal_name] + self.beta[signal_name])

        # Peso = base_weight * (1 + (posterior_mean - 0.5) * 2)
        # Si posterior > 0.5, peso aumenta; si < 0.5, peso disminuye
        adjustment = (posterior_mean - 0.5) * 2.0
        self.weights[signal_name] = base_weight * (1 + adjustment)

    def get_weight(self, signal_name: str, default: float = 0.1) -> float:
        """Obtiene el peso actualizado de una señal."""
        return self.weights.get(signal_name, default)

    def get_all_weights(self) -> Dict[str, float]:
        """Obtiene todos los pesos actualizados."""
        return self.weights

    def get_posterior(self, signal_name: str) -> Tuple[float, float]:
        """Obtiene los parámetros posteriores de una señal."""
        return self.alpha.get(signal_name, self.prior_alpha), self.beta.get(signal_name, self.prior_beta)

    def save(self, path: str):
        """Guarda el estado."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "alpha": self.alpha,
            "beta": self.beta,
            "weights": self.weights,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        """Carga el estado."""
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            self.alpha = data.get("alpha", {})
            self.beta = data.get("beta", {})
            self.weights = data.get("weights", {})


# ============================================================
# 5. FatTailMonteCarlo — t-Student + Cornish-Fisher
# ============================================================

class FatTailMonteCarlo:
    """
    Simulación Monte Carlo con colas gruesas (t-Student) y
    VaR/ES con Cornish-Fisher.
    """

    def __init__(self, n_sims: int = 1000, dof: int = 5):
        self.n_sims = n_sims
        self.dof = dof  # Grados de libertad t-Student (menor = colas más gruesas)

    def simulate_returns(self, returns: np.ndarray, n_periods: int = 252) -> np.ndarray:
        """
        Simula retornos futuros usando t-Student con parámetros estimados.

        Args:
            returns: Retornos históricos
            n_periods: Número de periodos a simular

        Returns:
            Array de retornos simulados
        """
        returns = np.asarray(returns, dtype=float)
        if len(returns) < 20:
            return np.zeros(n_periods)

        mu = np.mean(returns)
        sigma = np.std(returns)

        # Simular con t-Student (colas más gruesas que normal)
        simulated = t_dist.rvs(df=self.dof, loc=mu, scale=sigma, size=n_periods)
        return simulated

    def simulate_equity_curves(self, returns: np.ndarray, initial_equity: float = 25000.0,
                               n_sims: int = None) -> np.ndarray:
        """
        Simula curvas de equity con t-Student.

        Returns:
            Array de shape (n_sims, n_periods) con curvas de equity
        """
        n_sims = n_sims or self.n_sims
        n_periods = len(returns)
        curves = np.zeros((n_sims, n_periods + 1))
        curves[:, 0] = initial_equity

        for i in range(n_sims):
            sim_returns = self.simulate_returns(returns, n_periods)
            curves[i, 1:] = initial_equity * np.cumprod(1 + sim_returns)

        return curves

    def cornish_fisher_var(self, returns: np.ndarray, alpha: float = 0.05) -> float:
        """
        VaR con Cornish-Fisher expansion.

        VaR_α = μ + σ·(z_α + (z_α²-1)·S/6 + (z_α³-3·z_α)·K/24 - (2·z_α³-5·z_α)·S²/36)
        """
        returns = np.asarray(returns, dtype=float)
        if len(returns) < 20:
            return 0.0

        mu = np.mean(returns)
        sigma = np.std(returns)
        if sigma == 0:
            return 0.0

        # Skewness y kurtosis
        S = stats.skew(returns)
        K = stats.kurtosis(returns, fisher=True)  # Excess kurtosis

        z_alpha = stats.norm.ppf(alpha)

        # Cornish-Fisher adjustment
        z_cf = (z_alpha
                + (z_alpha**2 - 1) * S / 6
                + (z_alpha**3 - 3 * z_alpha) * K / 24
                - (2 * z_alpha**3 - 5 * z_alpha) * S**2 / 36)

        return float(mu + sigma * z_cf)

    def expected_shortfall(self, returns: np.ndarray, alpha: float = 0.05) -> float:
        """
        Expected Shortfall (CVaR): E[X | X ≤ VaR_α]
        """
        returns = np.asarray(returns, dtype=float)
        if len(returns) < 20:
            return 0.0

        var = self.cornish_fisher_var(returns, alpha)
        tail = returns[returns <= var]
        if len(tail) == 0:
            return var
        return float(np.mean(tail))

    def monte_carlo_metrics(self, returns: np.ndarray, initial_equity: float = 25000.0) -> Dict:
        """
        Calcula métricas Monte Carlo con colas gruesas.

        Returns:
            Dict con mean, p5, p95, prob_loss, VaR, ES
        """
        curves = self.simulate_equity_curves(returns, initial_equity)
        final_equities = curves[:, -1]

        # VaR y ES de los retornos
        var_95 = self.cornish_fisher_var(returns, 0.05)
        es_95 = self.expected_shortfall(returns, 0.05)

        return {
            "mean": float(np.mean(final_equities)),
            "p5": float(np.percentile(final_equities, 5)),
            "p95": float(np.percentile(final_equities, 95)),
            "prob_loss": float(np.mean(final_equities < initial_equity)),
            "var_95": round(var_95 * 100, 2),
            "expected_shortfall_95": round(es_95 * 100, 2),
            "n_sims": self.n_sims,
            "dof": self.dof,
        }


# ============================================================
# 6. CopulaRiskAnalyzer — Dependencia de colas
# ============================================================

class CopulaRiskAnalyzer:
    """
    Analiza dependencia de colas entre activos usando cópulas
    de Clayton (cola inferior) y Gumbel (cola superior).
    """

    @staticmethod
    def _pseudo_observations(x: np.ndarray) -> np.ndarray:
        """Convierte a pseudo-observaciones uniformes [0,1]."""
        x = np.asarray(x, dtype=float)
        n = len(x)
        ranks = stats.rankdata(x)
        return ranks / (n + 1)

    @staticmethod
    def fit_clayton(u: np.ndarray, v: np.ndarray) -> float:
        """
        Estima theta de Clayton vía tau de Kendall (Genest & Rivest 1993):
        θ = 2τ / (1-τ). La log-verosimilitud original (MLE numérico) tenía
        un error de signo y le faltaban términos — el optimizador siempre
        convergía al límite theta≈0 sin importar los datos (verificado con
        datos sintéticos de dependencia conocida). Este estimador cerrado
        es el estándar de la literatura precisamente por ser más robusto
        que MLE directo para cópulas Arquimedeanas de 1 parámetro.
        """
        tau, _ = stats.kendalltau(u, v)
        if pd.isna(tau) or tau <= 0:
            return 1e-6  # Clayton sólo captura dependencia positiva
        if tau >= 1.0:
            return 1e6  # dependencia perfecta (series degeneradas): theta acotado
        return float(2 * tau / (1 - tau))

    @staticmethod
    def fit_gumbel(u: np.ndarray, v: np.ndarray) -> float:
        """
        Estima theta de Gumbel vía tau de Kendall: θ = 1/(1-τ). Mismo
        motivo que fit_clayton — reemplaza el MLE numérico roto.
        """
        tau, _ = stats.kendalltau(u, v)
        if pd.isna(tau) or tau <= 0:
            return 1.0  # independencia
        if tau >= 1.0:
            return 50.0  # dependencia perfecta (series degeneradas)
        theta = 1 / (1 - tau)
        return float(min(theta, 50.0))  # cap: evita overflow en tail_dependence_gumbel cuando tau->1

    @staticmethod
    def tail_dependence_clayton(theta: float) -> float:
        """Dependencia de cola inferior: λ_L = 2^(-1/θ)."""
        if theta <= 0:
            return 0.0
        return 2 ** (-1 / theta)

    @staticmethod
    def tail_dependence_gumbel(theta: float) -> float:
        """Dependencia de cola superior: λ_U = 2 - 2^(1/θ)."""
        if theta < 1:
            return 0.0
        return 2 - 2 ** (1 / theta)

    def analyze_pair(self, x: np.ndarray, y: np.ndarray, name_x: str = "X", name_y: str = "Y") -> Dict:
        """
        Analiza dependencia de colas entre dos series.

        Returns:
            Dict con Pearson, Spearman, Kendall, cópulas, tail dependence
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        # Alinear
        n = min(len(x), len(y))
        x, y = x[-n:], y[-n:]

        if n < 30:
            return {"error": "Datos insuficientes"}

        # Correlaciones
        pearson = float(np.corrcoef(x, y)[0, 1])
        spearman = float(stats.spearmanr(x, y)[0])
        kendall = float(stats.kendalltau(x, y)[0])

        # Pseudo-observaciones
        u = self._pseudo_observations(x)
        v = self._pseudo_observations(y)

        # Cópulas
        theta_clayton = self.fit_clayton(u, v)
        theta_gumbel = self.fit_gumbel(u, v)

        # Tail dependence
        lambda_L = self.tail_dependence_clayton(theta_clayton)
        lambda_U = self.tail_dependence_gumbel(theta_gumbel)

        # Interpretación
        risk_level = "BAJO"
        if lambda_L > 0.3 or lambda_U > 0.3:
            risk_level = "MEDIO"
        if lambda_L > 0.5 or lambda_U > 0.5:
            risk_level = "ALTO"

        return {
            "pair": f"{name_x}-{name_y}",
            "pearson": round(pearson, 4),
            "spearman": round(spearman, 4),
            "kendall": round(kendall, 4),
            "clayton_theta": round(theta_clayton, 4),
            "gumbel_theta": round(theta_gumbel, 4),
            "tail_dependence_lower": round(lambda_L, 4),
            "tail_dependence_upper": round(lambda_U, 4),
            "risk_level": risk_level,
            "n": n,
        }

    def analyze_macro_risks(self, macro_data: Dict[str, pd.DataFrame]) -> Dict:
        """
        Analiza riesgos de cola entre activos macro.

        Args:
            macro_data: Dict con DataFrames de DXY, gold, silver, SPY, VIX, etc.

        Returns:
            Dict con análisis de pares
        """
        results = {}
        _assets = list(macro_data.keys())

        # Pares clave para riesgo
        key_pairs = [
            ("DXY", "gold"), ("DXY", "SPY"), ("SPY", "VIX"),
            ("gold", "silver"), ("SPY", "TLT"), ("gold", "TLT"),
        ]

        # `da = macro_data.get(a) or macro_data.get(...)` rompía con
        # ValueError ("the truth value of a DataFrame is ambiguous") apenas
        # macro_data.get(a) devolvía un DataFrame real de más de una fila —
        # nunca se probó con datos reales. `is None` en vez de truthiness.
        alt_keys = {"DXY": "DX-Y.NYB", "gold": "GC=F", "silver": "SI=F",
                    "SPY": "^GSPC", "VIX": "^VIX"}
        for a, b in key_pairs:
            da = macro_data.get(a)
            if da is None:
                da = macro_data.get(alt_keys.get(a, a))
            db = macro_data.get(b)
            if db is None:
                db = macro_data.get(alt_keys.get(b, b))
            if da is not None and db is not None and len(da) > 30 and len(db) > 30:
                # Usar retornos para dependencia de colas
                ret_a = da["close"].pct_change().dropna().values
                ret_b = db["close"].pct_change().dropna().values
                results[f"{a}_{b}"] = self.analyze_pair(ret_a, ret_b, a, b)

        return results


# ============================================================
# 7. WalkForwardValidator — Validación out-of-sample
# ============================================================

class WalkForwardValidator:
    """
    Valida el modelo con walk-forward: entrena en ventana,
    evalúa en ventana siguiente, avanza.
    """

    def __init__(self, train_window: int = 504, test_window: int = 63):
        self.train_window = train_window
        self.test_window = test_window

    def validate(self, df: pd.DataFrame, signal_col: str, return_col: str = "close",
                 horizon: int = 5) -> Dict:
        """
        Walk-forward validation de una señal.

        Args:
            df: DataFrame con señal y precios
            signal_col: Columna de señal
            return_col: Columna de precios
            horizon: Horizonte de retorno

        Returns:
            Dict con métricas out-of-sample
        """
        if signal_col not in df.columns or return_col not in df.columns:
            return {"error": "Columnas no encontradas"}

        prices = df[return_col]
        signal = df[signal_col]
        forward_returns = prices.shift(-horizon) / prices - 1

        # Walk-forward
        ic_scores = []
        rank_ic_scores = []
        n_windows = 0

        for start in range(0, len(df) - self.train_window - self.test_window, self.test_window):
            train_end = start + self.train_window
            test_end = train_end + self.test_window

            # Train window
            _train_signal = signal.iloc[start:train_end]
            _train_returns = forward_returns.iloc[start:train_end]

            # Test window
            test_signal = signal.iloc[train_end:test_end]
            test_returns = forward_returns.iloc[train_end:test_end]

            # Calcular IC en test
            ic = SignalQualityMetrics.compute_ic(test_signal, test_returns)
            rank_ic = SignalQualityMetrics.compute_rank_ic(test_signal, test_returns)
            ic_scores.append(ic)
            rank_ic_scores.append(rank_ic)
            n_windows += 1

        if n_windows == 0:
            return {"error": "No hay suficientes ventanas"}

        ic_arr = np.array(ic_scores)
        rank_ic_arr = np.array(rank_ic_scores)

        return {
            "n_windows": n_windows,
            "mean_ic": round(float(np.mean(ic_arr)), 4),
            "std_ic": round(float(np.std(ic_arr)), 4),
            "mean_rank_ic": round(float(np.mean(rank_ic_arr)), 4),
            "icir": round(float(np.mean(ic_arr) / np.std(ic_arr)) if np.std(ic_arr) > 0 else 0.0, 4),
            "positive_ic_windows": int(np.sum(ic_arr > 0)),
            "positive_ic_pct": round(float(np.mean(ic_arr > 0)), 4),
            "train_window": self.train_window,
            "test_window": self.test_window,
        }


# ============================================================
# 8. ProbabilisticEngine — Integración completa
# ============================================================

class ProbabilisticEngine:
    """
    Motor probabilístico integrado que combina todas las mejoras.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.calibrator_short = ProbabilityCalibrator(method="platt")
        self.calibrator_medium = ProbabilityCalibrator(method="platt")
        self.calibrator_long = ProbabilityCalibrator(method="platt")
        self.kelly_sizer = KellyPositionSizer()
        self.bayesian_updater = BayesianOnlineUpdater()
        self.monte_carlo = FatTailMonteCarlo()
        self.copula_analyzer = CopulaRiskAnalyzer()
        self.walk_forward = WalkForwardValidator()
        self._load_state()

    def _load_state(self):
        """Carga estado persistente."""
        calib_path = os.path.join(self.data_dir, "calibrators.json")
        if os.path.exists(calib_path):
            try:
                with open(calib_path, "r") as f:
                    data = json.load(f)
                self.calibrator_short.A = data.get("short_A", 1.0)
                self.calibrator_short.B = data.get("short_B", 0.0)
                self.calibrator_short.is_fitted = data.get("short_fitted", False)
                self.calibrator_medium.A = data.get("medium_A", 1.0)
                self.calibrator_medium.B = data.get("medium_B", 0.0)
                self.calibrator_medium.is_fitted = data.get("medium_fitted", False)
                self.calibrator_long.A = data.get("long_A", 1.0)
                self.calibrator_long.B = data.get("long_B", 0.0)
                self.calibrator_long.is_fitted = data.get("long_fitted", False)
            except Exception:
                pass

        bayes_path = os.path.join(self.data_dir, "bayesian_weights.json")
        if os.path.exists(bayes_path):
            self.bayesian_updater.load(bayes_path)

    def _save_state(self):
        """Guarda estado persistente."""
        os.makedirs(self.data_dir, exist_ok=True)
        calib_path = os.path.join(self.data_dir, "calibrators.json")
        data = {
            "short_A": self.calibrator_short.A,
            "short_B": self.calibrator_short.B,
            "short_fitted": self.calibrator_short.is_fitted,
            "medium_A": self.calibrator_medium.A,
            "medium_B": self.calibrator_medium.B,
            "medium_fitted": self.calibrator_medium.is_fitted,
            "long_A": self.calibrator_long.A,
            "long_B": self.calibrator_long.B,
            "long_fitted": self.calibrator_long.is_fitted,
        }
        with open(calib_path, "w") as f:
            json.dump(data, f, indent=2)

        self.bayesian_updater.save(os.path.join(self.data_dir, "bayesian_weights.json"))

    def calibrate_probabilities(self, score: float, horizon: str) -> float:
        """
        Convierte score a probabilidad calibrada.

        Args:
            score: Score compuesto
            horizon: "short_term_1_30d", "medium_term_1_6m", "long_term_1_5y"
        """
        if horizon == "short_term_1_30d":
            return float(self.calibrator_short.predict(np.array([score]))[0])
        elif horizon == "medium_term_1_6m":
            return float(self.calibrator_medium.predict(np.array([score]))[0])
        else:
            return float(self.calibrator_long.predict(np.array([score]))[0])

    def fit_calibrators(self, historical_scores: Dict[str, np.ndarray],
                        historical_outcomes: Dict[str, np.ndarray]):
        """
        Ajusta los calibradores con datos históricos.

        Args:
            historical_scores: Dict con scores por horizonte
            historical_outcomes: Dict con outcomes por horizonte
        """
        if "short" in historical_scores:
            self.calibrator_short.fit(historical_scores["short"], historical_outcomes["short"])
        if "medium" in historical_scores:
            self.calibrator_medium.fit(historical_scores["medium"], historical_outcomes["medium"])
        if "long" in historical_scores:
            self.calibrator_long.fit(historical_scores["long"], historical_outcomes["long"])
        self._save_state()

    def compute_position_size(self, equity: float, price: float, atr: float,
                              win_prob: float, payoff_ratio: float,
                              edge_estimate: float = 0.0) -> Tuple[int, float]:
        """Calcula tamaño de posición con Kelly fraccional."""
        return self.kelly_sizer.compute_position_size(
            equity, price, atr, win_prob, payoff_ratio, edge_estimate
        )

    def update_signal_weight(self, signal_name: str, correct: bool, base_weight: float = 0.1):
        """Actualiza peso Bayesiano de una señal."""
        self.bayesian_updater.update(signal_name, correct, base_weight)
        self._save_state()

    def get_signal_weight(self, signal_name: str, default: float = 0.1) -> float:
        """Obtiene peso Bayesiano de una señal."""
        return self.bayesian_updater.get_weight(signal_name, default)

    def analyze_tail_risk(self, macro_data: Dict[str, pd.DataFrame]) -> Dict:
        """Analiza riesgo de cola entre activos macro."""
        return self.copula_analyzer.analyze_macro_risks(macro_data)

    def simulate_risk(self, returns: np.ndarray, initial_equity: float = 25000.0) -> Dict:
        """Simula riesgo con colas gruesas."""
        return self.monte_carlo.monte_carlo_metrics(returns, initial_equity)

    def validate_signal(self, df: pd.DataFrame, signal_col: str, horizon: int = 5) -> Dict:
        """Valida calidad de señal con walk-forward."""
        return self.walk_forward.validate(df, signal_col, horizon=horizon)

    def get_status(self) -> Dict:
        """Estado del motor probabilístico."""
        return {
            "calibrators": {
                "short": {"fitted": self.calibrator_short.is_fitted,
                          "A": round(self.calibrator_short.A, 4),
                          "B": round(self.calibrator_short.B, 4)},
                "medium": {"fitted": self.calibrator_medium.is_fitted,
                           "A": round(self.calibrator_medium.A, 4),
                           "B": round(self.calibrator_medium.B, 4)},
                "long": {"fitted": self.calibrator_long.is_fitted,
                         "A": round(self.calibrator_long.A, 4),
                         "B": round(self.calibrator_long.B, 4)},
            },
            "kelly": {
                "fractional": self.kelly_sizer.fractional_kelly,
                "max_position_pct": self.kelly_sizer.max_position_pct,
            },
            "bayesian_weights": self.bayesian_updater.get_all_weights(),
            "monte_carlo": {
                "n_sims": self.monte_carlo.n_sims,
                "dof": self.monte_carlo.dof,
            },
            "walk_forward": {
                "train_window": self.walk_forward.train_window,
                "test_window": self.walk_forward.test_window,
            },
        }
