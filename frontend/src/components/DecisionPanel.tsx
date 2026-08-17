import { useEffect, useState } from "react";
import { DecisionSymbolResponse, getStateColor, getTransitionColor, getTransitionLabel, useDecisionHistory, SymbolHistory } from "../hooks/useDecision";

interface DecisionPanelProps {
  apiUrl: string;
  symbol: string;
}

export default function DecisionPanel({ apiUrl, symbol }: DecisionPanelProps) {
  const [data, setData] = useState<DecisionSymbolResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { data: historyData } = useDecisionHistory(apiUrl, symbol);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiUrl}/api/decision/${symbol}`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const json = await response.json();
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error desconocido");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [apiUrl, symbol]);

  if (loading) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-full animate-pulse">
        <div className="flex items-center justify-between mb-4">
          <div className="h-6 bg-gray-700 rounded w-32"></div>
          <div className="h-6 bg-gray-700 rounded w-24"></div>
        </div>
        <div className="space-y-4">
          <div className="h-4 bg-gray-700 rounded w-full"></div>
          <div className="h-4 bg-gray-700 rounded w-3/4"></div>
          <div className="h-4 bg-gray-700 rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  if (error || !data || !data.state) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-full flex items-center justify-center text-gray-400">
        <p>{error || `No hay datos para ${symbol}`}</p>
      </div>
    );
  }

  const state = data.state;
  const ticket = state;

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-6 h-full">
      {/* Header: Symbol + State Badge */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-xl font-bold font-mono">{symbol}</h3>
          <span className={`text-xs px-3 py-1 rounded-full border ${getStateColor(state.state)}`}>
            {state.state}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${getTransitionColor(ticket.transition)}`}>
            {getTransitionLabel(ticket.transition)}
          </span>
          {ticket.transition !== "SIN_CAMBIO" && (
            <span className="text-xs text-gray-500">
              ({new Date(data.as_of).toLocaleDateString()})
            </span>
          )}
        </div>
      </div>

      {/* Price and Entry Range */}
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <p className="text-3xl font-mono font-bold">
            ${ticket.indicators?.close?.toFixed(2) ?? ticket.entry_price?.toFixed(2) ?? "N/A"}
          </p>
        </div>
        <p className="text-xs text-gray-400">Precio actual</p>
      </div>

      {/* Entry/Stop/Target */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-dark-bg rounded-lg p-3 text-center">
          <p className="text-xs text-gray-400 mb-1">Entrada</p>
          <p className="font-mono text-sm">
            ${ticket.entry_price?.toFixed(2) ?? "N/A"}
          </p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3 text-center">
          <p className="text-xs text-gray-400 mb-1">Stop</p>
          <p className="font-mono text-sm text-accent-red">
            ${ticket.stop_loss?.toFixed(2) ?? "N/A"}
          </p>
        </div>
        <div className="bg-dark-bg rounded-lg p-3 text-center">
          <p className="text-xs text-gray-400 mb-1">Target</p>
          <p className="font-mono text-sm text-accent-green">
            ${ticket.take_profit?.toFixed(2) ?? "N/A"}
          </p>
        </div>
      </div>

      {/* M2 Interval */}
      {ticket.m2 && (
        <div className="mb-6 p-3 bg-dark-bg rounded-lg">
          <p className="text-xs text-gray-400 mb-1">Intervalo M2 (90% confianza)</p>
          <p className="font-mono text-sm">
            {ticket.m2.point_estimate > 0 ? "+" : ""}
            {(ticket.m2.point_estimate * 100).toFixed(1)}% [
            {ticket.m2.lower > 0 ? "+" : ""}
            {(ticket.m2.lower * 100).toFixed(1)}%,
            {ticket.m2.upper > 0 ? "+" : ""}
            {(ticket.m2.upper * 100).toFixed(1)}%]
          </p>
          {ticket.m2.abstenerse && (
            <p className="text-xs text-accent-yellow mt-1">
              ⚠️ M2 sugiere abstención: {ticket.m2.razon}
            </p>
          )}
        </div>
      )}

      {/* Win Prob and Reason */}
      <div className="mb-6 p-3 bg-dark-bg rounded-lg">
        <p className="text-xs text-gray-400 mb-1">Probabilidad de acierto</p>
        <p className="text-2xl font-mono font-bold">
          {(ticket.win_prob !== null && ticket.win_prob !== undefined) ?
            (ticket.win_prob * 100).toFixed(1) + "%" : "N/A"}
        </p>
        <p className="text-xs text-gray-500 mt-1">{ticket.reason}</p>
      </div>

      {/* Factors */}
      <div className="mb-6">
        <p className="text-xs text-gray-400 mb-2">Factores</p>
        <div className="grid grid-cols-2 gap-2">
          {ticket.factors && Object.entries(ticket.factors).map(([key, value]) => (
            <div key={key} className="bg-dark-bg rounded p-2">
              <p className="text-xs text-gray-500 capitalize">{key.replace("_", " ")}</p>
              <p className={`font-mono text-sm ${value > 0 ? "text-accent-green" : "text-accent-red"}`}>
                {value > 0 ? "+" : ""}{value.toFixed(3)}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Gates */}
      {ticket.gates && (
        <div className="mb-6 p-3 bg-dark-bg rounded-lg">
          <p className="text-xs text-gray-400 mb-2">Gates técnicos</p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex justify-between">
              <span>Trend OK:</span>
              <span className={ticket.gates.trend_ok ? "text-accent-green" : "text-accent-red"}>
                {ticket.gates.trend_ok ? "✓" : "✗"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>ADX:</span>
              <span className={ticket.gates.adx > 20 ? "text-accent-green" : "text-gray-400"}>
                {ticket.gates.adx.toFixed(1)}
              </span>
            </div>
            <div className="flex justify-between">
              <span>RSI:</span>
              <span className={ticket.gates.rsi > 70 ? "text-accent-red" : ticket.gates.rsi < 30 ? "text-accent-green" : "text-white"}>
                {ticket.gates.rsi.toFixed(1)}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Vol Ratio:</span>
              <span>{ticket.gates.volume_ratio.toFixed(2)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Regime */}
      <div className="p-3 bg-dark-bg rounded-lg">
        <p className="text-xs text-gray-400 mb-1">Régimen de mercado</p>
        <p className="font-mono text-sm">{data.regime.name}</p>
        <p className="text-xs text-gray-500">
          Confianza: {(data.regime.confidence * 100).toFixed(1)}%
        </p>
      </div>

      {/* Blocked Reason */}
      {data.blocked_reason && (
        <div className="mt-4 p-3 bg-accent-red/10 border border-accent-red/30 rounded-lg text-accent-red text-xs">
          ⚠️ {data.blocked_reason}
        </div>
      )}

      {/* Transition History */}
      {historyData && historyData.transitions && historyData.transitions.length > 0 && (
        <div className="mt-6 p-3 bg-dark-bg rounded-lg">
          <p className="text-xs text-gray-400 mb-2">Historial de transiciones</p>
          <div className="space-y-2">
            {historyData.transitions.slice(-5).reverse().map((t, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-gray-500">
                  {new Date(t.from_date).toLocaleDateString()} → {new Date(t.to_date).toLocaleDateString()}
                </span>
                <span className={`px-2 py-0.5 rounded ${getStateColor(t.from)}`}>{t.from}</span>
                <span className="text-gray-400">→</span>
                <span className={`px-2 py-0.5 rounded ${getStateColor(t.to)}`}>{t.to}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
