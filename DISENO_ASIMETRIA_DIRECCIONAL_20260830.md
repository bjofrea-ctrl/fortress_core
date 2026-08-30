# Diseño — Estudio de asimetría direccional (factores bajo impulso de alza vs. de baja)

**Fecha:** 2026-08-30 · **Autor:** Cline (worktree `fundamentales-automatizado`)
**Estado:** DISEÑO — NO es pre-registro, NO se ejecuta, NO integra nada. Este documento
especifica el estudio para que Boris decida si se convierte en pre-registro
(`PRE_REGISTRO_*.md`) y trial de la familia `signal_diagnosis` (slot 23).
**Mandato:** "que factores condicionan el impulso de ALZA de precio vs los que
condicionan el impulso de BAJA, en vez de tratar el movimiento como una sola cosa."

---

## 0. Motivación y estado del arte — lo que ya se sabe (verificado hoy)

La queja que motiva esto tiene evidencia acumulada: los factores del motor se aplican
**en bloque** (`signal_engine.py:123-167` — `momentum_score` = normalize(mom_12_1,
−50, 100); `rsi_score` = 0.8 si 45<RSI<70 si no 0.4; `adx_score` = 0.9 si ADX>25 si no
0.3 — ningún score distingue si el símbolo está en impulso alcista o bajista), y el
resultado pooled es débil o nulo:

