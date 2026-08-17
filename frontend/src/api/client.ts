// Capa de datos del advisor — ÚNICO punto de contacto con /api/advisor.
// La URL de API viene de VITE_API_URL (build) o localhost:8000 por defecto.
export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export interface ProjectedLabel {
  label: string;
  evidence: string;
  n: number;
  win_prob?: number;
}

export interface AdvisorGates {
  trend_ok: boolean;
  adx: number;
  rsi: number;
  volume_ratio: number;
}

export interface AdvisorM2 {
  point_estimate: number;
  lower: number;
  upper: number;
  abstenerse: boolean;
  razon: string;
}

export interface AdvisorTicket {
  symbol: string;
  state: "INVERTIR" | "NO_INVERTIR" | "VIGILAR";
  reason: string;
  score: number | null;
  win_prob: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  payoff_ratio: number | null;
  atr: number | null;
  m2: AdvisorM2 | null;
  factors: Record<string, number> | null;
  gates: AdvisorGates | null;
  projected: ProjectedLabel;
  last_close: number;
  last_close_date: string;
  dist_ema50: number | null;
  dist_ema200: number | null;
  transition: "NUEVO" | "MEJORA" | "DETERIORO" | "SIN_CAMBIO";
}

export interface AdvisorUniverseResponse {
  as_of: string;
  regime: { state: number; name: string; confidence: number };
  blocked_reason: string | null;
  staleness: { stale: boolean; last_cache: string | null; business_days_behind: number | null };
  honesty_badge: string;
  risk_params: { absolute_ceiling: number; risk_per_trade: number; max_position_pct: number };
  states: AdvisorTicket[];
}

export interface OhlcvBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  ema50: number | null;
  ema200: number | null;
}

export interface ExitPlan {
  [key: string]: { trigger: string; action: string };
}

export interface AdvisorSymbolResponse {
  as_of: string;
  regime: { state: number; name: string; confidence: number };
  blocked_reason: string | null;
  state: AdvisorTicket & {
    exit_plan: ExitPlan | null;
    indicators: {
      close: number;
      ema50: number;
      ema200: number;
      adx14: number;
      rsi14: number;
      volume_ratio: number;
    } | null;
    ohlcv: OhlcvBar[];
    fundamentals: Record<string, number | null> | null;
    fundamentals_coverage: "edgar" | "sin_cobertura_edgar";
  };
}

export interface ThesisEntry {
  entry_date: string;
  score: number | null;
  win_prob: number | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  gates: AdvisorGates | null;
}

export interface ThesisRow {
  symbol: string;
  status: "TESIS_VIGENTE" | "TESIS_DEGRADADA" | "TESIS_ROTA";
  entry: ThesisEntry;
  current_state: string;
  current_win_prob: number | null;
  current_last_close: number | null;
  reasons: string[];
}

export interface AdvisorThesesResponse {
  as_of: string;
  theses: ThesisRow[];
  note: string;
}

export interface EvidenceResponse {
  total_trials: number;
  families: Array<{
    familia: string;
    n_consumidos: number;
    umbral_aplicado_ultimo: number;
    ultimo_veredicto: string;
    ultima_seccion: string;
    n_trials_en_ledger: number;
  }>;
  recent: Array<{
    id: string;
    fecha: string;
    familia: string;
    veredicto: string;
    seccion: string;
  }>;
  note: string;
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`);
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail += ` — ${body.detail}`;
    } catch {
      /* sin cuerpo JSON: dejar el status */
    }
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export const api = {
  universe: () => get<AdvisorUniverseResponse>("/api/advisor/universe"),
  symbol: (symbol: string) => get<AdvisorSymbolResponse>(`/api/advisor/${symbol}`),
  theses: () => get<AdvisorThesesResponse>("/api/advisor/theses"),
  evidence: () => get<EvidenceResponse>("/api/advisor/evidence"),
};
