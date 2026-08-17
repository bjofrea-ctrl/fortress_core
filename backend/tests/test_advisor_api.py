"""Tests del contrato /api/advisor (dashboard institucional).

Patrón del repo (ver test_opportunities_api.py): se llama a la corutina del
router directamente (asyncio.run) — el repo no tiene httpx/TestClient en
dev-deps. Monkeypatch de _load_context para validar la ESTRUCTURA del
contrato sin red ni cálculo de ~60s.

Lo que se valida es el CONTRATO que el frontend consume:
- mapeo de etiquetas §29 (exacto, con n de evidencia),
- estructura de universe/symbol/theses/evidence,
- honestidad: sin cobertura EDGAR -> null + flag, nunca datos inventados.
"""
import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from app.api.routes import advisor


class FakeCalibrator:
    def __init__(self, fitted=True, prob=0.72):
        self.is_fitted = fitted
        self._prob = prob

    def predict(self, x):
        return np.full(len(x), self._prob)


class FakeConformal:
    def predict(self, score):
        return SimpleNamespace(
            point_estimate=0.01, lower=-0.02, upper=0.04, abstenerse=False, razon="ok"
        )


class FakeSignalEngine:
    """Devuelve señal solo para símbolos que pasen 'gate' (los que terminan en A)."""

    def generate_signal(self, df, symbol, regime_state):
        if not symbol.endswith("A") or regime_state == 3:
            return None
        close = float(df["close"].iloc[-1])
        atr = close * 0.02
        return {
            "score": 0.65,
            "entry_price": close,
            "stop_loss": close - 2 * atr,
            "take_profit": close + 4 * atr,
            "payoff_ratio": 2.0,
            "atr": atr,
            "factors": {"momentum": 0.5, "rsi": 0.4},
            "indicators": {
                "close": close,
                "ema50": close * 0.98,
                "ema200": close * 0.95,
                "adx14": 25.0,
                "rsi14": 55.0,
                "volume_ratio": 1.2,
            },
        }


def _bull(sym: str) -> pd.DataFrame:
    n = 400
    dates = pd.bdate_range("2024-01-02", periods=n)
    rets = np.array([0.008 if i % 14 < 11 else -0.015 for i in range(n)])
    close = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": 2_000_000 * np.linspace(1.0, 2.2, n),
        },
        index=dates,
    )


@pytest.fixture
def ctx(monkeypatch, tmp_path):
    """Contexto fake: 3 símbolos (2 con señal, 1 sin), régimen 1."""
    price_data = {s: _bull(s) for s in ["TESTA", "TESTB", "TESTC"]}
    monkeypatch.setattr(
        advisor,
        "_load_context",
        lambda: (
            price_data,
            pd.Timestamp("2026-08-17"),
            {"state": 1, "state_name": "REFLATION", "confidence": 0.8},
            1,
            FakeSignalEngine(),
            FakeCalibrator(fitted=True, prob=0.72),
            FakeConformal(),
        ),
    )
    monkeypatch.setattr(advisor, "_cache_date", lambda: pd.Timestamp("2026-08-14"))
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH", str(tmp_path / "decision_states.json"))
    monkeypatch.setattr(advisor, "_theses_path", lambda: str(tmp_path / "decision_theses.json"))
    return price_data


def _set_win_prob(monkeypatch, prob, fitted=True):
    """Redirige _compute_ticket del módulo advisor para pinchar el win_prob."""
    original = advisor._compute_ticket

    def patched(symbol, df, regime_state, today, signal_engine, calibrator, conformal, sig=None):
        t = original(symbol, df, regime_state, today, signal_engine, calibrator, conformal, sig=sig)
        if t["win_prob"] is not None:
            t["win_prob"] = round(prob, 4)
        return t

    monkeypatch.setattr(advisor, "_compute_ticket", patched)


# --- Mapeo de etiquetas §29 (función pura: exacta, con n) ---

@pytest.mark.parametrize(
    "wp,fitted,label,n",
    [
        (0.72, True, "GANANCIA_PROYECTADA_ALTA", 8),
        (0.70, True, "GANANCIA_PROYECTADA_ALTA", 8),
        (0.6999, True, "GANANCIA_PROYECTADA", 19),
        (0.65, True, "GANANCIA_PROYECTADA", 19),
        (0.6499, True, "NEUTRO", 0),
        (0.50, True, "NEUTRO", 0),
        (0.45, True, "NEUTRO", 0),
        (0.4499, True, "RIESGOSA_SIN_APOYO", 0),
        (0.10, True, "RIESGOSA_SIN_APOYO", 0),
        (None, True, "SIN_SCORE", 0),
        (None, False, "SIN_CALIBRAR", 0),
    ],
)
def test_projected_label_mapping_pre_registrado(wp, fitted, label, n):
    out = advisor._projected_label(wp, fitted)
    assert out["label"] == label, f"wp={wp} -> {out['label']}, esperado {label}"
    assert out["n"] == n


