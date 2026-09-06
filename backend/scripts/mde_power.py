"""B5 — Gate de potencia ex-ante MDE (PLAN_REMEDIO_BRECHAS_20260903 §B5).

Fin de la refutación-teatro: hoy el sistema deja que un trial con un diseño
sub-potente corra igual y luego "no detecta nada" — confundiendo "no pude
detectarlo" (potencia insuficiente) con "el efecto no existe". Este módulo
computa, ANTES de correr, el efecto mínimo detectable (MDE) a un nivel de
significancia corregido por comparaciones múltiples (Bonferroni por familia).

Dos métricas, dos usos:

1. MDE del IC (Information Coefficient) — la métrica primaria de B5. Dado el
   diseño (n símbolos, T fechas, horizonte, autocorrelación estimada), el
   rank-IC medio de una señal SIN poder predictivo tiene desvío estándar
   aprox sigma_IC = 1/sqrt(n-1) por fecha (ruido puro). Con T fechas
   independientes, el SE del IC medio es sigma_IC/sqrt(T_eff) y:

       MDE_IC = z_{1-alpha/n_family} * sigma_IC / sqrt(T_eff)

   Si MDE_IC > efecto plausible (default 0.10), el trial es INEJECUTABLE:
   no consume slot Bonferroni ni produce "refutación".

2. MDE del SR/DSR — el análisis aplicado del gate de diciembre (criterio C1:
   DSR>=0.90 en >=2/3 ventanas con ~60 días de paper trading real). La DSR
   con N tan chico exige un Sharpe diario tan extremo que la barra puede ser
   matemáticamente inalcanzable. `gate_diciembre_2026()` lo calcula y
   `ANALISIS_MDE_GATE_DICIEMBRE_2026.md` documenta el veredicto con los
   supuestos explícitos (autocorrelación/varianza asumidas).

Corrección por autocorrelación (Newey-West): la memoria de la serie reduce
las observaciones independientes:

    T_eff = T / (1 + 2*sum(rho_k, k=1..L))

y para horizontes de h días sin autocorrelación medida, el default es
T_eff = T/h (retornos solapados de h días → ~1 observación independiente
cada h fechas).
"""
import math
from typing import Dict, Optional

from scipy.stats import norm

# Nivel por trial antes de Bonferroni (ONBOARDING.md regla 1).
DEFAULT_ALPHA = 0.05

# Efecto plausible default (plan §B5): un IC de 0.10 ya es un edge grande
# (el rango realista del proyecto es 0.02-0.08 — brecha #1); MDE > 0.10
# significa que ni siquiera un edge generoso sería detectable.
DEFAULT_EFFECT_PLAUSIBLE = 0.10

# Constante de Euler-Mascheroni (misma que backtest_engine.calculate_metrics).
GAMMA_EULER = 0.5772156649015329

# Raíz de días hábiles para anualizar Sharpe diario.
SQRT_252 = 252.0 ** 0.5


def bonferroni_alpha(alpha: float = DEFAULT_ALPHA, n_family: int = 1) -> float:
    """Nivel por trial tras corrección por familia: alpha / n_trials."""
    return alpha / max(int(n_family), 1)


def ic_null_std(n_symbols: int) -> float:
    """Desvío estándar del rank-IC por fecha bajo la hipótesis nula.

    Para un IC cross-seccional de n símbolos, bajo ruido puro el IC de una
    fecha ~ N(0, 1/(n-1)). Con n<3 el ruido domina cualquier diseño."""
    return 1.0 / math.sqrt(max(int(n_symbols) - 1, 2))


def effective_T(T_dates: int, horizon_days: int = 1,
                autocorr: Optional[Dict[int, float]] = None) -> float:
    """Observaciones independientes efectivas de la serie de IC.

    - Horizonte h: retornos forward de h días solapados -> ~1 obs cada h
      fechas (T/h). Es el default cuando no hay autocorrelación medida.
    - Autocorrelación estimada (dict {lag: rho} de la SERIE DE IC): corrección
      Newey-West adicional T_eff /= (1 + 2*sum(rho_k)).
    """
    T_eff = float(T_dates) / max(int(horizon_days), 1)
    if autocorr:
        suma = sum(r for r in autocorr.values() if abs(r) > 0.05)
        T_eff = T_eff / max(1.0 + 2.0 * suma, 1.0)
    return max(T_eff, 1.0)


