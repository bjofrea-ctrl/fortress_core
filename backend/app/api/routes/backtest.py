from fastapi import APIRouter
import json
import os

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

RESULTS_FILE = "data/backtest_results.json"


@router.get("/results")
async def get_backtest_results():
    """Retorna los resultados del último backtest ejecutado."""
    if not os.path.exists(RESULTS_FILE):
        return {"status": "no_data", "message": "No hay backtest ejecutado. Ejecuta scripts/run_backtest.py"}

    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)

    return data


@router.get("/metrics")
async def get_backtest_metrics():
    """Retorna solo las métricas del backtest."""
    if not os.path.exists(RESULTS_FILE):
        return {"status": "no_data"}

    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)

    return data.get("metrics", {})


@router.get("/equity-curve")
async def get_equity_curve():
    """Retorna la curva de equity del backtest."""
    if not os.path.exists(RESULTS_FILE):
        return {"status": "no_data", "equity_curve": []}

    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)

    curve = data.get("equity_curve", [])
    # Sample to max 300 points for frontend performance
    if len(curve) > 300:
        step = len(curve) // 300
        curve = curve[::step]

    # Format for charts
    formatted = []
    for point in curve:
        formatted.append({
            "date": point["date"][:10] if isinstance(point["date"], str) else point["date"].strftime("%Y-%m-%d"),
            "equity": round(point["equity"], 2),
            "drawdown": round(point["drawdown_pct"] * 100, 2),
        })

    return {"equity_curve": formatted}


@router.get("/trades")
async def get_trades():
    """Retorna los trades del backtest."""
    if not os.path.exists(RESULTS_FILE):
        return {"status": "no_data", "trades": []}

    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)

    trades = data.get("trades", [])
    # Return last 50 trades for the table
    recent = trades[-50:] if len(trades) > 50 else trades

    formatted = []
    for t in recent:
        formatted.append({
            "symbol": t["symbol"],
            "entry_date": t["entry_date"][:10] if isinstance(t["entry_date"], str) else t["entry_date"].strftime("%Y-%m-%d"),
            "exit_date": t["exit_date"][:10] if isinstance(t["exit_date"], str) else t["exit_date"].strftime("%Y-%m-%d"),
            "entry_price": round(t["entry_price"], 2),
            "exit_price": round(t["exit_price"], 2),
            "shares": t["shares"],
            "pnl": round(t["pnl"], 2),
            "exit_reason": t["exit_reason"],
        })

    return {"trades": formatted, "total": len(trades)}


@router.get("/monte-carlo")
async def get_monte_carlo():
    """Retorna los resultados de Monte Carlo."""
    if not os.path.exists(RESULTS_FILE):
        return {"status": "no_data"}

    with open(RESULTS_FILE, "r") as f:
        data = json.load(f)

    return data.get("monte_carlo", {})