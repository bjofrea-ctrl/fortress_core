import { useAdvisorEvidence } from "../../api/hooks";
import type { EvidenceResponse } from "../../api/client";

/**
 * Footer de evidencia vivo: lee el ledger de trials (trial_registry.json)
 * — la firma de confianza institucional del proyecto. Cada cifra viene del
 * registro, nunca hardcodeada.
 *
 * Track A / B5: una entrada puede no haber corrido nunca (RESERVADA,
 * EXPIRADA o INEJECUTABLE por potencia insuficiente). En ese caso NO se le
 * inventa veredicto: se muestra su estado, que es lo que el registro sabe.
 */
type FamilyRow = EvidenceResponse["families"][number];

const ESTADO_LABEL: Record<string, string> = {
  RESERVED: "RESERVADO",
  EXPIRED: "EXPIRADO",
  INEJECUTABLE: "INEJECUTABLE",
};

export function veredictoOrEstado(f: FamilyRow): string {
  if (f.ultimo_veredicto) return f.ultimo_veredicto;
  const status = f.status_ultimo ?? "";
  return ESTADO_LABEL[status] ?? (status || "SIN VEREDICTO");
}

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
          {(data.n_inejecutables ?? 0) > 0 && (
            <span data-testid="b5-inejecutables" className="border border-dark-border rounded px-2 py-0.5">
              {data.n_inejecutables} rechazados por potencia (B5)
            </span>
          )}
          {data.families.map((f) => (
            <span key={f.familia} className="border border-dark-border rounded px-2 py-0.5">
              {f.familia}: {f.n_consumidos} ({veredictoOrEstado(f)} · {f.ultima_seccion})
            </span>
          ))}
        </div>
        <p className="text-[11px]">{data.note}</p>
      </div>
    </footer>
  );
}
