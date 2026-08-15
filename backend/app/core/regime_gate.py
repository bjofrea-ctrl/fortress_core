"""M3 — Compuerta de régimen (DISENO_INSTRUMENTO.md §7 etapa 3).

MOTIVO: el factor macro compuesto es el más fuerte medido en todo el proyecto
(IC +0.13, RESUMEN_VALIDACION_VARIABLES.md §1) — más que momentum o RSI. Pero Fase 2
midió que es CONTRA-RÉGIMEN: IC +0.198 en GOLDILOCKS, −0.173 en DEFLATION. Promediado
entre regímenes da el +0.13 mediocre que nunca cruza DSR. Esa señal nunca se probó
como COMPUERTA (operar solo en régimen favorable, abstenerse en el resto) — solo como
término lineal ponderado dentro de `ridge_3f`, que se refutó por otra razón (trial #13,
gates/sizing/costos/salidas — no por el término macro en sí).

Un peso promedia los dos regímenes. Una compuerta los separa. Es la misma clase de
corrección que el pooled-vs-intra-día en rank IC, que ONBOARDING.md llama "el error
más importante que se corrigió en toda la investigación" — aplicada a otra dimensión.

POR QUÉ WALK-FORWARD (no negociable, no un detalle de implementación): el
`GlobalRegimeClassifier` (HMM) existente se ajusta con `fit()` sobre TODO el
`price_data` que se le pase. Si se ajusta una sola vez sobre 2015-2026 y ese modelo
se usa para etiquetar W1 (2020-2021), el modelo "sabe" cómo terminó el mercado en
2026 al clasificar 2020 — es lookahead, la misma trampa que ROADMAP.md ítem 21 marcó
para los stops EVT. Acá se re-ajusta cada `recalib_every` días hábiles usando SOLO
datos estrictamente anteriores a la fecha de recalibración, igual que el walk-forward
de `trial_evt_stops.py` (recalibración cada 63d, ventana móvil).

QUÉ NO HACE ESTE MÓDULO: no decide qué estados son "favorables". Eso es una hipótesis
de investigación que se pre-registra y se prueba (DSR≥0.90, Bonferroni, walk-forward
del HMM en sí) — este módulo es la infraestructura de la compuerta, construida libre
y sin ceremonia; el TRIAL que la usa para afirmar "esto mejora el motor" sí necesita
pre-registro antes de correr (regla no-negociable #1/#2 de ONBOARDING.md).
"""
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List

import pandas as pd

from app.core.regime_classifier import GlobalRegimeClassifier

DEFAULT_RECALIB_EVERY = 63    # días hábiles, mismo valor que trial_evt_stops.py
DEFAULT_MIN_HISTORY = 756     # ventana mínima antes de la primera recalibración (~3 años)


@dataclass(frozen=True)
class RegimeGateResult:
    """Etiqueta de compuerta para UNA fecha."""
    date: pd.Timestamp
    regime_state: int
    regime_name: str
    operar: bool
    fecha_recalibracion: pd.Timestamp   # la recalibración vigente que produjo esta etiqueta


@dataclass
class WalkForwardDiagnostics:
    """Para verificar que el walk-forward se comportó como se espera antes de
    confiar en las etiquetas — no se interpreta el resultado sin mirar esto."""
    n_recalibraciones: int
    fechas_recalibracion: List[pd.Timestamp] = field(default_factory=list)
    n_fechas_etiquetadas: int = 0
    distribucion_regimenes: Dict[int, int] = field(default_factory=dict)


