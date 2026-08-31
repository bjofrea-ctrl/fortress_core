# PRE-REGISTRO — Trial #21: asimetría direccional de factores (impulso de alza vs. de baja)

**Fecha de pre-registro:** 2026-08-30 · **Familia:** `signal_diagnosis` · **Slot:** 28
(consumo real verificado contra ledger hoy: 27 consumidos — corrección sobre el diseño
original que decía "slot 23" con conteo viejo; enmienda ANTES de congelar, permitida por §12)
**Aprobación de Boris:** 2026-08-30, en conversación con OpenCode ("realizar lo más sólido
y mejor para el proyecto no necesariamente lo más fácil", tras presentación del diseño
`DISENO_ASIMETRIA_DIRECCIONAL_20260830.md` de Cline). Enmiendas al diseño aprobadas en esta
congelación: (1) slot 23→28 (conteo ledger real); (2) umbrales recalculados con scipy y
congelados acá (2.4977→**2.50**, 2.7344→**2.74**, ambos redondeo conservador hacia arriba
como manda el diseño §Apéndice B); (3) n secciones: §48 de PLAN_MEJORA_MATEMATICA.md.
**Regla del repo:** NO se edita después de correr. Este documento congela TODO el diseño.

**En una línea:** el poder predictivo (rank IC vs. retorno 20d) de los factores del motor y
de los 8 residuales RMT ¿es distinto bajo impulso de alza que bajo impulso de baja — y la
diferencia (|Δ|≥0.05, t Bonferroni) basta para que condicionar por dirección rescate señal
que el pooling destruye?

