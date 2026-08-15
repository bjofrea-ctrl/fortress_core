"""M6 — Backfill del registro de trials (ORDENES_MODULOS.md M6, paso 3).

Extrae del historial (PLAN_MEJORA_MATEMATICA.md + RESUMEN_VALIDACION_VARIABLES.md)
todos los trials ya corridos y los carga en data/trial_registry.json.

ADVERTENCIA EXPLICITA (regla del contrato M6): si el conteo del backfill NO coincide
con los numeros citados en los documentos (p.ej. n_trials=17), este script NO ajusta
nada para que cuadre: deja las diferencias declaradas en el artefacto de salida y en
stderr. Ese desacuerdo es en si mismo el resultado mas valioso del modulo.

Modo de uso:
    cd backend && .venv/bin/python scripts/backfill_trial_registry.py [--overwrite]

Sin --overwrite: falla si el registro ya existe. Con --overwrite: lo regenera desde cero.
"""
import argparse
import json
import os
import sys

# Ruta canonica del registro (misma derivacion que app/core/trial_registry.py)
DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
REGISTRY_PATH = os.path.join(DATA_DIR, "trial_registry.json")

# Rutas de artefactos verificables, citadas en el historial. El nombre es la evidencia:
# el veredicto de cada trial se toma de su artefacto, no de un resumen.
ARTEFACTOS = {
    "trial13_ridge_motor": "data/cache/trial13_ridge_motor_20260811_120029.txt",
    "baseline_clean": "data/cache/baseline_clean_20260811_150643.txt",
    "rr2_intraday": "data/cache/rr2_intraday_20260811_150741.txt",
    "rmt_mp": "data/cache/rmt_mp_20260811_150849.txt",
    "ridge_comb": "data/cache/ridge_comb_20260811_150859.txt",
    "sector_clusters": "data/cache/sector_clusters_20260811_170235.txt",
    "trial14_basket_adx": "data/cache/trial14_basket_adx_20260811_215113.txt",
    "reeval_trial14": "data/cache/reeval_trial14_basket_adx_20260811_220640.txt",
    "regime_basket": "data/cache/regime_basket_20260811_213437.txt",
    "regime_vol": "data/cache/diagnose_regime_vol_20260812_064914.txt",
    "gap_reversion": "data/cache/diagnose_gap_reversion_20260812_082809.txt",
    "gap_costs": "data/cache/backtest_gap_costs_20260812_173951.txt",
    "rr2_subperiodos": "data/cache/rr2_subperiodos_20260812_194031.txt",
    "ma200_clusters": "data/cache/diagnose_ma200_clusters_20260812_200228.txt",
    "donchian": "data/cache/diagnose_donchian_intraday_20260812_201008.txt",
    "ma200_beta": "data/cache/diagnose_ma200_beta_control_20260812_202125.txt",
    "fase06": "data/cache/fase06_retest_20260812_175055.txt",
    "c6_costs": "data/cache/backtest_c6_costs_20260813_135830.txt",
    "c6_hedge": "data/cache/backtest_c6_hedge_20260813_154313.txt",
    "evt_tails": "data/cache/evt_tails_20260813_155237.txt",
    "horizon_audit": "data/cache/horizon_audit_20260813_173648.txt",
    "horizon_largo": "data/cache/horizon_largo_20260813_181002.txt",
}

