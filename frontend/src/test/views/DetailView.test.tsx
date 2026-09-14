import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DetailView } from "../../components/advisor/DetailView";
import { AdvisorSymbolResponse, ThesisRow } from "../../api/client";

// El chart local usa canvas (lightweight-charts) — fuera del alcance de jsdom.
// Se mockedea devolviendo las props que recibió: así el test puede afirmar que
// DetailView le pasa la ventana de datos correcta, que es lo que garantizan
// adentro el sello "al último cierre" y el aviso de datos EOD.
// No se mockedea ningún widget externo: el de TradingView se fue del proyecto
// (pre-registro Slice 2, ítem A / auditoría G2-3).
vi.mock("../../components/advisor/LocalEodChart", () => ({
  LocalEodChart: (p: { symbol: string; last_close_date: string; entry_price: number | null }) => (
    <div
      data-testid="local-chart"
      data-symbol={p.symbol}
      data-last-close-date={p.last_close_date}
      data-entry={String(p.entry_price)}
    />
  ),
}));

function symbolResponse(over: Partial<AdvisorSymbolResponse["state"]> = {}): AdvisorSymbolResponse {
  return {
    as_of: "2026-08-22",
    regime: { state: 1, name: "GOLDILOCKS", confidence: 0.8 },
    blocked_reason: null,
    state: {
      symbol: "AAPL", state: "INVERTIR", reason: "gate y calibración ok", score: 0.6,
      win_prob: 0.62, entry_price: 100, stop_loss: 95, take_profit: 115, payoff_ratio: 2,
      atr: 2.5, m2: null, factors: null, gates: null,
      projected: { label: "GANANCIA_PROYECTADA", evidence: "rank IC W1", n: 42 },
      last_close: 101.5, last_close_date: "2026-08-22", dist_ema50: 0.021, dist_ema200: -0.01,
      transition: "MEJORA",
      exit_plan: null,
      indicators: null,
      ohlcv: [],
      fundamentals: null,
      fundamentals_coverage: "sin_cobertura_edgar",
      ...over,
    },
  };
}

const TESIS: ThesisRow = {
  symbol: "AAPL", status: "TESIS_VIGENTE", reasons: [],
  entry: { entry_date: "2026-08-01", score: 0.6, win_prob: 0.62, entry_price: 99.4, stop_loss: 94, take_profit: 118, gates: null },
  current_state: "INVERTIR", current_win_prob: 0.62, current_last_close: 101.5,
};

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => vi.unstubAllGlobals());

describe("DetailView — contrato de zonas mecánicas y degradación", () => {
  it("zonas mecánicas: entrada/stop/target con valores formateados y disclaimer anti-predicción", () => {
    render(<DetailView data={symbolResponse()} thesis={null} onBack={() => {}} />);
    expect(screen.getByText("Entrada (mecánica)")).toBeInTheDocument();
    expect(screen.getByText("$100.00")).toBeInTheDocument();
    expect(screen.getByText("Stop (2×ATR)")).toBeInTheDocument();
    expect(screen.getByText("$95.00")).toBeInTheDocument();
    expect(screen.getByText("Target (4×ATR)")).toBeInTheDocument();
    expect(screen.getByText("$115.00")).toBeInTheDocument();
    // Honestidad regla #4: nunca se presentan como niveles predichos
    expect(screen.getByText(/Zonas mecánicas del motor — no son niveles predichos/)).toBeInTheDocument();
  });

  it("valores null → — (nunca NaN ni undefined visible)", () => {
    render(<DetailView data={symbolResponse({ entry_price: null, stop_loss: null, win_prob: null, dist_ema50: null })} thesis={null} onBack={() => {}} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument();
  });

  it("sin cobertura EDGAR → mensaje explícito, datos NUNCA inventados", () => {
    render(<DetailView data={symbolResponse({ fundamentals: null })} thesis={null} onBack={() => {}} />);
    expect(screen.getByText("Sin cobertura EDGAR para AAPL.")).toBeInTheDocument();
    expect(screen.getByText(/No se muestran datos inventados/)).toBeInTheDocument();
  });

  it("con fundamentales: valores numéricos y null interno → —", () => {
    render(<DetailView data={symbolResponse({ fundamentals: { pe_ratio: 28.41, net_margin: null } })} thesis={null} onBack={() => {}} />);
    expect(screen.getByText("28.41")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("fuente: EDGAR point-in-time")).toBeInTheDocument();
  });

  it("tesis registrada → estado y razones; sin tesis → mensaje explícito", () => {
    const { rerender } = render(<DetailView data={symbolResponse()} thesis={TESIS} onBack={() => {}} />);
    expect(screen.getByText("TESIS VIGENTE")).toBeInTheDocument();
    rerender(<DetailView data={symbolResponse()} thesis={null} onBack={() => {}} />);
    expect(screen.getByText(/Sin tesis registrada/)).toBeInTheDocument();
  });

  it("M2 conforme: abstención visible con su razón; sin M2 → no calibrado", () => {
    const { rerender } = render(
      <DetailView data={symbolResponse({ m2: { point_estimate: 0.04, lower: -0.02, upper: 0.09, abstenerse: true, razon: "intervalo muy ancho" } })} thesis={null} onBack={() => {}} />
    );
    expect(screen.getByText(/⚠ intervalo muy ancho/)).toBeInTheDocument();
    rerender(<DetailView data={symbolResponse()} thesis={null} onBack={() => {}} />);
    expect(screen.getByText(/M2 no calibrado/)).toBeInTheDocument();
  });

  it("blocked_reason y plan de salida condicional", () => {
    const resp = symbolResponse({ exit_plan: null });
    resp.blocked_reason = "ventana de earnings"; // a nivel RESPUESTA, no de state
    const { rerender } = render(
      <DetailView data={resp} thesis={null} onBack={() => {}} />
    );
    expect(screen.getByText("ventana de earnings")).toBeInTheDocument();
    expect(screen.getByText(/sin plan \(fuera de gate\)/)).toBeInTheDocument();
    rerender(<DetailView data={symbolResponse({ exit_plan: { stop_duradero: { trigger: "cierre < 94", action: "salir total" } } })} thesis={null} onBack={() => {}} />);
    expect(screen.getByText("stop duradero")).toBeInTheDocument();
    expect(screen.getByText("cierre < 94")).toBeInTheDocument();
  });

  it("un solo chart: el local monta y no queda ninguna puerta a TradingView", async () => {
    const onBack = vi.fn();
    render(<DetailView data={symbolResponse()} thesis={null} onBack={onBack} />);
    expect(screen.getByTestId("local-chart")).toBeInTheDocument();
    // G2-3: ya no existe el toggle ni el widget externo.
    expect(screen.queryByText("TradingView")).not.toBeInTheDocument();
    expect(screen.queryByText("Lightweight (EOD)")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tv-widget")).not.toBeInTheDocument();
    // Y el Detalle no inyecta scripts de terceros en el documento.
    expect(
      document.querySelector("script[src*='tradingview'], script[src*='s3.tradingview.com']"),
    ).toBeNull();
    await userEvent.click(screen.getByText("← Mesa"));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("la carta recibe la ventana de datos que justifica su sello EOD", () => {
    render(<DetailView data={symbolResponse()} thesis={null} onBack={() => {}} />);
    const chart = screen.getByTestId("local-chart");
    expect(chart).toHaveAttribute("data-symbol", "AAPL");
    expect(chart).toHaveAttribute("data-last-close-date", "2026-08-22");
    expect(chart).toHaveAttribute("data-entry", "100");
  });
});
