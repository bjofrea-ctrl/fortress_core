# Fortress Core — Memoria de Sesiones (Última sesión resumida)

## Sesión 5 — Sistema de Gobernanza Multi-Agente con RAG/OKF + LLMs NVIDIA NIM

**Fecha**: 2026-05-08
**Autor**: Cline + bjofrea-ctrl
**Estado**: Sistema de gobernanza reestructurado y validado

### Nuevo flujo de decisión implementado
```
Tríada (BULL, BEAR, CONTRARIAN) → CONTROLADOR → discusión CONTROLADOR ↔ PROFESOR
→ Si no hay consenso → JUEZ decide finalmente
```

### Modelos LLM NVIDIA NIM asignados
| Agente | Modelo |
|--------|--------|
| BULL | DeepSeek V4 Flash |
| BEAR | MiniMax M3 |
| CONTRARIAN | GLM 5.2 |
| **CONTROLADOR** | **DeepSeek V4 Flash** |
| **PROFESOR** | **MiniMax M3** |
| **JUEZ** | **GLM 5.2** |

### Sistema RAG/OKF de conocimiento
- **KnowledgeRepository**: 17 entradas académicas en 4 dominios (macroeconomía, microeconomía, trading, indicadores)
- **RAGMemorySystem**: memoria de enseñanza persistente para educar a los agentes
- **OKF**: estructura jerárquica de conocimiento organizado

### Archivos creados/modificados
- `backend/app/core/knowledge_repo.py` — Repositorio RAG/OKF (NUEVO)
- `backend/app/core/advanced_agents.py` — GovernanceSystem reestructurado con flujo Tríada→Controlador↔Profesor→Juez, RAG integrado
- `backend/app/api/routes/governance.py` — Endpoints con nuevo flujo + búsqueda/agregado de conocimiento

### Validación
- Test motor predictivo: ✅
- Test sistema original: ✅
- Flujo gobernanza AAPL: final_decision=COMPRAR, Controlador aprobó, Juez no necesario (consenso)
- Knowledge repo: 17 entradas | RAG memory operativa

---
*Fin de Sesión 5 — 2026-05-08*

---


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

## Sesión 3 — Motor Predictivo Fase 2 (Investigación + Implementación)

**Fecha**: 2026-05-08  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Motor predictivo implementado y validado

### Resumen
Se realizó una investigación académica exhaustiva sobre indicadores predictivos y se implementó una capa predictiva completa (Fase 2) para Fortress Core.

### Investigación académica generada
📄 **`RESEARCH_PREDICTIVE_INDICATORS.md`** — Documento de 8 partes:
1. **15 indicadores técnicos** más fiables con correlaciones documentadas (Momentum 12-1, RSI, MACD, SMA 50/200, Bollinger, ADX, Volumen/OBV, ATR, Estocástico, Williams %R, Ichimoku, CCI, Parabolic SAR, Donchian, MFI)
2. **15 indicadores fundamentales** (P/E, P/B, EV/EBITDA, ROE, ROA, D/E, FCF Yield, Div Yield, EPS Growth, Gross Margin, PEG, Current Ratio, Asset Turnover, Book Value Growth, SUE/PEAD)
3. **Mercados de predicción** (Polymarket) — Correlaciones de probabilidad de recesión, recorte Fed, inflación con S&P 500
4. **Volatilidad y liquidez** — VIX, Amihud, patrones de volumen institucional
5. **Correlaciones macro históricas** — Matriz DXY/Oro/Plata/SP500/Bonos/Petróleo/Cobre
6. **Manipulación institucional** — Ciclo completos: acumular → markup → distribuir → markdown; smart money, CMF, divergencias
7. **Pesos variables por régimen y horizonte** — Diseño de score compuesto con umbrales
8. **Referencias bibliográficas** — 28 papers académicos clave

### Implementación — Nuevos archivos

**Backend:**
- `backend/app/core/predictive_indicators.py` — 15 indicadores técnicos adicionales
  - Williams %R, CCI, Parabolic SAR, Donchian Channel, MFI, OBV, A/D Line, CMF, Force Index, PVT, Volume-Price Confirmation, Volume Divergence, Smart Money Index, Ichimoku Cloud, RSI Divergence
- `backend/app/core/predictive_engine.py` — Motor predictivo completo
  - Pesos adaptativos por régimen de mercado (bull/bear/rango/turbulento)
  - Pesos por horizonte temporal (corto/mediano/largo plazo)
  - Score compuesto en [-1, +1] con umbrales de decisión (COMPRAR_FUERTE → VENDER_FUERTE)
  - Probabilidades calibradas con Platt scaling por horizonte
  - Detección de manipulación institucional (divergencias RSI, volumen, CMF, AD line)
  - Señales de mercados de predicción (Polymarket-like)
  - Análisis de correlaciones macro en vivo
- `backend/app/api/routes/predict.py` — API endpoints:
  - `GET /api/predict/analyze/{symbol}` — Análisis completo de un símbolo
  - `GET /api/predict/universe` — Ranking de todo el universo
  - `GET /api/predict/macro-correlations` — Correlaciones macro en vivo
- `backend/scripts/test_predictive.py` — Prueba integral del motor predictivo

**Modificado:**
- `backend/app/main.py` — Registrado router predict

### Resultados de validación

**Test motor predictivo:**
```
✅ 15 indicadores predictivos calculados (2913 registros)
✅ Score: 0.1554 | Decisión: MANTENER
✅ Fund. score: -0.0682
✅ Macro score: 0.0994
✅ Sentimiento score: 0.1875
✅ Manipulación: 0 señales
✅ Señales totales: 43
✅ AAPL: MANTENER (+0.1554) → Prob corto: 52.7%
✅ MSFT: MANTENER (+0.0450) → Prob corto: 44.5%
✅ NVDA: MANTENER (+0.1508) → Prob corto: 51.3%
✅ AMZN: MANTENER (+0.1563) → Prob corto: 49.1%
```

**API predictivo (datos reales):**
- `GET /api/predict/analyze/AAPL` → Score: +0.201, Decisión: MANTENER, 35+ señales detalladas
- `GET /api/predict/universe` → 19 símbolos analizados
  - Top: GOOGL: COMPRAR (+0.3724), NVDA: COMPRAR (+0.3228), HG=F: COMPRAR (+0.3010)
- `GET /api/predict/macro-correlations` → Correlaciones en vivo:
  - DXY: 99.89 | Oro: $4,095 | Plata: $60.06 | SPY: $771.33
  - DXY-Gold: -0.897 (desviación -0.547 del promedio histórico -0.35)

**Test sistema original:**
```
✅ Todas las pruebas pasaron (indicadores, riesgo, régimen, señales, risk parity, backtest)
```

### Endpoints nuevos en la API
| Endpoint | Descripción |
|----------|-------------|
| `/api/predict/analyze/{symbol}` | Análisis predictivo completo de un símbolo |
| `/api/predict/universe` | Ranking predictivo de todos los símbolos |
| `/api/predict/macro-correlations` | Correlaciones macro en vivo + régimen de riesgo |

### Decisiones tomadas
- 🔒 **Pesos adaptativos por régimen** — El score técnico/predicción cambia según el estado del mercado (bull, bear, rango, turbulento)
- 🔒 **Probabilidades por horizonte** — Se calculan probabilidades separadas para corto (1-30d), mediano (1-6m) y largo (1-5y) plazo
- 🔒 **Manipulación institucional cuantificada** — Se detectan divergencias RSI/precio, volumen/precio, CMF y A/D Line como proxy de distribución institucional
- 🔒 **Datos fundamentales de muestra** — `SAMPLE_FUNDAMENTALS` en predict.py son valores aproximados; sustituir por API real (e.g., AlphaVantage, Finnhub)
- 🔒 **Polymarket integrable** — `SAMPLE_PREDICTION_DATA` son valores de ejemplo; se pueden conectar a la API pública de Polymarket

