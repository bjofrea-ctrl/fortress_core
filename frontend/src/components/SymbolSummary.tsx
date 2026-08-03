import { useEffect, useState } from "react"

interface SymbolSummaryProps {
  apiUrl: string
  symbol: string
}

interface Summary {
  symbol: string
  last_price: number
  total_return_pct: number
  annual_return_pct: number
  annual_volatility_pct: number
  rsi14: number | null
  adx14: number | null
  trend_bullish: boolean
  ema20: number
  ema50: number
  ema200: number
  momentum_12_1: number | null
  date_range: string
  total_days: number
}

export default function SymbolSummary({ apiUrl, symbol }: SymbolSummaryProps) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`${apiUrl}/api/market/summary/${symbol}`)
      .then(r => r.json())
      .then(data => {
        if (!data.error) setSummary(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl, symbol])

  if (loading) {
    return <div className="h-96 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (!summary) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-96 flex items-center justify-center text-gray-400">
        Sin datos para {symbol}
      </div>
    )
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">{summary.symbol}</h3>
        <span className={`text-xs px-2 py-1 rounded ${summary.trend_bullish ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
          {summary.trend_bullish ? "📈 Alcista" : "📉 Bajista"}
        </span>
      </div>

      <div className="mb-4">
        <p className="text-xs text-gray-400">Precio Actual</p>
        <p className="text-3xl font-mono font-bold">${summary.last_price.toFixed(2)}</p>
      </div>

      <div className="space-y-3 text-sm">
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Retorno Total</span>
          <span className={`font-mono ${summary.total_return_pct > 0 ? "text-accent-green" : "text-accent-red"}`}>
            {summary.total_return_pct > 0 ? "+" : ""}{summary.total_return_pct.toFixed(2)}%
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Retorno Anual</span>
          <span className={`font-mono ${summary.annual_return_pct > 0 ? "text-accent-green" : "text-accent-red"}`}>
            {summary.annual_return_pct > 0 ? "+" : ""}{summary.annual_return_pct.toFixed(2)}%
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Volatilidad Anual</span>
          <span className="font-mono text-accent-yellow">{summary.annual_volatility_pct.toFixed(2)}%</span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">RSI (14)</span>
          <span className={`font-mono ${summary.rsi14 && summary.rsi14 > 70 ? "text-accent-red" : summary.rsi14 && summary.rsi14 < 30 ? "text-accent-green" : "text-white"}`}>
            {summary.rsi14?.toFixed(1) ?? "N/A"}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">ADX (14)</span>
          <span className={`font-mono ${summary.adx14 && summary.adx14 > 25 ? "text-accent-green" : "text-gray-400"}`}>
            {summary.adx14?.toFixed(1) ?? "N/A"}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Momentum 12-1</span>
          <span className={`font-mono ${summary.momentum_12_1 && summary.momentum_12_1 > 0 ? "text-accent-green" : "text-accent-red"}`}>
            {summary.momentum_12_1?.toFixed(1) ?? "N/A"}%
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">EMA 20 / 50 / 200</span>
          <span className="font-mono text-xs text-gray-300">
            ${summary.ema20.toFixed(0)} / ${summary.ema50.toFixed(0)} / ${summary.ema200.toFixed(0)}
          </span>
        </div>
        <div className="pt-2">
          <p className="text-xs text-gray-500">Rango: {summary.date_range}</p>
          <p className="text-xs text-gray-500">{summary.total_days} días de datos</p>
        </div>
      </div>
    </div>
  )
}