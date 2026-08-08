import numpy as np
import pandas as pd
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler
from typing import Dict


class GlobalRegimeClassifier:
    REGIME_ALLOCATION = {
        0: {"equity": 0.60, "bonds": 0.15, "gold": 0.15, "cash": 0.10},
        1: {"equity": 0.40, "bonds": 0.10, "gold": 0.40, "cash": 0.10},
        2: {"equity": 0.15, "bonds": 0.10, "gold": 0.55, "cash": 0.20},
        3: {"equity": 0.10, "bonds": 0.55, "gold": 0.10, "cash": 0.25},
    }

    def __init__(self, n_states: int = 4):
        self.n_states = n_states
        self.model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            tol=1e-4
        )
        self.scaler = StandardScaler()
        self.is_fitted = False
        self.state_labels = {
            0: "GOLDILOCKS",
            1: "REFLATION",
            2: "STAGFLATION",
            3: "DEFLATION"
        }

    def _extract_features(self, price_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        features = {}
        for t in ["SPY", "EFA", "QQQ"]:
            if t in price_data:
                features[f"growth_{t}"] = price_data[t].close.pct_change(60)
        for t in ["GLD", "DBC", "TIP"]:
            if t in price_data:
                features[f"inflation_{t}"] = price_data[t].close.pct_change(60)
        for t in ["TLT", "AGG"]:
            if t in price_data:
                features[f"rates_{t}"] = price_data[t].close.pct_change(60)
        vix_key = "VIX" if "VIX" in price_data else "^VIX" if "^VIX" in price_data else None
        if vix_key:
            features["vix_level"] = price_data[vix_key].close
        return pd.DataFrame(features).ffill().dropna()

    def _align_states(self, states: np.ndarray, features: pd.DataFrame) -> np.ndarray:
        if len(states) < 50:
            return states

        metrics = {}
        for s in range(self.n_states):
            mask = states == s
            if mask.sum() == 0:
                continue
            metrics[s] = {
                "equity": features.get("growth_SPY", pd.Series(0, index=features.index)).values[mask].mean(),
                "bond": features.get("rates_TLT", pd.Series(0, index=features.index)).values[mask].mean(),
                "commodity": features.get("inflation_DBC", pd.Series(0, index=features.index)).values[mask].mean(),
            }

        if len(metrics) < 4:
            return states

        goldilocks = max(metrics, key=lambda s: metrics[s]["equity"])
        deflation = max(metrics, key=lambda s: metrics[s]["bond"])
        reflation = max(metrics, key=lambda s: metrics[s]["commodity"])
        remaining = [s for s in metrics if s not in (goldilocks, deflation, reflation)]
        stagflation = remaining[0] if remaining else 2

        remap = {goldilocks: 0, reflation: 1, stagflation: 2, deflation: 3}
        return np.array([remap.get(s, s) for s in states])

    def fit(self, price_data: Dict[str, pd.DataFrame]) -> None:
        feats = self._extract_features(price_data)
        if len(feats) < 252:
            raise ValueError(f"Datos insuficientes: {len(feats)} días")
        scaled = self.scaler.fit_transform(feats.values)
        self.model.fit(scaled)
        self.is_fitted = True

    def predict_current_regime(self, price_data: Dict[str, pd.DataFrame]) -> Dict:
        if not self.is_fitted:
            return self._default()

        feats = self._extract_features(price_data)
        if len(feats) < 60:
            return self._default()

        scaled = self.scaler.transform(feats.values)
        raw_states = self.model.predict(scaled)
        aligned = self._align_states(raw_states, feats)
        current = int(aligned[-1])
        probs = self.model.predict_proba(scaled)[-1]

        # probs está indexado por el componente RAW del HMM (orden interno
        # arbitrario), no por el estado semántico remapeado (0=GOLDILOCKS..
        # 3=DEFLATION). current es el id remapeado -> indexar probs con él
        # directamente lee la probabilidad de un componente distinto salvo
        # que el remap sea la identidad. raw_states[-1] es el id correcto
        # para indexar probs, y por construcción de _align_states siempre
        # corresponde al mismo régimen que 'current' (remapeado o no).
        raw_current = int(raw_states[-1])

        return {
            "state": current,
            "state_name": self.state_labels[current],
            "allocation": self.REGIME_ALLOCATION[current],
            "confidence": float(probs[raw_current]),
        }

    def _default(self) -> Dict:
        return {
            "state": 0,
            "state_name": "GOLDILOCKS",
            "allocation": self.REGIME_ALLOCATION[0],
            "confidence": 0.5,
        }