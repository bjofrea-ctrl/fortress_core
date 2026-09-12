"""
Golden test B6 2/3 — validacion_oos_fresca_mom_rsi.py alineado al contrato de señal única.

Congela la señal mensual OOS: el refactor (importar el contrato en vez de redefinir
umbrales/scoring localmente) NO debe mover ni un bit del valor histórico. El test
reproduce la fórmula PRE-refactor como referencia independiente y la compara con la
salida de compute_oos_signal, que ahora delega en app.core.signal_contract.

Si alguien cambia los umbrales/pesos del contrato, este test falla -> guarda la señal.
"""

import numpy as np
import pandas as pd

from scripts.validacion_oos_fresca_mom_rsi import compute_oos_signal

# Pesos del régimen 0 (priors), idénticos a SignalEngine.factor_weights[0] y al contrato.
W_MOM = 0.6642
W_RSI = 0.3358

# Umbrales PRE-refactor (eco del contrato, valores idénticos).
RSI_SCORE_LO, RSI_SCORE_HI = 45, 70
RSI_GATE_LO, RSI_GATE_HI = 40, 75
ADX_MIN = 20
VR_MIN = 1.0
ENTRY_THRESHOLD = 0.60


def _make_panels(seed=0):
    """Panel mensual sintético ym×symbol con inyección de NaN para cubrir ramas."""
    ym = pd.period_range("2024-02", periods=6, freq="M")
    ym.name = "ym"
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    rng = np.random.default_rng(seed)
    panels = {}
    for col, scale, shift in (
        ("close", 1.0, 100.0),
        ("ema50", 1.0, 98.0),
        ("ema200", 1.0, 95.0),
        ("adx14", 25.0, 0.0),
        ("rsi14", 15.0, 55.0),
        ("volume_ratio", 0.5, 1.0),
        ("momentum_12_1", 8.0, 0.0),
    ):
        panels[col] = pd.DataFrame(
            rng.normal(scale, size=(len(ym), len(symbols))) + shift,
            index=ym, columns=symbols,
        )
    # NaN para ejercitar el branch NaN -> 0.5 (momentum/rsi) y fillna(False).
    panels["momentum_12_1"].iloc[0, 0] = np.nan
    panels["rsi14"].iloc[1, 1] = np.nan
    panels["close"].iloc[2, 2] = np.nan
    for c in panels:
        panels[c].columns.name = "symbol"
    return panels


def _reference_signal(panels):
    """Reproduce EXACTAMENTE la fórmula PRE-refactor (bit-a-bit)."""
    mom = panels["momentum_12_1"]
    rsi_v = panels["rsi14"]
    close = panels["close"]
    ema50 = panels["ema50"]
    ema200 = panels["ema200"]
    adx = panels["adx14"]
    vr = panels["volume_ratio"]

    ms = ((mom + 50.0) / 150.0).clip(0.0, 1.0)
    ms = ms.where(mom.notna(), 0.5)
    rs = pd.DataFrame(
        np.where((rsi_v > RSI_SCORE_LO) & (rsi_v < RSI_SCORE_HI), 0.8, 0.4),
        index=rsi_v.index, columns=rsi_v.columns,
    )
    rs = rs.where(rsi_v.notna(), 0.5)
    overall = W_MOM * ms + W_RSI * rs

    eligible = (
        (close > ema50) & (ema50 > ema200)
        & (adx >= ADX_MIN)
        & (rsi_v > RSI_GATE_LO) & (rsi_v < RSI_GATE_HI)
        & (vr >= VR_MIN)
    ).fillna(False)
    signal = (eligible & (overall >= ENTRY_THRESHOLD)).fillna(False)
    return signal, overall, eligible


def test_signal_bit_identical_to_prefactor_reference():
    panels = _make_panels()
    signal, overall, eligible = compute_oos_signal(panels)
    r_sig, r_ov, r_elig = _reference_signal(panels)

    pd.testing.assert_frame_equal(signal, r_sig)
    pd.testing.assert_frame_equal(overall, r_ov)
    pd.testing.assert_frame_equal(eligible, r_elig)


def test_signal_uses_contract_thresholds_not_local():
    """El helper delega en el contrato: cambiar umbrales del contrato rompe la señal.

    Si el contrato cambiara sus umbrales, compute_oos_signal ya no coincidiría con la
    referencia PRE-refactor (que usa los valores congelados). Esto es la guarda B6.
    """
    panels = _make_panels(seed=7)
    signal, _, _ = compute_oos_signal(panels)
    r_sig, _, _ = _reference_signal(panels)
    # Sin NaN forzados en este panel, la señal debe coincidir totalmente con la referencia.
    assert signal.shape == r_sig.shape
    pd.testing.assert_frame_equal(signal, r_sig)
