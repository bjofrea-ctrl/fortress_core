"""
Motor Probabilístico Avanzado Fortress Core — Fase 3.5

Implementa mejoras matemáticas y probabilísticas estilo Jim Simons:

1. ProbabilityCalibrator — Platt scaling + Isotonic regression
2. SignalQualityMetrics — IC, RankIC, ICIR
3. BayesianOnlineUpdater — Actualización Bayesiana de pesos
4. FatTailMonteCarlo — t-Student + Cornish-Fisher VaR/ES
5. CopulaRiskAnalyzer — Cópulas Clayton/Gumbel para dependencia de colas
6. WalkForwardValidator — Validación out-of-sample

KellyPositionSizer y el wrapper ProbabilisticEngine (integraba las 6 clases de arriba)
se eliminaron (M8, 2026-08-15): código muerto verificado — solo los usaba
scripts/test_probabilistic.py, sin imports en producción. Ver ROADMAP.md.

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
from typing import Dict, List, Optional, Tuple

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
# 2. SignalQualityMetrics — IC, RankIC, ICIR
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
# 3. BayesianOnlineUpdater — Actualización Bayesiana
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

    def update(self, signal_name: str, correct: bool, base_weight: float = 0.1,
               strength: float = 1.0):
        """
        Actualiza el peso de una señal con nueva evidencia.

        Args:
            signal_name: Nombre de la señal
            correct: Si la señal fue correcta
            base_weight: Peso base de la señal
            strength: Fuerza de la evidencia (>= 0). 1.0 = una observación binaria
                (comportamiento previo); valores > 1.0 dan más peso a outcomes de
                magnitud grande (p.ej. un pnl_r alto). Se permiten fracciones.
        """
        if signal_name not in self.alpha:
            self.alpha[signal_name] = self.prior_alpha
            self.beta[signal_name] = self.prior_beta

        evidence = max(float(strength), 0.0)
        if correct:
            self.alpha[signal_name] += evidence
        else:
            self.beta[signal_name] += evidence

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
# 4. FatTailMonteCarlo — t-Student + Cornish-Fisher
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
# 5. CopulaRiskAnalyzer — Dependencia de colas
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
# 6. WalkForwardValidator — Validación out-of-sample
# ============================================================

class WalkForwardValidator:
    """
    Valida el modelo con walk-forward: entrena en ventana,
    evalúa en ventana siguiente, avanza.

    PURGE/EMBARGO (T2.1 — PLAN_INTEGRACION_INDICAGENT.md, Fase 2):
    Hallazgo verificado contra este código: el corte train/test era CONTIGUO
    sin purga, y `forward_returns = prices.shift(-horizon)/prices - 1` hace
    que el retorno de una observación de TRAIN en el día train_end-h sea una
    ventana que se solapa con las observaciones de TEST (h <= horizon). Sin
    embargo, purge del LADO DEL TRAIN no corresponde acá: en este diseño no
    hay modelo entrenado sobre train (cada ventana del walk-forward solo computa
    correlaciones de test con si misma), y el IC de train jamás se reporta ni
    decide nada — por lo tanto no existe ninguna estimación que se contamine.
    El embargo que sí es necesario: excluir del fold de TEST las primeras
    `purge_bars` observaciones posteriores al corte train/test, cuyo forward
    return usa el bloque [t+1, t+horizon] que arranca dentro de la ventana de
    train (momento de la señal inmediatamente previo al fold, contiguo a lo
    que un hipotético estimador habría visto). Se implementó
    `purge_bars: int | None = None` → default `horizon` (criterio de
    indicAgent: "sizeado al horizonte de retorno más largo"), con `purge_bars=0`
    disponible para reproducir el comportamiento pre-2026-08-20 si alguna vez
    se necesita comparar contra resultados históricos.
    """

    def __init__(self, train_window: int = 504, test_window: int = 63):
        self.train_window = train_window
        self.test_window = test_window

    def validate(self, df: pd.DataFrame, signal_col: str, return_col: str = "close",
                 horizon: int = 5, purge_bars: Optional[int] = None) -> Dict:
        """
        Walk-forward validation de una señal.

        Args:
            df: DataFrame con señal y precios
            signal_col: Columna de señal
            return_col: Columna de precios
            horizon: Horizonte de retorno
            purge_bars: Barras de embargo excluidas del inicio del fold de test
                (ver docstring de la clase, T2.1). None → default = horizon.
                0 → leg contiguo al corte train/test (comportamiento pre-2026-08-20,
                solo para reproducir resultados históricos).

        Returns:
            Dict con métricas out-of-sample
        """
        if signal_col not in df.columns or return_col not in df.columns:
            return {"error": "Columnas no encontradas"}

        prices = df[return_col]
        signal = df[signal_col]
        forward_returns = prices.shift(-horizon) / prices - 1

        effective_purge = int(horizon) if purge_bars is None else max(0, int(purge_bars))

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

            # Test window — PURGE T2.1: embargo de `effective_purge` barras despues
            # del corte train/test (forward return del bloque purgado usaba barras
            # que arrancan dentro de la ventana de train)
            test_start = train_end + effective_purge
            if test_start >= test_end:
                continue
            test_signal = signal.iloc[test_start:test_end]
            test_returns = forward_returns.iloc[test_start:test_end]

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
            "purge_bars": effective_purge,
        }

