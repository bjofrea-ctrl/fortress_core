import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useExecutionCosts, useAdvisorSymbol } from "./hooks";

/**
 * Tests de los hooks de datos del advisor (useFetch genérico + clientes api.*).
 * Todo vía global.fetch stubbeado — cero red.
 */

const COSTS_OK = {
  medido: true,
  cost_per_side_medido: 0.00018883,
  slippage_p50: null,
  slippage_p95: null,
  comision_media: null,
  n_ordenes: 156,
  ventana: null,
  fecha_medicion: "2026-08-18",
  sizes: [],
  nota: "ok",
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("hooks advisor — useFetch genérico", () => {
  it("useExecutionCosts resuelve data y apaga loading", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve(COSTS_OK) });
    const { result } = renderHook(() => useExecutionCosts());
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data?.medido).toBe(true);
    expect(result.current.data?.cost_per_side_medido).toBeCloseTo(0.00018883, 10);
    expect(result.current.error).toBeNull();
  });

  it("HTTP != 200 → error con status y detail del body (formato de get())", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "sin medición disponible" }),
    });
    const { result } = renderHook(() => useExecutionCosts());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("HTTP 404 — sin medición disponible");
    expect(result.current.data).toBeNull();
  });

  it("error de red → mensaje del Error capturado", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    const { result } = renderHook(() => useExecutionCosts());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("network down");
  });

  it("refetch vuelve a invocar la API", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve(COSTS_OK) });
    const { result } = renderHook(() => useExecutionCosts());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      result.current.refetch();
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("useAdvisorSymbol(null) no llama a la API y resuelve sin data", async () => {
    const { result } = renderHook(() => useAdvisorSymbol(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
  });

  it("useAdvisorSymbol(symbol) llama al endpoint correcto", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ as_of: "hoy" }) });
    const { result } = renderHook(() => useAdvisorSymbol("AAPL"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/advisor/AAPL")
    );
    expect(result.current.data?.as_of).toBe("hoy");
  });
});
