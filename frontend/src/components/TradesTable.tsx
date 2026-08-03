import { useEffect, useState } from "react"

interface TradesTableProps {
  apiUrl: string
}

interface Trade {
  symbol: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  shares: number
  pnl: number
  exit_reason: string
}

export default function TradesTable({ apiUrl }: TradesTableProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${apiUrl}/api/backtest/trades`)
      .then(r => r.json())
      .then(data => {
        if (data.trades) {
          setTrades(data.trades)
          setTotal(data.total || 0)
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return <div className="h-96 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (trades.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-96 flex items-center justify-center text-gray-400">
        Sin trades. Ejecuta el backtest primero.
      </div>
    )
  }

  const reasonColors: Record<string, string> = {
    "STOP_LOSS": "text-accent-red",
    "TAKE_PROFIT": "text-accent-green",
    "PARTIAL_TP": "text-accent-green",
    "TECHNICAL": "text-accent-yellow",
    "TRAILING": "text-blue-400",
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Trades Recientes</h3>
        <span className="text-xs text-gray-400">{total} trades totales</span>
      </div>

      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-dark-card">
            <tr className="text-left text-xs text-gray-400 border-b border-dark-border">
              <th className="pb-2 pr-3">Símbolo</th>
              <th className="pb-2 pr-3">Entrada</th>
              <th className="pb-2 pr-3">Salida</th>
              <th className="pb-2 pr-3 text-right">P. Entrada</th>
              <th className="pb-2 pr-3 text-right">P. Salida</th>
              <th className="pb-2 pr-3 text-right">Shares</th>
              <th className="pb-2 pr-3 text-right">P&L</th>
              <th className="pb-2">Razón</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice().reverse().map((t, i) => (
              <tr key={i} className="border-b border-dark-border/50 hover:bg-dark-bg/50">
                <td className="py-2 pr-3 font-mono font-bold">{t.symbol}</td>
                <td className="py-2 pr-3 text-gray-400 text-xs">{t.entry_date}</td>
                <td className="py-2 pr-3 text-gray-400 text-xs">{t.exit_date}</td>
                <td className="py-2 pr-3 text-right font-mono">${t.entry_price.toFixed(2)}</td>
                <td className="py-2 pr-3 text-right font-mono">${t.exit_price.toFixed(2)}</td>
                <td className="py-2 pr-3 text-right font-mono text-gray-400">{t.shares}</td>
                <td className={`py-2 pr-3 text-right font-mono font-bold ${t.pnl > 0 ? "text-accent-green" : "text-accent-red"}`}>
                  {t.pnl > 0 ? "+" : ""}${t.pnl.toFixed(2)}
                </td>
                <td className={`py-2 text-xs ${reasonColors[t.exit_reason] || "text-gray-400"}`}>
                  {t.exit_reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}