### Pendiente para próximas sesiones
- [ ] Conectar datos fundamentales reales (API Finnhub/AlphaVantage)
- [ ] Conectar Polymarket API en tiempo real
- [ ] Frontend: panel predictivo en el dashboard
- [ ] Calibrar los pesos con optimización basada en backtest
- [ ] Integrar análisis de manipulación con datos de nível 2 (order book)
- [ ] Configurar NVIDIA NIM API key en .env

---
*Fin de Sesión 3 — 2026-05-08*

---

## Sesión 4 — Agentes Avanzados: TRIAD + PROFESSOR + CONTROLLER + JUDGE + NVIDIA NIM

**Fecha**: 2026-05-08  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Sistema de gobernanza multi-agente implementado y validado

### Resumen
Se implementó el sistema completo de agentes con gobernanza y aprendizaje:
1. **TRIAD** — Triple validación independiente (BULL, BEAR, CONTRARIAN)
2. **PROFESSOR** — Aprende de la experiencia histórica y enseña
3. **CONTROLLER** — Controla decisiones y valida riesgo
4. **JUDGE** — Dirime conflictos entre agentes
5. **NVIDIA NIM** — Integración con LLMs gratuitos

### Implementación — Nuevos archivos

**`backend/app/core/triad_agents.py`** — Sistema TRIAD:
- Agente BULL: busca evidencia alcista (tendencia, momentum, RSI, MACD, volumen, CMF, fundamentales, macro)
- Agente BEAR: busca evidencia bajista (tendencia, momentum, RSI sobrecompra, MACD, distribución, deuda, P/E)
- Agente CONTRARIAN: busca reversión y manipulación (RSI extremo, divergencias, Bollinger, volumen extremo, Smart Money, Gold/Silver, VIX)
- Consenso TRIAD: bull - bear + contrarian*0.5, con nivel de acuerdo (CONVERGENTE/PARCIAL/DIVERGENTE)

**`backend/app/core/advanced_agents.py`** — Sistema de gobernanza:
- **PROFESSOR**: memoria persistente (JSON), registra predicciones, genera lecciones, ajusta pesos basado en accuracy
- **CONTROLLER**: valida contra reglas de riesgo (ceiling 12%, posición 10%, riesgo 1.5%, stops por régimen)
- **JUDGE**: resuelve conflictos entre agentes, pondera macro y manipulación, emite veredictos vinculantes
- **NVIDIA NIM Client**: integración con LLMs gratuitos (Llama 3.1 8B, Nemotron, Mistral, DeepSeek)
- **Prompts nivel dios**: PROFESSOR_PROMPT, CONTROLLER_PROMPT, JUDGE_PROMPT

**`backend/app/api/routes/governance.py`** — API endpoints:
- `GET /api/governance/status` — Estado del sistema de gobernanza
- `GET /api/governance/analyze/{symbol}` — Análisis completo con gobernanza
- `POST /api/governance/record-prediction` — Registrar predicción para aprendizaje
- `GET /api/governance/professor/lessons` — Lecciones del profesor
- `GET /api/governance/professor/feedback` — Feedback de agentes
- `GET /api/governance/prompts` — Prompts nivel dios

**`backend/scripts/backtest_predictive.py`** — Backtest del motor predictivo

### Resultados del backtest predictivo (2020-2024)
```
=== RESUMEN AGREGADO ===
1d: Accuracy promedio = 51.1% | Brier promedio = 0.2553
5d: Accuracy promedio = 53.7% | Brier promedio = 0.2487
20d: Accuracy promedio = 57.5% | Brier promedio = 0.2445
60d: Accuracy promedio = 56.5% | Brier promedio = 0.2471

Mejores por símbolo:
- SPY: 60d accuracy = 66.5% (mejor)
- GOOGL: 60d accuracy = 63.3%
- NVDA: 60d accuracy = 61.7%
- AMZN: 20d accuracy = 54.8%
```

### Validación del sistema de gobernanza
```
Símbolo: AAPL
Score predictivo: 0.2243
Decisión predictiva: MANTENER
Controller aprobado: True
Controller decisión: MANTENER
Juez veredicto: MANTENER
Juez sobrepasó: []
Decisión final: MANTENER
Razón final: Aprobado por controlador
```

### Decisiones tomadas
- 🔒 **TRIAD integrado en motor predictivo** — 20% del score compuesto viene del consenso TRIAD
- 🔒 **PROFESSOR con memoria persistente** — Aprende de cada predicción y ajusta pesos
- 🔒 **CONTROLLER con reglas de riesgo NO violables** — Ceiling 12%, posición 10%, riesgo 1.5%
- 🔒 **JUDGE con poder de veto** — Puede sobrepasar a agentes en conflicto
- 🔒 **NVIDIA NIM opcional** — Funciona sin API key (modo determinista); con key usa LLM para razonamiento avanzado
- 🔒 **Backtest validado** — El sistema tiene poder predictivo real en horizontes 20-60 días (57.5% y 56.5% accuracy)

### Cómo configurar NVIDIA NIM
1. Crear cuenta gratis en https://build.nvidia.com
2. Obtener API key
3. Agregar a `backend/.env`:
   ```
   NVIDIA_NIM_API_KEY=tu_api_key_aqui
   ```

### Modelos LLM asignados a la tríada (NVIDIA NIM)
| Agente | Modelo LLM | Rol |
|--------|-----------|-----|
| BULL | DeepSeek V4 Flash | Análisis alcista con razonamiento avanzado |
| BEAR | MiniMax M3 | Análisis bajista con razonamiento avanzado |
| CONTRARIAN | GLM 5.2 | Detección de reversión y manipulación |
| JUDGE | Llama 3.1 8B (default) | Arbitraje de conflictos |
| PROFESSOR | Llama 3.1 8B (default) | Aprendizaje y enseñanza |
| CONTROLLER | Llama 3.1 8B (default) | Control de riesgo |

### Pendiente para próximas sesiones
- [ ] Configurar NVIDIA NIM API key
- [ ] Conectar datos fundamentales reales
- [ ] Conectar Polymarket API en tiempo real
- [ ] Frontend: panel de gobernanza en el dashboard
- [ ] Calibrar pesos con optimización basada en backtest
- [ ] Integrar análisis de manipulación con datos de nível 2

---
*Fin de Sesión 4 — 2026-05-08*

---

## Sesión 5 — Frontend: LiveTicker + GovernancePanel + commit de Sesiones 3-4

**Fecha**: 2026-08-06  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Frontend actualizado con LiveTicker y panel de gobernanza, trabajo pendiente commiteado

### Contexto
- Se retomó el proyecto después de las Sesiones 3-4 (motor predictivo + gobernanza multi-agente)
- Se encontró trabajo sin commitear de las Sesiones 3-4 (16 archivos, 4,773 líneas)
- El backend ya corría en `:8000` y el frontend en `:3000`

