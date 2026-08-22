# Resumen — T2.3: Hurst exponent y realized_vol_regime (features de régimen por símbolo)

Fecha: 2026-08-21 · Ticket T2.3 de `PLAN_INTEGRACION_INDICAGENT.md` (líneas 920-975)

**Código:** ya implementado (sesión previa, Kilo). Este documento cierra el ticket con
la medición que faltaba (criterios 1 y 2 del plan): tests unitarios en verde con
evidencia de calibración, y diagnóstico de IC de ambas features contra retornos
futuros con el rigor del repo.

## 1. Estado de los tests (criterio 1 — líneas 964-965)

Los 2 tests fallaban. Diagnóstico con evidencia: **era el test, no el código**. Ambos
fueron recalibrados al comportamiento real del estimador (ver sección 3); el código
de `indicators.py` no se tocó (el `hurst_exponent` vectorizado con `sliding_window_view`
sigue semánticamente idéntico al rolling original).

| Test | Causa raíz | Fix aplicado |
|---|---|---|
| `test_hurst_exponent_ar1_persistente_mayor_que_antipersistente` | `n=800` + semilla 7 del rng compartido era un **outlier de muestra finita**: margen 0.103 (H 0.499 vs 0.395). Con n≥2000 ninguna de las semillas probadas cae bajo 0.2 | Panel `n=3000` (config de producción window=100). Distribución medida en 50 semillas: min 0.230, p5 0.242, media 0.282 — 0/50 bajo el umbral 0.2. El umbral NO se bajó |
| `test_realized_vol_regime_detecta_shock_de_volatilidad` | La aserción "últimos 20 días todos > 1.2" era frágil por ruido de muestreo del std de 20 días (un día puntual cae bajo 1.2 en ~la mitad de las semillas) y porque al final del shock la ventana larga (100d) ya absorbió los 60 días de shock → el ratio se comprime hacia ~1.27 (comportamiento correcto del proxy) | Aserciones robustas sobre 30 semillas (mismas σ): pico del ratio ≥ 1.91 → umbral 1.5; media del período de shock ≥ 1.58 → umbral 1.3; ≥78% de los días del shock >1.2 → umbral 0.75; media de calma ∈ [0.92, 1.06] → acotada a (0.8, 1.2) |

## 2. Diagnóstico de IC (criterio 2 — líneas 966-969)

`scripts/diagnose_hurst_vol_ic.py` (nuevo), misma disciplina que §36: rank IC
intra-día (Spearman por fecha sobre el corte transversal de 50 símbolos), SE
Newey-West (L=min(12, n_dias//8)), ventanas W1/W2/W3, referencia Bonferroni de la
familia signal_diagnosis (n=19, dos colas → |t| > 3.008). Output:
`backend/data/cache/diagnose_hurst_vol_ic_20260821_210750.txt`.

Panel: 133.450 filas, 2.649 fechas, 50 símbolos, 2016-01-04 → 2026-08-14.

### A) `hurst_exponent` vs `fwd_return_20d` (edge direccional)

| Ventana | n_dias | mean_IC | SE_NW | t |
|---|---|---|---|---|
| W1 (2020-21) | 505 | +0.0282 | 0.0278 | +1.01 |
| W2 (2022-23) | 501 | +0.0001 | 0.0241 | +0.00 |
| W3 (2024-26) | 637 | −0.0492 | 0.0182 | −2.70 |
| TOTAL | 2649 | −0.0127 | 0.0102 | −1.24 |

### B) `realized_vol_regime` vs `fwd_return_20d` (edge direccional)

| Ventana | n_dias | mean_IC | SE_NW | t |
|---|---|---|---|---|
| W1 (2020-21) | 505 | −0.0311 | 0.0260 | −1.20 |
| W2 (2022-23) | 501 | +0.0052 | 0.0262 | +0.20 |
| W3 (2024-26) | 637 | +0.0104 | 0.0200 | +0.52 |
| TOTAL | 2649 | +0.0046 | 0.0101 | +0.45 |

### C) `realized_vol_regime` vs volatilidad realizada futura a 20d (validación de clustering)

| Ventana | n_dias | mean_IC | SE_NW | t |
|---|---|---|---|---|
| W1 (2020-21) | 505 | +0.0952 | 0.0293 | **+3.25** (SIG+) |
| W2 (2022-23) | 501 | +0.0082 | 0.0291 | +0.28 |
| W3 (2024-26) | 637 | +0.0018 | 0.0182 | +0.10 |
| TOTAL | 2649 | +0.0328 | 0.0116 | +2.84 |

## 3. Veredicto

**Las features NO se promueven a `signal_engine._factor_scores`** (mantienen su rol
diagnóstico). Evidencia:

1. **Sin edge direccional robusto**: A y B son nulos en TODAS las ventanas bajo el
   umbral de la familia (máx |t| = 2.70, hurst W3, negativo). El signo de hurst además
   es inestable entre ventanas (W1 +, W3 −): no es señal, es ruido de muestra.
   Coherente con el principio del plan ("two HMM systems": el régimen es conditioning,
   no gate direccional — el IC nulo sobre retornos no refuta ese rol).
2. **Clustering de vol parcial**: C valida el proxy en W1 (t=+3.25) pero W2/W3 son
   nulos. La señal no es robusta entre ventanas. Lectura técnica: `realized_vol_regime`
   es un ratio (vol 20d/vol 100d = indicador de CAMBIO de vol) y predice el NIVEL de vol
   futura de forma débil; el clustering fuerte vive en el nivel, no en el ratio. Se
   registra como limitación del proxy, no como bug.
3. **Costo**: `hurst_exponent` es O(n·lags) vectorizado — seguro para diagnóstico por
   símbolo en `calculate_all_indicators`.

## 4. Archivos tocados

- `backend/app/core/indicators.py` — sin cambios (fix vectorizado previo se conserva).
- `backend/tests/test_indicators.py` — 2 tests recalibrados con evidencia (secciones 1 y 3).
- `backend/scripts/diagnose_hurst_vol_ic.py` — nuevo, diagnóstico de IC.
- `backend/data/cache/diagnose_hurst_vol_ic_20260821_210750.txt` — output crudo.

## 5. Pendientes / notas

- Si en el futuro se sospecha que un GARCH(1,1) real tiene poder que el proxy no
  muestra (decisión explícita del plan, línea 957-961), el punto de entrada es la
  validación C: el proxy predice vol futura sólo en W1. Medir un GARCH contra el mismo
  target (real_vol_20, W1/W2/W3) antes de agregar la dependencia `arch`.
- El diagnóstico NO consume slot de ledger (exploratorio, según plan). Cualquier
  promoción futura requiere trial pre-registrado.