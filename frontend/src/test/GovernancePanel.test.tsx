import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import GovernancePanel from "../components/GovernancePanel";

/**
 * Tests de CONTRATO frontend↔backend del panel de gobernanza.
 *
 * El bug P0 (cerrado 2026-08-12, ver ROADMAP) fue que el frontend esperaba
 * `governance.triad_consensus.*` cuando el backend sirve
 * `governance.triad.{bull,bear,contrarian}.score`. Este suite fija el contrato
 * real (mismo que backend/tests/test_governance_contract.py): si el backend o
 * el frontend lo rompen de nuevo, acá se ataja antes del build.
 */

const STATUS_PAYLOAD = {
  flow: "predictivo→tríada→controller→judge",
  // A9: default real del backend desde 2026-09-03 — la capa LLM está APAGADA.
  governance_llm_enabled: false,
  nvidia_nim_blocked_by_a9: false,
  professor: { lessons_count: 42, teaching_summary: "resumen" },
  controller: { absolute_ceiling: 0.25, risk_per_trade: 0.01, max_position: 0.1, regime_stops: {} },
  judge: { verdicts_count: 100 },
  nvidia_nim: { available: false, model: "m", models_available: [], models: { triad: {}, governance: {} } },
  knowledge_repo: { total_entries: 7, by_domain: {} },
  rag_memory: { total_lessons: 42 },
  prompts: { professor: "p", controller: "c", judge: "j" },
};

const ANALYZE_PAYLOAD = {
  symbol: "AAPL",
  flow: "tríada→controller→judge",
  predictive: {
    composite_score: 0.72,
    decision: "COMPRAR",
    prob_up_short: 0.61,
    prob_up_medium: 0.58,
    prob_up_long: 0.55,
  },
  governance: {
    final_decision: "APROBADO",
    final_reason: "consenso y gates ok",
    triad: {
      bull: { score: 0.8, verdict: "ALCISTA" },
      bear: { score: 0.2, verdict: "BAJISTA" },
      contrarian: { score: 0.4, verdict: "NEUTRAL" },
      consensus: 0.467,
      decision: "COMPRAR",
      agreement: "PARCIAL",
    },
    controller: {
      approved: true,
      decision: "APPROVE",
      confidence: 0.9,
      position_size_pct: 5.0,
      stop_loss_pct: 6.0,
      take_profit_pct: 12.0,
      risk_checks: { regime_ok: true, vol_ok: false },
      llm_model: null,
    },
    judge: {
      verdict: "APPROVED",
      status: "OK",
      score: 0.85,
      reasoning: "riesgo dentro de límites",
      overruled_agents: [],
      risk_assessment: "BAJO",
      confidence: 0.88,
      conditions: ["mantener stop 6%"],
      llm_model: null,
    },
    professor: null,
  },
};

function jsonResponse(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as unknown as Response;
}

function errorResponse(status: number): Response {
  return { ok: false, status, json: () => Promise.resolve({}) } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockHappyPath(statusPayload: unknown = STATUS_PAYLOAD) {
  fetchMock.mockImplementation((url: string | URL) => {
    if (String(url).includes("/api/governance/status")) return Promise.resolve(jsonResponse(statusPayload));
    return Promise.resolve(jsonResponse(ANALYZE_PAYLOAD));
  });
}

describe("GovernancePanel — contrato con el backend", () => {
  it("llama exactamente a las dos URLs del contrato", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("http://test/api/governance/status");
      expect(fetchMock).toHaveBeenCalledWith("http://test/api/governance/analyze/AAPL");
    });
  });

  it("renderiza la tríada desde governance.triad.{bull,bear,contrarian} — contrato post-fix P0", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    // Los tres agentes con su score (score*100 toFixed(1)) y su verdict
    expect(await screen.findByText("🐂 BULL")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
    expect(screen.getByText("🐻 BEAR")).toBeInTheDocument();
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getByText("🔄 CONTRARIAN")).toBeInTheDocument();
    expect(screen.getByText("40.0%")).toBeInTheDocument();
    expect(screen.getByText("ALCISTA")).toBeInTheDocument();
    // Resumen de tríada: consensus.toFixed(3), decisión y acuerdo
    expect(screen.getByText("Consenso Tríada")).toBeInTheDocument();
    expect(screen.getByText("0.467")).toBeInTheDocument();
    expect(screen.getAllByText("COMPRAR").length).toBeGreaterThan(0);
    expect(screen.getByText("PARCIAL")).toBeInTheDocument();
  });

  it("renderiza controller determinista: posición, riesgo y risk_checks", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByText(/Controlador \(Determinista\)/)).toBeInTheDocument();
    expect(screen.getByText("5.0%")).toBeInTheDocument();
    expect(screen.getByText("regime_ok: ✓")).toBeInTheDocument();
    expect(screen.getByText("vol_ok: ✗")).toBeInTheDocument();
  });

  it("renderiza juez determinista: score, razonamiento y condiciones", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByText(/Juez \(Determinista\)/)).toBeInTheDocument();
    expect(screen.getByText("0.850")).toBeInTheDocument();
    expect(screen.getByText("riesgo dentro de límites")).toBeInTheDocument();
    expect(screen.getByText("mantener stop 6%")).toBeInTheDocument();
  });

  it("muestra estado del sistema desde /api/governance/status", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByText(/Estado del Sistema/)).toBeInTheDocument();
    // nvidia_nim.available=false → DETERMINISTA (verdad documentada del proyecto)
    expect(screen.getByText("DETERMINISTA")).toBeInTheDocument();
  });

  it("HTTP != 200 en analyze → mensaje de error visible con el status", async () => {
    fetchMock.mockImplementation((url: string | URL) => {
      if (String(url).includes("/api/governance/status")) return Promise.resolve(jsonResponse(STATUS_PAYLOAD));
      return Promise.resolve(errorResponse(500));
    });
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    const alerta = await screen.findByText(/Error al cargar/);
    expect(alerta).toHaveTextContent("Error al cargar: HTTP 500");
  });

  it("mientras carga muestra skeleton, no datos ni error", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { container } = render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    expect(screen.queryByText(/Gobernanza Multi-Agente/)).not.toBeInTheDocument();
  });
});

