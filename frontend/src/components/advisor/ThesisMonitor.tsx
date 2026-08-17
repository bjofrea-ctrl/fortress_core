import { AdvisorThesesResponse } from "../../api/client";
import { fmtPrice } from "./Badges";

/**
 * Exit Thesis Monitor — la filosofía del proyecto operacionalizada:
 * se sale cuando se pierde la tesis de entrada. No predice salidas:
 * compara la foto de la entrada contra el estado actual, mecánica pura.
 */
export function ThesisMonitor({ data, onSelectSymbol }: {
  data: AdvisorThesesResponse;
  onSelectSymbol: (symbol: string) => void;
}) {
  const order: Record<string, number> = { TESIS_ROTA: 0, TESIS_DEGRADADA: 1, TESIS_VIGENTE: 2 };
  const theses = [...data.theses].sort(
    (a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9)
  );

  if (theses.length === 0) {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-4 text-xs text-tv-dim">
        Sin tesis activas: no hay símbolos con posición de entrada registrada
        (solo se registra tesis al pasar a INVERTIR).
      </div>
    );
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-dark-border text-[11px] font-mono text-tv-dim uppercase">
            <th className="text-left px-3 py-2">Tesis</th>
            <th className="text-left px-3 py-2">Símbolo</th>
            <th className="text-right px-3 py-2">Entrada</th>
            <th className="text-right px-3 py-2">Stop tesis</th>
            <th className="text-right px-3 py-2">Últ. cierre</th>
            <th className="text-left px-3 py-2">Razones de degradación</th>
          </tr>
        </thead>
        <tbody>
          {theses.map((t) => (
            <tr
              key={t.symbol}
              className="border-b border-dark-border/50 cursor-pointer hover:bg-dark-bg/60"
              onClick={() => onSelectSymbol(t.symbol)}
            >
              <td className="px-3 py-2 font-mono text-xs">
                <span
                  className={
                    t.status === "TESIS_ROTA"
                      ? "text-accent-red"
                      : t.status === "TESIS_DEGRADADA"
                      ? "text-accent-yellow"
                      : "text-accent-green"
                  }
                >
                  {t.status.replace(/_/g, " ")}
                </span>
              </td>
              <td className="px-3 py-2 font-mono font-bold text-tv-text">{t.symbol}</td>
              <td className="px-3 py-2 font-mono num text-right">{fmtPrice(t.entry.entry_price)}</td>
              <td className="px-3 py-2 font-mono num text-right text-accent-red">{fmtPrice(t.entry.stop_loss)}</td>
              <td className="px-3 py-2 font-mono num text-right">{fmtPrice(t.current_last_close)}</td>
              <td className="px-3 py-2 text-xs text-tv-dim">
                {t.reasons.length > 0 ? t.reasons.join(" · ") : "tesis sostenida"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
