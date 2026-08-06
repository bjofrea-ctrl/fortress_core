import { useEffect, useState } from "react"

interface GovernancePanelProps {
  apiUrl: string
  symbol: string
}

interface GovernanceData {
  symbol: string
  flow: string
  predictive?: {
    composite_score: number
    decision: string
    prob_up_short: number
    prob_up_medium: number
    prob_up_long: number
  }
  governance?: {
    final_decision: string
    final_reason: string
    controller_approved: boolean
    controller_decision: string
    judge_verdict: string
    judge_overrides: string[]
    triad_consensus?: {
      bull_score: number
      bear_score: number
      contrarian_score: number
      agreement: string
    }
  }
}

interface GovernanceStatus {
  flow: string
  professor?: {
    lessons_count: number
    teaching_summary: string
  }
  controller?: {
    absolute_ceiling: number
    risk_per_trade: number
    max_position: number
  }
  judge?: {
    verdicts_count: number
  }
  nvidia_nim?: {
    available: boolean
    model: string
  }
  knowledge_repo?: {
    total_entries: number
    by_domain: Record<string, number>
  }
}

const DECISION_COLORS: Record<string, string> = {
  "COMPRAR_FUERTE": "text-accent-green",
  "COMPRAR": "text-accent-green",
  "MANTENER": "text-accent-yellow",
  "VENDER": "text-accent-red",
  "VENDER_FUERTE": "text-accent-red",
}

export default function GovernancePanel({ apiUrl, symbol }: GovernancePanelProps) {
  const [data, setData] = useState<GovernanceData | null>(null)
  const [status, setStatus] = useState<GovernanceStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)

    // Fetch governance status
    fetch(`${apiUrl}/api/governance/status`)
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {})

    // Fetch governance analysis for symbol
    fetch(`${apiUrl}/api/governance/analyze/${symbol}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setData(data)
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [apiUrl, symbol])

  if (loading) {
    return <div className="h-80 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (error) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <h3 className="text-lg font-bold mb-2">Gobernanza Multi-Agente</h3>
        <p className="text-sm text-accent-red">Error al cargar: {error}</p>
      </div>
    )
  }

  const predictive = data?.predictive
  const governance = data?.governance
  const decisionColor = DECISION_COLORS[predictive?.decision ?? ""] || "text-gray-300"

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Gobernanza Multi-Agente</h3>
        <span className="text-xs text-gray-500 font-mono">{data?.flow}</span>
      </div>

      {/* TRIAD Consensus */}
      {governance?.triad_consensus && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-dark-bg rounded-lg p-3 text-center">
            <p className="text-xs text-gray-400 mb-1">🐂 BULL</p>
            <p className="text-lg font-mono font-bold text-accent-green">
              {(governance.triad_consensus.bull_score * 100).toFixed(1)}%
            </p>
          </div>
          <div className="bg-dark-bg rounded-lg p-3 text-center">
            <p className="text-xs text-gray-400 mb-1">🐻 BEAR</p>
            <p className="text-lg font-mono font-bold text-accent-red">
              {(governance.triad_consensus.bear_score * 100).toFixed(1)}%
            </p>
          </div>
          <div className="bg-dark-bg rounded-lg p-3 text-center">
            <p className="text-xs text-gray-400 mb-1">🔄 CONTRARIAN</p>
            <p className="text-lg font-mono font-bold text-accent-yellow">
              {(governance.triad_consensus.contrarian_score * 100).toFixed(1)}%
            </p>
          </div>
        </div>
      )}

      {/* Predictive Score */}
      {predictive && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div className="bg-dark-bg rounded-lg p-3">
            <p className="text-xs text-gray-400">Score Compuesto</p>
            <p className={`text-lg font-mono font-bold ${predictive.composite_score >= 0 ? "text-accent-green" : "text-accent-red"}`}>
              {predictive.composite_score >= 0 ? "+" : ""}{predictive.composite_score.toFixed(3)}
            </p>
          </div>
          <div className="bg-dark-bg rounded-lg p-3">
            <p className="text-xs text-gray-400">Decisión</p>
            <p className={`text-lg font-mono font-bold ${decisionColor}`}>{predictive.decision}</p>
          </div>
          <div className="bg-dark-bg rounded-lg p-3">
            <p className="text-xs text-gray-400">Prob. Subida (1-30d)</p>
            <p className="text-lg font-mono font-bold text-white">{(predictive.prob_up_short * 100).toFixed(1)}%</p>
          </div>
          <div className="bg-dark-bg rounded-lg p-3">
            <p className="text-xs text-gray-400">Prob. Subida (1-6m)</p>
            <p className="text-lg font-mono font-bold text-white">{(predictive.prob_up_medium * 100).toFixed(1)}%</p>
          </div>
        </div>
      )}

      {/* Governance Flow */}
      {governance && (
        <div className="mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-3 py-1 rounded-md text-sm font-bold ${
              governance.controller_approved
                ? "bg-accent-green/20 text-accent-green"
                : "bg-accent-red/20 text-accent-red"
            }`}>
              Controller: {governance.controller_approved ? "APROBADO" : "RECHAZADO"}
            </span>
            <span className="px-3 py-1 rounded-md text-sm font-bold bg-dark-bg text-gray-300">
              Juez: {governance.judge_verdict}
            </span>
            <span className={`px-3 py-1 rounded-md text-sm font-bold ${
              governance.final_decision === "COMPRAR" || governance.final_decision === "COMPRAR_FUERTE"
                ? "bg-accent-green/20 text-accent-green"
                : governance.final_decision === "VENDER" || governance.final_decision === "VENDER_FUERTE"
                ? "bg-accent-red/20 text-accent-red"
                : "bg-accent-yellow/20 text-accent-yellow"
            }`}>
              Final: {governance.final_decision}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-2">{governance.final_reason}</p>
          {governance.judge_overrides && governance.judge_overrides.length > 0 && (
            <p className="text-xs text-accent-yellow mt-1">
              ⚠️ Juez sobrepasó: {governance.judge_overrides.join(", ")}
            </p>
          )}
        </div>
      )}

      {/* System Status */}
      {status && (
        <div className="pt-4 border-t border-dark-border">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Lecciones Profesor</p>
              <p className="text-lg font-mono font-bold text-white">{status.professor?.lessons_count ?? 0}</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Veredictos Juez</p>
              <p className="text-lg font-mono font-bold text-white">{status.judge?.verdicts_count ?? 0}</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Conocimiento RAG</p>
              <p className="text-lg font-mono font-bold text-white">{status.knowledge_repo?.total_entries ?? 0} entradas</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">NVIDIA NIM</p>
              <p className={`text-lg font-mono font-bold ${status.nvidia_nim?.available ? "text-accent-green" : "text-gray-500"}`}>
                {status.nvidia_nim?.available ? "ACTIVO" : "DETERMINISTA"}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}