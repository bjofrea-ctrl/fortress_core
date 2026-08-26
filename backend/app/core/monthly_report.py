"""Reporte mensual por variante del ensamble (Frente 2, Semana 2).

Mecanismo de construcción — NO es un trial de investigación: NO toca
trial_registry.json, NO consume presupuesto Bonferroni, NO necesita
pre-registro (decisión de Boris, 2026-08-26).

Qué hace:
  1. Toma las filas CERRADAS del signal_ledger (open_order/close_order de
     Semana 1) y agrupa por MES DE CIERRE y VARIANTE.
  2. Por celda calcula el Sharpe REALIZADO del mes sobre la serie de `pnl_r`
     (retornos en unidades de riesgo, frecuencia nativa por-oficio):
     sharpe = mean(pnl_r) / std(pnl_r, ddof=1). También expone el anualizado
     (× sqrt(12)) solo como referencia — el veredicto compara nativo vs
     nativo contra lo que el backtest predijo para esa variante.
  3. Compara contra la EXPECTATIVA por variante (Sharpe mensual que dejó la
     validación OOS congelada de cada variante, en config/expected_sharpe.json).
     Veredicto por mes: EN_CALIBRACION (>= umbral × esperado), DEBAJO_ESPERADO
     (>=0 pero bajo el umbral), NEGATIVO (<0), SIN_DATOS (<2 oficios),
     DEGENERADO (std=0), ESPERADO_NO_DEFINIDO (variante sin expectativa).
  4. Bitácora ACUMULADA: cada mes queda registrado en la tabla
     `monthly_report_log` (fortress.db, upsert por variante+mes — regenerar
     un mes no duplica filas). Tabla PROPIA, ajena a trial_registry.

Variante: se lee de factors_json["variant"]; si la fila no lo trae se asigna
DEFAULT_VARIANT ("mom_rsi_congelada") porque hoy TODO el pipeline corre esa
única definición congelada. Cuando el ensamble sume variantes (A5 u otro
candidato del árbol), el pipeline debe etiquetar factors_json["variant"].

Limitación honesta (mecanismo, no señal): con pocos oficios por mes el Sharpe
mensual por-oficio es ruidoso y su frecuencia nativa no es idéntica al
Sharpe mensual de retornos de cartera del backtest. La comparación se vuelve
cada vez más fiel a medida que acumulan meses en la bitácora — valida el
MECANISMO desde el día 1, como pide el checkpoint de Semana 2.
"""
import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.signal_ledger import SignalLedger

# Variante por defecto: la única definición viva hoy (ver docstring).
DEFAULT_VARIANT = "mom_rsi_congelada"

# Expectativas por defecto (semilla): la validación OOS fresca congelada.
# Archivo canónico editable — cada variante nueva del ensamble agrega su entrada.
DEFAULT_EXPECTATIONS_PATH = "config/expected_sharpe.json"

_DEFAULT_EXPECTATIONS = {
    DEFAULT_VARIANT: {
        "sharpe_mensual": 0.383816,
        "sharpe_anualizado": 1.3296,
        "fuente": "data/cache/validacion_oos_fresca_mom_rsi_20260822_155520.txt",
        "nota": "definicion congelada sin re-optimizar; OOS efectivo 2024-02..2026-07",
    }
}

_BITACORA_SQL = """
CREATE TABLE IF NOT EXISTS monthly_report_log (
    variant TEXT NOT NULL,
    month TEXT NOT NULL,
    n_trades INTEGER NOT NULL,
    pnl_sum REAL NOT NULL,
    sharpe_native REAL,
    sharpe_annualized REAL,
    expected_sharpe_mensual REAL,
    verdict TEXT NOT NULL,
    diagnostico TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (variant, month)
)
"""


def month_key(date_str: str) -> str:
    """'2026-08-25' -> '2026-08' (toma los primeros 7 caracteres ISO)."""
    return str(date_str)[:7]