### Lo que se hizo en esta sesión
1. ✅ **Commit de Sesiones 3-4** — `103b81b` con 16 archivos (4,773 líneas):
   - Motor predictivo (`predictive_engine.py`, `predictive_indicators.py`)
   - Gobernanza multi-agente (`governance.py`, `advanced_agents.py`, `triad_agents.py`)
   - Live data (`live.py`, `LiveTicker.tsx`)
   - RAG/OKF (`knowledge_repo.py`)
   - Backtest predictivo (`backtest_predictive.py`, `test_predictive.py`)
   - Documentación (`RESEARCH_PREDICTIVE_INDICATORS.md`)
2. ✅ **LiveTicker integrado en App.tsx** — Ticker de precios en vivo debajo del header, con actualización cada 30s y selección de símbolo al hacer clic
3. ✅ **GovernancePanel.tsx creado** — Panel de gobernanza multi-agente en el dashboard:
   - Consenso TRIAD (BULL/BEAR/CONTRARIAN scores)
   - Score compuesto predictivo y decisión
   - Probabilidades por horizonte (1-30d, 1-6m)
   - Flujo de gobernanza (Controller aprobado, Juez veredicto, Decisión final)
   - Estado del sistema (lecciones profesor, veredictos juez, conocimiento RAG, NVIDIA NIM)
4. ✅ **TypeScript compilado sin errores** — `npx tsc --noEmit` pasó limpio
5. ✅ **Endpoints verificados**:
   - `GET /api/governance/status` → OK (professor, controller, judge, nvidia_nim, knowledge_repo)
   - `GET /api/governance/analyze/SPY` → OK (SPY: COMPRAR, score +0.42, prob subida 59.4%)

### Estado actual del sistema
- **Backend**: Corriendo en `http://localhost:8000` con todos los routers (risk, system, backtest, market, live, predict, governance)
- **Frontend**: Corriendo en `http://localhost:3000` con LiveTicker + GovernancePanel integrados
- **Git**: 8 commits en `main`, sincronizado con GitHub
- **NVIDIA NIM**: No configurado (modo determinista activo)

### Pendiente para próximas sesiones
- [ ] Configurar NVIDIA NIM API key en `.env`
- [ ] Conectar datos fundamentales reales (API Finnhub/AlphaVantage)
- [ ] Conectar Polymarket API en tiempo real
- [ ] Calibrar pesos con optimización basada en backtest
- [ ] Integrar análisis de manipulación con datos de nível 2 (order book)
- [ ] Backtest con datos más recientes (2025-2026)
- [ ] Implementar paper trading en vivo

### Decisiones tomadas
- 🔒 **LiveTicker con cache de 30s** — Evita sobrecargar Yahoo Finance con requests frecuentes
- 🔒 **GovernancePanel con fetch dual** — Carga status del sistema + análisis del símbolo seleccionado en paralelo
- 🔒 **Modo determinista por defecto** — NVIDIA NIM es opcional; el sistema funciona sin API key

---
*Fin de Sesión 5 — 2026-08-06*

---

## Sesión 6 — Auto-backup automático cada 10 minutos (cron job)

**Fecha**: 2026-08-06  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Sistema de respaldo automático activo — nunca se pierde trabajo

### Contexto
- El usuario pidió protección contra pérdida de trabajo por cortes de energía, internet, créditos agotados o cualquier problema
- Se implementó un cron job que respalda automáticamente cada 10 minutos

### Lo que se hizo en esta sesión
1. ✅ **Script `scripts/auto_backup.sh` creado** — Script inteligente que:
   - Detecta si hay cambios sin commitear (si no hay, no hace nada)
   - Hace `git add -A` + commit con timestamp
   - Push a GitHub (si hay internet)
   - Backup al disco externo EMPRESA (si está montado)
   - Usa lockfile para evitar ejecución concurrente
   - Log en `scripts/auto_backup.log` (mantiene últimas 200 líneas)
2. ✅ **Cron job configurado** — `*/10 * * * * /Users/boris/Desktop/fortress_core/scripts/auto_backup.sh`
   - Se ejecuta cada 10 minutos automáticamente
   - No requiere intervención manual
3. ✅ **Primera ejecución probada** — Funcionó perfectamente:
   - Detectó el script nuevo
   - Commit `ee5b810` con auto-backup
   - Push a GitHub exitoso
   - Backup a disco externo completado

### Cómo verificar que funciona
```bash
# Ver cron activo
crontab -l

# Ver log del auto-backup
cat /Users/boris/Desktop/fortress_core/scripts/auto_backup.log

# Ejecutar manualmente si es necesario
bash /Users/boris/Desktop/fortress_core/scripts/auto_backup.sh
```

### Protección en 3 niveles
1. **Cron cada 10 min** — Commit local + push GitHub automático
2. **Disco externo** — Backup a `/Volumes/EMPRESA` cuando está montado
3. **Manual** — `scripts/backup.sh` para backup completo con snapshot

### Pendiente para próximas sesiones
- [ ] Configurar NVIDIA NIM API key en `.env`
- [ ] Conectar datos fundamentales reales (API Finnhub/AlphaVantage)
- [ ] Conectar Polymarket API en tiempo real
- [ ] Calibrar pesos con optimización basada en backtest
- [ ] Integrar análisis de manipulación con datos de nível 2 (order book)
- [ ] Backtest con datos más recientes (2025-2026)
- [ ] Implementar paper trading en vivo

### Decisiones tomadas
- 🔒 **Auto-backup cada 10 minutos** — Balance entre frecuencia suficiente y no saturar GitHub con commits vacíos
- 🔒 **Lockfile** — Evita que dos ejecuciones concurrentes del cron causen conflictos
- 🔒 **Log rotativo** — Solo mantiene las últimas 200 líneas para no llenar el disco

---
*Fin de Sesión 6 — 2026-08-06*

---

## Sesión 7 — Motor Probabilístico Avanzado (estilo Jim Simons)

**Fecha**: 2026-08-06  
**Autor**: Cline (asistente IA) + bjofrea-ctrl  
**Estado**: Motor probabilístico avanzado implementado y validado con 8 pruebas

### Contexto
- El usuario pidió evaluar y mejorar el modelo probabilístico del sistema con enfoque matemático estilo Jim Simons
- Se realizó un diagnóstico completo del modelo actual y se implementaron mejoras basadas en papers académicos

### Diagnóstico del modelo actual
| Componente | Método actual | Debilidad |
|-----------|---------------|-----------|
| Probabilidad | Logística simple con k fijo | No calibrado con datos |
| Position sizing | Riesgo fijo 1.5% / ATR | No usa Kelly, no adapta a edge |
| Monte Carlo | Bootstrap simple | No modela colas gruesas |
| Correlaciones | Pearson 60d | No captura dependencia de colas |
| Pesos | Fijos por régimen | No se actualizan con evidencia |
| Backtest | In-sample | No walk-forward |

### Implementación — `backend/app/core/probabilistic_engine.py`

**7 módulos matemáticos implementados:**

1. **ProbabilityCalibrator** — Platt scaling (Platt, 1999) + Isotonic regression (Zadrozny & Elkan, 2002)
   - Optimiza A y B por máxima verosimilitud
   - PAV algorithm para isotonic
   - Persistencia de parámetros calibrados

2. **KellyPositionSizer** — Kelly fraccional (Kelly, 1956; Thorp, 2006)
   - f* = (p·b - q) / b
   - 25% Kelly fraccional para reducir varianza
   - Ajuste con edge del PROFESSOR

3. **SignalQualityMetrics** — IC, RankIC, ICIR (Grinold & Kahn, 2000)
   - Pearson IC y Spearman RankIC
   - ICIR = mean(IC)/std(IC)
   - Significancia estadística: |IC| > 2/√n

