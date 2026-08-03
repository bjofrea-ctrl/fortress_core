import { useEffect, useState } from "react"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"

interface MonteCarloPanelProps {
  apiUrl: string
}

interface MonteCarloData {
  mean: number
  p5: number
  p95: number
  prob_loss: number
}

export default function MonteCarloPanel({ apiUrl }: MonteCarloPanelProps) {
  const [mc, setMc] = useState<MonteCarloData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${apiUrl}/api/backtest/monte-carlo`)
      .then(r => r.json())
      .then(data => {
        if (data.mean !== undefined) setMc(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return <div className="h-96 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (!mc) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-96 flex items-center justify-center text-gray-400">
        Sin datos de Monte Carlo.
      </div>
    )
  }

  const chartData = [
    { name: "P5", value: mc.p5, fill: "#ff4757" },
    { name: "Media", value: mc.mean, fill: "#00d395" },
    { name: "P95", value: mc.p95, fill: "#3b82f6" },
  ]

  const probLossPct = (mc.prob_loss * 100).toFixed(2)

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-full">
      <h3 className="text-lg font-bold mb-4">Monte Carlo (1000 sims)</h3>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">P&L Medio</p>
          <p className={`text-xl font-mono font-bold ${mc.mean > 0 ? "text-accent-green" : "text-accent-red"}`}>
            ${mc.mean.toFixed(0)}
          </p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">Prob. Pérdida</p>
          <p className={`text-xl font-mono font-bold ${mc.prob_loss < 0.05 ? "text-accent-green" : "text-accent-yellow"}`}>
            {probLossPct}%
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">P5 (Peor caso)</p>
          <p className="text-lg font-mono font-bold text-accent-red">${mc.p5.toFixed(0)}</p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">P95 (Mejor caso)</p>
          <p className="text-lg font-mono font-bold text-blue-400">${mc.p95.toFixed(0)}</p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={150}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
          <XAxis dataKey="name" stroke="#6b7280" fontSize={11} />
          <YAxis stroke="#6b7280" fontSize={10} tickFormatter={(v) => `$${v.toFixed(0)}`} />
          <Tooltip
            contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "12px" }}
            formatter={(v: any) => [`$${v.toFixed(2)}`, "P&L"]}
          />
          <ReferenceLine y={0} stroke="#6b7280" />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}