import { useExecutionCosts } from "../../api/hooks";

/**
 * Campo de COSTO REAL por lado (M4) — visible en todas las vistas del dashboard.
 *
 * Consume /api/costs/current, que lee la medición real de ejecución
 * (execution_costs.db / artefacto measure_execution_costs_*) — NUNCA simula un
 * número: si el backend dice medido=false, acá se ve "SIN MEDICIÓN".
 *
 * El caveat M4 (costo PAPER = piso inferior, no costo live final) viaja en el
 * tooltip del campo, como exige el contrato de honestidad del proyecto.
 */
const fmtBps = (v: number | null): string =>
  v === null ? "—" : `${(v * 100).toFixed(3)}%`;

export function CostField() {
  const { data, loading } = useExecutionCosts();

  if (loading || !data) {
    return (
      <span className="px-2 py-1 rounded text-[10px] font-mono bg-dark-card text-tv-dim border border-dark-border">
        COSTO REAL: …
      </span>
    );
  }

  if (!data.medido) {
    return (
      <span
        className="px-2 py-1 rounded text-[10px] font-mono bg-accent-yellow/10 text-accent-yellow border border-accent-yellow/30"
        title={data.nota}
      >
        COSTO REAL: SIN MEDICIÓN
      </span>
    );
  }

  const curva =
    data.sizes.length > 1
      ? data.sizes
          .map((p) => `q${p.size}: ${fmtBps(p.cost_per_side_medido)}`)
          .join(" · ")
      : null;

  return (
    <span
      className="px-2 py-1 rounded text-[10px] font-mono bg-dark-card text-tv-text border border-accent-green/40"
      title={`${data.nota}\nSlippage p50: ${fmtBps(data.slippage_p50)} · p95: ${fmtBps(
        data.slippage_p95
      )} · n=${data.n_ordenes} · medición ${data.fecha_medicion ?? "?"}`}
    >
      COSTO REAL/LADO: {fmtBps(data.cost_per_side_medido)} · n={data.n_ordenes}
      {curva ? ` · ${curva}` : ""}
    </span>
  );
}
