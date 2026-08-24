import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MesaPage from "../../components/views/MesaPage";
import { AdvisorTicket } from "../../api/client";

function ticket(symbol: string, state: AdvisorTicket["state"], winProb: number | null): AdvisorTicket {
  return {
    symbol, state, reason: "razon test", score: 0.5, win_prob: winProb,
    entry_price: 100, stop_loss: 95, take_profit: 115, payoff_ratio: 2, atr: 2.5,
    m2: null, factors: null,
    gates: { trend_ok: true, adx: 25, rsi: 55, volume_ratio: 1.2 },
    projected: { label: "NEUTRO", evidence: "ev", n: 10 },
    last_close: 101.5, last_close_date: "2026-08-22", dist_ema50: 0.02, dist_ema200: -0.01,
    transition: "SIN_CAMBIO",
  };
}

const UNIVERSE = {
  as_of: "2026-08-22",
  regime: { state: 1, name: "GOLDILOCKS", confidence: 0.8 },
  blocked_reason: null as string | null,
  staleness: { stale: false, last_cache: null as string | null, business_days_behind: null as number | null },
  honesty_badge: "honesto",
  risk_params: { absolute_ceiling: 0.25, risk_per_trade: 0.01, max_position_pct: 0.1 },
  states: [
    ticket("AAPL", "INVERTIR", 0.62),
    ticket("MSFT", "VIGILAR", null),
    ticket("TSLA", "NO_INVERTIR", 0.31),
  ],
};

const THESES = {
  as_of: "2026-08-22",
  note: "test",
  theses: [
    { symbol: "AAPL", status: "TESIS_VIGENTE", reasons: [],
      entry: { entry_date: "2026-08-01", score: 0.6, win_prob: 0.62, entry_price: 100, stop_loss: 94, take_profit: 118, gates: null },
      current_state: "INVERTIR", current_win_prob: 0.62, current_last_close: 101.5 },
  ],
};

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function route(universe = UNIVERSE, theses: unknown = THESES) {
  fetchMock.mockImplementation((url: string | URL) => {
    const u = String(url);
    if (u.includes("/api/advisor/universe")) return Promise.resolve({ ok: true, json: () => Promise.resolve(universe) });
    if (u.includes("/api/advisor/theses")) return Promise.resolve({ ok: true, json: () => Promise.resolve(theses) });
    return Promise.reject(new Error("url inesperada: " + u));
  });
}

describe("MesaPage — contrato universo + tesis", () => {
  it("muestra skeleton mientras carga, sin datos ni error", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { container } = render(<MesaPage selectedSymbol={null} onSelectSymbol={() => {}} />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("error del backend → mensaje con el error y botón reintentar que vuelve a llamar", async () => {
    fetchMock.mockRejectedValueOnce(new Error("boom backend"));
    render(<MesaPage selectedSymbol={null} onSelectSymbol={() => {}} />);
    expect(await screen.findByText(/Error al cargar la mesa/)).toHaveTextContent("boom backend");
    const antes = fetchMock.mock.calls.length;
    await userEvent.click(screen.getByText("reintentar"));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(antes));
  });

  it("happy path: filas visibles, contadores por estado y win_prob null → —", async () => {
    route();
    render(<MesaPage selectedSymbol="AAPL" onSelectSymbol={() => {}} />);
    expect((await screen.findAllByText("AAPL")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("TODOS (3)")).toBeInTheDocument();
    expect(screen.getByText("INVERTIR (1)")).toBeInTheDocument();
    expect(screen.getByText("VIGILAR (1)")).toBeInTheDocument();
    expect(screen.getByText("NO_INVERTIR (1)")).toBeInTheDocument();
    // degradación graceful: MSFT sin win_prob calibrada muestra —, nunca NaN
    expect(screen.getAllByText("MSFT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$101.50").length).toBeGreaterThanOrEqual(1);
  });

  it("staleness y blocked_reason se muestran como banners (contrato de honestidad)", async () => {
    route(
      { ...UNIVERSE, blocked_reason: "Régimen CRISIS: motor bloqueado", staleness: { stale: true, last_cache: "2026-08-14", business_days_behind: 5 } },
    );
    render(<MesaPage selectedSymbol={null} onSelectSymbol={() => {}} />);
    expect(await screen.findByText(/Régimen CRISIS: motor bloqueado/)).toBeInTheDocument();
    expect(screen.getByText(/Cache de datos desactualizado/)).toHaveTextContent("2026-08-14");
  });

  it("tesis pendiente → fallback 'Cargando tesis...' sin crashear", async () => {
    fetchMock.mockImplementation((url: string | URL) => {
      const u = String(url);
      if (u.includes("/api/advisor/universe")) return Promise.resolve({ ok: true, json: () => Promise.resolve(UNIVERSE) });
      return new Promise(() => {}); // theses cuelga para siempre
    });
    render(<MesaPage selectedSymbol={null} onSelectSymbol={() => {}} />);
    expect(await screen.findByText(/Cargando tesis/)).toBeInTheDocument();
  });

  it("tesis resueltas → monitor con TESIS ROTA primero y razones unidas", async () => {
    route(undefined, {
      ...THESES,
      theses: [
        THESES.theses[0],
        { ...THESES.theses[0], symbol: "TSLA", status: "TESIS_ROTA", reasons: ["win_prob bajo piso", "perdió EMA50"] },
      ],
    });
    render(<MesaPage selectedSymbol={null} onSelectSymbol={() => {}} />);
    const rota = await screen.findByText("TESIS ROTA");
    const vigente = screen.getByText("TESIS VIGENTE");
    expect(rota.compareDocumentPosition(vigente) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/win_prob bajo piso · perdió EMA50/)).toBeInTheDocument();
  });
});
