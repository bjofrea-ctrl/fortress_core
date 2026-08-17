import { useState, useEffect } from "react";
import { DecisionTicket, getStateColor, getTransitionColor, getTransitionLabel } from "../hooks/useDecision";

interface UniverseTableProps {
  apiUrl: string;
  onSelectSymbol: (symbol: string) => void;
  selectedSymbol: string;
}

export default function UniverseTable({ apiUrl, onSelectSymbol, selectedSymbol }: UniverseTableProps) {
  const [data, setData] = useState<DecisionTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiUrl}/api/decision/universe`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const json = await response.json();
        setData(json.states || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error desconocido");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [apiUrl]);

  if (loading) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-48 mb-4"></div>
        <div className="space-y-3">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-10 bg-gray-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-dark-card border border-dark-border rounded-lg p-6 flex items-center justify-center text-gray-400">
        <p>Error: {error}</p>
      </div>
    );
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="grid grid-cols-6 gap-4 p-4 border-b border-dark-border font-mono text-xs text-gray-400 bg-dark-bg/50">
        <span>Estado</span>
        <span>Símbolo</span>
        <span>win_prob</span>
        <span>Precio</span>
        <span>Cambio</span>
        <span>Transición</span>
      </div>

      {/* Rows */}
      <div className="divide-y divide-dark-border">
        {data.map((ticket) => {
          const isSelected = selectedSymbol === ticket.symbol;
          const isExpanded = expandedSymbol === ticket.symbol;

          return (
            <div key={ticket.symbol} className={isSelected ? "bg-accent-green/5" : ""}>
              {/* Main Row */}
              <button
                onClick={() => {
                  onSelectSymbol(ticket.symbol);
                  if (isExpanded) {
                    setExpandedSymbol(null);
                  } else {
                    setExpandedSymbol(ticket.symbol);
                  }
                }}
                className={`w-full text-left p-4 grid grid-cols-6 gap-4 items-center transition-colors hover:bg-dark-bg/50 ${
                  isSelected ? "bg-accent-green/10" : ""
                }`}
              >
                <span className={`text-xs px-2 py-1 rounded-full border ${getStateColor(ticket.state)}`}>
                  {ticket.state}
                </span>
                <span className="font-mono font-medium">{ticket.symbol}</span>
                <span className="font-mono text-sm">
                  {ticket.win_prob !== null && ticket.win_prob !== undefined ?
                    (ticket.win_prob * 100).toFixed(1) + "%" : "N/A"}
                </span>
                <span className="font-mono text-sm">
                  ${ticket.entry_price?.toFixed(2) ?? "N/A"}
                </span>
                <span className="font-mono text-sm">
                  {ticket.payoff_ratio !== null ?
                    (ticket.payoff_ratio > 0 ? "+" : "") + ticket.payoff_ratio.toFixed(2) + "R" : "N/A"}
                </span>
                <span className={`text-xs ${getTransitionColor(ticket.transition)}`}>
                  {getTransitionLabel(ticket.transition)}
                </span>
              </button>

              {/* Expanded Detail Row */}
              {isExpanded && (
                <div className="bg-dark-bg/50 p-4 border-t border-dark-border">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* M2 Interval */}
                    {ticket.m2 && (
                      <div className="p-3 bg-dark-card rounded-lg border border-dark-border">
                        <p className="text-xs text-gray-400 mb-1">Intervalo M2 (90%)</p>
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
                            ⚠️ {ticket.m2.razon}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Stop/Target/ATR */}
                    <div className="p-3 bg-dark-card rounded-lg border border-dark-border">
                      <p className="text-xs text-gray-400 mb-1">Salida / Riesgo</p>
                      <div className="space-y-1 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Stop (2×ATR):</span>
                          <span className="font-mono text-accent-red">${ticket.stop_loss?.toFixed(2) ?? "N/A"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Target:</span>
                          <span className="font-mono text-accent-green">${ticket.take_profit?.toFixed(2) ?? "N/A"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">ATR:</span>
                          <span className="font-mono">${ticket.atr?.toFixed(2) ?? "N/A"}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Payoff:</span>
                          <span className="font-mono">{ticket.payoff_ratio?.toFixed(2) ?? "N/A"}R</span>
                        </div>
                      </div>
                    </div>

                    {/* Factors */}
                    <div className="p-3 bg-dark-card rounded-lg border border-dark-border">
                      <p className="text-xs text-gray-400 mb-2">Factores</p>
                      <div className="space-y-1">
                        {ticket.factors && Object.entries(ticket.factors).map(([key, value]) => (
                          <div key={key} className="flex justify-between text-xs">
                            <span className="text-gray-400 capitalize">{key.replace("_", " ")}</span>
                            <span className={`font-mono ${value > 0 ? "text-accent-green" : "text-accent-red"}`}>
                              {value > 0 ? "+" : ""}{value.toFixed(3)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Reason */}
                  <div className="mt-3 p-2 bg-dark-card rounded border border-dark-border">
                    <p className="text-xs text-gray-400">Razón: {ticket.reason}</p>
                    {ticket.gates && (
                      <p className="text-xs text-gray-500 mt-1">
                        Gates: Trend {ticket.gates.trend_ok ? "✓" : "✗"} |
                        ADX {ticket.gates.adx.toFixed(1)} |
                        RSI {ticket.gates.rsi.toFixed(1)} |
                        Vol {ticket.gates.volume_ratio.toFixed(2)}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}