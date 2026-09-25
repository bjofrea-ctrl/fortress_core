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

  // Estado vacío que EXPLICA (G2): distinguir universo sin tickets de "hoy
  // el motor no marca ninguno como INVERTIR". Ningún dato inventado: solo el
  // conteo real de data.states por estado.
  const nTotal = data.states.length;
  const nInvertir = data.states.filter((s) => s.state === "INVERTIR").length;

  return (
    <div className="space-y-4">
      {nTotal === 0 ? (
        <div className="bg-dark-card border border-dark-border rounded p-4 text-xs text-tv-dim leading-relaxed">
          El universo del advisor está vacío: el backend aún no devolvió tickets
          (no corrió la rueda, o el cache de datos está ausente). Recargá cuando
          el pipeline haya escrito el estado del día.
        </div>
      ) : nInvertir === 0 ? (
        <div className="bg-accent-yellow/10 border border-accent-yellow/40 rounded p-3 text-xs text-accent-yellow leading-relaxed">
          Hoy el motor no marca <b>ningún</b> símbolo como INVERTIR ({nTotal} en
          VIGILAR/NO_INVERTIR). Es el resultado esperado en régimen adverso: la
          abstención es señal, no falla. Revisá los VIGILAR y sus gates en la mesa.
        </div>
      ) : null}
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
