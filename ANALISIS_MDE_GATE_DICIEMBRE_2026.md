# MDE DEL GATE DE DICIEMBRE 2026 — ¿es alcanzable el criterio DSR>=0.90 con ~60 días de paper?

**Fecha**: 2026-09-04 · **Autor**: Cline · **Ticket**: B5 (PLAN_REMEDIO_BRECHAS_20260903 §B5)
**Código**: `backend/scripts/mde_power.py` (`gate_diciembre_2026()`) · **Test**: `backend/tests/test_mde_power.py`

---

## 1. La pregunta

El gate de diciembre (C1) contempla evaluar el desempeño del paper trading real
(~60 días) contra el criterio estándar de los trials del proyecto: **DSR >= 0.90
en >= 2/3 ventanas**. Pregunta concreta: ¿esa barra es alcanzable con esa
cantidad de datos, o es matemáticamente casi imposible dado el ruido de una
DSR estimada con N tan chico?

## 2. Veredicto ejecutivo

**INEJECUTABLE — matemáticamente casi imposible.** Con T=60 días de paper y la
familia con N=17 trials:

- Para alcanzar DSR=0.90 se necesita un **Sharpe diario ~0.53 → anualizado
  ~8.4** (con autocorrelación ρ₁=0.25; sin ella, ~6.7). Para referencia: el
  mejor fondo del mundo opera con Sharpe anual 2-4.
- Un edge **plausible** (SR diario 0.10 ≈ Sharpe anual 1.59, ya optimista)
  produce en 60 días una **DSR ≈ 0.11** — indistinguible del ruido, no porque
  el edge no exista sino porque T es muy chico para verlo.
- Incluso bajando la familia a **N=2** (el mínimo del estimador), el SR diario
  requerido es 0.29 → anual 4.7. Sigue imposible.
- Para que un SR diario de 0.10 alcance DSR=0.90 harían falta **~973 días**
  (~4 años) de paper con retornos iid, o **~1460 días** (~6 años) con ρ₁=0.25.

La consecuencia operativa: si en diciembre se aplica ese criterio tal cual
está escrito, el resultado es un NO_CUMPLE **pre-ordenado por la matemática,
sin importar si el edge existe**. El criterio debe re-especificarse ANTES de
diciembre (§6).

## 3. La matemática (mismo estimador que el motor, auditado 2026-08-10)

La DSR que calcula `backtest_engine.calculate_metrics`:

```
sr_std   = sqrt(var_num / (T_eff - 1))
var_num  = 1 - γ3·SR + (γ4-1)/4·SR²        (varianza de Lo 2002)
e_max(N) = (1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e)),  γ = 0.5772
DSR      = Φ((SR - e_max(N)·sr_std) / sr_std)
```

DSR >= 0.90 ⟺ SR/sr_std >= Φ⁻¹(0.90) + e_max(N) = 1.2816 + e_max(17) = 1.2816 + 1.8241 = 3.1057.

Con T=60: sr_std = sqrt(1/59) = 0.1302 → SR >= 0.4043 **diario**. Con
autocorrelación ρ₁=0.25: T_eff = 60/1.5 = 40 → sr_std = sqrt(1/39) = 0.1601 →
SR >= 0.5115 (el punto fijo converge a 0.5320 con var_num(SR)>1 por el término
cuadrático).

**Por qué T chico mata la DSR**: sr_std decrece con 1/√T. La DSR compara el SR
observado contra el "mejor de N Sharpe bajo ruido" (e_max), y el ruido del
estimador con 59 observaciones es tan grande que solo un Sharpe de clase
mundial × 3 lo supera. No es un problema de implementación: es la definición
de la DSR haciendo su trabajo (castigar la selección con N chico y muestra
corta).

## 4. Supuestos explícitos (los que pediste declarar)

| Supuesto | Valor asumido | Justificación | Si está mal |
|---|---|---|---|
| σ de retornos diarios del paper | 1.5%/día (var 0.000225) | nivel del equity del motor en el OOS 2024-2026 | NO afecta el SR requerido: sr_std escala con var_num, no con la varianza cruda (SR=μ/σ es adimensional). La varianza solo entra vía var_num(SR). |
| Autocorrelación retornos paper | ρ₁ = 0.25 → T_eff = T/1.5 | equity de momentum con horizonte de señal ~5-20 días: los retornos del equity heredan memoria del horizonte | ρ mayor → SR requerido SUBE (veredicto no empeora). ρ=0 → 6.7 anual, igual imposible. |
| N (familia) | 17 (signal_diagnosis al cierre del plan, 2026-09-03) | es el N que usa el criterio vigente "DSR>=0.90 2/3 ventanas (n_trials=17)" | N=29 (fallback del motor) → SR anual ~8.6. N=2 → 4.7. Ningún N razonable salva la barra. |
| Forma de la distribución | skew=0, kurt=3 (normal) | conservador: colas gruesas (kurt>3) SUBEN var_num → SUBEN el SR requerido | el veredicto con colas reales es IGUAL O PEOR. |
| SR diario "plausible" | 0.10 (anual 1.59) | techo del efecto plausible (plan §B5 usa 0.10 para el IC); un edge de investigación honesto está muy por debajo | con SR diario 0.05 (anual 0.79): DSR ≈ 0.05 en 60 días. Peor. |