def compute_month_stats(pnls: List[float]) -> Dict[str, Any]:
    """Sharpe nativo de una serie de pnl_r de UNA celda (variante, mes).

    Sin datos suficientes o sin dispersión devuelve sharpe=None + veredicto
    estructural (SIN_DATOS / DEGENERADO) — nunca divide por cero ni inventa.
    """
    n = len(pnls)
    total = float(sum(pnls))
    if n < 2:
        return {"n": n, "pnl_sum": total, "sharpe": None,
                "sharpe_annualized": None, "base_verdict": "SIN_DATOS"}
    mean = total / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    std = math.sqrt(var)
    if std == 0.0:
        return {"n": n, "pnl_sum": total, "mean": mean, "std": 0.0,
                "sharpe": None, "sharpe_annualized": None,
                "base_verdict": "DEGENERADO"}
    sharpe = mean / std
    return {"n": n, "pnl_sum": total, "mean": mean, "std": std,
            "sharpe": sharpe, "sharpe_annualized": sharpe * math.sqrt(12),
            "base_verdict": None}

class MonthlyReporter:
    """Genera el reporte mensual por variante y acumula la bitácora."""

    def __init__(
        self,
        db_path: str = "fortress.db",
        expectations_path: Optional[str] = DEFAULT_EXPECTATIONS_PATH,
        umbral_calibracion: float = 0.5,
        ledger: Optional[SignalLedger] = None,
    ):
        self.db_path = db_path
        self.umbral = float(umbral_calibracion)
        self.ledger = ledger or SignalLedger(db_path)
        self.expectations = self._load_expectations(expectations_path)

    def _load_expectations(self, path: Optional[str]) -> Dict[str, Any]:
        """Carga config/expected_sharpe.json; si falta, usa la semilla embebida."""
        if path is None:
            return dict(_DEFAULT_EXPECTATIONS)
        try:
            with open(path) as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else dict(_DEFAULT_EXPECTATIONS)
        except (OSError, json.JSONDecodeError):
            return dict(_DEFAULT_EXPECTATIONS)

    # -- reporte ------------------------------------------------------------

    def month_rows(self, month: Optional[str] = None) -> List[Dict[str, Any]]:
        """Filas cerradas del ledger agrupadas en celdas (variante, mes)."""
        rows = self.ledger.fetch()
        cells: Dict[tuple, List[float]] = {}
        meta: Dict[tuple, Dict[str, float]] = {}
        for row in rows:
            if row.get("status") != "closed":
                continue
            mk = month_key(row["exit_date"])
            if month is not None and mk != month:
                continue
            try:
                factors = json.loads(row.get("factors_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                factors = {}
            variant = factors.get("variant", DEFAULT_VARIANT)
            key = (variant, mk)
            cells.setdefault(key, []).append(float(row["pnl_r"]))
            m = meta.setdefault(key, {"worst": 0.0, "best": 0.0})
            m["worst"] = min(m["worst"], float(row["pnl_r"]))
            m["best"] = max(m["best"], float(row["pnl_r"]))
        out = []
        for (variant, mk), pnls in sorted(cells.items()):
            stats = compute_month_stats(pnls)
            out.append({"variant": variant, "month": mk,
                        "worst_trade_r": meta[(variant, mk)]["worst"],
                        "best_trade_r": meta[(variant, mk)]["best"], **stats})
        return out

    def generate(self, month: Optional[str] = None,
                 persist: bool = True) -> Dict[str, Any]:
        """Reporte de UN mes ('YYYY-MM') o de todo el historial (None)."""
        cells = self.month_rows(month)
        report_rows = [self._verdict(c) for c in cells]
        if persist:
            for row in report_rows:
                self._log_row(row)
        return {"generated_at": self._now(), "umbral_calibracion": self.umbral,
                "rows": report_rows}

    def _verdict(self, cell: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica la expectativa de la variante y produce veredicto+línea."""
        variant = cell["variant"]
        exp = self.expectations.get(variant)
        exp_monthly = (exp or {}).get("sharpe_mensual")
        out = dict(cell)
        out["expected_sharpe_mensual"] = exp_monthly
        bv = cell["base_verdict"]
        if bv:  # SIN_DATOS / DEGENERADO
            out["verdict"] = bv
        elif exp_monthly is None:
            out["verdict"] = "ESPERADO_NO_DEFINIDO"
        elif cell["sharpe"] < 0:
            out["verdict"] = "NEGATIVO"
        elif cell["sharpe"] >= self.umbral * float(exp_monthly):
            out["verdict"] = "EN_CALIBRACION"
        else:
            out["verdict"] = "DEBAJO_ESPERADO"
        out["diagnostico"] = self._diagnostico(out)
        return out

    @staticmethod
    def _diagnostico(row: Dict[str, Any]) -> str:
        """Una línea, sin adornos: qué pasó y el número dominante."""
        v = row["verdict"]
        if v == "SIN_DATOS":
            return f"menos de 2 oficios cerrados (n={row['n']}) — nada medible"
        if v == "DEGENERADO":
            return f"{row['n']} oficios con pnl identico ({row['pnl_sum']:+.2f}R) — sin dispersion"
        if v == "ESPERADO_NO_DEFINIDO":
            return ("sin expectativa registrada para esta variante en "
                    "config/expected_sharpe.json — agregar entrada")
        base = (f"n={row['n']} suma={row['pnl_sum']:+.2f}R "
                f"sharpe={row['sharpe']:.2f} vs esperado "
                f"{row['expected_sharpe_mensual']:.2f}")
        if v == "NEGATIVO":
            return base + f" — mes negativo, peor oficio {row['worst_trade_r']:+.2f}R"
        if v == "DEBAJO_ESPERADO":
            return base + " — direccion OK, magnitud debajo del umbral de calibracion"
        return base + " — dentro del rango de calibracion"


    # -- bitácora -----------------------------------------------------------

    def _log_row(self, row: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_BITACORA_SQL)
            conn.execute(
                """
                INSERT INTO monthly_report_log
                    (variant, month, n_trades, pnl_sum, sharpe_native,
                     sharpe_annualized, expected_sharpe_mensual, verdict,
                     diagnostico, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(variant, month) DO UPDATE SET
                    n_trades = excluded.n_trades,
                    pnl_sum = excluded.pnl_sum,
                    sharpe_native = excluded.sharpe_native,
                    sharpe_annualized = excluded.sharpe_annualized,
                    expected_sharpe_mensual = excluded.expected_sharpe_mensual,
                    verdict = excluded.verdict,
                    diagnostico = excluded.diagnostico,
                    generated_at = excluded.generated_at
                """,
                (row["variant"], row["month"], int(row["n"]),
                 float(row["pnl_sum"]), row.get("sharpe"),
                 row.get("sharpe_annualized"), row.get("expected_sharpe_mensual"),
                 row["verdict"], row["diagnostico"], self._now()),
            )

    def bitacora(self, variant: Optional[str] = None) -> List[Dict[str, Any]]:
        """Historial acumulado por variante: meses y veredictos agregados."""
        sql = ("SELECT variant, COUNT(*) AS meses, "
               "SUM(verdict = 'EN_CALIBRACION') AS en_calibracion, "
               "SUM(verdict = 'DEBAJO_ESPERADO') AS debajo_esperado, "
               "SUM(verdict = 'NEGATIVO') AS negativos, "
               "SUM(verdict IN ('SIN_DATOS','DEGENERADO',"
               "'ESPERADO_NO_DEFINIDO')) AS no_medibles "
               "FROM monthly_report_log")
        params: List[Any] = []
        if variant is not None:
            sql += " WHERE variant = ?"
            params.append(variant)
        sql += " GROUP BY variant ORDER BY variant"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [{k: r[k] for k in r.keys()} for r in
                    conn.execute(sql, params).fetchall()]

    def months(self, variant: Optional[str] = None) -> List[Dict[str, Any]]:
        """Detalle mes a mes de la bitácora (para el reporte imprimible)."""
        sql = "SELECT * FROM monthly_report_log"
        params: List[Any] = []
        if variant is not None:
            sql += " WHERE variant = ?"
            params.append(variant)
        sql += " ORDER BY variant, month"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [{k: r[k] for k in r.keys()} for r in
                    conn.execute(sql, params).fetchall()]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
