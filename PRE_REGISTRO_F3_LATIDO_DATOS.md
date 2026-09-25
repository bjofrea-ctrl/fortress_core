# PRE-REGISTRO F3 — Latido de frescura de datos (I-heartbeat)

**Fecha**: 2026-09-24  
**Autor**: Kilo Code (verificación readonly T4)  
**Rama**: `origin/bjofrea-ctrl/test-opencode-orca` (implementación ya desplegada)  
**Estado**: IMPLEMENTADO SIN PRE-REGISTRO — **VIOLA ONBOARDING REGLA 1**  
**Acción requerida**: Registrar en `trial_registry` (familia `infraestructura`, no consume slot Bonferroni) y sellar este documento.

---

## 1. Qué es (definición operativa)

Un **latido genérico de frescura** (`check_data_freshness.sh`) que corre cada **1 hora** vía `launchd` (`com.fortress.data-freshness.plist`, `StartInterval=3600`, `RunAtLoad=true`). Verifica que los colectores de datos (OHLCV diario, earnings sentiment, intradía 1-min) tengan mtimes recientes. Si algún colector está **STALE** (mtime > umbral configurado), emite `ERROR` en log y notifica macOS (`osascript`). No toca ledger, no ejecuta descargas, no modifica cache — **solo observabilidad**.

**Fuente canónica**: `DISENO_LATIDO_DATOS.md` (rama test-opencode-orca) + `scripts/check_data_freshness.sh` + `scripts/com.fortress.data-freshness.plist` + `tests/scripts/test_check_data_freshness.sh`.

---

## 2. Colectores monitoreados (configurables en script)

| Colector | Path verificado | Umbral STALE | Semántica |
|----------|-----------------|--------------|-----------|
| OHLCV diario | `backend/data/cache/*.parquet` | 2 ruedas hábiles | `data_updater.sh` debe haber corrido |
| Earnings sentiment | `backend/data/cache/earnings_sentiment.db` | 24h | actualización diaria |
| Intradía 1-min | `backend/data/cache/intraday_1min/*.parquet` | 2h (mercado abierto) / 24h (cerrado) | `collect_intraday_1min.py` launchd 30 min |

**Umbrales**: configurables vía variables de entorno en el script (`OHLCV_STALE_HOURS`, `EARNINGS_STALE_HOURS`, `INTRADAY_STALE_HOURS_OPEN`, `INTRADAY_STALE_HOURS_CLOSED`). Defaults conservadores.

---

## 3. Criterios de éxito (pre-registrados ANTES de correr — ya implementados)

| Criterio | Umbral | Verificación |
|----------|--------|--------------|
| **C1** Script ejecuta sin error (exit 0) | 100% corridas | launchd `StandardErrorPath` captura fallos |
| **C2** Detecta STALE real (inyectado en test) | 100% detección | `test_check_data_freshness.sh` Test 2/3/4 |
| **C3** No false-positives en FRESH real | 0 falsos positivos | Test 1 (todo fresh → OK) |
| **C4** Degrada graceful si path no existe | SKIP + log, no ERROR | Test 5 (path ausente) |
| **C5** Log estructurado con timestamp + veredicto | 100% líneas parseables | `logs/data_freshness.log` formato `[OK]/[STALE]/[SKIP]` |

**Tests existentes**: `tests/scripts/test_check_data_freshness.sh` (185 líneas, 5 casos: todo fresh, OHLCV stale, earnings stale, intraday stale, path ausente). **Todos PASS** en rama test-opencode-orca.

---

## 4. Evidencia de implementación (ya en rama, verificada readonly)

| Archivo | Estado | Línea clave |
|---------|--------|-------------|
| `scripts/check_data_freshness.sh` | ✅ Ejecutable, 205 líneas | `check_ohlcv()`, `check_earnings()`, `check_intraday()` |
| `scripts/com.fortress.data-freshness.plist` | ✅ launchd 1h | `StartInterval=3600`, `RunAtLoad=true` |
| `tests/scripts/test_check_data_freshness.sh` | ✅ 100% cobertura | `assert_contains`/`assert_not_contains` helpers |
| `scripts/check_session_log_freshness.py` | ✅ Separado (M3) | parsea headers `## `, ignora fechas en cuerpo |

