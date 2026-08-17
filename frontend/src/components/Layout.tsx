import { useState } from "react"
import Header from "./Header"
import MarketOverview from "./MarketOverview"
import LiveTicker from "./LiveTicker"
import KPICards from "./KPICards"
import EquityCurve from "./EquityCurve"
import RegimePanel from "./RegimePanel"
import PriceChart from "./PriceChart"
import SymbolSummary from "./SymbolSummary"
import TechnicalIndicators from "./TechnicalIndicators"
import TradesTable from "./TradesTable"
import MonteCarloPanel from "./MonteCarloPanel"
import TradeDistribution from "./TradeDistribution"
import GovernancePanel from "./GovernancePanel"
import OpportunitiesPanel from "./OpportunitiesPanel"
import UniverseTable from "./UniverseTable"
import DecisionPanel from "./DecisionPanel"

const API_URL = "http://localhost:8000"
const SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

interface PanelState {
  isOpen: boolean
  height?: number
}

export default function Layout() {
  const [selectedSymbol, setSelectedSymbol] = useState("SPY")
  const [panelStates, setPanelStates] = useState<Record<string, PanelState>>({
    marketOverview: { isOpen: true },
    equityRegime: { isOpen: true },
    priceSummary: { isOpen: true },
    technicalIndicators: { isOpen: true },
    tradesDistribution: { isOpen: true },
    governance: { isOpen: true },
    opportunities: { isOpen: true },
    decisionDesk: { isOpen: true },
    universe: { isOpen: true },
  })

  const togglePanel = (key: string) => {
    setPanelStates(prev => ({
      ...prev,
      [key]: { ...prev[key], isOpen: !prev[key]?.isOpen }
    }))
  }

  const CollapsiblePanel = ({
    title,
    key,
    children,
    className = "",
    headerActions
  }: {
    title: string
    key: string
    children: React.ReactNode
    className?: string
    headerActions?: React.ReactNode
  }) => {
    const isOpen = panelStates[key]?.isOpen ?? true
    return (
      <div className={`bg-dark-card border border-dark-border rounded-lg overflow-hidden ${className}`}>
        <div
          className="flex items-center justify-between p-4 cursor-pointer hover:bg-dark-bg/50 transition-colors"
          onClick={() => togglePanel(key)}
        >
          <h3 className="text-lg font-bold flex items-center gap-2">
            {isOpen ? "▼" : "▶"} {title}
          </h3>
          <div className="flex items-center gap-2">
            {headerActions}
            <span className="text-xs text-gray-400 font-mono">{isOpen ? "ocultar" : "mostrar"}</span>
          </div>
        </div>
        {isOpen && (
          <div className="p-4 pt-0 animate-slide-down">
            {children}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-dark-bg text-white">
      <Header apiUrl={API_URL} />

      {/* Live Ticker - always visible at top */}
      <LiveTicker apiUrl={API_URL} onSelectSymbol={setSelectedSymbol} />

      {/* Main Content */}
      <main className="max-w-[1800px] mx-auto px-4 py-4 space-y-4">
        {/* Symbol Selector Bar - sticky, compact */}
        <div className="bg-dark-card border border-dark-border rounded-lg p-3 sticky top-16 z-40">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-400 mr-2 font-mono">Activo:</span>
            {SYMBOLS.map((s) => (
              <button
                key={s}
                onClick={() => setSelectedSymbol(s)}
                className={`px-3 py-1 rounded-md text-sm font-mono transition-all ${
                  selectedSymbol === s
                    ? "bg-accent-green text-dark-bg font-bold shadow-lg shadow-accent-green/20"
                    : "bg-dark-bg border border-dark-border text-gray-300 hover:border-accent-green hover:text-white"
                }`}
              >
                {s}
              </button>
            ))}
            <div className="flex-1" />
            <span className="text-xs text-gray-500 font-mono">
              Capital: $25,000 | Ceiling: -12% | Riesgo: 1.5%
            </span>
          </div>
        </div>

        {/* Row 1: Market Overview */}
        <CollapsiblePanel title="📊 Market Overview" key="marketOverview">
          <MarketOverview apiUrl={API_URL} onSelectSymbol={setSelectedSymbol} />
        </CollapsiblePanel>

        {/* Row 2: KPI Cards */}
        <KPICards apiUrl={API_URL} />

        {/* Row 3: Equity Curve + Regime Panel */}
        <CollapsiblePanel title="📈 Equity Curve & Régimen" key="equityRegime">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <EquityCurve apiUrl={API_URL} />
            <RegimePanel apiUrl={API_URL} />
          </div>
        </CollapsiblePanel>

        {/* Row 4: Price Chart + Symbol Summary */}
        <CollapsiblePanel title={`📊 ${selectedSymbol} — Gráfico de Precio & Resumen`} key="priceSummary">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              <PriceChart apiUrl={API_URL} symbol={selectedSymbol} />
            </div>
            <SymbolSummary apiUrl={API_URL} symbol={selectedSymbol} />
          </div>
        </CollapsiblePanel>

        {/* Row 5: Technical Indicators */}
        <CollapsiblePanel title={`🔧 Análisis Técnico — ${selectedSymbol}`} key="technicalIndicators">
          <TechnicalIndicators apiUrl={API_URL} symbol={selectedSymbol} />
        </CollapsiblePanel>

        {/* Row 6: Trades + Distribution + Monte Carlo */}
        <CollapsiblePanel title="📋 Trades, Distribución & Monte Carlo" key="tradesDistribution">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              <TradesTable apiUrl={API_URL} />
            </div>
            <div className="space-y-4">
              <MonteCarloPanel apiUrl={API_URL} />
              <TradeDistribution apiUrl={API_URL} />
            </div>
          </div>
        </CollapsiblePanel>

        {/* Row 7: Governance Panel - FIXED CONTRACT */}
        <CollapsiblePanel title="🤖 Gobernanza Multi-Agente" key="governance">
          <GovernancePanel apiUrl={API_URL} symbol={selectedSymbol} />
        </CollapsiblePanel>

        {/* Row 8: Opportunities Panel */}
        <CollapsiblePanel title="🎯 Oportunidades de Hoy" key="opportunities">
          <OpportunitiesPanel apiUrl={API_URL} />
        </CollapsiblePanel>

        {/* Row 9: Decision Desk - The Core Institutional View */}
        <CollapsiblePanel title={`🎛️ Mesa de Decisión — ${selectedSymbol}`} key="decisionDesk">
          <DecisionPanel apiUrl={API_URL} symbol={selectedSymbol} />
        </CollapsiblePanel>

        {/* Row 10: Universe Table - Full Ranking */}
        <CollapsiblePanel title="📋 Mesa de Decisión - Universo Completo" key="universe">
          <UniverseTable
            apiUrl={API_URL}
            onSelectSymbol={setSelectedSymbol}
            selectedSymbol={selectedSymbol}
          />
        </CollapsiblePanel>

        {/* Footer */}
        <footer className="border-t border-dark-border pt-4 pb-8 text-center text-xs text-gray-500">
          <p className="font-mono">Fortress Core — Instrumento Diagnóstico Calibrado</p>
          <p className="mt-1">M1 Etiquetado por Barreras · M2 Predicción Conforme · M3 Compuerta de Régimen · M4 Costos Medidos · M5 Detector de Deriva · M6 Ledger de Trials</p>
        </footer>
      </main>
    </div>
  )
}