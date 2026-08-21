"""T1.3 — PLAN_INTEGRACION_INDICAGENT.md: tests del módulo market_structure (SMC).

Criterios de aceptación del ticket:
1. Test por detector con casos sintéticos mínimos (FVG de 3 velas exactas, etc.).
2. Test de mitigación: zona detectada se marca mitigada/reclaimed cuando barras
   posteriores vuelven a operar la zona.
3. Los 4 detectores sobre un símbolo real completo no rompen con NaN/None cuando
   no hay suficiente historia (min_lookback: 50 OB, 30 FVG, 60 BOS/sweeps).
"""
import numpy as np
import pandas as pd
from app.core.market_structure import (
    MIN_LOOKBACK_BOS_CHOCH,
    MIN_LOOKBACK_FVG,
    MIN_LOOKBACK_SWEEPS,
    analyze_market_structure,
    detect_bos_choch,
    detect_fair_value_gaps,
    detect_liquidity_sweeps,
    detect_order_blocks,
    find_swing_highs,
    find_swing_lows,
)


def _df_from_arrays(open_, high, low, close):
    n = len(close)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close},
        index=pd.bdate_range("2023-01-02", periods=n),
    )


# ============================================================
# Swings (infraestructura)
# ============================================================

def test_find_swing_highs_detecta_el_maximo_local():
    arr = np.array([100.0] * 5 + [120.0] + [100.0] * 5)
    assert find_swing_highs(arr, neighbor=5) == [5]
    # el mismo array visto como lows da un swing low en el MÍNIMO (no en las mesetas)
    lows = np.where(arr == 120.0, 100.0, 100.0)
    lows = np.array([100.0] * 5 + [80.0] + [100.0] * 5)
    assert find_swing_lows(lows, neighbor=5) == [5]


def test_find_swings_no_reporta_los_bordes():
    """Un máximo en el borde no es swing (no puede ser roto después)."""
    arr = np.concatenate([[130.0], np.full(10, 100.0)])
    assert find_swing_highs(arr, neighbor=5) == []


# ============================================================
# 1. Order Blocks
# ============================================================

def _ob_df(mitigated: bool = False) -> pd.DataFrame:
    """30 barras base planas + 1 vela bajista (OB) + 3 velas de impulso alcista
    + barras posteriores que (no) vuelven a la zona."""
    n = 60
    open_ = np.full(n, 100.0)
    close = np.full(n, 100.0)
    high = np.full(n, 100.2)
    low = np.full(n, 99.8)
    b = 30  # vela OB
    open_[b], close[b], high[b], low[b] = 100.5, 99.5, 101.0, 99.0
    # impulso alcista: 3 velas con movimiento >> min_move_pct
    for k, (o, c, h, lw) in enumerate([
        (99.6, 103.0, 103.5, 99.3),
        (103.2, 107.0, 107.5, 103.0),
        (107.2, 111.0, 111.5, 107.0),
    ]):
        i = b + 1 + k
        open_[i], close[i], high[i], low[i] = o, c, h, lw
    # barras posteriores
    if mitigated:
        # vuelven a operar la zona (99.5-100.5): barra con low 99.6, high 100.2
        open_[b + 5], close[b + 5], high[b + 5], low[b + 5] = 109.0, 100.0, 100.2, 99.6
    for i in range(b + 4, n):
        if mitigated and i == b + 5:
            continue
        open_[i], close[i], high[i], low[i] = 110.5, 111.5, 112.0, 109.5
    return _df_from_arrays(open_, high, low, close)


def test_detect_order_blocks_bullish_no_mitigado():
    df = _ob_df(mitigated=False)
    res = detect_order_blocks(df)
    assert res["ob_detected"] is True
    assert res["ob_type"] == 1  # impulsó ALCISTA (vela OB bajista antes)
    assert res["ob_top"] == 100.5 and res["ob_bottom"] == 99.5  # cuerpo de la OB
    assert res["ob_mitigated"] is False
    assert 0.0 < res["ob_strength"] <= 1.0
    assert res["ob_distance_pct"] > 0  # precio final muy por encima de la zona


def test_detect_order_blocks_mitigado_cuando_el_precio_vuelve_a_la_zona():
    """Criterio 2: la zona se marca mitigada cuando barras posteriores la operan."""
    df = _ob_df(mitigated=True)
    res = detect_order_blocks(df)
    assert res["ob_detected"] is True
    assert res["ob_mitigated"] is True