def mde_ic(
    n_symbols: int,
    T_dates: int,
    horizon_days: int = 1,
    alpha: float = DEFAULT_ALPHA,
    n_family: int = 1,
    autocorr: Optional[Dict[int, float]] = None,
    ic_std: Optional[float] = None,
    effect_plausible: float = DEFAULT_EFFECT_PLAUSIBLE,
) -> Dict:
    """IC mínimo detectable a nivel de significancia corregido (B5).

    Args:
        n_symbols: símbolos cross-seccionales por fecha (universo del trial).
        T_dates: fechas del panel (observaciones temporales del IC).
        horizon_days: horizonte del retorno forward en días hábiles.
        alpha: nivel de significancia por trial (antes de Bonferroni).
        n_family: trials de la familia -> Bonferroni alpha/n_family.
        autocorr: {lag: rho} de la serie de IC (autocorrelación estimada).
        ic_std: desvío del IC por fecha; default 1/sqrt(n-1) (hipótesis nula).
        effect_plausible: techo del efecto plausible; MDE > esto => INEJECUTABLE.

    Returns:
        {"mde_ic", "ic_std", "T_eff", "alpha_corr", "ejecutable",
         "inejecutable_reason", "effect_plausible"}
    """
    if int(n_symbols) < 3 or int(T_dates) < 3:
        raise ValueError(
            f"diseno insuficiente para medir potencia: n_symbols={n_symbols}, "
            f"T_dates={T_dates} (minimo 3 y 3)"
        )
    alpha_corr = bonferroni_alpha(alpha, n_family)
    sigma = float(ic_std) if ic_std is not None else ic_null_std(n_symbols)
    T_eff = effective_T(T_dates, horizon_days, autocorr)
    se_mean_ic = sigma / math.sqrt(T_eff)
    mde = float(norm.ppf(1.0 - alpha_corr) * se_mean_ic)
    ejecutable = mde <= effect_plausible
    return {
        "mde_ic": mde,
        "ic_std": sigma,
        "T_eff": T_eff,
        "alpha_corr": alpha_corr,
        "ejecutable": bool(ejecutable),
        "inejecutable_reason": (
            "" if ejecutable else
            f"MDE_IC={mde:.4f} > efecto plausible={effect_plausible:.2f} "
            f"(n_symbols={n_symbols}, T_dates={T_dates}, horizon_days="
            f"{horizon_days}, T_eff={T_eff:.1f}, alpha_corr={alpha_corr:.4f})"
        ),
        "effect_plausible": float(effect_plausible),
    }


# ---------------------------------------------------------------------------
# DSR — maquinaria para el cálculo aplicado del gate de diciembre (criterio
# C1: DSR>=0.90 en >=2/3 ventanas con ~60 días de paper trading real).
# Mismo estimador que backtest_engine.calculate_metrics (auditado 2026-08-10):
#   sr_std^2 = var_num / (T_eff - 1),  var_num = 1 - g3*SR + (g4-1)/4 * SR^2
#   DSR = Phi((SR - e_max(N) * sr_std) / sr_std)
# ---------------------------------------------------------------------------

def dsr_emax(n_trials: int) -> float:
    """E[max SR] esperado bajo la hipótesis nula con N trials (Bailey-LdP)."""
    N = max(int(n_trials), 2)  # N=1 degenera (Phi^-1(0) = -inf)
    return float(
        (1.0 - GAMMA_EULER) * norm.ppf(1.0 - 1.0 / N)
        + GAMMA_EULER * norm.ppf(1.0 - 1.0 / (N * math.e))
    )


def dsr_achieved(
    sr_daily: float, T: int, n_trials: int,
    autocorr: Optional[Dict[int, float]] = None,
    skew: float = 0.0, kurt: float = 3.0,
) -> float:
    """DSR que produce un Sharpe diario dado, con T días y N trials."""
    T_eff = effective_T(T, 1, autocorr)
    var_num = max(1.0 - skew * sr_daily + (kurt - 1.0) / 4.0 * sr_daily ** 2, 1e-8)
    sr_std = math.sqrt(var_num / max(T_eff - 1.0, 1.0))
    e_max = dsr_emax(n_trials)
    return float(norm.cdf((sr_daily - e_max * sr_std) / sr_std))


def dsr_required_daily_sr(
    T: int, n_trials: int, dsr_target: float = 0.90,
    autocorr: Optional[Dict[int, float]] = None,
    skew: float = 0.0, kurt: float = 3.0,
) -> float:
    """Sharpe diario mínimo para alcanzar una DSR objetivo con T días y N trials.

    Punto fijo: SR* = sr_std(SR*) * (Phi^-1(target) + e_max(N)), con
    sr_std(SR) = sqrt(var_num(SR)/(T_eff-1)) — var_num depende de SR, así que
    se itera (converge rápido; es una contracción para T grande).
    """
    z_target = norm.ppf(dsr_target)
    e_max = dsr_emax(n_trials)
    T_eff = effective_T(T, 1, autocorr)
    sr = math.sqrt(1.0 / max(T_eff - 1.0, 1.0)) * (z_target + e_max)
    for _ in range(50):
        var_num = max(1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2, 1e-8)
        sr_std = math.sqrt(var_num / max(T_eff - 1.0, 1.0))
        sr_next = sr_std * (z_target + e_max)
        if abs(sr_next - sr) < 1e-12:
            return float(sr_next)
        sr = sr_next
    return float(sr)