/**
 * A9 (PLAN_REMEDIO_BRECHAS_20260903 §A9) — el dashboard debe mostrar la
 * gobernanza como "descriptiva — no conectada a decisiones del pipeline" cuando
 * el flag GOVERNANCE_LLM_ENABLED está apagado (el default desde 2026-09-03).
 *
 * Lo que estos tests fijan es la FUENTE del cartel: sale del flag que sirve
 * /api/governance/status, no de un texto libre (final_reason, llm_model) que
 * aparezca por otra razón y se preste para mentir.
 */
describe("GovernancePanel — A9 estado del flag GOVERNANCE_LLM_ENABLED", () => {
  it("flag=false → cartel descriptivo visible sin expandir nada", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByTestId("a9-governance-mode")).toBeInTheDocument();
    expect(screen.getByTestId("a9-governance-mode-badge")).toHaveTextContent("DESACTIVADA (A9)");
    expect(screen.getByTestId("a9-governance-mode-note")).toHaveTextContent(
      "descriptiva — no conectada a decisiones del pipeline",
    );
  });

  it("el cartel NO está escondido dentro de un <details> colapsable", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    const banner = await screen.findByTestId("a9-governance-mode");
    expect(banner.closest("details")).toBeNull();
  });

  it("flag=true → dice ACTIVA y no deja el cartel de desactivada", async () => {
    mockHappyPath({ ...STATUS_PAYLOAD, governance_llm_enabled: true });
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByTestId("a9-governance-mode-badge")).toHaveTextContent("ACTIVA");
    expect(screen.queryByText(/DESACTIVADA/)).not.toBeInTheDocument();
  });

  it("flag ausente (backend viejo o /status caído) → DESCONOCIDA, nunca asume activa", async () => {
    const sinFlag = { ...STATUS_PAYLOAD } as Record<string, unknown>;
    delete sinFlag.governance_llm_enabled;
    delete sinFlag.nvidia_nim_blocked_by_a9;
    mockHappyPath(sinFlag);
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByTestId("a9-governance-mode-badge")).toHaveTextContent("DESCONOCIDA");
    expect(screen.getByTestId("a9-governance-mode-note")).toHaveTextContent(
      "no se asume que la capa esté activa",
    );
  });

  it("NIM disponible pero bloqueado por A9 → BLOQUEADA (A9), no ACTIVO ni DETERMINISTA", async () => {
    mockHappyPath({
      ...STATUS_PAYLOAD,
      governance_llm_enabled: false,
      nvidia_nim_blocked_by_a9: true,
      nvidia_nim: { ...STATUS_PAYLOAD.nvidia_nim, available: true },
    });
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    expect(await screen.findByTestId("a9-nim-bloqueado")).toBeInTheDocument();
    expect(screen.getByText("BLOQUEADA (A9)")).toBeInTheDocument();
    expect(screen.queryByText("ACTIVO")).not.toBeInTheDocument();
    expect(screen.queryByText("DETERMINISTA")).not.toBeInTheDocument();
  });

  it("NIM no disponible y flag apagado → sigue diciendo DETERMINISTA (contract previo)", async () => {
    mockHappyPath();
    render(<GovernancePanel apiUrl="http://test" symbol="AAPL" />);
    await screen.findByTestId("a9-governance-mode");
    expect(screen.getByText("DETERMINISTA")).toBeInTheDocument();
  });
});