def test_detect_order_blocks_historial_insuficiente():
    df = _ob_df().iloc[:20]  # < 50 barras
    res = detect_order_blocks(df)
    assert res["ob_detected"] is False
    assert res["ob_type"] == 0


# ============================================================
# 2. Fair Value Gaps
# ============================================================

def _fvg_df(fill: bool = False) -> pd.DataFrame:
    """Paso suave (sin gaps) + patrón de 3 velas que deja un FVG alcista en la
    vela media m, con zona esperada (high[m-1], low[m+1]) = (111.0, 116.0)."""
    n = 45
    close = 100.0 + 0.5 * np.arange(n)          # 100, 100.5, ..., 122
    open_ = close - 0.2
    high = close + 1.0                           # high[m-1] = 111.0 con m=20
    low = close - 1.0                            # low[m+1]  = 116.0 con m=20
    m = 20  # vela media del patrón
    high[m - 1] = 111.0
    low[m - 1] = 108.0
    open_[m], close[m], high[m], low[m] = 110.5, 112.5, 113.0, 109.5
    open_[m + 1], close[m + 1], high[m + 1], low[m + 1] = 116.5, 118.0, 118.5, 116.0
    # resto plano lejos de la zona
    for i in range(m + 2, n):
        open_[i], close[i], high[i], low[i] = 119.0, 119.5, 120.0, 118.5
    if fill:
        # barra posterior opera DENTRO de la zona (111.0, 116.0) → rellenada
        open_[m + 2], close[m + 2], high[m + 2], low[m + 2] = 118.5, 113.5, 118.8, 113.0
    return _df_from_arrays(open_, high, low, close)


def test_detect_fvg_exact_3balas_bullish():
    """Criterio 1: 3 velas exactas que forman un gap conocido -> top/bottom correctos."""
    df = _fvg_df(fill=False)
    res = detect_fair_value_gaps(df)
    assert res["fvg_detected"] is True
    assert res["fvg_type"] == 1
    # zona del fixture: (high[m-1]=111.0, low[m+1]=116.0)
    assert abs(res["fvg_bottom"] - 111.0) < 1e-9
    assert abs(res["fvg_top"] - 116.0) < 1e-9
    assert res["fvg_open_count"] >= 1


def test_detect_fvg_filled_disappece_del_abierto():
    """Criterio 2: una zona FVG rellenada deja de reportarse como abierta."""
    df = _fvg_df(fill=True)
    res = detect_fair_value_gaps(df)
    # El único gap del fixture fue rellenado -> no hay FVG abiertos
    assert res["fvg_detected"] is False
    assert res["fvg_open_count"] == 0


def test_detect_fvg_historial_insuficiente():
    df = _fvg_df().iloc[:10]  # < 30 barras
    assert detect_fair_value_gaps(df)["fvg_detected"] is False


# ============================================================
# 3. BOS / CHoCH
# ============================================================

def _bos_df(last_close: float) -> pd.DataFrame:
    """70 barras: swing highs 120/125/130 en idx 10/25/55, swing lows 80/85/90
    en idx 17/32/47 → tendencia ALCISTA (HH+HL). El último cierre decide BOS."""
    n = 70
    high = np.full(n, 100.0)
    low = np.full(n, 100.0)
    close = np.full(n, 100.0)
    open_ = np.full(n, 100.0)
    for i, v in ((10, 120.0), (25, 125.0), (55, 130.0)):
        high[i] = v
    for i, v in ((17, 80.0), (32, 85.0), (47, 90.0)):
        low[i] = v
    close[-1] = last_close
    high[-1] = max(last_close, 101.0)
    low[-1] = min(last_close, 99.0)
    open_[-1] = 100.0
    return _df_from_arrays(open_, high, low, close)


def test_bos_alcista_en_tendencia_alcista_no_es_choch():
    res = detect_bos_choch(_bos_df(last_close=131.0))
    assert res["bos_detected"] is True
    assert res["bos_direction"] == 1
    assert res["bos_level"] == 130.0  # el último swing high
    assert res["choch_detected"] is False  # misma dirección que la tendencia
    assert res["smc_trend_direction"] == 1


def test_choch_cuando_la_ruptura_va_contra_la_tendencia():
    res = detect_bos_choch(_bos_df(last_close=78.0))  # debajo del swing low 90
    assert res["bos_detected"] is True
    assert res["bos_direction"] == -1
    assert res["bos_level"] == 90.0
    assert res["choch_detected"] is True
    assert res["choch_direction"] == -1
    assert res["smc_trend_direction"] == 1


