# PRE-REGISTRO — Dashboard tabs: cache compartido + keep-alive

Registrado ANTES de tocar código (criterio de éxito fijado de antemano, doctrina repo).
Root-cause verificado contra el código real, no inferido.

## Root-cause (verificado)

1. `frontend/src/components/Layout.tsx:90-98` — render condicional puro:
   `{view === "mesa" && <MesaPage/>}`. Cada cambio de tab **desmonta** la página
   anterior: se pierde estado local, scroll y el DOM se reconstruye desde cero.
2. `frontend/src/api/hooks.ts:12-35` — `useFetch` es `useState`/`useEffect` local,
   **sin cache compartido**. Cada montaje = fetch nuevo. Agravante: `Layout` (línea 29)
   y `MesaPage` llaman ambos `useAdvisorUniverse()` → el mismo endpoint se fetchea
   2+ veces por montaje de mesa.

## Fix (alcance exacto)

1. **Dep**: `@tanstack/react-query` v5 (única dependencia nueva).
2. **Provider**: `QueryClientProvider` en el entry de la app.
3. **hooks.ts**: `useFetch` migrado a `useQuery`. La firma de retorno se PRESERVA
   (`{ data, loading, error, refetch }`) para tocar **cero consumidores**
   (Layout, MesaPage, DetailPage, CostField, EvidenceFooter).
   - `staleTime: 300_000` (300s — igual al TTL del cache del backend, verificado en
     `backend/app/api/routes/advisor.py` comentario "mismo del contexto, 300s").
   - `gcTime: 600_000` (10 min: el estado en cache sobrevive a la navegación por tabs).
   - Defaults de QueryClient que preservan el contrato actual de `useFetch`:
     `retry: false` (hoy no hay retry), `refetchOnWindowFocus: false`,
     `refetchOnReconnect: false` (hoy no hay refetch en focus/reconnect).
   - Mapeo de contrato: `data = q.data ?? null` (T|null), `error = q.error?.message`
     (string, formato actual de `get()`), `loading = isPending || isFetching`.
   - Los tests existentes llaman `renderHook` SIN provider; `useQuery` sin provider
     lanza excepción → se añade un wrapper de QueryClient a las llamadas `renderHook`
     (única edición permitida en `hooks.test.tsx`; cada test crea un QueryClient
     fresco para aislamiento). Las ASERCIONES quedan byte-idénticas.
4. **Keep-alive acumulativo en Layout**: cada página se monta la PRIMERA vez que se
   visita (conserva el code-splitting lazy diferido) y de ahí en adelante NO se
   desmonta — se oculta con `hidden` de Tailwind. `DetailPage` (Mesa→detalle) mismo
   patrón dentro de la vista mesa.

## No-objetivos (explícitos)

- NO tocar `client.ts` (capa HTTP intacta, `get()` sigue igual).
- NO tocar consumidores de los hooks (Layout.jsx line 29 incluida — la firma es igual).
- NO cambiar endpoints del backend ni su TTL.
- NO unificar DetailPage en otro componente: mismo patrón de montaje, cero refactor.

## Tests (criterio pre-registrado — el suite define el veredicto, no la impresión)

1. **Cache compartido**: 2 montajes del mismo hook dentro de staleTime → **1 solo fetch**
   (cuenta de llamadas al fetcher con QueryClient real).
2. **staleTime**: después de 300s simulados → refetch automático al remontar.
3. **Contrato intacto**: los 6 tests existentes de `hooks.test.tsx` pasan con
   ASERCIONES byte-idénticas (única edición permitida: wrapper de QueryClient en
   `renderHook` — mecánico, no cambia qué se testea).
4. **Keep-alive**: cambiar tab y volver **no desmonta** el componente (estado local
   sobrevive; el componente NO se re-monta — verificado por counter de mounts).
5. **Suite completa**: `vitest run` verde (tests existentes + nuevos).

## Criterio de éxito / reversión

- ÉXITO: vitest verde + los 3 tests existentes sin cambios + 2 montajes = 1 fetch.
- REVERSIÓN: `git revert` del commit — la rama es independiente, sin cambios en
  backend ni en otros frentes.
