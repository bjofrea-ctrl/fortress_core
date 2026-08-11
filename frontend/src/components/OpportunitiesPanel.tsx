import { useEffect, useState } from "react"

interface OpportunitiesPanelProps {
  apiUrl: string
}

interface Opportunity {
  symbol: string
  score: number
  win_prob: number | null
  factors: Record<string, number>
  gates: {
    trend_ok: boolean
    adx: number
    rsi: number
    volume_ratio: number
  }
  entry_price: number
  stop_loss: number
  take_profit: number
  payoff_ratio: number
  atr: number
  g2_score: number | null
  exit_plan: {
    partial_tp: { trigger: string; action: string }
    trailing_stop: { trigger: string; action: string }
    technical: { trigger: string; action: string }
    regime_stop: { trigger: string; action: string }
  }
}

interface OpportunitiesData {
  as_of: string
  regime: { state: number; name: string; confidence: number }
  blocked_reason: string | null
  min_score: number
  opportunities: Opportunity[]
  concentration: {
    alerts: { pair: string; tail_dependence_lower: number; tail_dependence_upper: number }[]
    n_pairs_analyzed: number
  }
  track_record: {
    sufficient: boolean
    n: number
    win_rate: number | null
    brier: number | null
  }
  evaluation: { evaluated: number; remaining: number }
  suggestions_recorded_today: number
}

const FACTOR_LABELS: Record<string, string> = {
  momentum: "Momentum",
  trend: "Tendencia",
  rsi: "RSI",
  adx: "ADX",
}

