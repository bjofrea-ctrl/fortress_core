import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import GovernancePage from "../../components/views/GovernancePage";
import GovernancePanel from "../../components/GovernancePanel";
import MarketOverview from "../../components/MarketOverview";
import OpportunitiesPanel from "../../components/OpportunitiesPanel";
import { API_URL } from "../../api/client";

// La página es composición pura: el contrato a fijar es QUÉ recibe cada hijo
// (symbol con fallback SPY, apiUrl = API_URL) y que las 3 secciones montan.
vi.mock("../../components/GovernancePanel", () => ({
  default: vi.fn(({ symbol }) => <div data-testid="gov-panel" data-symbol={symbol} />),
}));
vi.mock("../../components/MarketOverview", () => ({
  default: vi.fn(({ apiUrl }) => <div data-testid="market-overview" data-url={apiUrl} />),
}));
vi.mock("../../components/OpportunitiesPanel", () => ({
  default: vi.fn(({ apiUrl }) => <div data-testid="opp-panel" data-url={apiUrl} />),
}));

beforeEach(() => {});
afterEach(() => {
  vi.clearAllMocks();
});

describe("GovernancePage — cableado de props y secciones", () => {
  it("sin símbolo seleccionado → GovernancePanel usa el default SPY (contrato)", () => {
    render(<GovernancePage selectedSymbol={null} />);
    expect(screen.getByTestId("gov-panel")).toHaveAttribute("data-symbol", "SPY");
  });

  it("con símbolo seleccionado → pasa exactamente ese símbolo", () => {
    render(<GovernancePage selectedSymbol="AAPL" />);
    expect(screen.getByTestId("gov-panel")).toHaveAttribute("data-symbol", "AAPL");
  });

  it("las 3 secciones montan y todos los hijos reciben API_URL centralizada", () => {
    render(<GovernancePage selectedSymbol={null} />);
    expect(screen.getByText("Resumen de mercado")).toBeInTheDocument();
    expect(screen.getByText("Gobernanza multi-agente")).toBeInTheDocument();
    expect(screen.getByText("Oportunidades (motor)")).toBeInTheDocument();
    expect(screen.getByTestId("market-overview")).toHaveAttribute("data-url", API_URL);
    expect(screen.getByTestId("opp-panel")).toHaveAttribute("data-url", API_URL);
    expect(vi.mocked(GovernancePanel).mock.calls[0][0].apiUrl).toBe(API_URL);
  });
});
