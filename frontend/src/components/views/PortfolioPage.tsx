import { API_URL } from "../../api/client";
import EquityCurve from "../EquityCurve";
import KPICards from "../KPICards";
import MonteCarloPanel from "../MonteCarloPanel";
import RegimePanel from "../RegimePanel";
import RiskPanel from "../RiskPanel";
import TradeDistribution from "../TradeDistribution";
import TradesTable from "../TradesTable";

/**
 * Vista PORTFOLIO: la parte de cartera del panel — equity, régimen,
 * riesgo, distribución y trades. Componentes existentes del rebuild de
 * Claude Code (contratos verificados), reubicados sin reescribir.
 */
export default function PortfolioPage() {
  return (
    <div className="space-y-4">
      <KPICards apiUrl={API_URL} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-dark-card border border-dark-border rounded p-3">
          <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Curva de capital (baseline)</h3>
          <EquityCurve apiUrl={API_URL} />
        </div>
        <div className="space-y-4">
          <div className="bg-dark-card border border-dark-border rounded p-3">
            <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Régimen (M3 HMM)</h3>
            <RegimePanel apiUrl={API_URL} />
          </div>
          <div className="bg-dark-card border border-dark-border rounded p-3">
            <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Riesgo adaptativo</h3>
            <RiskPanel apiUrl={API_URL} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 bg-dark-card border border-dark-border rounded p-3">
          <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Trades — Backtest + Paper (real)</h3>
          <TradesTable apiUrl={API_URL} />
        </div>
        <div className="space-y-4">
          <div className="bg-dark-card border border-dark-border rounded p-3">
            <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Monte Carlo</h3>
            <MonteCarloPanel apiUrl={API_URL} />
          </div>
          <div className="bg-dark-card border border-dark-border rounded p-3">
            <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">Distribución de trades</h3>
            <TradeDistribution apiUrl={API_URL} />
          </div>
        </div>
      </div>
    </div>
  );
}
