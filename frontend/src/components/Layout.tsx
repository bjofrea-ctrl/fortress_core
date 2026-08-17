import { Suspense, lazy, useState } from "react";
import { API_URL } from "../api/client";
import { useAdvisorUniverse } from "../api/hooks";
import LiveTicker from "./LiveTicker";
import Header from "./Header";
import { EvidenceFooter } from "./advisor/EvidenceFooter";

// Code splitting por vista: lightweight-charts/recharts caen solo donde se usan.
const MesaPage = lazy(() => import("./views/MesaPage"));
const DetailPage = lazy(() => import("./views/DetailPage"));
const PortfolioPage = lazy(() => import("./views/PortfolioPage"));
const GovernancePage = lazy(() => import("./views/GovernancePage"));

type View = "mesa" | "portfolio" | "gobernanza";

function PageLoader() {
  return (
    <div className="bg-dark-card border border-dark-border rounded p-10 text-center text-tv-dim font-mono text-sm animate-pulse">
      Cargando módulo...
    </div>
  );
}

export default function Layout() {
  const [view, setView] = useState<View>("mesa");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const { data: universe } = useAdvisorUniverse();

  const openDetail = (symbol: string) => {
    setSelectedSymbol(symbol);
  };
  const backToMesa = () => setSelectedSymbol(null);

  // El universo real del backend reemplaza la lista hardcodeada del rebuild.
  // LiveTicker conserva su contrato propio (solo necesita apiUrl).
  return (
    <div className="min-h-screen bg-dark-bg text-tv-text">
      <Header apiUrl={API_URL} />

      {/* Badge de honestidad permanente + navegación */}
      <div className="sticky top-0 z-40 bg-dark-bg/95 backdrop-blur border-b border-dark-border">
        <div className="max-w-[1800px] mx-auto px-4 flex items-center gap-4 flex-wrap py-2">
          <nav className="flex items-center gap-1">
            {(
              [
                ["mesa", "Mesa de decisión"],
                ["portfolio", "Portfolio"],
                ["gobernanza", "Gobernanza"],
              ] as [View, string][]
            ).map(([v, label]) => (
              <button
                key={v}
                onClick={() => {
                  setView(v);
                  if (v !== "mesa") setSelectedSymbol(null);
                }}
                className={`px-3 py-1.5 rounded text-sm font-mono transition-colors ${
                  view === v && !selectedSymbol
                    ? "bg-dark-card text-tv-text border border-accent-green/40"
                    : "text-tv-dim hover:text-tv-text border border-transparent"
                }`}
              >
                {label}
              </button>
            ))}
            {selectedSymbol && view === "mesa" && (
              <span className="px-3 py-1.5 text-sm font-mono text-accent-green">
                {selectedSymbol}
              </span>
            )}
          </nav>
          <div className="flex-1" />
          <span
            className="px-2 py-1 rounded text-[10px] font-mono bg-accent-yellow/10 text-accent-yellow border border-accent-yellow/30"
            title={universe?.honesty_badge}
          >
            APOYO A DECISIÓN — SIN SEÑAL COMERCIAL VALIDADA
          </span>
        </div>
      </div>

      <LiveTicker apiUrl={API_URL} onSelectSymbol={openDetail} />

      <main className="max-w-[1800px] mx-auto px-4 py-4">
        <Suspense fallback={<PageLoader />}>
          {view === "mesa" && !selectedSymbol && (
            <MesaPage selectedSymbol={selectedSymbol} onSelectSymbol={openDetail} />
          )}
          {view === "mesa" && selectedSymbol && (
            <DetailPage symbol={selectedSymbol} onBack={backToMesa} />
          )}
          {view === "portfolio" && <PortfolioPage />}
          {view === "gobernanza" && <GovernancePage selectedSymbol={selectedSymbol} />}
        </Suspense>
      </main>

      <EvidenceFooter />
    </div>
  );
}
