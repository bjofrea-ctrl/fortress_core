"""Tests de M5 — Detector de deriva (app/core/drift_detector.py).

Casos obligatorios de la orden (ORDENES_MODULOS.md M5):
- dos muestras de la MISMA distribución -> NO debe detectar deriva (falso positivo)
- dos distribuciones claramente distintas -> SÍ debe detectarla
- muestras chicas (n<30) -> debe abstenerse, no afirmar
- la corrección de Bonferroni testeada explícitamente
"""
import numpy as np
import pytest
from app.core.drift_detector import (
    detect_concept_drift,
    detect_feature_drift,
    recommend_action,
    run_drift_report,
)

RNG = np.random.default_rng(42)


class TestFeatureDrift:
    def test_misma_distribucion_no_detecta(self):
        """Mismo generador, dos muestras grandes de N(0,1): sin deriva."""
        a = RNG.normal(0.0, 1.0, size=500)
        b = RNG.normal(0.0, 1.0, size=500)
        res = detect_feature_drift({"f1": a}, {"f1": b})
        assert res["f1"]["drift"] is False
        assert res["f1"]["severidad"] == "LOW"

    def test_distribuciones_distintas_detecta(self):
        """N(0,1) vs N(5,1): deriva clara."""
        a = RNG.normal(0.0, 1.0, size=500)
        b = RNG.normal(5.0, 1.0, size=500)
        res = detect_feature_drift({"f1": a}, {"f1": b})
        assert res["f1"]["drift"] is True
        assert res["f1"]["severidad"] in ("MEDIUM", "HIGH")
        assert res["f1"]["ks"] > 0.5

    def test_muestras_chicas_se_abstiene(self):
        """n=20 < 30: abstención, no afirmación."""
        a = RNG.normal(0.0, 1.0, size=20)
        b = RNG.normal(5.0, 1.0, size=20)  # distribuciones CLARAMENTE distintas
        res = detect_feature_drift({"f1": a}, {"f1": b})
        assert res["f1"]["drift"] is None
        assert res["f1"]["severidad"] == "ABSTENCION"
        assert res["f1"]["ks"] is None and res["f1"]["p_value"] is None

    def test_bonferroni_corrige_por_comparaciones_multiples(self):
        """Con K features, el umbral se endurece: un p marginal no pasa.

        Se controla el p-valor de ks_2samp vía mock (0.03, que está entre 0.005
        y 0.05): con K=1 el umbral es 0.05 -> pasa; con K=10 el umbral es 0.005
        -> NO pasa. La corrección Bonferroni es la que cambia el veredicto.
        """
        import app.core.drift_detector as dd

        a = RNG.normal(0.0, 1.0, size=200)
        b = RNG.normal(0.0, 1.0, size=200)
        orig = dd.stats.ks_2samp

        def fake_ks(x, y):
            return 0.15, 0.03  # estadístico + p-valor controlado

        dd.stats.ks_2samp = fake_ks
        try:
            uno = dd.detect_feature_drift({"f1": a}, {"f1": b})
            diez = dd.detect_feature_drift({f"f{i}": a for i in range(10)},
                                           {f"f{i}": b for i in range(10)})
        finally:
            dd.stats.ks_2samp = orig

        assert uno["f1"]["drift"] is True   # 0.03 < 0.05 (K=1)
        assert diez["f1"]["drift"] is False  # 0.03 > 0.005 (K=10)
        assert diez["f1"]["severidad"] == "LOW"

    def test_bonferroni_sin_falso_positivo_y_sin_sobre_corregir(self):
        """Con p reales: mismo par sin deriva no genera falso positivo con K=10,
        y una deriva real sigue detectándose con K=10 (no sobre-corrige)."""
        a = RNG.normal(0.0, 1.0, size=300)
        b = RNG.normal(0.0, 1.0, size=300)
        c = RNG.normal(6.0, 1.0, size=300)
        diez_igual = detect_feature_drift({f"f{i}": a for i in range(10)},
                                          {f"f{i}": b for i in range(10)})
        diez_mix = detect_feature_drift({f"f{i}": a for i in range(10)},
                                        {f"f{i}": (c if i == 0 else b) for i in range(10)})
        assert diez_igual["f1"]["drift"] is False
        assert diez_mix["f0"]["drift"] is True
        assert diez_mix["f1"]["drift"] is False

    def test_ks_estadistico_reportado_es_el_real(self):
        from scipy import stats as sp_stats

        a = RNG.normal(0.0, 1.0, size=400)
        b = RNG.normal(2.0, 1.0, size=400)
        d_expected, _ = sp_stats.ks_2samp(a, b)
        res = detect_feature_drift({"f1": a}, {"f1": b})
        assert res["f1"]["ks"] == pytest.approx(d_expected, abs=1e-9)

    def test_feature_faltante_en_una_ventana_se_omite(self):
        a = RNG.normal(0.0, 1.0, size=200)
        b = RNG.normal(0.0, 1.0, size=200)
        res = detect_feature_drift({"f1": a, "f2": a}, {"f1": b})
        assert "f1" in res
        assert "f2" not in res


