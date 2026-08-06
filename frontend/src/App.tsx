import { useState } from "react"
import SystemStatus from "./components/SystemStatus"
import KPICards from "./components/KPICards"
import EquityCurve from "./components/EquityCurve"
import PriceChart from "./components/PriceChart"
import TechnicalIndicators from "./components/TechnicalIndicators"
import SymbolSummary from "./components/SymbolSummary"
import TradesTable from "./components/TradesTable"
import MonteCarloPanel from "./components/MonteCarloPanel"
import RegimePanel from "./components/RegimePanel"
import MarketOverview from "./components/MarketOverview"
import TradeDistribution from "./components/TradeDistribution"
import LiveTicker from "./components/LiveTicker"
import GovernancePanel from "./components/GovernancePanel"

const API_URL = "http://localhost:8000"

export default function App() {
  const [selectedSymbol, setSelectedSymbol] = useState("SPY")
  const symbols = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

  return (
    <div className="min-h-screen bg-dark-bg text-white">
      {/* Header */}
      <header className="border-b border-dark-border bg-dark-card sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🏛️</span>
            <div>
              <h1 className="text-xl font-bold text-accent-green">Fortress Core</h1>
              <p className="text-xs text-gray-400">Sistema de Trading Cuantitativo</p>
            </div>
          </div>
          <SystemStatus />
        </div>
      </header>

      {/* Live Ticker */}
      <LiveTicker apiUrl={API_URL} onSelectSymbol={setSelectedSymbol} />

      {/* Main content */}
      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* Row 1: Market Overview */}
        <MarketOverview apiUrl={API_URL} onSelectSymbol={setSelectedSymbol} />

        {/* Row 2: Symbol selector */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-400 mr-2">Activo:</span>
          {symbols.map((s) => (
            <button
              key={s}
              onClick={() => setSelectedSymbol(s)}
              className={`px-3 py-1 rounded-md text-sm font-mono transition-colors ${
                selectedSymbol === s
                  ? "bg-accent-green text-dark-bg font-bold"
                  : "bg-dark-card border border-dark-border text-gray-300 hover:border-accent-green"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Row 3: KPI Cards */}
        <KPICards apiUrl={API_URL} />

        {/* Row 4: Equity Curve + Regime */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <EquityCurve apiUrl={API_URL} />
          <RegimePanel apiUrl={API_URL} />
        </div>

        {/* Row 5: Price Chart + Symbol Summary */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <PriceChart apiUrl={API_URL} symbol={selectedSymbol} />
          </div>
          <SymbolSummary apiUrl={API_URL} symbol={selectedSymbol} />
        </div>

        {/* Row 6: Technical Indicators */}
        <TechnicalIndicators apiUrl={API_URL} symbol={selectedSymbol} />

        {/* Row 7: Trades Table + Trade Distribution + Monte Carlo */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <TradesTable apiUrl={API_URL} />
          </div>
          <div className="space-y-6">
            <MonteCarloPanel apiUrl={API_URL} />
          </div>
        </div>

        {/* Row 8: Trade Distribution */}
        <TradeDistribution apiUrl={API_URL} />

        {/* Row 9: Governance Panel */}
        <GovernancePanel apiUrl={API_URL} symbol={selectedSymbol} />

        {/* Footer */}
        <footer className="border-t border-dark-border pt-4 pb-8 text-center text-xs text-gray-500">
          <p>Fortress Core — Fase 1 (Deterministic MVP) | Sin IA en el loop crítico</p>
          <p className="mt-1">Ceiling absoluto: 12% drawdown | Riesgo por trade: 1.5% | Capital inicial: $25,000</p>
        </footer>
      </main>
    </div>
  )
}