4. **BayesianOnlineUpdater** — Actualización Bayesiana (Bayes, 1763)
   - Prior Beta-Binomial conjugado
   - Posterior mean ajusta pesos de señales
   - Persistencia de pesos aprendidos

5. **FatTailMonteCarlo** — t-Student + Cornish-Fisher
   - Simulación con colas gruesas (t-Student)
   - VaR con Cornish-Fisher expansion (1937)
   - Expected Shortfall (Acerbi & Tasche, 2002)

6. **CopulaRiskAnalyzer** — Cópulas Clayton/Gumbel
   - Dependencia de cola inferior (Clayton, 1978)
   - Dependencia de cola superior (Gumbel, 1960)
   - Estimación por máxima verosimilitud con log-space

7. **WalkForwardValidator** — Validación out-of-sample
   - Ventanas de train/test deslizantes
   - IC out-of-sample por ventana
   - ICIR y % de ventanas positivas

### Resultados de validación (8 pruebas)
```
✅ TEST 1: ProbabilityCalibrator — A=0.7644, B=-0.0301, probs calibradas
✅ TEST 2: KellyPositionSizer — Kelly(0.6,2.0)=0.40, Kelly(0.4,1.0)=0.00
✅ TEST 3: SignalQualityMetrics — IC=0.6911, RankIC=0.6759, ICIR=12.81
✅ TEST 4: BayesianOnlineUpdater — momentum=0.38, rsi=0.01
✅ TEST 5: FatTailMonteCarlo — VaR=-4.88%, ES=-7.54%
✅ TEST 6: CopulaRiskAnalyzer — Clayton/Gumbel estimados sin overflow
✅ TEST 7: WalkForwardValidator — 11 ventanas, MeanIC=0.28, ICIR=2.61
✅ TEST 8: ProbabilisticEngine — Integrado, prob=0.887, shares=25
```

### Documentación generada
📄 **`RESEARCH_PROBABILISTIC_IMPROVEMENTS.md`** — Documento de 5 secciones:
1. Diagnóstico del modelo actual con debilidades
2. 10 fórmulas académicas y experimentales (Platt, Kelly, BMA, SV-HMM, Cópulas, Cornish-Fisher, Walk-Forward, Stacking, Bayes, IC)
3. Arquitectura del nuevo módulo
4. Priorización en 3 fases (A: inmediato, B: significativo, C: avanzado)
5. 20 referencias académicas

### Pendiente para próximas sesiones
- [ ] Integrar ProbabilisticEngine con PredictiveEngine (usar calibradores en vez de logística simple)
- [ ] Integrar KellyPositionSizer con AdaptiveRiskManager
- [ ] Conectar PROFESSOR con BayesianOnlineUpdater
- [ ] Fase B: WalkForwardValidator en backtest_engine
- [ ] Fase B: FatTailMonteCarlo en backtest_engine
- [ ] Fase C: StochasticVolatilityHMM con GARCH
- [ ] Fase C: EnsembleStacker con Gradient Boosting
- [ ] Configurar NVIDIA NIM API key en `.env`
- [ ] Conectar datos fundamentales reales (API Finnhub/AlphaVantage)
- [ ] Conectar Polymarket API en tiempo real

### Decisiones tomadas
- 🔒 **Platt scaling como método principal** — Más robusto que isotonic para datos pequeños
- 🔒 **25% Kelly fraccional** — Balance entre crecimiento óptimo y reducción de varianza
- 🔒 **t-Student con dof=5** — Modela colas gruesas sin ser extremo
- 🔒 **Log-space para cópulas** — Evita overflow numérico en estimación de Gumbel
- 🔒 **Persistencia de calibradores** — Los parámetros aprendidos se guardan en `data/calibrators.json`

---
*Fin de Sesión 7 — 2026-08-06*

---
## Sesión 8 — 2026-08-09: Fase E.1 v3 — Ola 2 (V1 sentimiento directo) COMPLETADA

### Objetivo
Validar V1 (sentimiento directo del inversor minorista) y decidir su integración por prueba de bloques (plan v4.3).

### Logros
- **AAII integrado** (`market_sentiment.py` → `fetch_aaii`, columna `aaii_bullbear_spread`): xls completo 1987-2026, cache parquet, anti-lookahead jueves → shift(1)+ffill. 0 NaN en panel 2019-2024.
- **Fuentes descartadas**: NAAIM (suscripción paga 2025+), CBOE put/call diario 2019+ (CDN S3 403 AccessDenied a bots; CSVs estáticos solo hasta 10/2019).
- **Diagnóstico extendido** (`diagnose_sentiment_ic.py`): AAII en univariado/terciles, H6/V1 2×2 (sent × liq), H2' (sent → posiciones COT), IC condicional por bucket de AAII, y **H7 prueba de bloques** (Grupo 1 baseline vs Grupo 2 con V1 dominante 50-70%, Brier/accuracy por horizonte 1/5/20/60d).

### Resultados clave (n=3633, sig ±0.0332)
- **Tesis del usuario CONFIRMADA**: AAII IC 60d = **-0.0773*** (rank_ic -0.0857***), única variable con IC negativo consistente en todos los horizontes. Terciles 60d monótonos: sentimiento bajo +0.0987 > medio +0.0609 > alto +0.0585. Pesimismo → sube; euforia → cae.
- **H6/V1 2×2 60d**: sent_baja domina en ambas liquideces (+0.0916, +0.0747 vs +0.0642, +0.0537) — el sentimiento domina, la liquidez modula (en línea con la tesis: liquidez es condición, no causa).
- **H2'**: sentimiento hoy → posiciones retail futuras rho +0.243 → +0.095 (lag 0→8) — la gente actúa según su actitud.
- **H6 condicional**: en euforia (bucket AAII alto) RSI IC -0.1254 y ER -0.1122 a 60d — los factores de tendencia se INVIERTEN. Base del "cuestionamiento" del ContrarianAgent.
- **H7 prueba de bloques**: G2 (V1 con 50-70% del peso) gana en Brier en **4/5 horizontes** (mejor dom=50%: 0.2616 vs 0.2694 a 60d) → **VEREDICTO: V1 se integra con peso dominante**.
- Bug menor: `fwd_1` faltaba en collect_records y en sub del H7 → corregido (horizontes 1/5/20/60).

### Pendiente
- [ ] Integrar `sentiment_regime` en `predictive_engine.py` (REGIME_WEIGHTS + capa V1 dominante)
- [ ] Reglas del ContrarianAgent sobre V1 (`triad_agents.py:268`)
- [ ] `pytest` + OOS 2025-2026 + cierre

---

### Sesión 8b — Correcciones de rigor + OOS (spec congelada) — COMPLETADO

**Pregunta del usuario**: ¿los *** corrigieron autocorrelación semanal (n_eff)? ¿el peso 50-70% fue pre-registrado o barrido? Ambas respuestas fueron NO → correcciones antes de integrar.

