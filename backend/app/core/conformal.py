"""M2 — Instrumento conforme: abstención calibrada (DISENO_INSTRUMENTO.md §5, §7 etapa 1).

TESIS: Fortress no debería construirse como un predictor — debería construirse como
un instrumento diagnóstico calibrado. Un test clínico bien calibrado no solo predice:
declara CUÁNDO su lectura no es confiable. Este módulo es esa declaración, formalizada.

QUÉ HACE: envuelve cualquier score continuo de un modelo existente (ya construido por
otro módulo — este no entrena nada) y produce un intervalo de predicción con garantía
de cobertura en muestra finita (Split Conformal Prediction, Vovk et al.), calibrado
contra las etiquetas REALES de M1 (barrier_labeling.ret_net) — no contra retorno a
horizonte fijo. Si el intervalo es más ancho que el umbral declarado, el instrumento
se abstiene.

POR QUÉ SPLIT CONFORME Y NO OTRA COSA: no asume distribución del error (el retorno
neto de este proyecto está lejos de ser gaussiano — colas gordas, EVT §19 lo midió).
La única supuesto es intercambiabilidad entre calibración y predicción — más débil que
cualquier alternativa paramétrica, y es la técnica que la literatura reconoce con
garantía de cobertura exacta en muestra finita, no asintótica.

MÉTRICA PRIMARIA: no es Sharpe. Es VPP bajo abstención (de lo que el instrumento SÍ
opera, cuánto acierta) y la cobertura empírica (¿el intervalo del 90% contiene al
90% real de los casos?). Un instrumento que se abstiene el 80% del tiempo y acierta
el 20% restante es un ÉXITO, no un fracaso — ver DISENO_INSTRUMENTO.md §8.

LIMITACIÓN DECLARADA: la garantía de cobertura de conformal prediction asume que los
datos de calibración y los de predicción son intercambiables (i.i.d. o exchangeable).
Series financieras tienen autocorrelación y no-estacionariedad — la garantía formal
se debilita con el tiempo. Por eso M5 (detector de deriva) existe: cuando detecta
deriva, la calibración de este módulo debe rehacerse, no confiar en una calibración
vieja indefinidamente. Este módulo no re-calibra solo.

CORRECCIÓN ESTRUCTURAL 2026-08-17 (hallazgo del trial #16, PLAN_MEJORA_MATEMATICA §24):
la versión anterior usaba residuos ABSOLUTOS `|outcome - point|` — el ancho del
intervalo era CONSTANTE (2×cuantil) para todo score, así que la abstención comparaba
dos constantes: o abstenía todo (default 2×mediana < 2×cuantil → 100% garantizado)
o nada. Estructuralmente incapaz de abstención diferencial. Ahora:
  - Residuos RELATIVOS `|outcome - point| / max(|point|, floor)` — el ancho del
    intervalo escala con la señal del score → la abstención puede discriminar.
  - Default de umbral = percentil 90 del ancho de calibración (abstención ~10% de
    los casos más inciertos), no 2×mediana.
  - El floor evita la explosión del residuo relativo con puntos ≈ 0 (señal nula:
    si el punto esperado es ~0, el intervalo relativo explota y el instrumento se
    abstiene — comportamiento correcto para "señal nula = no confiable").
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class ConformalCalibration:
    """Resultado de calibrar el instrumento contra un set de calibración."""
    quantile: float          # cuantil de residuos RELATIVOS que define el intervalo
    alpha: float              # nivel de significancia (0.10 = intervalo del 90%)
    n_calibration: int
    residuals_median: float   # mediana de residuos RELATIVOS
    residuals_p90: float      # p90 de residuos RELATIVOS


@dataclass(frozen=True)
class ConformalPrediction:
    """Salida del instrumento para una predicción individual."""
    point_estimate: float
    lower: float
    upper: float
    interval_width: float
    abstenerse: bool
    razon: str


class ConformalAbstentionEngine:
    """
    Split Conformal Prediction para regresión, con decisión de abstención.

    Uso:
      1. calibrate(scores_calib, outcomes_calib) — UNA vez, sobre un set de
         calibración separado del set donde se va a predecir (nunca el mismo).
      2. predict(score) — por cada score nuevo, devuelve intervalo + abstención.

    El "score" es lo que ya produce el motor (ej. composite_score, win_prob del
    calibrador existente) — este módulo NO genera scores, los envuelve.
    """

    def __init__(self, alpha: float = 0.10, max_interval_width: Optional[float] = None):
        """
        alpha: nivel de significancia. 0.10 -> intervalo de cobertura nominal 90%.
        max_interval_width: umbral de abstención. Si None, se fija en calibrate()
            como el percentil 90 de los anchos de calibración (abstención ~10% de
            los casos más inciertos) — un default razonable, no mágico.
        """
        if not 0 < alpha < 1:
            raise ValueError(f"alpha debe estar en (0,1), recibido {alpha}")
        self.alpha = alpha
        self.max_interval_width = max_interval_width
        self._calibration: Optional[ConformalCalibration] = None
        self._point_model: Optional[np.poly1d] = None
        # Floor del residuo relativo: p50(|punto|)/10 de calibración. Evita la
        # explosión de |outcome - point|/|point| cuando el punto esperado ~ 0.
        self._floor: float = 1e-12

    def calibrate(self, scores: Sequence[float], outcomes: Sequence[float]) -> ConformalCalibration:
        """
        Calibra el instrumento. `scores` y `outcomes` deben venir de un set NUNCA
        usado para predecir (separación estricta calibración/predicción — es lo
        que sostiene la garantía de cobertura).

        `outcomes` deben ser `ret_net` de M1 (barrier_labeling), no fwd_return a
        horizonte fijo — el objetivo que el motor realmente persigue.
        """
        scores = np.asarray(scores, dtype=float)
        outcomes = np.asarray(outcomes, dtype=float)
        if len(scores) != len(outcomes):
            raise ValueError(f"scores y outcomes deben tener igual longitud: {len(scores)} vs {len(outcomes)}")
        if len(scores) < 30:
            raise ValueError(
                f"Calibración con n={len(scores)} < 30 no es confiable — el cuantil "
                "de conformal prediction necesita masa suficiente en la cola. Abstenerse "
                "de calibrar, no de operar con una calibración débil."
            )

        # Modelo puntual: regresión lineal simple score->outcome. Deliberadamente
        # el modelo más simple posible — este módulo calibra incertidumbre, no
        # compite por ser el mejor predictor puntual. Navaja de Occam (DISENO_INSTRUMENTO
        # no lo dice explícito acá, pero es coherente con "perder mejor, no predecir mejor").
        coeffs = np.polyfit(scores, outcomes, deg=1)
        self._point_model = np.poly1d(coeffs)
        points = self._point_model(scores)

        # Residuos RELATIVOS: |outcome - point| / max(|point|, floor). El floor
        # escala con la señal típica (p50(|point|)/10) para no explotar con puntos
        # ~ 0. El ancho del intervalo resultante (2*q*denom) depende del score —
        # la abstención puede discriminar entre scores (corrección estructural del
        # hallazgo del trial #16: antes el ancho era constante, abstención 100% o 0%).
        self._floor = max(float(np.median(np.abs(points))) / 10.0, 1e-12)
        denom = np.maximum(np.abs(points), self._floor)
        residuals = np.abs(outcomes - points) / denom
        # Cuantil conforme: ceil((n+1)*(1-alpha))/n -- la corrección de muestra finita
        # de Split Conformal Prediction (Vovk et al. 2005), no un percentil ingenuo.
        n = len(residuals)
        q_level = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n)
        quantile = float(np.quantile(residuals, q_level))

        self._calibration = ConformalCalibration(
            quantile=quantile,
            alpha=self.alpha,
            n_calibration=n,
            residuals_median=float(np.median(residuals)),
            residuals_p90=float(np.quantile(residuals, 0.90)),
        )

        if self.max_interval_width is None:
            # Default declarado, no mágico: percentil 90 de los ANCHOS de calibración
            # (ancho_i = 2*q*denom(point_i)). Un intervalo más ancho que el 90% de los
            # casos típicos de este instrumento dispara la abstención — ~10% de los
            # scores más inciertos, no 100% ni 0% (fix del hallazgo del trial #16).
            calib_widths = 2.0 * quantile * denom
            self.max_interval_width = float(np.quantile(calib_widths, 0.90))

        return self._calibration

    def predict(self, score: float) -> ConformalPrediction:
        """Predice un intervalo para un score nuevo y decide si abstenerse."""
        if self._calibration is None:
            raise RuntimeError("Instrumento sin calibrar — llamar calibrate() primero")

        point = float(self._point_model(score))
        q = self._calibration.quantile
        # El ancho escala con la señal del score (residuos relativos): un score con
        # punto esperado grande tiene intervalo absoluto ancho, pero el ancho RELATIVO
        # al punto es el mismo para todos — la abstención compara el ancho absoluto
        # contra el caso típico de calibración.
        denom = max(abs(point), self._floor)
        half_width = q * denom
        lower, upper = point - half_width, point + half_width
        width = upper - lower

        abstenerse = width > self.max_interval_width
        if abstenerse:
            razon = (f"Intervalo [{lower:.4f}, {upper:.4f}] (ancho {width:.4f}) supera "
                     f"el umbral {self.max_interval_width:.4f} — incertidumbre demasiado "
                     "alta para este score, el instrumento no opera.")
        else:
            razon = (f"Intervalo [{lower:.4f}, {upper:.4f}] (ancho {width:.4f}) dentro "
                     f"del umbral {self.max_interval_width:.4f}.")

        return ConformalPrediction(
            point_estimate=point, lower=lower, upper=upper,
            interval_width=width, abstenerse=abstenerse, razon=razon,
        )

    def empirical_coverage(self, scores: Sequence[float], outcomes: Sequence[float]) -> float:
        """
        Cobertura empírica sobre un set de VALIDACIÓN (distinto de calibración y de
        predicción real). Debe aproximar 1-alpha si el instrumento está bien calibrado
        — esta es la verificación central de M2, no un test más: si esto falla, el
        instrumento no se usa (DISENO_INSTRUMENTO.md §8).
        """
        if self._calibration is None:
            raise RuntimeError("Instrumento sin calibrar")
        hits = 0
        for s, o in zip(scores, outcomes):
            pred = self.predict(s)
            if pred.lower <= o <= pred.upper:
                hits += 1
        return hits / len(scores) if len(scores) else float("nan")


def vpp_bajo_abstencion(predictions: List[ConformalPrediction], outcomes: Sequence[float]) -> dict:
    """
    Métrica primaria del instrumento (DISENO_INSTRUMENTO.md §8): de las predicciones
    donde el instrumento SÍ operó (no se abstuvo), ¿qué fracción tuvo signo correcto
    (outcome > 0 cuando point_estimate > 0, y viceversa)? Y qué fracción del universo
    total representa esa decisión de operar.

    No es accuracy simple: separa explícitamente "cuánto acierta cuando opera" de
    "cuánto elige operar" — son dos preguntas distintas y ambas importan.
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions y outcomes deben tener igual longitud")

    operados = [(p, o) for p, o in zip(predictions, outcomes) if not p.abstenerse]
    if not operados:
        return {"n_total": len(predictions), "n_operados": 0, "tasa_abstencion": 1.0,
                "vpp": float("nan")}

    aciertos = sum(1 for p, o in operados if np.sign(p.point_estimate) == np.sign(o) and o != 0)
    return {
        "n_total": len(predictions),
        "n_operados": len(operados),
        "tasa_abstencion": 1.0 - len(operados) / len(predictions),
        "vpp": aciertos / len(operados),
    }
