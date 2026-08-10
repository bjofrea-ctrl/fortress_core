"""Capa de régimen de sentimiento V1 (AAII bull-bear spread).

Pre-registrada en PLAN_SENTIMIENTO.md §7 — NO cambiar estos valores sin
re-validar. El peso 0.50 quedó fijado por el OOS 2025-2026 con spec
congelada (veredicto CONFIRMA: G2/50 gana Brier 4/4 con Diebold-Mariano
p<0.05 en 4/4 horizontes).

Fuentes del diseño:
- H1: IC de AAII bull-bear negativo en 60d (-0.36 OOS, n_eff=36).
- H6: en euforia extrema, RSI/ER pierden poder e invierten (RSI -0.1254,
  ER -0.1122 @60d en el bucket alto) -> el régimen los "cuestiona".
- V4: subidas lentas con sentimiento bajo -> acumulación silenciosa;
  subidas rápidas con euforia -> distribución.
"""

SENTIMENT_REGIME_DOMINANCE: float = 0.50
SENTIMENT_EXTREME: float = 0.50
SENTIMENT_PANIC_SPREAD: float = -15.0
SENTIMENT_EUPHORIA_SPREAD: float = 15.0
AAII_SPREAD_BOUND: float = 35.0
ER_SLOW: float = 0.25
ER_FAST: float = 0.60
