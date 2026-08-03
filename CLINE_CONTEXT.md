# 🧠 CLINE CONTEXT — Protocolo de Recuperación de Sesiones

> **LEER ESTE ARCHIVO PRIMERO SIEMPRE**
>
> Este archivo es el punto de entrada para cualquier sesión nueva de Cline.
> Si estás en una sesión nueva y el usuario menciona `fortress_core`,
> lee este archivo **antes de hacer cualquier cosa** para recuperar el contexto completo.

---

## 🔄 PROTOCOLO DE RECUPERACIÓN (para Cline)

Cuando el usuario abra una sesión nueva de Cline y quiera continuar con `fortress_core`:

### Paso 1: Leer este archivo
```bash
cat /Users/boris/Desktop/fortress_core/CLINE_CONTEXT.md
```

### Paso 2: Leer el SESSION_LOG (memoria de sesiones)
```bash
cat /Users/boris/Desktop/fortress_core/SESSION_LOG.md
```

### Paso 3: Verificar estado de git
```bash
cd /Users/boris/Desktop/fortress_core && git log --oneline && git status
```

### Paso 4: Verificar que el backup existe
```bash
ls /Volumes/EMPRESA/fortress_core_backups/
```

### Paso 5: Leer los archivos clave
- `README.md` — Arquitectura del sistema
- `backend/app/config.py` — Configuración
- `backend/app/core/` — Motor cuantitativo
- `.env.example` — Variables de entorno

---

## 📋 INFORMACIÓN DEL PROYECTO

### Identidad
- **Nombre**: Fortress Core
- **Descripción**: Sistema de trading cuantitativo con gestión de riesgo adaptativa (MVP determinista, sin IA en el loop crítico)
- **Ubicación**: `/Users/boris/Desktop/fortress_core`
- **GitHub**: https://github.com/bjofrea-ctrl/fortress_core (público)
- **Usuario GitHub**: `bjofrea-ctrl` (autenticado con `gh auth`)

### Stack
- **Backend**: Python 3.9.6 (venv en `backend/.venv`), FastAPI, SQLAlchemy, pandas, numpy, scipy, scikit-learn, hmmlearn, yfinance
- **Frontend**: React 18, TypeScript, Vite, TailwindCSS, Recharts (`frontend/node_modules` instalado)
- **Infra**: Docker (NO instalado en la máquina actual), PostgreSQL 15, Redis 7

### Reglas de riesgo (no modificar sin consultar)
- Ceiling absoluto: 12% drawdown máximo, jamás violable
- Stops por régimen: 5% (Goldilocks), 7% (Reflation), 8% (Stagflation), 3% (Deflation)
- Riesgo por trade: 1.5% del equity
- Posición máxima: 10% del equity
- Cooldown: 5-15 días según régimen

---

## ✅ ESTADO ACTUAL (al cierre de Sesión 2)

- **Git**: 5+ commits en `main`, sincronizado con GitHub
- **Test integral**: ✅ PASÓ — todas las pruebas (indicators, risk, regime, signals, parity, backtest)
- **Backtest con datos reales**: ✅ PASÓ — Max DD -5.37%, PF 1.52, Sharpe 0.366, 550 trades
- **Backend**: ✅ Corriendo en `http://localhost:8000` (uvicorn con --reload)
- **Frontend**: ✅ Corriendo en `http://localhost:3000` (Vite dev server)
- **BD**: ✅ SQLite en `backend/fortress.db` con 5 tablas creadas
- **Backup**: `/Volumes/EMPRESA/fortress_core_backups/` con `current/` + snapshots
- **Dependencias backend**: Instaladas en `backend/.venv` (Python 3.9.6, yfinance 1.2.0)
- **Dependencias frontend**: Instaladas en `frontend/node_modules`

### Comandos que funcionan (sin Docker)
```bash
# Test integral
cd /Users/boris/Desktop/fortress_core/backend && PYTHONPATH=. .venv/bin/python scripts/test_system.py

# Backend local
cd /Users/boris/Desktop/fortress_core/backend && PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload

# Inicializar BD
cd /Users/boris/Desktop/fortress_core/backend && PYTHONPATH=. .venv/bin/python scripts/init_db.py

# Backtest con datos reales (yfinance)
cd /Users/boris/Desktop/fortress_core/backend && PYTHONPATH=. .venv/bin/python scripts/run_backtest.py

# Frontend
cd /Users/boris/Desktop/fortress_core/frontend && npm run dev

# Backup completo (GitHub + disco externo)
bash /Users/boris/Desktop/fortress_core/scripts/backup.sh
```

---

## 🔒 BACKUP — CÓMO FUNCIONA

### Script: `scripts/backup.sh`
```
1. Verifica que el disco externo /Volumes/EMPRESA esté montado
2. git add -A + commit con timestamp
3. git push origin main (GitHub)
4. rsync a /Volumes/EMPRESA/fortress_core_backups/current/
5. rsync a /Volumes/EMPRESA/fortress_core_backups/snapshots/fortress_core_YYYYMMDD_HHMMSS/
6. Autolimpieza: mantiene solo los 10 snapshots más recientes
```

**Exclusiones del backup**: `.git`, `.venv`, `venv`, `node_modules`, `.env`, `__pycache__`, DBs, cachés

### Regla de oro
> **SIEMPRE ejecutar `bash scripts/backup.sh` al finalizar cada sesión de trabajo.**

---

## 📝 SESSION_LOG.md — CÓMO ACTUALIZARLO

Cada sesión de Cline debe **agregar una nueva entrada** al `SESSION_LOG.md`:

```
## Sesión N — Título descriptivo

**Fecha**: YYYY-MM-DD
**Autor**: Cline + bjofrea-ctrl
**Estado**: [qué se logró]

### Lo que se hizo
1. ✅ ...

### Pendiente para la próxima sesión
- [ ] ...

### Decisiones tomadas
- ...

---
*Fin de Sesión N — YYYY-MM-DD*
```

---

## 🆘 COMANDOS DE EMERGENCIA

| Situación | Comando |
|---|---|
| Recuperar todo desde GitHub | `git clone https://github.com/bjofrea-ctrl/fortress_core.git` |
| Recuperar desde disco externo | `cp -R /Volumes/EMPRESA/fortress_core_backups/current/ ~/Desktop/fortress_core` |
| Verificar integridad del repo | `git fsck --full` |
| Ver último state | `cat SESSION_LOG.md` + `git log --oneline -5` |