**Lectura honesta (heredada del diseño §0):** intento de rescate con a priori baja. Toda la
evidencia pooled previa va en contra (§0.5a IC −0.01/+0.04/+0.07; ADX 0/3 §25; semanales
0/3 §26; MACD 0/3 §36; PBO 0.4688 #22). Lo que justifica este ÚLTIMO test específico:
ningún test previo condicionó por DIRECCIÓN del estado del símbolo; RMT documenta estructura
real (8 factores, 33.9% varianza total) que el momentum pooled no captura; la literatura de
microestructura documenta asimetrías de volumen reales. Un NO_CUMPLE cierra la línea
limpiamente (doctrina: probá, luego desechá). El PBO y la muerte del ranking pooled NO se
reabren.

---

## 1. Hipótesis (una línea, del diseño §1)

> El rank IC de los factores es **diferente** bajo impulso alcista que bajo bajista, y la
> diferencia es suficiente para que condicionar por dirección antes de promediar rescate
> señal destruida por pooling.

Sub-hipótesis mecánica (§1 del diseño): los gates binarios (RSI 45-70, ADX>25) degeneran en
un lado — tras impulso bajista el RSI casi nunca está en 45-70 → score colapsa a 0.4
constante → IC_down no interpretable. Verificable sin mercado; explica mecánicamente la
dilución del pooling.

## 2. Etiquetado direccional (§2 del diseño, sin look-ahead — textual)

```
ret_impulso(i,t) = P_close(i, t−1) / P_close(i, t−1−63) − 1     (D=63 hábiles)
dir(i,t) = UP    si ret_impulso ≥ +0.10
           DOWN  si ret_impulso ≤ −0.10
           NEUTRO si |ret_impulso| < 0.10   (excluido del test direccional)
```

- Etiqueta usa SOLO precios hasta t−1 inclusive; outcome es t→t+20d hábiles. **Cero
  solape** etiqueta/outcome. Factor medido con cierre de t−1 → decisión ejecutable t+1
  open (mismo lag del motor, §0.5a/§25/§26/§36).
- **Primaria ÚNICA (test formal): D=63, X=±10%, h=20d, universo 50 canónico.**
- Robustez descriptiva (SIN test formal, corre SOLO después del veredicto primario, solo
  puede DEGRADAR): X=±15%, h=5d, NEUTRO aparte. Nada reviviría un NO_CUMPLE.
- Panel: fechas diarias hábiles 2019-01-01→2026-08-04 con warmup desde 2016 (cache
  parquet verificado: 50/50 símbolos, 2010→2026-08-28, OHLCV completo).

## 3. Factores e hipótesis de signo pre-declaradas (§3 del diseño — ANTI P-HACKING)

**Regla: factor solo entra al confirmatorio si su signo esperado de Δ_f está declarado
ACÁ.** Los 8 RMT (sin signo) van a estrato exploratorio con umbral propio y veredicto
acotado (§6).

### 3.1 Estrato PRIMARIO confirmatorio (4 factores)

| Factor | Definición exacta | Δ_f esperado | Mecanismo |
|---|---|---|---|
| **volume_shock** | dollar_volume(t−1)/media_60d(t−2..t−61), con dollar_volume = close·volume | **> 0** | Volumen alto en impulsos alcistas confirma continuación (IC_up>0); en caídas anticipa capitulación/reversión (IC_down<0). Asimetría más documentada. |
| **rsi_14** | RSI Wilder 14d — el del motor (`indicators.py:25`) | **> 0** (degeneración) | En DOWN el score colapsa a 0.4 casi constante → IC_down no interpretable; en UP conserva discriminación. **Métrica obligatoria:** fracción de fechas-DOWN con score degenerado (std intra-fecha < 0.01 en el score binario 0.4/0.8); si >1/3 de fechas-DOWN en una ventana → Δ de RSI NO interpretable EN ESA VENTANA (regla pre-escrita §9.3 del diseño). |
| **momentum_12_1** | pct_change(252)·100 — el del motor (`indicators.py:381`) | **> 0**, circularidad declarada | Comparte 63d con la etiqueta → correlación mecánica parcial. **Métrica obligatoria:** Spearman(momentum_63d, ret_impulso) por ventana para cuantificarla. Interpretación válida = decisión del MOTOR, no inferencia pura. RSI/ADX/volume/RMT no comparten ventana (limpios). |
| **adx_14** | ADX 14d — el del motor (`indicators.py:48`) | **≈ 0** (SIMETRÍA) | ADX mide fuerza SIN signo por diseño. Si Δ≠0 significativo → hallazgo SORPRESA (etiquetado como tal, jamás confirmación a priori). |

### 3.2 Estrato EXPLORATORIO (8 factores RMT, sin signo)

Scores F0-F7 de `rmt_loadings_8factors.csv` (loadings del artefacto
`rmt_mp_20260811_150849.txt`, proyección documentada en
`ANALISIS_RMT_8FACTORES_20260830.md`). El script re-proyecta los residuos estandarizados
(mismo pipeline de `diagnose_rmt_mp.py`/`diagnose_sector_clusters.py:residual_matrix`)
sobre los loadings y alinea las fechas al panel diario (los CSV existentes son semanales
stride-5; para el panel diario se reproyecta — pipeline idéntico, sin re-estimar).

**LIMITACIÓN heredada y declarada:** loadings estimados in-sample 2019-2026 (T=1658).
Usarlos sobre el MISMO período es descriptivo, no OOS. **Veredicto acotado pre-declarado:**
aunque algún F pase su umbral, el resultado es **candidato a confirmación OOS fresca**
(loadings rolling) — NUNCA integración directa, nunca "asimetría confirmada".

### 3.3 Nivel 2 — macro/régimen (SIN test formal)

Δ_f por estado HMM (4 del `regime_classifier`, fit≤2024-12-31 decodificación causal —
patrón `trial_macd_bollinger.py:label_regimes`) y por tercil de VIX: tabla descriptiva
SOLO para factores que sobrevivan el nivel 1. 4×2×4=32 celdas → testear formal sería
multiple testing garantizado; queda como generador de hipótesis SIN presupuesto.

## 4. Estadística (§4 del diseño — textual)

Por fecha t y lado d (con suficientes símbolos en ese lado):

```
IC_d(t) = Spearman_rank( factor_f(i, t−1) , fwd_ret_20d(i, t) )   sobre dir(i,t)=d
d_f(t)  = IC_up(t) − IC_down(t)      SOLO fechas con AMBOS lados válidos
Δ_f     = mean(d_f);  SE = Newey-West(L=4, pesos Bartlett);  t_f = Δ_f / SE
```

- `newey_west_se` = copia fiel de §0.5a/§25/§26/§36 (`diagnose_sector_clusters.py:95`) →
  t por lado DIRECTAMENTE comparable con los pooled existentes (momentum −0.28, rsi +1.38,
  adx +2.31).
- **El test de asimetría es UNA estadística (Δ_f) por factor** — no dos ICs con deducción
  manual. Evita el error de comparar dos "no significativos" y concluir diferencia.
- Piso por fecha para IC de lado: ≥10 símbolos en ese lado (mediana de cobertura por fecha
  se reporta ANTES de calcular ICs — gate §5).
- ICs unilaterales (fechas con un solo lado): descriptivos, fuera del test.

## 5. Ventanas, cobertura y no-interpretabilidad (§5 del diseño — textual)

- **Ventanas:** W1 2020-01-01→2021-12-31, W2 2022-01-01→2023-12-31, W3
  2024-01-01→2026-08-04 + TOTAL descriptivo. Diagnóstico de panel: SIN backtest, SIN
  motor, SIN costos (familia signal_diagnosis).
- **Piso por ventana (pre-especificado):** ≥75 fechas con AMBOS lados válidos Y ≥10
  símbolos por lado por fecha (mediana). Debajo → ventana **NO INTERPRETABLE** (lección
  #17: cobertura fuera de rango invalida, no "cuenta como cero").
- **Riesgo W2 declarado:** 2022 es bear — lado UP puede quedarse corto. Regla
  pre-especificada: ventana no-interpretable por cobertura → trial **PARCIAL**; con ≥2
  interpretables el veredicto se evalúa sobre esas; con 1 sola → **GRIS automático**
  (decisión de Boris), jamás CUMPLE por una ventana sola.
- Sanity a priori del etiquetado (verificado 2026-08-30, NO es pre-medición de cobertura
  — solo comprobar que el panel carga): 2020-06 UP=21/DOWN=5; 2022-06 UP=10/DOWN=16;
  2024-06 UP=9/DOWN=9; 2026-06 UP=16/DOWN=8 (n=50 por fecha). El gate de cobertura corre
  ANTES de cualquier IC.

## 6. Presupuesto de multiple testing (§6 del diseño + Apéndice B, scipy congelado)

| Estrato | Hipótesis | α bilateral | \|t\| crítico (scipy, verificado 2026-08-30) |
|---|---|---|---|
| Confirmatorio (signo pre-declarado) | 4 | 0.05/8 = 0.00625 | **2.50** (2.4977 redondeado hacia arriba) |
| Exploratorio RMT (sin signo) | 8 | 0.05/16 = 0.003125 | **2.74** (2.7344 ≈ 2.73 de §26, consistencia interna) |

- El test Δ_f es el ÚNICO que consume hipótesis; ICs por lado son descriptivos.
- **Familia `signal_diagnosis`, slot 28** (27 consumidos verificados hoy vía
  `consumed_budget()`, último id `screening_palas`). Registro: `register_trial_reservation`
  con status RESERVED ANTES de correr (Track A), `complete_trial` con el veredicto
  mecánico después. Artefacto: `backend/data/cache/trial21_asimetria_direccional_<ts>.txt`
  (+ `.json` desechable por .gitignore — el .txt es la evidencia trackeada).

## 7. Criterios de veredicto (§7 del diseño — pre-especificados, binarios)

**umbral_aplicado (registro):** "Δ_f = IC_up − IC_down con |t_NW|>2.50 (confirmatorio) / >2.74 (RMT) en ≥2/3 ventanas interpretables, signo pre-declarado, |Δ_f|≥0.05, cobertura ≥75 fechas y ≥10 símbolos/lado"

**CUMPLE:** ≥1 factor confirmatorio con |t_f| > 2.50 en ≥2/3 ventanas interpretables,
signo igual al pre-declarado §3.1, |Δ_f| ≥ 0.05 en las ventanas significativas, coberturas
cumplidas.

**NO_CUMPLE (línea cerrada):** ningún confirmatorio lo logra. Conclusión: "condicionar por
dirección NO rescata señal — la debilidad pooled no es artefacto del pooling". El PBO y
la muerte del ranking pooled quedan intactos. Documentar en PLAN_MEJORA §48 + ledger +1.

**GRIS (parqueado, decisión de Boris):** (a) solo 1 ventana interpretable; (b) algún RMT
pasa 2.74 → candidato a confirmación OOS con loadings rolling; (c) sorpresa ADX
(simetría refutada) con |Δ|≥0.05 pero sin ≥2/3. Nada se integra por un GRIS.

## 8. Condicional post-veredicto (§8 del diseño — textual)

- **Si CUMPLE:** el uso sería un condicionante direccional sobre los scores existentes →
  ES un cambio de motor → requiere pre-registro y trial `motor_signal` DSR≥0.90 con
  presupuesto 13→14 (umbral vigente 0.992857). Este estudio solo autoriza MEDIR, nunca
  integrar.
- **Si NO_CUMPLE:** línea "asimetría direccional como rescate de momentum/RSI" cerrada
  como refutada. El siguiente frente es el que ya sugiere la evidencia (rama W2 §9:
  basket único o rotación sectorial con los 8 RMT como hipótesis generadoras) — no más
  condicionales sobre los factores actuales.
- **Si GRIS:** nada se integra; el doc de veredicto lista exactamente qué falta para
  desempatar.

## 9. Riesgos y neutralización (§9 del diseño — resumen)

1. **Asimetría como p-hacking disfrazado** (el mayor): neutralizado por signos
   pre-declarados (§3.1), estratos separados (§6), robustez solo degrada (§2), nivel 2
   sin test (§3.3), ≥2/3 ventanas + magnitud |Δ|≥0.05.
2. **Circularidad momentum-etiqueta:** advertida + Spearman(mom_63d, ret_impulso)
   obligatorio por ventana + interpretación acotada a decisión del motor.
3. **Degeneración RSI en DOWN:** fracción de fechas degeneradas reportada; >1/3 en una
   ventana → Δ de RSI no-interpretable EN ESA VENTANA (pre-escrito).
4. **Robustez/primario mismo panel:** robustez DESPUÉS del veredicto, solo degrada.
5. **Loadings RMT in-sample:** declarado (§3.2) — veredicto acotado a candidato.
6. **Supervivencia del universo 50:** limitación compartida de todos los §previos; se
   lista, no se corrige (comparabilidad > corrección).

## 10. Limitaciones (§11 del diseño — textual)

(1) Universo 50 ACTUAL → supervivencia leve, idéntico a todos los estudios previos.
(2) Loadings RMT in-sample. (3) Momentum con circularidad parcial. (4) Una sola
configuración primaria — si la asimetría vive en otra ventana/umbral, este diseño la
pierde (precio de no inflar presupuesto; alternativa rechazada: grid → PBO garantizado).
(5) Nada dice de ejecutabilidad (costos/capacidad) — un Δ_f grande sería PUERTA a un
trial de motor, no integración. (6) W2 puede quedar no-interpretable → PARCIAL.

## 11. Ejecución (§12 del diseño)

- Script: `backend/scripts/diagnose_asimetria_direccional.py` (patrón
  `trial_macd_bollinger.py` / `diagnose_sector_clusters.py`): carga panel diario → gate
  de cobertura PRIMERO (sin resultado antes del gate) → ICs por lado → Δ_f + t_NW →
  veredicto binario mecánico → artefacto .txt + .json → `complete_trial`.
- Reserva del slot ANTES de correr (`register_trial_reservation`, preregistro=este doc —
  el `umbral_aplicado` de §7 pasa la validación mecánica).
- **UNA corrida.** Sin re-corridas por resultados intermedios. Corre desde
  `~/Desktop/fortress_core` (cache con los 110 parquets verificado).
- Determinismo: seed 42, cache-only (sin descargas nuevas), HMM random_state=42.

## 12. Checklist de no-ejecución (estado al congelar)

- [x] Diseño aprobado por Boris 2026-08-30.
- [x] Enmiendas (slot 28, umbrales scipy, §48) hechas ANTES de congelar.
- [x] Ninguna corrida parcial ni exploratoria de este estudio existe.
- [x] PBO (#22), ranking pooled (muerto) y veredicto A6.3 (NO_CUMPLE sellado) NO se
      reabren. Este trial mide una hipótesis nueva y distinta.
- [ ] Ejecutar UNA vez → completar reserva con veredicto mecánico §7 → apéndice de
      resultados en §48 → ROADMAP.md.

---

*Congelado 2026-08-30. Post-corrida: SOLO apéndice de resultados. El criterio de §7 no
se toca.*
