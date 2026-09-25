import { useMemo, useState, type ReactNode } from "react";
import { AdvisorTicket, AdvisorUniverseResponse } from "../../api/client";
import { ProjectedBadge, StateBadge, TransitionArrow, fmtPct, fmtPrice } from "./Badges";

interface Props {
  data: AdvisorUniverseResponse;
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

type SortKey = "order" | "symbol" | "win_prob" | "last_close" | "projected" | "dist_ema50";

/**
 * Definiciones de la metodología, donde se mira (PRE-REG UX Slice 1, ítem 4).
 * Cada texto está CITADO al código del motor que lo produce — si el motor cambia,
 * esta tabla cambia con él. Nada aquí es interpretativo: es la regla escrita en
 * backend/app/api/routes/{decision,advisor}.py y backend/app/core/{signal_contract,
 * signal_engine}.py.
 */
const TIP = {
  state:
    "Veredicto (decision.py:58-74, regla compuesta exacta): régimen 3 bloquea entradas → NO_INVERTIR; " +
    "sin score (fuera de gate) → NO_INVERTIR; win_prob < 0.50 → NO_INVERTIR; 0.50–0.60 → VIGILAR; " +
    "win_prob ≥ 0.60 → INVERTIR, salvo que M2 se abstenga (entonces VIGILAR).",
  close:
    "Último cierre del cache de datos (advisor.py:309-311). Si hay atraso, arriba aparece el banner de staleness.",
  winProb:
    "Win prob: probabilidad de ganar calibrada por Platt sobre el Score, con replay histórico a 20 días en " +
    "ventana móvil de ~2 años (decision.py:76-95,113-115). '—' = sin score (fuera de gate) o calibrador sin " +
    "ajustar (n < 20). Umbrales del veredicto: < 0.50 · 0.50–0.60 · ≥ 0.60.",
  projected:
    "Proyección §29 (advisor.py:71-95) — mapeo pre-registrado de win_prob a evidencia REAL medida: " +
    "≥ 0.70 GANANCIA_PROYECTADA_ALTA (VPP 87.5%, n=8) · ≥ 0.65 GANANCIA_PROYECTADA (VPP 73.7%, n=19) · " +
    "≥ 0.45 NEUTRO (VPP ≈ win_rate global 0.59, sin selectividad medida) · < 0.45 RIESGOSA_SIN_APOYO. " +
    "El n se muestra siempre: sin n no hay afirmación.",
  ema:
    "Dist = cierre / EMA - 1 (advisor.py:325-326), en % sobre la media exponencial. El gate de tendencia " +
    "exige cierre > EMA50 > EMA200 (signal_contract.py:150).",
  stop:
    "Stop: jerarquía estructural order block → liquidity sweep → último swing low; fallback entrada " +
    "− 2·ATR14 (signal_engine.py:36-62). Es una zona mecánica, no una predicción: con ella se midió el backtest.",
  target:
    "Target: candidato estructural MÁS CERCANO (FVG / resistencia más próxima), no el más optimista; " +
    "fallback entrada + 4·ATR14 (signal_engine.py:65-81). Si el objetivo deja RR < 1.5 (MIN_RR) la señal no se genera.",
  delta:
    "Δ de transición (decision.py:55,178-188): compara el estado de hoy con el último estado persistido " +
    "(decision_states.json) sobre el rango NO_INVERTIR 0 < VIGILAR 1 < INVERTIR 2. " +
    "↑ MEJORA · ↓ DETERIORO · ✦ NUEVO (sin estado previo) · → SIN_CAMBIO.",
  gates:
    "Gates duros de entrada (signal_contract.py:21-23,136-158): cierre > EMA50 > EMA200, ADX14 ≥ 20, " +
    "RSI14 en (40, 75), volume_ratio ≥ 1.0; y además Score ≥ 0.60 (ENTRY_THRESHOLD). Falla uno y no hay señal.",
  m2:
    "M2: intervalo de predicción split-conformal con α = 0.10, calibrado sobre el MISMO set que el " +
    "calibrador (decision.py:92-95). Necesita n ≥ 30; con menos, M2 no existe. Abstención = intervalo " +
    "demasiado ancho: el motor se niega a afirmar y el ticket queda en VIGILAR aunque win_prob ≥ 0.60.",
  factors:
    "Componentes que se combinan ponderados por régimen (contrato §29) para dar Score = momentum·w₁ + rsi·w₂",
} as const;

/** Rótulo que admite definición al pasar el cursor (línea punteada sutil). */
function Dotted({ children }: { children: ReactNode }) {
  return <span className="cursor-help underline decoration-dotted underline-offset-2">{children}</span>;
}

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
              <th className="text-left px-3 py-2" title={TIP.state}><Dotted>Estado</Dotted></th>
              <th className="text-left px-3 py-2">Símbolo</th>
              <th className="text-right px-3 py-2" title={TIP.close}><Dotted>Cierre</Dotted></th>
              <th className="text-right px-3 py-2" title={TIP.winProb}><Dotted>Win prob</Dotted></th>
              <th className="text-left px-3 py-2" title={TIP.projected}><Dotted>Proyección</Dotted></th>
              <th className="text-right px-3 py-2" title={TIP.ema}><Dotted>Dist EMA50</Dotted></th>
              <th className="text-right px-3 py-2" title={TIP.ema}><Dotted>Dist EMA200</Dotted></th>
              <th className="text-right px-3 py-2" title={TIP.stop}><Dotted>Stop</Dotted></th>
              <th className="text-right px-3 py-2" title={TIP.target}><Dotted>Target</Dotted></th>
              <th className="text-center px-3 py-2" title={TIP.delta}><Dotted>Δ</Dotted></th>
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