- **F1 n_eff Newey-West** (`newey_west_neff` en diagnose_sentiment_ic.py): n_eff por símbolo con pesos Bartlett, L=ceil(h/stride), piso 1+L. Resultado: TODOS los *** del IS se cayeron (AAII 60d: n=3633 → n_eff=279). La dirección se mantiene: terciles 60d +0.0987 > +0.0609 > +0.0585.
- **F2 H7 sin barrido**: V1_DOMINANCE=0.50 fijo, Diebold-Mariano con varianza NW (lag=ceil(h/5)). IS: G2/50 gana Brier 4/4, DM p<0.05 en 2/4 (5d p=0.001, 1d p=0.043) → cumple criterio pre-registrado.
- **F3 OOS 2025-2026** (`diagnose_sentiment_oos.py`, spec congelada pre-registrada en PLAN §7, ranking rolling 260d causal, evaluación ≥2025-01-01, UNA corrida → data/cache/oos_result_20260809_213058.txt):
  - IC AAII: 5d -0.0880, 20d -0.1326, 60d -0.3567*** (n_eff=36) — negativo en TODOS los horizontes.
  - H7-OOS: G2/50 gana Brier 4/4 con DM p<0.05 en 4/4 (60d p=0.000).
  - G1 baseline OOS: ic_score NEGATIVO (-0.33 @60d) — el baseline falla OOS, V1 lo rescata.
  - **VEREDICTO: CONFIRMA → V1 se integra con peso dominante 0.50.**
- Pendiente: integración `sentiment_regime` en predictive_engine.py + reglas ContrarianAgent (autorización del usuario), pytest, cierre.

---

### Sesión 8c — Integración de V1 (sentiment_regime) COMPLETADA — 2026-08-09

**Autorizado por el usuario**: "dale, integrá sentiment_regime en predictive_engine.py y las reglas en ContrarianAgent, con peso 0.50 como quedó pre-registrado."

- **Nuevo módulo** `app/core/sentiment_regime.py`: constantes pre-registradas §7 (dominancia 0.50, umbral extremo 0.50, pánico -15 / euforia +15, bound AAII ±35, ER lento 0.25 / rápido 0.60). Importado por engine y tríada sin ciclo (el módulo no depende de ninguno).
- **predictive_engine.py**:
  - `analyze(sentiment_data={"aaii_bullbear_spread": X})` — backward-compatible: sin datos → baseline idéntico.
  - `_sentiment_regime_signal()`: s_v1 = -normalize(spread, ±35).
  - Blend `composite = 0.5*composite + 0.5*s_v1` (pre-registrado).
  - H6: euforia extrema (s_v1 < -0.5) → tech_mom/tech_rev ×0.5 antes del compuesto + señal de reporte.
  - V4: ER20 < 0.25 con pesimismo → +0.10 (acumulación silenciosa); ER20 > 0.60 con euforia → -0.10 (distribución).
  - Señales nuevas con categoría `sentiment_regime` en el reporte.
- **triad_agents.py**: `ContrarianAgent.evaluate` acepta `sentiment_data`; regla 8 V1 (pánico < -15 → +0.3, euforia > +15 → -0.3, intermedio proporcional); en euforia extrema las señales de reversión (reglas 1-5) ×0.5 (H6). `TriadEvaluator.evaluate` propaga el param.
- **Tests** `tests/test_sentiment_regime.py` (10): blend 0.50 pre-registrado, backward-compat (None vs {}), señal neutra diluye a 0.5 (fiel a H7), pánico/euforia desplazan el compuesto, cuestionamiento H6 presente en reporte, señal invertida respecto del spread, agente contrarian pánico/euforia. **Suite completa: 36/36 passed.**
- Gotcha: el blend opera sobre el composite pre-TRIAD; el resultado expuesto (`composite_score`) lleva el ×0.8 del consenso — los tests se calibraron sobre la señal completa, no sobre el valor expuesto.
- PLAN_SENTIMIENTO.md: §4 Integración marcada IMPLEMENTADA + nueva sección 8 (estado de integración). Pendiente documentado: data feeding en el pipeline (`predict.py`) — pasar `sentiment_data` alineado a la fecha; auditoría futura: régimen HMM 2025-2026 (G1 tuvo IC negativo OOS) y n_eff=36.

### Sesión 8d — Data feeding V1 en predict.py + guardas de revisión COMPLETADA — 2026-08-10

Revisión de Claude Code antes del sí automático: (1) ¿fetch_aaii lee de caché o re-descarga el xls en cada request? (2) ¿si el fetch falla, degrada a baseline o se cae la request?

**Hallazgo de la verificación**: el cache parquet ya se leía, PERO sin TTL — una vez escrito, nunca se refrescaba (dato congelado en producción). El riesgo real no era "descarga por request" sino "cache eterno". Se corrigió con TTL semanal.

- **Guarda 1 (TTL)**: `AAII_CACHE_MAX_AGE_DAYS = 7` en `market_sentiment.py` — cache fresco (mtime < 7d) → parquet; viejo → re-descarga (máx 1/semana, nunca por request). Si la descarga falla y hay cache → devuelve **stale** (dato viejo > nada). Si el xls viene con formato inesperado (< 400 filas) → NO pisa el cache bueno, tira el dato. Solo sin cache y con descarga fallida propaga (el caller degrada).
- **Guarda 2 (degradado)**: `_load_sentiment_data()` en `predict.py` — alineación anti-lookahead (solo valores publicados antes de hoy, shift(1)); try/except → `None` → el motor corre baseline (backward-compatible). Conectado en `/analyze/{symbol}` y `/universe`.
- **Verificación en vivo**: cache real (2026-08-09) fresco → lee parquet, 0 descargas → `{'aaii_bullbear_spread': -0.926}`.
- **Tests**: `tests/test_market_sentiment.py` (6): cache fresco no descarga, stale refresca, stale degrada a stale, sin cache falla propaga, sin cache ok crea parquet, formato inesperado no pisa cache bueno. Suite: **42/42 passed**.

### Sesión 8e — Fase 0a: auditoría del régimen HMM 2025-2026 COMPLETADA — 2026-08-10

**Pregunta pre-registrada**: ¿el IC negativo del baseline G1 en OOS (2025-2026) se explica por un régimen de mercado anómalo respecto del IS?

- **Script nuevo** `scripts/audit_regime_hmm.py` (huella: `data/cache/regime_audit_20260810_082318.txt`):
  - Fit del `GlobalRegimeClassifier` SOLO con datos <= 2024-12-31 (sin lookahead en el fit).
  - Etiquetado **walk-forward**: Viterbi sobre la ventana [2015, t] por fecha (evita el lookahead suave del Viterbi global que usaría fechas futuras); remap semántico con métricas del IS.
  - Registros de señal idénticos al OOS (mismas constantes/pesos importados de `diagnose_sentiment_oos.py`), IS 2019-2024 vs OOS 2025-2026, IC por régimen con n_eff Newey-West.
- **Resultados**:
  - Distribución: OOS = 100% REFLATION (54.8%) + STAGFLATION (45.2%); GOLDILOCKS/DEFLATION 0% (vs 12.3%/14.3% IS).
  - G1 60d por régimen: REFLATION +0.03 → **-0.29**; STAGFLATION +0.03 → **-0.42 (***, inversión de signo)**.
  - V1 (aaii) 60d por régimen: REFLATION +0.11 → **+0.23**; STAGFLATION -0.05 → **+0.32** (mejora).
- **Veredicto**: el deterioro G1 es TRANSVERSAL a los regímenes activos — no hay "excusa de régimen" (STAGFLATION era el régimen dominante del IS y ahí G1 era positivo). Implicación: Fase 0b (backtest con costos) es obligatoria. Bonus: V1 se comporta opuesto al baseline (pisa fuerte donde G1 falla) → la integración 0.50 gana apoyo con evidencia por régimen.
- Caveat: n_eff OOS chico (30-136; STAGFLATION en el límite 30), dirección consistente en 1d/5d/20d/60d pero magnitudes con error amplio.
- Gotcha del script: `predict` de hmmlearn decodifica con Viterbi global → para etiquetado histórico honesto hay que decodificar por ventana parcial (walk-forward), O(n²) pero trivial con 4 estados.
- PLAN_SENTIMIENTO.md §8 actualizado con el veredicto y el archivo de huella.