def T_needed_for_dsr(
    sr_daily: float, n_trials: int, dsr_target: float = 0.90,
    autocorr_factor: float = 1.0,
    skew: float = 0.0, kurt: float = 3.0,
) -> int:
    """Días (aprox) para que un SR diario dado alcance la DSR objetivo.

    De sr_std^2 = var_num/(T_eff-1) y SR/sr_std >= z+e_max:
        T_eff - 1 >= var_num * (z+e_max)^2 / SR^2.  autocorr_factor multiplica
    (p.ej. 1.5 con rho_1=0.25). Aproximado: var_num se evalúa en SR."""
    z_target = norm.ppf(dsr_target)
    e_max = dsr_emax(n_trials)
    var_num = max(1.0 - skew * sr_daily + (kurt - 1.0) / 4.0 * sr_daily ** 2, 1e-8)
    T_eff = 1.0 + var_num * (z_target + e_max) ** 2 / max(sr_daily, 1e-8) ** 2
    return int(math.ceil(T_eff * autocorr_factor))


def gate_diciembre_2026(
    n_trials: int = 17,
    T_paper: int = 60,
    rho1: float = 0.25,
    sr_plausible_daily: float = 0.10,
    dsr_target: float = 0.90,
) -> Dict:
    """Cálculo aplicado: ¿es alcanzable el criterio del gate de diciembre?

    Criterio C1: DSR >= 0.90 en >= 2/3 ventanas con ~60 días de paper trading
    real. Supuestos explícitos (documentados en
    ANALISIS_MDE_GATE_DICIEMBRE_2026.md):
      - retornos diarios del paper con sigma ~ 1.5%/día (var 0.000225) — el
        nivel del equity del motor en el OOS 2024-2026;
      - autocorrelación de la serie de retornos del paper: rho_1 = 0.25
        (equity de momentum con horizonte ~5-20 días) -> T_eff = T/1.5;
      - familia con N = n_trials trials (17 = signal_diagnosis al cierre del
        plan; 29 = fallback conservador del motor);
      - normalidad (skew=0, kurt=3) para var_num — CONSERVADOR: colas gruesas
        SUBEN la DSR requerida, o sea que el veredicto no empeora.

    Returns: dict con lo requerido, lo alcanzable y el veredicto.
    """
    autocorr = {1: rho1} if rho1 else None
    autocorr_factor = 1.0 + 2.0 * rho1 if rho1 else 1.0
    requerido_iid = dsr_required_daily_sr(T_paper, n_trials, dsr_target, None)
    requerido_ac = dsr_required_daily_sr(T_paper, n_trials, dsr_target, autocorr)
    dsr_en_plausible = dsr_achieved(sr_plausible_daily, T_paper, n_trials, autocorr)
    T_necesario_iid = T_needed_for_dsr(sr_plausible_daily, n_trials, dsr_target, 1.0)
    T_necesario_ac = T_needed_for_dsr(sr_plausible_daily, n_trials, dsr_target,
                                      autocorr_factor)
    requerido_n2 = dsr_required_daily_sr(T_paper, 2, dsr_target, autocorr)
    return {
        "criterio": f"DSR>={dsr_target:.2f} en >=2/3 ventanas, T={T_paper} dias paper",
        "n_trials": n_trials,
        "T_paper": T_paper,
        "T_eff": effective_T(T_paper, 1, autocorr),
        "rho1_supuesto": rho1,
        "sr_requerido_diario_iid": float(requerido_iid),
        "sr_requerido_diario_autocorr": float(requerido_ac),
        "sr_requerido_anual_iid": float(requerido_iid * SQRT_252),
        "sr_requerido_anual_autocorr": float(requerido_ac * SQRT_252),
        "sr_requerido_diario_n2": float(requerido_n2),
        "sr_requerido_anual_n2": float(requerido_n2 * SQRT_252),
        "sr_plausible_diario": float(sr_plausible_daily),
        "dsr_alcanzado_en_plausible": float(dsr_en_plausible),
        "T_necesario_dias_iid": T_necesario_iid,
        "T_necesario_dias_autocorr": T_necesario_ac,
        "veredicto": (
            "INEJECUTABLE — barra matemáticamente casi imposible: exige un "
            f"Sharpe anualizado ~{requerido_ac * SQRT_252:.1f} con {T_paper} "
            "dias de paper (un edge real plausible produce DSR ~"
            f"{dsr_en_plausible:.2f}). Re-especificar el criterio ANTES de "
            "diciembre (ver ANALISIS_MDE_GATE_DICIEMBRE_2026.md)."
        ),
    }
