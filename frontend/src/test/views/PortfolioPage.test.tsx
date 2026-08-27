import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import PortfolioPage from "../../components/views/PortfolioPage";

// PortfolioPage compone 7 paneles que fetchean por su cuenta. Acá testeamos
// composición + degradación: la página NUNCA crashea aunque los endpoints
// cuelguen o devuelvan error — cada panel degrada solo.
const ENDPOINTS = [
  "/api/backtest/equity-curve", "/api/backtest/metrics", "/api/backtest/monte-carlo",
  "/api/risk/monitor", "/api/backtest/trades", "/api/market/overview",
];

const HEADERS = [
  "Curva de capital (baseline)",
  "Régimen (M3 HMM)",
  "Riesgo adaptativo",
  "Trades (verificación #10)",
  "Monte Carlo",
  "Distribución de trades",
];

beforeEach(() => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("PortfolioPage — composición y degradación graceful", () => {
  it("endpoints colgados para siempre → los 6 encabezados montan igual, sin crash ni datos", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<PortfolioPage />);
    for (const h of HEADERS) expect(screen.getByText(h)).toBeInTheDocument();
  });

  it("todos los endpoints HTTP 500 → la página sigue en pie (cada panel maneja su error)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) }));
    render(<PortfolioPage />);
    for (const h of HEADERS) expect(screen.getByText(h)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50)); // dejar resolver los fetch fallidos
    for (const h of HEADERS) expect(screen.getByText(h)).toBeInTheDocument();
  });

  it("endpoints con payloads mínimos válidos → sin crash y sin NaN visible", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string | URL) => {
        const u = String(url);
        const body = u.includes("metrics") ? { total_return: 0.12, sharpe: 1.1 }
          : u.includes("equity-curve") ? { points: [] }
          : u.includes("trades") ? { trades: [] }
          : u.includes("monte-carlo") ? { percentiles: [] }
          : u.includes("risk") ? { positions: [] }
          : { regime: "GOLDILOCKS" };
        return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
      })
    );
    const { container } = render(<PortfolioPage />);
    await new Promise((r) => setTimeout(r, 100));
    expect(container.textContent).not.toContain("NaN");
    expect(container.textContent).not.toContain("undefined");
  });
});
