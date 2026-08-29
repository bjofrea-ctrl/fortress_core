# Pre-registro — saneamiento metodológico del check de sanidad de A6.3

Borrador para aprobación de Boris. **No ejecutado.** No reabre ni reinterpreta el
veredicto ya sellado de `screening_palas` (NO_CUMPLE, ver
`PRE_REGISTRO_SCREENING_PALAS.md` §12). Esto es exclusivamente sobre el
*instrumento de medición* (el check de sanidad §4.2), no sobre la hipótesis PALA.

## 1. Qué se investigó y quién

`screening_palas` dio NO_INTERPRETABLE el 28/08: el check de sanidad (POOLED vs
`baseline_clean`) salió fuera de tolerancia en las 3 ventanas. Se investigó la
causa en dos rondas, cada una por un agente distinto al que escribió el código
que audita (regla fija desde hoy: ejecutor ≠ verificador):

- **Ronda 1** (Claude Code, coordinador): el costo de transacción difiere —
  `baseline_clean_20260811` corrió con los defaults viejos del motor
  (`commission=0.001 + slippage=0.0005` = 0.15%/lado); `screening_palas.py` usa
  el costo vigente §33 (`0.0005+0.0005` = 0.10%/lado). Verificado con números
  exactos, no explica todo: el Sharpe converge en W1/W2 pero el DSR sigue
  divergiendo en las 3 ventanas, y W3 diverge en ambas métricas.
- **Ronda 2** (OpenCode, verificador independiente, worktree separado): recalculó
  la aritmética completa contra ambos artefactos crudos (ver tabla abajo).
  Encontró que igualando `N_TRIALS` entre ambos scripts, W1 y W2 quedan dentro
  de tolerancia en Sharpe Y DSR — pero recomendó adoptar `N_TRIALS=17` como
  "doctrina del proyecto", lo cual **es impreciso** (ver §2).
- **Ronda 3** (Claude Code, verificando la Ronda 2): `N_TRIALS=17` no es un valor
  doctrinal — es un constante local de `backtest_baseline_clean.py`, heredada
  textualmente de `backtest_universe50.py` ("mismo N_TRIALS=17 para DSR
  comparable" — línea 14 del script). Pertenece a la familia de trials de
  `universe50` (validación de la estrategia principal), una lineage totalmente
  distinta a `signal_diagnosis` (la familia de A6.3, `n_trials=5`, elegido a
  propósito como "gate laxo, escalón 1" — un umbral de corrección multiple-testing
  deliberadamente más permisivo para un screening barato).

## 2. Por qué el DSR nunca iba a coincidir (no es bug)

El DSR depende de `N_TRIALS` como corrección por comparaciones múltiples: a más
trials asumidos, más se deflaciona el Sharpe observado. `baseline_clean` y
`screening_palas` usan `N_TRIALS` de **familias distintas por diseño** — no es
un parámetro que uno de los dos scripts tenga "mal puesto". Comparar sus DSR
directamente sin igualarlos iba a divergir sin importar si la implementación de
`screening_palas.py` era perfecta.

**Conclusión**: el check de §4.2 tiene un defecto de diseño, no `screening_palas.py`
un bug. El check compara un DSR calculado con una convención de corrección
(`N_TRIALS=17`, heredada de otra familia) contra otro calculado con una
convención distinta (`n_trials=5`, la propia de A6.3) — nunca fueron
comparables tal como estaba planteado.

## 3. Evidencia cruda (tabla de OpenCode, verificada por mí)

| Ventana | Contra viejo (0.15%, N17) | Contra nuevo desigual (0.10%, N5 vs N17) | Corregido (0.10%, ambos N17) |
|---|---|---|---|
| W1 | dSharpe 0.24 FUERA · dDSR 0.24 FUERA | dSharpe 0.06 OK · dDSR 0.16 FUERA | dSharpe 0.06 OK · dDSR 0.02 OK → **OK** |
| W2 | dSharpe 0.34 FUERA · dDSR 0.19 FUERA | dSharpe 0.06 OK · dDSR 0.13 FUERA | dSharpe 0.06 OK · dDSR 0.01 OK → **OK** |
| W3 | dSharpe 0.18 FUERA · dDSR 0.32 FUERA | dSharpe 0.40 FUERA · dDSR 0.40 FUERA | dSharpe 0.40 FUERA · dDSR 0.16 FUERA → **FUERA** |

Verificado independientemente por mí: `statistics.NormalDist().cdf()` (usado por
OpenCode al no tener `scipy` en su entorno) coincide con `scipy.stats.norm.cdf()`
a precisión de punto flotante (diff ≤ 1e-16) — la aritmética de la tabla es
confiable.

**W3 se investigó aparte**: la hipótesis de que 10 días extra de datos
(`screening_palas` carga hasta 2026-08-14, `baseline_clean` hasta 2026-08-04)
explicaran la divergencia se **descartó** — el delta de trades en esa ventana
dio 0 comparando ambos rangos. La causa de W3 queda **sin explicar**.

## 4. Propuesta (no ejecutada — decisión de Boris)

1. **Para el check de §4.2 específicamente** (no para el DSR "real" que cada
   script reporta en su propio contexto): igualar `N_TRIALS` en ambos lados de
   la comparación al correr el check — no adoptar 17 como default de ningún
   script, sino calcular el DSR de comparación con el mismo `N_TRIALS` en las
   dos series, documentando que es una igualación ad-hoc para esta verificación,
   no un cambio de metodología de ninguna de las dos familias.
2. Con esa igualación: el check pasaría en 2/3 ventanas (W1, W2) — cumple el
   umbral de §4.2 ("≥2/3 ventanas" para "implementación correcta").
3. **W3 queda marcado explícitamente como no resuelto** — no se cuenta como
   ventana "pasada", no se investiga su causa en este documento. Antes de usar
   W3 para cualquier decisión futura, requiere su propia investigación
   (ventanas independientes vs. serie continua, warmup del HMM en el borde de
   ventana).
4. **No se re-corre nada todavía.** Esto es una propuesta de corrección del
   *instrumento*. Ejecutarla implica editar el check de `screening_palas.py`
   (o un script de verificación aparte) y — si Boris decide que amerita una
   nueva corrida de A6.3 con el check corregido — sería un trial nuevo,
   reservado en el ledger antes de correr, no una reapertura del ya completado.

## 5. Checklist de no-ejecución

- [x] Ninguna corrida nueva se lanzó para producir este documento.
- [x] El veredicto NO_CUMPLE de `screening_palas` (ya en el ledger, `COMPLETED`)
      no se toca ni se reabre.
- [ ] **Aprobación explícita de Boris** antes de tocar el check o reservar un
      trial nuevo.

---

*Fin del borrador — pendiente de aprobación. Autor: Claude Code, con verificación
cruzada de OpenCode (investigación) y Kilo (sin intervención en este documento).*
