"""M7 — Pipeline integrado M1+M2+M3 (DISENO_INSTRUMENTO.md §5, §7 etapa 3).

MOTIVO: M1 (etiquetado por barreras), M2 (instrumento conforme) y M3 (compuerta de
régimen) existen como tres piezas separadas, cada una con sus propios tests. Hoy quien
quiera usarlas tiene que cablearlas a mano — exactamente lo que la tesis de
DISENO_INSTRUMENTO.md prometió evitar: "Fortress como instrumento diagnóstico
calibrado", UN instrumento, no tres módulos sueltos.

POR QUÉ ESTE MÓDULO SE QUEDÓ CON CLAUDE CODE (no se delegó, ver ORDENES_MODULOS.md M7
y SESSION_LOG.md 2026-08-15): el cableado entre módulos de distintos dueños puede fallar
en SILENCIO — números plausibles, tests que pasan sin detectarlo — y el radio de daño se
propaga a cada trial futuro que use esta pieza. Dos invariantes son las que importan:

1. SEPARACIÓN TEMPORAL ESTRICTA entre calibración y predicción de M2. Si se mezclan
   fechas, la garantía de cobertura de conformal prediction se invalida en silencio —
   el código sigue corriendo, los números parecen razonables. El split acá es por FECHA
   REAL (`calibration_cutoff`), nunca por posición en un array, y nunca mezclando
   símbolos antes de cortar — exactamente el pooled-vs-intra-día que ONBOARDING.md
   llama el error más importante del proyecto, en otra forma.

2. LA COMPUERTA M3 ES UN AND, NUNCA UN OR. Una fecha solo "opera" si el instrumento
   conforme NO se abstiene Y la compuerta de régimen dice operar=True. Si se cablea
   como OR, la compuerta deja de filtrar nada — el bug más fácil de cometer sin que
   ningún test lo note si no se prueba explícitamente.

ESTE MÓDULO NO ES UN TRIAL: no se corre contra el universo real de 50 símbolos para
sacar conclusiones sobre si el motor mejora — eso necesita pre-registro nuevo (regla
#1/#2 de ONBOARDING.md) y es decisión del usuario. Este pipeline es infraestructura de
conexión; se prueba con datos sintéticos, igual que M1/M2/M3.
"""
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional

import pandas as pd

from app.core.barrier_labeling import DEFAULT_COST_PER_SIDE, DEFAULT_MAX_HORIZON, label_symbol
from app.core.conformal import ConformalAbstentionEngine, ConformalCalibration, vpp_bajo_abstencion
from app.core.regime_gate import WalkForwardRegimeGate


@dataclass(frozen=True)
class PipelineResult:
    """Salida única del instrumento: detalle por (símbolo, fecha) + resumen agregado."""
    detalle: pd.DataFrame          # symbol, date, score, ret_net, abstenerse, gate_operar, operar, razon
    resumen: dict                  # vpp_bajo_abstencion sobre las decisiones finales (con gate aplicado)
    calibracion: ConformalCalibration
    n_simbolos: int
    ventana_calibracion: str       # "YYYY-MM-DD a YYYY-MM-DD"
    ventana_prediccion: str


