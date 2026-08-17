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
    triad?: {
      bull: { score: number; verdict: string }
      bear: { score: number; verdict: string }
      contrarian: { score: number; verdict: string }
      consensus: number
      decision: string
      agreement: string
    }
    controller?: {
      approved: boolean
      decision: string
      confidence: number
      position_size_pct: number
      stop_loss_pct: number
      take_profit_pct: number
      risk_checks: Record<string, boolean>
      llm_model: string | null
    }
    judge?: {
      verdict?: string
      status?: string
      score: number
      reasoning: string
      overruled_agents: string[]
      risk_assessment: string
      confidence: number
      conditions: string[]
      llm_model: string | null
    }
    professor?: {
      recommendation: string
      lessons: number
      weight_adjustments: Record<string, number>
      teaching_summary: string
      knowledge_repo_stats: Record<string, number>
      llm_model: string | null
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
    regime_stops: Record<number, number>
  }
  judge?: {
    verdicts_count: number
  }
  nvidia_nim?: {
    available: boolean
    model: string
    models_available: string[]
    models: {
      triad: Record<string, string>
      governance: Record<string, string>
    }
  }
  knowledge_repo?: {
    total_entries: number
    by_domain: Record<string, number>
  }
  rag_memory?: {
    total_lessons: number
  }
  prompts?: {
    professor: string
    controller: string
    judge: string
  }
}

const DECISION_COLORS: Record<string, string> = {
  "COMPRAR_FUERTE": "text-accent-green",
  "COMPRAR": "text-accent-green",
  "MANTENER": "text-accent-yellow",
  "VENDER": "text-accent-red",
  "VENDER_FUERTE": "text-accent-red",
  "INVERTIR": "text-accent-green",
  "VIGILAR": "text-accent-yellow",
  "NO_INVERTIR": "text-accent-red",
}

const AGENT_COLORS = {
  bull: "text-accent-green",
  bear: "text-accent-red",
  contrarian: "text-accent-yellow",
}

