"""M5 — Detector de deriva de features y de concepto (DISENO_INSTRUMENTO.md §7).

MOTIVO: el motor y sus modelos se entrenaron/midieron sobre historia. Si el mercado
cambia de comportamiento, siguen operando con un mapa viejo y nadie se entera. Este
módulo detecta cuándo eso pasa — REPORTA, nunca actúa: no re-entrena, no apaga nada,
no toca el motor.

DOS DETECCIONES INDEPENDIENTES:

1. DERIVA DE FEATURES (cambió la distribución de las entradas): test de
   Kolmogorov-Smirnov de dos muestras (scipy.stats.ks_2samp) por feature, ventana
   histórica vs ventana reciente. Corregido por comparaciones múltiples con
   Bonferroni sobre K features (regla del proyecto: p<0.05 sin corregir sobre
   muchas features no es un hallazgo, es ruido).

2. DERIVA DE CONCEPTO (se rompió la relación entrada->resultado): compara accuracy
   y correlación predicción-vs-resultado entre ventana histórica y reciente.
   Deriva si la accuracy cae más de 10 puntos o la correlación más de 0.15
   (umbrales pre-registrados en la orden M5, no calibrados acá).

ABSTENCIÓN (regla de la orden): con n < 30 en cualquiera de las dos ventanas el
detector NO afirma ni "hay deriva" ni "no hay deriva" — devuelve `drift: None` con
severidad "ABSTENCION". Afirmar con muestras chicas sería fabricar evidencia.

CONTRATO DE SALIDA (lo que consume el resto del proyecto):
   {"feature_drift": {nombre: {"ks": float, "p_value": float, "drift": bool,
                               "severidad": "LOW|MEDIUM|HIGH|ABSTENCION"}},
    "concept_drift": {"accuracy_hist": float, "accuracy_reciente": float,
                      "caida": float, "drift": bool, "severidad": str},
    "accion_recomendada": str}
"""
from typing import Dict, Optional, Sequence, Union

import numpy as np
from scipy import stats

# Umbrales pre-registrados en la orden M5 (ORDENES_MODULOS.md).
MIN_SAMPLE_SIZE = 30                 # por debajo: abstención, no afirmación
ACCURACY_DROP_THRESHOLD = 0.10       # puntos de accuracy
CORRELATION_DROP_THRESHOLD = 0.15    # puntos de correlación
ALPHA_DEFAULT = 0.05

# Severidad de deriva de features: cuánto más estricto que el umbral Bonferroni.
HIGH_SEVERITY_FACTOR = 10.0          # p < alpha_corrected/10 -> HIGH


def _clean(series: Sequence[float]) -> np.ndarray:
    """Convierte a float array y descarta no-finitos (NaN/Inf) por feature."""
    arr = np.asarray(series, dtype=float)
    return arr[np.isfinite(arr)]


def _severity_feature(p_value: float, alpha_corrected: float) -> str:
    if p_value < alpha_corrected / HIGH_SEVERITY_FACTOR:
        return "HIGH"
    return "MEDIUM"


