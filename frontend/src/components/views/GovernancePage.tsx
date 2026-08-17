import { API_URL } from "../../api/client";
import GovernancePanel from "../GovernancePanel";
import MarketOverview from "../MarketOverview";
import OpportunitiesPanel from "../OpportunitiesPanel";

interface Props {
  selectedSymbol: string | null;
}

/**
 * Vista GOBERNANZA: multi-agente (LLM, rate-limited) + oportunidades +
 * resumen de mercado. Fuera de la vista default porque dispara LLM real.
 * Componentes existentes del rebuild de Claude Code, reubicados sin reescribir.
 */
export default function GovernancePage({ selectedSymbol }: Props) {
  return (
    <div className="space-y-4">
      <div className="bg-dark-card border border-dark-border rounded p-3">
        <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Resumen de mercado</h3>
        <MarketOverview apiUrl={API_URL} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="bg-dark-card border border-dark-border rounded p-3">
          <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Gobernanza multi-agente</h3>
          <GovernancePanel apiUrl={API_URL} symbol={selectedSymbol ?? "SPY"} />
        </div>
        <div className="bg-dark-card border border-dark-border rounded p-3">
          <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Oportunidades (motor)</h3>
          <OpportunitiesPanel apiUrl={API_URL} />
        </div>
      </div>
    </div>
  );
}
