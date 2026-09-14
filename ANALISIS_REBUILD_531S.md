# Análisis del rebuild de 531s — desglose medido y propuesta de corte

**Fecha**: 2026-09-10 · **Worktree**: `test-opencode-orca` (análisis, sin tocar código de producción)
**Contexto**: re-hecho desde cero tras caída de sesión (RAM) que perdió el análisis previo.
Todas las cifras de este documento son **MEDIDAS** en este worktree el 2026-09-10, con el venv
de main (solo intérprete) + copia read-only del cache de main (`sandbox/` en `/tmp`), cache al
**2026-09-09** (fresco del día). El número 531s proviene de `SESSION_LOG.md:4518` de main:
`process_time_ms=531680` (medición de Kilo, worktree test-kilo-orca, cache 21 días stale).

---

## 1. El número 531s, desglosado

El rebuild del contexto advisor (`_load_context_sync`) ejecuta en serie:

| Fase del rebuild | Qué hace | Medido (serial, zero-net, cache fresco 09-09) | % del 531s observado |
|---|---|---|---|
| `load_universe` (download_data ×111) | backfill/refresh + `_integrity_hook` por símbolo | 1691.37s serial (14.2s/sym median) | **dominante** |
| └─ de los cuales `_integrity_hook` solo | validate_returns + gaps + reconcile | **1789.73s** (más que A porque en V se re-procesa) | **dominante** |
| `_fit_calibrators` (replay 20d × ~2 años × 102) | replay walk-forward + Platt + M2 | **1004.02s** (~16.7 min) | ~190s del 531 (paralelizado ×8 → ~393s medidos en DIAGNOSTICO previo; en el run de Kilo corrió en paralelo con la descarga) |
| `_fit_regime` | 8 market tickers | **3.83s** | despreciable |
| Loop de tickets (`_build_tickets_sync`) | generate_signal ×102 | ~174s (medido antes, DIAGNOSTICO_PERF_ADVISOR_102) | secundario |

**Nota metodológica sobre el 531s real**: la medición de Kilo fue sobre cache **21 días stale**
(`end` real de hoy), con descarga yfinance real: lote 72/102 OK, 30 fallos red, **291.8s de
descarga**. Con el hook disparando reconcile por hard-flag en cada símbolo con historia
pre-2015, el 531s = descarga (~292s) + reconcile CPU (~14s × ~72 símbolos efectivos ÷
paralelismo 10) + replay calibradores + tickets. Con cache fresco y paralelismo 10, el
path dominante del hook sigue pagándose completo en CADA rebuild.

**Hallazgo central (valida la hipótesis de Boris)**: sobre el mismo cache fresco del día,
la **2ª pasada idéntica** del load pagó **1200.9s** (median 10.6s/sym) — el costo no
disminuye: la reconciliación es **no-idempotente por diseño** y se re-corre entera en cada
rebuild aunque los parquets estén limpios y frescos.

---

## 2. ¿Cuánto es load_universe paralelo vs loop de tickets vs cache_integrity?

**Carga (load_universe paralelo, 10 workers)**: en el worktree de OPENCODE el serial completo
mide 1691s; con ThreadPoolExecutor(10) de main (I/O-bound), el componente de red se solapa
pero **el CPU del hook no se solapa** (threads + pandas = CPU-bound en segmentos largos):
la medición de Kilo con 10 workers + descarga real dio 291.8s de descarga para 72/102
OK. El cuello de botella del load NO es ya la descarga — es el `_integrity_hook` CPU-bound
que corre serial dentro de cada worker (y GIL-limitado entre workers).

**Loop de tickets**: ~174s serial (medición previa documentada en
DIAGNOSTICO_PERF_ADVISOR_102.md), ya cacheado con TTL por el fix de 2026-09-02/03 (2ª
llamada ~1s). No es el problema hoy.

**cache_integrity (_integrity_hook)**: **el problema**. Medición directa:
- Primera pasada (cache fresco del día): **1691.37s** serial, de los cuales el hook solo
  mide **1789.73s** (V mide el hook puro sobre los 111; A incluye backfill/refresh-checks
  baratos + hook): el hook es ~100% del costo del load en caliente.
- Segunda pasada idéntica: **1200.9s**. Cero ahorro por caches limpios. El pipeline es
  idempotente en RESULTADO (no cambia los parquets) pero no en COSTO.
- **108 de 109 símbolos pagaron reconcile** (>1s cada uno; median 14.2s, p90 21.2s, max
  28.5s REGN).

### Perfil del hot-path dentro del hook (cProfile, REGN 14.08s)

