from typing import Dict

import numpy as np
import pandas as pd
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler


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
        """Renombra raw states del HMM a etiquetas semánticas ESTABLES entre
        refits (FIX B6, MAPEO_ESTADOS_HMM.md §2-3).

        Problema original: el método usaba `max(metrics, key=...)` sobre
        equity/bond/commodity. Eso depende del ranking de cada refit — entre
        refits trimestrales (WalkForwardRegimeGate recalibra cada 63d), el
        mismo raw state podía terminar mapeado a GOLDILOCKS en un refit y a
        DEFLATION en otro, aunque el perfil económico subyacente fuera el mismo.
        Consecuencia: el gate de régimen observaba "switches" que eran
        reordenamientos arbitrarios del HMM, no cambios reales.

        Convención nueva: ordenar raw states por **VIX medio ascendente**
        (VIX bajo = bull, VIX alto = bear) y asignar por rank con **SPY60d
        descendente como tie-breaker** para los rangos 1/2. Robusto en 4 refits
        empíricos (2015-2026, 2020-2026, 2015-2019, 2018-2026): los rangos 0
        y 3 son estables (bull/bear), los rangos 1/2 son intercambiables
        entre REFLATION y STAGFLATION según la muestra — aceptable porque esos
        rangos no son críticos para gates operacionales.

        Returns:
            Array de la misma longitud que `states` con valores en {0, 1, 2, 3}:
            0 = GOLDILOCKS, 1 = REFLATION, 2 = STAGFLATION, 3 = DEFLATION.
        """
        if len(states) < 50:
            return states

        # Necesitamos VIX para el criterio de orden. Si no está, fallback al
        # método original (mantiene backward compat sin datos macro completos).
        if "vix_level" not in features.columns:
            return self._align_states_legacy(states, features)

        # Calcular VIX medio y SPY 60d medio por raw state
        vix_by_state = {}
        spy_by_state = {}
        for s in range(self.n_states):
            mask = states == s
            if mask.sum() == 0:
                continue
            vix_by_state[s] = float(features.loc[mask, "vix_level"].mean())
            spy_by_state[s] = float(
                features.loc[mask, "growth_SPY"].mean()
                if "growth_SPY" in features.columns
                else 0.0
            )

        if len(vix_by_state) < 2:
            return states  # no hay suficientes estados para reordenar

        # Ordenar raw states por VIX ascendente; desempate por SPY60d descendente
        sorted_states = sorted(
            vix_by_state.keys(),
            key=lambda s: (vix_by_state[s], -spy_by_state[s]),
        )

        # Asignar etiquetas semánticas por rank
        remap = {sorted_states[0]: 0}  # rank 0 = VIX más bajo = GOLDILOCKS
        if len(sorted_states) > 1:
            remap[sorted_states[1]] = 1  # rank 1 = REFLATION
        if len(sorted_states) > 2:
            remap[sorted_states[2]] = 2  # rank 2 = STAGFLATION
        if len(sorted_states) > 3:
            remap[sorted_states[3]] = 3  # rank 3 = VIX más alto = DEFLATION

        return np.array([remap.get(int(s), int(s)) for s in states])

    def _align_states_legacy(self, states: np.ndarray, features: pd.DataFrame) -> np.ndarray:
        """Método original (pre-B6): max(metrics) sobre equity/bond/commodity.
        Se mantiene como fallback para cuando VIX no está disponible en features
        (e.g. datos de prueba sin VIX). El bug B6 es conocido y aceptable
        solo en este fallback — el camino normal tiene VIX siempre
        (vía `_extract_features`).
        """
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

    def predict_regime_series(self, price_data: Dict[str, pd.DataFrame]) -> pd.Series:
        """Como predict_current_regime pero devuelve el estado alineado para CADA
        fecha, no solo la última. Reutiliza el mismo pipeline de features/alineación
        para que un walk-forward externo (M3, regime_gate.py) pueda re-ajustar el
        modelo periódicamente y etiquetar cada ventana con el modelo vigente en ese
        momento, sin tener que re-implementar extracción de features.

        ADVERTENCIA (leakage): esta variante decodifica Viterbi UNA vez sobre la
        secuencia completa pasada (`self.model.predict(scaled)`). La etiqueta de un
        día temprano de la secuencia puede quedar informada por días posteriores de
        la misma secuencia (leakage acotado a la longitud de la secuencia). Usar
        SOLO para diagnóstico; para walk-forward de gates o trials pre-registrados
        usar `predict_regime_series_causal`."""
        if not self.is_fitted:
            return pd.Series(dtype=int)
        feats = self._extract_features(price_data)
        if feats.empty:
            return pd.Series(dtype=int)
        scaled = self.scaler.transform(feats.values)
        aligned = self._align_states(self.model.predict(scaled), feats)
        return pd.Series(aligned, index=feats.index)

    def predict_regime_series_causal(self, price_data: Dict[str, pd.DataFrame]) -> pd.Series:
        """Como predict_regime_series pero decodifica día por día SIN leakage.

        Para cada fecha, trunca `price_data` a esa fecha y llama
        `predict_current_regime`, tomando solo la última etiqueta. Son O(n)
        decodificaciones Viterbi en vez de 1, pero cada etiqueta solo puede estar
        informada por datos <= a esa fecha — nunca por el futuro del bloque.

        Usar en cualquier contexto donde el leakage acotado de
        `predict_regime_series` no sea aceptable (walk-forward gates, trials
        pre-registrados, etiquetado de régimen histórico).
        """
        if not self.is_fitted:
            return pd.Series(dtype=int)
        feats = self._extract_features(price_data)
        if feats.empty:
            return pd.Series(dtype=int)
        labels = {}
        for date in feats.index:
            truncated = {s: df[df.index <= date] for s, df in price_data.items()}
            result = self.predict_current_regime(truncated)
            labels[date] = result["state"]
        return pd.Series(labels, index=feats.index)

    def _default(self) -> Dict:
        return {
            "state": 0,
            "state_name": "GOLDILOCKS",
            "allocation": self.REGIME_ALLOCATION[0],
            "confidence": 0.5,
        }
