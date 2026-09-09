// Hooks de datos del advisor — patrón idéntico a hooks/useDecision.ts del repo.
//
// Cache compartido vía TanStack Query (pre-registro DASH_TABS_PREREGISTRO.md):
// el cache vive en el QueryClient del provider (main.tsx), así el cambio de
// pestaña NO re-fetchea dentro de staleTime (300s = TTL del backend) y el
// resultado sobrevive al desmontaje (gcTime 10 min).
//
// Contrato preservado respecto al useFetch anterior:
//   data    -> T | null                (antes: useState<T | null>)
//   loading -> boolean                 (antes: useState(true) al montar)
//   error   -> string | null           (formato de get(): "HTTP 404 — detail")
//   refetch -> () => Promise<void>     (antes: fetchData)
//
// Nota useAdvisorSymbol(null): resuelve null inmediatamente SIN llamar a la API
// (contrato del test existente). enabled=false dejaría isPending=true eterno.
// La queryKey incluye el symbol: cada símbolo es su propia entrada de cache.
import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";
import {
  AdvisorSymbolResponse,
  AdvisorThesesResponse,
  AdvisorUniverseResponse,
  CostsResponse,
  EvidenceResponse,
  api,
} from "./client";

type UseFetchReturn<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<unknown>;
};

function useFetch<T>(
  queryKey: readonly unknown[],
  fetcher: () => Promise<T>
): UseFetchReturn<T> {
  const query: UseQueryResult<T, Error> = useQuery<T, Error>({
    queryKey,
    queryFn: fetcher,
  });

  return {
    data: query.data ?? null,
    // Contrato anterior: loading=true desde el primer render hasta resolver.
    // isPending cubre "sin datos aún"; isFetching cubre refetch en vuelo
    // (visible al cambiar de tab con cache expirado, igual que antes).
    loading: query.isPending || query.isFetching,
    error: query.error ? query.error.message : null,
    refetch: () => query.refetch(),
  };
}

export function useAdvisorUniverse() {
  return useFetch<AdvisorUniverseResponse>(["advisor", "universe"], () =>
    api.universe()
  );
}

export function useAdvisorSymbol(symbol: string | null) {
  return useFetch<AdvisorSymbolResponse>(["advisor", "symbol", symbol], () =>
    symbol ? api.symbol(symbol) : Promise.resolve(null as never)
  );
}

export function useAdvisorTheses() {
  return useFetch<AdvisorThesesResponse>(["advisor", "theses"], () =>
    api.theses()
  );
}

export function useAdvisorEvidence() {
  return useFetch<EvidenceResponse>(["advisor", "evidence"], () =>
    api.evidence()
  );
}

export function useExecutionCosts() {
  return useFetch<CostsResponse>(["advisor", "costs"], () => api.costs());
}
