import React from "react"
import ReactDOM from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import App from "./App.tsx"
import "./index.css"

// Cache compartido entre tabs (pre-registro DASH_TABS_PREREGISTRO.md).
// staleTime = TTL del backend (advisor.py: "mismo del contexto, 300s").
// retry/refetch desactivados = contrato del useFetch anterior (sin retry,
// sin refetch on focus) — ver pre-registro, sección Fix.3.
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
})

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
)
