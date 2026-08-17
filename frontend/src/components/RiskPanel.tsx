import { useEffect, useState } from "react"

interface RiskPanelProps {
  apiUrl: string
}

interface RiskData {
  status?: string
  current_equity: number
  current_drawdown_pct: number
  absolute_ceiling: number
  regime_state: number
  num_positions: number
  violations_60d: number
}

export default function RiskPanel({ apiUrl }: RiskPanelProps) {
  const [risk, setRisk] = useState<RiskData | null>(null)

  useEffect(() => {
    fetch(`${apiUrl}/api/risk/monitor`)
      .then(r => r.json())
      .then(setRisk)
  }, [apiUrl])

  if (!risk || risk.status === "no_data") {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 text-gray-400">
        Sin datos de riesgo aún.
      </div>
    )
  }

  const ddPct = (risk.current_drawdown_pct * 100).toFixed(2)
  const isWarning = risk.current_drawdown_pct <= -0.05
  const isCritical = risk.current_drawdown_pct <= -0.12

  return (
    <div
      className={`p-6 rounded-lg border-2 ${
        isCritical
          ? "bg-red-950 border-red-500"
          : isWarning
          ? "bg-yellow-950 border-yellow-500"
          : "bg-dark-card border-dark-border"
      }`}
    >
      <h3 className="text-lg font-bold mb-4">Monitor de Riesgo en Tiempo Real</h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-xs text-gray-400">Drawdown Actual</p>
          <p className={`text-2xl font-mono font-bold ${isCritical ? "text-red-400" : "text-white"}`}>
            {ddPct}%
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Ceiling Absoluto</p>
          <p className="text-2xl font-mono font-bold text-red-400">-{(risk.absolute_ceiling * 100).toFixed(0)}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Régimen</p>
          <p className="text-2xl font-mono font-bold">{risk.regime_state}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Violaciones (60d)</p>
          <p className="text-2xl font-mono font-bold">{risk.violations_60d}</p>
        </div>
      </div>

      <div className="mt-4">
        <div className="h-2 bg-dark-bg rounded-full overflow-hidden relative">
          <div className="absolute top-0 right-[12%] w-0.5 h-full bg-red-500"></div>
          <div
            className={`h-full transition-all ${
              isCritical ? "bg-red-500" : isWarning ? "bg-yellow-500" : "bg-accent-green"
            }`}
            style={{ width: `${Math.min(100, Math.abs(risk.current_drawdown_pct) / risk.absolute_ceiling * 100)}%` }}
          ></div>
        </div>
      </div>
    </div>
  )
}