      {/* Leyenda visible: la regla del gate escrita donde se opera, no en un manual. */}
      <p className="text-[10px] text-tv-dim leading-relaxed font-mono">
        Gate técnico (los 5, falla uno y no hay señal): cierre &gt; EMA50 &gt; EMA200 · ADX14 ≥ 20 ·
        RSI14 en (40, 75) · Vol ≥ 1.0× · Score ≥ 0.60 — y encima del rótulo de cada columna está su definición.
      </p>
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
                <p className="text-tv-dim mb-1" title={TIP.state}><Dotted>Razón del veredicto</Dotted></p>
                <p className="text-tv-text">{t.reason}</p>
                <p className="text-tv-dim mt-1" title={TIP.winProb}>
                  Score: {t.score ?? "—"} · Payoff: {t.payoff_ratio ?? "—"}R · ATR: {t.atr ?? "—"}
                </p>
                {t.factors && (
                  <div className="mt-2">
                    <p className="text-tv-dim mb-1" title={TIP.factors}>
                      <Dotted>Factores del Score</Dotted>
                    </p>
                    <div className="space-y-1">
                      {Object.entries(t.factors).map(([k, v]) => {
                        const pct = Math.max(0, Math.min(1, v)) * 100
                        return (
                          <div key={k} className="flex items-center gap-2">
                            <span className="w-16 text-tv-dim capitalize">{k}</span>
                            <span className="flex-1 h-1.5 bg-dark-border rounded overflow-hidden">
                              <span
                                className="block h-full bg-accent-green"
                                style={{ width: `${pct.toFixed(0)}%` }}
                              />
                            </span>
                            <span className="w-10 text-right font-mono num text-tv-text">{pct.toFixed(0)}%</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
              <div>
                <p className="text-tv-dim mb-1" title={TIP.gates}><Dotted>Gates técnicos</Dotted></p>
                {t.gates ? (
                  <p className="font-mono text-tv-text" title={TIP.gates}>
                    Trend {t.gates.trend_ok ? "✓" : "✗"} · ADX {t.gates.adx.toFixed(1)} · RSI{" "}
                    {t.gates.rsi.toFixed(1)} · Vol {t.gates.volume_ratio.toFixed(2)}
                  </p>
                ) : (
                  <p className="text-tv-dim" title={TIP.gates}>fuera de gate (sin score)</p>
                )}
                {t.m2 ? (
                  <p className="font-mono text-tv-text mt-1" title={TIP.m2}>
                    <span className="text-tv-dim"><Dotted>M2</Dotted></span>:{" "}
                    {fmtPct(t.m2.point_estimate, 1)} [{fmtPct(t.m2.lower, 1)},{fmtPct(t.m2.upper, 1)}]
                    {t.m2.abstenerse && (
                      <span className="text-accent-yellow"> ⚠ abstención → VIGILAR</span>
                    )}
                  </p>
                ) : (
                  <p className="text-tv-dim mt-1" title={TIP.m2}>
                    M2 no calibrado (n &lt; 30): sin garantía conforme, sin intervalo
                  </p>
                )}
                <p className="text-tv-dim mt-1" title={`${TIP.stop} ${TIP.target}`}>
                  <Dotted>Stop/Target</Dotted>: zonas mecánicas 2×/4× ATR, no predicción
                </p>
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
