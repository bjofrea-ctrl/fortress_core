import { ProjectedLabel } from "../api/client";

/**
 * Etiqueta de resultado proyectado (mapeo §29 pre-registrado).
 * Muestra SIEMPRE el n de evidencia: regla no negociable de honestidad.
 */
export function ProjectedBadge({ projected }: { projected: ProjectedLabel }) {
  const styles: Record<string, string> = {
    GANANCIA_PROYECTADA_ALTA: "bg-accent-green/20 text-accent-green border-accent-green/40",
    GANANCIA_PROYECTADA: "bg-accent-green/10 text-accent-green border-accent-green/30",
    NEUTRO: "bg-gray-500/10 text-tv-dim border-gray-500/30",
    RIESGOSA_SIN_APOYO: "bg-accent-red/15 text-accent-red border-accent-red/30",
    SIN_SCORE: "bg-dark-bg text-tv-dim border-dark-border",
    SIN_CALIBRAR: "bg-dark-bg text-tv-dim border-dark-border",
  };
  const cls = styles[projected.label] ?? styles.NEUTRO;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono border ${cls}`}
      title={projected.evidence}
    >
      {projected.label.replace(/_/g, " ")}
      {projected.n > 0 && <span className="opacity-70">n={projected.n}</span>}
    </span>
  );
}

export function StateBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    INVERTIR: "bg-accent-green/20 text-accent-green border-accent-green/40",
    VIGILAR: "bg-accent-yellow/20 text-accent-yellow border-accent-yellow/40",
    NO_INVERTIR: "bg-accent-red/15 text-accent-red border-accent-red/30",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-mono border ${styles[state] ?? "bg-dark-bg text-tv-dim border-dark-border"}`}>
      {state.replace(/_/g, " ")}
    </span>
  );
}

export function TransitionArrow({ transition }: { transition: string }) {
  const map: Record<string, [string, string]> = {
    MEJORA: ["↑", "text-accent-green"],
    DETERIORO: ["↓", "text-accent-red"],
    NUEVO: ["✦", "text-accent-blue"],
    SIN_CAMBIO: ["→", "text-tv-dim"],
  };
  const [glyph, cls] = map[transition] ?? map.SIN_CAMBIO;
  return (
    <span className={`font-mono text-xs ${cls}`} title={transition.replace(/_/g, " ")}>
      {glyph}
    </span>
  );
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

export function fmtPrice(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `$${v.toFixed(2)}`;
}
