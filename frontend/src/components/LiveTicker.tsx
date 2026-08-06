import { useEffect, useState } from "react"

interface LiveTickerProps {
  apiUrl: string
  onSelectSymbol?: (symbol: string) => void
}

interface LiveSymbol {
  symbol: string
  price: number
  change: number
  change_pct: number
  previous_close: number
  market_cap: number
}

export default function LiveTicker({ apiUrl, onSelectSymbol }: LiveTickerProps) {
  const [symbols, setSymbols] = useState<LiveSymbol[]>([])
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = () => {
      fetch(`${apiUrl}/api/market/live/overview`)
        .then(r => r.json())
        .then(data => {
          if (data.symbols) {
            setSymbols(data.symbols)
            setLastUpdate(new Date())
          }
          setLoading(false)
        })
        .catch(() => setLoading(false))
    }

    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [apiUrl])

  if (loading && symbols.length === 0) {
    return (
      <div className="bg-dark-card border-b border-dark-border py-2 overflow-hidden">
        <div className="max-w-[1600px] mx-auto px-6">
          <div className="flex items-center gap-4 h-8">
            <div className="h-6 w-24 bg-dark-border rounded animate-pulse"></div>
            {[...Array(7)].map((_, i) => (
              <div key={i} className="h-6 w-32 bg-dark-border rounded animate-pulse"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (symbols.length === 0) {
    return null
  }

  return (
    <div className="bg-dark-card border-b border-dark-border py-2 overflow-hidden">
      <div className="max-w-[1600px] mx-auto px-6">
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-hide">
          {/* Live indicator */}
          <div className="flex items-center gap-1.5 mr-4 pr-4 border-r border-dark-border shrink-0">
            <span className="w-2 h-2 rounded-full bg-accent-red animate-pulse"></span>
            <span className="text-xs font-bold text-accent-red">EN VIVO</span>
          </div>

          {/* Ticker items */}
          {symbols.map((s) => (
            <button
              key={s.symbol}
              onClick={() => onSelectSymbol?.(s.symbol)}
              className="flex items-center gap-2 px-3 py-1 rounded hover:bg-dark-bg transition-colors shrink-0"
            >
              <span className="text-xs font-mono font-bold text-gray-300">{s.symbol}</span>
              <span className="text-xs font-mono text-white">${s.price.toFixed(2)}</span>
              <span className={`text-xs font-mono ${s.change >= 0 ? "text-accent-green" : "text-accent-red"}`}>
                {s.change >= 0 ? "▲" : "▼"} {Math.abs(s.change_pct).toFixed(2)}%
              </span>
            </button>
          ))}

          {/* Last update */}
          {lastUpdate && (
            <div className="ml-auto pl-4 border-l border-dark-border shrink-0 text-xs text-gray-500">
              {lastUpdate.toLocaleTimeString("es-CL")}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}