import { useEffect, useState } from "react"
import { ComposedChart, Line, Bar, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from "recharts"

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
  bb_upper?: number | null
  bb_middle?: number | null
  bb_lower?: number | null
}

const TIMEFRAMES: Record<string, number> = {
  "1M": 22,
  "3M": 66,
  "6M": 132,
  "1Y": 252,
  "ALL": 500,
}

export default function PriceChart({ apiUrl, symbol }: PriceChartProps) {
  const [data, setData] = useState<PricePoint[]>([])
  const [loading, setLoading] = useState(true)
  const [showEMAs, setShowEMAs] = useState(true)
  const [showBB, setShowBB] = useState(false)
  const [timeframe, setTimeframe] = useState("6M")

  useEffect(() => {
    setLoading(true)
    const limit = TIMEFRAMES[timeframe] || 132
    fetch(`${apiUrl}/api/market/indicators/${symbol}?limit=${limit}`)
      .then(r => r.json())
      .then(data => {
        if (data.data) setData(data.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl, symbol, timeframe])

  if (loading) {
    return <div className="h-[500px] bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (data.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-[500px] flex items-center justify-center text-gray-400">
        Sin datos para {symbol}
      </div>
    )
  }

  const latest = data[data.length - 1]
  const prev = data.length > 1 ? data[data.length - 2] : latest
  const dayChange = latest.close - prev.close
  const dayChangePct = (dayChange / prev.close) * 100

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      {/* Header with price info */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-2xl font-bold">{symbol}</h3>
              <span className={`text-sm font-mono ${dayChange >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {dayChange >= 0 ? "▲" : "▼"} {dayChangePct >= 0 ? "+" : ""}{dayChangePct.toFixed(2)}%
              </span>
            </div>
            <p className="text-3xl font-mono font-bold">${latest.close.toFixed(2)}</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          {/* Timeframe selector */}
          <div className="flex gap-1">
            {Object.keys(TIMEFRAMES).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2 py-1 rounded text-xs font-mono ${timeframe === tf ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400 hover:text-white"}`}
              >
                {tf}
              </button>
            ))}
          </div>
          {/* Indicator toggles */}
          <div className="flex gap-1">
            <button onClick={() => setShowEMAs(!showEMAs)} className={`px-2 py-1 rounded text-xs ${showEMAs ? "bg-accent-green/20 text-accent-green" : "bg-dark-bg text-gray-400"}`}>EMAs</button>
            <button onClick={() => setShowBB(!showBB)} className={`px-2 py-1 rounded text-xs ${showBB ? "bg-blue-500/20 text-blue-400" : "bg-dark-bg text-gray-400"}`}>BB</button>
          </div>
        </div>
      </div>

      {/* Price chart */}
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
          <XAxis dataKey="date" stroke="#6b7280" fontSize={10} tickFormatter={(v) => v.slice(5)} />
          <YAxis stroke="#6b7280" fontSize={10} domain={["auto", "auto"]} tickFormatter={(v) => `$${v.toFixed(0)}`} />
          <Tooltip
            contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", borderRadius: "8px", fontSize: "12px" }}
            formatter={(value: any, name: string) => [`$${Number(value).toFixed(2)}`, name]}
          />
          <Legend wrapperStyle={{ fontSize: "11px" }} />

          {/* Bollinger Bands */}
          {showBB && (
            <>
              <Area type="monotone" dataKey="bb_upper" stroke="#3b82f6" strokeWidth={1} strokeOpacity={0.3} fill="#3b82f6" fillOpacity={0.05} dot={false} name="BB Upper" />
              <Area type="monotone" dataKey="bb_lower" stroke="#3b82f6" strokeWidth={1} strokeOpacity={0.3} fill="#3b82f6" fillOpacity={0.05} dot={false} name="BB Lower" />
              <Line type="monotone" dataKey="bb_middle" stroke="#3b82f6" strokeWidth={1} strokeDasharray="4 4" dot={false} name="BB Mid" />
            </>
          )}

          {/* Price line */}
          <Line type="monotone" dataKey="close" stroke="#ffffff" strokeWidth={2} dot={false} name="Close" />

          {/* EMAs */}
          {showEMAs && (
            <>
              <Line type="monotone" dataKey="ema20" stroke="#fbbf24" strokeWidth={1} dot={false} name="EMA 20" />
              <Line type="monotone" dataKey="ema50" stroke="#3b82f6" strokeWidth={1} dot={false} name="EMA 50" />
              <Line type="monotone" dataKey="ema200" stroke="#a855f7" strokeWidth={1} dot={false} name="EMA 200" />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Volume chart */}
      <div className="mt-2">
        <p className="text-xs text-gray-400 mb-1">Volume</p>
        <ResponsiveContainer width="100%" height={80}>
          <ComposedChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
            <XAxis dataKey="date" stroke="#6b7280" fontSize={9} tickFormatter={(v) => v.slice(5)} />
            <YAxis stroke="#6b7280" fontSize={9} tickFormatter={(v) => `${(v / 1e6).toFixed(0)}M`} />
            <Tooltip
              contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "11px" }}
              formatter={(v: any) => [`${(v / 1e6).toFixed(2)}M`, "Volume"]}
            />
            <Bar dataKey="volume" fill="#1e2636" name="Volume" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}