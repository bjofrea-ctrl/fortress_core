"""ATLAS — ingeniería inversa precio→indicador por ticker.

Implementación del §8 de DISENO_ATLAS_INGENIERIA_INVERSA_20260901.md (aprobado
por Boris 2026-09-01). CAPA 1 del sistema: descriptiva, SIN ledger, SIN
veredictos, SIN red, SIN tocar el motor (solo lee parquet cache y usa
`app.core.indicators.calculate_all_indicators` VERBATIM para medir LOS MISMOS
indicadores que el motor).

Grid v1 (§4-§5 del diseño, alcance explícito aprobado):
    - Universo 50 canónico (`opportunities_universe.SYMBOLS`, parseado por AST
      desde su fuente única — sin importar la cadena de rutas que tira hmmlearn).
    - Indicadores FIJOS: momentum_12_1, rsi14, vol20 (std log-ret 20d anualizada).
      Escala primaria: percentil propio (rank rodante 252d, min 60 — espejo de
      `_rolling_rank01` del signal_engine).
    - Horizontes: h ∈ {5, 20, 60}. Celdas calendario: W1/W2/W3/TOTAL × los 3 h.
    - Celdas de régimen del propio ticker: tendencia (ret_63d en t−1, ±10%) ×
      vol (tercil del percentil propio de vol20 en t−1) = 9 celdas. h=5 sobre
      W1/W2/W3/TOTAL; h=20 SOLO sobre TOTAL; h=60 no existe (§5.4: N efectivo
      insuficiente por diseño — no se disfraza con solapamiento).
    - Convención temporal (§4.4): x_t = percentil propio del indicador en t−1
      (datos ≤ cierre t−1); y_t = close[t+h]/close[t] − 1. El outcome es
      estrictamente futuro respecto del info-set de x.
    - Gates ANTES de interpretar (§5.3): INSUFICIENTE (N < N_min: 75 calendario,
      40 régimen), DEGENERADO (varianza ~0 en la celda), CIRCULAR (vol20×h5).

Salidas (outdir = backend/data/cache/atlas_<stamp>/):
    atlas_celdas.csv        — el grid completo (una fila por celda)
    atlas_meta.json         — corrida + n_celdas_escaneadas (deflactación §7)
    fichas/<TICKER>.md      — ficha humana por ticker (curvas + arquetipos)
    resumen_arquetipos.md   — mapa cross-ticker + candidatos visibles
    kilo_validacion.csv     — solo con --kilo-validacion (cross-check piloto)

Uso:
    python scripts/atlas_ticker.py [--cache-dir DIR] [--outdir DIR]
                                   [--tickers NVDA,KO] [--universe CSV]
                                   [--stamp YYYYmmdd_HHMMSS] [--kilo-validacion]

Cero red. Cero escritura fuera de outdir. Cero consumo de ledger.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.indicators import calculate_all_indicators  # noqa: E402

# ─────────────────────────── CONFIG del diseño (§4-§5, fija) ─────────────────────

# Ventanas calendario del proyecto (§4.2a). W3 y TOTAL abiertas a la derecha:
# "fin de datos del cache" (intención declarada del diseño) — se resuelven por
# corrida, no se hardcodean a una fecha que el cache ya superó.
WINDOWS = {
    "W1": ("2020-01-01", "2021-12-31"),
    "W2": ("2022-01-01", "2023-12-31"),
    "W3": ("2024-01-01", None),
    "TOTAL": (None, None),
}

HORIZONS = [5, 20, 60]
INDICATORS = ["momentum_12_1", "rsi14", "vol20"]

PCT_WINDOW = 252          # percentil propio: rank rodante (§4.1)
PCT_MIN_PERIODS = 60
RET_REGIME_WINDOW = 63    # tendencia propia: ret_63d (§4.2b, maquinaria asimetría)
TREND_THRESHOLD = 0.10    # ±10%
VOL20_WINDOW = 20         # std de log-retornos diarios, anualizada √252

N_MIN_CALENDARIO = 75     # §5.3 gates de cobertura
N_MIN_REGIMEN = 40
N_QUINTILES = 5

# Arquetipos (§6, umbrales pre-especificados ANTES de correr)
ARCH_STABLE = 0.70        # ≥70% de celdas interpretables con mismo signo
ARCH_CHAM_MIN_CELLS = 0.60  # CAMALEÓN: ≥60% con |IC| ≥ magnitud
ARCH_CHAM_MAG = 0.05
ARCH_INTERP_MIN = 0.50    # <50% interpretables → INSUFICIENTE

RSI_SCORE_BAND = (45, 70)  # gate del motor (signal_engine.py:125-126)
RSI_DEGEN_STD = 0.01       # std de rsi_score en la celda por debajo → degenerado
FRAC_MODAL_DEGEN = 2 / 3   # x con >2/3 de valores idénticos → degenerado

REGIMENES = [
    f"{t}_{v}" for t in ("UP", "DOWN", "NEUTRO") for v in ("VOL_BAJA", "VOL_MEDIA", "VOL_ALTA")
]


# ─────────────────────────── universo canónico (por AST, sin imports pesados) ────

def _ast_literal_list(path: Path, varname: str) -> list:
    """Extrae una lista literal de un módulo SIN importarlo (la cadena de
    imports de opportunities_universe tira hmmlearn; el atlas es offline)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == varname:
                    if isinstance(node.value, ast.List):
                        return [ast.literal_eval(e) for e in node.value.elts]
    raise ValueError(f"{varname} no encontrada como lista literal en {path}")


