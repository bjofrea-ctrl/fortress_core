import { useState } from "react";
import { AdvisorSymbolResponse, ThesisRow } from "../../api/client";
import { ProjectedBadge, StateBadge, TransitionArrow, fmtPct, fmtPrice } from "./Badges";
import { TVWidget } from "./TVWidget";
import { TradingViewChart } from "./TradingViewChart";

interface Props {
  data: AdvisorSymbolResponse;
  thesis: ThesisRow | null;
  onBack: () => void;
}

type ChartMode = "local" | "tv";

/**
 * Vista DETALLE de un símbolo: chart institutional (Lightweight Charts local o
 * widget TradingView), mecánica de salida, tesis de entrada y fundamentales.
 *
 * Honestidad (regla #4): entrada/stop/target son ZONAS MECÁNICAS del motor
 * (entry/stop 2×ATR/target 4×ATR), no niveles predichos. Fundamentales sin
 * cobertura EDGAR se muestran explícitamente como "sin datos", nunca inventados.
 */
export function DetailView({ data, thesis, onBack }: Props) {
  const [chartMode, setChartMode] = useState<ChartMode>("local");
  const t = data.state;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={onBack}
          className="px-2 py-1 rounded border border-dark-border text-tv-dim text-xs font-mono hover:text-tv-text"
        >
          ← Mesa
        </button>
        <h2 className="text-lg font-bold font-mono text-tv-text">{t.symbol}</h2>
        <StateBadge state={t.state} />
        <ProjectedBadge projected={t.projected} />
        <TransitionArrow transition={t.transition} />
        <div className="flex-1" />
        <div className="flex border border-dark-border rounded overflow-hidden">
          {(["local", "tv"] as ChartMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setChartMode(m)}
              className={`px-3 py-1 text-xs font-mono ${
                chartMode === m ? "bg-dark-card text-tv-text" : "bg-dark-bg text-tv-dim hover:text-tv-text"
              }`}
            >
              {m === "local" ? "Lightweight (EOD)" : "TradingView"}
            </button>
          ))}
        </div>
      </div>

      {data.blocked_reason && (
        <div className="bg-accent-red/10 border border-accent-red/40 rounded p-3 text-sm text-accent-red">
          {data.blocked_reason}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        {/* Chart */}
        <div className="xl:col-span-2 bg-dark-card border border-dark-border rounded p-2">
          {chartMode === "local" ? (
            <TradingViewChart
              symbol={t.symbol}
              bars={t.ohlcv}
              entry_price={t.entry_price}
              stop_loss={t.stop_loss}
              take_profit={t.take_profit}
              last_close_date={t.last_close_date}
            />
          ) : (
            <TVWidget symbol={t.symbol} />
          )}
        </div>

        {/* Panel derecho: decisión + salida */}
        <div className="space-y-3">
          <Panel title="Veredicto">
            <p className="text-xs text-tv-text">{t.reason}</p>
            <div className="grid grid-cols-2 gap-2 mt-2 text-xs font-mono">
              <Kv k="Score" v={t.score ?? "—"} />
              <Kv k="Win prob" v={t.win_prob !== null ? `${(t.win_prob * 100).toFixed(1)}%` : "—"} />
              <Kv k="ATR" v={t.atr ?? "—"} />
              <Kv k="Payoff" v={t.payoff_ratio !== null ? `${t.payoff_ratio}R` : "—"} />
            </div>
            <p className="text-[10px] text-tv-dim mt-2">
              {t.projected.evidence}
              {t.projected.n > 0 && ` (n=${t.projected.n})`}
            </p>
          </Panel>

          <Panel title="Zonas mecánicas de salida">
            <div className="space-y-1.5 text-xs font-mono">
              <Row k="Entrada (mecánica)" v={fmtPrice(t.entry_price)} cls="text-tv-text" />
              <Row k="Stop (2×ATR)" v={fmtPrice(t.stop_loss)} cls="text-accent-red" />
              <Row k="Target (4×ATR)" v={fmtPrice(t.take_profit)} cls="text-accent-green" />
              <Row k="Dist. EMA50" v={fmtPct(t.dist_ema50, 1)} cls="text-tv-text" />
              <Row k="Dist. EMA200" v={fmtPct(t.dist_ema200, 1)} cls="text-tv-text" />
            </div>
            <p className="text-[10px] text-tv-dim mt-2">
              Zonas mecánicas del motor — no son niveles predichos.
            </p>
          </Panel>

          <Panel title="M2 conforme">
            {t.m2 ? (
              <div className="text-xs font-mono">
                <p className="text-tv-text">
                  {fmtPct(t.m2.point_estimate, 1)} [{fmtPct(t.m2.lower, 1)}, {fmtPct(t.m2.upper, 1)}]
                </p>
                <p className={t.m2.abstenerse ? "text-accent-yellow mt-1" : "text-tv-dim mt-1"}>
                  {t.m2.abstenerse ? `⚠ ${t.m2.razon}` : "intervalo operativo"}
                </p>
              </div>
            ) : (
              <p className="text-xs text-tv-dim">M2 no calibrado (n&lt;30)</p>
            )}
          </Panel>
        </div>
      </div>

      {/* Plan de salida + tesis + fundamentales */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Panel title="Plan de salida (4 mecanismos)">
          {t.exit_plan ? (
            <ul className="space-y-2">
              {Object.entries(t.exit_plan).map(([name, m]) => (
                <li key={name} className="text-xs">
                  <p className="font-mono text-tv-text">{name.replace(/_/g, " ")}</p>
                  <p className="text-tv-dim">Si: <span className="text-tv-text font-mono">{m.trigger}</span></p>
                  <p className="text-tv-dim">→ {m.action}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-tv-dim">sin plan (fuera de gate)</p>
          )}
        </Panel>

        <Panel title="Tesis de entrada (exit monitor)">
          {thesis ? (
            <div className="text-xs">
              <p className="font-mono mb-1">
                <ThesisStatus status={thesis.status} />
              </p>
              <p className="text-tv-dim">Entrada: {thesis.entry.entry_date} @ {fmtPrice(thesis.entry.entry_price)}</p>
              <p className="text-tv-dim">Win prob al entrar: {thesis.entry.win_prob !== null ? `${(thesis.entry.win_prob * 100).toFixed(1)}%` : "—"}</p>
              {thesis.reasons.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {thesis.reasons.map((r, i) => (
                    <li key={i} className="text-accent-red">• {r}</li>
                  ))}
                </ul>
              )}
              <p className="text-[10px] text-tv-dim mt-2">
                Se sale cuando se pierde la tesis — perder poco importa más que ganar mucho.
              </p>
            </div>
          ) : (
            <p className="text-xs text-tv-dim">Sin tesis registrada (no está/estuvo en INVERTIR)</p>
          )}
        </Panel>

        <Panel title="Fundamentales">
          {t.fundamentals ? (
            <div className="grid grid-cols-2 gap-1.5 text-xs font-mono">
              {Object.entries(t.fundamentals).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-tv-dim">{k}</span>
                  <span className="text-tv-text">{v !== null ? v.toFixed(2) : "—"}</span>
                </div>
              ))}
              <p className="col-span-2 text-[10px] text-tv-dim mt-1">fuente: EDGAR point-in-time</p>
            </div>
          ) : (
            <div className="text-xs">
              <p className="text-tv-dim">Sin cobertura EDGAR para {t.symbol}.</p>
              <p className="text-[10px] text-tv-dim mt-1">
                No se muestran datos inventados. El universo tiene cobertura fundamental
                parcial por limitación de datos gratuitos.
              </p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function ThesisStatus({ status }: { status: string }) {
  const map: Record<string, string> = {
    TESIS_VIGENTE: "text-accent-green",
    TESIS_DEGRADADA: "text-accent-yellow",
    TESIS_ROTA: "text-accent-red",
  };
  return <span className={map[status] ?? "text-tv-dim"}>{status.replace(/_/g, " ")}</span>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-dark-card border border-dark-border rounded p-3">
      <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">{title}</h3>
      {children}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <p className="text-tv-dim">{k}</p>
      <p className="text-tv-text">{v}</p>
    </div>
  );
}

function Row({ k, v, cls }: { k: string; v: string; cls: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-tv-dim">{k}</span>
      <span className={cls}>{v}</span>
    </div>
  );
}