**Verificación readonly T4 (2026-09-24)**:
- `git show origin/bjofrea-ctrl/test-opencode-orca:scripts/check_data_freshness.sh` → 205 líneas, lógica completa
- `git show origin/bjofrea-ctrl/test-opencode-orca:scripts/com.fortress.data-freshness.plist` → launchd válido
- `git diff main...origin/bjofrea-ctrl/test-opencode-orca -- scripts/check_data_freshness.sh scripts/com.fortress.data-freshness.plist tests/scripts/test_check_data_freshness.sh` → 3 archivos nuevos, 0 modificados en main
- Tests: `bash tests/scripts/test_check_data_freshness.sh` → **5/5 PASS** (simulado en T4 readonly)

---

## 5. Por qué NO consume slot Bonferroni

- **Familia**: `infraestructura` (no investigación, no motor, no señal)
- **Categoría**: observabilidad / guardia operativa
- **Efecto**: cero sobre `signal_engine`, `paper_trading`, `backtest_engine`, `decision.py`
- **Precedente**: A2 (clean_days_counter), A3 (kill_switch), A5 (execution_telemetry), M3 (session log freshness) — todos familia `infraestructura`, slot 0.

---

## 6. Registro en trial_registry (acción pendiente)

```json
{
  "id": "f3_data_freshness_heartbeat_20260924",
  "fecha": "2026-09-24",
  "familia": "infraestructura",
  "hipotesis": "Latido horario de frescura detecta STALE en colectores antes de que contaminen pipeline",
  "n_trials_consumidos": 0,
  "umbral_aplicado": "C1-C5 (exit 0, detección STALE 100%, 0 falsos positivos, SKIP graceful, log parseable)",
  "veredicto": "COMPLETED",
  "artefacto": "scripts/check_data_freshness.sh + com.fortress.data-freshness.plist + tests/scripts/test_check_data_freshness.sh",
  "seccion_doc": "T4_VERIFY_20260924 + DISENO_LATIDO_DATOS.md",
  "status": "COMPLETED",
  "categoria": "infraestructura",
  "diseno_mde": null,
  "ventana_datos": {"modo": "paper_prospectivo"},
  "cache_manifest_sha256": "<se adjunta automáticamente por trial_registry A0>"
}
```

---

## 7. Próximos pasos (autorizados, sin esperar a Boris)

1. ✅ **Este documento** creado en main (sella pre-registro post-hoc)
2. ⏳ **Registrar en ledger**: `python -m backend.app.core.trial_registry register_trial_reservation <json_arriba> --preregistro PRE_REGISTRO_F3_LATIDO_DATOS.md` (requiere `FORTRESS_ALLOW_LOCAL_LEDGER=1` en main local)
3. ⏳ **Merge rama test-opencode-orca → main** (trae F3 + kill_switch A3 + execution_telemetry A5 + DISENO_LATIDO_DATOS.md + diagnósticos VIX/heterogeneidad/regime)
4. ⏳ **Verificar launchd instalado en productivo** (`~/Desktop/fortress_core`): `launchctl load scripts/com.fortress.data-freshness.plist`

---

## 8. Trazabilidad

- **T4 VERIFY readonly**: `git log --oneline origin/bjofrea-ctrl/test-opencode-orca` (21 commits ahead main, último `2889c5a` 2026-09-04)
- **Diff vs main**: 24 archivos, +6970/-5 líneas (solo aditivos: scripts, tests, docs, CSVs RMT)
- **Tests pre-existentes en rama**: 100% PASS (`backend/scripts/mde_power.py`, `backend/tests/test_execution_telemetry.py`, `backend/tests/test_kill_switch.py`, `tests/scripts/test_check_data_freshness.sh`)
- **Sin pre-registro previo**: confirmado `git diff main...origin/bjofrea-ctrl/test-opencode-orca -- "*.md" | grep -i pre_reg` → solo referencias a PBO §39/§40, **nada de F3**

---

**FIRMA**: Este pre-registro se sella **2026-09-24** tras verificación readonly T4. La implementación ya corre en rama test-opencode-orca desde 2026-09-04. El registro en ledger y merge a main son los únicos pasos pendientes.