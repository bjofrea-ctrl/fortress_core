import { useAdvisorTheses, useAdvisorUniverse } from "../../api/hooks";
import { MesaView } from "../advisor/MesaView";
import { ThesisMonitor } from "../advisor/ThesisMonitor";

interface Props {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

export default function MesaPage({ selectedSymbol, onSelectSymbol }: Props) {
  const { data, loading, error, refetch } = useAdvisorUniverse();
  const { data: thesesData } = useAdvisorTheses();

  if (loading) {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-6 animate-pulse space-y-3">
        <div className="h-6 bg-dark-border rounded w-64" />
        {[...Array(10)].map((_, i) => (
          <div key={i} className="h-9 bg-dark-border rounded" />
        ))}
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-6 text-center">
        <p className="text-accent-red text-sm mb-2">Error al cargar la mesa: {error ?? "sin datos"}</p>
        <button onClick={refetch} className="px-3 py-1 rounded border border-dark-border text-tv-dim text-xs font-mono hover:text-tv-text">
          reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <MesaView data={data} selectedSymbol={selectedSymbol} onSelectSymbol={onSelectSymbol} />

      <div>
        <h2 className="text-sm font-bold text-tv-dim uppercase tracking-wide mb-2">
          Exit Thesis Monitor — se sale cuando se pierde la tesis
        </h2>
        {thesesData ? (
          <ThesisMonitor data={thesesData} onSelectSymbol={onSelectSymbol} />
        ) : (
          <div className="bg-dark-card border border-dark-border rounded p-4 text-xs text-tv-dim animate-pulse">
            Cargando tesis...
          </div>
        )}
      </div>
    </div>
  );
}
