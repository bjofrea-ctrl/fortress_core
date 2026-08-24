import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DetailPage from "../../components/views/DetailPage";
import { DetailView } from "../../components/advisor/DetailView";

// Stub del hijo pesado: acá testeamos la LÓGICA DE PÁGINA (carga, error,
// matching de tesis), no el render interno de DetailView.
vi.mock("../../components/advisor/DetailView", () => ({
  DetailView: vi.fn(({ data, thesis }) => (
    <div data-testid="detail-view" data-symbol={data?.state?.symbol} data-thesis={thesis?.symbol ?? "null"} />
  )),
}));

const SYMBOL_RESPONSE = {
  as_of: "2026-08-22",
  regime: { state: 1, name: "GOLDILOCKS", confidence: 0.8 },
  blocked_reason: null as string | null,
  state: {
    symbol: "AAPL", state: "INVERTIR", reason: "ok", score: 0.6, win_prob: 0.62,
    entry_price: 100, stop_loss: 95, take_profit: 115, payoff_ratio: 2, atr: 2.5,
    m2: null, factors: null, gates: null,
    projected: { label: "NEUTRO", evidence: "ev", n: 10 },
    last_close: 101.5, last_close_date: "2026-08-22", dist_ema50: 0.02, dist_ema200: -0.01,
    transition: "SIN_CAMBIO",
    exit_plan: null, indicators: null, ohlcv: [], fundamentals: null,
    fundamentals_coverage: "sin_cobertura_edgar" as const,
  },
};

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(DetailView).mockClear();
});

function routeSymbol(body: unknown = SYMBOL_RESPONSE) {
  fetchMock.mockImplementation((url: string | URL) => {
    const u = String(url);
    if (u.includes("/api/advisor/") && !u.includes("theses")) return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    if (u.includes("/api/advisor/theses"))
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ as_of: "x", note: "n", theses: [
        { symbol: "AAPL", status: "TESIS_VIGENTE", reasons: [], entry: { entry_date: "d", score: null, win_prob: null, entry_price: 100, stop_loss: 94, take_profit: 118, gates: null }, current_state: "INVERTIR", current_win_prob: null, current_last_close: 101.5 },
        { symbol: "MSFT", status: "TESIS_ROTA", reasons: [], entry: { entry_date: "d", score: null, win_prob: null, entry_price: 400, stop_loss: 380, take_profit: 460, gates: null }, current_state: "NO_INVERTIR", current_win_prob: null, current_last_close: 390 },
      ] }) });
    return Promise.reject(new Error("url inesperada: " + u));
  });
}

describe("DetailPage — lógica de página", () => {
  it("loading → skeleton sin llamar a DetailView", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { container } = render(<DetailPage symbol="AAPL" onBack={() => {}} />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    expect(screen.queryByTestId("detail-view")).not.toBeInTheDocument();
  });

  it("error HTTP incluye el símbolo y el status; reintentar re-invoca", async () => {
    fetchMock.mockImplementation((url: string | URL) =>
      String(url).includes("/api/advisor/AAPL")
        ? Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
        : Promise.reject(new Error("inesperada"))
    );
    render(<DetailPage symbol="AAPL" onBack={() => {}} />);
    expect(await screen.findByText(/Error al cargar AAPL/)).toHaveTextContent("HTTP 500");
    const antes = fetchMock.mock.calls.length;
    await userEvent.click(screen.getByText("reintentar"));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(antes)); // AAPL y theses se re-intentan
  });

  it("happy path: pasa al detalle la data y la TESIS DEL SÍMBOLO correcta (no otra)", async () => {
    routeSymbol();
    render(<DetailPage symbol="AAPL" onBack={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("detail-view")).toBeInTheDocument());
    const props = vi.mocked(DetailView).mock.calls[0][0];
    expect(props.data.state.symbol).toBe("AAPL");
    expect(props.thesis?.symbol).toBe("AAPL"); // matchea por símbolo, nunca agarra MSFT
    expect(props.onBack).toBeTypeOf("function");
  });

  it("símbolo sin tesis registrada → thesis=null (degradación graceful)", async () => {
    routeSymbol();
    render(<DetailPage symbol="TSLA" onBack={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("detail-view")).toBeInTheDocument());
    expect(vi.mocked(DetailView).mock.calls[0][0].thesis).toBeNull();
  });
});
