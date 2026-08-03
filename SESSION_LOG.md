# Fortress Core — Memoria de Sesiones

> **Propósito**: Este archivo es la memoria persistente del proyecto. Cada sesión de trabajo debe actualizarlo con lo que se hizo, lo que sigue y decisiones tomadas. Así ninguna sesión se pierde.

---

## Sesión 1 — Estado inicial y resurrección del proyecto

**Fecha**: 2026-03-08  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Proyecto recuperado, git inicializado, backups configurados

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
7. ✅ **Primer backup ejecutado** — Backup completo al disco externo EMPRESA
8. ✅ **Script optimizado** — Exclusión de `.venv`, `venv`, `node_modules`, `.env`, DBs, cachés

### Estado actual del repositorio
- **GitHub**: https://github.com/bjofrea-ctrl/fortress_core (público, rama `main`)
- **Disco externo**: `/Volumes/EMPRESA/fortress_core_backups/` con `current/` y `snapshots/`
- **Local**: `/Users/boris/Desktop/fortress_core` con `main` sincronizado
- **Commits**: 2 (`ff5dacd` inicial + `f43b155` optimización backup)

### Pendiente para próximas sesiones
- [ ] **Instalar dependencias** — `cd backend && source .venv/bin/activate && pip install -r requirements.txt` (hay `.venv` ya creado con Python 3.9)
- [ ] Crear `.env` desde `.env.example`
- [ ] Ejecutar `python backend/scripts/test_system.py` para validar el motor cuantitativo
- [ ] Lanzar el sistema backend: `uvicorn app.main:app --reload` (o reinstalar Docker)
- [ ] Backtest de validación con datos reales (yfinance): `python backend/scripts/run_backtest.py`
- [ ] Levantar frontend: `cd frontend && npm run dev`

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

# Test integral del motor cuantitativo (requiere dependencias)
cd /Users/boris/Desktop/fortress_core/backend && python scripts/test_system.py

# Levantar todo con Docker
cd /Users/boris/Desktop/fortress_core && docker-compose up --build -d
```

---
*Fin de Sesión 1 — 2026-03-08*