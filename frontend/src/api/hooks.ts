// Hooks de datos del advisor — patrón idéntico a hooks/useDecision.ts del repo.
import { useCallback, useEffect, useState } from "react";
import {
  AdvisorSymbolResponse,
  AdvisorThesesResponse,
  AdvisorUniverseResponse,
  CostsResponse,
  EvidenceResponse,
  api,
} from "./client";

function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetcher());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

export function useAdvisorUniverse() {
  return useFetch<AdvisorUniverseResponse>(() => api.universe(), []);
}

export function useAdvisorSymbol(symbol: string | null) {
  return useFetch<AdvisorSymbolResponse>(
    () => (symbol ? api.symbol(symbol) : Promise.resolve(null as never)),
    [symbol]
  );
}

export function useAdvisorTheses() {
  return useFetch<AdvisorThesesResponse>(() => api.theses(), []);
}

export function useAdvisorEvidence() {
  return useFetch<EvidenceResponse>(() => api.evidence(), []);
}

export function useExecutionCosts() {
  return useFetch<CostsResponse>(() => api.costs(), []);
}