def _corr_or_none(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Correlación Pearson, None si no es calculable (varianza nula, n<2)."""
    if len(x) < 2 or len(y) < 2:
        return None
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def detect_feature_drift(
    historical: Dict[str, Sequence[float]],
    recent: Dict[str, Sequence[float]],
    alpha: float = ALPHA_DEFAULT,
) -> Dict[str, Dict[str, Union[float, bool, str]]]:
    """KS de dos muestras por feature, histórico vs reciente, con Bonferroni.

    `historical`/`recent`: {nombre_feature: secuencia de valores}. Si una feature
    no está en ambas entradas se omite del resultado (llamador desalineado).

    Bonferroni sobre K = features EVALUABLES (ambas listas con muestras válidas).
    Con n < MIN_SAMPLE_SIZE en cualquier ventana: abstinencia (drift=None).
    """
    names = [f for f in set(historical) & set(recent) if f in historical and f in recent]
    names = sorted(names)
    result: Dict[str, Dict[str, Union[float, bool, str]]] = {}

    ks_raw: Dict[str, float] = {}
    p_raw: Dict[str, float] = {}
    for name in names:
        h = _clean(historical[name])
        r = _clean(recent[name])
        if len(h) == 0 or len(r) == 0 or len(h) < MIN_SAMPLE_SIZE or len(r) < MIN_SAMPLE_SIZE:
            result[name] = {"ks": None, "p_value": None, "drift": None, "severidad": "ABSTENCION"}
            continue
        d, p = stats.ks_2samp(h, r)
        ks_raw[name] = float(d)
        p_raw[name] = float(p)

    k = len(ks_raw)
    alpha_corrected = alpha / k if k > 0 else alpha

    for name in ks_raw:
        drift = p_raw[name] < alpha_corrected
        result[name] = {
            "ks": ks_raw[name],
            "p_value": p_raw[name],
            "drift": drift,
            "severidad": _severity_feature(p_raw[name], alpha_corrected) if drift else "LOW",
        }
    return result


def detect_concept_drift(
    actual_hist: Sequence[float],
    predicted_hist: Sequence[float],
    actual_recent: Sequence[float],
    predicted_recent: Sequence[float],
    accuracy_drop_threshold: float = ACCURACY_DROP_THRESHOLD,
    correlation_drop_threshold: float = CORRELATION_DROP_THRESHOLD,
) -> Dict[str, Union[float, bool, str]]:
    """Compara accuracy y correlación predicción-vs-resultado entre ventanas.

    Accuracy = fracción de signos coincidentes (sirve tanto para etiquetas +1/-1 de
    M1 como para clases binarias 0/1). Deriva si la accuracy cae más de
    `accuracy_drop_threshold` puntos o la correlación más de
    `correlation_drop_threshold`. Con n < MIN_SAMPLE_SIZE en alguna ventana:
    abstinencia.
    """
    ah = _clean(actual_hist)
    ph = _clean(predicted_hist)
    ar = _clean(actual_recent)
    pr = _clean(predicted_recent)

    if len(ah) == 0 or len(ph) == 0 or len(ar) == 0 or len(pr) == 0:
        return {"accuracy_hist": None, "accuracy_reciente": None, "caida": None,
                "drift": None, "severidad": "ABSTENCION"}
    if min(len(ah), len(ph), len(ar), len(pr)) < MIN_SAMPLE_SIZE:
        return {"accuracy_hist": None, "accuracy_reciente": None, "caida": None,
                "drift": None, "severidad": "ABSTENCION"}

    n_min = min(len(ah), len(ph))
    acc_hist = float(np.mean(np.sign(ph[:n_min]) == np.sign(ah[:n_min])))
    n_min_r = min(len(ar), len(pr))
    acc_recent = float(np.mean(np.sign(pr[:n_min_r]) == np.sign(ar[:n_min_r])))

    corr_hist = _corr_or_none(ph[:n_min], ah[:n_min])
    corr_recent = _corr_or_none(pr[:n_min_r], ar[:n_min_r])

    caida_acc = acc_hist - acc_recent
    caida_corr = None if (corr_hist is None or corr_recent is None) else corr_hist - corr_recent

    drop_acc = caida_acc > accuracy_drop_threshold
    drop_corr = caida_corr is not None and caida_corr > correlation_drop_threshold
    drift = bool(drop_acc or drop_corr)

    if drift and drop_acc and drop_corr:
        severidad = "HIGH"
    elif drift:
        severidad = "MEDIUM"
    else:
        severidad = "LOW"

    return {
        "accuracy_hist": round(acc_hist, 6),
        "accuracy_reciente": round(acc_recent, 6),
        "caida": round(float(caida_acc), 6),
        "corr_hist": None if corr_hist is None else round(corr_hist, 6),
        "corr_reciente": None if corr_recent is None else round(corr_recent, 6),
        "caida_corr": None if caida_corr is None else round(float(caida_corr), 6),
        "drift": drift,
        "severidad": severidad,
    }


def recommend_action(
    feature_drift: Dict[str, Dict[str, Union[float, bool, str]]],
    concept_drift: Dict[str, Union[float, bool, str]],
) -> str:
    """Acción sugerida — REPORTA, nunca la ejecuta.

    Reglas declaradas:
      - abstención en algún lado y nada confirmado -> no actuar, juntar datos
      - solo features -> recalibrar/revisar entradas
      - solo concepto -> revisar modelo
      - ambos -> pausar decisiones nuevas hasta revisar
    """
    abstained = False
    feature_flagged = False
    for f in feature_drift.values():
        if f.get("drift") is True:
            feature_flagged = True
        elif f.get("drift") is None:
            abstained = True

    concept_flagged = concept_drift.get("drift") is True
    if concept_drift.get("drift") is None:
        abstained = True

    if feature_flagged and concept_flagged:
        return ("ALTA PRIORIDAD: features y concepto derivaron — pausar decisiones "
                "nuevas y revisar modelo y entradas antes de operar.")
    if feature_flagged:
        return ("Revisar features: la distribución de las entradas cambió — "
                "recalibrar o re-entrenar el preprocesamiento.")
    if concept_flagged:
        return ("Revisar modelo: la relación entrada->resultado cambió — evaluar "
                "re-entrenamiento o pausa.")
    if abstained:
        return ("Abstención: datos insuficientes para decidir — acumular más "
                "observaciones antes de afirmar algo.")
    return "Continuar: sin deriva detectada."


def run_drift_report(
    historical: Dict[str, Sequence[float]],
    recent: Dict[str, Sequence[float]],
    actual_hist: Sequence[float],
    predicted_hist: Sequence[float],
    actual_recent: Sequence[float],
    predicted_recent: Sequence[float],
    alpha: float = ALPHA_DEFAULT,
) -> Dict:
    """Reporte completo con el CONTRATO DE SALIDA de M5."""
    fd = detect_feature_drift(historical, recent, alpha=alpha)
    cd = detect_concept_drift(actual_hist, predicted_hist, actual_recent, predicted_recent)
    return {
        "feature_drift": fd,
        "concept_drift": cd,
        "accion_recomendada": recommend_action(fd, cd),
    }