def test_projected_label_nunca_inventa_perdida():
    """Regla §29: la cola baja NO dice 'pérdida proyectada' (no hay evidencia)."""
    out = advisor._projected_label(0.10, True)
    assert "pérdida" not in out["label"].lower()
    assert "apoyo" in out["evidence"]


# --- GET /api/advisor/universe ---

def test_universe_structure_and_honesty(ctx, monkeypatch):
    body = asyncio.run(advisor.advisor_universe())

    assert body["as_of"] == "2026-08-17"
    assert body["regime"]["state"] == 1
    assert body["blocked_reason"] is None
    assert body["honesty_badge"].startswith("Apoyo a decisión")
    assert body["risk_params"]["absolute_ceiling"] > 0
    st = body["staleness"]
    assert st["last_cache"] == "2026-08-14"
    assert st["stale"] is False
    assert st["business_days_behind"] == 1

    syms = {t["symbol"] for t in body["states"]}
    assert syms == {"TESTA", "TESTB", "TESTC"}
    for t in body["states"]:
        for key in ("state", "reason", "win_prob", "projected", "last_close",
                    "dist_ema50", "dist_ema200", "transition"):
            assert key in t
        assert t["projected"]["label"] in (
            "GANANCIA_PROYECTADA_ALTA", "GANANCIA_PROYECTADA", "NEUTRO",
            "RIESGOSA_SIN_APOYO", "SIN_SCORE", "SIN_CALIBRAR",
        )

    # orden: INVERTIR primero (TESTA pasa el gate fake), NO_INVERTIR al final
    state_seq = [t["state"] for t in body["states"]]
    ranks = [{"NO_INVERTIR": 0, "VIGILAR": 1, "INVERTIR": 2}[s] for s in state_seq]
    assert ranks == sorted(ranks, reverse=True)


def test_universe_blocked_regime_3(monkeypatch, tmp_path):
    price_data = {s: _bull(s) for s in ["TESTA", "TESTB"]}
    monkeypatch.setattr(
        advisor,
        "_load_context",
        lambda: (
            price_data,
            pd.Timestamp("2026-08-17"),
            {"state": 3, "state_name": "DEFLATION", "confidence": 0.95},
            3,
            FakeSignalEngine(),
            FakeCalibrator(),
            FakeConformal(),
        ),
    )
    monkeypatch.setattr(advisor, "_cache_date", lambda: pd.Timestamp("2026-08-14"))
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH", str(tmp_path / "ds.json"))
    body = asyncio.run(advisor.advisor_universe())
    assert body["regime"]["state"] == 3
    assert body["blocked_reason"] is not None
    assert all(t["state"] == "NO_INVERTIR" for t in body["states"])


def test_universe_stale_flag(monkeypatch, tmp_path, ctx):
    """Cache con >2 ruedas hábiles de atraso -> stale=True (UI debe avisar)."""
    monkeypatch.setattr(advisor, "_cache_date", lambda: pd.Timestamp("2026-08-07"))
    body = asyncio.run(advisor.advisor_universe())
    assert body["staleness"]["stale"] is True
    assert body["staleness"]["business_days_behind"] > 2


# --- GET /api/advisor/{symbol} ---

def test_symbol_detail_ohlcv_and_overlays(ctx, monkeypatch):
    body = asyncio.run(advisor.advisor_symbol("TESTA"))
    t = body["state"]
    assert t["symbol"] == "TESTA"
    assert len(t["ohlcv"]) == 400
    bar = t["ohlcv"][-1]
    for key in ("date", "open", "high", "low", "close", "ema50", "ema200"):
        assert key in bar
    assert t["ohlcv"][-1]["ema50"] is not None
    assert t["exit_plan"]["partial_tp"]["trigger"] == "precio >= entrada + 2*ATR"
    assert t["projected"]["label"] == "GANANCIA_PROYECTADA_ALTA"
    # sin cobertura EDGAR para TESTA -> null honesto, nunca inventado
    assert t["fundamentals"] is None
    assert t["fundamentals_coverage"] == "sin_cobertura_edgar"


def test_symbol_404_fuera_universo(ctx):
    with pytest.raises(Exception) as exc:
        asyncio.run(advisor.advisor_symbol("NOEXISTE"))
    assert "404" in str(exc.value.status_code) or exc.value.status_code == 404


