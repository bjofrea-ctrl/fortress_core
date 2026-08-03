import { useEffect, useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell } from "recharts"

interface TechnicalIndicatorsProps {
  apiUrl: string
  symbol: string
}

interface IndicatorPoint {
  date: string
  close: number
  rsi14: number | null
  adx14: number | null
  macd: number | null
  macd_signal: number | null
  volume_ratio: number | null
  momentum_12_1: number | null
}

export default function TechnicalIndicators({ apiUrl, symbol }: TechnicalIndicatorsProps) {
  const [data, setData] = useState<IndicatorPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`${apiUrl}/api/market/indicators/${symbol}?limit=200`)
      .then(r => r.json())
      .then(data => {
        if (data.data) setData(data.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl, symbol])

  if (loading) {
    return <div className="h-80 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (data.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-80 flex items-center justify-center text-gray-400">
        Sin datos de indicadores para {symbol}
      </div>
    )
  }

  const latest = data[data.length - 1]

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Análisis Técnico — {symbol}</h3>
        <div className="flex gap-3 text-xs">
          {latest.rsi14 != null && (
            <span className="font-mono">
              RSI: <span className={latest.rsi14 > 70 ? "text-accent-red" : latest.rsi14 < 30 ? "text-accent-green" : "text-white"}>{latest.rsi14.toFixed(1)}</span>
            </span>
          )}
          {latest.adx14 != null && (
            <span className="font-mono">
              ADX: <span className={latest.adx14 > 25 ? "text-accent-green" : "text-gray-400"}>{latest.adx14.toFixed(1)}</span>
            </span>
          )}
          {latest.momentum_12_1 != null && (
            <span className="font-mono">
              Mom: <span className={latest.momentum_12_1 > 0 ? "text-accent-green" : "text-accent-red"}>{latest.momentum_12_1.toFixed(1)}%</span>
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* RSI Chart */}
        <div>
          <p className="text-xs text-gray-400 mb-2">RSI (14)</p>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
              <XAxis dataKey="date" stroke="#6b7280" fontSize={9} tickFormatter={(v) => v.slice(5)} />
              <YAxis stroke="#6b7280" fontSize={9} domain={[0, 100]} />
              <Tooltip contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "11px" }} />
              <ReferenceLine y={70} stroke="#ff4757" strokeDasharray="3 3" />
              <ReferenceLine y={30} stroke="#00d395" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="rsi14" stroke="#fbbf24" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* MACD Chart */}
        <div>
          <p className="text-xs text-gray-400 mb-2">MACD (12, 26, 9)</p>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
              <XAxis dataKey="date" stroke="#6b7280" fontSize={9} tickFormatter={(v) => v.slice(5)} />
              <YAxis stroke="#6b7280" fontSize={9} />
              <Tooltip contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "11px" }} />
              <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="macd" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="MACD" />
              <Line type="monotone" dataKey="macd_signal" stroke="#ff4757" strokeWidth={1} dot={false} name="Signal" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* ADX Chart */}
        <div>
          <p className="text-xs text-gray-400 mb-2">ADX (14) — Tendencia</p>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
              <XAxis dataKey="date" stroke="#6b7280" fontSize={9} tickFormatter={(v) => v.slice(5)} />
              <YAxis stroke="#6b7280" fontSize={9} />
              <Tooltip contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "11px" }} />
              <ReferenceLine y={25} stroke="#00d395" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="adx14" stroke="#a855f7" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Volume Ratio */}
        <div>
          <p className="text-xs text-gray-400 mb-2">Volume Ratio</p>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={data.slice(-60)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2636" />
              <XAxis dataKey="date" stroke="#6b7280" fontSize={9} tickFormatter={(v) => v.slice(5)} />
              <YAxis stroke="#6b7280" fontSize={9} />
              <Tooltip contentStyle={{ backgroundColor: "#131824", border: "1px solid #1e2636", fontSize: "11px" }} />
              <ReferenceLine y={1} stroke="#fbbf24" strokeDasharray="3 3" />
              <Bar dataKey="volume_ratio" name="Vol Ratio">
                {data.slice(-60).map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={(entry.volume_ratio ?? 1) > 1.5 ? "#00d395" : (entry.volume_ratio ?? 1) < 0.5 ? "#ff4757" : "#3b82f6"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}