class WalkForwardRegimeGate:
    """
    Compuerta de régimen walk-forward: etiqueta cada fecha con `operar=True/False`
    según si el estado HMM vigente en ESA fecha (ajustado solo con datos previos)
    está en el conjunto de estados favorables declarado.

    El conjunto de estados favorables es un parámetro, no una constante de este
    módulo — la hipótesis de investigación ("GOLDILOCKS es favorable, DEFLATION no")
    se declara en el pre-registro del trial que use esta compuerta, no acá.
    """

    def __init__(self, favorable_states: FrozenSet[int],
                 recalib_every: int = DEFAULT_RECALIB_EVERY,
                 min_history: int = DEFAULT_MIN_HISTORY,
                 n_states: int = 4):
        if not favorable_states:
            raise ValueError("favorable_states no puede estar vacío — declarar al menos un régimen")
        self.favorable_states = favorable_states
        self.recalib_every = recalib_every
        self.min_history = min_history
        self.n_states = n_states

    def label_series(self, price_data: Dict[str, pd.DataFrame]) -> tuple[pd.Series, WalkForwardDiagnostics]:
        """
        Devuelve una Serie booleana indexada por fecha (`True` = operar) y el
        diagnóstico del proceso walk-forward.

        Cada bloque de `recalib_every` días se etiqueta con un modelo ajustado
        EXCLUSIVAMENTE sobre datos anteriores a la fecha de recalibración del bloque
        — invariante verificado con assert, no solo declarado.
        """
        probe = GlobalRegimeClassifier(n_states=self.n_states)
        all_dates = probe._extract_features(price_data).index
        if len(all_dates) < self.min_history + self.recalib_every:
            raise ValueError(
                f"Historia insuficiente: {len(all_dates)} fechas de features, se necesitan "
                f"al menos {self.min_history + self.recalib_every} (min_history + un bloque)."
            )

        labels: Dict[pd.Timestamp, bool] = {}
        states: Dict[pd.Timestamp, int] = {}
        recalib_dates: List[pd.Timestamp] = []

        recalib_idx = self.min_history
        while recalib_idx < len(all_dates):
            recalib_date = all_dates[recalib_idx]
            window_end_idx = min(recalib_idx + self.recalib_every, len(all_dates))
            window_end_date = all_dates[window_end_idx - 1]
            recalib_dates.append(recalib_date)

            # Ajustar SOLO con datos estrictamente anteriores a recalib_date.
            train_data = {
                sym: df[df.index < recalib_date] for sym, df in price_data.items()
            }
            clf = GlobalRegimeClassifier(n_states=self.n_states)
            clf.fit(train_data)

            # Predecir sobre datos hasta el final de la ventana (incluye el propio
            # bloque a etiquetar), pero solo se PUBLICAN las fechas >= recalib_date.
            predict_data = {
                sym: df[df.index <= window_end_date] for sym, df in price_data.items()
            }
            series = clf.predict_regime_series(predict_data)

            block_dates = all_dates[recalib_idx:window_end_idx]
            for d in block_dates:
                if d not in series.index:
                    continue
                # Assert anti-lookahead: la fecha etiquetada nunca es anterior a la
                # recalibración que la etiqueta (mismo patrón que trial_evt_stops.py).
                assert d >= recalib_date, (
                    f"lookahead: fecha {d} etiquetada con recalibración de {recalib_date}"
                )
                state = int(series.loc[d])
                states[d] = state
                labels[d] = state in self.favorable_states

            recalib_idx = window_end_idx

        result = pd.Series(labels).sort_index()
        result.index.name = "date"

        distribucion: Dict[int, int] = {}
        for s in states.values():
            distribucion[s] = distribucion.get(s, 0) + 1

        diag = WalkForwardDiagnostics(
            n_recalibraciones=len(recalib_dates),
            fechas_recalibracion=recalib_dates,
            n_fechas_etiquetadas=len(result),
            distribucion_regimenes=distribucion,
        )
        return result, diag

    def label_symbol_dates(self, price_data: Dict[str, pd.DataFrame],
                            symbol_dates: List[pd.Timestamp]) -> pd.Series:
        """
        Conveniencia para conectar con M1: dado un conjunto de fechas de entrada
        (ej. las fechas de `barrier_labeling.label_symbol`), devuelve `operar` para
        cada una. Fechas fuera del rango etiquetado quedan `False` (abstención por
        defecto — no hay régimen conocido, no se opera, nunca al revés).
        """
        gate_series, _ = self.label_series(price_data)
        return pd.Series(
            [bool(gate_series.get(d, False)) for d in symbol_dates],
            index=symbol_dates,
        )
