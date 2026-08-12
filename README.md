# The Fortress Core — MVP Determinista

Sistema de trading cuantitativo con gestión de riesgo adaptativa, sin dependencias de IA en el loop crítico.

> **🔑 PARA CLINE / ASISTENTES IA**: Lee [`CLINE_CONTEXT.md`](./CLINE_CONTEXT.md) para recuperar el contexto completo de sesiones anteriores. Consulta [`SESSION_LOG.md`](./SESSION_LOG.md) para el historial de trabajo.

## Inicio Rápido
1. Copia `.env.example` a `.env`
2. Ejecuta: `docker-compose up --build -d`
3. Inicializa BD: `docker exec -it fortress_core-backend-1 python scripts/init_db.py`
4. Ejecuta backtest: `docker exec -it fortress_core-backend-1 python scripts/run_backtest.py`
5. Frontend: http://localhost:3000 | API Docs: http://localhost:8000/docs

## Arquitectura

```
fortress_core/
├── backend/
│   ├── app/
│   │   ├── core/          # Motor cuantitativo (indicadores, régimen, señales, riesgo)
│   │   ├── models/        # Modelos SQLAlchemy y persistencia
│   │   ├── api/           # Endpoints FastAPI
│   │   └── main.py        # Punto de entrada FastAPI
│   └── scripts/           # Scripts de inicialización y backtest
├── frontend/
│   └── src/               # Dashboard React + TypeScript
├── docker-compose.yml
└── .env.example
```

## Módulos Core

| Módulo | Responsabilidad |
|---|---|
| `indicators.py` | EMA, RSI, MACD, ATR, ADX, volumen relativo, momentum |
| `regime_classifier.py` | HMM de 4 estados (Goldilocks, Reflation, Stagflation, Deflation) |
| `signal_engine.py` | Scoring multifactor y generación de señales BUY |
| `adaptive_risk.py` | Stops por régimen, ceiling absoluto 12%, cooldown, sizing ATR |
| `risk_parity.py` | Asignación por contribución igual de riesgo con volatility targeting |
| `backtest_engine.py` | Simulación con costos, slippage, stops y métricas |

## Reglas de Riesgo

- **Ceiling absoluto**: 12% de drawdown máximo, jamás violable
- **Stops por régimen**: 5% (Goldilocks), 7% (Reflation), 8% (Stagflation), 3% (Deflation)
- **Riesgo por trade**: 1.5% del equity
- **Posición máxima**: 10% del equity
- **Cooldown**: 5-15 días según régimen tras violaciones

## API Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio |
| GET | `/api/system/status` | Configuración del sistema |
| GET | `/api/risk/monitor` | Monitor de riesgo en tiempo real |
| GET | `/api/backtest/results` | Resultados del último backtest |
| GET | `/api/backtest/metrics` | Métricas agregadas del backtest |
| GET | `/api/backtest/equity-curve` | Curva de equity |
| GET | `/api/backtest/trades` | Trades del backtest |
| GET | `/api/backtest/monte-carlo` | Simulaciones Monte Carlo |
| GET | `/api/market/symbols` | Símbolos disponibles |
| GET | `/api/market/prices/{symbol}` | Precios históricos |
| GET | `/api/market/indicators/{symbol}` | Indicadores técnicos |
| GET | `/api/market/summary/{symbol}` | Resumen de mercado |
| GET | `/api/market/overview` | Panorama del mercado |
| GET | `/api/market/live/overview` | Resumen en vivo |
| GET | `/api/market/live/{symbol}` | Estado en vivo de un símbolo |
| GET | `/api/predict/analyze/{symbol}` | Predicción (usa NVIDIA NIM) |
| GET | `/api/predict/universe` | Universo de predicción |
| GET | `/api/predict/macro-correlations` | Correlaciones macro |
| GET | `/api/governance/status` | Estado del sistema de gobernanza |
| GET | `/api/governance/analyze/{symbol}` | Análisis de gobernanza (usa NVIDIA NIM) |
| POST | `/api/governance/record-prediction` | Registrar predicción (API key) |
| GET | `/api/governance/professor/lessons` | Lecciones del PROFESSOR |
| GET | `/api/governance/professor/feedback` | Feedback del PROFESSOR |
| GET | `/api/governance/knowledge/search` | Búsqueda en repositorio de conocimiento |
| POST | `/api/governance/knowledge/add` | Agregar conocimiento (API key) |
| GET | `/api/governance/prompts` | Prompts del sistema |
| GET | `/api/opportunities/today` | Oportunidades del día |

## Stack

- **Backend**: Python 3.9, FastAPI, SQLAlchemy, pandas, numpy, scipy, scikit-learn, hmmlearn, yfinance
- **Frontend**: React 18, TypeScript, Vite, TailwindCSS, Recharts
- **Infra**: Docker, PostgreSQL 15