import { useMemo, useState } from "react";
import { AdvisorTicket, AdvisorUniverseResponse } from "../../api/client";
import { ProjectedBadge, StateBadge, TransitionArrow, fmtPct, fmtPrice } from "./Badges";

interface Props {
  data: AdvisorUniverseResponse;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

type SortKey = "order" | "symbol" | "win_prob" | "last_close" | "projected" | "dist_ema50";

/** Vista MESA: el universo completo en una tabla densa, ordenable y filtrable. */
export function MesaView({ data, selectedSymbol, onSelectSymbol }: Props) {
  const [filter, setFilter] = useState<string>("TODOS");
  const [sortKey, setSortKey] = useState<SortKey>("order");
  const [expanded, setExpanded] = useState<string | null>(null);

  const rows = useMemo(() => {
    let list = data.states;
    if (filter !== "TODOS") list = list.filter((t) => t.state === filter);
    if (sortKey === "symbol") return [...list].sort((a, b) => a.symbol.localeCompare(b.symbol));
    if (sortKey === "win_prob") return [...list].sort((a, b) => (b.win_prob ?? -1) - (a.win_prob ?? -1));
    if (sortKey === "last_close") return [...list].sort((a, b) => b.last_close - a.last_close);
    if (sortKey === "projected")
      return [...list].sort((a, b) => (b.win_prob ?? -1) - (a.win_prob ?? -1));
    if (sortKey === "dist_ema50")
      return [...list].sort((a, b) => (b.dist_ema50 ?? -9) - (a.dist_ema50 ?? -9));
    return list; // "order": orden institucional del backend
  }, [data.states, filter, sortKey]);

  const counts = useMemo(() => {
    const c = { INVERTIR: 0, VIGILAR: 0, NO_INVERTIR: 0 };
    data.states.forEach((t) => {
      c[t.state] = (c[t.state] ?? 0) + 1;
    });
    return c;
  }, [data]);

  return (
    <div className="space-y-3">
      {/* Banner de régimen + staleness */}
      {data.blocked_reason && (
        <div className="bg-accent-red/10 border border-accent-red/40 rounded p-3 text-sm text-accent-red">
          {data.blocked_reason}
        </div>
      )}
      {data.staleness.stale && (
        <div className="bg-accent-yellow/10 border border-accent-yellow/40 rounded p-3 text-sm text-accent-yellow">
          Cache de datos desactualizado: último cierre {data.staleness.last_cache} (+
          {data.staleness.business_days_behind} ruedas de atraso). Precios al último
          dato disponible.
        </div>
      )}

      {/* Filtros + orden */}
      <div className="flex items-center gap-2 flex-wrap">
        {(["TODOS", "INVERTIR", "VIGILAR", "NO_INVERTIR"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded text-xs font-mono border transition-colors ${
              filter === f
                ? "bg-dark-card border-accent-green/50 text-tv-text"
                : "bg-dark-bg border-dark-border text-tv-dim hover:border-tv-dim"
            }`}
          >
            {f === "TODOS" ? `TODOS (${data.states.length})` : `${f} (${counts[f] ?? 0})`}
          </button>
        ))}
        <div className="flex-1" />
        <label className="text-xs text-tv-dim font-mono">
          Orden:
          <select
            className="ml-1 bg-dark-card border border-dark-border rounded px-2 py-1 text-xs text-tv-text"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
          >
            <option value="order">Institucional (estado + win_prob)</option>
            <option value="symbol">Símbolo</option>
            <option value="win_prob">Win prob</option>
            <option value="last_close">Precio</option>
            <option value="dist_ema50">Dist. EMA50</option>
          </select>
        </label>
      </div>

      {/* Tabla */}
      <div className="bg-dark-card border border-dark-border rounded overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-dark-border text-[11px] font-mono text-tv-dim uppercase">
              <th className="text-left px-3 py-2">Estado</th>
              <th className="text-left px-3 py-2">Símbolo</th>
              <th className="text-right px-3 py-2">Cierre</th>
              <th className="text-right px-3 py-2">Win prob</th>
              <th className="text-left px-3 py-2">Proyección</th>
              <th className="text-right px-3 py-2">Dist EMA50</th>
              <th className="text-right px-3 py-2">Dist EMA200</th>
              <th className="text-right px-3 py-2">Stop</th>
              <th className="text-right px-3 py-2">Target</th>
              <th className="text-center px-3 py-2">Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <FragmentRow
                key={t.symbol}
                t={t}
                selected={selectedSymbol === t.symbol}
                expanded={expanded === t.symbol}
                onSelect={() => onSelectSymbol(t.symbol)}
                onToggle={() => setExpanded(expanded === t.symbol ? null : t.symbol)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FragmentRow({
  t,
  selected,
  expanded,
  onSelect,
  onToggle,
}: {
  t: AdvisorTicket;
  selected: boolean;
  expanded: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className={`border-b border-dark-border/50 cursor-pointer transition-colors hover:bg-dark-bg/60 ${
          selected ? "bg-accent-green/5" : ""
        }`}
      >
        <td className="px-3 py-2"><StateBadge state={t.state} /></td>
        <td className="px-3 py-2 font-mono font-bold text-tv-text">{t.symbol}</td>
        <td className="px-3 py-2 font-mono num text-right">{fmtPrice(t.last_close)}</td>
        <td className="px-3 py-2 font-mono num text-right">
          {t.win_prob !== null ? `${(t.win_prob * 100).toFixed(1)}%` : "—"}
        </td>
        <td className="px-3 py-2"><ProjectedBadge projected={t.projected} /></td>
        <td className={`px-3 py-2 font-mono num text-right ${t.dist_ema50 !== null && t.dist_ema50 > 0 ? "text-accent-green" : "text-accent-red"}`}>
          {fmtPct(t.dist_ema50, 1)}
        </td>
        <td className={`px-3 py-2 font-mono num text-right ${t.dist_ema200 !== null && t.dist_ema200 > 0 ? "text-accent-green" : "text-accent-red"}`}>
          {fmtPct(t.dist_ema200, 1)}
        </td>
        <td className="px-3 py-2 font-mono num text-right text-accent-red">{fmtPrice(t.stop_loss)}</td>
        <td className="px-3 py-2 font-mono num text-right text-accent-green">{fmtPrice(t.take_profit)}</td>
        <td className="px-3 py-2 text-center"><TransitionArrow transition={t.transition} /></td>
      </tr>
      {expanded && (
        <tr className="bg-dark-bg/60">
          <td colSpan={10} className="px-6 py-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div>
                <p className="text-tv-dim mb-1">Razón del veredicto</p>
                <p className="text-tv-text">{t.reason}</p>
                <p className="text-tv-dim mt-1">Score: {t.score ?? "—"} · Payoff: {t.payoff_ratio ?? "—"}R · ATR: {t.atr ?? "—"}</p>
              </div>
              <div>
                <p className="text-tv-dim mb-1">Gates técnicos</p>
                {t.gates ? (
                  <p className="font-mono text-tv-text">
                    Trend {t.gates.trend_ok ? "✓" : "✗"} · ADX {t.gates.adx.toFixed(1)} · RSI{" "}
                    {t.gates.rsi.toFixed(1)} · Vol {t.gates.volume_ratio.toFixed(2)}
                  </p>
                ) : (
                  <p className="text-tv-dim">fuera de gate (sin score)</p>
                )}
                {t.m2 && (
                  <p className="font-mono text-tv-text mt-1">
                    M2: {fmtPct(t.m2.point_estimate, 1)} [{fmtPct(t.m2.lower, 1)},{fmtPct(t.m2.upper, 1)}]
                    {t.m2.abstenerse && <span className="text-accent-yellow"> ⚠ abstención</span>}
                  </p>
                )}
              </div>
              <div className="flex items-end justify-end">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect();
                  }}
                  className="px-3 py-1.5 rounded bg-accent-green/20 border border-accent-green/40 text-accent-green font-mono text-xs hover:bg-accent-green/30"
                >
                  Ver detalle {t.symbol} →
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
