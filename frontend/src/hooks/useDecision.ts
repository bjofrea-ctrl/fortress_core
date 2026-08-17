import { useState, useEffect, useCallback } from "react";

export interface DecisionTicket {
  symbol: string;
  state: "INVERTIR" | "NO_INVERTIR" | "VIGILAR";
  reason: string;
  score: number | null;
  win_prob: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  payoff_ratio: number | null;
  atr: number | null;
  m2: {
    point_estimate: number;
    lower: number;
    upper: number;
    abstenerse: boolean;
    razon: string;
  } | null;
  factors: Record<string, number> | null;
  gates: {
    trend_ok: boolean;
    adx: number;
    rsi: number;
    volume_ratio: number;
  } | null;
  transition: "NUEVO" | "MEJORA" | "DETERIORO" | "SIN_CAMBIO";
  exit_plan: string[] | null;
  indicators: {
    close: number;
    ema50: number;
    ema200: number;
    adx14: number;
    rsi14: number;
    volume_ratio: number;
  } | null;
}

export interface DecisionUniverseResponse {
  as_of: string;
  regime: {
    state: number;
    name: string;
    confidence: number;
  };
  blocked_reason: string | null;
  states: DecisionTicket[];
}

export interface DecisionSymbolResponse {
  as_of: string;
  regime: {
    state: number;
    name: string;
    confidence: number;
  };
  blocked_reason: string | null;
  state: DecisionTicket;
}

export function useDecisionUniverse(apiUrl: string) {
  const [data, setData] = useState<DecisionUniverseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/api/decision/universe`);
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
  }, [apiUrl]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

export function useDecisionSymbol(apiUrl: string, symbol: string | null) {
  const [data, setData] = useState<DecisionSymbolResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!symbol) return;
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
  }, [apiUrl, symbol]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

export function getStateColor(state: string): string {
  switch (state) {
    case "INVERTIR":
      return "bg-accent-green/20 text-accent-green border-accent-green/30";
    case "VIGILAR":
      return "bg-accent-yellow/20 text-accent-yellow border-accent-yellow/30";
    case "NO_INVERTIR":
      return "bg-accent-red/20 text-accent-red border-accent-red/30";
    default:
      return "bg-gray-800/50 text-gray-400 border-gray-600";
  }
}

export function getTransitionColor(transition: string): string {
  switch (transition) {
    case "MEJORA":
      return "text-accent-green";
    case "DETERIORO":
      return "text-accent-red";
    case "NUEVO":
      return "text-accent-blue";
    default:
      return "text-gray-400";
  }
}

export function getTransitionLabel(transition: string): string {
  switch (transition) {
    case "MEJORA":
      return "⬆️ MEJORA";
    case "DETERIORO":
      return "⬇️ DETERIORO";
    case "NUEVO":
      return "✨ NUEVO";
    default:
      return "➡️ SIN CAMBIO";
  }
}