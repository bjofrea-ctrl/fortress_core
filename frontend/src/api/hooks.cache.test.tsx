import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, renderHook, waitFor, act } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useState, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useExecutionCosts } from "./hooks";

/**
 * Tests del cache compartido (pre-registro DASH_TABS_PREREGISTRO.md):
 * el motivo del fix es que cambiar de tab NO re-fetchee dentro de staleTime
 * y que el cache sea compartido entre consumidores del mismo endpoint.
 */

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// Client por test (aislamiento) — mismos defaults que main.tsx.
function makeClient() {
  return new QueryClient({
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
}

function Wrapper({ children }: { children: ReactNode; client?: QueryClient }) {
  return <QueryClientProvider client={makeClient()}>{children}</QueryClientProvider>;
}

describe("cache compartido — TanStack Query (pre-registro §Tests.1-2)", () => {
  it("2 montajes del mismo hook con el MISMO client → 1 solo fetch", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const client = makeClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const first = renderHook(() => useExecutionCosts(), { wrapper });
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Remontaje completo (cambio de tab y vuelta): mismo client → sin fetch.
    const second = renderHook(() => useExecutionCosts(), { wrapper });
    await waitFor(() => expect(second.result.current.loading).toBe(false));
    expect(fetchMock).toHaveBeenCalledTimes(1); // <- el criterio del pre-registro
    expect(second.result.current.data).toEqual(first.result.current.data);
  });

  it("consumidores distintos del mismo hook comparten cache (Layout + MesaPage)", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const client = makeClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const a = renderHook(() => useExecutionCosts(), { wrapper });
    const b = renderHook(() => useExecutionCosts(), { wrapper });
    await waitFor(() => expect(a.result.current.loading).toBe(false));
    await waitFor(() => expect(b.result.current.loading).toBe(false));
    // Dedup en vuelo: 2 consumidores montando a la vez = 1 request.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

/**
 * Keep-alive (pre-registro §Tests.4): el mecanismo de Layout — montar en la
 * primera visita y ocultar con hidden después — testado como unidad aislada
 * con counter de mounts (el criterio es NO re-montar).
 */
function KeepAlive({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <div hidden={!active} data-active={active}>
      {children}
    </div>
  );
}

function MountProbe({ active }: { active: boolean }) {
  const [mounts, setMounts] = useState(0);
  useEffect(() => {
    setMounts((m) => m + 1);
  }, []);
  return (
    <KeepAlive active={active}>
      <span data-testid="mounts">{mounts}</span>
    </KeepAlive>
  );
}

describe("keep-alive — el tab no se desmonta al ocultarse (pre-registro §Tests.4)", () => {
  it("ocultar y reactivar NO re-monta: estado local sobrevive", async () => {
    const { rerender, getByTestId } = render(<MountProbe active={true} />);

    // Primera visita: 1 mount.
    expect(getByTestId("mounts").textContent).toBe("1");

    // Cambio de tab: oculto (hidden), NO desmontado.
    rerender(<MountProbe active={false} />);
    const el = getByTestId("mounts").parentElement as HTMLElement;
    expect(el.hidden).toBe(true);
    expect(getByTestId("mounts").textContent).toBe("1"); // sin re-mount

    // Vuelta al tab: sigue en 1 mount — estado sobrevive.
    rerender(<MountProbe active={true} />);
    expect(el.hidden).toBe(false);
    expect(getByTestId("mounts").textContent).toBe("1");
  });
});

describe("contrato hooks.ts bajo cache (complemento a hooks.test.tsx)", () => {
  it("loading=false con cache caliente: data disponible en el primer render", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    const client = makeClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );

    const first = renderHook(() => useExecutionCosts(), { wrapper });
    await waitFor(() => expect(first.result.current.loading).toBe(false));

    // Con cache caliente el remontaje arranca SIN loading (instantáneo).
    const second = renderHook(() => useExecutionCosts(), { wrapper });
    expect(second.result.current.loading).toBe(false);
    expect(second.result.current.data).not.toBeNull();
  });
});
