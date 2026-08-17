import { useEffect, useState } from "react"

interface SystemStatusData {
  risk_manager_active: boolean
  absolute_ceiling: number
  risk_per_trade: number
  violation_window_days: number
  ai_agents_enabled: boolean
  phase: string
}

export default function Header({ apiUrl }: { apiUrl: string }) {
  const [status, setStatus] = useState<SystemStatusData | null>(null)

  useEffect(() => {
    fetch(`${apiUrl}/api/system/status`)
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {})
  }, [apiUrl])

  return (
    <header className="border-b border-dark-border bg-dark-card sticky top-0 z-50">
      <div className="max-w-[1800px] mx-auto px-4 py-3 flex items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-2xl">🏛️</span>
          <div>
            <h1 className="text-xl font-bold text-accent-green">Fortress Core</h1>
            <p className="text-xs text-gray-400">Sistema de Trading Cuantitativo — Instrumento Diagnóstico Calibrado</p>
          </div>
        </div>

        {/* Live status badges */}
        <div className="flex items-center gap-3 flex-wrap">
          {status && (
            <>
              <span className="px-2 py-1 rounded text-xs font-mono bg-accent-green/20 text-accent-green border border-accent-green/30">
                Risk Manager: ON
              </span>
              <span className="px-2 py-1 rounded text-xs font-mono bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/30">
                Ceiling: {(status.absolute_ceiling * 100).toFixed(0)}%
              </span>
              <span className="px-2 py-1 rounded text-xs font-mono bg-dark-bg text-gray-400 border border-dark-border">
                Riesgo/trade: {(status.risk_per_trade * 100).toFixed(1)}%
              </span>
              <span className={`px-2 py-1 rounded text-xs font-mono ${status.ai_agents_enabled ? "bg-accent-blue/20 text-accent-blue border border-accent-blue/30" : "bg-gray-800/50 text-gray-400 border border-gray-600"}`}>
                {status.ai_agents_enabled ? "LLM: NIM ACTIVO" : "LLM: DETERMINISTA"}
              </span>
              <span className="px-2 py-1 rounded text-xs font-mono bg-dark-bg text-gray-400 border border-dark-border">
                {status.phase}
              </span>
            </>
          )}
          {!status && (
            <span className="px-2 py-1 rounded text-xs font-mono bg-dark-bg text-gray-400 animate-pulse">
              Cargando sistema...
            </span>
          )}
        </div>
      </div>
    </header>
  )
}