def test_bos_con_atr_normaliza_la_fuerza():
    atr = pd.Series(np.full(70, 2.0), index=pd.bdate_range("2023-01-02", periods=70))
    res = detect_bos_choch(_bos_df(last_close=133.0), atr=atr)
    # 133 - 130 = 3 → strength = 3/2 = 1.5
    assert abs(res["bos_strength"] - 1.5) < 1e-9


def test_bos_historial_insuficiente():
    assert detect_bos_choch(_bos_df(100.0).iloc[:30])["bos_detected"] is False


# ============================================================
# 4. Liquidity Sweeps
# ============================================================

def _sweep_df(reclaim: bool = True) -> pd.DataFrame:
    """70 barras planas (100), swing low en idx 20 (low=80), vela de sweep en
    idx 30 (mecha 79.5, cierre 81). Si reclaim=True, los 3 cierres siguientes
    confirman por encima del nivel; si reclaim=False, cierran DEBAJO (80) —
    sin confirmación de recuperación."""
    n = 70
    open_ = np.full(n, 100.0)
    high = np.full(n, 101.0)
    low = np.full(n, 99.0)
    close = np.full(n, 100.0)
    low[20] = 80.0  # swing low: 5 barras mayores a cada lado (todas 99)
    close[20] = 82.0
    open_[20] = 100.0
    high[20] = 101.0
    # sweep bullish: mecha perfora 80 pero cierra arriba
    open_[30], close[30], high[30], low[30] = 99.5, 81.0, 100.5, 79.5
    for k in (31, 32, 33):
        if reclaim:
            open_[k], close[k], high[k], low[k] = 82.0, 83.0, 83.5, 81.5
        else:
            open_[k], close[k], high[k], low[k] = 80.5, 79.5, 80.8, 79.0
    return _df_from_arrays(open_, high, low, close)


def test_sweep_bullish_detectado_y_reclaimed():
    """Criterios 1+2: mecha perfora el swing low y cierre adentro; barras
    siguientes confirman → reclaimed=True."""
    res = detect_liquidity_sweeps(_sweep_df(reclaim=True))
    assert res["sweep_detected"] is True
    assert res["sweep_type"] == 1
    assert res["sweep_level"] == 80.0
    assert res["sweep_reclaimed"] is True
    assert res["sweep_depth_pct"] > 0
    assert res["sweep_strength"] > 0


def test_sweep_sin_confirmacion_no_reclaimed():
    res = detect_liquidity_sweeps(_sweep_df(reclaim=False))
    assert res["sweep_detected"] is True
    assert res["sweep_type"] == 1
    assert res["sweep_reclaimed"] is False


def test_sweep_historial_insuficiente():
    assert detect_liquidity_sweeps(_sweep_df().iloc[:20])["sweep_detected"] is False


# ============================================================
# 3/4. Detector conjunto sobre símbolo real + min_lookbacks
# ============================================================

def test_analyze_market_structure_real_symbol_no_crash(ohlcv_df):
    """Criterio 3: los detectores no rompen con NaN/None sobre un panel real
    completo (400 barras sintéticas con tendencia + ruido)."""
    res = analyze_market_structure(ohlcv_df, atr=ohlcv_df["close"].rolling(14).std())
    for key in ("order_block", "fair_value_gap", "bos_choch", "liquidity_sweep",
                "nearest_swing_low", "nearest_resistance"):
        assert key in res
    # los detectores devuelven bools consistentes, nunca valores rotos
    for det in ("order_block", "fair_value_gap", "bos_choch", "liquidity_sweep"):
        assert isinstance(res[det].get("ob_detected",
                                       res[det].get("fvg_detected",
                                                    res[det].get("bos_detected",
                                                                 res[det].get("sweep_detected")))), bool)
    for k in ("nearest_swing_low", "nearest_resistance"):
        assert res[k] is None or isinstance(res[k], float)


def test_analyze_market_structure_short_history_clean_empty(ohlcv_df):
    """Con menos history que el lookback mínimo → dict 'vacío' consistente."""
    short = ohlcv_df.iloc[:5]
    res = analyze_market_structure(short)
    assert res["order_block"]["ob_detected"] is False
    assert res["fair_value_gap"]["fvg_detected"] is False
    assert res["bos_choch"]["bos_detected"] is False
    assert res["liquidity_sweep"]["sweep_detected"] is False
    assert res["nearest_swing_low"] is None
    assert res["nearest_resistance"] is None


