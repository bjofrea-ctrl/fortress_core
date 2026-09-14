import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MarketOverview from "../components/MarketOverview";

/**
 * Contrato de `MarketOverview` contra el payload real de `/api/market/overview`
 * (campos verificados en `backend/app/api/routes/market.py:190-201`).
 *
 * Fija la decisión del pre-registro Slice 2, ítem B / auditoría G2-4: esta grilla
 * muestra la ventana larga EOD (retorno total, 30D, vol, posición en el rango de
 * 52 semanas) y NO el precio, que ya vive en `LiveTicker` (montado globalmente por
 * `Layout.tsx`). Dos precios distintos del mismo símbolo en la misma pantalla no
 * son dos vistas: son ruido con pinta de dato.
 */

function jsonResponse(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as unknown as Response;
}

const SPY = {
  symbol: "SPY", price: 571.4, total_return_pct: 214.5, return_30d_pct: -1.2,
  return_90d_pct: 8.4, volatility_pct: 15, high_52w: 610, low_52w: 460,
  range_position: 87.5, volume: 45000000,
};
const AAPL = {
  symbol: "AAPL", price: 230.1, total_return_pct: 980.2, return_30d_pct: 4.7,
  return_90d_pct: -2.1, volatility_pct: 26, high_52w: 260, low_52w: 165,
  range_position: 70.2, volume: 52000000,
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) =>
    Promise.resolve(jsonResponse({ symbols: [SPY, AAPL] }))
  ));
});
afterEach(() => vi.unstubAllGlobals());

describe("MarketOverview — ventana EOD propia, sin duplicar el precio vivo", () => {
  it("no renderiza el precio: la card deja de pisar la info del LiveTicker", async () => {
    render(<MarketOverview apiUrl="" />);
    await screen.findByText("SPY");
    expect(screen.queryByText("$571.40")).not.toBeInTheDocument();
    expect(screen.queryByText(/\$571/)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\$230\.10/);
  });

  it("sí renderiza lo que le es propio: retorno total, 30D, vol y posición en rango", async () => {
    render(<MarketOverview apiUrl="" />);
    await screen.findByText("SPY");
    // Orden por defecto = total_return_pct desc → primera card es AAPL (980.2),
    // segunda SPY (214.5). El marcador respeta range_position del payload de cada una.
    const markers = screen.getAllByTestId("range-marker");
    expect(markers[0]).toHaveStyle({ left: "70.2%" });  // AAPL
    expect(markers[1]).toHaveStyle({ left: "87.5%" });  // SPY
    expect(screen.getByText("15%")).toBeInTheDocument();     // volatility_pct SPY
    expect(screen.getByText("-1.2%")).toBeInTheDocument();   // return_30d_pct SPY
    expect(screen.getByText("$460")).toBeInTheDocument();    // low_52w
    expect(screen.getByText("$610")).toBeInTheDocument();    // high_52w
  });

  it("declara en pantalla qué ventana es esta (caption honesto, sin datos nuevos)", async () => {
    render(<MarketOverview apiUrl="" />);
    expect(await screen.findByText(/No es precio en vivo/)).toBeInTheDocument();
  });

  it("ordena por retorno total de mayor a menor y permite reordenar", async () => {
    render(<MarketOverview apiUrl="" />);
    await screen.findByText("SPY");
    // Orden por defecto = total_return_pct desc → AAPL (980.2) antes que SPY (214.5).
    const cards = screen.getAllByText(/^(SPY|AAPL)$/).map((el) => el.textContent);
    expect(cards[0]).toBe("AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Vol" }));
    const reordenadas = screen.getAllByText(/^(SPY|AAPL)$/).map((el) => el.textContent);
    expect(reordenadas[0]).toBe("AAPL"); // AAPL también es la más volátil (26 vs 15)
    await userEvent.click(screen.getByRole("button", { name: "30D" }));
    expect((await screen.findAllByText(/^(SPY|AAPL)$/))[0].textContent).toBe("AAPL");
  });

  it("el click en una card notifica el símbolo seleccionado", async () => {
    const onSelectSymbol = vi.fn();
    render(<MarketOverview apiUrl="" onSelectSymbol={onSelectSymbol} />);
    await userEvent.click(await screen.findByText("AAPL"));
    expect(onSelectSymbol).toHaveBeenCalledWith("AAPL");
  });

  it("payload vacío → no rompe, no inventa cards", async () => {
    vi.mocked(fetch).mockImplementationOnce(() => Promise.resolve(jsonResponse({})));
    render(<MarketOverview apiUrl="" />);
    await waitFor(() => expect(screen.queryByText("SPY")).not.toBeInTheDocument());
    expect(screen.getByText(/No es precio en vivo/)).toBeInTheDocument();
  });
});
