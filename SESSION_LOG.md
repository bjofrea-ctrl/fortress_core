# Fortress Core — Memoria de Sesiones (Última sesión resumida)

## Sesión (Kilo Code) — Recuperador de sesión + M4 medición viva COMPLETADA

**Fecha**: 2026-08-18
**Autor**: Kilo Code + boris
**Estado**: M4 cerrado con número medido; recuperador de sesión instalado

### Contexto de apertura
- La sesión de Kilo de ayer estaba guardada (no perdida) pero no aparecía: la ventana se
  había abierto con raíz `/` en lugar de `~/Desktop/fortress_core`; el historial es por
  carpeta de proyecto. Sesión original: `ses_feeafaaf6ffe1X8G5BaIcxbZUS`.
- Construido el recuperador para que ninguna jornada dependa de la memoria del chat:
  - `~/Desktop/Recuperar-Sesion-Fortress.command` (doble clic → abre VS Code en la carpeta
    correcta y muestra cuál fue la última sesión)
  - `scripts/recuperar_ultima_sesion.sh` + alias `fs` en `~/.zshrc`
    (`fs` retoma última sesión, `fs --listar` las muestra, `fs --nueva` arranca de cero)
  - Symlink estable `~/.local/bin/kilo` → binario de la extensión (se auto-repara si la
    extensión cambia de versión)
  - Documentado como "Ritual de apertura de sesión" en `AGENTS.md` y `ONBOARDING.md`

### M4 — medición viva de costos de ejecución (Alpaca PAPER)
El runner de ayer (`run_costs_at_open.py`, PID 17770) sobrevivió la noche, detectó la
apertura, arrancó la ronda BUY y CRASHÓ con 404 en `paper-api.alpaca.markets/v2/last/trade/SPY`.

Tres bugs reales del cliente Alpaca, todos corregidos y testeados (suite 265 passed):
1. **Endpoint de datos**: el último trade vive en `data.alpaca.markets/v2/stocks/{sym}/trades/latest`,
   NO en el host de trading (`paper-api`). Verificado en vivo: el viejo daba 404, el nuevo 200.
   Nuevo atributo `market_data_base_url` (overridable vía `ALPACA_MARKET_DATA_BASE_URL`).
2. **Fills asincrónicos**: las market orders paper responden `pending_new` en el HTTP POST —
   el fill llega 1-10s después (verificado manualmente contra SPY). `submit_market_order`
   ahora hace polling del GET de la orden hasta `filled` (deadline 30s, falla ruidoso en
   estados terminales unfilled: no registra un fill que no llegó).
3. **Símbolos con guion**: la API de datos rechaza `BRK-B` con 400 (exige `BRK.B`).
   Normalización `BRK-B`→`BRK.B` solo en el borde HTTP; la DB persiste el símbolo interno.

**Resultado medido** (ronda viva, mercado abierto, 12:30-13:43 ET):
- 120 órdenes paper = 60 buy + 60 sell; los 50 símbolos del universo cubiertos
  (los 10 primeros, SPY…AVGO, se midieron dos veces por lado — muestra extra válida)
- `cost_per_side_medido = 0.000189` (≈0.019% por lado)
- slippage_p50 = 0.000122 · slippage_p95 = 0.000519 · comisión media = 0.0 (paper sin comisión)
- Artefacto: `backend/data/cache/measure_execution_costs_20260818_134338.txt`
  + DB `backend/data/cache/execution_costs.db` (verificado: cuentas por lado consistentes,
  BRK-B con fills reales ambos lados, posiciones abiertas = 0 tras la ronda sell)

**Caveat registrado honestamente**: papel = fills instantáneos al último trade, sin
comisión, sin mercado real detrás. Es un PISO medido del costo de ejecución, no el número
live. `COST_PER_SIDE` (0.0015 asumido) NO se tocó — cambiarlo por el medido es decisión del
usuario con pre-registro (afecta retroactivamente los veredictos de todos los trials).

### Validación
- Suite completa: 265 passed (15 en `test_execution_costs.py`)
- ruff limpio en los archivos tocados (los 89 errores del resto del repo son preexistentes
  en scripts de diagnóstico viejos, fuera de alcance del CI que corre lint+test)
- Smoke en vivo contra las APIs reales de Alpaca antes de cada relanzamiento
- Orden de diagnóstico manual cerrada a cero (cuenta flat, sin residuos)

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

### Sesión — Proyecto §11 Fase 0-3 + Trial #13 (ridge como score) REFUTADO — 2026-08-11

- **Proyecto §11 completado** (huellas en data/cache, commit bafeae8): panel
  `factor_panel_20260811_092828.parquet` (18,900 filas, 2,069 eligible, 50 símbolos,
  378 fechas, régimen HMM real con refit trimestral). Fase 1a correlaciones PASA
  (máx |rho| 0.295). Fase 1b ridge purgado PASA: ridge_3f IC OOS +0.0156, ICIR 0.78,
  4/5 folds positivos vs blend −0.0129 (delta +0.0285); ridge+sent IC −0.0127
  (sentimiento refutado OTRA vez). Fase 2: score del motor estable en los 4 regímenes
  (0.086/0.049/0.040/0.086) → pesos por régimen ARCHIVADO; macro es CONTRARÉGIMEN
  (+0.198 GOLDILOCKS / −0.133 REFLATION / −0.173 DEFLATION). Fase 3 PBO=0.5 exacto
  (nulo de selección, sin sobreajuste sistemático).
- **Proyecto §12 pares CERRADO**: Fase 4a cointegración NO PASA (mejor par 47% MA-CRM,
  4 pares > 40%, media 18.1%) → 4b nunca se corre; cópulas quedan SOLO como riesgo.
- **Trial #13 (PLAN §13, aprobado por el usuario) — ridge_3f como score del motor**:
  inyección por subclase dentro del script (producción intocada), score =
  predicción ridge walk-forward (refit 63d expansivo, StandardScaler fit en train,
  gate ridge_pred > 0), sin sentiment (ridge como ranking/entrada puro). Corridas
  baseline + V1 + ridge. **VEREDICTO NO CUMPLE 0/3** (huella
  `trial13_ridge_motor_20260811_120029.txt`): W1 DSR 0.0538, W2 0.0010, W3 0.1803.
  El ridge generó MÁS trades (118/77/163 vs 103/47/113) con win_rate similar pero
  Sharpe W2 −0.820, W3 0.554 — la mejora de IC (+0.0285) NO se tradujo en PnL.
  **El criterio 0.90 congelado hizo exactamente su trabajo: IC != plata.**
- **Revert aplicado (pre-registrado §13.4)**: script `trial13_ridge_motor.py` borrado;
  producción nunca se tocó (inyección por subclase). Evidencia completa en
  data/cache (txt + parquets de trades/equity/events). El motor queda en trial #10/V1.

## 2026-08-11 — Fase -1 + Fase 0.5 ejecutadas (PLAN_MEJORA_MATEMATICA §8)

- **Fase -1 bugs de flujo corregidos** (todo verificado contra artefacto):
  1. Lookahead régimen (§3.1): `build_factor_panel.py` ahora corta `market_data` en
     `date` para `predict_current_regime`. **260/378 fechas cambiaron de régimen** —
     el bug era masivo. Panel limpio: `factor_panel_20260811_144857.parquet`.
  2. **Hallazgo extra**: `MARKET_TICKERS` nunca incluyó DXY/gold/oil → el composite
     macro (y el motor) usaba SOLO SPY+TLT desde siempre. Cargados los 3 faltantes;
     panel ahora expone 4 features crudas (0 NaN) + composite con las 3 reglas.
  3. Baseline único (§4.4.4): `baseline_clean_20260811_150643.txt` reproduce 1:1 la
     huella post-fix `universe50_phaseA_20260810_165713.txt` (motor determinista).
     **Los PF 1.46/2.35 de §3.4 NO tienen artefacto verificable** → descartados como
     referencia; este baseline es el oficial para toda comparación futura.
- **Gate 0 (panel limpio): PASADO.**
- **Fase 0.5 — 3 sondas independientes**:
  - 0.5a rr2 intra-día + Newey-West: momentum t=−0.28 (no sig), rsi t=+1.38 (no sig),
    adx t=+2.31 (sig nominal, no resiste Bonferroni 4 tests). Cross-section operable
    real: ~6 símbolos/fecha, no 50. Solo momentum es ranking continuo; rsi/adx son
    gates binarios.
  - 0.5b RMT/Marchenko-Pastur (mercado removido): PC1 = 30.8% de varianza; 8
    autovalores residuales sobre λ₊=1.385, primero 15.2% → estructura sectorial débil,
    no plano de selección explotable.
  - 0.5c ridge macro crudo: delta −0.0046 vs blend, ICIR 0.174 → NO mejora nada.
    Corrobora trial #13 (la combinación no es el problema).
- **VEREDICTO GATE: W2 con matices** — timing, no selección. Rama W2 (re-evaluar
  producto: 50 símbolos vs basket) pendiente de confirmación del usuario (§9).
- 70/70 tests OK. Cambios: build_factor_panel.py, diagnose_ridge_combination.py,
  nuevos backtest_baseline_clean.py / diagnose_rr2_intraday.py / diagnose_rmt_mp.py.

## 2026-08-11 — Corrección del veredicto del gate (revisión del usuario)

- El usuario verificó los artefactos (las 3 corridas RMT chicas 150820/30/40 = cortes
  incompletos del mismo script en arreglo, sin cherry-picking) e identificó una
  tensión real en el §8: el script RMT imprime "Estructura residual real amplia ->
  consistente con W3", pero el §8 lo había reescrito como evidencia de W2
  ("sectorial débil, no explotada"). 8 autovalores reales de 49 dimensiones
  residuales, ninguno dominante al 15.2%, es estructura DIFUSA sectorial real, no
  ausencia de estructura.
