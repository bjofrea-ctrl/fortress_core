// Helper de test: render con QueryClient fresco por llamada (aislamiento de
// cache entre tests). Defaults idénticos a main.tsx — pre-registro
// DASH_TABS_PREREGISTRO.md (enmienda 1: tests de componentes que consumen
// hooks necesitan el provider tras la migración a TanStack Query).
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";

export function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 300_000,
        gcTime: 600_000,
        retry: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
      },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper });
}