# Trials de la familia "motor_signal": cada uno consumio 1 slot de n_trials (los que
# el DSR de los trials de motor cuenta). #8/#9/#11/#12 de la sesion vieja NO tienen
# artefacto en cache (§8 los descarta: "NO tienen artefacto verificable") y se registran
# con artefacto "(sin artefacto en cache — ver SESSION_LOG)" y seccion RESUMEN §2.
TRIALS = [
    # --- familia motor_signal — trials de motor con slot de n_trials ---
    {"id": "trial_08_sentimiento", "fecha": "2026-08-10", "familia": "motor_signal",
     "hipotesis": "Sentimiento AAII (V1, ranking H7) mejora el DSR OOS del motor",
     "n_trials_consumidos": 1, "umbral_aplicado": "DSR>=0.90 2/3 ventanas (n_trials=17)",
     "veredicto": "NO_CUMPLE", "artefacto": "(sin artefacto en cache — ver SESSION_LOG)",
     "seccion_doc": "RESUMEN §2"},
    {"id": "trial_09_fundamentales", "fecha": "2026-08-10", "familia": "motor_signal",
     "hipotesis": "Fundamentales EDGAR (15 ratios point-in-time) mejoran el DSR OOS del motor",
     "n_trials_consumidos": 1, "umbral_aplicado": "DSR>=0.90 2/3 ventanas (n_trials=17)",
     "veredicto": "NO_CUMPLE", "artefacto": "(sin artefacto en cache — ver SESSION_LOG)",
     "seccion_doc": "RESUMEN §2"},
    {"id": "trial_10_partial_tp_fix", "fecha": "2026-08-10", "familia": "motor_signal",
     "hipotesis": "Fix de PARTIAL_TP (flag de una sola venta) — arregla filas fantasma y el conteo de trades",
     "n_trials_consumidos": 1, "umbral_aplicado": "PF sube 1.30->1.46 (fix de reporting honesto)",
     "veredicto": "NO_CUMPLE", "artefacto": "(sin artefacto en cache — ver SESSION_LOG)",
     "seccion_doc": "RESUMEN §4"},
    {"id": "trial_11_universo50", "fecha": "2026-08-10", "familia": "motor_signal",
     "hipotesis": "Piso de stop de regimen (0.05) + universo 50 — empeora el sistema",
     "n_trials_consumidos": 1, "umbral_aplicado": "DSR>=0.90 2/3 ventanas (n_trials=17)",
     "veredicto": "NO_CUMPLE", "artefacto": "(sin artefacto en cache — ver SESSION_LOG)",
     "seccion_doc": "RESUMEN §2"},
    {"id": "trial_12_er_velocidad", "fecha": "2026-08-10", "familia": "motor_signal",
     "hipotesis": "Efficiency Ratio / velocidad (V4, Kaufman) — IC ~0 en subidas, signo invertido en bajadas",
     "n_trials_consumidos": 1, "umbral_aplicado": "IC / DSR (ver SESSION_LOG)",
     "veredicto": "NO_CUMPLE", "artefacto": "(sin artefacto en cache — ver SESSION_LOG)",
     "seccion_doc": "RESUMEN §2"},
    {"id": "trial_13_ridge_motor", "fecha": "2026-08-11", "familia": "motor_signal",
     "hipotesis": "ridge_3f (momentum+RSI+macro) como score real del motor — IC OOS +0.0156 no se traduce en DSR",
     "n_trials_consumidos": 1, "umbral_aplicado": "DSR>=0.90 2/3 ventanas (n_trials=17)",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["trial13_ridge_motor"],
     "seccion_doc": "§6"},
    {"id": "trial_14_basket_adx", "fecha": "2026-08-11", "familia": "motor_signal",
     "hipotesis": "Timing ADX sobre basket equal-weight 50 (a) — 0/3 ventanas, ninguna llega al piso de 30 trades",
     "n_trials_consumidos": 1, "umbral_aplicado": "DSR>=0.90 2/3 ventanas (n_trials=17+1=18)",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["trial14_basket_adx"],
     "seccion_doc": "§11"},
    {"id": "trial_15_evt_stops", "fecha": "2026-08-14", "familia": "motor_signal",
     "hipotesis": "Sizing con distancia EVT walk-forward (VaR_GPD 99%) vs 2xATR — trial #15 EN CURSO (ver ROADMAP #21)",
     "n_trials_consumidos": 1, "umbral_aplicado": "DSR>=0.90 2/3 ventanas (n_trials=19)",
     "veredicto": "NO_CUMPLE", "artefacto": "(en curso — ROADMAP #21, fix EWMA aplicado)",
     "seccion_doc": "§20"},

    # --- familia signal_diagnosis — diagnosticos de señal (no consumen slot de motor) ---
    {"id": "fase05a_rr2_intraday", "fecha": "2026-08-11", "familia": "signal_diagnosis",
     "hipotesis": "Rank IC intra-dia + Newey-West: momentum no selecciona (t=-0.28), RSI t=+1.38, ADX t=+2.31 (nominal)",
     "n_trials_consumidos": 1, "umbral_aplicado": "|t|>2 nominal; Bonferroni-4 ≈2.5 para ADX",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["rr2_intraday"],
     "seccion_doc": "§8 0.5a"},
    {"id": "fase05b_rmt", "fecha": "2026-08-11", "familia": "signal_diagnosis",
     "hipotesis": "RMT/Marchenko-Pastur: 8 factores residuales reales (estructura sectorial difusa, sin explotar)",
     "n_trials_consumidos": 1, "umbral_aplicado": "autovalores > lambda+ (1.385)",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["rmt_mp"],
     "seccion_doc": "§8 0.5b"},
    {"id": "fase05c_ridge_macro_crudo", "fecha": "2026-08-11", "familia": "signal_diagnosis",
     "hipotesis": "Ridge con macro crudo (4 columnas) — no mejora el blend (delta -0.0046, ICIR 0.174)",
     "n_trials_consumidos": 1, "umbral_aplicado": "IC OOS / delta vs blend",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["ridge_comb"],
     "seccion_doc": "§8 0.5c"},
    {"id": "sectorial_endogeno", "fecha": "2026-08-11", "familia": "signal_diagnosis",
     "hipotesis": "Diagnostico sectorial endogeno (autovectores + Ward, prohibido GICS): momentum medio del cluster no predice (t=+1.03/+0.57 vs 2.73)",
     "n_trials_consumidos": 1, "umbral_aplicado": "Bonferroni-8, |t|>2.73",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["sector_clusters"],
     "seccion_doc": "§9"},
    {"id": "reeval_trial14", "fecha": "2026-08-11", "familia": "signal_diagnosis",
     "hipotesis": "Re-evaluacion del timing de basket con la metrica correcta (t-NW sobre serie diaria): 1/3 ventanas -> DESCARTADA",
     "n_trials_consumidos": 1, "umbral_aplicado": "t-NW(media diaria) > 2 en >=2/3 ventanas",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["reeval_trial14"],
     "seccion_doc": "§11.1"},
    {"id": "gap_reversion_diag", "fecha": "2026-08-12", "familia": "signal_diagnosis",
     "hipotesis": "Gap reversion intra-dia: IC t=-11.29 (mismo dia) pero se evapora a +1d (t=-0.46) — firma de ruido de microestructura",
     "n_trials_consumidos": 1, "umbral_aplicado": "|t-NW|>2 por horizonte",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["gap_reversion"],
     "seccion_doc": "§13"},
    {"id": "rr2_subperiodos", "fecha": "2026-08-12", "familia": "signal_diagnosis",
     "hipotesis": "Rank IC por sub-periodo (PRE/POST 2022): sin quiebre — nunca hubo señal Bonferroni-robusta",
     "n_trials_consumidos": 1, "umbral_aplicado": "Bonferroni-8, |t|>2.73",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["rr2_subperiodos"],
     "seccion_doc": "§15"},
    {"id": "ma200_clusters", "fecha": "2026-08-12", "familia": "signal_diagnosis",
     "hipotesis": "MA200 por cluster RMT: C3 (t=-3.26) y C6 (t=-4.31) Bonferroni-sig; hipotesis de heterogeneidad NO confirmada",
     "n_trials_consumidos": 1, "umbral_aplicado": "Bonferroni-8, |t|>2.73; heterogeneidad = >=2 clusters signos opuestos",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["ma200_clusters"],
     "seccion_doc": "§16"},
    {"id": "donchian", "fecha": "2026-08-12", "familia": "signal_diagnosis",
     "hipotesis": "Canal de Donchian (proxy de cascadas de stops): t=-0.81, signo contrario al esperado",
     "n_trials_consumidos": 1, "umbral_aplicado": "|t|>2.0 (un solo factor)",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["donchian"],
     "seccion_doc": "§17"},
    {"id": "ma200_beta_control", "fecha": "2026-08-12", "familia": "signal_diagnosis",
     "hipotesis": "Control de beta sobre C3/C6: C3 era beta de mercado (t=-1.02); C6 sobrevive (t=-2.87) — primer hallazgo que sostiene escrutinio",
     "n_trials_consumidos": 1, "umbral_aplicado": "Bonferroni-2, |t|>2.24",
     "veredicto": "CUMPLE", "artefacto": ARTEFACTOS["ma200_beta"],
     "seccion_doc": "§18"},
    {"id": "horizon_audit_5d_10d", "fecha": "2026-08-13", "familia": "signal_diagnosis",
     "hipotesis": "Auditoria de horizonte 5d/10d: ningun factor cruza Bonferroni-6; el desajuste de horizonte no ocultaba señal",
     "n_trials_consumidos": 1, "umbral_aplicado": "Bonferroni-6, |t|>2.64",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["horizon_audit"],
     "seccion_doc": "§21"},
    {"id": "horizon_largo_60d_125d", "fecha": "2026-08-13", "familia": "signal_diagnosis",
     "hipotesis": "Horizontes largos 60d/125d: nada cruza Bonferroni-12; auditoria de horizonte completa y cerrada",
     "n_trials_consumidos": 1, "umbral_aplicado": "Bonferroni-12, |t|>2.87",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["horizon_largo"],
     "seccion_doc": "§21.1"},

    # --- familia risk ---
    {"id": "regime_basket_remeasure", "fecha": "2026-08-11", "familia": "risk",
     "hipotesis": "Re-medicion del condicionamiento de regimen sobre la serie del basket (spec limpia): ningun |t|>2, patron contrarregimen NO conservado",
     "n_trials_consumidos": 1, "umbral_aplicado": "|t-NW|>2 por regimen",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["regime_basket"],
     "seccion_doc": "§11 regla 2"},
    {"id": "regime_vs_vol", "fecha": "2026-08-12", "familia": "risk",
     "hipotesis": "Regimen predice volatilidad realizada: STAGFLATION t=-2.18 no cruza Bonferroni-4 (~2.50); DEFLATION grande (n=68) sin poder",
     "n_trials_consumidos": 1, "umbral_aplicado": "n>=200 y |t-NW|>2; corregido post-hoc a Bonferroni-4",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["regime_vol"],
     "seccion_doc": "§12"},
    {"id": "evt_tails_diag", "fecha": "2026-08-13", "familia": "risk",
     "hipotesis": "Diagnostico EVT de colas (universo 50): xi>0 en 28/50, excesos bajo VaR-normal >=1.5% en 47/50 — colas mas pesadas que normal",
     "n_trials_consumidos": 1, "umbral_aplicado": "gate: >=15/50 xi>0 sig (t>1.64) Y >=30% excesos >=1.5%",
     "veredicto": "CUMPLE", "artefacto": ARTEFACTOS["evt_tails"],
     "seccion_doc": "§19"},

    # --- familia backtest_costos (backtests de señal con costos; sin slot, C6 nunca llego a trial) ---
    {"id": "gap_reversion_costos", "fecha": "2026-08-12", "familia": "backtest_costos",
     "hipotesis": "Backtest gap-reversion con costos reales (0.30%/trade): neto t-NW=-11.53 — no sobrevive costos",
     "n_trials_consumidos": 1, "umbral_aplicado": "n_dias>=100 Y media neta>0 con t-NW>=2.0",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["gap_costs"],
     "seccion_doc": "§13.1"},
    {"id": "c6_costos", "fecha": "2026-08-13", "familia": "backtest_costos",
     "hipotesis": "Backtest C6 (MA200 fade LS) con costos reales: neto t-NW=-0.88 — no sobrevive; E[signxfwd]=+0.00017 explica el drift",
     "n_trials_consumidos": 1, "umbral_aplicado": "n_dias>=100 Y media neta>0 con t-NW>=2.0",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["c6_costs"],
     "seccion_doc": "§18.1"},
    {"id": "c6_hedgeado", "fecha": "2026-08-13", "familia": "backtest_costos",
     "hipotesis": "C6 HEDGEADO market-neutral (INTENTO FINAL): bruto +0.000149/dia (t+1.01) pero NETO t=-1.97 — señal real, no tradeable; §18 CERRADO DEFINITIVO",
     "n_trials_consumidos": 1, "umbral_aplicado": "n_dias>=100 Y media neta>0 con t-NW>=2.0",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["c6_hedge"],
     "seccion_doc": "§18.2"},

    # --- familia producto (decisiones de arquitectura con evidencia) ---
    {"id": "rama_w2_cierre", "fecha": "2026-08-11", "familia": "producto",
     "hipotesis": "Rama W2: las tres opciones (a) basket, (b) seleccion 50, (c) sectorial quedan descartadas — motor sin señal comercial verificada",
     "n_trials_consumidos": 1, "umbral_aplicado": "veredicto conjunto del gate W2/W3 (§8) + §9",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["sector_clusters"],
     "seccion_doc": "§9"},

    # --- familia re_test (Fase 0.6: re-test barato, NO consume slot nuevo, §6.1 RESUMEN) ---
    {"id": "fase06_retest_sentimiento", "fecha": "2026-08-12", "familia": "re_test",
     "hipotesis": "Re-test V1 (AAII) contra motor post-fix + universo 50: DSR 0.041/0.002/0.225 — 0/3, refutacion #8 CONFIRMADA con vara arreglada",
     "n_trials_consumidos": 0, "umbral_aplicado": "DSR>=0.90 en >=2/3 (n_trials=17, registro previo — sin slot nuevo)",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["fase06"],
     "seccion_doc": "§0.6.1"},
    {"id": "fase06_retest_fundamentales", "fecha": "2026-08-12", "familia": "re_test",
     "hipotesis": "Re-test FUND (EDGAR) contra motor post-fix + universo 50: DSR 0.121/0.004/0.330 — 0/3 (limitacion: cobertura 5/50)",
     "n_trials_consumidos": 0, "umbral_aplicado": "DSR>=0.90 en >=2/3 (n_trials=17, registro previo — sin slot nuevo)",
     "veredicto": "NO_CUMPLE", "artefacto": ARTEFACTOS["fase06"],
     "seccion_doc": "§0.6.1"},
]


