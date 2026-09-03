"""
Generación de artefactos (Excel + Dashboard) con el motor canónico real.

Fase 4 del plan — "el dashboard y el Excel IGUALES al original de AAI".

ESTRATEGIA: en lugar de reimplementar un render propio (que inevitablemente
se desvía del layout original del screening de AAI), este módulo usa el
**motor canónico** — `motor_screening.py` vendorizado en
`backend/app/core/motor_canonico/scripts/motor_screening.py`, copia
byte-a-byte de
`~/.claude/skills/aai-screening-acciones/scripts/motor_screening.py` (con su
`assets/` y `references/` completos, para que el motor cargue logos y
sectores excluidos como lo hace en el skill) — y usa
SUS funciones `generar_excel()` y `generar_dashboard()` sobre:

  (1) `filas`/`hmap`: filas en el formato del export de InvestingPro que el
      motor canónico lee (columnas con nombres exactos, ratios en decimal).
  (2) `evals`/`orden`: la salida de `motor_screening.evaluate()` — el MISMO
      motor canónico, no una reimplementación paralela.

Así, por construcción, el Excel y el HTML quedan IGUALES al original de AAI:
misma función `generar_excel`, mismo `generar_dashboard`, mismo layout,
mismo branding, mismos umbrales.

NOTA sobre el vendor: si el motor en el skill cambia, la copia del repo debe
actualizarse a mano (diff verificable). NUNCA modificar la copia sin
actualizar también la fuente del skill.

TODO en este módulo es escritor puro (disco) — NO toca la red. Los tests lo
corren contra fixtures FMP + el motor vendorizado; el job runner lo invoca
después de completar el screening. Ningún endpoint usa esto; los endpoints
solo leen los archivos que esto produce.
"""

import importlib.util
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fundamentals_artifacts")

_HERE = os.path.dirname(os.path.abspath(__file__))
_MOTOR_SRC = os.path.join(
    _HERE, "motor_canonico", "scripts", "motor_screening.py"
)

# Orden de columnas del layout del motor canónico (lista completa en
# `motor_screening.py::generar_excel`). El `hmap` del motor canónico mapea
# nombre -> índice; acá definimos el orden «canónico» para que el row que
# armamos tenga los índices correctos.
_COLS = [
    "Name", "Ticker", "Full Ticker", "Price, Current", "Market Cap (Adjusted)",
    "Return on Invested Capital", "Avg Return on Invested Capital (5y)",
    "Return on Equity", "Gross Profit Margin",
    "Avg EPS Growth (5y)", "Revenue CAGR (5y)",
    "FCF / Net Income", "Buyback Yield", "Total Debt / Total Capital",
    "Beta (5 Year)", "P/E Ratio", "PEG Ratio Fwd", "EV / EBIT",
    "Free Cash Flow Yield", "Fair Value",
    "Fair Value Label (Analyst Targets)", "Piotroski Score", "Altman Z-Score",
    "Beneish M-Score", "Overall Health Label",
]

# Los ratios vienen de Fase 2 en DECIMAL (0.208 = 20.8%) — misma convención
# del export de InvestingPro que el motor canónico lee (su `pctv()` internamente
# multiplica por 100). Mapa columna-canónica -> clave en screen_payload().
_COL_TO_PAYLOAD_KEY = {
    "Name": "name",
    "Ticker": "ticker",
    "Full Ticker": "full_ticker",
    "Price, Current": "price",
    "Market Cap (Adjusted)": "market_cap",
    "Return on Invested Capital": "roic",
    "Avg Return on Invested Capital (5y)": "roic_5y",
    "Return on Equity": "roe",
    "Gross Profit Margin": "gross_margin",
    "Avg EPS Growth (5y)": "eps_growth_5y",
    "Revenue CAGR (5y)": "rev_cagr_5y",
    "FCF / Net Income": "fcf_to_ni",
    "Buyback Yield": "buyback_yield",
    "Total Debt / Total Capital": "debt_to_capital",
    "Beta (5 Year)": "beta",
    "P/E Ratio": "pe_ratio",
    "PEG Ratio Fwd": "peg_ratio_fwd",
    "EV / EBIT": "ev_to_ebit",
    "Free Cash Flow Yield": "fcf_yield",
    "Fair Value": "fair_value",
    "Fair Value Label (Analyst Targets)": "fair_value_label",
    "Piotroski Score": "piotroski_f_score",
    "Altman Z-Score": "altman_z_score",
    "Beneish M-Score": "beneish_m_score",
}

_motor = None


