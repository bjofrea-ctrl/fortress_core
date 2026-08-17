import { useAdvisorSymbol, useAdvisorTheses } from "../../api/hooks";
import { DetailView } from "../advisor/DetailView";

interface Props {
  symbol: string;
  onBack: () => void;
}

export default function DetailPage({ symbol, onBack }: Props) {
  const { data, loading, error, refetch } = useAdvisorSymbol(symbol);
  const { data: thesesData } = useAdvisorTheses();

  if (loading) {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-6 animate-pulse space-y-3">
        <div className="h-6 bg-dark-border rounded w-72" />
        <div className="h-[420px] bg-dark-border rounded" />
        <div className="h-24 bg-dark-border rounded" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-6 text-center">
        <p className="text-accent-red text-sm mb-2">
          Error al cargar {symbol}: {error ?? "sin datos"}
        </p>
        <button onClick={refetch} className="px-3 py-1 rounded border border-dark-border text-tv-dim text-xs font-mono hover:text-tv-text">
          reintentar
        </button>
      </div>
    );
  }

  const thesis = thesesData?.theses.find((t) => t.symbol === symbol) ?? null;

  return <DetailView data={data} thesis={thesis} onBack={onBack} />;
}
