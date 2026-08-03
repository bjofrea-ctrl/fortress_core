import numpy as np
import pandas as pd
from typing import Dict
from scipy.optimize import minimize


class RiskParityAllocator:
    def __init__(self, target_volatility: float = 0.10):
        self.target_volatility = target_volatility

    def calculate_covariance(self, returns_df: pd.DataFrame, window=252, ewma_halflife=60) -> pd.DataFrame:
        r = returns_df.tail(window)
        # Calcular covarianza EWMA y extraer la última matriz
        ewma_cov = r.ewm(halflife=ewma_halflife).cov()
        # El resultado tiene MultiIndex (fecha, activo); extraer la última fecha
        last_date = ewma_cov.index.get_level_values(0)[-1]
        cov = ewma_cov.loc[last_date] * 252
        return cov

    def _risk_contribution(self, weights, cov):
        port_var = weights @ cov @ weights
        port_vol = np.sqrt(port_var)
        return weights * (cov @ weights) / port_vol

    def _objective(self, weights, cov):
        n = len(weights)
        rc = self._risk_contribution(weights, cov)
        target = np.sqrt(weights @ cov @ weights) / n
        return np.sum((rc - target) ** 2)

    def solve(self, cov: pd.DataFrame) -> Dict[str, float]:
        assets = cov.columns.tolist()
        n = len(assets)
        constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        bounds = [(0.01, 0.40)] * n
        result = minimize(
            self._objective,
            np.ones(n) / n,
            args=(cov.values,),
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000},
        )
        weights = result.x if result.success else np.ones(n) / n
        weights = weights / weights.sum()
        return {a: float(w) for a, w in zip(assets, weights)}

    def apply_volatility_targeting(self, weights: Dict[str, float], cov: pd.DataFrame) -> Dict[str, float]:
        assets = list(weights.keys())
        w = np.array([weights[a] for a in assets])
        port_vol = np.sqrt(w @ cov.loc[assets, assets].values @ w)
        scale = min(self.target_volatility / port_vol, 1.0) if port_vol > 0 else 1.0
        scaled = {a: w[i] * scale for i, a in enumerate(assets)}
        scaled["CASH"] = max(0.0, 1.0 - sum(scaled.values()))
        return scaled

    def allocate(self, returns_df: pd.DataFrame) -> Dict[str, float]:
        cov = self.calculate_covariance(returns_df)
        return self.apply_volatility_targeting(self.solve(cov), cov)