import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CostField } from "../components/advisor/CostField";

/**
 * Tests de contrato del campo de COSTO REAL por lado (M4).
 *
 * Contrato de honestidad del proyecto: si no hay medición real
 * (medido=false), el campo NUNCA inventa un número — muestra SIN MEDICIÓN.
 */

function costsPayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    medido: true,
    cost_per_side_medido: 0.00018883,
    slippage_p50: 0.00012,
    slippage_p95: 0.00045,
    comision_media: 0.00002,
    n_ordenes: 156,
    ventana: "2026",
    fecha_medicion: "2026-08-18",
    sizes: [
      { size: 1, cost_per_side_medido: 0.00018883, slippage_p50: 0.00012, slippage_p95: 0.00045, n_ordenes: 156 },
      { size: 10, cost_per_side_medido: 0.00021, slippage_p50: 0.00014, slippage_p95: 0.0005, n_ordenes: 120 },
      { size: 50, cost_per_side_medido: 0.00034, slippage_p50: 0.0002, slippage_p95: 0.0007, n_ordenes: 60 },
    ],
    nota: "Medición PAPER — piso inferior, no costo live final",
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CostField — contrato de costo real medido", () => {
  it("mientras carga muestra el placeholder, sin número", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<CostField />);
    const chip = screen.getByText(/COSTO REAL/);
    expect(chip).toHaveTextContent("COSTO REAL: …");
    expect(chip.textContent).not.toContain("%");
  });

  it("sin medición (medido=false) muestra SIN MEDICIÓN con la nota en tooltip — nunca un número", async () => {
    // cost_per_side_medido NO null a propósito: aunque venga basura, no debe mostrarse
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(costsPayload({ medido: false })),
    });
    render(<CostField />);
    const chip = await screen.findByText(/SIN MEDICIÓN/);
    expect(chip).toHaveAttribute("title", "Medición PAPER — piso inferior, no costo live final");
    expect(chip.textContent).not.toContain("%");
  });

  it("medido → costo formateado en %, n de órdenes y curva por tamaño", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve(costsPayload()) });
    render(<CostField />);
    const chip = await screen.findByText(/COSTO REAL\/LADO/);
    // 0.00018883 * 100 = 0.018883 → toFixed(3) = "0.019"
    expect(chip).toHaveTextContent("0.019%");
    expect(chip).toHaveTextContent("n=156");
    expect(chip).toHaveTextContent("q1: 0.019%");
    expect(chip).toHaveTextContent("q10: 0.021%");
    expect(chip).toHaveTextContent("q50: 0.034%");
  });

  it("tooltip incluye caveat PAPER + p50/p95/n/fecha (contrato de honestidad M4)", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve(costsPayload()) });
    render(<CostField />);
    const chip = await screen.findByText(/COSTO REAL\/LADO/);
    const title = chip.getAttribute("title") ?? "";
    expect(title).toContain("PAPER");
    expect(title).toContain("p50");
    expect(title).toContain("p95");
    expect(title).toContain("n=156");
    expect(title).toContain("2026-08-18");
  });
});
