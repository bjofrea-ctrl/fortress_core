import { useEffect, useState } from "react"

interface RegimePanelProps {
  apiUrl: string
}

interface RiskData {
  current_equity?: number
  current_drawdown_pct?: number
  absolute_ceiling: number
  regime_state?: number
  num_positions?: number
  violations_60d?: number
  status?: string
}

const REGIME_INFO: Record<number, { name: string; color: string; allocation: string; stop: string }> = {
  0: { name: "Goldilocks", color: "text-accent-green", allocation: "60% Equity / 15% Bonds / 15% Gold / 10% Cash", stop: "5%" },
  1: { name: "Reflation", color: "text-accent-yellow", allocation: "40% Equity / 10% Bonds / 40% Gold / 10% Cash", stop: "7%" },
  2: { name: "Stagflation", color: "text-accent-red", allocation: "15% Equity / 10% Bonds / 55% Gold / 20% Cash", stop: "8%" },
  3: { name: "Deflation", color: "text-blue-400", allocation: "10% Equity / 55% Bonds / 10% Gold / 25% Cash", stop: "3%" },
}

export default function RegimePanel({ apiUrl }: RegimePanelProps) {
  const [risk, setRisk] = useState<RiskData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${apiUrl}/api/risk/monitor`)
      .then(r => r.json())
      .then(data => {
        setRisk(data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [apiUrl])

  if (loading) {
    return <div className="h-80 bg-dark-card rounded-lg animate-pulse"></div>
  }

  const regimeState = risk?.regime_state ?? 0
  const regime = REGIME_INFO[regimeState] || REGIME_INFO[0]
  const ddPct = risk?.current_drawdown_pct ? (risk.current_drawdown_pct * 100).toFixed(2) : "0.00"
  const equity = risk?.current_equity?.toFixed(2) ?? "25000.00"
  const isWarning = risk?.current_drawdown_pct && risk.current_drawdown_pct <= -0.05
  const isCritical = risk?.current_drawdown_pct && risk.current_drawdown_pct <= -0.12

  return (
    <div className={`bg-dark-card border-2 rounded-lg p-6 h-full ${isCritical ? "border-accent-red" : isWarning ? "border-accent-yellow" : "border-dark-border"}`}>
      <h3 className="text-lg font-bold mb-4">Régimen & Riesgo</h3>

      {/* Regime */}
      <div className="mb-4">
        <p className="text-xs text-gray-400 mb-1">Régimen Macro Actual</p>
        <div className="flex items-center gap-2">
          <span className={`text-2xl font-bold ${regime.color}`}>{regime.name}</span>
          <span className="text-xs text-gray-500">(Estado {regimeState})</span>
        </div>
        <p className="text-xs text-gray-400 mt-1">{regime.allocation}</p>
        <p className="text-xs text-gray-400">Stop por régimen: <span className="text-accent-red font-mono">{regime.stop}</span></p>
      </div>

      {/* Risk metrics */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">Equity</p>
          <p className="text-lg font-mono font-bold text-white">${equity}</p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">Drawdown</p>
          <p className={`text-lg font-mono font-bold ${isCritical ? "text-accent-red" : isWarning ? "text-accent-yellow" : "text-accent-green"}`}>
            {ddPct}%
          </p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">Ceiling Absoluto</p>
          <p className="text-lg font-mono font-bold text-accent-red">-12.00%</p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3">
          <p className="text-xs text-gray-400">Violaciones (60d)</p>
          <p className="text-lg font-mono font-bold text-white">{risk?.violations_60d ?? 0}</p>
        </div>
      </div>

      {/* Drawdown bar */}
      <div className="mb-2">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Drawdown vs Ceiling</span>
          <span>{ddPct}% / -12.00%</span>
        </div>
        <div className="h-3 bg-dark-bg rounded-full overflow-hidden relative">
          <div className="absolute top-0 right-0 w-0.5 h-full bg-accent-red z-10"></div>
          <div
            className={`h-full transition-all ${isCritical ? "bg-accent-red" : isWarning ? "bg-accent-yellow" : "bg-accent-green"}`}
            style={{ width: `${Math.min(100, Math.abs(parseFloat(ddPct)) / 12 * 100)}%` }}
          ></div>
        </div>
      </div>

      {/* Positions */}
      <div className="mt-4 pt-4 border-t border-dark-border">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Posiciones Abiertas</span>
          <span className="font-mono font-bold">{risk?.num_positions ?? 0}</span>
        </div>
      </div>
    </div>
  )
}