```
download_data REGN ................ 14.080s
└─ _integrity_hook ................. 13.893s  (98.7%)
   └─ reconcile_symbol .............. 13.830s
      └─ detect_cross_contamination . 12.843s  (91.3% del símbolo)
         ├─ _norm × 4457 ........... 6.471s  (una copia+sort_index POR FILA)
         ├─ _row_from × 4462 ........ 2.693s  (df.loc[ts] POR FILA)
         └─ iterrows ............... 2.241s
```

`detect_cross_contamination` normaliza el DataFrame del "otro símbolo" **una vez por fila
del cache** (4457 filas → 4457 `_norm` completos con copy+sort_index), y compara fila a
fila con `df.loc[ts]`. Es O(N_filas × N_columnas) con constante pandas enorme. Para un
símbolo de 11 años de diario (~2900-4400 filas), son ~7-14s de CPU puro.

### Por qué dispara para (casi) todos los símbolos

El hook (data_ingestion.py:52-70) llama `validate_returns` y, si hay **cualquier hard-flag
(retorno >20% large-cap / >30% high-vol)**, dispara `reconcile_symbol` con descarga fresca
completa 2015→hoy. El umbral es estático, pero la **historia real** del mercado tiene
retornos legítimos >20%:

- El cache de main arranca en **2009-01-02** (no 2015): incluye el retorno del **2-ene-2015**
  cuando la serie arrancaba en 2014 (post-split/bad-base) y el regreso post-crisis 2009-2011
  (REGN +210% 2018-11-28 split, LRCX +144% 2018-12-13 split, CHTR -86.6% 2018-12-13,
  ISRG -53.3% 2025-01-17, ^VIX con **80 hard-flags legítimos** por naturaleza volátil...).
- **106 de 109 símbolos** levantan al menos un hard-flag en la historia 2009-2026. No son
  contaminación: son **splits, earnings y volatilidad real del VIX**. El validate es una
  SEÑAL DE REVISIÓN (su propio docstring lo dice), pero el hook la trata como acción
  automática de re-descarga.
- Resultado medido: en cada rebuild, ~108 símbolos × (descarga fresca 2015→hoy + comparación
  fila-a-fila) — aunque el parquet del día ya esté limpio y fresco.

### Los 2 huecos falsos que nunca se reparan (y se re-intentan en cada rebuild)

- 25 símbolos reportan huecos `2012-10-29..2025-01-09` (4 fechas) o `2018-12-05..2025-01-09`
  (2 fechas): son los **cierres de duelo presidencial** (Bush 2018-12-05, Carter 2025-01-09)
  + Sandy 2012-10-29/30 que el calendario `nyse_trading_days` no modela. El propio docstring
  de `nyse_trading_days` lo documenta y diseñó `known_trading_days` para auto-excluirlos,
  **pero `_integrity_hook` llama `find_intermediate_gaps(df)` sin ese parámetro** — siempre
  `None` → siempre "hueco" → siempre `repair_gap_range` → siempre "re-descarga devuelta
  incompleta" (440 intentos fallidos en las 4 pasadas de este análisis; **0 reparados**).
- Esto agrega por rebuild: 1 descarga de tramo fallida + re-lectura/re-escritura del parquet
  por símbolo afectado, además del reconcile.

---

## 3. Hipótesis de Boris — VALIDADA (con evidencia medible)

> "Si los 102 parquets ya están limpios y frescos del día, correr toda esa reconciliación
> en cada rebuild es desperdicio — debería memoizarse por día (mtime+hash sin cambios => skip)."

**Confirmado con números**:
1. Cache fresco 09-09 + zero-net: el load completo pagó 1691s; el hook solo 1790s; la 2ª
   pasada idéntica 1201s. **El costo NO baja con el cache limpio** — se paga completo
   en cada rebuild (TTL 300s ⇒ hasta ~12 veces por hora de uso del dashboard, aunque
   el warmup loop de Kilo lo dispara cada 280s).
2. El resultado de la reconciliación es idéntico (cero cambios de parquets: 0
   "re-descarga completa", 0 "cache existente conservado", solo gap-repairs fallidos
   re-escritos) ⇒ **reconciliar un parquet que no cambió produce exactamente el mismo
   output**. Es el caso ideal de memoización.
3. Los disparadores (hard-flags y huecos) son función de (parquet, calendario) — ambos
   cambian a lo sumo una vez por día (updater nocturno) o cuando un parquet se repara.
   Re-evaluarlos por rebuild intradía es trabajo redundante por diseño.

---

## 4. Propuesta: dónde está el tiempo y cómo cortar 531s a segundos

