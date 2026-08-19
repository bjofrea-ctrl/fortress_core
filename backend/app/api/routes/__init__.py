# Fortress Core - API routes

from app.api.routes import (
    advisor,
    backtest,
    costs,
    decision,
    decision_history,
    governance,
    live,
    market,
    opportunities,
    predict,
    ranking,
    risk,
    system,
)

# Router aggregation for main app
routers = [
    advisor.router,
    costs.router,
    decision.router,
    decision_history.router,
    ranking.router,
    backtest.router,
    governance.router,
    live.router,
    market.router,
    opportunities.router,
    predict.router,
    risk.router,
    system.router,
]
