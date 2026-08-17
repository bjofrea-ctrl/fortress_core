import { useAdvisorEvidence } from "../../api/hooks";

/**
 * Footer de evidencia vivo: lee el ledger de trials (trial_registry.json)
 * — la firma de confianza institucional del proyecto. Cada cifra viene del
 * registro, nunca hardcodeada.
 */
export function EvidenceFooter() {
  const { data, loading } = useAdvisorEvidence();

  if (loading || !data) {
    return (
      <footer className="border-t border-dark-border mt-4 py-3 text-center text-xs text-tv-dim font-mono">
        Fortaleza Core — Instrumento de apoyo a decisión · cargando evidencia...
      </footer>
    );
  }

  return (
    <footer className="border-t border-dark-border mt-4 pt-3 pb-8 px-4 max-w-[1800px] mx-auto">
      <div className="text-center text-xs text-tv-dim font-mono space-y-2">
        <p>
          Fortress Core — Instrumento Diagnóstico Calibrado · M1 Barreras · M2 Conforme ·{" "}
          M3 Régimen · M4 Costos · M5 Deriva · M6 Ledger
        </p>
        <div className="flex items-center justify-center gap-4 flex-wrap text-[11px]">
          <span>{data.total_trials} trials en ledger</span>
          {data.families.map((f) => (
            <span key={f.familia} className="border border-dark-border rounded px-2 py-0.5">
              {f.familia}: {f.n_consumidos} ({f.ultimo_veredicto} · {f.ultima_seccion})
            </span>
          ))}
        </div>
        <p className="text-[11px]">{data.note}</p>
      </div>
    </footer>
  );
}