def run_diagnostic_pipeline(
    price_data: Dict[str, pd.DataFrame],
    scores: Dict[str, pd.Series],
    calibration_cutoff: pd.Timestamp,
    alpha: float = 0.10,
    favorable_states: Optional[FrozenSet[int]] = None,
    regime_recalib_every: int = 63,
    regime_min_history: int = 756,
    max_horizon: int = DEFAULT_MAX_HORIZON,
    cost_per_side: float = DEFAULT_COST_PER_SIDE,
) -> PipelineResult:
    """
    price_data: símbolo -> DataFrame con columnas close/atr14 (y las que M3 necesite
        si favorable_states se activa: SPY/EFA/QQQ/GLD/DBC/TIP/TLT/AGG/VIX).
    scores: símbolo -> Series indexada por fecha con el score YA calculado por quien
        llama (este pipeline no genera scores, los consume — mismo principio que M2).
    calibration_cutoff: fechas < cutoff van a calibración de M2; fechas >= cutoff son
        las que se predicen y potencialmente se operan. Split ESTRICTO por fecha real.
    favorable_states: si se pasa, activa M3 como compuerta AND sobre la decisión de M2.
        Si es None, el gate no aplica — el resultado es idéntico a correr M1+M2 solos.
    """
    if not price_data:
        raise ValueError("price_data vacío")
    if not scores:
        raise ValueError("scores vacío")

    # --- M1: etiquetar cada símbolo con las barreras reales del motor ---
    per_symbol_labels: Dict[str, pd.DataFrame] = {}
    for symbol, df in price_data.items():
        if symbol not in scores:
            continue
        labels = label_symbol(df, max_horizon=max_horizon, cost_per_side=cost_per_side)
        if labels.empty:
            continue
        labels = labels.set_index("date")
        per_symbol_labels[symbol] = labels

    if not per_symbol_labels:
        raise ValueError("Ningún símbolo produjo etiquetas M1 (revisar price_data/scores)")

    # --- Combinar score (del llamador) + label (M1) por (símbolo, fecha) ---
    rows: List[dict] = []
    for symbol, labels in per_symbol_labels.items():
        symbol_scores = scores[symbol]
        common_dates = labels.index.intersection(symbol_scores.index)
        for d in common_dates:
            rows.append({
                "symbol": symbol,
                "date": d,
                "score": float(symbol_scores.loc[d]),
                "ret_net": float(labels.loc[d, "ret_net"]),
            })
    combined = pd.DataFrame(rows)
    if combined.empty:
        raise ValueError("Sin fechas en común entre scores y etiquetas M1 para ningún símbolo")

    # --- Split temporal ESTRICTO por fecha real, nunca por posición ---
    calibration_cutoff = pd.Timestamp(calibration_cutoff)
    calib_mask = combined["date"] < calibration_cutoff
    calib = combined[calib_mask]
    predict = combined[~calib_mask].copy()

    if calib.empty:
        raise ValueError("Sin datos de calibración antes de calibration_cutoff")
    if predict.empty:
        raise ValueError("Sin datos de predicción en/después de calibration_cutoff")

    # --- M2: calibrar SOLO con el pasado, predecir el resto ---
    engine = ConformalAbstentionEngine(alpha=alpha)
    calibracion = engine.calibrate(calib["score"].to_numpy(), calib["ret_net"].to_numpy())

    predicciones = [engine.predict(s) for s in predict["score"]]
    predict["point_estimate"] = [p.point_estimate for p in predicciones]
    predict["interval_width"] = [p.interval_width for p in predicciones]
    predict["abstenerse_m2"] = [p.abstenerse for p in predicciones]
    razon_m2 = [p.razon for p in predicciones]

    # --- M3: compuerta de régimen, AND explícito — nunca OR ---
    if favorable_states is not None:
        gate = WalkForwardRegimeGate(
            favorable_states=favorable_states,
            recalib_every=regime_recalib_every,
            min_history=regime_min_history,
        )
        fechas_unicas = sorted(predict["date"].unique())
        gate_por_fecha = gate.label_symbol_dates(price_data, fechas_unicas)
        predict["gate_operar"] = predict["date"].map(gate_por_fecha.to_dict())
        predict["operar"] = (~predict["abstenerse_m2"]) & predict["gate_operar"]
        predict["razon"] = [
            f"{r} | régimen: {'favorable' if g else 'desfavorable, gate bloquea'}"
            for r, g in zip(razon_m2, predict["gate_operar"])
        ]
    else:
        predict["gate_operar"] = True
        predict["operar"] = ~predict["abstenerse_m2"]
        predict["razon"] = razon_m2

    # --- Resumen: métrica primaria es vpp_bajo_abstencion sobre la decisión FINAL ---
    class _Decision:
        """Adaptador mínimo: vpp_bajo_abstencion espera .abstenerse/.point_estimate."""
        __slots__ = ("abstenerse", "point_estimate")

        def __init__(self, operar: bool, point_estimate: float):
            self.abstenerse = not operar
            self.point_estimate = point_estimate

    decisiones_finales = [
        _Decision(op, pe) for op, pe in zip(predict["operar"], predict["point_estimate"])
    ]
    resumen = vpp_bajo_abstencion(decisiones_finales, predict["ret_net"].tolist())

    return PipelineResult(
        detalle=predict.reset_index(drop=True),
        resumen=resumen,
        calibracion=calibracion,
        n_simbolos=len(per_symbol_labels),
        ventana_calibracion=f"{calib['date'].min().date()} a {calib['date'].max().date()}",
        ventana_prediccion=f"{predict['date'].min().date()} a {predict['date'].max().date()}",
    )
