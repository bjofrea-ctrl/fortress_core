# Fortress Core — Memoria de Sesiones

> **Propósito**: Este archivo es la memoria persistente del proyecto. Cada sesión de trabajo debe actualizarlo con lo que se hizo, lo que sigue y decisiones tomadas. Así ninguna sesión se pierde.

---

## Sesión 1 — Estado inicial y resurrección del proyecto

**Fecha**: 2026-03-08  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Proyecto recuperado, git inicializado, backups configurados, motor validado

### Contexto previo
- El proyecto `fortress_core` fue desarrollado en una sesión anterior (última modificación: 3 de agosto 2025)
- Se encontró en `/Users/boris/Desktop/fortress_core` **sin control de versiones** (solo `.gitignore` sin repo)
- El código estaba **100% escrito** pero nunca se ejecutó ni versionó

### Lo que se hizo en esta sesión
1. ✅ **Auditoría completa del proyecto** — Se verificó que todos los módulos están implementados:
   - Backend: motor cuantitativo completo (indicators, regime_classifier, signal_engine, adaptive_risk, risk_parity, backtest_engine)
   - API: endpoints `/health`, `/api/system/status`, `/api/risk/monitor`
   - Frontend: dashboard React con SystemStatus y RiskPanel
   - Scripts: init_db, run_backtest, test_system (prueba integral)
2. ✅ **Git inicializado** — `git init -b main` con usuario `bjofrea-ctrl`
3. ✅ **Git configurado** — `git config --global user.name "bjofrea-ctrl"`, email noreply de GitHub
4. ✅ **GitHub creado** — Repo público `bjofrea-ctrl/fortress_core` en https://github.com/bjofrea-ctrl/fortress_core
5. ✅ **Commit inicial** — `ff5dacd` con 44 archivos (4,930 líneas)
6. ✅ **Backup configurado** — Script `scripts/backup.sh` creado y funcional:
   - Backup al disco externo `/Volumes/EMPRESA/fortress_core_backups/`
   - Push automático a GitHub (repo `bjofrea-ctrl/fortress_core`)
   - Snapshot versionado con timestamp en `/Volumes/EMPRESA/fortress_core_backups/snapshots/`
   - Maneja 10 snapshots más recientes (autolimpieza)
   - Excluye `.venv`, `venv`, `node_modules`, `.env`, DBs, cachés
7. ✅ **Primer backup ejecutado** — Backup completo al disco externo EMPRESA
8. ✅ **TEST INTEGRAL PASÓ** — Motor cuantitativo validado con datos sintéticos

### TEST INTEGRAL — Resultados
Ejecutado con `.venv/bin/python` (Python 3.9.6) + `PYTHONPATH=.`:
```
✅ Indicadores técnicos OK
✅ Gestor de riesgo OK
✅ Clasificador de régimen OK
✅ Motor de señales OK
✅ Risk Parity OK
✅ Backtest OK
   Métricas: {'cagr': 0.0035, 'sharpe_ratio': 0.294, 'sortino_ratio': 0.304,
   'max_drawdown': -0.0214, 'calmar_ratio': 0.162, 'win_rate': 0.418,
   'profit_factor': 1.54, 'total_trades': 364, 'deflated_sharpe': 1.0}
✅✅✅ TODAS LAS PRUEBAS PASARON CORRECTAMENTE ✅✅✅
```

**Hallazgos clave**:
- Max drawdown: **-2.14%** → muy por debajo del ceiling absoluto de 12% ✅
- Profit factor: **1.54** → sistema rentable en datos sintéticos ✅
- 364 trades generados → el sistema opera activamente ✅
- Las dependencias en `.venv` (Python 3.9.6) **sí están instaladas** y funcionan

### Estado actual del repositorio
- **GitHub**: https://github.com/bjofrea-ctrl/fortress_core (público, rama `main`)
- **Disco externo**: `/Volumes/EMPRESA/fortress_core_backups/` con `current/` y `snapshots/`
- **Local**: `/Users/boris/Desktop/fortress_core` con `main` sincronizado
- **Commits**: 3 (`ff5dacd` inicial, `f43b155` optimización backup, `8d37d56` docs SESSION_LOG)