| Evidencia previa | Resultado | Fuente |
|---|---|---|
| momentum_score intra-día (§0.5a) | IC −0.0100, t −0.28 (187 días) — no sig | `rr2_intraday_20260811_150741.txt` |
| rsi_score intra-día (§0.5a) | IC +0.0404, t +1.38 — no sig | idem |
| adx_score intra-día (§0.5a) | IC +0.0679, t +2.31 — nominal, muere en Bonferroni-4 | idem |
| ADX walk-forward (§25, trial #15) | 0/3 ventanas (t +0.79/+1.54/+1.47) | `trial_adx_walkforward_20260817_103916.txt` |
| Indicadores semanales mom/rsi/adx (§26, #16) | 0/3, máx \|t\|=0.44 | `weekly_indicators_20260817_105918.txt` |
| MACD dirección (§36, #19) | 0/3 (t +0.04/−0.68/+0.03) | `trial_macd_bollinger_20260820_174735.txt` |
| Interacción Bollinger (§36) | ΔIC máx 0.0074 ≪ 0.05 | idem |
| PBO/CSCV momentum+RSI (#22) | PBO 0.4688 → overfitting de proceso, NO_CUMPLE | `pbo_cscv_mom_rsi_20260822_093300.txt` |
| Ridge macro crudo (§0.5c) | IC OOS −0.0062, empeora vs blend | `ridge_comb_20260811_150859.txt` |
| RMT clusters × momentum (OpenCode 30/08) | IC +0.0339, t +1.03 pooled — no sig | `ANALISIS_RMT_8FACTORES_20260830.md` |

Lectura honesta: **la hipótesis de asimetría es un intento de rescate de una línea con
mucha evidencia en contra**. Su a priori debe ser baja. Lo que la justifica como último
test específico: (i) todos los tests previos fueron pooled o de interacción genérica
(Bollinger-ii), ninguno condicionó explícitamente por DIRECCIÓN del estado del símbolo;
(ii) RMT documenta estructura real (8 factores residuales, 33.9% varianza total) que el
momentum pooled no captura; (iii) la literatura de microestructura documenta asimetrías
reales (volumen en caídas anticipa reversión, no continuación — testable con los datos
que ya tenemos).

Este estudio NO reabre el veredicto del PBO (sigue NO_CUMPLE) ni declara vivo al
ranking pooled (sigue muerto). Mide UNA hipótesis específica y distinta.

---

## 1. Hipótesis central (una línea)

> El poder predictivo (rank IC vs. retorno futuro 20d) de los factores del motor y de
> los 8 factores residuales RMT es **diferente bajo impulso de alza que bajo impulso de
> baja** del símbolo — y la diferencia es lo suficientemente grande como para que
> condicionar por dirección antes de promediar rescate señal que el pooling destruye.

Sub-hipótesis mecánica (testable, del propio diseño del score): los gates binarios
(RSI 45-70, ADX>25) **degeneran en un lado** — tras un impulso bajista fuerte el RSI
rara vez está en 45-70 (casi todos quedan en 0.4) → la señal RSI colapsa a constante
en DOWN y su IC deja de ser interpretable. Esto es verificable sin mercado y explica
mecánicamente por qué el pooling diluye.

---

## 2. Definición operacional de "impulso" (etiquetado, sin look-ahead)

### 2.1 Estado direccional del símbolo

En cada fecha t, para cada símbolo i del universo 50:

```
ret_impulso(i,t) = P_close(i, t−1) / P_close(i, t−1−D) − 1        (D = 63 días hábiles ≈ 1 trimestre)

dir(i,t) = UP      si ret_impulso(i,t) ≥ +X          (X = 0.10, definición primaria)
           DOWN    si ret_impulso(i,t) ≤ −X
           NEUTRO  si |ret_impulso(i,t)| < X         (excluido del test direccional)
```

- **La etiqueta usa SOLO precios hasta t−1 inclusive.** El outcome es el retorno
  t → t+h (h=20 días hábiles). **Cero solape** entre ventana de etiqueta
  (t−1−D..t−1) y ventana de outcome (t..t+h): no hay look-ahead ni fuga entre
  partición y target.
- **Elección de D=63:** ventana de impulso "de estado" (persistente), no evento
  puntual. Un evento puntual (día de gran movimiento) daría 1 observación por evento —
  insuficiente para rank IC diario. El estado da panel (fecha × símbolo) denso.
- **Elección de X=±10% en 63d:** filtra la zona muerta sin vaciar el panel (§2.4).

### 2.2 Alineación temporal (idéntica al estándar del proyecto)

factor(i,t−1) medido con información de cierre de t−1 → decisión ejecutable en t+1 open
(mismo lag de ejecución que el motor; §0.5a/§25/§26/§36 usan esta convención).

### 2.3 Configuración primaria ÚNICA y robustez declarada

- **Primaria (única con test formal):** D=63, X=±10%, h=20d, universo 50.
- **Robustez descriptiva (declarada antes, SIN test formal, SIN consumo):**
  (a) X=±15%; (b) h=5d. Si la conclusión de la primaria no se sostiene cualitativamente
  en las robusteces, el hallazgo se reporta como frágil. Nada de esto puede revivir un
  NO_CUMPLE — solo puede degradar un CUMPLE.

### 2.4 Cobertura esperada (estimación a priori, no medida)

~15-25 símbolos por lado por fecha en mercados con dispersión normal (los parquets
cubren 2010→2026-08-28 con OHLCV completo — verificado). El script debe reportar la
cobertura REAL ANTES de calcular cualquier IC (gate de cobertura pre-resultado, §5) —
y este diseño deliberadamente NO pre-mide la cobertura para no ajustar umbrales con
los datos.

---

## 3. Factores candidatos e hipótesis direccionales pre-declaradas

**Regla anti p-hacking: un factor solo entra al test confirmatorio si su signo esperado
de Δ_f se declara AQUÍ, antes de correr, con su justificación.** Los factores sin
hipótesis direccional fuerte (los 8 RMT) entran a un estrato EXPLORATORIO separado con
umbral propio y veredicto acotado (§6-§7).

### 3.1 Estrato PRIMARIO (4 factores, hipótesis con signo)

| Factor | Definición | Δ_f esperado | Justificación |
|---|---|---|---|
| **volume_shock** | dollar_volume(t−1) / media_60d(t−2..t−61). Volume disponible en cache (verificado) | **Δ > 0** | Literatura de volumen: alto volumen en impulsos ALCISTAS confirma continuación (IC_up > 0); alto volumen en caídas anticipa capitulación/reversión (IC_down < 0). El factor con la asimetría más documentada de la lista. |
| **rsi_14** | RSI Wilder 14d (el del motor) | **Δ > 0** (mecanismo de degeneración) | Hipótesis MECÁNICA: en DOWN el score colapsa a 0.4 casi constante (varianza → 0) → IC_down no interpretable; en UP conserva discriminación. Se reporta la fracción de fechas-DOWN con score degenerado (varianza intra-fecha < umbral) como evidencia del mecanismo. |
| **momentum_12_1** | pct_change(252)·100 (el del motor, `indicators.py:381`) | **Δ > 0**, con advertencia de circularidad | Tras impulso alcista, continuación; tras bajista, rebote/value invierte. **ADVERTENCIA declarada:** comparte 63 días de historia con la etiqueta → correlación mecánica parcial factor-etiqueta. Se reporta Spearman(momentum_63d, ret_impulso) para cuantificarla. El test sigue siendo relevante como decisión del MOTOR (usa mom_12_1 tal cual), pero la inferencia estadística pura está contaminada — decirlo en el veredicto. RSI/ADX/volume/RMT no comparten ventana con la etiqueta y son los limpios. |
| **adx_14** | ADX 14d (el del motor) | **Δ ≈ 0** (hipótesis de SIMETRÍA) | ADX mide fuerza de tendencia SIN signo por diseño. Si Δ ≠ 0 significativo → hallazgo SORPRESA (más valioso, pero etiquetado como tal, no como confirmación a priori). |

### 3.2 Estrato EXPLORATORIO (8 factores RMT, sin signo pre-declarado)

Scores factoriales F0-F7 de `rmt_loadings_8factors.csv` (loadings del artefacto
`rmt_mp_20260811_150849.txt`, proyección documentada por OpenCode en
`ANALISIS_RMT_8FACTORES_20260830.md`).

- **LIMITACIÓN declarada (heredada):** los loadings se estimaron in-sample sobre
  2019-2026 (T=1658). Usarlos como variables explicativas del MISMO período es
  descriptivo, no predictivo out-of-sample — misma limitación que tuvo el análisis de
  OpenCode y del sector_clusters (§9c). El estudio los usa como hipótesis generadoras,
  no como señal validada.
- **Veredicto acotado de este estrato (pre-declarado):** aunque algún F pase su umbral,
  el resultado es **candidato para confirmación OOS fresca** (loadings rolling fuera de
  la ventana de estimación) — nunca integración directa, nunca "asimetría confirmada".

### 3.3 Nivel 2 — macro/régimen (heterogeneidad, SIN test formal)

Estado HMM (4 estados del `regime_classifier`) y VIX: se reporta el Δ_f POR régimen
como tabla descriptiva, SOLO para factores que sobrevivan el nivel 1. Razón: 4 factores
× 2 lados × 4 estados = 32 celdas → multiple testing garantizado si se testea formal.
El nivel 2 queda como generador de hipótesis para un eventual trial futuro con su
propio presupuesto. (Esto responde el "macro/regime" del mandato sin inflar el
presupuesto de este estudio.)

---

## 4. Estadística — IC por lado y test de asimetría

### 4.1 Métrica por celda (idéntica a §0.5a/rr2 — comparabilidad directa)

Para cada fecha t con suficientes símbolos en el lado d:

```
IC_d(t) = Spearman_rank( factor_f(i, t−1) , fwd_ret_20d(i, t) )  calculado SOLO sobre
          los símbolos con dir(i,t)=d
```

- IC_up(t) promediado sobre fechas UP-válidas; IC_down(t) ídem. SE por Newey-West
  L=4 (mismo estimador que §0.5a) → t por lado directamente comparable con los
  números pooled existentes (momentum −0.28, rsi +1.38, adx +2.31).

### 4.2 Métrica de ASIMETRÍA (el test primario del estudio)

```
d_f(t)  = IC_up(t) − IC_down(t)     solo fechas t con AMBOS lados válidos
Δ_f     = mean(d_f),  SE_NW(d_f, L=4),  t_f = Δ_f / SE
```

- El test de asimetría es UNA estadística por factor (Δ_f) — NO dos ICs independientes
  con deducción de significancia a mano. Esto evita el error clásico de comparar dos
  "no significativos" y concluir diferencia.
- Fechas con un solo lado válido se descartan del test (se reportan los IC
  unilaterales como descriptivo).
- Reporte obligatorio junto a cada t_f: n de fechas por lado, símbolos promedio por
  celda, fracción de scores degenerados (para RSI, §3.1), correlación de circularidad
  (para momentum, §3.1).

---

## 5. Ventanas, coberturas mínimas y regla de no-interpretabilidad

- **Ventanas:** W1 2020-2021, W2 2022-2023, W3 2024-01-01→2026-08-04 (las del
  proyecto) + período total como descriptivo. Es diagnóstico sobre panel de
  precios/indicadores — SIN backtest, SIN re-corridas del motor (familia
  signal_diagnosis, igual que §0.5a/§25/§26/§36).
- **Piso por ventana (pre-especificado):** ≥75 fechas con ambos lados válidos Y ≥10
  símbolos por lado por fecha (mediana). Debajo → ventana **NO INTERPRETABLE**
  (lección trial #17: cobertura fuera de rango invalida, no "cuenta como cero").
- **Riesgo W2 específico (declarado antes):** 2022 es bear — el lado UP puede quedarse
  sin cobertura. Regla pre-especificada: si una ventana es no-interpretable por
  cobertura, el trial queda **PARCIAL**; con 2+ ventanas interpretables el veredicto se
  evalúa sobre esas; con 1 sola interpretable → **GRIS automático** (decisión de
  Boris), jamás CUMPLE por una ventana sola.
- W3 sub-años 2024 (+704/49 trades) / 2025 (desierto, 11 trades) / 2026 (−239,
  sharpe −0.50) del check A63 advierten que la cobertura por sub-período varía mucho —
  el gate de cobertura corre ANTES de cualquier IC (sin excepciones).

---

## 6. Presupuesto de multiple testing y ledger

- **Familia:** `signal_diagnosis`. Ledger vigente: 22 consumidos (último: PBO #22,
  21→22). Este estudio sería el **slot 23**.
- **Estratificación de hipótesis (pre-especificada, 12 en total):**
  - **Confirmatorio (4 factores con signo):** Bonferroni-4 bilateral → α = 0.05/8 =
    0.00625 → **|t| > 2.50** por ventana.
  - **Exploratorio (8 RMT sin signo):** Bonferroni-8 bilateral → α = 0.05/16 = 0.003125
    → **|t| > 2.74** (mismo estándar que el Bonferroni-8 de §26 → 2.73, consistencia
    interna del repo).
  - El test de asimetría (Δ_f) es el único que consume hipótesis; los IC por lado son
    descriptivos (aunque se reporten sus t).
- **Criterio de ventana:** el estándar del proyecto es significancia en ≥2/3 ventanas
  (W1/W2/W3), no pooling total (lección §25: el t TOTAL era pooling de señal débil
  repartida, no robustez).
- **Umbral de magnitud además de significancia** (lección ADX: t+2.31 nominal sin
  magnitud no integra): **|Δ_f| ≥ 0.05** en las ventanas significativas — hereda el
  umbral de interacción de §36 (Bollinger-ii), consistencia interna.
- Registro: `register_trial(...)` familia `signal_diagnosis`, artefacto
  `backend/data/cache/trial23_asimetria_direccional_<ts>.txt` + `.json`. El pre-registro
  formal (§nuevo de PLAN_MEJORA_MATEMATICA.md) se escribe ANTES de correr y no se edita
  después (regla del repo).

---

## 7. Criterios de veredicto (pre-especificables, binarios)

**CUMPLE (línea de asimetría confirmada):** ≥1 factor del estrato confirmatorio con
|t_f| > 2.50 en ≥2/3 ventanas interpretables, signo igual al pre-declarado en §3.1,
|Δ_f| ≥ 0.05 en las ventanas significativas, coberturas mínimas cumplidas.

**NO_CUMPLE (asimetría refutada — línea cerrada):** ningún factor confirmatorio lo
logra. Los IC por lado pueden reportarse, pero la conclusión es: "condicionar por
dirección NO rescata señal — la debilidad pooled no es un artefacto del pooling".
Línea cerrada con evidencia (doctrina: probá, luego desechá). El PBO y la muerte del
ranking pooled quedan intactos.

**GRIS (parqueado):** (a) solo 1 ventana interpretable (cobertura, §5); (b) algún RMT
pasa su umbral exploratorio → candidato a confirmación OOS con loadings rolling;
(c) hallazgo sorpresa ADX (simetría refutada) con magnitud ≥0.05 pero sin ≥2/3.
Decisión de Boris en los tres casos; nada se integra por un GRIS.

---

## 8. Condicional post-veredicto (qué pasaría en cada caso)

- **Si CUMPLE:** el uso NO es un nuevo motor ni un re-weighting directo — es un
  **condicionante direccional** sobre los scores existentes (ej. peso o gate del factor
  según dir(i,t)). Eso ES un cambio de motor → requiere su propio pre-registro y trial
  `motor_signal` con DSR ≥ 0.90 en W1/W2/W3 (estándar del proyecto, presupuesto
  motor_signal 13→14, umbral vigente 0.992857). Este diseño solo autoriza la medición,
  nunca la integración.
- **Si NO_CUMPLE:** documentar en PLAN_MEJORA_MATEMATICA.md (§nuevo) + ledger +1.
  La línea "asimetría direccional como rescate del momentum/RSI" queda cerrada como
  refutada, junto con el resto del cuadro del §0. El siguiente frente sería el que ya
  sugiere la evidencia (rama W2 §9 del gate: basket único o rotación sectorial con los
  8 RMT como hipótesis generadoras) — no más condicionales sobre los factores actuales.
- **Si GRIS:** nada se integra; el doc del veredicto lista exactamente qué falta para
  desempatar (confirmación OOS fresca, loadings rolling, o ventana adicional si el
  calendario del mercado la da).

---

## 9. Riesgos específicos de este diseño y cómo se neutralizan

1. **La asimetría como p-hacking disfrazado** (el riesgo mayor): buscar subgrupos
   donde la señal "funciona" es la forma más común de fabricar un hallazgo.
   Neutralización: signos pre-declarados (§3.1), estratos separados confirmatorio/
   exploratorio (§6), robustez solo puede degradar (§2.3), nivel 2 descriptivo sin
   test (§3.3), y el criterio ≥2/3 ventanas con umbral de magnitud.
2. **Circularidad momentum-etiqueta:** momentum_63d y la etiqueta comparten ventana.
   Neutralización: advertencia declarada + métrica de correlación obligatoria (§3.1) +
   la interpretación válida es de decisión del motor, no de inferencia pura. Los
   factores limpios (RSI/ADX/volume/RMT) no comparten ventana con la etiqueta.
3. **Degeneración del gate RSI en DOWN:** el IC_down de RSI puede ser no-interpretable
   por varianza cero (todos 0.4) y contaminar d_f(t) con ruido. Neutralización: se
   reporta la fracción de fechas con score degenerado; si supera 1/3 de fechas-DOWN en
   una ventana, el Δ de RSI se marca no-interpretable EN ESA VENTANA (regla
   pre-especificada, no post-hoc).
4. **Doble uso del mismo panel para robustez y primario:** la robustez (X=15%, h=5)
   corre SOLO después del veredicto primario y solo puede degradarlo (§2.3).
5. **Loadings RMT in-sample:** ya declarado (§3.2) — veredicto acotado a candidato.
6. **Sesgo de supervivencia del universo actual (50):** limitación conocida y ya
   documentada del proyecto (todos los § previos la comparten). No se corrige acá; se
   lista en §11 para que el veredicto no la ignore.

---

## 10. Robustez descriptiva declarada (sin test formal, sin consumo)

| Variante | Qué chequea | Uso permitido |
|---|---|---|
| X=±15% (impulso más estricto) | sensibilidad al umbral de etiqueta | degradar, nunca revivir |
| h=5d (outcome corto) | persistencia del Δ en horizonte corto | ídem |
| NEUTRO analizado aparte | ¿la señal vive en la zona muerta? | descriptivo, genera hipótesis |

---

## 11. Limitaciones conocidas (honestidad del diseño)

1. Universo 50 ACTUAL → supervivencia leve; idéntico a todos los estudios previos
   (comparabilidad > corrección).
2. Loadings RMT in-sample (§3.2).
3. Momentum con circularidad parcial con la etiqueta (§3.1).
4. Una sola configuración primaria: si la asimetría real vive en otra ventana/umbral,
   este diseño la va a perder — es el precio de no inflar el presupuesto. (Alternativa
   rechazada: grid D×X×h → decenas de hipótesis → PBO garantizado, lección #22.)
5. Este estudio NO dice nada sobre ejecutabilidad (costos, capacidad): un Δ_f grande
   sería la puerta a un trial de motor, no la integración en sí (§8).
6. W2 puede quedar no-interpretable por cobertura UP (§5) → riesgo de veredicto PARCIAL.

---

## 12. Para pasar de diseño a ejecución (lo que decide Boris)

1. **Aprobar este diseño** (o enmendarlo — toda enmienda ANTES del pre-registro).
2. **Escribir el pre-registro formal** (`PRE_REGISTRO_ASIMETRIA_DIRECCIONAL.md`, §nuevo
   de PLAN_MEJORA_MATEMATICA.md) con TODO lo de acá congelado + fecha + slot 23
   reservado. No se edita post-resultado (regla del repo).
3. **Script** `backend/scripts/diagnose_asimetria_direccional.py` (patrón de
   `trial_macd_bollinger.py` / `pbo_cscv_mom_rsi.py`): gate de cobertura primero (§5),
   luego ICs, luego Δ, luego veredicto binario, artefacto txt+json, ledger.
4. **Correr UNA vez.** Sin re-corridas por resultados intermedios.

Costo estimado: 1 slot de signal_diagnosis, sin consumo de motor_signal, sin backtest
(panel + indicadores ya existentes; parquets OHLCV en el cache del repo principal —
el worktree fundamentales NO tiene los parquets, correr desde `~/Desktop/fortress_core`
o sincronizar cache).

---

## Apéndice A. Números citados, verificados contra fuente hoy (2026-08-30)

- `PLAN_MEJORA_MATEMATICA.md` §0.5a (tabla IC/SE/t por factor, cross-section real ~6
  símbolos/fecha), §0.5b (RMT: λ₊=1.385, 8 factores, F0 15.2% residual / 33.9% total),
  §0.5c (ridge macro crudo), §25/§26/§36 (0/3 con umbrales 2.77/2.73/3.008).
- `ROADMAP.md`: PBO #22 (0.4688, 21→22), ADX #15, semanales #16, MACD/Bollinger #19,
  W3 A63 y sub-años (49/11/29 trades, sharpe 0.54/0.36/−0.50).
- `INVESTIGACION_W3_A63_20260830.md` (OpenCode): warmup HMM, ventanas, composición W3.
- `ANALISIS_RMT_8FACTORES_20260830.md` (OpenCode): loadings F0-F7, cluster IC
  +0.0339 (t+1.03), limitación in-sample declarada.
- `backend/app/core/signal_engine.py:123-167` (scores en bloque, sin dirección),
  `backend/app/core/indicators.py:381` (momentum_12_1).
- Cache verificado: `AAPL.parquet` cols [Open/High/Low/Close/Volume], 4189 filas,
  2010-01-04 → 2026-08-28; 110 parquets en `~/Desktop/fortress_core/backend/data/cache/`.

## Apéndice B. Umbrales ya calculados (z bicaudal, df efectivo grande)

| Estrato | n hipótesis | α corregida | \|t\| crítico |
|---|---|---|---|
| Confirmatorio (con signo pre-declarado) | 4 | 0.05/8 = 0.00625 | 2.50 |
| Exploratorio RMT | 8 | 0.05/16 = 0.003125 | 2.74 (≈2.73 de §26) |
| Si se prefiriera pool único 12 | 12 | 0.05/24 = 0.002083 | 3.10 |

*(El script del pre-registro debe recalcularlos con scipy y congelarlos en el
pre-registro; este apéndice fija la escala esperada.)*

---

*Documento de diseño — sin ejecución, sin ledger, sin integración. Próximo paso
pertenece a Boris: aprobar → pre-registro → correr una vez.*