### Sesión 8f — Fase 0b: backtest con costos V1 vs baseline COMPLETADA (con hallazgo estructural) — 2026-08-10

**Huella**: `data/cache/backtest_v1_costs_20260810_083449.txt` + JSON.

- **Auditoría del deflated Sharpe** (backtest_engine.py `calculate_metrics`): implementación correcta en su forma simplificada (e_max_sr exacto del paper, Lo con T-1, SR_0 = sr_std·E[max]); defecto corregido: faltaba skewness/kurtosis en la varianza del estimador (asumía normalidad → DSR optimista con colas gruesas). Ahora usa la fórmula completa de Lo (1 - γ3·SR + (γ4-1)/4·SR²), clampeada.
- **Inyección V1 en el backtest**: `signal_engine.generate_signal(..., sentiment_score=None)` con blend 0.50 pre-gate (backward-compatible; factor `sentiment_v1` en trades); `backtest_engine.run(..., sentiment_scores={fecha: s_v1})`; filtro en `_update_bayesian_weights` para que el BMA ignore factores sin prior (sentiment_v1 es externo al BMA — sin el filtro crasheaba con KeyError). Señal V1 = -clip((spread+35)/70, 0, 1) (misma definición que sentiment_regime.py), alineación anti-lookahead con build_sentiment_frame.
- **Resultados**:
  - Baseline (7 símbolos, 2019-2026, costos 0.10%+0.05%): 341 trades, win 0.355, PF 1.17, CAGR +0.12%/año, Sharpe 0.07, DSR p=0.118 → **sin edge neto demostrable**. OOS 2025-2026: Sharpe -0.60, PF 0.60 → perdió.
  - V1: **0 trades** — bloqueo MATEMÁTICO: s_v1 ∈ [-1, 0] siempre → blend = 0.5·overall + 0.5·s_v1 ≤ 0.5 < gate 0.6. La integración por bounds del motor es incompatible con el gate de entrada del backtest. La señal AAII no es el problema (0a lo confirmó); la escala lo es.
- **Decisión de diseño pendiente del usuario** (3 opciones en el veredicto): (a) señal centrada [0,1] + re-ajuste de gate; (b) blend solo sobre ranking [-1,1] (lo pre-registrado en §7 — la más fiel al OOS); (c) V1 como modulador de riesgo (posición/stops) sin tocar el gate. NINGUNA se corre sin aprobación (spec congelada).
- Cambios de código: `signal_engine.py` (parámetro sentiment_score + factor de trazabilidad), `backtest_engine.py` (sentiment_scores en run + filtro BMA + fórmula Lo completa), `scripts/backtest_v1_costs.py` (nuevo). Tests: 27 passed (signal_engine + sentiment_regime + market_sentiment + regime_classifier).
- Gotcha: `generate_signal` recalcula `calculate_all_indicators` por llamada — el dataframe de test sintético necesita columnas open/high/low/volume.

### Sesión 8g — Fase 0b-v2: variante (b) ranking H7, trial #8 COMPLETADA — 2026-08-10

Decisión del usuario (argumento: (b) es la única que corresponde a lo que H7 validó — calidad de ranking, no gate binario; (a) y (c) serían hipótesis nuevas que gastan OOS sin validación previa). Marco corregido por el usuario: no estamos montando V1 sobre un sistema que funciona — estamos probando si V1 puede CREAR un edge. Trial #8 del conteo n_trials.

- **Implementación (b)**: `signal_engine.compute_g2_rank_scores()` — G2 = 0.5·rank(score técnico con pesos FIJOS sin BMA) + 0.5·(-rank(aaii, causal 260d)). La señal es la pre-registrada en §7 (ranking), NO la normalización bounds ±35 del motor (la que 0b-v1 expuso como incompatible). Gate de entrada puro (generate_signal sin blend, revertido); `rank_signals` ordena por g2_score cuando existe (backward-compatible). `backtest_engine.run(sentiment_data={fecha: spread crudo})` precomputa G2 por símbolo; trades guardan g2_score. Pesos fijos en la serie histórica para no contaminar el rank con pesos BMA futuros.
- **Resultados (huella `data/cache/backtest_v1_costs_20260810_091011.txt`)**:
  - Mecánicamente funciona: 340 trades (baseline 341).
  - FULL: Sharpe 0.07→0.17, DSR p=0.164 (n_trials=8) → SIN edge demostrable.
  - DESARROLLO: Sharpe 0.22→0.39 (la mejora vive solo acá).
  - **OOS 2025-2026: Sharpe -0.60→-0.72 (empeora), PF 0.60→0.54** → la mejora no sobrevive fuera de muestra.
  - Buckets g2 no discriminan pnl: g2>0.7 tiene win_rate 0.314 (peor que g2≤0.5 con 0.349).
- **Veredicto**: V1 (gate o ranking) NO crea edge neto demostrable hoy. La integración del motor (8c) queda como diversificador de régimen (evidencia 0a), sin base para esperar rentabilidad con costos. No integrar más variantes de V1 sin evidencia nueva (n_trials=8 diluye el poder del DSR).
- Tests: 46/46 (5 nuevos en test_signal_engine: g2 sin sentiment, g2 rank causal del spread, ranking con g2, backward-compat, + peso priors). Gotcha del test: spread constante rankea +1 (s_v1=-1) — los tests usan tendencias, no constantes.
- Siguiente: la Fase 1 (fundamentales QC) ataca el hueco más grande (SAMPLE_FUNDAMENTALS hardcode) — decisión pendiente del usuario.

### Sesión 8h — Fase 1: fundamentales EDGAR (trial #9) COMPLETADA — 2026-08-10