def _load_motor():
    """Carga el motor canónico vendorizado (una sola vez, importlib puro)."""
    global _motor
    if _motor is not None:
        return _motor
    if not os.path.exists(_MOTOR_SRC):
        raise FileNotFoundError(
            f"Motor canónico no encontrado en {_MOTOR_SRC}. "
            "¿Se borró el vendor? git checkout restaura el archivo."
        )
    spec = importlib.util.spec_from_file_location(
        "app_core_motor_screening_vendored", _MOTOR_SRC
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _motor = mod
    return mod


def build_hmap() -> Dict[str, int]:
    """Devuelve el mapa nombre->índice (igual que leer_export del motor)."""
    return {c: i for i, c in enumerate(_COLS)}


def result_to_row(result: Dict[str, Any], hmap: Dict[str, int]) -> List[Any]:
    """Convierte el output de screen_payload() en una fila tipo export.

    La fila es una lista con el MISMO orden de columnas que `hmap` (que a su
    vez es el orden de `_COLS`). Los ratios van en DECIMAL — el motor canónico
    los multiplica por 100 internamente vía `pctv()`.
    """
    row = [None] * len(_COLS)
    for col_name, idx in hmap.items():
        payload_key = _COL_TO_PAYLOAD_KEY.get(col_name)
        if payload_key is None:
            continue  # p.ej. Overall Health Label — ausente, se deja None
        row[idx] = result.get(payload_key)
    if row[hmap["Name"]] is None:
        row[hmap["Name"]] = result.get("name") or result.get("ticker") or ""
    if row[hmap["Ticker"]] is None:
        row[hmap["Ticker"]] = result.get("ticker") or ""
    return row


def build_evals_and_orden(
    results_by_symbol: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[int, Dict], List[int]]:
    """Dado {sym: screen_payload_output}, construye `evals` y `orden`
    EXACTAMENTE como los produciría motor_screening.main() sobre un export.

    - `evals[k] = evaluate(row, raw, num, pctv)` — el motor canónico real.
    - `orden` = filas ordenadas por (balde, -punt, ticker) — igual que main().
    - `fund`/`sectx` los agrega el propio evaluate() (detección Fondos/ETFs
      y exclusión sectorial vía SECT_EXCL del motor).

    Devuelve (evals, orden).
    """
    motor = _load_motor()
    hmap = build_hmap()
    raw, num, pctv = motor._mk_accessors(hmap)

    rows = []
    for sym in sorted(results_by_symbol.keys()):
        rows.append(result_to_row(results_by_symbol[sym], hmap))

    evals = {k: motor.evaluate(row, raw, num, pctv) for k, row in enumerate(rows)}

    ob = {"Deep Dive": 0, "Watchlist": 1, "Neutral": 2, "Descartada": 3, "Omitida": 4}
    orden = sorted(
        evals.keys(),
        key=lambda k: (
            (9, 0, "")
            if evals[k]["fund"]
            else (ob.get(evals[k]["balde"], 9), -evals[k]["punt"], str(evals[k]["ticker"] or "").lower())
        ),
    )
    return evals, orden


def rows_for_excel(
    results_by_symbol: Dict[str, Dict[str, Any]],
) -> List[List[Any]]:
    """Devuelve las filas en el orden que espera generar_excel (filas[k]
    para cada k en evals). Mismo orden que build_evals_and_orden."""
    hmap = build_hmap()
    return [result_to_row(results_by_symbol[sym], hmap)
            for sym in sorted(results_by_symbol.keys())]


def render_artifacts(
    results_by_symbol: Dict[str, Dict[str, Any]],
    run_date: str,
    outdir: str,
    export_name: Optional[str] = None,
) -> Dict[str, str]:
    """Genera los artefactos VISUALES del screening con el motor canónico real.

    Llamada por el job runner después de completar el screening (o por el
    test end-to-end). Escribe en `outdir`:

        Screening_AAI_<fecha>.xlsx   — Excel enriquecido (motor canónico)
        dashboard_<fecha>.html       — dashboard interactivo (motor canónico)

    VERDAD ÚNICA para el screen_<date>.json: lo escribe el JOB RUNNER (que
    conoce calls_used, failed_count, etc.) ANTES de llamar acá. Este módulo
    NO toca el JSON — evita el bug de doble escritura/sobreescritura con
    formatos distintos según el orden de correr.

    Devuelve un dict con los paths generados {kind: path}. Si `generar_excel`
    o `generar_dashboard` falla, la excepción sube — el job runner convierte
    el fallo en rc != 0 para que el test end-to-end lo vea en rojo.
    """
    if not results_by_symbol:
        raise ValueError("render_artifacts: sin resultados para renderizar")

    motor = _load_motor()
    export_name = export_name or f"fortress_core_{run_date}"

    evals, orden = build_evals_and_orden(results_by_symbol)

    os.makedirs(outdir, exist_ok=True)
    xlsx_path = os.path.join(outdir, f"Screening_AAI_{run_date}.xlsx")
    html_path = os.path.join(outdir, f"dashboard_{run_date}.html")

    # 1) Excel — generar_excel REAL del motor canónico.
    (cts, funds, sectx, exc, tr, analizadas) = motor.generar_excel(
        rows_for_excel(results_by_symbol),
        build_hmap(),
        evals,
        orden,
        xlsx_path,
        export_name,
        run_date,
    )

    # 2) Dashboard HTML — generar_dashboard REAL del motor canónico.
    faltan_cols = [
        c for c in motor.COLS_NUCLEO + motor.COLS_OPCIONALES
        if c not in build_hmap()
    ]
    motor.generar_dashboard(
        evals, orden, html_path, export_name, run_date,
        cts, funds, exc, tr, analizadas, faltan=faltan_cols,
    )

    logger.info(
        "fundamentals_artifacts_rendered",
        extra={
            "xlsx": xlsx_path,
            "html": html_path,
            "deep_dive": cts.get("Deep Dive", 0),
            "watchlist": cts.get("Watchlist", 0),
            "analizadas": analizadas,
        },
    )
    return {"xlsx": xlsx_path, "html": html_path}