def load_universe_canonical(backend_dir: Path = _BACKEND) -> list:
    """SYMBOLS canónico con la MISMA semántica de opportunities_universe.py:35
    (dict.fromkeys(_BASE_SYMBOLS + NEW_UNIVERSE)), leído por AST de sus dos
    fuentes únicas."""
    base = _ast_literal_list(
        backend_dir / "app" / "api" / "routes" / "opportunities_universe.py",
        "_BASE_SYMBOLS",
    )
    new = _ast_literal_list(
        backend_dir / "scripts" / "fetch_universe_data.py", "NEW_UNIVERSE"
    )
    return list(dict.fromkeys(base + new))


# ─────────────────────────── carga de datos e indicadores ────────────────────────

def load_ticker_frame(cache_dir: Path, ticker: str) -> pd.DataFrame:
    """Parquet OHLCV → frame de indicadores (calculate_all_indicators VERBATIM,
    que internamente hace ffill().dropna() — misma preparación que el motor y
    que el piloto de Kilo). Añade vol20 y rsi_score (definiciones del diseño)."""
    path = cache_dir / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"sin parquet para {ticker} en {cache_dir}")
    df = pd.read_parquet(path)
    df.columns = [c.lower() for c in df.columns]
    df = df.sort_index()
    ind = calculate_all_indicators(df)
    logret = np.log(ind["close"]).diff()
    ind["vol20"] = logret.rolling(VOL20_WINDOW).std() * np.sqrt(252)
    rsi_v = ind["rsi14"]
    ind["rsi_score"] = pd.Series(
        np.where(
            rsi_v.between(RSI_SCORE_BAND[0], RSI_SCORE_BAND[1], inclusive="neither"),
            0.8,
            0.4,
        ),
        index=ind.index,
    )
    ind["rsi_score"] = ind["rsi_score"].where(rsi_v.notna())
    return ind


def _pct_rank(s: pd.Series) -> pd.Series:
    """Percentil propio: rank del último valor dentro de la ventana rodante.
    Espejo de `_rolling_rank01` del signal_engine (252d, min 60)."""
    return s.rolling(PCT_WINDOW, min_periods=PCT_MIN_PERIODS).rank(pct=True)


def _classify_trend(ret63_lag: pd.Series) -> pd.Series:
    """UP / DOWN / NEUTRO por ret_63d medido en t−1 (±10%, asimetría §2.1)."""
    out = pd.Series(
        np.where(
            ret63_lag >= TREND_THRESHOLD,
            "UP",
            np.where(ret63_lag <= -TREND_THRESHOLD, "DOWN", "NEUTRO"),
        ),
        index=ret63_lag.index,
    )
    return out.where(ret63_lag.notna())


def _classify_vol_tercil(pct_vol_lag: pd.Series) -> pd.Series:
    """VOL_BAJA / VOL_MEDIA / VOL_ALTA por terciles del percentil propio de vol20 en t−1."""
    out = pd.Series(
        np.where(
            pct_vol_lag < 1 / 3,
            "VOL_BAJA",
            np.where(pct_vol_lag < 2 / 3, "VOL_MEDIA", "VOL_ALTA"),
        ),
        index=pct_vol_lag.index,
    )
    return out.where(pct_vol_lag.notna())


def build_observations(ind: pd.DataFrame, h: int) -> pd.DataFrame:
    """Frame de observaciones para un horizonte h (convención §4.4 del diseño).

    Observación fechada t:
        x_<ind>  = percentil propio del indicador en t−1  (shift(1))
        y        = close[t+h] / close[t] − 1              (outcome estrictamente
                                                            futuro respecto de t−1)
        tendencia / vol_regimen = etiquetas de régimen en t (usando datos ≤ t−1)
        rsi_score_lag = score del motor en t−1 (para el gate de degeneración)
    """
    out = pd.DataFrame(index=ind.index)
    out["close"] = ind["close"]
    out["y"] = ind["close"].shift(-h) / ind["close"] - 1.0
    out["x_momentum_12_1"] = _pct_rank(ind["momentum_12_1"]).shift(1)
    out["x_rsi14"] = _pct_rank(ind["rsi14"]).shift(1)
    out["x_vol20"] = _pct_rank(ind["vol20"]).shift(1)
    ret63 = ind["close"].pct_change(RET_REGIME_WINDOW)
    out["tendencia"] = _classify_trend(ret63.shift(1))
    out["vol_regimen"] = _classify_vol_tercil(_pct_rank(ind["vol20"]).shift(1))
    out["rsi_score_lag"] = ind["rsi_score"].shift(1)
    return out