## 5. Números (salida literal de `gate_diciembre_2026()`)

```
criterio                     = DSR>=0.90 en >=2/3 ventanas, T=60 dias paper
n_trials                     = 17
T_paper                      = 60      T_eff = 40.0 (rho1=0.25)
sr_requerido_diario_iid      = 0.4225  ->  anual 6.71
sr_requerido_diario_autocorr = 0.5320  ->  anual 8.45
sr_requerido_diario_n2       = 0.2946  ->  anual 4.68   (N=2, piso del estimador)
sr_plausible_diario          = 0.10    ->  DSR alcanzado = 0.114
T_necesario_dias_iid         = 973     (~4 años)
T_necesario_dias_autocorr    = 1460    (~6 años)
veredicto                    = INEJECUTABLE — barra matemáticamente casi imposible
```

Contexto adicional del MDE en su métrica natural (IC, `mde_ic()`):

| Diseño | MDE_IC | ¿Ejecutable (<=0.10)? |
|---|---|---|
| 50 símbolos, 250 fechas, horizonte 1d, familia 17 | 0.0249 | **SÍ** — detecta el rango realista 0.02-0.08 |
| 50 símbolos, 250 fechas, horizonte 20d, familia 17 | 0.1113 | NO |
| Paper 60 fechas, horizonte 5d, familia 17 | 0.1136 | NO |

El gate de potencia ex-ante funciona: los diseños diarios de 250 fechas sí
tienen potencia; el paper de 60 días con horizonte semanal, no.

## 6. Qué hacer antes de diciembre (opciones, no me lo guardo)

1. **Re-especificar el criterio de diciembre** para lo que 60 días pueden
   decidir: la racha de días limpios (condiciones a+b+c de observabilidad),
   el fill rate / slippage medido (A5), y la coherencia paper-vs-señal. Es
   decir: diciembre decide si el TUBO corre y acumula datos, no si el edge
   existe.
2. **Mantener DSR>=0.90 solo donde tiene potencia**: sobre las ventanas OOS
   históricas PRE-corte (W1/W2/W3, ~500 días hábiles c/u — ahí el criterio
   vigente sí es alcanzable y es el que se usó siempre), con el paper como
   verificación prospectiva de coherencia, no como test de hipótesis.
3. **Si se quiere un test estadístico del paper**: usar el IC de las señales
   del paper (no la DSR) con su MDE — pero con 60 días y horizonte ~5d el
   MDE_IC ≈ 0.11: solo detectaría edges generosos. Honestamente: 60 días no
   alcanzan para tests de edge; alcanzan para verificar ejecución.
4. **No hacer**: estirar T a ~1000 días antes de decidir (son 4 años) ni
   "bajar la barra" de la DSR (la DSR baja = refutación-teatro invertida).

## 7. Reproducir

```bash
cd backend && .venv/bin/python -c "
from scripts.mde_power import gate_diciembre_2026, mde_ic
import json
print(json.dumps(gate_diciembre_2026(), indent=2, ensure_ascii=False))
print(mde_ic(n_symbols=50, T_dates=250, horizon_days=1, n_family=17))
"
```

Tests: `pytest tests/test_mde_power.py -q` (incluye
`test_gate_diciembre_es_matematicamente_casi_imposible`, que pinea estos
números: si alguien cambia el estimador, el test rompe y obliga a revisar este

## 8. Estado de implementación (2026-09-05)

El análisis se convirtió en mecanismo y vive en el ledger, no en este documento:

| Pieza | Dónde | Qué hace |
|---|---|---|
| `mde_ic()` / `sr_requerido_dsr()` / `gate_diciembre_2026()` | `backend/scripts/mde_power.py` | estimación de potencia; no importa nada de `app` (cero ciclo de importación) |
| Campo `diseno_mde` en la reserva | `backend/app/core/trial_registry.py` → `_mde_check()` | el pre-registro declara el diseño; si no se declara, no se juzga (regla por escritura, como B4) |
| Estado `INEJECUTABLE` | `trial_registry.py` | `MDE > efecto plausible` (`MDE_EFFECT_PLAUSIBLE = 0.10`) → se guarda con `n_trials_consumidos=0` y el dictamen en `mde`: no quema slot Bonferroni ni produce refutación |
| Rechazo post-hoc | `register_trial()` | un veredicto salido de un diseño sub-potente **no se registra**: no puede degradarse a INEJECUTABLE porque la entrada afirma veredicto + artefacto |
| Visibilidad | `scripts/audit_trial_budget.py` | columna `rechazados B5` por familia — el rechazo queda auditable, no desaparece |
| Dashboard | `/api/advisor/evidence` + `EvidenceFooter.tsx` | `status_ultimo`, `n_sin_correr`, `n_inejecutables`; el footer muestra el estado (RESERVADO / EXPIRADO / INEJECUTABLE) cuando no hay veredicto |

Lo que **no** hace el gate (límite honesto): no juzga diseños no declarados — es
instrumentación sobre la honestidad de lo declarado, no un fiscal. Y no decide el criterio
de diciembre: eso sigue siendo debate de redacción (§6), donde la posición recomendada es
la opción 1 (diciembre verifica el tubo, no la existencia del edge) y la DSR≥0.90 se
mantiene solo donde tiene potencia (ventanas OOS pre-corte).

análisis).