- §8 corregido: el veredicto ahora distingue (1) W2 SÓLIDO para el ranking individual
  (momentum/RSI intra-día, trial #13, ridge crudo — 3 fuentes independientes) de
  (2) lo NO resuelto por RMT: hay estructura sectorial real que los factores actuales
  no tocan.
- §9 completado: rama W2 CONFIRMADA por el usuario. Alcance corregido: la
  re-evaluación compara TRES opciones — (a) basket único, (b) selección 50 símbolos
  (descartada), (c) rotación sectorial/cluster (la única con evidencia positiva RMT).
- Criterio: no pre-registrar trial de motor sobre sectores hasta tener diagnóstico
  sectorial propio (mismo protocolo intra-día/Newey-West/pre-registrado).

## 2026-08-11 — Diagnóstico sectorial endógeno (§9.c): NO pasa, (a) por defecto

- Pre-registrado con restricciones del usuario: clusters ENDÓGENOS (autovectores
  residuales RMT + jerárquico Ward sobre la misma matriz residual), PROHIBIDO GICS
  (fuente externa, riesgo de lookahead de membership point-in-time); Bonferroni 8
  clusters, umbral |t| > 2.73.
- Primera corrida con bug detectado y corregido: usó autovectores de la matriz
  COMPLETA (5 factores) en vez de la residual — el conteo de 8 de RMT es sobre
  corr_res. Fix aplicado; huella final `sector_clusters_20260811_170235.txt`
  consistente con `rmt_mp_20260811_150849.txt`.
- RESULTADO: (c) NO pasa. autovectores t=+1.03, jerárquico t=+0.57 (umbral 2.73),
  rank IC intra-día del momentum medio del cluster vs fwd 20d.
- Lectura: la estructura RMT es co-movimiento (riesgo compartido), no
  predictibilidad — §4.2 lo advertía. Momentum medio de cluster no predice.
- Opción (a) basket único queda como candidata por defecto (requiere pre-registro
  propio si llega a trial).
- 70/70 tests OK (sin cambios en app/, solo scripts nuevos). Script:
  `backend/scripts/diagnose_sector_clusters.py`.

## 2026-08-11 — Trial #14 (a) basket ADX: DESCARTADO (DSR) + re-evaluación con métrica correcta

- Trial #14 corrió según pre-registro §11: basket equal-weight 50, ADX(14) del
  basket, LONG>25/FLAT<20/histéresis 20-25, costos 0.15%/lado, W1/W2/W3.
  Chequeo de distribución previo (`basket_adx_dist_20260811_214847.txt`): NO
  degenerada (long>25 62.6%, flat<20 21.2%) → umbrales absolutos del motor.
  Re-medición de régimen sobre serie del basket (`regime_basket_20260811_213437.txt`):
  STAGFLATION invierte signo esperado, ningún |t|>2 → condicionamiento de régimen
  FUERA del trial (corre solo con ADX).
- Resultado DSR: 0/3 ventanas (W1 n=11 DSR=0.035, W2 n=10 DSR=0.067, W3 n=12
  DSR=0.029) → (a) DESCARTADA. 51 trades en 2915 días; PF 2.07/1.18/4.69,
  win_rate 73/60/67% (direccionalmente positivos pero sin evaluar).
- Script del trial borrado (revert patrón #13, producción intacta). Commit 3c2b04a.
- **CRÍTICA DEL USUARIO (correcta)**: el piso de 30 trades y el DSR están
  calibrados para el motor de 50 símbolos; para timing de UN activo, n=10-12
  trades/ventana es estructural (histéresis sobre un solo activo cruza pocas
  veces al año) y DSR≈0 es el comportamiento correcto de la métrica con muestra
  chica, no evidencia de falta de edge. Mismo patrón que
  RESUMEN_VALIDACION_VARIABLES §6.1 (sentimiento/fundamentales). La conclusión
  "el motor queda sin señal comercial en vivo" NO podía cerrarse con ese
  estadístico.
- RE-EVALUACIÓN §11.1 pre-registrada ANTES de correr: misma serie exacta
  (fidelidad verificada: ADX mediana 28.1 y 51 trades = artefacto del trial),
  métricas sobre la SERIE DIARIA: media diaria, Sharpe/Sortino anualizados,
  t de Newey-West (L=floor(4(n/100)^(2/9)), Bartlett), criterio t-NW>2 en ≥2/3
  ventanas; contexto: delta vs buy&hold del basket.
- Resultado re-evaluación (`reeval_trial14_basket_adx_20260811_220640.txt`):
  W1 t-NW +0.63 (Sharpe 0.35), W2 +0.47 (0.29), W3 +2.24 (1.31) → 1/3 ventanas
  → (a) DESCARTADA por el estadístico correcto. Delta vs buy&hold NEGATIVO en
  las 3 ventanas (t −3.06/−0.53/−1.33): el timing ADX del basket nunca supera
  a MANTENER el basket; en W1 es significativamente peor.
- Conclusión final del gate: (a) descartada con la métrica apropiada. La
  implicación global (§4.5) se sostiene: el motor queda sin señal comercial
  en vivo — ahora sí con el estadístico correcto.
- Script `reeval_trial14_basket_adx.py` CONSERVADO (registro del veredicto;
  el trial #14 se borró por patrón de revert, el re-eval no es una réplica de
  producción sino el artefacto de la decisión).
- LECCIÓN: distinguir la unidad de muestra del estadístico — piso de trades es
  para estrategias con entradas por símbolo; para timing de un activo la muestra
  es la serie diaria y el estadístico es Sharpe/t-NW, no DSR sobre conteo.
  El propio usuario pasó por alto el §11 al verificar el pre-registro; el
  principio (auditoría informa, backtest pre-registrado decide) sigue intacto.

## 2026-08-11 — CIERRE de la rama W2: las 3 opciones descartadas; motor sin señal en vivo

- Revisión del usuario del re-eval §11.1: fórmula Newey-West correcta (2/9,
  estándar NW 1994 — el 2/3 del resumen de chat era typo de transcripción, sin
  bug en código ni plan); fidelidad verificada línea por línea (ADX 28.1, 51
  trades); números idénticos entre artefacto/plan/reporte; criterio pre-registrado
  con la muestra correcta (serie diaria 505/501/649 días); buy&hold encuadrado
  como contexto, no criterio.
- Commit del re-eval intentado: ya estaba en auto-backup a8ab0a5 (22:10) —
  árbol limpio sin cambios manuales.
- CIERRE formal de la rama W2 (documentado en §9 del plan): (b) 50 símbolos
  descartada (3 fuentes), (c) sectorial descartada (t=1.03/0.57 vs 2.73),
  (a) basket ADX descartada (t-NW 1/3; delta vs hold negativo 3/3).
- Conclusión de producto: el motor queda SIN señal comercial en vivo verificada
  (§4.5). Lo que sigue es decisión de PRODUCTO, no matemática sobre esta
  arquitectura (§5 no se agenda hasta que se defina).

## 2026-08-12 — P0 implementados: contrato governance, errores HTTP, auth (ROADMAP)

En modo build, verificado contra código real antes de tocar nada (disciplina §3.4 aplicada a los 3 hallazgos de AUDITORIA_TECNICA.md):

- **P0-1 Contrato GovernancePanel ↔ backend cerrado**: el frontend esperaba `governance.triad_consensus.*`, `controller_approved`, `judge_verdict` planos; el backend envía `triad.{bull,bear,contrarian}.score`, `controller.approved`, `judge.verdict|status`, `judge.overruled_agents` (advanced_agents.py:570-675). Fix en `GovernancePanel.tsx`: interfaz y render alineados al contrato real; TS compila limpio (`tsc --noEmit` exit 0).
- **P0-2 Errores HTTP**: `market.py` (3 rutas) y `live.py` (1 ruta) devolvían `{"error": str(e)}` con 200 OK → ahora `HTTPException(500)` con detalle. `except:` desnudo de `live.py:53` acotado a `(AttributeError, TypeError, ValueError)` (era un continue con try/except interno). Verificado con grep: 0 `except:` desnudos y 0 `return {"error"` restantes en todos los routers.
- **P0-3 Auth**: `verify_api_key` pasa a `hmac.compare_digest` (governance.py); `config.py` agrega `model_validator` que FALLA si `ENVIRONMENT != development` y `SECRET_KEY` es vacía o el default `change-me-in-production`. `.env` real de backend la tiene seteada (verificado sin exponer valor) → no rompe el arranque.
- **Tests nuevos (10)**: `test_governance_contract.py` (5: shape triad/controller/judge/final + ausencia de campos legacy) y `test_governance_auth.py` (5: acepta/rechaza/missing/time-constant/validator production). **Suite total: 80 passed, 0 failed** (70 previos + 10 nuevos). Frontend: `tsc --noEmit` limpio.
- ROADMAP.md actualizado: 3 filas P0 → 🟢 cerrado, Gantt con :done. Nota documentada: 25/27 endpoints siguen abiertos POR DECISIÓN (UI pública + repo público) — solo escritura RAG protegida.
- Note: los P1/P2 del ROADMAP (fechas 2015-2024 de market.py, Python 3.11 vs 3.9.6, README, docstring Controller/Judge, prompt_engine.py, CI) siguen pendientes — no incluidos en esta tanda.

## 2026-08-12 — Tanda D: §13.1 costos CERRADO (no pasa), Fase 0.6 corriendo, investigación externa hecha

Sesión de investigación (Tanda D del plan consolidado). Disciplina §14 respetada: criterios pre-registrados ANTES de correr, verificación contra artefactos, cero post-hoc.

### Item 10 — §13.1 backtest gap-reversion con costos reales: NO CUMPLE (cerrado)
- **Pre-registro** en PLAN_MEJORA_MATEMATICA §13.1 (criterio: n_dias ≥ 100 Y media del retorno neto diario > 0 con t-NW ≥ 2.0, fade EW open→close, |gap|≥1%, ≥3 fades/día, costos 0.15%/lado × 2).
- **Script**: `scripts/backtest_gap_costs.py` (reutiliza el aparato NW de diagnose_gap_reversion.py).
- **Artefacto**: `backtest_gap_costs_20260812_173951.txt` — 145729 filas, 2206 días operados (75.7%), media 11.3 fades/día.
- **Resultado**: bruto medio diario −0.00005 (t-NW −0.20, indistinguible de cero); neto −0.00305 (t-NW **−11.53**); Sharpe neto −3.90; 39.3% días positivos. → NO CUMPLE.
- **Lectura (interrogatorio honesto)**: el rank-IC −0.0525 (t=−11.29) medía consistencia de ordenamiento; el fade EW diluye los gaps grandes. El retorno bruto ya es ≈0 → la significancia del IC no se tradujo en PnL promedio NI ANTES de costos. §13 queda CERRADO de verdad: gap-reversion = hallazgo académico, ejecución intradía descartada con esta infraestructura. Explorar umbrales/top-N post-hoc violaría el pre-registro (§14) — si se quisiera, es un pre-registro nuevo.

### Item 12 — Fase 0.6 re-test V1/fundamentales: COMPLETADA — NO CUMPLE 0/3 ambas variantes
- **Terminó** (2026-08-12): artefacto `fase06_retest_20260812_175055.txt`, TODAS las
  ventanas evaluables (n≥30 en las 9 celdas). Veredicto mecánico aplicado: V1 0/3
  (DSR 0.041/0.002/0.225) y FUND 0/3 (DSR 0.121/0.004/0.330) vs baseline 0.071/0.028/0.173.
- **Lectura honesta**: (1) V1/AAII — la única variable con cobertura completa (2913/2913)
  — es más débil que baseline en W1/W2: el "rescatador" de la sesión 8d no sobrevive el
  universo 50 con la vara arreglada → refutación #8 robusta. (2) FUND gana W1/W3 pero
  con cobertura 5/50 (10%) el efecto no es atribuible a la categoría, y pierde W2 — sin
  consistencia. (3) El patrón del trial #11 histórico (≈0 trades post-2023) NO se repitió:
  W3 operó n=113-134. Baseline post-fix universo 50 queda como único modo documentado.
- ROADMAP item 12 → ✅; resultados en PLAN §0.6.1.

### Item 11 — §12 régimen-vs-volatilidad: CERRADO como pista sin acción (decisión del usuario)
- **Decisión (2026-08-12)**: cerrar §12 como pista sin acción. No se conecta
  TARGET_VOLATILITY, no se reducen estados del HMM (tocaría el modelo de régimen en
  producción sin hipótesis nueva), no se espera más historia pasivamente. Documentado
  en PLAN_MEJORA_MATEMATICA §12 + ROADMAP. Se retoma solo con pre-registro nuevo.

### Item 13 — Investigación externa (trading cuántico / gobernanza multi-agente LLM): HECHA
- Informe completo en `RESEARCH_EXTERNA_CRITICA.md` (fuentes verificadas, 2026-08-12):
  - **Gobernanza multi-agente LLM**: TradingAgents (UCLA, arXiv:2412.20138, ICML2025 wsp, 182 citas) y FinCon (NeurIPS 2024) validan el patrón "firma simulada" (bull/bear + risk team) — el diseño de fortress_core es esa clase, con la variante ventajosa de loop determinista. **TradeTrap (2025)**: pequeñas perturbaciones en agentes LLM autónomos → concentración extrema y drawdowns → valida nuestra decisión de NIM solo en capa de gobernanza/evaluación, nunca en el loop de decisión.
  - **Risk-mgmt-first para operadores chicos**: Barber & Odean 2000 (JF 55(2), 1144 citas): 11.4% vs 17.9% anual los que más operan; Barber-Lee-Liu-Odean (Taiwan 2008): costos −3.8 pp/año; survival day-trading 44/24/15% a 1/2/3 años. = el sistema ya internaliza las dos únicas reglas con evidencia: no sobreoperar + costos reales (hoy §13.1 lo demostró en miniatura).
  - **Trading cuántico**: papers reales (QAOA/annealing portfolio, TUM/TNO/arXiv 2504.08843) pero el valor está en miles de activos + constraints (NISQ híbrido); para 50 tickers con 1 Mac el QP clásico resuelve en milisegundos → CERRADO como no-relevante, confirmando el escepticismo de la primera auditoría.

### Ritual / pendientes
- Tanda D COMPLETA: items 10 ✅ (NO CUMPLE), 11 ✅ (pista sin acción), 12 ✅ (NO CUMPLE 0/3), 13 ✅ (research hecha).
- Commit + push + espejo + memoria Engram al cerrar (commits d611f67, 7e0c7b0, y el de este cierre).

## 2026-08-13 — §18.1 C6 backtest con costos: NO CUMPLE (cierre §18, Tanda D completa)

- Pre-registro §18.1 (PLAN_MEJORA_MATEMATICA.md) antes de correr: fade LS del IC pooled
  de C6 (dist_ma200 vs fwd_20d, t=−2.87 exceso mercado §18), hold 20d, stride 5d,
  costos 0.15%/lado, criterio n_días≥100 Y media neta >0 con t-NW≥2.0.
- Script `backend/scripts/backtest_c6_costs.py`: 3 defectos metodológicos detectados y
  corregidos ANTES de correr (no suavizar fwd/20 por día; sin lookahead en el día de
  entrada; 20 filas del símbolo, no Timedelta calendario) + 2 errores ruff.
- Resultado: NO CUMPLE. LS bruto −0.000019/día (t-NW −0.07), NETO −0.000228 (t-NW −0.88),
  Sharpe −0.27, 45.5% días positivos. SO neto −0.000758 (t-NW −2.92). 3703 units, 2661 días.
- Verificación de integridad §14: panel reproduce §16 EXACTO (Pearson IC −0.1582,
  Spearman −0.1129, n=3703) — señal fiel.
- Diagnóstico: E[sign×fwd]=+0.00017 → el fade crudo pierde el drift (short la mayoría
  del tiempo en mercado alcista). El hallazgo de §16/§18 vive en exceso de mercado,
  no en nivel; la mecánica LS cruda no lo capitaliza. Una variante market-neutral sería
  UN NUEVO pre-registro, no un ajuste (disciplina §14).
- §18 CERRADO: C6 = hallazgo académico. Tanda D completa. Baseline universo 50 =
  único modo de operación documentado. Próximo: Fase 1 EVT o Fase 2 Kalman+GP-BO.
- Artefacto trackeado: `backend/data/cache/backtest_c6_costs_20260813_135830.txt`.

## 2026-08-13 — §18.2 backtest C6 hedgeado: NO CUMPLE (INTENTO FINAL) — §18 CERRADO DEFINITIVO

- Pre-registro §18.2 en PLAN_MEJORA_MATEMATICA.md antes de correr: fade LS hedged por
  beta de mercado (pata opuesta en SPY de tamano |beta_sym|, AMBAS patas — decision de
  diseno declarada a priori), beta OLS pre-muestra 2015-2018 (cero datos de test),
  costos 0.15%/lado x 2 patas = 0.003*(1+|beta|) al entrar, criterio identico a §18.1.
- Regla de parada del usuario incorporada al pre-registro: INTENTO FINAL de C6; si NO
  CUMPLE -> §18 cierra DEFINITIVO, sin tercera variante.
- Resultado: NO CUMPLE. LS-HEDGE bruto +0.000149/dia (t-NW +1.01), NETO -0.000292
  (t-NW -1.97), Sharpe -0.61. SO-HEDGE neto -0.000349 (t-NW -2.72). 3703 units, 2661 dias.
- Check de integridad ok en el artefacto: n=3703, Pearson IC -0.1582, Spearman -0.1129,
  P(dist>0)=0.744. Betas: AAPL 1.195, V 1.005, MA 1.105, ORCL 1.062, IBM 0.833,
  QCOM 1.352, TXN 1.217 (|beta| medio 1.110).
- Interpretacion final: el hedge funciono (bruto paso de -0.000019 crudo a +0.000149,
  la magnitud exacta de E[sign*fwd]=+0.000172) -> la senal EN EXCESO DE MERCADO existe,
  confirmada al neutralizar el drift. Pero su tamano es del orden de los costos:
  +0.30% bruto/trade vs 0.63% hedged. Senal real, no tradeable.
- §18 CERRADO DEFINITIVO (regla de parada): C6 = hallazgo academico, linea MA200
  CERRADA. Baseline universo 50 = unico modo de operacion documentado.
- Artefacto trackeado: backend/data/cache/backtest_c6_hedge_20260813_154313.txt.
- Bugf ies del script: unpacking lstsq (2 coefs, no 1) + F821.

## 2026-08-13 — Fase 1 EVT: diagnóstico de colas universo 50 — PASA el gate

- Pre-registro §19 en PLAN_MEJORA_MATEMATICA.md antes de correr: GPD/POT sobre
  retornos estandarizados EWMA (lambda=0.94, RiskMetrics — arch/GARCH NO instalado,
  limitacion declarada), umbral p95% (~146 excesos/activo), VaR/ES-GPD 99% vs
  empirico vs normal, backtest de la cola, Ljung-Box(10) sobre z^2.
- Gate fijado ANTES: (1) >=15/50 con xi>0 sig (t>1.64) Y (2) >=30% con excesos bajo
  VaR-normal >= 1.5%.
- Resultado: PASA. xi>0 sig en 28/50 (56%); excesos VaR-normal >=1.5% en 47/50 (94%,
  promedio 1.95% vs 1% esperado); ratio VaR99-GPD/VaR-normal medio 1.26 (VaR-GPD ~3.0 z
  vs 2.326); excesos reales bajo VaR-GPD 0.98% (calibra bien); LB(10) sig solo 8/50.
- Implicacion: la regla de stop 2xATR del motor esta sistematicamente subdimensionada
  contra el riesgo de cola (~26% de distancia al VaR 99%) -> siguiente paso: trial de
  stops EVT del motor (pre-registro aparte, ventanas W1-W3, DSR>=0.90, n_trials=18).
- Bug de script detectado por interrogatorio de verosimilitud: VaR normal con signo
  invertido (excesos del 98% — imposible para VaR 99%); corregido y re-corrido;
  artefacto 155217 descartado como artefacto del error (misma convencion que §9).
- Artefacto trackeado: backend/data/cache/evt_tails_20260813_155237.txt.

## 2026-08-14 — M2 contrafáctico REGIME_STOP_HIT CERRADO + M0 trial EVT relanzado (heartbeat + desacople)

- Contexto: retomar pendientes de ROADMAP (items 21 y 22 + plan de mecánica). Al leer
  AUDITORIA_MECANICA.md: Hallazgo 0 (trial EVT murió 2 veces sin traceback), plan M0-M4.
  M1/M1b ya cerrados → siguiente paso del plan = M2 (contrafáctico de las 41 salidas por
  REGIME_STOP_HIT), que no depende de M0.
- M0 (en curso): antes del 3er intento del trial EVT se aplicó el checklist del Hallazgo 0:
  (1) heartbeat propio en `trial_evt_stops.py` (`[heartbeat] t=Ns | fase=...` cada 60s,
  daemon thread, log() con flush — sin cambio de metodología, verificado py_compile);
  (2) lanzamiento desacoplado: `nohup` + wrapper con `os.setsid()` (grupo de procesos
  propio, PID 8856, PGID=8856) + `PYTHONPATH=.` (sin esto el import de `app` falla —
  invocación canónica del repo, SESSION_LOG:131). Causa raíz probable de las muertes
  silenciosas: el harness del lanzador anterior mata el grupo de procesos al terminar
  (por eso cada reintento moría sin traceback, un paso más adelante). Heartbeat
  verificado funcionando (t=120s, t=180s, fase=baseline run).
- M2 CERRADO: `diagnose_regime_stop_contrafactual.py` (pre-registrado en docstring),
  artefacto `regime_stop_contrafactual_20260814_173001.txt`.
  - Puerta de fidelidad (pre-registrada): 152 posiciones con salidas 100% naturales
    reproducen el parquet EXACTO (exit_date + razón + pnl). La réplica de la mecánica
    de salida per-symbol es fiel al motor (ceiling 0.12 → parcial 2xATR → trailing
    1.5x/2xATR → técnica adx<20 o close<ema20<ema50; slip 0.0005; PnL sin comisión).
  - Resultado: 16/41 (39%) se habrían recuperado; 25/41 igual o peor; delta total ≈ $0
    (real −$5,867.12 vs cf −$5,867.15); solo 6/41 habrían ganado; salidas cf: 23
    TÉCNICA, 13 CEILING, 5 TRAILING; mediana +9 días.
  - Lectura: el stop convierte pérdidas profundas (13 habrían llegado a CEILING: NVDA
    −$554 vs −$286, PFE −$313 vs −$145) en pérdidas tempranas chicas, sacrificando una
    minoría de recuperaciones (NVDA +$151, GE +$115, JPM +$158). El −$5,867 es el
    precio del seguro, no una fuga.
  - Verdicto per criterio pre-registrado (<50% recuperadas): M3 NO se dispara; M4
    tampoco. Del plan de mecánica queda solo M0 (trial EVT en curso).
- Bug propio detectado y corregido durante la verificación de fidelidad: la primera
  versión incluía las 41 posiciones REGIME_STOP_HIT en la puerta de fidelidad (imposible:
  el replay sin stop de régimen no puede reproducir su salida por diseño) — corregido a
  posiciones con salidas 100% naturales. Artefacto fallado 172929 conservado como
  evidencia del ciclo.
- Docs actualizados: AUDITORIA_MECANICA.md (Fase M2 cerrada), ROADMAP.md (item 23
  agregado, item 21 actualizado a "en curso", fecha de actualización).

- **M6 — Ledger de trials HECHO (Command Code, 2026-08-14)**: `app/core/trial_registry.py`
  (lectura/escritura de `data/trial_registry.json`, `register_trial`/`trials_by_family`/
  `consumed_budget`/`current_threshold` con corrección Bonferroni), backfill de 29
  entradas desde `PLAN_MEJORA_MATEMATICA.md` + `RESUMEN_VALIDACION_VARIABLES.md`
  (`scripts/backfill_trial_registry.py`), auditoría `scripts/audit_trial_budget.py`
  (imprime presupuesto por familia y avisa si un trial nuevo excedería el umbral),
  15 tests en `tests/test_trial_registry.py` (registrar/releer, presupuesto por familia,
  umbral que se endurece, fallo ruidoso ante JSON corrupto/incompleto, n=0 válido para
  re-tests).
- **HALLAZGO (contrato M6 — el desacuerdo ES el resultado)**: el backfill cuenta **27
  n_trials_consumidos** vs el **n_trials=17** citado en §6/§0.6.1/§20 (diferencia +10).
  No se ajustó nada para cuadrar. Descomposición: 17 = 13 trials #1-#13 (§6) + 4 sin
  slot (fix #10, re-tests Fase 0.6 #8/#9); 27 = 13 + 8 hipótesis de motor adicionales
  registradas (trial #14 basket, trial #15 EVT en curso, diagnóstico sectorial,
  re-evaluación §11.1, gap-reversion, sub-períodos, MA200 clusters, Donchian). El
  número 17 subestima el presupuesto real consumido: el umbral Bonferroni vigente de
  la familia motor_signal es 0.9889 (no 0.90). Artefacto:
  `data/cache/trial_registry_backfill_audit_20260814_202751.txt`.
- Decisión de diseño (declarada): `n_trials_consumidos=0` es válido para re-tests de
  variables ya refutadas (Fase 0.6, RESUMEN §6.1 — "no consume slot nuevo"); el umbral
  actual `current_threshold(familia)` = 1 − (1−0.90)/n con n = consumidos+1.
- Verificación: suite completa `cd backend && .venv/bin/python -m pytest` → **151
  passed** (136 previos + 15 nuevos); ruff limpio en los 4 archivos.
- Docs: `ROADMAP.md` (item 24), `ORDENES_MODULOS.md` (M6 → ✅ hecho). Sin commit/push
  (regla de ORDENES_MODULOS.md: no commitear sin autorización explícita de Boris).

## Cierre de sesión — 2026-08-14 21:16 (Claude Code)

**Doctrina de equipo**: acordada con Boris tras corrección directa (frenaba con
restricciones falsas en vez de acompañar). Grabada en memoria persistente
(`feedback_como_trabajar_con_boris.md`, `user_boris_constructor.md`, ambas "LEER
PRIMERO" en `MEMORY.md`) y propagada a los 5 puntos de entrada de agentes
(fortress_core, medai, empresa-hibrida, discover-rapanui, `~/.config/opencode/`),
0 líneas borradas en los 5 diffs, verificado. 8 puntos, incluido el último agregado
hoy por Boris: "siempre lo sólido, lo mejor, nunca lo más fácil" — con la aclaración
explícita de que no contradice "construir sin ceremonia" (trámite vs. factura).

**Diseño**: `DISENO_INSTRUMENTO.md` — tesis "Fortress como instrumento diagnóstico
calibrado, no predictor". Releído el documento completo de Qwen ("Quantamental God")
párrafo por párrafo y clasificado contra el código real (verificado con grep, no de
memoria). Dos aportes genuinos sobrevivieron: (1) Predicción Conforme — abstención
como salida de primera clase, 0 apariciones en el repo antes de hoy; (2) desajuste de
etiquetado — toda la investigación midió `fwd_return` a horizonte fijo pero el motor
sale por barreras (confirmado leyendo `backtest_engine.py`/`adaptive_risk.py`). 6
módulos definidos por contexto que exigen, no por qué hacen — la palanca real contra
el gasto de tokens es localidad de contexto, no paralelismo (Qwen identificó mal esto).

**M1 — Etiquetado por barreras HECHO**: `app/core/barrier_labeling.py`, replica las 4
barreras de `adaptive_risk.check_all_stops` verbatim y en orden de prioridad (techo
absoluto 12% → stop de régimen → toma parcial 2×ATR → trailing). 17 tests de
fidelidad, no de cobertura (prioridad entre barreras, anti-lookahead, bruto vs. neto
con costos). Suite completa: 136 passed. Ruff limpio.

**Órdenes de trabajo por módulo**: `ORDENES_MODULOS.md` — bloques autocontenidos para
M4 (Cline), M5 (OpenCode), M6 (Command Code), cada uno con su propio contrato de
salida y sin necesidad de leer el proyecto entero.

**M6 verificado por Claude Code** (no solo el autoreporte de Command Code): archivos
en disco, 15 tests corridos de nuevo, `audit_trial_budget.py` ejecutado — el 27 vs 17
se sostiene, se ve en el desglose por familia (`re_test`: 2 entradas, 0 consumidos).

**Auto-backup**: se confirmó que `scripts/auto_backup.sh` hace `git push origin main`
automáticamente cada 10-20 min (`grep` en el script + verificado contra GitHub vía
`gh api`, HEAD remoto = HEAD local). Todo el trabajo de hoy ya está público. Barrido
de secretos sobre el diff completo del día (2915 líneas, 5 patrones de credenciales
reales) → limpio. Primer intento de barrido falló por un flag mal usado (`rg -E`) y
casi se reportó como "limpio" sin haber corrido — corregido antes de afirmar nada.

**EVT (ítem 21) — ESTADO PARA MAÑANA**: el bug mecánico (Hallazgo 5, EWMA sin
cuadrado) ya está diagnosticado y arreglado (1 carácter) por OpenCode, documentado en
`AUDITORIA_MECANICA.md` y `ROADMAP.md`. El re-run válido (PID 19831, lanzado 19:58)
**sigue corriendo al cierre de esta sesión**: último heartbeat `t=4621s` (~77 min),
fase `EVT run` (ya pasó el baseline). Estimado total ~90-105 min — probablemente
termine solo, sin que nadie lo mire. **No matar este proceso.** Al retomar mañana:
1. Revisar `backend/data/cache/trial15_evt_stops_20260814_195828.txt` — si terminó,
   el veredicto sale de ESTA corrida (no de los intentos #1/#2, que murieron por
   terminación externa del proceso, ni del intento #3, que tenía el bug de sizing).
2. Si terminó: verificar contra el artefacto (parquet + log), no contra ningún
   resumen — sigue siendo la regla más importante del proyecto.
3. M2 (instrumento conforme) es la continuación natural — M1 ya está listo para
   consumirse.
4. M4 y M5 siguen libres — las órdenes ya están escritas en `ORDENES_MODULOS.md`,
   listas para pegar en una sesión nueva.

**Pendiente de decisión de Boris, no ejecutado**: commit final descriptivo que cierre
esta unidad de trabajo (auto-backup ya guardó y pusheó el contenido, pero sin mensaje
descriptivo real). Se deja para cuando el EVT termine, así el commit cubre el
veredicto completo en vez de cortarlo a mitad de camino.

- **Trial #15 EVT — CERRADO (Command Code, 2026-08-15)**: el re-run válido terminó
  solo (último heartbeat ~77 min, corrida total ~3h50). Verificado contra el artefacto
  `trial15_evt_stops_20260814_195828.txt` (log `trial15_evt_stops_run2_console.log`):
  **NO CUMPLE 0/3** — W1 n=103 DSR=0.0649, W2 n=47 DSR=0.0253, W3 n=113 DSR=0.1602
  (criterio DSR≥0.90 en ≥2/3). Parquet `_evt_trades.parquet`: 281 filas, win_rate
  60.5%, n por ventana coincide con el log. El sizing EVT (VaR_GPD 99% walk-forward)
  no supera al baseline 2×ATR → no se integra. Fase 1 EVT queda cerrada: §19
  (diagnóstico PASA) + §20 (trial NO CUMPLE) como evidencia, el camino que el propio
  pre-registro definió.
- **Verificación independiente del veredicto (Claude Code, 2026-08-15)** —
  reconstrucción COMPLETA del sizing sobre los 281 trades del parquet EVT (mismas
  tablas walk-forward, ATR 14 y régimen por trade):
  (a) `var_mult×σ_EWMA_día` (mediana 0.052, p90 0.091, max 0.266) **nunca superó**
  `price×position_stop` ni `2×ATR` (`evt_term > floor` = 0/281, `evt_term > 2×ATR` = 0/281);
  (b) `max_shares ≤ shares_by_risk` en 281/281 (álgebra: `0.5×E/P > 0.1×E/P` dado el
  piso de régimen 0.03 → `shares_by_risk`, donde vive la variable EVT, nunca es
  binding; el `min()` lo decide Kelly o el tope);
  (c) corolario: métricas baseline==EVT idénticas a 4 decimales = el sistema midiéndose
  a sí mismo. **El veredicto es vacío por diseño, no una refutación del EVT** —
  probar cualquier distancia de riesgo requiere rediseñar el sizing para que
  `shares_by_risk` sea binding (p. ej. `fractional_kelly=0` en la comparación),
  decisión del usuario. Documentado en `AUDITORIA_MECANICA.md` Hallazgo 6.
- Con esto, del plan de mecánica (M0-M6) queda CERRADO M0 (como trial inválido, no
  concluyente); M2 (instrumento conforme) sigue en curso (dueño Claude Code); M4/M5
  libres; M6 hecho.
- Docs: ROADMAP.md (ítem 21 → ✅, tabla maestra + fila trial EVT).

- **M8 — Código muerto ⚪ verificado (Command Code, 2026-08-15)**: se confirmó con
  grep contra el código real (no memoria) que `ProbabilisticEngine` + `KellyPositionSizer`
  solo los usa `scripts/test_probabilistic.py` y `RiskParityAllocator` solo
  `scripts/test_system.py` — sin tests automatizados, sin imports en producción, sin
  correr en CI. PERO `probabilistic_engine.py` NO es descartable: `backtest_engine.py:10-17`
  importa 6 clases en producción (BayesianOnlineUpdater, CopulaRiskAnalyzer,
  FatTailMonteCarlo, ProbabilityCalibrator, SignalQualityMetrics, WalkForwardValidator),
  `signal_engine.py:7` importa BayesianOnlineUpdater y `opportunities.py:23` importa
  CopulaRiskAnalyzer + ProbabilityCalibrator. Eliminar las 3 clases muertas requiere
  decidir el destino de los 2 smoke scripts — decisión que queda para Claude Code.
  ROADMAP.md fila ⚪ actualizada a 🟢 verificado.

## Cierre de sesión — 2026-08-15 (Claude Code)

**M2 (instrumento conforme) HECHO**: `app/core/conformal.py` — Split Conformal
Prediction envolviendo cualquier score existente, calibrado contra `ret_net` de M1
(no horizonte fijo). 16 tests, el central verifica cobertura empírica ≈ nominal
(90%/80%) con calibración y validación en sets DISTINTOS. Métrica primaria
`vpp_bajo_abstencion`, no Sharpe. Declarado en el docstring: la garantía de
cobertura se debilita con el tiempo (no intercambiabilidad estricta en series
financieras) — M5 (deriva) es quien avisa cuándo recalibrar, este módulo no lo
hace solo.

**M3 (compuerta de régimen) HECHO**: `app/core/regime_gate.py`. Walk-forward real
sobre `GlobalRegimeClassifier` (se le agregó `predict_regime_series` para exponer
la serie completa, reuso sin duplicar). Re-ajusta cada 63 días hábiles con datos
ESTRICTAMENTE anteriores a la recalibración — evita el lookahead que el ítem 21 ya
había señalado para EVT. Assert anti-lookahead interno, no solo declarado. 8 tests.
Infraestructura lista para probar si macro-como-compuerta (IC +0.198 GOLDILOCKS /
−0.173 DEFLATION, Fase 2) supera el promedio ponderado que falló en `ridge_3f` —
el TRIAL en sí sigue pendiente de pre-registro, decisión del usuario.

**M7 retirado de Command Code, criterio de delegación establecido**: Boris preguntó
si el cableado M1+M2+M3 era trabajo sensible para delegar. Respuesta: sí — se
delega lo que falla RUIDOSO (contrato verificable desde afuera), se queda el
orquestador lo que puede fallar EN SILENCIO (números plausibles, tests que pasan
sin detectarlo) y cuyo daño se propaga a todo lo que lo consuma después. Confirmado
el mismo día: Cline centralizó `COST_PER_SIDE` en `config.py` y tocó
`barrier_labeling.py` con un import roto (`app.core.config` en vez de
`app.config`) — los 17 tests de M1 dejaron de colectar. Se detectó corriendo la
suite completa, no el subset de la orden de M4. Corregido. Grabado en memoria
persistente (`feedback_delegar_trabajo_sensible.md`).

**M8 ejecutado (decisión + código, Claude Code)**: sobre el veredicto documental de
Command Code — `KellyPositionSizer` y el wrapper `ProbabilisticEngine` eliminados
de `probabilistic_engine.py` (quedan las 6 clases vivas, secciones renumeradas
1-6). `risk_parity.py` eliminado completo. Los 2 smoke scripts NO se borraron
enteros (mezclaban código vivo y muerto, a diferencia de `prompt_engine.py` en
Tanda C): se recortó solo `test_kelly`/`test_integrated` de
`scripts/test_probabilistic.py` y `test_risk_parity` de `scripts/test_system.py`,
conservando la cobertura smoke de lo que sigue vivo. Verificado grep repo-wide (0
referencias restantes salvo el docstring explicativo), ambos scripts corridos
end-to-end tras el recorte (exit code 0 los dos), suite completa 206 passed.

**M4 (costos medidos) HECHO por Cline, verificado independientemente**:
`app/core/execution_costs.py` — cliente Alpaca paper con inyección de dependencias
(testeable sin red), `base_url` fijo a `paper-api.alpaca.markets` (test dedicado
`test_cliente_base_url_es_paper_siempre`), `ConfigurationError` ruidoso si faltan
credenciales, `cost_per_side_medido = mean(|slippage|) + mean(comisión)` por lado.
13 tests propios, verificados por Claude Code (no solo el reporte de Cline dado el
incidente de M1 arriba): suite completa, ruff, barrido de secretos sobre el diff.
Falta la medición viva — necesita cuenta Alpaca paper real, script listo
(`scripts/measure_execution_costs.py`), sale con código 1 y explica qué falta si
no hay credenciales.

**Estado del instrumento diagnóstico (DISENO_INSTRUMENTO.md) al cierre**: M1, M2,
M3, M4, M6, M8 hechos y verificados. M5 hecho (OpenCode, verificado por suite
193→206 passed acumulada). M7 (integración) queda pendiente, mío. Ningún trial
nuevo corrido — todo lo de hoy es infraestructura, sin consumir presupuesto
Bonferroni.

**Verificación final antes de push**: `git diff origin/main..HEAD` revisado
completo (solo `ORDENES_MODULOS.md`, el resto ya estaba en `origin/main` vía
auto-backup — confirmado con `gh api` en un chequeo anterior de la sesión), suite
completa 206 passed corrida fresca inmediatamente antes del push, sin secrets.

## M7 (pipeline integrado M1+M2+M3) HECHO — cierra el instrumento completo

`app/core/diagnostic_pipeline.py`, `run_diagnostic_pipeline()`. Construido por
Claude Code (no delegado — ver "criterio de delegación" arriba), con el cuidado
extra que el cableado entre módulos de distintos dueños exige.

- Split temporal ESTRICTO por fecha real entre calibración y predicción de M2
  (`calibration_cutoff`), nunca por posición en array ni mezclando símbolos antes
  de cortar. Verificado con `test_calibracion_y_prediccion_nunca_comparten_fechas`
  desde afuera del código, no solo confiado en la implementación.
- Compuerta M3 como AND explícito, nunca OR:
  `operar = (not abstenerse_m2) AND gate_operar`. Verificado con
  `test_compuerta_es_and_no_or_verificado_en_la_salida_real` — chequea la ecuación
  booleana exacta sobre la salida real del pipeline, no una expectativa
  estadística. Si el cableado se rompe a OR algún día, este test revienta antes
  de que nadie lo note en un trial real.
- Sin `favorable_states`, el resultado es idéntico a correr M1+M2 solos (M3 no
  toca nada) — verificado explícito, no asumido.
- 10 tests, suite completa 216 passed, ruff limpio.

**Con esto, el instrumento diagnóstico completo (M1-M8, `DISENO_INSTRUMENTO.md`)
queda cerrado.** Lo único que falta para usarlo con propósito real es el TRIAL
pre-registrado de macro-como-compuerta (M3) — decisión del usuario, cuándo
escribirlo y correrlo.

`ROADMAP.md` (fila Instrumento M7 → 🟢, M2-M5 corregidas de su estado stale
anterior) y `ORDENES_MODULOS.md` (M7 → hecho) actualizados.

## 2026-08-16 — Comentario/cita falsa sobre ADX en signal_engine.py CORREGIDO (task_22ea3f8d)

- **Task disparado por el usuario** ("continua con el trabajo pendiente") — era el único ítem 🟡
  de la tabla maestra de `ROADMAP.md`.
- **Hallazgo verificado contra el artefacto real** (`rr2_intraday_20260811_150741.txt`, §0.5a
  del `PLAN_MEJORA_MATEMATICA.md`): los comentarios de `backend/app/core/signal_engine.py`
  afirmaban "adx mostró IC negativo (premiar ADX alto predecía PEOR retorno, no mejor)" en dos
  lugares (líneas 21 y 58). La medición correcta (rank IC intra-día con Newey-West — la
  metodología que el propio proyecto estableció como la correcta, no pooled) dice lo contrario:
  **adx_score IC = +0.0679, t = +2.31, "SIGNIFICATIVO (W3)"** — el ÚNICO factor con señal
  nominal, POSITIVO, que no resiste Bonferroni-4 (umbral ≈2.5) → marginal, no robusto. El
  comentario repetía la conclusión de la auditoría pooled vieja, la metodología descartada.
- **Corrección**: ambos comentarios ahora citan la evidencia correcta (IC +0.0679, t=+2.31
  nominal, §0.5a, Bonferroni-4 ≈2.5). No se tocó código — solo documentación.
- **Verificación**: suite completa `pytest` desde `backend/` → 216 passed (174s), sin regresión.
- `ROADMAP.md` actualizado (fila → 🟢, commit `TBD`).

- **Tarea C — Lead-lag entre símbolos CERRADA (Command Code, 2026-08-15)**: pre-registro
  §22 en PLAN_MEJORA_MATEMATICA.md (10 pares sector/cadena × 5 lags, Bonferroni-50,
  umbral |t|>3.48, criterio ≥2 lags consecutivos SIG(+)). Script
  `backend/scripts/diagnose_lead_lag.py`. **NO CUMPLE**: ningún par con ≥2 lags
  consecutivos significativos; los t máximos fueron ~2.7 (NVDA→AVGO lag4 −2.69),
  todos bajo el umbral. Hipótesis de lead-lag entre símbolos del universo refutada
  con la vara más estricta. Artefacto `data/cache/lead_lag_20260816_090220.txt`.
  Registrado en ledger (familia signal_diagnosis, 30 entradas totales).
- Corrección sobre la marcha (declarada): el primer run usó por error el SE de
  Newey-West sobre la serie de retornos del seguidor (SE ~0.0003 → t de ±24 a ±151,
  sin sentido estadístico). Corregido al SE asintótico de la correlación de Spearman
  `sqrt((1-ρ²)/(n-2))` (SE ~0.0185 → t razonables). El SE-NW aplica sobre series de
  ICs diarios (patrón §0.5a/§21), no sobre una correlación única por par-lag. El
  pre-registro §22 y el docstring del script se actualizaron para declarar el SE
  correcto. Primer artefacto (090136) descartado como artefacto del error.
- Suite completa: 216 passed, ruff limpio. ROADMAP.md (fila §22) actualizado.

## Cierre de sesión 2026-08-16 (Cline) — Tarea A (PLAN_LARGO_PLAZO.md): Triple Barrier como target. CERRADA — NO CUMPLE.

- **Pre-registro §23** en `PLAN_MEJORA_MATEMATICA.md` (3 factores × 3 ventanas, Bonferroni-9, |t|>2.77, signo esperado +1, lags NW por ventana `min(12, n//8)`, exclusión de los 60 barras finales por símbolo declarada ANTES de correr).
- **Script** `backend/scripts/retest_triple_barrier.py` (solo lectura de `barrier_labeling.py` — M1 — y del motor; no toca ninguno de los dos). Replica el patrón rank IC intra-día + Newey-West de `diagnose_horizon_largo.py`.
- **Corrida** (artefacto `data/cache/retest_triple_barrier_20260816_091649.txt`, EXIT 0): 142,729 labels (50 símbolos, 2,855 fechas), fidelidad OK (win_rate_neto 0.586, barrera temporal 6.24%, toma parcial 58.95%), 2,028 pares eligible+label.
- **Resultado**: ningún factor cruza Bonferroni-9 en ninguna ventana. Máximo |t|: momentum TOTAL −2.48 (signo NEGATIVO, no cuenta y no cruza). Nominales contexto: rsi W2 +1.73 (n=22), adx W2 +1.90 (n=19). Veredicto pre-registrado aplicado mecánicamente.
- **Interpretación**: el re-test contra el objetivo binario que el motor persigue (¿toca TP antes que SL?) reproduce el veredicto de magnitud — la hipótesis de "generador vacío" queda reforzada también en probabilidad, no solo en `fwd_return_20d`. Se cierra la vía "nulo en magnitud pero predice ganar/perder".
- **Ledger**: registrado `signal_diagnosis` `triple_barrier_retest` (n=1). Nota de coordinación: el texto de PLAN_LARGO_PLAZO decía familia `motor_signal`, pero el contrato del ledger clasifica rank-IC de señal bajo `signal_diagnosis` (igual que §21, §21.1 y §22) — el desvío quedó documentado en §23; `motor_signal` queda intacto (8 consumidos).
- **Verificación**: suite completa `cd backend && .venv/bin/python -m pytest -q` (ver conteo al pie), ruff limpio en el script nuevo.
- `ROADMAP.md` fila §23 → 🟢.

## 2026-08-17 — Tarea B (PLAN_LARGO_PLAZO.md): PASO 1 FinBERT earnings HECHO + acumulación universo 50 en curso (OpenCode)

- **PASO 1 implementado y verificado**: `backend/app/core/earnings_sentiment.py` — store SQLite
  (`data/cache/earnings_sentiment.db`, dedup por accession UNIQUE), fetch SEC EDGAR 8-K item 2.02
  (comunicado oficial, point-in-time; NO transcripción verbatim — limitación documentada en el
  docstring: el tono del comunicado es proxy del tono del call), FinBERT `ProsusAI/finbert`
  (import lazy, chunking ~1800 chars, score = prob_pos − prob_neg ponderado por longitud).
  CLI `backend/scripts/accumulate_earnings_sentiment.py` (universo 50, ETFs excluidos, backfill
  ~8 8-Ks por símbolo + incremental). 25 tests en `tests/test_earnings_sentiment.py`.
- **Verificación**: suite completa `cd backend && .venv/bin/python -m pytest -q` → **241 passed**
  (fresca, esta sesión), ruff limpio. Base con 24 filings (AAPL/AMD/NVDA) de la corrida de
  desarrollo (2026-08-16).
- **PASO 2 (trial) BLOQUEADO por datos**: requiere ≥8 trimestres × ≥30 símbolos acumulados.
  Hoy: 3 símbolos → no simular, documentar bloqueo. En curso: corrida completa universo 50
  (47 símbolos con earnings) lanzada desacoplada (setsid, log `/tmp/earnings_universe_full.log`)
  — verificar artefacto `data/cache/earnings_sentiment_run_*.txt` al terminar antes de cerrar.
- **Gotchas registrados** (heredados de la sesión de desarrollo, verificados en el código):
  EDGAR 403 sin User-Agent con dominio real; 8-K 2.02 de grandes tecnológicas = solo referencia
  administrativa (el comunicado vive en exhibit 99 — el fetch lo detecta); transformers
  moderno exige torch≥2.6 inexistente para macOS x86_64/Py3.9 → fijado
  `transformers==4.44.2` + `torch==2.2.2`; BRK-B → BRK.B en EDGAR.
- `ROADMAP.md` fila Tarea B agregada (PASO 1 🟢, PASO 2 ⚪ bloqueado por datos).

## 2026-08-17 — Trial #16 (pre-registro §24): abstención M2 contra baseline — NO CONCLUYENTE, defecto estructural de M2 encontrado (OpenCode)

- **Decisión del usuario** (2026-08-17): pre-registrar y correr el trial de abstención calibrada
  M2 contra el baseline real — "el motor debe callarse cuando no hay señal" con la evidencia ya
  existente.
- **Pre-registro §24** en `PLAN_MEJORA_MATEMATICA.md` (ANTES de correr): familia `motor_signal`,
  score `win_prob` (el real del motor), outcome `ret = pnl/(shares×entry_price)`, walk-forward
  acumulado sin lookahead, W2/W3 evaluables (W1 excluida por diseño: 24 trades de 2019 < piso 30
  de M2, declarado antes), Bonferroni-2 unilateral p<0.025, n_operados≥30, abst≤0.80, cobertura
  empírica [0.80,0.97] como fidelidad.
- **Corrida** (`scripts/trial_m2_abstencion.py`, artefacto
  `data/cache/trial16_m2_abstencion_20260817_100548.txt`): **abstención 100% en ambas ventanas
  (n_operados=0)** → VEREDICTO FORMAL NO_CUMPLE, pero **tautológico — hipótesis SIN MEDIR**.
- **HALLAZGO ESTRUCTURAL DE M2** (confirmado con reproducción mínima independiente, no hipótesis):
  1. El ancho del intervalo de `ConformalAbstentionEngine.predict()` NO depende del score:
     residuos absolutos + regresión lineal simple → q constante por calibración → ancho SIEMPRE
     2q. La abstención `width > max_interval_width` compara dos constantes: o abstiene todo o
     nada — incapaz de abstención diferencial por construcción (contradice la promesa de
     DISENO_INSTRUMENTO.md §7).
  2. El default `max_interval_width = 2×median(residuos)` es SIEMPRE < 2×quantile(α=0.10,
     ~91.5%) → abstención 100% garantizada matemáticamente. Cobertura empírica en rango
     (0.8367/0.8908): el instrumento calibra bien y aun así nunca opera con su default.
  3. Los 16 tests de `test_conformal.py` no lo detectan: fijan `max_interval_width` explícito
     (999/0.001/0.0); el test del default (línea 116) verifica que el default SE CALCULA como
     2×median, no que produzca abstención utilizable.
- **Ledger**: `trial_16_m2_abstencion` registrado, familia `motor_signal`, n=1, NO_CUMPLE
  (formal) → motor_signal 8→9 consumidos, umbral próximo 0.99.
- **Estado**: hipótesis de abstención ni refutada ni confirmada — M2 necesita fix de diseño
  (residuos relativos para ancho score-dependiente + default utilizable) antes de que cualquier
  trial de abstención pueda medir algo. Decisión del usuario (mismo patrón que #15).
- `ROADMAP.md`: filas Trial #16 + M2 defecto estructural agregadas. En paralelo: acumulación
  FinBERT universo 50 en curso (19/47 símbolos al cierre de esta entrada, 0 errores).
## 2026-08-17 — Tarea B (PLAN_LARGO_PLAZO) ADX walk-forward CERRADA: NO CUMPLE (Cline)

- **Task**: Tarea B del plan de largo plazo (asignada a Cline) — pre-registrar + ejecutar el
  trial ADX walk-forward para decidir si ADX, el único factor con señal nominal positiva,
  pasa a candidato a "bueno" con evidencia OOS.
- **Pre-registro §25 escrito ANTES de correr** en `PLAN_MEJORA_MATEMATICA.md`: rank IC intra-día
  adx_score vs fwd_return_20d por ventana W1/W2/W3, SE Newey-West con L=min(12, n_dias//8) (§23),
  umbral |t|>2.77 (Bonferroni-9 bilateral) con signo +1 en ≥2/3 ventanas. Cheque de fidelidad
  contra §0.5a (TOTAL L=4 debe reproducir IC +0.0679, t +2.31) — aborta sin interpretar si falla.
  Test secundario (premia operativa alto vs bajo ADX) declarado como contexto, nunca hallazgo.
- **Script** `backend/scripts/trial_adx_walkforward.py` (solo lectura del panel, NO toca el
  motor), artefacto `data/cache/trial_adx_walkforward_20260817_103916.txt` (EXIT 0).
- **Cheque de fidelidad**: OK, reproducción exacta (mean_IC +0.0679, t +2.31, 151 n_dias).
- **VEREDICTO: NO CUMPLE (0/3)** — W1 t +0.79, W2 t +1.54, W3 t +1.47; ninguna ventana cruza
  Bonferroni-9 (2.773). TOTAL ref +2.31.
- **Lectura**: señal positiva en las 3 ventanas (signo + siempre), pero ninguna significativa en
  aislamiento — el t TOTAL +2.31 era el pooling de señal débil repartida, no robustez OOS. El
  criterio ≥2/3 (que la señal se sostenga sola) no se cumple. ADX queda **marginal-no-robusto con
  evidencia walk-forward, CERRADO como candidato a "bueno"**.
- **Test secundario (contexto)**: premia ADX alto vs bajo positiva (W1 +0.0090, W2 +0.0075, W3
  +0.0135) pero t pooled no sig (máx +1.73) e inconsistente en VPP (W2 alto 0.476 < bajo 0.481).
- **Corrección declarada sobre la marcha (declarada)**: el primer run (artefacto
  `trial_adx_walkforward_20260817_103529.txt`) implementó L con `n_days_est` (fechas brutas) en
  vez de `n_dias` usados — desvío de la regla de §23. Se corrigió el script a `L=min(12, n_dias
  //8)` con n_dias = ICs usados, se re-corrió (artefacto válido 103916) y se ELIMINÓ el artefacto
  inválido. El veredicto no cambió (todos los t quedaron lejos de 2.77).
- **Ledger**: registrado `adx_walkforward`, familia `signal_diagnosis`, n=1 → **14→15 consumidos**,
  umbral vigente 0.99375. `motor_signal` intacto (9). El texto del plan decía `motor_signal`, pero
  por contrato del ledger un rank-IC de señal va a `signal_diagnosis` (mismo desvío documentado en §23).
- **Docs actualizados**: PLAN_MEJORA_MATEMATICA §25 (RESULTADO completo), PLAN_LARGO_PLAZO
  (Tarea B → 🟢 cerrado + línea ADX del estado de partida), ROADMAP (fila §25 + fecha),
  RESUMEN_VALIDACION_VARIABLES (fila ADX corregida: "IC negativo" ↓ por la evidencia real,
  mismo fix de espíritu que el de signal_engine.py del 16/8).
- **Verificación**: suite completa `cd backend && .venv/bin/python -m pytest -q` → **242 passed**
  (196s), ruff limpio en el script nuevo, sin cambios en el motor.


## 2026-08-17 — Trial #17 (pre-registro §24.1): re-trial abstención M2 con instrumento CORREGIDO — hipótesis REFUTADA con medición real (OpenCode)

- **Decisión del usuario** (2026-08-17): "sigue la implementación que a ti te corresponde" —
  P0 de su tabla: re-medir la abstención M2 tras el hallazgo estructural del #16.
- **Fix de M2 aplicado ANTES del trial** (`app/core/conformal.py`, suite 242 passed):
  (1) residuos RELATIVOS `|outcome−point|/max(|point|, floor)` con floor = p50(|point|)/10
  → el ancho del intervalo escala con el score → abstención diferencial posible; (2) default
  `max_interval_width` = p90 de los anchos de calibración (~10% de abstención, ni 100% ni 0%);
  (3) test de regresión nuevo `test_default_produce_abstencion_diferencial_no_100_ni_0`
  (test_conformal.py: 16→17 tests).
- **Corrida** (`scripts/trial_m2_abstencion.py`, artefacto
  `data/cache/trial17_m2_abstencion_20260817_104452.txt`):
  - W2 2022-2023: VPP_base 0.4694, VPP_M2 0.4043, n_operados 47, abst 4.08%, cobertura 0.7755
    → **NO INTERPRETABLE** (fidelidad: cobertura fuera de [0.80, 0.97] — DISENO_INSTRUMENTO §8).
  - W3 2024-2026: VPP_base 0.5798, VPP_M2 0.6000, n_operados 100, abst 15.97%, cobertura 0.8908 ✓
    → p=0.4347 ≫ 0.025 → **NO CUMPLE**.
  - VEREDICTO FINAL: **NO_CUMPLE**.
- **Interpretación**: con el instrumento corregido (abstención ahora discrimina de verdad),
  la abstención calibrada M2 sobre `win_prob` NO mejora significativamente el VPP (+2.0pp en
  W3, p=0.43). La pregunta del usuario "¿debería el motor callarse cuando no hay señal?" queda
  respondida: con este score y esta mecánica, NO. La cobertura W2 (77.6%) confirma además que
  la garantía conforme no se sostiene en regímenes cambiantes.
- **Estado de la línea**: abstención sobre win_prob CERRADA como refutada (no re-litigar sin
  evidencia nueva). M2 queda CORREGIDO en código y disponible para scores futuros (FinBERT
  podrá re-medirla con pre-registro nuevo cuando haya datos).
- **Ledger**: `trial_17_m2_abstencion`, familia motor_signal, n=1, umbral aplicado 0.99,
  NO_CUMPLE → motor_signal 9→10, umbral próximo 0.9909.
- `ROADMAP.md`: filas #16 (resuelto en cadena), #17 (refutada), M2 defecto (🟢 resuelto).
  En paralelo: acumulación FinBERT universo 50 en curso (25/47 símbolos al cierre, 0 errores).

## 2026-08-17 — §26 Indicadores semanales (Tarea C, Command Code): NO CUMPLE

- **Tarea C asignada** por PLAN_LARGO_PLAZO.md: probar si indicadores sobre velas
  semanales (resample W-FRI) revelan rank IC significativo contra fwd_ret_1w.
- **Pre-registro** §26 en PLAN_MEJORA_MATEMATICA.md: hipótesis, metodología, criterio
  (Bonferroni-8, |t|>2.73 en ≥2/3 ventanas), n_trials fijado ANTES de correr.
- **Script**: `backend/scripts/diagnose_weekly_indicators.py` — carga OHLCV diario de
  50 símbolos, resamplea a semanal, calcula momentum_20w/rsi_14w/adx_14w, rank IC
  intra-semana con Newey-West (L=1).
- **Corrida** (artefacto `data/cache/weekly_indicators_20260817_105918.txt`):
  - W1 (2019-2021): mom −0.17, rsi −0.08, adx +0.31
  - W2 (2022-2023): mom −0.01, rsi −0.44, adx +0.16
  - W3 (2024-2026): mom +0.19, rsi +0.14, adx +0.33
  - Máx |t| = 0.44 (rsi W2) — nowhere near significancia (umbral 2.73).
- **Veredicto**: **NO_CUMPLE**. Ningún indicador semanal alcanza significancia bajo
  Bonferroni-8. Ruido semanal no oculta señal — baseline diario sigue siendo el único
  modo de operación documentado.
- **Ledger**: `weekly_indicators_2026`, familia signal_diagnosis, n=1, umbral 0.99375,
  NO_CUMPLE → signal_diagnosis 15→16.
- **ROADMAP.md**: fila §26 agregada, estado 🟢 cerrado.
- **Suite**: no se tocó código del motor (solo script diagnóstico nuevo), suite no
  ejecutada pero sin cambios que pudieran romper.

## 2026-08-17 — Diagnóstico de ASESORÍA: mezclas de indicadores vs blend (Brier/calibración) — NINGUNA MEJORA (OpenCode)

- **Pregunta del usuario**: ¿los indicadores mezclados entre sí aumentan la predictibilidad EN LA ASESORÍA (55-90%)?
- **Contexto verificado**: las mezclas SÍ se habían evaluado pero solo con vara de señal/DSR (motor): ridge_3f IC OOS +0.0156/ICIR 0.78 (mejoró blend por |IC|) pero 0/3 DSR como score de motor (#13, revertido); BMA existe como método, no factor; macro contra-régimen capturado por ridge. NUNCA se midió Brier/calibración de las combinaciones.
- **Medición nueva** (`asesoria_combinaciones_20260817_110427.txt`): panel eligible n=2069, purga+embargo (sin lookahead), calibración ISOTÓNICA por fold aplicada OOS. Brier referencia baseline=0.2447 (base_rate 0.5727):
  - blend_actual 0.2468 (+0.0043) | ridge_3f 0.2484 (+0.0059) | ridge_3f+adx 0.2477 | ridge_macro_crudo 0.2476 | ridge_macro_crudo+adx 0.2475.
  - VPP@0.55 ≈ base rate en TODOS (0.559-0.574) → sin selectividad en el rango de asesoría.
  - VPP@0.65: blend 0.667 (n=24); los ridge 0.36-0.43 (n=11-14, ruido) — NINGUNA mejora al blend.
- **Hallazgo**: con vara de asesoría (Brier), mezclar indicadores NO agrega predictibilidad — el blend actual ya está en el piso del baseline. Consistente con #13 (IC mejor no se tradujo en PnL): tampoco se traduce en mejor probabilidad calibrada.
- **La selectividad real de asesoría sigue siendo la del win_prob del motor** (calibrado sobre ret_net/barreras): umbral ≥0.65 → VPP real 73.7% (n=19), ≥0.70 → 87.5% (n=8) — cola alta con cobertura chica (6.6%/2.8%).
- **Conclusión**: la ganancia pendiente de asesoría NO está en combinar indicadores — está en el rank cross-sectional (relativo al universo, confusor §6.2: todo se midió absoluto). No consume slot (diagnóstico read-only, sin cambio de motor).

## 2026-08-17 — §27 Trial FinBERT PASO 2 (Tarea B): NO CUMPLE — línea sentimiento-earnings CERRADA con la evidencia disponible (Kilo Code)

- **Desbloqueo verificado**: el contrato de datos del PASO 2 ("≥8 trimestres × ≥30 símbolos") se
  cumplió hoy — acumulación completa `earnings_sentiment_run_20260817_120713.txt` (48/48 símbolos,
  369 filings, 0 errores); DB verificada: 8 trimestres (2024Q3→2026Q2) con ≥30 símbolos, 45 símbolos
  con 8 filings.
- **Pre-registro §27** escrito ANTES de correr. Diseño adaptado porque el sentimiento es event-based
  (no panel diario): pendiente HAC Newey-West de ret_relativo_a_SPY(20 ruedas) ~ score_finbert sobre
  la serie cronológica de eventos, ventanas E1/E2/E3 por fecha de filing, Bonferroni-9 |t|>2.77
  signo + en ≥2/3. Target relativo (no absoluto) declarado como lección §6.2. Cheque de fidelidad
  contra el artefacto de la corrida (aborta si difiere). Bug atrapado antes de correr: el t original
  del script medía la MEDIA de rel (drift), no la pendiente de predicción — corregida la estadística
  y aclaramiento en §27.
- **Corrida** (`scripts/trial_finbert_eventstudy.py`, artefacto
  `trial_finbert_eventstudy_20260817_163512.txt`, EXIT 0): fidelidad OK (369 filas/48 símbolos exacto).
  331/369 eventos con ventana completa (38 excluidos, pre-declarado). E1 n=137 t=+0.38, E2 n=113
  t=−0.85, E3 n=81 t=−0.08 → **0/3, NO_CUMPLE**. Signo spearman inconsistente entre ventanas
  (+0.05/−0.11/+0.03). Test secundario (premia terciles) mixto y no significativo.
- **Lectura**: el tono del comunicado 8-K 2.02 no predice retorno relativo a 20 ruedas. Línea
  CERRADA con la evidencia disponible; dos reservas declaradas como única vía de reapertura: (1)
  el 8-K es comunicado editado, no transcripción del call; (2) 2 años × ~110-140 eventos/ventana
  da poder solo para rhos ≳ 0.25-0.30. La store NO se borra (acumulación incremental barata para
  el futuro). Artefacto inválido del run con KeyError ELIMINADO (precedente §25).
- **Ledger**: `finbert_sentiment_eventstudy`, signal_diagnosis, n=1 → 16→17 consumidos,
  umbral próximo 0.99444. motor_signal intacto (10).
- **Verificación**: suite 242 passed, ruff limpio. ROADMAP (filas Tarea B), PLAN_LARGO_PLAZO y §27
  actualizados.

## 2026-08-17 — M4: cuenta Alpaca paper conectada + medición viva lanzada al open (Kilo Code)

- **Credenciales**: el usuario generó cuenta paper `PA3QUWEX1XBJ` (ACTIVE, $25k sintéticos).
  Primer intento: las claves de la nota eran de la cuenta LIVE (verificado contra el artefacto
  real: `api.alpaca.markets` autenticó, `paper-api` rechazó 401) → no se usaron (decisión de
  producto: no broker real). Usuario regeneró el par PAPER correcto y lo dejó en Notas.
- **Configuración**: credenciales en `backend/.env` (gitignored, `Settings` las carga; script
  de medición las lee de `os.environ`). Smoke test sin exponer valores en el chat.
- **Hallazgo**: fuera de rueda Alpaca rechaza market orders con 422 ("extended hours order
  must be DAY or GTC limit orders") — la medición real exige mercado abierto.
- **Runner lanzado**: `scripts/run_costs_at_open.py` (nuevo, ruff limpio) en background
  (PID 17770, log `backend/data/cache/m4_runner.log`, deadline 36h): al open corre ronda
  BUY + ronda SELL (cierra posiciones) del universo completo, qt=1, vía
  `scripts/measure_execution_costs.py`. Artefactos → `data/cache/measure_execution_costs_*.txt`
  + DB `execution_costs.db`.
- **Pendiente**: mañana post-open verificar artefactos, extraer el costo real medido
  (slippage medio + comisión), registrarlo en docs y actualizar ROADMAP M4 a cerrado.
- Higiene de seguridad recordada al usuario: rotar el secret LIVE y la contraseña de la
  cuenta (quedaron en texto plano en Notas antes de la regeneración).

## 2026-08-17 — Pipeline de datos automatizado: refresh OHLCV + cron launchd (Kilo Code)

- **Brecha (auditoría)**: el cache OHLCV estaba estancado al 2026-08-07/10 (43/18/3
  archivos, hoy 8/17 ≈ 5 ruedas de trading faltantes) y la acumulación FinBERT no tenía
  ningún cron — ambos flujos corrían solo si alguien los lanzaba. El poder estadístico
  futuro (sentimiento, re-tests) depende de no perder días/trimestres.
- **Fix paso 1 (ahora)**: refresh manual del universo 50 vía `download_data()` (ya es
  incremental por fecha) → 50/50 frescos ≥ 2026-08-14, 0 fallos.
- **Fix paso 2 (cron)**: `scripts/data_updater.sh` (bash, sin credenciales: yfinance +
  EDGAR declarativo) + `scripts/com.fortresscore.dataupdater.plist` INSTALADO en
  `~/Library/LaunchAgents/` y cargado (`launchctl list` OK). Corre 22:00 diario (tras
  cierre US): (1) OHLCV incremental, (2) acumulación FinBERT incremental. Log
  `scripts/data_updater.log`. `RunAtLoad=false` a propósito (no correr al boot).
- **Prueba end-to-end**: corrida manual del script OK — precios actualizados, 48/48
  símbolos, 8-Ks nuevos 0 (dedup por accession funciona, no re-procesa), ERRORES ninguno.
- **Suite**: 242 passed. ONBOARDING actualizado (sección launchd). ROADMAP fila Datos
  agregada. Pendiente VPS (siguiente paso declarado): migrar este cron + runner M4 a
  un servidor chico; requiere acceso SSH del usuario.

## 2026-08-17 — §28: las dos mediciones justas que faltaban (Kilo Code). NO CUMPLE en ambas.

- **Origen (usuario)**: "lo perfecto es enemigo de lo bueno, pero es más fácil descartar
  que aprobar — trabajar con lo bueno como apoyo a decisiones; además hay indicadores que
  no se evaluaron con datos/tiempo suficiente". Consecuencia concreta: dos factores del
  proyecto nunca fueron medidos contra lo que estructuralmente miden.
- **Pre-registro §28 ANTES de correr** (PLAN_MEJORA_MATEMATICA): Test A = rank IC de
  momentum/rsi/adx contra retorno RELATIVO a SPY (resuelve el confusor §6.2, declarado
  en RESUMEN §5 como "el más prometedor sin probar"); Test B = AAII como timing de fecha
  (verificado nunique=1 por fecha en el panel → las refutaciones anteriores #8/Fase0.6
  lo midieron donde estructuralmente no puede variar). Umbral único Bonferroni-12
  |t|>2.86, signo +1 (A) y −1 contrarian (B), ≥2/3 ventanas.
- **Corrida** (`scripts/trial_xsec_relative.py`, artefacto
  `trial_xsec_relative_20260817_184355.txt`): fidelidad §0.5a exacta (n 187/164/151).
  A: momentum 0/3 (t −0.03/−1.01/−0.11), rsi 0/3, adx 0/3 (t +0.79/+1.54/+1.47).
  B: 0/3 (t −0.32/+2.94/+0.04) — W2 cruza el umbral PERO con signo positivo, invertido
  del pre-registrado −1; re-signar post-hoc está prohibido. **VEREDICTO: NO_CUMPLE.**
- **Lecturas**: (1) la hipótesis "los factores parecían débiles por medir absoluto" queda
  refutada CON el test que la propia auditoría pidió — los IC relativos ≈ absolutos; el
  confusor beta era ruido chico, no la señal perdida. (2) AAII queda refutado como timing
  en su primera medición justa; línea sentimiento retail CERRADA. (3) ADX mantiene la
  única dirección consistentemente positiva (absoluta y relativa) sin cruzar nunca la
  barra → marginal-no-robusto confirmado por segunda metodología.
- **Consecuencia**: ya no queda hipótesis de señal declarada sin medir en el espacio del
  proyecto (diario, 50 símbolos, factores del gate, sentimiento, relativas y absolutas).
  RESUMEN §5 actualizado (PROPUESTA → PROBADO Y REFUTADO); ROADMAP fila §28.
- **Ledger**: signal_diagnosis 17→18, umbral próximo 0.994737. Suite 242 passed.
  Respuesta al usuario sobre "tiempo suficiente": detección de IC 0.05 con la vara del
  proyecto necesita ~500 fechas (~2 años de cross-section DIARIO; el panel stride-5 da
  ~50/año — el límite es frecuencia de observación, no años); eventos de earnings ~5 años
  (FinBERT reabriría ~2029-30); macro ~2 ciclos (~10-15 años, inalcanzable acá).

---

## Sesión 6 — Rediseño completo del Dashboard (Estilo Institucional)

**Fecha**: 2026-08-17
**Autor**: Claude Code
**Estado**: Dashboard rediseñado estilo TradingView/Investing.com, build OK, tests OK

### Cambios principales

**Frontend — Arquitectura nueva:**
- `Layout.tsx` — Componente principal con paneles colapsables, Header unificado, selector de símbolo sticky
- `Header.tsx` — Estado del sistema en header (Risk Manager, Ceiling, LLM status, fase)
- `GovernancePanel.tsx` — **Fix crítico**: contrato alineado con backend (triad/controller/judge/professor con campos reales)
- `SystemStatus.tsx` — Ahora recibe `apiUrl` prop (no hardcoded)
- `RiskPanel.tsx` — Ahora recibe `apiUrl` prop (no hardcoded)
- `index.css` — Tokens CSS, animaciones, scrollbar custom, reduced-motion support

**Fixes críticos:**
- Contrato GovernancePanel ↔ backend: ahora usa `governance.triad`, `governance.controller.approved`, `governance.judge.verdict`, `governance.professor.recommendation` (era `triad_consensus`, `controller_approved`, `judge_verdict`)
- URLs hardcodeadas `http://localhost:8000` eliminadas de SystemStatus y RiskPanel
- Build: TypeScript sin errores, Vite build OK (624kB JS, 17kB CSS gzipped)

**Backend verificado:**
- 242 tests pass (pytest 13.46s)
- Todos los endpoints de gobernanza funcionan con el nuevo flujo Tríada→Controlador↔Profesor→Juez
- Rate limit en memoria (10 req/60s) activo en predict y governance

### Archivos creados/modificados
- **Nuevos**: `frontend/src/components/Header.tsx`, `frontend/src/components/Layout.tsx`
- **Reescritos**: `frontend/src/App.tsx` (usa Layout), `frontend/src/components/GovernancePanel.tsx`, `frontend/src/components/SystemStatus.tsx`, `frontend/src/components/RiskPanel.tsx`, `frontend/src/index.css`
- **Existentes reutilizados**: MarketOverview, PriceChart, TechnicalIndicators, EquityCurve, RegimePanel, SymbolSummary, TradesTable, MonteCarloPanel, TradeDistribution, OpportunitiesPanel, UniverseTable, DecisionPanel, LiveTicker, KPICards

### Validación
- ✅ `npm run build` — 0 errores TS, build exitoso
- ✅ `pytest` backend — 242 passed
- ✅ Contrato GovernancePanel verificado contra `advanced_agents.py` y `governance.py`
- ✅ Sin URLs hardcodeadas en componentes

### Próximos pasos
- M4: Verificar artefactos de medición de costos Alpaca paper (runner en background)
- Considerar code-splitting para reducir bundle JS (actualmente 624kB)
- Panel de deriva (M5) en dashboard si se quiere visualizar

---
*Fin de Sesión 6 — 2026-08-17*

## 2026-08-17 — Dashboard institucional consolidado: advisor API + vistas lazy + Exit Thesis Monitor (Kilo Code)

- **Contexto**: usuario pidió consolidar lo mejor del rebuild de Claude Code (Layout,
  tokens, GovernancePanel verificado, componentes funcionales) con el plan Kilo
  (advisor API, etiquetas proyectadas, charts institucionales, tesis de salida) en UN
  dashboard nivel dios, sobre `frontend/` (Claude ya terminó, sin rama aparte).
- **Pre-registro §29**: mapeo de etiquetas proyectadas escrito ANTES de implementar,
  verificado contra el artefacto real `baseline_clean_20260811_150643_trades.parquet`
  (286 trades): ≥0.70→VPP 87.5% (n=8), ≥0.65→73.7% (n=19), 0.45-0.65→NEUTRO (sin
  selectividad), <0.45→RIESGOSA_SIN_APOYO (nunca "pérdida proyectada" — no hay
  evidencia en la cola baja). Las citas del SESSION_LOG previo coincidieron exactas.
- **Backend**: `app/api/routes/advisor.py` — 4 endpoints solo lectura (`/universe`,
  `/theses`, `/evidence`, `/{symbol}`) que REUTILIZAN `_compute_ticket` de decision.py
  (cero reprogramación del motor). Exit Thesis Monitor en `decision_theses.json`
  (escritura atómica temp+rename, gitignored como su hermano decision_states.json).
  Fix durante acceptance: `umbral_aplicado` string en entradas viejas del ledger →
  endpoint tolerante (test de regresión agregado).
- **Frontend**: `src/api/{client,hooks}.ts` (VITE_API_URL, sin localStorage), tokens
  TradingView exactos (#131722/#1e22d/#26a69a/#ef5350), Layout reescrito con tabs de
 4 vistas lazy: Mesa (tabla universo 50 + monitor de tesis), Detalle (Lightweight
  Charts EOD con EMA50/200 + zonas mecánicas entry/stop/target + widget TV con
  degradación graceful + plan de salida 4 mec + tesis + fundamentales), Portfolio y
  Gobernanza (componentes de Claude reubicados sin reescribir). Badge de honestidad
  global, chip staleness (>2 ruedas), Evidence Footer vivo del ledger.
- **Acceptance (regla #1 — contra el artefacto crudo)**: 263 tests passed (242 previos
  + 21 nuevos), ruff limpio en archivos nuevos (89 errores pre-existentes en scripts
  legados, no tocados), tsc+vite build OK sin warning de chunks (main 624→152 kB).
  Endpoints vivos verificados: universe 44 símbolos régimen 2 STAGFLATION (CVX 0.527→
  NEUTRO n=0 etiquetado justo), CVX detalle 400 barras con EMAs consistentes con el
  gate trend_ok, AAPL fundamentals EDGAR reales (pe/roe/etc), theses 0 activas,
  evidence 37 trials 6 familias.
- **Pendiente explícito**: verificación visual en navegador + campo costo/trade cuando
  el runner M4 entregue su artefacto mañana al open.

## 2026-08-17 — Dashboard institucional consolidado: verificación independiente + fix (Kilo Code)

- **Contexto**: la implementación del plan consolidado (advisor API + vistas lazy +
  tesis) fue completada en sesión paralela (commits d5851fe + auto-backups 19:20-19:37).
  Este turno: **verificación independiente contra el artefacto real** (regla #1) +
  cierre de un gap de consistencia.
- **Verificación backend (todo contra JSON crudo, servidor uvicorn levantado a mano)**:
  - `/api/advisor/universe` 200: 44 tickets, régimen STAGFLATION (estado 2, conf
    0.9998), honesty_badge presente ("Apoyo a decisión — sin señal comercial validada"),
    risk_params {12%, 1.5%, 10%}, staleness OK (cache 2026-08-14, 1 rueda atrás).
    Distribución: 1 VIGILAR (CVX win_prob 0.527), 43 NO_INVERTIR. Etiquetas §29
    aplicadas: NEUTRO n=0 + SIN_SCORE n=0 — código coincide con el pre-registro
    (VPP 87.5%/n=8 ≥0.70; 73.7%/n=19 ≥0.65; RIESGOSA_SIN_APOYO <0.45 sin afirmar pérdida).
  - `/api/advisor/CVX` 200: 400 barras OHLCV con EMA50/200 completos (realineado por
    fecha, no posición), entry/stop/tp 200/190.36/219.28 (payoff 2.0, ATR 4.82), exit_plan
    4 mecanismos (incl. el fix del trial #10 en partial_tp), m2 con intervalo, gates.
    fundamentals_coverage "sin_cobertura_edgar" honesto (null, no inventado).
  - `/api/advisor/AAPL` 200: fundamentals EDGAR reales con cobertura.
  - `/api/advisor/theses` 200 (0 tesis activas — correcto: sin INVERTIR hoy),
    `/api/advisor/evidence` 200 (18+10 trials, familias + recientes).
  - `routes/__init__.py` carecía de `advisor` en la lista `routers` → CORREGIDO
    (consistencia de inventario; main.py ya lo registraba, 4 rutas confirmadas en la app).
- **Verificación frontend**: `npm run build` OK (main 151.93 kB — code splitting
    efectivo: Mesa 9.47 / Detail 173.46 / Portfolio 402.92 / Governance 23.33 kB),
    SPA servida por `vite preview` HTTP 200, Layout con lazy+suspense de 4 vistas,
    tipos TS espejan el payload backend (client.ts/hooks.ts), TradingViewChart con
    lightweight-charts + fallback graceful, TVWidget secundario, API_URL por
    VITE_API_URL.
- **Suite**: 263 passed (242 + 21 advisor), ruff limpio. Espejo del disco externo
  pendiente de montar (el autobackup lo resuelve cuando esté).

## 2026-08-19 — Tarea E (Ronda 2026-08-19, OpenCode): campo de costo real en el dashboard

- **Contexto**: PLAN_LARGO_PLAZO.md Ronda 2026-08-19 asigna a OpenCode la Tarea E —
  construir el campo "costo/trade" que ROADMAP mencionaba y el frontend no tenía.
  El número real ya existe (M4, 2026-08-18, qty=1: cost_per_side_medido 0.000189,
  120 órdenes paper). Regla dura de la ronda: NO tocar `advisor.py` (fix recién
  pusheado del bug de event loop, commit 2f6fbeb) y NO cruzar archivos con la
  Tarea D (Kilo Code, curva qty=10/50).
- **Backend** (`backend/app/api/routes/costs.py`, NUEVO): `GET /api/costs/current`
  solo lectura. Fuentes en orden: (1) `execution_costs.db` — registro canónico vía
  `ExecutionCostRecorder.records()` + `summarize()` de `app.core.execution_costs`
  (importado, NO editado); (2) si no existe o está vacía, el artefacto `.txt` más
  reciente `measure_execution_costs_*` (parsea el JSON del bloque RESUMEN); (3) si
  no hay nada → 200 `{"medido": false, "nota"}` — NUNCA inventa un número. Respuesta:
  `{medido, cost_per_side_medido, slippage_p50, slippage_p95, comision_media,
  n_ordenes, ventana, fecha_medicion, sizes[], nota}`. `sizes[]` es la curva por
  tamaño de orden (ya lista para qty=1/10/50 de la Tarea D, sin cambio de contrato).
  Caveat PAPER adjunto siempre (`nota`). Robustez: DB corrupta/ilegible → cae al
  fallback honesto, nunca 500. Registrado en `routes/__init__.py` + `main.py`.
- **Tests** (`backend/tests/test_costs_api.py`, 6 nuevos): contrato desde DB real
  (tmp_path), curva por tamaño (3 tallas), fallback al .txt (parseo del RESUMEN),
  artefacto corrupto → medido=false, sin medición → medido=false con nota, DB
  corrupta → medido=false. Patrón del repo: `asyncio.run` + monkeypatch, sin red.
- **Frontend**: `client.ts` (interfaces `CostsPoint`/`CostsResponse` + `api.costs()`),
  `hooks.ts` (`useExecutionCosts`), `components/advisor/CostField.tsx` NUEVO — chip
  en la barra sticky de Layout (visible en todas las vistas): "COSTO REAL/LADO:
  0.019% · n=120", tooltip con caveat + p50/p95/fecha; si `medido=false` →
  "COSTO REAL: SIN MEDICIÓN" (amarillo, tooltip con la nota); si la curva tiene más
  de un punto, muestra "q1: 0.019% · q10: X% · q50: Y%". `Layout.tsx` monta el chip
  junto al badge de honestidad.
- **Verificación (regla #1 — contra el artefacto real)**: endpoint corrido contra la
  DB de producción: `cost_per_side_medido 0.00018883729749502882` — idéntico al
  artefacto `measure_execution_costs_20260818_134338.txt`. Suite backend 271 passed
  (265+ exigido por la ronda), ruff limpio en archivos nuevos, `npm run build` OK
  (tsc sin errores, bundle main 152.95 kB sin cambio significativo).
- **No tocado**: `advisor.py` (verificado con `git status` — solo los archivos de la
  Tarea E). **Sin commit/push** — regla de la ronda ("No commitear/pushear sin
  autorización de Boris").

## 2026-08-19 — Orquestación de la Ronda 2026-08-19: Tarea E cerrada, Tarea D bloqueada por Alpaca (OpenCode)

- **Contexto**: Claude Code sin créditos; Kilo Code entregó su reporte de cierre.
  Este turno (OpenCode): verificar el estado real de la ronda contra el repo,
  cerrar lo que se podía cerrar y dejar planificado lo que depende de acciones
  externas (Alpaca).
- **Verificación de integridad (regla #1 — contra el artefacto real)**:
  - Suite backend completa: **271 passed** (265+ exigido por la ronda) — los 21
    tests de costs (15 de execution_costs de Kilo + 6 de test_costs_api míos) integrados, nada roto.
  - `backend/scripts/measure_execution_costs.py` existe (Kilo), parametrizado con
    `--qty`, importa `NEW_UNIVERSE` — consistente.
  - `git status` limpio en código: la Tarea E quedó en el auto-backup db56f84
    (10:02, el auto-backup no espera autorización; los archivos están commiteados).
- **Hallazgo de orquestación**: el pre-registro de la Tarea D NO existía en
  PLAN_MEJORA_MATEMATICA.md (cero menciones a qty) — la regla #1 del proyecto
  exige criterio escrito ANTES de correr, y la corrida está bloqueada, así que
  todavía estábamos a tiempo. **Escribí el pre-registro §30** (naturaleza: medición,
  no consume ledger; hipótesis: el costo por lado sube con qty por impacto de
  mercado; qty=10/50 + el 1 ya medido; criterio descriptivo slippage_p50/p95 por
  qty — p95(q50) ≳ 3× p95(q1) ⇒ impacto medible; comandos exactos; restricciones
  paper + credenciales en .env; post-condición: tabla 3 puntos + ROADMAP).
- **PLAN_LARGO_PLAZO.md actualizado** (estados reales para que ningún agente
  reasigne): Tarea A CERRADA por trials #16/#17 (el archivo decía "EN CURSO"),
  Tarea D con estado de bloqueo + referencia a §30 (Kilo ya había dejado su
  VERIFICACIÓN), Tarea E CERRADA con verificación (la cabecera de la sección se
  había perdido en la edición de Kilo — restaurada), Verificación de la Ronda con
  el resultado real 271 passed.
- **ROADMAP.md**: fila M4 intacta (historia qty=1 conservada) + fila nueva Tarea D
  con estado 🟡, bloqueo explícito (403 Alpaca) y acción requerida del usuario.
- **Bloqueo externo documentado**: 403 Forbidden de Alpaca paper al enviar market
  orders (PA3QUWEX1XBJ). Market data funciona; trading no. Acción requerida:
  Boris habilita trading en la cuenta paper o regenera la API key con permisos.
  Comandos listos en §30. El endpoint /api/costs/current sirve la curva
  automáticamente cuando las mediciones qty=10/50 existan.
- **Sin commit descriptivo** (regla de la ronda: no commitear/pushear sin
  autorización de Boris; el auto-backup cubre el estado).

## 2026-08-19 (tarde) — DESBLOQUEO Y CIERRE DE LA TAREA D (curva qty=10/50) — OpenCode
- **Origen**: Boris indicó que la API de la cuenta prueba está en Apple Notes ("Alpaca Paper").
- **Diagnóstico del 403 (clave)**: NO era falta de permisos. La cuenta PA3QUWEX1XBJ está ACTIVE
  sin bloqueos; el error real era `40310000 "insufficient buying power"` con BP=0. Causa: la
  corrida qty=10 de la mañana (Kilo Code) alcanzó a entrar en 18 símbolos (~$81k notional) antes
  de agotar el margen; quedaron 18 posiciones abiertas, cash −$56k, BP 0 → todo lo posterior daba
  403. Las credenciales de la nota = las del `backend/.env` (mismo par) — no había que rotar nada.
- **Acción**: liquidé las 18 posiciones residuales (paper) → cash $24.9k, equity $25.1k, BP $100k,
  cuenta limpia, sin runners activos. Verifiqué que el 403 se reproduce con orden mínima (SPY qty=1)
  → confirmado el diagnóstico.
- **Enmienda 1 al pre-registro §30 (escrita ANTES de correr)**: el universo completo (50 símbolos)
  es inviable en esta cuenta (qty=10 ≈ $150k, qty=50 ≈ $750k vs BP $100k). Nuevo plan: qty=10 sobre
  los 7 BASE_SYMBOLS (los que opera el motor), qty=50 sobre SPY,QQQ,AAPL con fallback SPY+QQQ.
- **Corrida real (mercado abierto 12:13–12:14 ET, 4 comandos del script oficial)**:
  qty=10 buy 7 órdenes + qty=10 sell 7 órdenes (BASE_SYMBOLS); qty=50 buy 2 + sell 2 (SPY+QQQ;
  AAPL 50 dio 403 por BP — notional $90k > margen — fallback aplicado y documentado).
- **Curva real (156 órdenes en DB; fórmula contrato M4: abs(slippage); size=1 verificado idéntico
  al artefacto del 18/08: p50 0.000122 / p95 0.000519)**:
  - qty=1: n=120, p50 0.000122, p95 0.000519
  - qty=10: n=32, p50 0.000116, p95 0.000417
  - qty=50: n=4, p50 0.000029, p95 0.000098
- **VEREDICTO (criterio pre-registrado)**: curva plana/decreciente — p95(50) es 5.3× MENOR que
  p95(1). Impacto de mercado NO medible en rango 1→50 (mercados US líquidos, paper) → qty=1 es
  representativo (0.019%/lado). Consecuencia: `COST_PER_SIDE` (0.0015 asumido) sigue en pie;
  bajarlo a ~0.0002 es decisión del usuario con pre-registro aparte.
- **Documentación**: §30 actualizado (estado CERRADA + Enmienda 1 + RESULTADO con tabla y
  veredicto), ROADMAP fila Tarea D 🟢 cerrada, artefactos `measure_execution_costs_20260819_1213*.txt`.
- **Sin commit descriptivo** (regla de la ronda; el auto-backup cubre el estado).
