import { useEffect, useState } from "react"

interface TradesTableProps {
  apiUrl: string
}

interface Trade {
  origin: "backtest" | "paper"
  symbol: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number | null
  shares: number
  pnl: number | null
  pnl_r: number | null
  exit_reason: string
  status?: string
  signal_id?: string | null
}

export default function TradesTable({ apiUrl }: TradesTableProps) {
  const [trades, setTrades] = useState<Trade[]>([])
  const [total, setTotal] = useState(0)
  const [backtestTotal, setBacktestTotal] = useState(0)
  const [paperTotal, setPaperTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${apiUrl}/api/trades/combined`)
      .then(r => r.json())
      .then(data => {
        if (data.trades) {
          setTrades(data.trades)
          setTotal(data.total || 0)
          setBacktestTotal(data.backtest_total || 0)
          setPaperTotal(data.paper_total || 0)
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
        Sin trades. Ejecuta el backtest o esperá que el pipeline de paper trading genere operaciones reales.
      </div>
    )
  }

  const reasonColors: Record<string, string> = {
    "STOP_LOSS": "text-accent-red",
    "TAKE_PROFIT": "text-accent-green",
    "PARTIAL_TP": "text-accent-green",
    "TECHNICAL": "text-accent-yellow",
    "TRAILING": "text-blue-400",
    "OPEN": "text-blue-400",
    "RECONCILE": "text-accent-yellow",
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Historial de Trades</h3>
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-tv-dim"></span>
            {backtestTotal} backtest
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-accent-green"></span>
            {paperTotal} paper
          </span>
          <span>{total} totales</span>
        </div>
      </div>

      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-dark-card">
            <tr className="text-left text-xs text-gray-400 border-b border-dark-border">
              <th className="pb-2 pr-3">Origen</th>
              <th className="pb-2 pr-3">Símbolo</th>
              <th className="pb-2 pr-3">Entrada</th>
              <th className="pb-2 pr-3">Salida</th>
              <th className="pb-2 pr-3 text-right">P. Entrada</th>
              <th className="pb-2 pr-3 text-right">P. Salida</th>
              <th className="pb-2 pr-3 text-right">Shares</th>
              <th className="pb-2 pr-3 text-right">P&L</th>
              <th className="pb-2 pr-3 text-right">P&L %</th>
              <th className="pb-2">Razón</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => {
              const isOpen = t.origin === "paper" && t.status === "open"
              const showPnl = !isOpen && typeof t.pnl === "number" && typeof t.pnl_r === "number"
              return (
                <tr key={i} className="border-b border-dark-border/50 hover:bg-dark-bg/50">
                  <td className="py-2 pr-3">
                    <span
                      className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-bold ${
                        t.origin === "paper"
                          ? "bg-accent-green/20 text-accent-green"
                          : "bg-tv-dim/20 text-tv-dim"
                      }`}
                    >
                      {t.origin === "paper" ? "PAPER" : "BT"}
                    </span>
                  </td>
                  <td className="py-2 pr-3 font-mono font-bold">{t.symbol}</td>
                  <td className="py-2 pr-3 text-gray-400 text-xs">{t.entry_date}</td>
                  <td className="py-2 pr-3 text-gray-400 text-xs">
                    {isOpen ? <span className="text-blue-400">abierta</span> : t.exit_date}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono">${t.entry_price.toFixed(2)}</td>
                  <td className="py-2 pr-3 text-right font-mono">
                    {isOpen || t.exit_price === null ? <span className="text-gray-500">—</span> : `$${t.exit_price.toFixed(2)}`}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-gray-400">{t.shares}</td>
                  <td className={`py-2 pr-3 text-right font-mono font-bold ${!showPnl ? "text-gray-400" : t.pnl! > 0 ? "text-accent-green" : "text-accent-red"}`}>
                    {!showPnl ? "—" : `${t.pnl! > 0 ? "+" : ""}$${t.pnl!.toFixed(2)}`}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${!showPnl ? "text-gray-400" : t.pnl_r! > 0 ? "text-accent-green" : "text-accent-red"}`}>
                    {!showPnl ? "—" : `${t.pnl_r! > 0 ? "+" : ""}${(t.pnl_r! * 100).toFixed(2)}%`}
                  </td>
                  <td className={`py-2 text-xs ${reasonColors[t.exit_reason] || "text-gray-400"}`}>
                    {t.exit_reason}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}