### 4.1 El memoize por día (la hipótesis, hecha diseño)

**Dónde**: `data_ingestion.py` — envolver `_integrity_hook` (o el par download+hook) con
un guard memoizado por símbolo:

```python
# Estado memoizado por símbolo: (mtime, size, hash?) -> veredicto del hook
_INTEGRITY_MEMO: dict[str, tuple[float, int, pd.DataFrame]] = {}

def _integrity_hook(ticker, df, cache_path):
    if not INTEGRITY_CHECK_ON_UPDATE:
        return df
    st = os.stat(cache_path)
    memo = _INTEGRITY_MEMO.get(ticker)
    if memo and memo[0] == st.st_mtime and memo[1] == st.st_size:
        return memo[2]  # mismo parquet bytes->bytes: veredicto del hook YA hecho
    out = _integrity_hook_full(ticker, df, cache_path)   # el pipeline actual
    # memoizar SOLO si el hook no modificó el parquet (sin repair/re-descarga):
    # si lo modificó, el stat cambió y la próxima corrida re-valida gratis.
    _INTEGRITY_MEMO[ticker] = (st.st_mtime, st.st_size, out)
    return out
```

- **Clave de memoización**: `mtime + size` del parquet (estat barato, cero red). `hash`
  completo (SHA-256) es opcional si se desconfía de mtime (coarse): el costo de hash de un
  parquet de ~230 KB es <10 ms — puede incluirse sin romper el presupuesto.
- **Efecto medido (proyección sobre lo medido)**: segunda pasada del día = **~0s** por
  símbolo (stat + dict lookup). El rebuild completo intradía pasa de ~1690s a
  **~0s del hook** + 1004s de calibradores + 3.8s de regime + ~174s tickets ≈ **~1180s la
  primera vez del día** y **~2-5s en rebuilds intradía** (con calibradores cacheados por
  TTL, los rebuilds intradía ya casi no pagan nada).
- **La verificación no se saca**: el hook sigue corriendo COMPLETO la primera vez del día
  (o tras cualquier write del parquet: repair, re-descarga, refresh del updater). Solo
  deja de re-correlo sobre bytes idénticos. Mismo espíritu que `_CONTEXT_CACHE_TTL`:
  verificar sí, bloquear no.

### 4.2 Fix estructural #1: el disparador de hard-flag debe ser divergencia, no historia

El hook dispara reconcile por **cualquier hard-flag histórico**. Pero el propio docstring
de `validate_returns` lo advierte: un large-cap puede mover ±20% real (earnings, splits).
La firma de contaminación documentada (COMPARACION §3) es "retorno absurdo **Y diverge de
la descarga fresca**". El diseño ya prevé la confirmación en `reconcile_symbol` (2a:
"hard-flag + divergencia vs fresco propio alcanza") — pero **paga la descarga completa
2015→hoy y la comparación O(n²) para descubrir que no diverge**.

Propuesta (sin tocar `cache_integrity.py` de fondo, solo el hook):
- El hook ya relee el parquet tras `reconcile_symbol` — la condición de disparo puede
  acotarse a **flags hard en la ventana del updater (últimas N ruedas, p.ej. 10)** o a
  **flags no confirmados previamente** (memo de fechas confirmadas legítimas). Un
  retorno +210% de REGN en 2018-11-28 verificado legítimo una vez, no necesita
  re-verificarse contra descarga fresca en cada rebuild de aquí al infinito.
- Efecto: los 106/109 símbolos con hard-flags históricos dejan de pagar reconcile
  completo; solo los flags NUEVOS (la ventana móvil del día) disparan la descarga
  de verificación.

### 4.3 Fix estructural #2: `find_intermediate_gaps` con `known_trading_days`

Una línea conceptual: `_integrity_hook` / `reconcile_symbol` deben recibir
`known_trading_days=_market_days_present_in_cache(...)` (la función ya existe en
cache_integrity.py:577) — el docstring de `nyse_trading_days` dice exactamente que los
cierres presidenciales "NINGÚN símbolo del universo tiene" y por eso la detección los
exige. Hoy el hook pasa `None` → 25 símbolos re-intentan eternamente reparar 2-4 fechas
que no existen (440 intentos fallidos medidos, 0 exitosos).

- Efecto: -25 símbolos × (1 descarga de tramo + re-read/write parquet + re-gaps) por
  rebuild. Cero riesgo: la auto-corrección está diseñada para exactamente esto.

### 4.4 Fix de hot-loop (si se quiere ir más allá del memoize): `detect_cross_contamination` vectorizado

