import { useEffect, useState } from "react"
import { ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts"

interface PriceChartProps {
  apiUrl: string
  symbol: string
}

interface PricePoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  ema20?: number
  ema50?: number
  ema200?: number
}

export default function PriceChart({ apiUrl, symbol }: PriceChartProps) {
  const [data, setData] = useState<PricePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [showEMAs, setShowEMAs] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`${apiUrl}/api/market/indicators/${symbol}?limit=300`)
      .then(r => r.json())
      .then(data => {
        if (data.data) setData(data.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl, symbol])

  if (loading) {
    return <div className="h-96 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (data.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-96 flex items-center justify-center text-gray-400">
        Sin datos para {symbol}
      </div>
    )
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-bold">{symbol}</h3>
          <span className="text-sm text-gray-400">Price & Indicators</span>
        </div>
        <button
          onClick={() => setShowEMAs(!showEMAs)}
          className={`px-3 py-1 rounded text-xs font-mono ${showEMAs ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400"}`}
        >
          EMAs
        </button>
      </div>

      <ResponsiveContainer width="100%" height={350}>
        <ComposedChart data={data}>
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
            domain={["auto", "auto"]}
            tickFormatter={(v) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#131824",
              border: "1px solid #1e2636",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            formatter={(value: any, name: string) => [`$${Number(value).toFixed(2)}`, name]}
          />
          <Legend wrapperStyle={{ fontSize: "11px" }} />
          <Line type="monotone" dataKey="close" stroke="#ffffff" strokeWidth={2} dot={false} name="Close" />
          {showEMAs && (
            <>
              <Line type="monotone" dataKey="ema20" stroke="#fbbf24" strokeWidth={1} dot={false} name="EMA 20" />
              <Line type="monotone" dataKey="ema50" stroke="#3b82f6" strokeWidth={1} dot={false} name="EMA 50" />
              <Line type="monotone" dataKey="ema200" stroke="#a855f7" strokeWidth={1} dot={false} name="EMA 200" />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}