const AGENT_LABELS = {
  bull: "🐂 BULL",
  bear: "🐻 BEAR",
  contrarian: "🔄 CONTRARIAN",
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
  const triad = governance?.triad
  const controller = governance?.controller
  const judge = governance?.judge
  const professor = governance?.professor
  const decisionColor = DECISION_COLORS[predictive?.decision ?? governance?.final_decision ?? ""] || "text-gray-300"

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Gobernanza Multi-Agente</h3>
        <span className="text-xs text-gray-500 font-mono">{data?.flow}</span>
      </div>

      {/* TRIAD Consensus */}
      {triad && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          {(["bull", "bear", "contrarian"] as const).map(agent => {
            const agentData = triad[agent]
            const colorClass = AGENT_COLORS[agent]
            return (
              <div key={agent} className="bg-dark-bg rounded-lg p-3 text-center">
                <p className="text-xs text-gray-400 mb-1">{AGENT_LABELS[agent]}</p>
                <p className="text-lg font-mono font-bold {colorClass}">
                  {(agentData.score * 100).toFixed(1)}%
                </p>
                <p className="text-xs text-gray-500 mt-1">{agentData.verdict}</p>
              </div>
            )
          })}
        </div>
      )}

      {/* TRIAD Summary */}
      {triad && (
        <div className="grid grid-cols-2 gap-3 mb-4 bg-dark-bg rounded-lg p-3">
          <div>
            <p className="text-xs text-gray-400">Consenso Tríada</p>
            <p className="font-mono font-bold text-white">{triad.consensus.toFixed(3)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Decisión</p>
            <p className={`font-mono font-bold ${DECISION_COLORS[triad.decision] || "text-white"}`}>{triad.decision}</p>
          </div>
          <div className="col-span-2">
            <p className="text-xs text-gray-400">Acuerdo</p>
            <p className="font-mono font-bold text-white">{triad.agreement}</p>
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
          <div className="flex items-center gap-2 flex-wrap mb-2">
            {/* Controller Badge */}
            {controller && (
              <span className={`px-3 py-1 rounded-md text-sm font-bold ${
                controller.approved
                  ? "bg-accent-green/20 text-accent-green border border-accent-green/30"
                  : "bg-accent-red/20 text-accent-red border border-accent-red/30"
              }`}>
                Controller: {controller.approved ? "APROBADO" : "RECHAZADO"}
              </span>
            )}

            {/* Professor Badge */}
            {professor && (
              <span className={`px-3 py-1 rounded-md text-sm font-bold ${
                professor.recommendation === "APPROVE"
                  ? "bg-accent-blue/20 text-accent-blue border border-accent-blue/30"
                  : "bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/30"
              }`}>
                Profesor: {professor.recommendation}
              </span>
            )}

            {/* Judge Badge */}
            {judge && (
              <span className={`px-3 py-1 rounded-md text-sm font-bold ${
                judge.verdict && judge.verdict.includes("COMPRAR")
                  ? "bg-accent-green/20 text-accent-green border border-accent-green/30"
                  : judge.verdict && judge.verdict.includes("VENDER")
                  ? "bg-accent-red/20 text-accent-red border border-accent-red/30"
                  : "bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/30"
              }`}>
                Juez: {judge.verdict ?? judge.status ?? "—"}
              </span>
            )}

            {/* Final Decision Badge */}
            <span className={`px-3 py-1 rounded-md text-sm font-bold ${
              governance.final_decision === "COMPRAR" || governance.final_decision === "COMPRAR_FUERTE" || governance.final_decision === "INVERTIR"
                ? "bg-accent-green/20 text-accent-green border border-accent-green/30"
                : governance.final_decision === "VENDER" || governance.final_decision === "VENDER_FUERTE" || governance.final_decision === "NO_INVERTIR"
                ? "bg-accent-red/20 text-accent-red border border-accent-red/30"
                : "bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/30"
            }`}>
              Final: {governance.final_decision}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-2">{governance.final_reason}</p>
          {judge?.overruled_agents && judge.overruled_agents.length > 0 && (
            <p className="text-xs text-accent-yellow mt-1">
              ⚠️ Juez sobrepasó: {judge.overruled_agents.join(", ")}
            </p>
          )}
        </div>
      )}

      {/* Controller Details */}
      {controller && (
        <details className="mb-4">
          <summary className="cursor-pointer text-sm font-bold text-gray-300 hover:text-white flex items-center gap-2">
            <span>🎛️</span> Controlador (Determinista)
          </summary>
          <div className="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Posición %</p>
              <p className="font-mono text-white">{controller.position_size_pct.toFixed(1)}%</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Stop Loss %</p>
              <p className="font-mono text-accent-red">{controller.stop_loss_pct.toFixed(1)}%</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Take Profit %</p>
              <p className="font-mono text-accent-green">{controller.take_profit_pct.toFixed(1)}%</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Confianza</p>
              <p className="font-mono text-white">{(controller.confidence * 100).toFixed(0)}%</p>
            </div>
            <div className="col-span-4 bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400 mb-2">Risk Checks</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(controller.risk_checks).map(([check, passed]) => (
                  <span key={check} className={`px-2 py-1 rounded text-xs font-mono ${passed ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
                    {check}: {passed ? "✓" : "✗"}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </details>
      )}

      {/* Judge Details */}
      {judge && judge.verdict && (
        <details className="mb-4">
          <summary className="cursor-pointer text-sm font-bold text-gray-300 hover:text-white flex items-center gap-2">
            <span>⚖️</span> Juez (Determinista)
          </summary>
          <div className="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Score</p>
              <p className="font-mono text-white">{judge.score.toFixed(3)}</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Riesgo</p>
              <p className={`font-mono ${judge.risk_assessment === "ALTO" ? "text-accent-red" : judge.risk_assessment === "MEDIO" ? "text-accent-yellow" : "text-accent-green"}`}>
                {judge.risk_assessment}
              </p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Confianza</p>
              <p className="font-mono text-white">{(judge.confidence * 100).toFixed(0)}%</p>
            </div>
            <div className="col-span-4 bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400 mb-1">Razonamiento</p>
              <p className="text-gray-300 text-sm">{judge.reasoning}</p>
            </div>
            {judge.conditions.length > 0 && (
              <div className="col-span-4 bg-dark-bg rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">Condiciones</p>
                <div className="flex flex-wrap gap-2">
                  {judge.conditions.map((c, i) => (
                    <span key={i} className="px-2 py-1 rounded bg-dark-card text-xs text-gray-400">{c}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </details>
      )}

      {/* Professor Details */}
      {professor && (
        <details className="mb-4">
          <summary className="cursor-pointer text-sm font-bold text-gray-300 hover:text-white flex items-center gap-2">
            <span>🎓</span> Profesor {professor.llm_model && <span className="text-xs text-accent-blue">({professor.llm_model})</span>}
          </summary>
          <div className="mt-3 grid grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Lecciones</p>
              <p className="font-mono text-white">{professor.lessons}</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Entradas RAG</p>
              <p className="font-mono text-white">{professor.knowledge_repo_stats.total_entries ?? 0}</p>
            </div>
            <div className="bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400">Recomendación</p>
              <p className={`font-mono ${professor.recommendation === "APPROVE" ? "text-accent-green" : "text-accent-red"}`}>
                {professor.recommendation}
              </p>
            </div>
            <div className="col-span-3 bg-dark-bg rounded-lg p-3">
              <p className="text-xs text-gray-400 mb-1">Resumen de Enseñanza</p>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{professor.teaching_summary}</pre>
            </div>
          </div>
        </details>
      )}

      {/* System Status */}
      {status && (
        <details className="mb-4">
          <summary className="cursor-pointer text-sm font-bold text-gray-300 hover:text-white flex items-center gap-2">
            <span>📊</span> Estado del Sistema
          </summary>
          <div className="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-3">
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
        </details>
      )}
    </div>
  )
}