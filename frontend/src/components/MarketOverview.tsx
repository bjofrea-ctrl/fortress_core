import { useEffect, useState } from "react"

interface MarketOverviewProps {
  apiUrl: string
  onSelectSymbol?: (symbol: string) => void
}

interface SymbolOverview {
  symbol: string
  price: number
  total_return_pct: number
  return_30d_pct: number
  return_90d_pct: number
  volatility_pct: number
  high_52w: number
  low_52w: number
  range_position: number
  volume: number
}

/**
 * Resumen EOD del universo. MONTADO solo en Gobernanza (`views/GovernancePage.tsx`).
 *
 * Antes mostraba también el precio en grande, duplicado con `LiveTicker` (que se
 * monta globalmente en `Layout.tsx`): en la pantalla de Gobernanza convivían dos
 * precios distintos del mismo símbolo, uno EOD y otro en vivo, sin jerarquía.
 * Se sacó el precio de acá y quedó explícito qué ventana es esta
 * (pre-registro Slice 2, ítem B / auditoría G2-4).
 */
export default function MarketOverview({ apiUrl, onSelectSymbol }: MarketOverviewProps) {
  const [symbols, setSymbols] = useState<SymbolOverview[]>([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState<"total_return_pct" | "return_30d_pct" | "volatility_pct">("total_return_pct")

  useEffect(() => {
    fetch(`${apiUrl}/api/market/overview`)
      .then(r => r.json())
      .then(data => {
        if (data.symbols) setSymbols(data.symbols)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return <div className="h-64 bg-dark-card rounded-lg animate-pulse"></div>
  }

  const sorted = [...symbols].sort((a, b) => {
    if (sortBy === "volatility_pct") return b.volatility_pct - a.volatility_pct
    return b[sortBy] - a[sortBy]
  })

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-lg font-bold">📊 Market Overview</h3>
        <div className="flex gap-2">
          <button onClick={() => setSortBy("total_return_pct")} className={`px-2 py-1 rounded text-xs ${sortBy === "total_return_pct" ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400"}`}>Total</button>
          <button onClick={() => setSortBy("return_30d_pct")} className={`px-2 py-1 rounded text-xs ${sortBy === "return_30d_pct" ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400"}`}>30D</button>
          <button onClick={() => setSortBy("volatility_pct")} className={`px-2 py-1 rounded text-xs ${sortBy === "volatility_pct" ? "bg-accent-green text-dark-bg" : "bg-dark-bg text-gray-400"}`}>Vol</button>
        </div>
      </div>
      <p className="text-[11px] text-gray-500 mb-4">
        Cierres del cache EOD propio, sobre historia completa desde 2015: rendimientos,
        volatilidad y posición dentro del rango de 52 semanas. No es precio en vivo.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {sorted.map((s) => (
          <div
            key={s.symbol}
            onClick={() => onSelectSymbol?.(s.symbol)}
            className="bg-dark-bg rounded-lg p-3 cursor-pointer hover:border-accent-green border border-transparent transition-colors"
          >
            <div className="flex justify-between items-start mb-1">
              <span className="font-mono font-bold text-sm">{s.symbol}</span>
              <span className={`text-xs font-mono ${s.total_return_pct > 0 ? "text-accent-green" : "text-accent-red"}`}>
                {s.total_return_pct > 0 ? "+" : ""}{s.total_return_pct.toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between text-xs text-gray-400 mb-2">
              <span>30D: <span className={s.return_30d_pct > 0 ? "text-accent-green" : "text-accent-red"}>{s.return_30d_pct > 0 ? "+" : ""}{s.return_30d_pct.toFixed(1)}%</span></span>
              <span>Vol: <span className="text-accent-yellow">{s.volatility_pct.toFixed(0)}%</span></span>
            </div>
            {/* 52-week range bar */}
            <div className="relative h-1.5 bg-dark-border rounded-full">
              <div
                className="absolute h-full bg-gradient-to-r from-accent-red via-accent-yellow to-accent-green rounded-full"
                style={{ width: "100%" }}
              ></div>
              <div
                data-testid="range-marker"
                className="absolute h-3 w-1 bg-white rounded-full -top-0.5"
                style={{ left: `${s.range_position}%` }}
              ></div>
            </div>
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>${s.low_52w.toFixed(0)}</span>
              <span>${s.high_52w.toFixed(0)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}