# --- GET /api/advisor/theses (Exit Thesis Monitor) ---

def test_theses_captura_snapshot_al_invertir(ctx):
    """Primera llamada: TESTA es INVERTIR (gate fake) -> crea tesis."""
    body = asyncio.run(advisor.advisor_theses())
    syms = {t["symbol"] for t in body["theses"]}
    # la primera corrida crea los snapshots; la segunda ya los evalúa
    body2 = asyncio.run(advisor.advisor_theses())
    evaluated = {t["symbol"]: t for t in body2["theses"]}
    assert "TESTA" in evaluated
    assert evaluated["TESTA"]["status"] in (
        "TESIS_VIGENTE", "TESIS_DEGRADADA", "TESIS_ROTA")
    assert syms == set()  # primera llamada devuelve tesis previas (vacías)


def test_theses_rota_por_stop(monkeypatch, tmp_path):
    """Tesis con stop ya cruzado por el precio actual -> TESIS_ROTA."""
    price_data = {"TESTA": _bull("TESTA")}
    last_close = float(price_data["TESTA"]["close"].iloc[-1])

    monkeypatch.setattr(
        advisor,
        "_load_context",
        lambda: (
            price_data,
            pd.Timestamp("2026-08-17"),
            {"state": 1, "state_name": "REFLATION", "confidence": 0.8},
            1,
            FakeSignalEngine(),
            FakeCalibrator(),
            FakeConformal(),
        ),
    )
    monkeypatch.setattr(advisor, "DECISION_STATES_PATH", str(tmp_path / "ds.json"))
    theses_path = str(tmp_path / "decision_theses.json")
    monkeypatch.setattr(advisor, "_theses_path", lambda: theses_path)
    # tesis pre-cargada con stop ARRIBA del precio actual -> ya cruzado
    advisor._persist_theses({
        "TESTA": {
            "entry_date": "2026-08-10",
            "score": 0.65,
            "win_prob": 0.70,
            "entry_price": last_close * 1.05,
            "stop_loss": last_close * 1.02,
            "take_profit": last_close * 1.20,
            "gates": {"trend_ok": True, "adx": 25.0, "rsi": 55.0, "volume_ratio": 1.2},
        }
    })
    body = asyncio.run(advisor.advisor_theses())
    t = {x["symbol"]: x for x in body["theses"]}["TESTA"]
    assert t["status"] == "TESIS_ROTA"
    assert any("stop" in r for r in t["reasons"])


def test_evidence_tolerante_a_umbral_string(monkeypatch, ctx):
    """Entradas viejas del ledger guardaron umbral_aplicado como str —
    el endpoint debe tolerarlo, no caer (verificado contra el registro real)."""
    fake_entries = [
        {"id": "t1", "fecha": "2026-08-10", "familia": "signal_diagnosis",
         "hipotesis": "x", "n_trials_consumidos": 1, "umbral_aplicado": "0.90",
         "veredicto": "NO_CUMPLE", "artefacto": "a", "seccion_doc": "§20"},
    ]
    monkeypatch.setattr(advisor.trial_registry, "all_trials", lambda path=None: fake_entries)
    monkeypatch.setattr(advisor.trial_registry, "consumed_budget",
                        lambda fam, path=None: 1)
    body = asyncio.run(advisor.advisor_evidence())
    assert body["families"][0]["umbral_aplicado_ultimo"] == 0.90


# --- GET /api/advisor/evidence ---

def test_evidence_reads_ledger(monkeypatch, ctx):
    fake_entries = [
        {"id": "t1", "fecha": "2026-08-10", "familia": "signal_diagnosis",
         "hipotesis": "x", "n_trials_consumidos": 1, "umbral_aplicado": 0.90,
         "veredicto": "NO_CUMPLE", "artefacto": "a", "seccion_doc": "§20"},
        {"id": "t2", "fecha": "2026-08-17", "familia": "signal_diagnosis",
         "hipotesis": "y", "n_trials_consumidos": 1, "umbral_aplicado": 0.99,
         "veredicto": "NO_CUMPLE", "artefacto": "b", "seccion_doc": "§27"},
    ]
    monkeypatch.setattr(advisor.trial_registry, "all_trials", lambda path=None: fake_entries)
    monkeypatch.setattr(advisor.trial_registry, "consumed_budget",
                        lambda fam, path=None: 2)
    body = asyncio.run(advisor.advisor_evidence())
    assert body["total_trials"] == 2
    fams = {f["familia"]: f for f in body["families"]}
    assert fams["signal_diagnosis"]["n_consumidos"] == 2
    assert body["recent"][0]["id"] == "t2"  # más reciente primero
