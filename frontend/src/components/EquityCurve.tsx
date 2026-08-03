import { useEffect, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"

interface EquityCurveProps {
  apiUrl: string
}

interface EquityPoint {
  date: string
  equity: number
  drawdown: number
}

export default function EquityCurve({ apiUrl }: EquityCurveProps) {
  const [data, setData] = useState<EquityPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<"equity" | "drawdown">("equity")

  useEffect(() => {
    fetch(`${apiUrl}/api/backtest/equity-curve`)
      .then(r => r.json())
      .then(data => {
        if (data.equity_curve) setData(data.equity_curve)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return <div className="h-80 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (data.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-80 flex items-center justify-center text-gray-400">
        Sin datos de equity. Ejecuta el backtest primero.
      </div>
    )
  }

  const initialEquity = 25000
  const minEquity = Math.min(...data.map(d => d.equity)) * 0.98
  const maxEquity = Math.max(...data.map(d => d.equity)) * 1.02

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Curva de Equity</h3>
        <div className="flex gap-2">
          <button
            onClick={() => setView("equity")}
            className={`px-3 py-1 rounded text-xs font-mono ${view === "equity" ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400"}`}
          >
            Equity
          </button>
          <button
            onClick={() => setView("drawdown")}
            className={`px-3 py-1 rounded text-xs font-mono ${view === "drawdown" ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400"}`}
          >
            Drawdown
          </button>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
          <XAxis
            dataKey="date"
            stroke="#6b7280"
            fontSize={10}
            tickFormatter={(v) => v.slice(5)}
          />
          <YAxis
            stroke="#6b7280"
            fontSize={10}
            domain={view === "equity" ? [minEquity, maxEquity] : ["auto", 0]}
            tickFormatter={(v) => view === "equity" ? `$${(v / 1000).toFixed(0)}k` : `${v.toFixed(1)}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#131824",
              border: "1px solid #1e2636",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(value: any) => view === "equity" ? [`$${value.toLocaleString()}`, "Equity"] : [`${value}%`, "Drawdown"]}
          />
          {view === "equity" ? (
            <>
              <ReferenceLine y={initialEquity} stroke="#6b7280" strokeDasharray="3 3" label={{ value: "Inicial $25k", fill: "#6b7280", fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="equity"
                stroke="#00d395"
                strokeWidth={2}
                dot={false}
              />
            </>
          ) : (
            <>
              <ReferenceLine y={-12} stroke="#ff4757" strokeDasharray="5 5" label={{ value: "Ceiling -12%", fill: "#ff4757", fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="drawdown"
                stroke="#ff4757"
                strokeWidth={2}
                dot={false}
                fill="url(#ddGradient)"
              />
              <defs>
                <linearGradient id="ddGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff4757" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#ff4757" stopOpacity={0} />
                </linearGradient>
              </defs>
            </>
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}