**Pregunta pre-registrada**: ¿la categoría fundamental point-in-time crea edge neto con costos (DSR OOS, trial #9)? El freno pre-comprometido del usuario: si no despega → dejar de buscar variables → pasar la pregunta a arquitectura.

- **Data source pivot**: QuantConnect/Morningstar QC quedó CERRADO con evidencia concluyente (memoria engram 88): CLI `Error: There is no dataset named 'US Fundamental Data'`; API v2 rota (todos los endpoints devuelven `Invalid timestamp, value received: 0`, incl. account/read, GET/POST, epoch ms/s, ISO, OrganizationId); docs → listing es SPA; regla "sin CLI tab no se descarga". Token `...3816` nunca validado contra API real. Decisión del usuario ("sigue sin parar") → **SEC EDGAR XBRL** (filing dates REALES = point-in-time mejor que Morningstar, gratis).
- **Pipeline nuevo**: `scripts/fetch_edgar_fundamentals.py` (companyfacts 5/5, `data/cache/edgar/*.json`, 3.4-5.3 MB; User-Agent requerido, gzip) → `scripts/build_fundamentals_panel.py` (TTM por filing date, instantáneos por filing date, precios del día siguiente; `data/cache/fundamentals_panel.parquet`, 14,565 filas = 5 × 2,913 días; tags ASC 606 combinados) → `app/core/edgar_fundamentals.py` (loader `get_fundamentals` con degradación a SAMPLE_FUNDAMENTALS marcada `_data_source`; + `compute_fundamental_score_series` vectorizado que replica EXACTAMENTE el blend `_fundamental_signals` del motor, verificado vs motor diff=2e-16).
- **predict.py/governance.py**: SAMPLE_FUNDAMENTALS movido a edgar_fundamentals.py, `get_fundamentals` → `get_fundamentals_api`, `_finnhub_client` eliminado, imports actualizados. **sue_score excluido pre-registrado** (no derivable de EDGAR: requiere consenso de analistas).
- **Diagnóstico IC** (`scripts/diagnose_factor_ic.py`, n=3,633 registros 5d/stride, n_eff Newey-West, huella `/tmp/factor_ic_full.txt`): div_yield único consistente (5d +0.0785***, 20d +0.1560***, 60d +0.2730*** — pero casi dummy de empresa: 3 pagadores vs 2); ev_ebitda/current_ratio/fcf_yield dirección ok sin significancia; value (pe/pb) débil; **calidad/crecimiento (roe, roa, eps_growth, book_value_growth) en REVERSA** en estas 5 megacaps 2019-2026; peg IC nan (inf). Caveat: corte transversal de 5 acciones, no Fama-French.
- **Trial #9** (`scripts/backtest_v1_costs.py`, N_TRIALS=9, huella `data/cache/backtest_v1_costs_20260810_120906.txt`): G3 = 0.5·rank(score fijo) + 0.5·rank(score fundamental point-in-time), gate técnico puro, SIN AAII a propósito (aislar la categoría; ETFs sin cobertura → score puro). Resultados: FULL Sharpe 0.074→0.190, DSR 0.1589 (n_trials=9), maxDD -0.026 mejor; **OOS 2025-2026: Sharpe -0.595→-0.244 (sigue negativo, DSR 0.0338 — no despega)**; buckets g3 NO discriminan (g3>0.7 win_rate 0.247 < g3≤0.5 con 0.381).
- **VEREDICTO Fase 1 (freno pre-comprometido)**: la categoría fundamental NO crea edge neto demostrable. No es un problema de datos (EDGAR es real y point-in-time) — es el mismo patrón que V1 (trial #8): las variables de categoría no sobreviven el OOS con costos. **Fin de la búsqueda de variables; la pregunta pasa a arquitectura** (gates duros vs blend lineal, universo, definición de edge).
- Bugfixes: `direction="invert"` no se aplicaba en el score vectorizado (debt_equity invertido mal — dif 0.16 vs motor, corregido a 2e-16); `g3_by_symbol` parcial → KeyError con ETFs → `.get()`; timeout 15 min (3 backtests × ~5-6 min, refits HMM walk-forward = cuello de botella) → nohup en background.
- Tests: 46/46 después de todo el refactor.
### Sesión 8i — Gap audit señal→PnL + fix PARTIAL_TP (trial #10) COMPLETADA — 2026-08-10

**Orden acordado con el usuario** (sin objeciones a las 3 evaluaciones de Claude Code): criterio de "funciona" + gap audit PRIMERO; expansión de universo a 30-50 acciones DESPUÉS y solo si se justifica. Gate suelto desmentido con datos (el gate concentra señal: IC momentum dentro del gate 5d +0.194 vs +0.028 fuera). Criterio acordado: DSR OOS ≥ 0.90 sostenido en ≥2 de 3 ventanas OOS, sobre backtest con costos (no IC).

- **H1 (¿salidas cortan ganadores?)** — FALSA en la salida técnica (31 exits finales, pnl −3.3 avg, flat), pero CIERTA por **bug de PARTIAL_TP repetido**: `check_all_stops` re-dispara el parcial cada día mientras `price−entry ≥ 2×ATR` (sin flag), vendiendo 50%→25%→12.5%→… y con shares impares generando **filas fantasma** (`shares=0, pnl=0`) = 52% de las filas de trades en v1_fund. Eso contaminaba win_rate (reportado 0.36) y total_trades (340) — el real por leg era 0.787, por posición 0.562 (64 posiciones reales, +$951, payoff realizado 1.04 vs 2:1 teórico).
- **H2 (calibración población equivocada)** — premisa FALSA (el dataset de calibración ya usa `generate_signal` = población del gate), pero Platt resultó **plana/invertida**: p<0.4 gana 57% vs p>0.6 gana 54% (por posición), y Kelly solo rechaza 2% de señales → el sizing agrega ruido, no selección. El verdadero problema OOS: base_rate de "+close > entry a 20d" colapsó a 0.375 (el mercado no subió en 2025-26).
- **H3 (costo puro)** — CIERTA: 44% del pnl neto ($415 sobre $951) = 0.30% round-trip; $6.5 de costo vs $14.9 de pnl medio por posición.
- **Hallazgos extra**: régimen 1 (33/64 posiciones) sangra (win 51.5%, −$165); régimen 0/2 ganan; 0 violaciones/cooldowns/cesión cartera (capa cartera limpia); el motor opera **hambriento**: solo 27% de señales elegibles (lunes + bloqueo régimen 3 + top-5) → **9-15 posiciones OOS** → el criterio DSR OOS ≥ 0.90 es estructuralmente inalcanzable sin más frecuencia → expansión de universo relevante por PODER ESTADÍSTICO, no por edge.
- **Instrumentación**: `win_prob` + `regime_state` ahora en cada trade (diagnóstico, sin cambio de comportamiento). Determinismo confirmado (random_state=42; la diferencia 340 vs 321 era V1-sentiment vs V1+F, no ruido).
- **Trial #10 pre-registrado** (fix + metrics honestas): flag `partial_done` en `RiskState` (parcial UNA vez, reset en register_entry, pop en register_exit) + skip filas `shares≤0` en los dos appends de trades. Tests de regresión nuevos (`tests/test_risk_manager.py`, 3 tests). Huella `data/cache/backtest_v1_costs_20260810_133723.txt`, N_TRIALS=10.
  - FULL 2019-26 (V1+F): Sharpe 0.190→**0.249**, win_rate honesto **0.648** (era 0.356 con fantasma), PF 1.30→**1.46**, DSR 0.159→**0.187**, total_trades reales 91. Monte Carlo prob_loss 0.097.
  - **OOS 2025-26: Sharpe −0.198 (sigue negativo), win_rate honesto 0.667 (10/15), PF 0.848** — gana seguido pero pierde más de lo que gana (payoff, no selección); 15 trades apenas.
  - **Veredicto trial #10**: el fix mejora todo in-sample y hace honesto el reporting, pero NO cambia el problema estructural OOS: frecuencia insuficiente + payoff < 1 OOS. Siguiente fase: definición del criterio + decisiones de arquitectura.
- Script nuevo: `scripts/audit_gap_exits.py` (corre 1 backtest v1_fund y vuelca trades/events/equity a parquet; huellas `data/cache/audit_gap_exits_20260810_132028_*.parquet`).
- Tests: 49/49.
### Sesión 8j — Proyecto universo 50: Phase A (re-run post-fix) — VEREDICTO NO CUMPLE — 2026-08-10

- **Bug #2 descubierto (lock permanente)**: la Phase A original (huella `universe50_phaseA_20260810_152810.txt`) quedó congelada: último trade 2022-01-25, 0 trades en 4.5 años, maxDD -5.5%. Causa: `trigger_cooldown` se rearmaba TODOS los días mientras el drawdown de cartera persistía (≤ -5% régimen 0) incluso con CERO posiciones (el loop de liquidación era no-op pero el cooldown y el log de violación corrían igual); con equity = cash fijo el drawdown nunca se recupera → `cooldown_until` se desliza para siempre → `can_open_new_position` = False eterno. Los runs de 7 símbolos nunca rompieron -3.3% → nunca se trabaron (por eso trials #9/#10 parecían sanos).
- **Fix (aprobado por el usuario)**: guard `if self.state.positions:` en ambas ramas de drawdown de `check_all_stops` (adaptive_risk.py:122-132) — cooldown y violación solo cuando hay liquidación real. Tests de regresión: `test_no_cooldown_lock_without_positions`, `test_cooldown_still_fires_with_positions_in_drawdown` (tests/test_risk_manager.py). Suite 51/51.
- **Re-run Phase A** (huella `universe50_phaseA_20260810_165713.txt`, N_TRIALS=16, mismas ventanas): **las 3 ventanas ahora evaluables** (99/49/119 trades — la hipótesis de frecuencia CONFIRMADA) pero **criterio NO CUMPLE 0/3**:
  - W1 2020-2021: n=99, Sharpe 0.063, DSR 0.0435
  - W2 2022-2023: n=49, Sharpe -0.736, DSR 0.0021 (bear market, esperado para long-only)
  - W3 2024-2026: n=119, Sharpe +0.632, win 58.0%, PF 1.56, DSR 0.2337 (positivo y respetable, pero lejos de 0.90)
  - Monte Carlo: prob_loss 4.7%, mean +$2,789 (era 0.301/medio en el run trabado).
- **Freno pre-comprometido aplicado (§9.4)**: Phase A NO CUMPLE → proyecto cerrado SIN Phase B (EDGAR 50), pregunta de universo archivada. Lectura honesta: el universo dio el poder estadístico (49-119 trades/ventana vs 15) pero el edge no alcanza el umbral DSR ≥ 0.90 en ninguna ventana; W3 es genuinamente positivo (Sharpe 0.63, prob_loss 4.7%) — queda la pregunta de arquitectura abierta: qué significa "funciona" con estos números.
### Sesión 8k — Trial #11 (piso de stop) REFUTADO + Trial #12 (V4 ER) refutado en Fase 1 — 2026-08-10

- **Contexto**: tras la auditoría 8j (REGIME_STOP_HIT = 41 posiciones, 0% win, -$5,857), el usuario eligió el fix más quirúrgico: topar el stop de régimen al base -5% (nunca más profundo). Pre-registrado en PLAN §9.6, N_TRIALS 16→17.
- **Trial #11 (huella `universe50_phaseA_20260810_204559.txt`)**: NO CUMPLE 0/3 — y el piso EMPEORÓ el sistema: W3 DSR 0.2337→0.0584 (Sharpe 0.632→0.160, PF 1.56→1.19, win 58%→53.6%, prob_loss 4.7%→18.3%), W1 plano, W2 solo leve mejora. El stop ancho de regímenes 1/2 era lo que daba espacio para llegar al trailing en el bull 2024-26; cortar antes convierte recuperaciones en pérdidas realizadas. **Lección: el pnl aislado de un stop no es el leak — el efecto marginal sobre el sistema completo lo es. La auditoría informa, el backtest pre-registrado decide.**
- **Revert aplicado**: `adaptive_risk.py` de vuelta al estado trial #10 (mejor conocido). Tests 51/51.
- **Trial #12 (V4 — Kaufman ER, PLAN §9.7)**: el script `diagnose_er_ic.py` ya existía pre-registrado pero NUNCA ejecutado; actualizado a universo 50 + datos hasta 2026-08-04. **Fase 1 REFUTADA (huella `er_ic_trial12_20260810_211323.txt`)**: tramo alcista IC≈0 y terciles planos (ER no predice); la velocidad del tramo predice CONTINUACIÓN (+0.032/+0.058/+0.099 — momentum, lo opuesto de "el pico revierte"); tramo bajista IC POSITIVO significativo 3/3 horizontes (er20 5d +0.021**, 20d +0.034**, 60d +0.037**) — las caídas eficientes rebotan MÁS, no "siguen cayendo" (dirección opuesta a la hipótesis pre-registrada). Regla anti-anécdota aplicada (NVDA no contó). Freno: no llega al backtest, V4 archivado.
- **3 refutaciones seguidas de variable (sentimiento, fundamentales, velocidad)** → confirma que el hueco está en ejecución/arquitectura, no en variables nuevas.
- **Corolario de arquitectura**: el sistema con mejor estado conocido (trial #10, W3 DSR 0.2337, PF 2.35 total) es genuinamente positivo pero no cruza el umbral 0.90; la pregunta de "qué significa funciona" sigue abierta, ahora con 3 caminos de variable cerrados por evidencia.

### Sesión — Resumen de validación de variables + auditoría de confusores arquitectónicos — 2026-08-11

Documento nuevo: `RESUMEN_VALIDACION_VARIABLES.md` — síntesis pedida por el usuario de
todo lo probado (válido solo / refutado / mejora en combinación / pendiente). Hallazgo
nuevo al reconstruir la cronología: **trials #8 (sentimiento) y #9 (fundamentales)
corrieron ANTES del fix de PARTIAL_TP (8i) y de la expansión de universo (8j)** — sus
métricas están contaminadas por filas fantasma y por poca frecuencia (9-15 trades OOS
vs 49-119 actuales). Recomendación: re-testear ambas contra el motor actual antes de
darlas por cerradas — es más barato que sumar variables nuevas. Ver el documento para
el detalle completo, incluido el confusor de IC absoluto vs cross-sectional (sección 6.2).

### Sesión — Plan de mejora matemática (RMT/EVT/Kalman/GP-BO) — 2026-08-11

Documento nuevo: `PLAN_MEJORA_MATEMATICA.md` — inventario de OpenCode (Random Matrix
Theory, Extreme Value Theory, Bayesian Optimization, Kalman/DLM) + evaluación crítica.
Reparo aceptado: A3 (GP-BO) reencuadrado — con ~16 trials heterogéneos no hay datos
suficientes para que un GP elija entre hipótesis cualitativamente distintas; se baja de
prioridad y se re-especifica como herramienta de tuning fino dentro de un enfoque ya
elegido, no de selección de dirección de investigación. Orden final: RMT → EVT →
(paralelo: cross-sectional + re-test de sentimiento/fundamentales contra motor actual) →
Kalman → GP-BO re-especificado. Cronograma en Gantt (Mermaid) dentro del documento.

### Sesión — Auditoría académica independiente: 3 bugs de flujo + plan consolidado — 2026-08-11

`PLAN_MEJORA_MATEMATICA.md` reescrito con auditoría independiente: (1) lookahead en
`build_factor_panel.py:101` (regime del último día de la serie, no de `date` — invalida
"macro contra-régimen"); (2) IC macro +0.13 in-sample (pesos calibrados y evaluados en la
misma ventana; en panel amplio IC=-0.0247); (3) blend de comparación del trial de ridge
roto por el macro sobreponderado (ridge le gana a un baseline negativo, no confiable tal
como corrió); (4) confirmación con timestamps exactos de que trials #8/#9 corrieron
pre-fix de PARTIAL_TP; discrepancia PF 1.46 vs 2.35 sin reconciliar. Nuevo orden: Fase -1
(arreglar los 3 bugs de flujo, bloquea todo) → Fase 0 (re-correr ridge + rank_ic sobre
panel limpio) → Fase 0.5 (re-test sentimiento/fundamentales) → Fase 1 (RMT/EVT) →
Fase 2 (Kalman/GP-BO). Gantt actualizado en el documento.