### Pendiente para próximas sesiones
- [ ] Crear `.env` desde `.env.example`
- [ ] Lanzar el sistema backend: `cd backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload`
- [ ] Inicializar BD: `cd backend && PYTHONPATH=. .venv/bin/python scripts/init_db.py`
- [ ] Backtest con datos reales (yfinance): `cd backend && PYTHONPATH=. .venv/bin/python scripts/run_backtest.py`
- [ ] Levantar frontend: `cd frontend && npm run dev`
- [ ] (Opcional) Instalar Docker para despliegue completo con docker-compose

### Decisiones de arquitectura (mantener en memoria)
- 🔒 **Sin IA en el loop crítico** — El sistema es 100% determinista (Fase 1)
- 📊 **Regímenes macro** — HMM de 4 estados: Goldilocks, Reflation, Stagflation, Deflation
- 🛡️ **Riesgo absoluto** — Ceiling de drawdown 12% jamás violable, stops por régimen
- 💰 **Capital inicial** — $25,000 USD, riesgo 1.5% por trade, posición máx 10%
- 🏗️ **Stack** — Python 3.11 + FastAPI + React 18 + TypeScript + PostgreSQL 15 + Redis 7

### Comandos útiles
```bash
# Backup manual a disco externo + GitHub
bash /Users/boris/Desktop/fortress_core/scripts/backup.sh

# Test integral del motor cuantitativo
cd /Users/boris/Desktop/fortress_core/backend && PYTHONPATH=. .venv/bin/python scripts/test_system.py

# Lanzar backend local
cd /Users/boris/Desktop/fortress_core/backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload

# Levantar todo con Docker
cd /Users/boris/Desktop/fortress_core && docker-compose up --build -d
```

---
*Fin de Sesión 1 — 2026-03-08*

---

## Sesión 2 — Sistema completo: BD, backend, backtest real y frontend

**Fecha**: 2026-03-08
**Autor**: Cline (asistente IA) + bjofrea-ctrl
**Estado**: Sistema completo funcionando — backend, BD, backtest con datos reales y frontend operativos

### Lo que se hizo en esta sesión
1. ✅ **Recuperación de contexto** — Leídos `CLINE_CONTEXT.md` y `SESSION_LOG.md`, verificado git (4 commits en main) y backup en disco externo
2. ✅ **Creado `.env` para desarrollo local** — SQLite en vez de PostgreSQL (sin Docker), Redis local, todos los parámetros de riesgo
3. ✅ **Inicializada la BD** — `init_db.py` ejecutado, 5 tablas creadas en SQLite (`fortress.db`): `price_data`, `regime_states`, `positions`, `portfolio_snapshots`, `risk_events`
4. ✅ **Backend verificado** — Ya estaba corriendo de una sesión anterior. Endpoints verificados:
   - `/health` → `{"status":"ok","ai_layer":"disabled","database":"ok","environment":"development"}`
   - `/api/system/status` → `{"risk_manager_active":true,"absolute_ceiling":0.12,...}`
   - `/api/risk/monitor` → `{"status":"no_data","absolute_ceiling":0.12}`
5. ✅ **Backtest con datos reales (yfinance) — PASÓ** — Métricas sólidas con datos reales 2019-2024
6. ✅ **Frontend levantado** — Vite v5.4.21 en `http://localhost:3000/`, dashboard React carga correctamente

### Fixes de compatibilidad con yfinance 1.x
Durante el backtest con datos reales, se encontraron y arreglaron 4 problemas:

1. **yfinance 0.2.36 no descargaba datos** — Actualizado a yfinance 1.2.0 (instaló `curl-cffi` para compatibilidad SSL con LibreSSL de macOS)
2. **MultiIndex columns en yfinance 1.x** — yfinance 1.x devuelve DataFrames con columnas MultiIndex `('Close', 'SPY')` en vez de `'Close'`. Arreglado en `data_ingestion.py` con helper `_flatten_columns()` que aplanar MultiIndex y tuple columns antes de guardar a parquet
3. **Cache incompleto para SPY/QQQ** — SPY y QQQ están en ambos lists (`tickers` con start=2019 y `market_tickers` con start=2015). La primera llamada cacheaba datos desde 2019, y la segunda leía del cache sin descargar data anterior. Arreglado en `data_ingestion.py` con lógica para descargar data anterior si el cache no cubre el rango completo. También se cambió el orden en `run_backtest.py` para descargar `market_data` primero (rango más amplio)
4. **`signal_engine.py` IndexError** — `calculate_all_indicators` hace `dropna()` que puede eliminar todas las filas si hay menos de 252 días de data. Agregado check de seguridad `if len(stock_data) == 0: return None` después de `calculate_all_indicators`

### Archivos modificados
- `backend/.env` — **Creado** — Configuración para desarrollo local (SQLite, sin Docker)
- `backend/app/core/data_ingestion.py` — **Modificado** — Helper `_flatten_columns()`, lógica de cache bidireccional (descargar data anterior y posterior), aplanar MultiIndex antes de guardar parquet
- `backend/app/core/regime_classifier.py` — **Modificado** — Aceptar tanto `"VIX"` como `"^VIX"` como clave en price_data
- `backend/app/core/signal_engine.py` — **Modificado** — Check de seguridad después de `calculate_all_indicators` para evitar IndexError
- `backend/scripts/run_backtest.py` — **Modificado** — Usar `^VIX` en vez de `VIX`, descargar `market_data` antes de `price_data`
- `backend/requirements.txt` — **Modificado** — yfinance 0.2.36 → 1.2.0, agregado `curl-cffi>=0.13.0`

### Métricas del backtest con datos reales (2019-2024)
```
=== MÉTRICAS ===
cagr: 0.0073
sharpe_ratio: 0.3657
sortino_ratio: 0.3360
max_drawdown: -0.0537
calmar_ratio: 0.1363
win_rate: 0.2873
profit_factor: 1.5160
total_trades: 550
deflated_sharpe: 1.0000

=== MONTE CARLO ===
mean: 1579.2196
p5: 78.8593
p95: 3033.9541
prob_loss: 0.0380
```

**Comparación backtest sintético vs real:**
| Métrica | Sintético | Real |
|---|---|---|
| Max DD | -2.14% | -5.37% |
| Sharpe | 0.294 | 0.366 |
| Profit Factor | 1.54 | 1.52 |
| Trades | 364 | 550 |
| Win Rate | 41.8% | 28.7% |

### Estado actual del sistema
- **Backend**: Corriendo en `http://localhost:8000` (uvicorn con --reload)
- **Frontend**: Corriendo en `http://localhost:3000` (Vite dev server)
- **BD**: SQLite en `backend/fortress.db` con 5 tablas creadas
- **Cache de datos**: Parquet files en `backend/data/cache/` con datos 2015-2024

### Pendiente para próximas sesiones
- [ ] (Opcional) Instalar Docker para despliegue completo con docker-compose
- [ ] Conectar frontend con backend (verificar que el dashboard muestra datos del API)
- [ ] Backtest con datos más recientes (2025-2026)
- [ ] Optimizar parámetros del modelo basado en métricas reales
- [ ] Implementar paper trading en vivo

### Decisiones tomadas
- 🔒 **yfinance 1.2.0** — Actualizado desde 0.2.36 por incompatibilidad con API de Yahoo Finance
- 🔒 **SQLite para desarrollo local** — Usado en vez de PostgreSQL para no requerir Docker
- 🔒 **`^VIX` en vez de `VIX`** — VIX es un índice, yfinance requiere el prefijo `^`
- 🔒 **Orden de descarga** — `market_data` se descarga antes que `price_data` para que el cache cubra el rango completo

---
*Fin de Sesión 2 — 2026-03-08*
