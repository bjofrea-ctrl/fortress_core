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
  sharpe_like: number
  max_drawdown_pct: number
  rsi14: number | null
  adx14: number | null
  stoch_k: number | null
  trend_bullish: boolean
  ema20: number
  ema50: number
  ema200: number
  bb_upper: number | null
  bb_lower: number | null
  momentum_12_1: number | null
  high_52w: number
  low_52w: number
  pct_from_high: number
  pct_from_low: number
  avg_volume: number
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
    return <div className="h-[500px] bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (!summary) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-[500px] flex items-center justify-center text-gray-400">
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

      {/* 52-week range */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Rango 52 sem</span>
          <span>{summary.pct_from_high.toFixed(1)}% del máx</span>
        </div>
        <div className="relative h-2 bg-dark-bg rounded-full">
          <div className="absolute h-full bg-gradient-to-r from-accent-red via-accent-yellow to-accent-green rounded-full" style={{ width: "100%" }}></div>
          <div
            className="absolute h-3 w-1 bg-white rounded-full -top-0.5"
            style={{ left: `${Math.max(0, Math.min(100, ((summary.last_price - summary.low_52w) / (summary.high_52w - summary.low_52w)) * 100))}%` }}
          ></div>
        </div>
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>${summary.low_52w.toFixed(2)}</span>
          <span>${summary.high_52w.toFixed(2)}</span>
        </div>
      </div>

      <div className="space-y-2 text-sm">
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
          <span className="text-gray-400">Volatilidad</span>
          <span className="font-mono text-accent-yellow">{summary.annual_volatility_pct.toFixed(2)}%</span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Sharpe-like</span>
          <span className={`font-mono ${summary.sharpe_like > 0.5 ? "text-accent-green" : "text-accent-yellow"}`}>
            {summary.sharpe_like.toFixed(3)}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Max Drawdown</span>
          <span className="font-mono text-accent-red">{summary.max_drawdown_pct.toFixed(2)}%</span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">RSI (14)</span>
          <span className={`font-mono ${(summary.rsi14 ?? 50) > 70 ? "text-accent-red" : (summary.rsi14 ?? 50) < 30 ? "text-accent-green" : "text-white"}`}>
            {summary.rsi14?.toFixed(1) ?? "N/A"}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Stoch %K</span>
          <span className={`font-mono ${(summary.stoch_k ?? 50) > 80 ? "text-accent-red" : (summary.stoch_k ?? 50) < 20 ? "text-accent-green" : "text-white"}`}>
            {summary.stoch_k?.toFixed(1) ?? "N/A"}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">ADX (14)</span>
          <span className={`font-mono ${(summary.adx14 ?? 0) > 25 ? "text-accent-green" : "text-gray-400"}`}>
            {summary.adx14?.toFixed(1) ?? "N/A"}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Momentum 12-1</span>
          <span className={`font-mono ${(summary.momentum_12_1 ?? 0) > 0 ? "text-accent-green" : "text-accent-red"}`}>
            {summary.momentum_12_1?.toFixed(1) ?? "N/A"}%
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">BB Upper/Lower</span>
          <span className="font-mono text-xs text-gray-300">
            ${summary.bb_upper?.toFixed(0) ?? "N/A"} / ${summary.bb_lower?.toFixed(0) ?? "N/A"}
          </span>
        </div>
        <div className="flex justify-between border-b border-dark-border pb-2">
          <span className="text-gray-400">Vol Promedio</span>
          <span className="font-mono text-xs text-gray-300">
            {(summary.avg_volume / 1e6).toFixed(1)}M
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