export default function OpportunitiesPanel({ apiUrl }: OpportunitiesPanelProps) {
  const [data, setData] = useState<OpportunitiesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`${apiUrl}/api/opportunities/today`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message)
        setLoading(false)
      })
  }, [apiUrl])

  if (loading) {
    return <div className="h-80 bg-dark-card rounded-lg animate-pulse"></div>
  }

  if (error || !data) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6">
        <h3 className="text-lg font-bold mb-2">Oportunidades de Hoy</h3>
        <p className="text-sm text-accent-red">Error al cargar: {error}</p>
      </div>
    )
  }

  const tr = data.track_record
  const hasConcentration = data.concentration.alerts.length > 0

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-lg font-bold">Oportunidades de Hoy</h3>
        <span className="text-xs text-gray-500 font-mono">{data.as_of}</span>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        Régimen: <span className="text-accent-yellow">{data.regime.name}</span> (estado {data.regime.state}, confianza {(data.regime.confidence * 100).toFixed(0)}%) · Umbral mínimo: {data.min_score.toFixed(2)} · Sin top-5: todos los que pasan el gate
      </p>

      {/* Bloqueo explicado (principio 6) */}
      {data.blocked_reason && (
        <div className="bg-dark-bg border border-accent-yellow/40 rounded-lg p-4 mb-4">
          <p className="text-sm text-accent-yellow font-bold mb-1">Sin sugerencias hoy — esto es una decisión, no un fallo</p>
          <p className="text-sm text-gray-300">{data.blocked_reason}</p>
        </div>
      )}

      {/* Concentración de cola (principio 4) */}
      {hasConcentration && (
        <div className="bg-accent-red/10 border border-accent-red/40 rounded-lg p-4 mb-4">
          <p className="text-sm text-accent-red font-bold mb-1">⚠️ Los candidatos se mueven juntos</p>
          <p className="text-xs text-gray-300">
            {data.concentration.alerts.length} par(es) con dependencia de cola ALTA entre los candidatos de hoy —
            el sizing por activo (Kelly) no los descuenta:
          </p>
          <div className="flex gap-2 mt-2 flex-wrap">
            {data.concentration.alerts.map((a) => (
              <span key={a.pair} className="px-2 py-1 rounded bg-dark-bg text-xs font-mono text-accent-red">
                {a.pair} (cola baja {(a.tail_dependence_lower * 100).toFixed(0)}%)
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Track record real (principio 5) */}
      <div className="bg-dark-bg rounded-lg p-3 mb-4 flex items-center gap-6">
        <div>
          <p className="text-xs text-gray-400">Sugerencias evaluadas (20d)</p>
          <p className="text-lg font-mono font-bold text-white">{tr.n}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Win rate real</p>
          <p className="text-lg font-mono font-bold text-white">
            {tr.sufficient ? `${(tr.win_rate! * 100).toFixed(1)}%` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Brier</p>
          <p className="text-lg font-mono font-bold text-white">
            {tr.sufficient && tr.brier !== null ? tr.brier.toFixed(3) : "—"}
          </p>
        </div>
        {!tr.sufficient && (
          <p className="text-xs text-gray-500">Historial insuficiente (n≥5) — el número real aparece cuando exista.</p>
        )}
      </div>

      {/* Candidatos */}
      {data.opportunities.length === 0 && !data.blocked_reason && (
        <p className="text-sm text-gray-400 py-6 text-center">
          Ningún activo pasó el gate completo (tendencia + ADX≥20 + 40&lt;RSI&lt;75 + volumen) con score ≥ {data.min_score.toFixed(2)} hoy.
        </p>
      )}

      <div className="space-y-4">
        {data.opportunities.map((o) => (
          <div key={o.symbol} className="bg-dark-bg rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="text-lg font-bold font-mono">{o.symbol}</span>
                {o.g2_score !== null && (
                  <span className="px-2 py-0.5 rounded bg-dark-card text-xs font-mono text-accent-yellow">
                    G2 (sentimiento): {o.g2_score.toFixed(3)}
                  </span>
                )}
              </div>
              <span className="text-xs text-gray-400 font-mono">score {o.score.toFixed(4)}</span>
            </div>

            {/* Factores crudos + win_prob crudo (principios 1 y 3) */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
              {Object.entries(o.factors).map(([k, v]) => (
                <div key={k} className="bg-dark-card rounded-lg p-2">
                  <p className="text-xs text-gray-400">{FACTOR_LABELS[k] ?? k}</p>
                  <p className="font-mono font-bold text-white">{v.toFixed(3)}</p>
                </div>
              ))}
              <div className="bg-dark-card rounded-lg p-2">
                <p className="text-xs text-gray-400">Win prob (calibrada)</p>
                <p className="font-mono font-bold text-white">
                  {o.win_prob !== null ? `${(o.win_prob * 100).toFixed(1)}%` : "n/d"}
                </p>
              </div>
            </div>

            {/* Entrada + plan de salida (principio 2) */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 text-sm">
              <div className="bg-dark-card rounded-lg p-2">
                <p className="text-xs text-gray-400">Entrada</p>
                <p className="font-mono font-bold text-accent-green">${o.entry_price.toFixed(2)}</p>
              </div>
              <div className="bg-dark-card rounded-lg p-2">
                <p className="text-xs text-gray-400">Stop (−2 ATR)</p>
                <p className="font-mono font-bold text-accent-red">${o.stop_loss.toFixed(2)}</p>
              </div>
              <div className="bg-dark-card rounded-lg p-2">
                <p className="text-xs text-gray-400">Take profit (+4 ATR)</p>
                <p className="font-mono font-bold text-accent-green">${o.take_profit.toFixed(2)}</p>
              </div>
              <div className="bg-dark-card rounded-lg p-2">
                <p className="text-xs text-gray-400">Payoff / ATR</p>
                <p className="font-mono font-bold text-white">{o.payoff_ratio.toFixed(2)} / ${o.atr.toFixed(2)}</p>
              </div>
            </div>

            {/* Gates cumplidos explícitos */}
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <span className={`px-2 py-0.5 rounded text-xs font-bold ${o.gates.trend_ok ? "bg-accent-green/20 text-accent-green" : "bg-accent-red/20 text-accent-red"}`}>
                Tendencia {o.gates.trend_ok ? "OK" : "ROTA"}
              </span>
              <span className="px-2 py-0.5 rounded bg-dark-card text-xs font-mono text-gray-300">ADX {o.gates.adx.toFixed(1)}</span>
              <span className="px-2 py-0.5 rounded bg-dark-card text-xs font-mono text-gray-300">RSI {o.gates.rsi.toFixed(1)}</span>
              <span className="px-2 py-0.5 rounded bg-dark-card text-xs font-mono text-gray-300">Vol {o.gates.volume_ratio.toFixed(2)}</span>
            </div>

            {/* Mecanismos de salida (principio 2) */}
            <details className="text-xs text-gray-400">
              <summary className="cursor-pointer hover:text-gray-200">Plan de salida completo ({o.exit_plan.partial_tp.trigger})</summary>
              <ul className="mt-2 space-y-1 pl-2 border-l border-dark-border">
                <li><b className="text-gray-300">Parcial:</b> {o.exit_plan.partial_tp.trigger} → {o.exit_plan.partial_tp.action}</li>
                <li><b className="text-gray-300">Trailing:</b> {o.exit_plan.trailing_stop.trigger} → {o.exit_plan.trailing_stop.action}</li>
                <li><b className="text-gray-300">Técnica:</b> {o.exit_plan.technical.trigger} → {o.exit_plan.technical.action}</li>
                <li><b className="text-gray-300">Régimen:</b> {o.exit_plan.regime_stop.trigger} → {o.exit_plan.regime_stop.action}</li>
              </ul>
            </details>
          </div>
        ))}
      </div>
    </div>
  )
}
