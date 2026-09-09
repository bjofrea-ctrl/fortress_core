"""
Tests del feature store versionado (B3 / I6).

Criterio de éxito pre-registrado (ver B3_PREREGISTRO.md):
- write_panel preserva el dataframe BIT-A-BIT (sin cambio de resultados).
- version determinista (mismo df -> mismo sha12) y manifest dedupa.
- load_panel lee por versión; fallback legacy no rompe consumidores viejos.
- build_factor_panel y diagnose_ic_by_regime importan el refactor sin error.
- Los dos "bootstrap" NO son duplicados reales: distinto algoritmo y contrato.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core import feature_store as fs
from app.core.probabilistic_engine import circular_block_bootstrap_ci


def _load_script(name):
    path = BACKEND / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_t_{name}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_df():
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"] * 2),
        "symbol": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"],
        "momentum_score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
        "rsi_score": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "trend_score": [1, 2, 3, 4, 5, 6],
        "adx_score": [1.1, 1.2, 1.3, 1.4, 1.5, 1.6],
        "sentiment_v1": [0.0, 0.1, np.nan, 0.2, 0.3, 0.4],
        "macro_composite": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "dxy_ret_20d": [1, 2, 3, 4, 5, 6],
        "gold_ret_20d": [1, 2, 3, 4, 5, 6],
        "spy_ret_50d": [1, 2, 3, 4, 5, 6],
        "oil_ret_20d": [1, 2, 3, 4, 5, 6],
        "regime": [0, 1, 2, 0, 1, 2],
        "fwd_return_20d": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
        "eligible": [True, True, True, False, True, True],
    })


def test_write_load_roundtrip_preserves_dataframe(tmp_path):
    df = _make_df()
    entry = fs.write_panel(df, repo_root=str(tmp_path))
    assert entry["version"] and len(entry["version"]) == 12
    assert (tmp_path / "data" / "cache" / f"factor_panel_{entry['version']}.parquet").exists()
    assert (tmp_path / "data" / "cache" / "manifest.json").exists()

    loaded, e2 = fs.latest_panel(repo_root=str(tmp_path))
    cols = list(df.columns)
    # Contenido BIT-A-BIT idéntico (sin cambio de resultados)
    pd.testing.assert_frame_equal(
        loaded[cols].reset_index(drop=True), df[cols].reset_index(drop=True)
    )
    assert e2["version"] == entry["version"]
    assert set(e2["columns"]) == set(cols)
    assert e2["universe"] == ["AAA", "BBB"]
    assert e2["date_min"] == "2024-01-01 00:00:00"


def test_version_deterministic_and_manifest_dedupes(tmp_path):
    df = _make_df()
    e1 = fs.write_panel(df, repo_root=str(tmp_path))
    e2 = fs.write_panel(df, repo_root=str(tmp_path))  # mismo df -> mismo hash
    assert e1["version"] == e2["version"]
    idx = fs.panel_index(repo_root=str(tmp_path))
    assert len(idx) == 1  # dedupe por version


def test_load_by_explicit_version(tmp_path):
    df = _make_df()
    e = fs.write_panel(df, repo_root=str(tmp_path))
    loaded, ent = fs.load_panel(version=e["version"], repo_root=str(tmp_path))
    assert ent["version"] == e["version"]
    cols = list(df.columns)
    pd.testing.assert_frame_equal(
        loaded[cols].reset_index(drop=True), df[cols].reset_index(drop=True)
    )
    with pytest.raises(KeyError):
        fs.load_panel(version="deadbeefdead", repo_root=str(tmp_path))


def test_legacy_fallback_when_no_manifest(tmp_path):
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True)
    leg = pd.DataFrame({"a": [1, 2], "date": ["2024-01-01", "2024-01-02"]})
    leg.to_parquet(cache / "factor_panel_20260101_000000.parquet", index=False)
    loaded, ent = fs.latest_panel(repo_root=str(tmp_path))
    assert ent["version"] == "legacy"
    assert list(loaded.columns) == ["a", "date"]


def test_build_factor_panel_refactor_writes_versioned(tmp_path, monkeypatch):
    # El refactor cablea write_panel; main() debe escribir versionado + manifest
    # con el MISMO esquema de columnas que antes (sin cambio de resultados).
    bfp = _load_script("build_factor_panel")
    assert "write_panel" in dir(bfp)

    import app.core.feature_store as fsmod
    monkeypatch.setattr(fsmod, "_repo_root", lambda: tmp_path)

    n = 260
    idx = pd.date_range("2019-01-01", periods=n, freq="D")

    def fake_load(tickers, start, end):
        out = {}
        for t in tickers:
            out[t] = pd.DataFrame({
                "open": np.linspace(100, 200, n),
                "high": np.linspace(102, 202, n),
                "low": np.linspace(98, 198, n),
                "close": np.linspace(100, 200, n),
                "volume": np.full(n, 1_000_000, dtype=float),
            }, index=idx)
        return out

    monkeypatch.setattr("app.core.data_ingestion.load_universe", fake_load)
    monkeypatch.setattr(bfp, "SYMBOLS", ["SPY"])
    monkeypatch.setattr(bfp, "MARKET_TICKERS", ["SPY"])

    # Stubs para dependencias externas / costosas (sentiment, regime HMM, macro).
    # NO stubbiamos compute_factor_frame/calculate_all_indicators: es el código
    # real del panel que queremos ejercitar.
    bfp.build_sentiment_frame = lambda dates: pd.DataFrame(
        {"aaii_bullbear_spread": pd.Series(np.nan, index=dates)}
    )

    class _StubRegime:
        def fit(self, *a, **k):
            return None

        def predict_current_regime(self, *a, **k):
            return {"state": 0}

    bfp.GlobalRegimeClassifier = _StubRegime

    class _StubPred:
        def _macro_signals(self, *a, **k):
            return None, 0.5

    bfp.PredictiveEngine = _StubPred

    bfp.main()

    idx_after = fs.panel_index(repo_root=str(tmp_path))
    assert len(idx_after) >= 1
    assert idx_after[0]["meta"]["source"] == "build_factor_panel"
    # build_factor_panel sigue emitiendo las columnas del contrato del panel
    assert "fwd_return_20d" in idx_after[0]["columns"]
    assert "eligible" in idx_after[0]["columns"]


def test_diagnose_consumer_migration_imports_clean():
    # diagnose_ic_by_regime ahora consume por versión vía latest_panel().
    diag = _load_script("diagnose_ic_by_regime")
    assert "latest_panel" in dir(diag)


def test_bootstrap_copies_are_not_interchangeable():
    """B3: las dos 'copias' de bootstrap NO son duplicados reales.

    circular_block_bootstrap_ci = block-circular sobre un array de retornos
    (preserva autocorrelación). _boot_ci = bootstrap simple sobre pares de
    trades con random.Random. Distinto algoritmo y distinto contrato de
    entrada -> NO se pueden unificar ciegamente (se documenta la divergencia).
    """
    import inspect
    import random as pyrandom

    rng = np.random.default_rng(42)
    ret = rng.normal(0, 0.01, 200)

    def ret_mean(x):
        return float(np.mean(x))

    # Canonical: opera sobre un array de retornos, determinista con seed.
    lo, hi = circular_block_bootstrap_ci(ret, ret_mean, seed=42)
    assert np.isfinite(lo) and np.isfinite(hi)
    lo2, hi2 = circular_block_bootstrap_ci(ret, ret_mean, seed=42)
    assert (lo, hi) == (lo2, hi2)

    # _boot_ci: opera sobre pares (valor, fecha) con random.Random, no sobre un
    # array ni con seed de numpy.
    me = _load_script("measure_realized_edge")
    pairs = [(float(r), None) for r in ret]

    def pair_mean(sample):
        return float(np.mean([p[0] for p in sample]))

    mlo, mhi = me._boot_ci(pair_mean, pairs, pyrandom.Random(42), n_boot=200)
    assert np.isfinite(mlo) and np.isfinite(mhi)

    # Contratos de entrada incompatibles: el canonical no expone 'rng' ni acepta
    # 'pairs'; _boot_ci no expone 'returns'/'block_size'/'seed'.
    canon_params = set(inspect.signature(circular_block_bootstrap_ci).parameters)
    meas_params = set(inspect.signature(me._boot_ci).parameters)
    assert "rng" not in canon_params
    assert "returns" not in meas_params
    assert "block_size" not in meas_params
    assert "seed" not in meas_params
