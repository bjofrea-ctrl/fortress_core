import { useEffect, useState } from "react"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from "recharts"

interface TradeDistributionProps {
  apiUrl: string
}

interface Trade {
  symbol: string
  pnl: number
  exit_reason: string
}

export default function TradeDistribution({ apiUrl }: TradeDistributionProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${apiUrl}/api/backtest/trades`)
      .then(r => r.json())
      .then(data => {
        if (data.trades) setTrades(data.trades)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return <div className="h-64 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (trades.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-64 flex items-center justify-center text-gray-400">
        Sin datos de trades.
      </div>
    )
  }

  // Create histogram bins
  const pnls = trades.map(t => t.pnl)
  const min = Math.min(...pnls)
  const max = Math.max(...pnls)
  const range = max - min
  const numBins = 15
  const binSize = range / numBins || 1

  const bins = Array.from({ length: numBins }, (_, i) => {
    const binMin = min + i * binSize
    const binMax = binMin + binSize
    const count = pnls.filter(p => p >= binMin && p < binMax).length
    return {
      range: `${binMin.toFixed(0)}`,
      count,
      isPositive: binMin >= 0,
    }
  })

  const wins = trades.filter(t => t.pnl > 0).length
  const losses = trades.filter(t => t.pnl <= 0).length
  const winRate = (wins / trades.length * 100).toFixed(1)

  // Count by exit reason
  const reasons: Record<string, number> = {}
  trades.forEach(t => {
    reasons[t.exit_reason] = (reasons[t.exit_reason] || 0) + 1
  })

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Distribución de Trades</h3>
        <div className="flex gap-3 text-xs">
          <span className="text-accent-green">Wins: {wins}</span>
          <span className="text-accent-red">Losses: {losses}</span>
          <span className="text-gray-400">Win Rate: {winRate}%</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={bins}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
          <XAxis dataKey="range" stroke="#6b7280" fontSize={9} tickFormatter={(v) => `$${v}`} />
          <YAxis stroke="#6b7280" fontSize={10} />
          <Tooltip
            contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "12px" }}
            formatter={(v: any) => [`${v} trades`, "Count"]}
            labelFormatter={(l) => `P&L: $${l}`}
          />
          <ReferenceLine x={0} stroke="#6b7280" />
          <Bar dataKey="count" name="Trades">
            {bins.map((entry, i) => (
              <Cell key={`cell-${i}`} fill={entry.isPositive ? "#00d395" : "#ff4757"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Exit reasons */}
      <div className="mt-4 pt-4 border-t border-dark-border">
        <p className="text-xs text-gray-400 mb-2">Razones de Salida</p>
        <div className="flex flex-wrap gap-2">
          {Object.entries(reasons).map(([reason, count]) => (
            <span key={reason} className="text-xs bg-dark-bg px-2 py-1 rounded font-mono">
              {reason}: <span className="text-accent-green">{count}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}