# ─────────────────────────── estadística por celda (§5) ──────────────────────────

def _spearman(x: pd.Series, y: pd.Series) -> float:
    """Spearman por pandas (sin dependencia de scipy)."""
    if len(x) < 3:
        return float("nan")
    return float(x.corr(y, method="spearman"))


def _t_desflactado(ic: float, n_efectivo: int) -> float:
    """t descriptivo sobre N EFECTIVO = N/h (§5.2): el t solapado crudo inflaría
    la significancia ×h. Es descriptivo (capa 1), jamás un veredicto."""
    if not np.isfinite(ic) or n_efectivo < 3 or abs(ic) >= 1.0:
        return float("nan")
    return float(ic * np.sqrt((n_efectivo - 2) / (1 - ic * ic)))


def cell_stats(x: pd.Series, y: pd.Series, h: int, rsi_score: pd.Series | None = None):
    """Estadística de UNA celda (§5.1-§5.3): curva de respuesta por quintiles
    del percentil propio + IC + spread + monotonicidad + gates.

    Devuelve dict con: n_obs, n_efectivo, ic, t_desflactado, ic_nooverlap,
    t_nooverlap, spread_q5_q1_bp, monotonicidad, media_q1..q5 (bp),
    rsi_score_std, flags (string con INSUFICIENTE/DEGENERADO/CIRCULAR/QUINTIL_VACIO).
    """
    flags = []
    data = pd.concat({"x": x, "y": y}, axis=1).dropna()
    n_obs = int(len(data))
    n_efectivo = max(1, n_obs // h)

    if rsi_score is not None:
        rsi_score = rsi_score.reindex(data.index)

    if n_obs < 3:
        return _empty_cell(n_obs, n_efectivo, flags + ["INSUFICIENTE"])
    if n_obs < N_QUINTILES * 3:
        return _empty_cell(n_obs, n_efectivo, flags + ["INSUFICIENTE"])

    ic = _spearman(data["x"], data["y"])
    t_desf = _t_desflactado(ic, n_efectivo)

    # No-overlap (robustez §5.2): una observación cada h días → solape cero.
    x_no, y_no = data["x"].iloc[::h], data["y"].iloc[::h]
    ic_no = _spearman(x_no, y_no)
    n_no = len(x_no)
    t_no = (
        ic_no * np.sqrt((n_no - 2) / (1 - ic_no * ic_no))
        if np.isfinite(ic_no) and n_no >= 3 and abs(ic_no) < 1.0
        else float("nan")
    )

    # Quintiles del percentil propio DENTRO de la celda (§5.1)
    bins = pd.qcut(data["x"].rank(method="first"), N_QUINTILES, labels=False)
    means = []
    for q in range(N_QUINTILES):
        vals = data.loc[bins == q, "y"]
        means.append(float(vals.mean()) if len(vals) else float("nan"))
    if any(not np.isfinite(m) for m in means):
        flags.append("QUINTIL_VACIO")
    finite_pairs = [
        (means[k], means[k + 1])
        for k in range(N_QUINTILES - 1)
        if np.isfinite(means[k]) and np.isfinite(means[k + 1])
    ]
    monotonicidad = (
        float(np.mean([b > a for a, b in finite_pairs])) if finite_pairs else float("nan")
    )
    spread_bp = (
        float((means[-1] - means[0]) * 1e4)
        if np.isfinite(means[0]) and np.isfinite(means[-1])
        else float("nan")
    )

    # Gate de degeneración (§5.3.2): varianza ~0 del indicador en la celda
    rsi_score_std = float(rsi_score.std()) if rsi_score is not None else float("nan")
    frac_modal = float(data["x"].value_counts(normalize=True).iloc[0])
    if (rsi_score is not None and np.isfinite(rsi_score_std) and rsi_score_std < RSI_DEGEN_STD) or (
        frac_modal > FRAC_MODAL_DEGEN
    ):
        flags.append("DEGENERADO")

    return {
        "n_obs": n_obs,
        "n_efectivo": n_efectivo,
        "ic": ic,
        "t_desflactado": t_desf,
        "ic_nooverlap": ic_no,
        "t_nooverlap": float(t_no),
        "spread_q5_q1_bp": spread_bp,
        "monotonicidad": monotonicidad,
        **{f"media_q{q + 1}_bp": (means[q] * 1e4 if np.isfinite(means[q]) else float("nan")) for q in range(N_QUINTILES)},
        "rsi_score_std": rsi_score_std,
        "frac_modal": frac_modal,
        "flags": "|".join(flags),
    }


def _empty_cell(n_obs: int, n_efectivo: int, flags: list) -> dict:
    nan = float("nan")
    return {
        "n_obs": n_obs,
        "n_efectivo": n_efectivo,
        "ic": nan,
        "t_desflactado": nan,
        "ic_nooverlap": nan,
        "t_nooverlap": nan,
        "spread_q5_q1_bp": nan,
        "monotonicidad": nan,
        **{f"media_q{q + 1}_bp": nan for q in range(N_QUINTILES)},
        "rsi_score_std": nan,
        "frac_modal": nan,
        "flags": "|".join(flags),
    }


# ─────────────────────────── grid de celdas (§4.2, §5.4) ─────────────────────────

def expected_cells(tickers: list) -> list:
    """El grid teórico completo del atlas v1 (§5.4): lista de dicts
    (ticker, indicador, horizonte, tipo_contexto, contexto, n_min).
    Régimen×h60 NO existe (§5.4 — N efectivo insuficiente por diseño)."""
    cells = []
    for ticker in tickers:
        for ind in INDICATORS:
            for h in HORIZONS:
                # Calendario: W1/W2/W3/TOTAL × todos los h
                for wname in WINDOWS:
                    cells.append(
                        dict(ticker=ticker, indicador=ind, horizonte=h,
                             tipo_contexto="calendario", contexto=wname,
                             n_min=N_MIN_CALENDARIO)
                    )
                # Régimen (§5.4): h5 → W1/W2/W3/TOTAL; h20 → SOLO TOTAL; h60 → no existe
                if h == 5:
                    scopes = ["W1", "W2", "W3", "TOTAL"]
                elif h == 20:
                    scopes = ["TOTAL"]
                else:
                    scopes = []
                for scope in scopes:
                    for reg in REGIMENES:
                        cells.append(
                            dict(ticker=ticker, indicador=ind, horizonte=h,
                                 tipo_contexto="regimen", contexto=f"{scope}:{reg}",
                                 n_min=N_MIN_REGIMEN)
                        )
    return cells


def _window_mask(obs: pd.DataFrame, wname: str) -> pd.Series:
    ini, fin = WINDOWS[wname]
    mask = pd.Series(True, index=obs.index)
    if ini:
        mask &= obs.index >= pd.Timestamp(ini)
    if fin:
        mask &= obs.index <= pd.Timestamp(fin)
    return mask


def compute_cell(cell: dict, obs: pd.DataFrame) -> dict:
    """Calcula UNA celda del grid sobre el frame de observaciones."""
    h = cell["horizonte"]
    x = obs[f"x_{cell['indicador']}"]
    y = obs["y"]
    rsi_score = obs["rsi_score_lag"] if cell["indicador"] == "rsi14" else None

    if cell["tipo_contexto"] == "calendario":
        mask = _window_mask(obs, cell["contexto"])
    else:
        scope, reg = cell["contexto"].split(":", 1)
        tend, vol = reg.split("_", 1)
        mask = (
            _window_mask(obs, scope)
            & (obs["tendencia"] == tend)
            & (obs["vol_regimen"] == vol)
        )

    row = dict(cell)
    stats = cell_stats(x[mask], y[mask], h, rsi_score.loc[mask] if rsi_score is not None else None)
    if cell["indicador"] == "vol20" and h == 5:
        # §10 riesgo 6: persistencia mecánica de |retornos| — interpretación acotada
        prev = stats["flags"]
        stats["flags"] = (prev + "|" if prev else "") + "CIRCULAR"
    row.update(stats)
    # cobertura de la ventana (fechas reales de la celda, para la ficha)
    idx = obs.index[mask]
    row["ventana_ini"] = str(idx.min().date()) if len(idx) else ""
    row["ventana_fin"] = str(idx.max().date()) if len(idx) else ""
    return row


def _interpretable(row: dict) -> bool:
    flags = row.get("flags", "")
    return "INSUFICIENTE" not in flags and "DEGENERADO" not in flags


# ─────────────────────────── arquetipos (§6) ─────────────────────────────────────

def expected_context_count(h: int) -> int:
    """Celdas que EXISTEN para un trío (ind, h) — base del umbral INSUFICIENTE.
    TOTAL calendario excluido del voto (§4.2a: solo descriptivo, nunca head)."""
    cal = 3  # W1, W2, W3
    if h == 5:
        reg = len(REGIMENES) * 4  # W1/W2/W3/TOTAL
    elif h == 20:
        reg = len(REGIMENES)      # TOTAL
    else:
        reg = 0
    return cal + reg


def classify_archetype(rows: list) -> dict:
    """Arquetipo de un trío (ticker, ind, h) sobre sus celdas interpretables.
    Umbrales pre-especificados en el diseño (§6): 70/60/50."""
    esperadas = expected_context_count(rows[0]["horizonte"])
    interp = [r for r in rows if _interpretable(r)]
    out = {
        "celdas_esperadas": esperadas,
        "celdas_interpretables": len(interp),
        "arquetipo": "INSUFICIENTE",
        "estabilidad": float("nan"),
        "frac_mag": float("nan"),
    }
    if len(interp) < ARCH_INTERP_MIN * esperadas or not interp:
        return out
    w = np.array([max(1, r["n_efectivo"]) for r in interp], dtype=float)
    ics = np.array([r["ic"] for r in interp], dtype=float)
    finite = np.isfinite(ics)
    if not finite.any():
        return out
    w, ics = w[finite], ics[finite]
    pos = float(w[ics > 0].sum() / w.sum())
    neg = float(w[ics < 0].sum() / w.sum())
    mag_frac = float((np.abs(ics) >= ARCH_CHAM_MAG).mean())
    if pos >= ARCH_STABLE:
        arq = "CONTINUISTA"
    elif neg >= ARCH_STABLE:
        arq = "REVERSIONISTA"
    elif mag_frac >= ARCH_CHAM_MIN_CELLS:
        arq = "CAMALEÓN"
    else:
        arq = "INERTE"
    out["arquetipo"] = arq
    out["estabilidad"] = float(max(pos, neg))
    out["frac_mag"] = mag_frac
    return out


# ─────────────────────────── salidas: CSV, fichas, resumen ───────────────────────

CSV_COLUMNS = [
    "ticker", "indicador", "horizonte", "tipo_contexto", "contexto",
    "n_obs", "n_efectivo", "ic", "t_desflactado", "ic_nooverlap", "t_nooverlap",
    "spread_q5_q1_bp", "monotonicidad",
    "media_q1_bp", "media_q2_bp", "media_q3_bp", "media_q4_bp", "media_q5_bp",
    "rsi_score_std", "frac_modal", "flags", "n_min", "ventana_ini", "ventana_fin",
]

AVISO_FICHA = (
    "> ⚠️ **Descriptivo (capa 1 del diseño, §2). NO autoriza trades.** Único camino a "
    "regla: graduación pre-registrada (§7 del diseño). Los t están desflactados por "
    "solape (N_ef = N/h) y son descriptivos, jamás un veredicto.\n"
)


def build_archetypes(rows: list) -> list:
    """Un arquetipo por trío (ticker, indicador, horizonte)."""
    out = []
    keys = sorted({(r["ticker"], r["indicador"], r["horizonte"]) for r in rows})
    for ticker, ind, h in keys:
        sel = [r for r in rows if r["ticker"] == ticker and r["indicador"] == ind and r["horizonte"] == h]
        a = classify_archetype(sel)
        a.update(ticker=ticker, indicador=ind, horizonte=h)
        out.append(a)
    return out


def write_ficha(ticker: str, rows: list, archs: list, meta: dict, outdir: Path) -> None:
    """fichas/<TICKER>.md — la ficha humana del ticker (§3 del diseño)."""
    lines = [f"# Ficha ATLAS — {ticker}", "", AVISO_FICHA, ""]
    rows_t = [r for r in rows if r["ticker"] == ticker]
    if rows_t:
        lines.append(f"Corrida: {meta['stamp']} · Celdas del ticker: {len(rows_t)}")
    lines += [
        "",
        "Restricción del grid: las celdas de régimen × h=60 no existen (diseño §5.4: "
        "N efectivo insuficiente por diseño, no se disfraza con solapamiento).",
        "",
        "## Arquetipos",
        "",
        "| Indicador | h | Arquetipo | Estabilidad | Interp/Esp |",
        "|---|---|---|---|---|",
    ]
    for a in [a for a in archs if a["ticker"] == ticker]:
        lines.append(
            f"| {a['indicador']} | {a['horizonte']} | {a['arquetipo']} "
            f"| {a['estabilidad']:.2f} | {a['celdas_interpretables']}/{a['celdas_esperadas']} |"
        )
    for ind in INDICATORS:
        for h in HORIZONS:
            sel = [r for r in rows_t if r["indicador"] == ind and r["horizonte"] == h]
            if not sel:
                continue
            lines += [
                "", f"## {ind} — h={h}", "",
                "| Contexto | N | N_ef | IC | t_desf | Q1 | Q2 | Q3 | Q4 | Q5 "
                "| Spread bp | Mono | Flags |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
            ]
            for r in sel:
                q = " | ".join(
                    f"{r[f'media_q{k}_bp']:+.0f}" if np.isfinite(r[f"media_q{k}_bp"]) else "—"
                    for k in range(1, N_QUINTILES + 1)
                )
                lines.append(
                    f"| {r['contexto']} | {r['n_obs']} | {r['n_efectivo']} "
                    f"| {r['ic']:+.3f} | {r['t_desflactado']:+.2f} | {q} "
                    f"| {r['spread_q5_q1_bp']:+.0f} | {r['monotonicidad']:.2f} "
                    f"| {r['flags'] or '—'} |"
                )
    lines += [
        "",
        "Medias Q1..Q5 y spread en puntos base (bp = 1/10.000) sobre el retorno "
        "forward del propio ticker. Q5−Q1 > 0 = quintil alto del indicador siguió "
        "subiendo (continuación); < 0 = revirtió.",
        "",
    ]
    (outdir / "fichas").mkdir(parents=True, exist_ok=True)
    (outdir / "fichas" / f"{ticker}.md").write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────── validación Kilo (capa descriptiva) ────────────────────

def write_kilo_validation(rows: list, outdir: Path) -> None:
    """Genera `kilo_validacion.csv` con el cross-check del piloto Kilo.

    El piloto Kilo (INGENIERIA_INVERSA_POR_TICKER.md) usó TERCALES, ventanas
    de años (10y/7y/5y/2y) y terciles, media + bootstrap CI95%. El atlas usa
    QUINTILES, ventanas calendario (W1/W2/W3/TOTAL) y quintiles.

    La validación cruzada es estrictamente DIRSECCIONAL dentro de celdas
    comparables: mismo ticker × indicador × horizonte. Para el primario
    declarado (NVDA × momentum_12_1 × h20 × TOTAL), comparamos el signo del
    spread Q5−Q1 del atlas contra el signo del spread (high−low) del piloto.
    """
    import re
    ref = Path.home() / "Desktop" / "fortress_core" / "INGENIERIA_INVERSA_POR_TICKER.md"
    if not ref.exists():
        (outdir / "kilo_validacion.csv").write_text(
            "# Kilo piloto no encontrado — validación cruzada omitida\n", encoding="utf-8"
        )
        return

    text = ref.read_text(encoding="utf-8")

    # Parseamos líneas de datos tipo bloque ```: "momentum_12_1 low  n=144 mean +20.10% [16.79,23.44]"
    pat1 = re.compile(
        r"(momentum_12_1|rsi14|vol20)\s+(low|mid|high)\s+n=(\d+)\s+mean\s*([+-]?[\d.]+)%\s*\[\s*([+-]?[\d.]+),\s*([+-]?[\d.]+)\]"
    )
    data_lines = []
    for m in pat1.finditer(text):
        data_lines.append({
            "ind": m.group(1), "bucket": m.group(2),
            "n_kilo": int(m.group(3)), "mean_pct": float(m.group(4)),
            "ci_lo": float(m.group(5)), "ci_hi": float(m.group(6)),
        })

    # Parseamos tabla markdown primaria §5:
    # "| momentum_12_1 | +4.09% [3.13,5.08] | +4.11% [3.14,5.02] | **+6.58% [5.70,7.45]** | 48.2/140.6 |"
    # El n está en el header: "| Indicador | low (n=828) | mid (n=828) | high (n=829) | q33/q66 |"
    pat2 = re.compile(
        r"\|\s*(momentum_12_1|rsi14|vol20)\s*\|\s*[\\*]*\s*([+-]?[\d.]+)%\s*\[\s*([+-]?[\d.]+),\s*([+-]?[\d.]+)\]\s*[\\*]*\s*\|"
        r"\s*[\\*]*\s*([+-]?[\d.]+)%\s*\[\s*([+-]?[\d.]+),\s*([+-]?[\d.]+)\]\s*[\\*]*\s*\|"
        r"\s*[\\*]*\s*([+-]?[\d.]+)%\s*\[\s*([+-]?[\d.]+),\s*([+-]?[\d.]+)\]\s*[\\*]*\s*\|"
    )
    # Buscamos el header para extraer n por bucket
    header_pat = re.compile(r"\|\s*(low|mid|high)\s+\(n=(\d+)\)")
    header_matches = list(header_pat.finditer(text))
    n_map = {}
    for m in header_matches[:3]:
        n_map[m.group(1)] = int(m.group(2))

    for m in pat2.finditer(text):
        cols = [
            (float(m.group(2)), float(m.group(3)), float(m.group(4))),  # low
            (float(m.group(5)), float(m.group(6)), float(m.group(7))),  # mid
            (float(m.group(8)), float(m.group(9)), float(m.group(10))),  # high
        ]
        bucket_names = ["low", "mid", "high"]
        for i, (mean, lo, hi) in enumerate(cols):
            data_lines.append({
                "ind": m.group(1), "bucket": bucket_names[i],
                "n_kilo": n_map.get(bucket_names[i], 0), "mean_pct": mean,
                "ci_lo": lo, "ci_hi": hi,
            })

    # Solo validamos el primario NVDA × momentum_12_1 × h20 × TOTAL
    cross = [{
        "ticker": "NVDA", "indicador": "momentum_12_1",
        "horizonte": 20, "contexto": "TOTAL",
    }]
    for r in cross:
        match = [row for row in rows
                 if str(row.get("ticker", "")) == "NVDA"
                 and str(row.get("indicador", "")) == "momentum_12_1"
                 and float(row.get("horizonte", -1)) == 20
                 and str(row.get("contexto", "")) == "TOTAL"
                 and str(row.get("tipo_contexto", "")) == "calendario"]
        flags = str(match[0].get("flags", "")) if match else ""
        if not match or "INSUFICIENTE" in flags or "DEGENERADO" in flags:
            continue
        mr = match[0]
        r["atlas_spread_q5_q1_bp"] = mr["spread_q5_q1_bp"]
        r["atlas_ic"] = mr["ic"]
        r["atlas_n"] = mr["n_obs"]
        r["atlas_media_q1_pct"] = mr["media_q1_bp"] / 100.0
        r["atlas_media_q5_pct"] = mr["media_q5_bp"] / 100.0
        # datos Kilo del primario: NVDA 10y 20d momentum (n≈828/829)
        # El primario NVDA 10y 20d tiene n≈828; filtramos n>=820 para evitar
        # confundir con el 2y (n=144/145) o EPAM (n=398)
        kilo_high = [kl for kl in data_lines
                     if kl["ind"] == "momentum_12_1" and kl["bucket"] == "high"
                     and kl["n_kilo"] >= 820]
        kilo_low = [kl for kl in data_lines
                    if kl["ind"] == "momentum_12_1" and kl["bucket"] == "low"
                    and kl["n_kilo"] >= 820]
        if kilo_high and kilo_low:
            r["kilo_high_mean_pct"] = kilo_high[-1]["mean_pct"]
            r["kilo_high_n"] = kilo_high[-1]["n_kilo"]
            r["kilo_low_mean_pct"] = kilo_low[-1]["mean_pct"]
            r["kilo_low_n"] = kilo_low[-1]["n_kilo"]
            kilo_spread_bp = (r["kilo_high_mean_pct"] - r["kilo_low_mean_pct"]) * 100
            r["kilo_spread_high_low_bp"] = kilo_spread_bp
            r["match_direccional"] = (
                (r["atlas_spread_q5_q1_bp"] > 0) == (kilo_spread_bp > 0)
            )

    (outdir / "kilo_validacion.csv").write_text(
        pd.DataFrame(cross).to_csv(index=False), encoding="utf-8"
    )
    print(f"  Kilo validación -> {outdir / 'kilo_validacion.csv'}\n")


# ─────────────────────────── resumen arquetipos ───────────────────────────────────

def write_resumen_arquetipos(archs: list, outdir: Path, stamp: str, n_scan: int) -> None:
    """resumen_arquetipos.md — mapa cross-ticker + candidatos visibles."""
    lines = [
        "# Resumen ATLAS — arquetipos por ticker × indicador × horizonte",
        "",
        "> ⚠️ Descriptivo (capa 1, §2). NO autoriza trades. Único camino a regla: graduación pre-registrada (§7).",
        "",
        f"Corrida: {stamp} · Celdas escaneadas: {n_scan}",
        "",
        "## Tabla de arquetipos",
        "",
        "| Ticker | Indicador | h | Arquetipo | Estabilidad | Interp/Esp |",
        "|---|---|---|---|---|---|",
    ]
    for a in sorted(archs, key=lambda x: (x["ticker"], x["indicador"], x["horizonte"])):
        lines.append(
            f"| {a['ticker']} | {a['indicador']} | {a['horizonte']} | {a['arquetipo']} "
            f"| {a['estabilidad']:.2f} | {a['celdas_interpretables']}/{a['celdas_esperadas']} |"
        )

    candidatos = [a for a in archs
                  if a["arquetipo"] in ("CONTINUISTA", "REVERSIONISTA", "CAMALEÓN")
                  and np.isfinite(a["estabilidad"])]
    lines += ["", "## Candidatos visibles (no INERTE/INSUFICIENTE, IC ≠ 0)", ""]
    if candidatos:
        lines.append("| Ticker | Indicador | h | Arquetipo | Estabilidad |")
        lines.append("|---|---|---|---|---|")
        for a in sorted(candidatos, key=lambda x: -x["estabilidad"]):
            lines.append(f"| {a['ticker']} | {a['indicador']} | {a['horizonte']} | {a['arquetipo']} | {a['estabilidad']:.2f} |")
    else:
        lines.append("_Ningún candidato visible — todos INERTE o INSUFICIENTE._")

    lines += [
        "",
        "## Legenda de arquetipos (§6, umbrales pre-especificados)",
        "",
        "- **CONTINUISTA**: ≥70% de celdas interpretables con mismo signo positivo (IC>0).",
        "- **REVERSIONISTA**: ≥70% de celdas interpretables con mismo signo negativo (IC<0).",
        "- **CAMALEÓN**: ≥60% de celdas con |IC| ≥ 0.05 (signo mixto, magnitud consistente).",
        "- **INERTE**: celdas interpretables pero sin consenso de signo ni magnitud.",
        "- **INSUFICIENTE**: <50% de celdas interpretables (cobertura insuficiente).",
        "",
        "Los t están desflactados por N_ef = N/h. N efectivo acompaña siempre al t.",
    ]
    (outdir / "resumen_arquetipos.md").write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────── orquestación ───────────────────────────────────────

def run_atlas(cache_dir: Path, tickers: list, outdir: Path) -> dict:
    """Ejecuta el pipeline completo del atlas v1 sobre `tickers`.

    CAPA 1 (descriptiva): solo lee parquet cache, calcula estadísticas,
    NO escribe al ledger, NO toca el motor de señales.
    """
    from datetime import datetime as _dt
    stamp = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
    n_celdas_escaneadas = 0
    all_rows: list = []
    expected = expected_cells(tickers)

    for t in tickers:
        if not (cache_dir / f"{t}.parquet").exists():
            print(f"  [WARN] {t}: sin parquet en cache, lo salteo")
            continue
        ind = load_ticker_frame(cache_dir, t)
        for h in HORIZONS:
            obs = build_observations(ind, h)
            for cell in [c for c in expected if c["ticker"] == t and c["horizonte"] == h]:
                n_celdas_escaneadas += 1
                all_rows.append(compute_cell(cell, obs))

    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(all_rows)
    df.to_csv(outdir / "atlas_celdas.csv", index=False)

    archs = build_archetypes(all_rows)
    for t in tickers:
        rows_t = [r for r in all_rows if r["ticker"] == t]
        if rows_t:
            write_ficha(t, all_rows, archs, {"stamp": stamp}, outdir)

    write_resumen_arquetipos(archs, outdir, stamp, n_celdas_escaneadas)

    meta = {
        "stamp": stamp,
        "tickers_ok": len([t for t in tickers if (cache_dir / f"{t}.parquet").exists()]),
        "n_celdas_escaneadas": n_celdas_escaneadas,
        "n_celdas_esperadas": len(expected),
    }
    (outdir / "atlas_meta.json").write_text(json.dumps(meta, indent=2))
    return meta


# ─────────────────────────── main ────────────────────────────────────────────────

def main(argv=None) -> None:
    """CLI: python scripts/atlas_ticker.py [--cache-dir DIR] [--tickers NVDA,KO]
    [--kilo-validacion].

    Defaults: --cache-dir apunta al cache real de parquets en Desktop
    (fundamentos-automatizado no tiene los parquets). --outdir crea un
    directorio timestampado dentro del workspace.
    """
    ap = argparse.ArgumentParser(description="ATLAS v1: ingenieria inversa precio-indicador por ticker")
    ap.add_argument("--cache-dir", type=Path,
                    default=Path.home() / "Desktop" / "fortress_core" / "backend" / "data" / "cache",
                    help="Directorio con parquets OHVCV")
    ap.add_argument("--outdir", type=Path, default=None,
                    help="Output dir. Default: backend/data/cache/atlas_<stamp>/")
    ap.add_argument("--tickers", type=str, default=None,
                    help="Tickers a procesar (coma). Default: universo canonico 50")
    ap.add_argument("--kilo-validacion", action="store_true",
                    help="Genera kilo_validacion.csv")
    args = ap.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir = args.outdir or Path("backend/data/cache") / f"atlas_{stamp}"
    tickers = args.tickers.split(",") if args.tickers else load_universe_canonical()
    print(f"ATLAS v1 — {len(tickers)} tickers, cache={args.cache_dir}")
    print(f"Output: {outdir}")

    meta = run_atlas(args.cache_dir, tickers, outdir)
    if args.kilo_validacion:
        rows = pd.read_csv(outdir / "atlas_celdas.csv").to_dict("records")
        write_kilo_validation(rows, outdir)

    print(f"\n✅ Hecho. Meta: {json.dumps(meta)}")
    print(f"  Ver: {outdir / 'atlas_celdas.csv'}")
    print(f"  Ver: {outdir / 'fichas/'}")
    print(f"  Ver: {outdir / 'resumen_arquetipos.md'}")


if __name__ == "__main__":
    main()