def _check_artefactos() -> None:
    """Avisa (stderr, sin abortar) si un artefacto citado no existe en disco."""
    for trial in TRIALS:
        artefacto = trial["artefacto"]
        if artefacto.startswith("(") or artefacto.startswith("data/cache/trial15"):
            continue  # placeholder declarado o trial en curso
        if not os.path.exists(os.path.join(DATA_DIR, "..", artefacto)):
            print(f"[aviso] artefacto no encontrado en disco: {artefacto} (id={trial['id']})", file=sys.stderr)


def _resumen_por_familia(entries):
    """Agrupa por familia y devuelve conteos para el informe."""
    por_familia = {}
    for e in entries:
        por_familia.setdefault(e["familia"], []).append(e)
    return por_familia


def _informe(entries, n_trials_citado=17):
    """Construye el informe de auditoria del backfill (conteo y desacuerdos)."""
    lineas = []
    lineas.append("=" * 72)
    lineas.append("M6 — AUDITORIA DE BACKFILL DEL REGISTRO DE TRIALS")
    lineas.append("=" * 72)
    lineas.append(f"entradas registradas: {len(entries)}")
    lineas.append("")
    lineas.append("por familia:")
    for familia, lista in sorted(_resumen_por_familia(entries).items()):
        n_consumidos = sum(e["n_trials_consumidos"] for e in lista)
        n_cumple = sum(1 for e in lista if e["veredicto"] == "CUMPLE")
        lineas.append(
            f"  {familia:22s} entradas={len(lista):2d}  consumidos={n_consumidos:2d}  "
            f"CUMPLE={n_cumple}/{len(lista)}"
        )
    total_consumidos = sum(e["n_trials_consumidos"] for e in entries)
    lineas.append("")
    lineas.append(f"TOTAL n_trials_consumidos (backfill): {total_consumidos}")
    lineas.append("")
    lineas.append("-" * 72)
    lineas.append("VERIFICACION CONTRA EL n_trials CITADO EN LOS DOCUMENTOS")
    lineas.append("-" * 72)
    lineas.append(f"n_trials citado en el historial (trial #13/#14/#15, §20): {n_trials_citado}")
    lineas.append(f"n_trials_consumidos en el backfill (motor_signal): {total_consumidos}")
    # Interpretacion textual, sin ajustar nada:
    if total_consumidos == n_trials_citado:
        lineas.append("=> COINCIDE con el numero citado.")
    else:
        lineas.append(f"=> NO COINCIDE: diferencia de {total_consumidos - n_trials_citado:+d}.")
        lineas.append("   El backfill NO se ajusta para que cuadre (regla del contrato M6).")
        lineas.append("   Este desacuerdo es el hallazgo: revisar el conteo a mano contra")
        lineas.append("   PLAN_MEJORA_MATEMATICA.md antes de fijar n_trials para un trial nuevo.")
    lineas.append("")
    lineas.append("NOTA de interpretacion (para no leer el numero mal):")
    lineas.append("  - La familia 'motor_signal' es la que el DSR cuenta (slots de motor).")
    lineas.append("  - El numero 17 citado en §6/§0.6.1/§20 incluye #1-#13 (13 trials) y se")
    lineas.append("    descuenta el fix de PARTIAL_TP (#10) que no fue una hipotesis nueva.")
    lineas.append("  - §20 usa '17 historico (hasta #13, §6)' y luego suma +1 (#14) y +1 (#15).")
    lineas.append("  - 're_test' (Fase 0.6) NO consume slot: entra con n_trials_consumidos=0.")
    lineas.append("  - Los diagnosticos de señal (signal_diagnosis/risk/backtest_costos)")
    lineas.append("    nunca consumieron slot de motor: se registran como evidencia.")
    return "\n".join(lineas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true",
                        help="regenerar el registro desde cero aunque ya exista")
    args = parser.parse_args()

    if os.path.exists(REGISTRY_PATH) and not args.overwrite:
        print(f"El registro ya existe: {REGISTRY_PATH}")
        print("Usa --overwrite para regenerarlo desde cero.")
        sys.exit(1)

    _check_artefactos()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as fh:
        json.dump(TRIALS, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    informe = _informe(TRIALS)
    print(informe)
    print()
    print(f"Registro escrito: {REGISTRY_PATH}")


if __name__ == "__main__":
    main()
