import { useEffect, useState } from "react"

interface KPICardsProps {
  apiUrl: string
}

interface Metrics {
  cagr: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  calmar_ratio: number
  win_rate: number
  profit_factor: number
  total_trades: number
  deflated_sharpe: number
}

export default function KPICards({ apiUrl }: KPICardsProps) {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${apiUrl}/api/backtest/metrics`)
      .then(r => r.json())
      .then(data => {
        if (data.status !== "no_data") setMetrics(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-28 bg-dark-card rounded-lg animate-pulse"></div>
        ))}
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 text-center text-gray-400">
        No hay backtest ejecutado. Ejecuta <code className="text-accent-green">scripts/run_backtest.py</code> para ver métricas.
      </div>
    )
  }

  const cards = [
    {
      label: "CAGR",
      value: `${(metrics.cagr * 100).toFixed(2)}%`,
      color: metrics.cagr > 0 ? "text-accent-green" : "text-accent-red",
      icon: "📈",
    },
    {
      label: "Sharpe Ratio",
      value: metrics.sharpe_ratio.toFixed(3),
      color: metrics.sharpe_ratio > 0.3 ? "text-accent-green" : "text-accent-yellow",
      icon: "⚡",
    },
    {
      label: "Max Drawdown",
      value: `${(metrics.max_drawdown * 100).toFixed(2)}%`,
      color: metrics.max_drawdown > -0.06 ? "text-accent-green" : "text-accent-red",
      icon: "🛡️",
    },
    {
      label: "Profit Factor",
      value: metrics.profit_factor.toFixed(2),
      color: metrics.profit_factor > 1.2 ? "text-accent-green" : "text-accent-red",
      icon: "💰",
    },
    {
      label: "Total Trades",
      value: metrics.total_trades.toString(),
      color: "text-white",
      icon: "🔄",
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="bg-dark-card border border-dark-border rounded-lg p-4 hover:border-accent-green transition-colors">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">{card.label}</span>
            <span className="text-lg">{card.icon}</span>
          </div>
          <p className={`text-2xl font-mono font-bold ${card.color}`}>{card.value}</p>
        </div>
      ))}
    </div>
  )
}