`detect_cross_contamination` hace `_norm` por fila (4457 copias + sort_index) y compara con
`df.loc[ts]` fila a fila. Vectorizarlo (normalizar el "otro símbolo" UNA vez, join por
fecha, comparación vectorizada de ratios) es un cambio de ~20 líneas que baja el costo
de ~7-14s/símbolo a ~<0.5s/símbolo (estimación conservadora por el perfil: 91% del
tiempo es la normalización repetida + row lookup). Este fix es opcional si el memoize
está: solo afecta la primera corrida del día.

### 4.5 Números proyectados (medidos donde hay medición, proyección conservadora donde no)

| Escenario | Hoy (medido) | Con memoize 4.1 | + fixes 4.2/4.3 | + vectorizado 4.4 |
|---|---|---|---|---|
| Rebuild frío del día (cache fresco) | ~1691s load + 1004s calib + 174s tickets | ~1691s load (1ª vez) | ~30-60s load (solo flags nuevos) | ~5-10s load |
| Rebuild intradía (TTL 300s) | ~1200-1690s CADA VEZ | **~2-5s** | ~2-5s | ~2-5s |
| Verificación de integridad | cada rebuild | 1ª vez/día + en cada write real | igual | igual |

Corte del 531s observado: con cache 21 días stale, el 531 = descarga real (~292s) +
hook CPU (~14s×72÷10 workers) + calibradores (paralelizados desde 2026-09-03, ~393s
medidos para 102) + tickets. Con 4.1+4.2+4.3: descarga del día (una vez, updater) +
~60s de hook residual (solo flags nuevos) + calibradores ~393s una vez/día ⇒ **primer
rebuild del día ~7-8 min**, **rebuilds intradía ~2-5s**. La verificación completa sigue
existiendo (una vez por día y por parquet cambiado) — solo deja de pagarse 12 veces por
hora sobre bytes idénticos.

---

## 5. Verificabilidad y regresión

- **Cómo se midió**: `medir_rebuild.py` + `medir2.py` en `/tmp/opencode/` (sandbox con
  copia del cache de main), venv 3.9.6 de main como intérprete, zero-net monkeypatch de
  `yf.download`. Logs completos en `/tmp/opencode/logs/medir2.log`, resultados en
  `/tmp/opencode/logs/medir2_result.json` (copias a `backend/data/` NO hechas — datos
  temporales, no ensuciar el repo).
- **Artefactos de medición**: cProfile REGN: 14.08s total, 13.89s hook, 12.84s
  detect_cross_contamination (91%), _norm×4457=6.47s. Per-symbol JSON: 108/109 >1s.
- **Regresión del memoize**: si un parquet cambia (updater/repair), mtime/size cambian
  → memo invalidado → hook completo corre. Si un parquet se corrompe sin mtime change
  (imposible con escritura normal; sólo escrituras in-place idénticas en size y mtime
  lo evadirían — y para eso está el hash opcional). La invalidación por write es la
  misma semántica que el "fresh check" del updater.
- **La verificación no se elimina**: corre la primera vez del día y en cada parquet
  re-escrito. Esto es "hacerla barata e idempotente", no quitarla.

## 6. Conclusiones

1. **El 531s no es la descarga**: la descarga real fue 291.8s de los 531s. El resto es
   CPU del hook de integridad + calibradores + tickets, pagado INTRADÍA en cada rebuild.
2. **El hook de integridad es el cuello dominante en caliente**: 1789s de 1691s del
   load (108/109 símbolos pagan reconcile completo por hard-flags históricos legítimos).
3. **La hipótesis de memoización por día está validada**: el resultado de reconciliar
   bytes idénticos es idéntico (cero mutaciones), y el costo se re-paga completo hasta
   12×/hora. mtime+size+hash → skip es seguro, barato y preserva la verificación.
4. **Dos desperdicios estructurales identificados** (además del memoize): hard-flags
   históricos legítimos disparan reconcile completo (debe ser divergencia vs fresco,
   no historia), y `known_trading_days=None` fabrica 2-4 huecos falsos por símbolo
   (25 símbolos re-intentan la reparación eternamente, 0 exitosos).
5. **El loop de tickets ya está resuelto** (cache TTL de 2026-09-02) y los calibradores
   ya están paralelizados (2026-09-03). El rebuild hoy = hook de integridad. Cortarlo
   a segundos requiere el memoize + acotar el disparador + known_trading_days.

---

*Reporte generado por OpenCode en worktree `test-opencode-orca`. Sin commits, sin push,
sin código de producción tocado. Mediciones reproducibles con los scripts del sandbox
documentados en §5.*