def test_min_lookbacks_constants_match_ticket():
    assert MIN_LOOKBACK_FVG == 30
    assert MIN_LOOKBACK_BOS_CHOCH == 60
    assert MIN_LOOKBACK_SWEEPS == 60
    from app.core.market_structure import MIN_LOOKBACK_ORDER_BLOCKS
    assert MIN_LOOKBACK_ORDER_BLOCKS == 50


# ============================================================
# T1.4 — market_structure_history: serie causal per-fecha (sin look-ahead)
# ============================================================

def test_history_causal_no_sabe_el_futuro(_ob_df=_ob_df):  # noqa: F841 (alias)
    """Invariante causal: la fila de la fecha t es idéntica si se computa sobre
    la serie truncada a t o sobre la serie completa (aplicando el prefijo el
    detector bowwow no puede mirar más allá de t)."""
    from app.core.market_structure import market_structure_history
    df = _ob_df(mitigated=False)
    full = market_structure_history(df)
    t = df.index[len(df) // 2]
    truncated = market_structure_history(df.loc[:t])
    # columnas numéricas clave coinciden en el prefijo [0..t]
    for col in ("ob_type", "ob_top", "ob_bottom", "fvg_type", "fvg_top",
                "nearest_swing_low", "nearest_resistance", "sweep_type"):
        a = full.loc[:t, col]
        b = truncated.loc[:t, col]
        eq = ((a.values == b.values)
              | (np.isnan(a.values.astype(float)) & np.isnan(b.values.astype(float))))
        assert eq.all(), f"columna {col} difiere entre serie completa y truncada a {t}"


def test_history_mitigation_appece_recien_en_la_barra_que_toca_la_zona(_ob_df=_ob_df):  # noqa: F841
    """La mitigación de un OB es causal: False en las barras del impulso, True
    recién desde la barra que efectivamente opera dentro de la zona."""
    from app.core.market_structure import market_structure_history
    df = _ob_df(mitigated=True)
    hist = market_structure_history(df)
    b = 30  # barra OB del fixture; impulso en 31..33; mitigación en 35
    # antes y durante el impulso: no mitigado (la barra del OB aún "vive")
    assert bool(hist["ob_mitigated"].iloc[32]) is False
    # en la barra que toca la zona: ya mitigado
    assert bool(hist["ob_type"].iloc[35] != 0)
    assert bool(hist["ob_mitigated"].iloc[35]) is True


def test_history_length_and_index_match_input():
    from app.core.market_structure import market_structure_history
    n = 80
    idx = pd.bdate_range("2023-01-02", periods=n)
    df = pd.DataFrame({
        "open": np.full(n, 100.0), "high": np.full(n, 101.0),
        "low": np.full(n, 99.0), "close": np.full(n, 100.0),
    }, index=idx)
    hist = market_structure_history(df)
    assert len(hist) == n
    assert hist.index.equals(idx)


def test_structure_row_to_dict_roundtrip():
    """fila -> dict consumible por generate_signal con el shape exacto."""
    from app.core.market_structure import (
        market_structure_history, structure_row_to_dict,
    )
    df = _ob_df(mitigated=False)
    hist = market_structure_history(df)
    d = structure_row_to_dict(hist.iloc[-1])
    for key in ("order_block", "fair_value_gap", "bos_choch", "liquidity_sweep",
                "nearest_swing_low", "nearest_resistance"):
        assert key in d
    assert isinstance(d["order_block"]["ob_detected"], bool)
    assert "ob_bottom" in d["order_block"]
    assert "fvg_bottom" in d["fair_value_gap"]


_ob_df_fixture = _ob_df  # deja accesible el helper para los tests de arriba


def test_market_structure_history_real_symbol_lenghtiado(ohlcv_df):
    """Humo real: 400 barras sintéticas → serie completa sin excepciones."""
    from app.core.market_structure import market_structure_history
    hist = market_structure_history(
        ohlcv_df, atr=ohlcv_df["close"].rolling(14).std())
    assert len(hist) == len(ohlcv_df)
    # las columnas numéricas son finitas o NaN, nunca excepciones
    assert np.isfinite(hist["fvg_open_count"]).all()