class TestConceptDrift:
    def test_acc_hist_y_reciente_validas(self):
        hist_actual = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0] * 40
        hist_pred = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0] * 40
        res = detect_concept_drift(hist_actual, hist_pred, hist_actual, hist_pred)
        assert res["accuracy_hist"] == pytest.approx(1.0)
        assert res["accuracy_reciente"] == pytest.approx(1.0)
        assert res["caida"] == pytest.approx(0.0)
        assert res["drift"] is False
        assert res["severidad"] == "LOW"

    def test_caida_de_accuracy_mas_de_10_puntos_detecta(self):
        # hist: 100% acierto; recent: 85% acierto (caída 0.15 > 0.10)
        n = 200
        hist_actual = np.tile([1.0, -1.0], n // 2)
        hist_pred = hist_actual.copy()  # 100%
        recent_actual = np.tile([1.0, -1.0], n // 2)
        recent_pred = recent_actual.copy()
        # romper 30 de cada 200 en recent -> 170/200 = 85%
        rng2 = np.random.default_rng(7)
        idx = rng2.choice(n, size=30, replace=False)
        recent_pred[idx] = -recent_actual[idx]
        res = detect_concept_drift(hist_actual, hist_pred, recent_actual, recent_pred)
        assert res["accuracy_hist"] == pytest.approx(1.0)
        assert res["accuracy_reciente"] == pytest.approx(0.85, abs=1e-9)
        assert res["drift"] is True
        assert res["severidad"] in ("MEDIUM", "HIGH")
        assert res["caida"] > 0.10

    def test_caida_menor_al_umbral_no_detecta(self):
        # 92% -> 85%: caída 0.07 < 0.10 -> sin deriva
        n = 200
        hist_actual = np.tile([1.0, -1.0], n // 2)
        rng2 = np.random.default_rng(11)
        hist_pred = hist_actual.copy()
        idx = rng2.choice(n, size=16, replace=False)  # 184/200 = 92%
        hist_pred[idx] = -hist_actual[idx]
        recent_pred = hist_actual.copy()
        idx2 = rng2.choice(n, size=30, replace=False)  # 170/200 = 85%
        recent_pred[idx2] = -hist_actual[idx2]
        res = detect_concept_drift(hist_actual, hist_pred, hist_actual, recent_pred)
        assert res["drift"] is False
        assert res["severidad"] == "LOW"

    def test_caida_de_correlacion_mas_de_0_15_detecta(self):
        n = 300
        x = RNG.normal(size=n)
        y_hist = x + RNG.normal(scale=0.2, size=n)      # corr alta (~0.98)
        y_recent = RNG.normal(size=n)                    # corr ~0
        res = detect_concept_drift(x, y_hist, x, y_recent)
        assert res["corr_hist"] is not None and res["corr_reciente"] is not None
        assert res["caida_corr"] > 0.15
        assert res["drift"] is True

    def test_muestras_chicas_se_abstiene(self):
        res = detect_concept_drift([1.0] * 10, [1.0] * 10, [-1.0] * 10, [1.0] * 10)
        assert res["drift"] is None
        assert res["severidad"] == "ABSTENCION"
        assert res["accuracy_hist"] is None


class TestRecommendAction:
    def test_sin_deriva_continua(self):
        fd = {"f1": {"ks": 0.1, "p_value": 0.5, "drift": False, "severidad": "LOW"}}
        cd = {"accuracy_hist": 0.9, "accuracy_reciente": 0.9, "caida": 0.0,
              "drift": False, "severidad": "LOW"}
        assert "Continuar" in recommend_action(fd, cd)

    def test_solo_features(self):
        fd = {"f1": {"ks": 0.4, "p_value": 0.001, "drift": True, "severidad": "HIGH"}}
        cd = {"accuracy_hist": 0.9, "accuracy_reciente": 0.9, "caida": 0.0,
              "drift": False, "severidad": "LOW"}
        assert "features" in recommend_action(fd, cd).lower()

    def test_solo_concepto(self):
        fd = {"f1": {"ks": 0.1, "p_value": 0.5, "drift": False, "severidad": "LOW"}}
        cd = {"accuracy_hist": 0.95, "accuracy_reciente": 0.7, "caida": 0.25,
              "drift": True, "severidad": "HIGH"}
        assert "modelo" in recommend_action(fd, cd).lower()

    def test_ambos_alta_prioridad(self):
        fd = {"f1": {"ks": 0.4, "p_value": 0.001, "drift": True, "severidad": "HIGH"}}
        cd = {"accuracy_hist": 0.95, "accuracy_reciente": 0.7, "caida": 0.25,
              "drift": True, "severidad": "HIGH"}
        out = recommend_action(fd, cd)
        assert "ALTA PRIORIDAD" in out

    def test_abstencion_no_afirma(self):
        fd = {"f1": {"ks": None, "p_value": None, "drift": None, "severidad": "ABSTENCION"}}
        cd = {"accuracy_hist": None, "accuracy_reciente": None, "caida": None,
              "drift": None, "severidad": "ABSTENCION"}
        assert "Abstención" in recommend_action(fd, cd)


class TestContratoSalida:
    def test_run_drift_report_devuelve_el_contrato(self):
        a = RNG.normal(0.0, 1.0, size=300)
        b = RNG.normal(0.0, 1.0, size=300)
        hist_actual = np.tile([1.0, -1.0], 150)
        hist_pred = hist_actual.copy()
        out = run_drift_report({"f1": a}, {"f1": b},
                               hist_actual, hist_pred, hist_actual, hist_pred)
        assert set(out.keys()) == {"feature_drift", "concept_drift", "accion_recomendada"}
        assert set(out["feature_drift"]["f1"].keys()) == {"ks", "p_value", "drift", "severidad"}
        assert set(out["concept_drift"].keys()) >= {
            "accuracy_hist", "accuracy_reciente", "caida", "drift", "severidad"}
        assert isinstance(out["accion_recomendada"], str)
        assert out["feature_drift"]["f1"]["drift"] is False
