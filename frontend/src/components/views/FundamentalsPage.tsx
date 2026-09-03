import { useEffect, useState } from "react";
import { API_URL } from "../../api/client";

type Status = "loading" | "ready" | "unavailable";

/**
 * Screening de fundamentales automatizado (Fase 4 del plan).
 *
 * Embebe el HTML que genera el motor canónico real
 * (`/api/fundamentals/screen/dashboard.html`) via <iframe>. El endpoint lo
 * produce el cron nocturno (`scripts/fundamentals_screen_daily.sh`, 22:30);
 * si el cron no corrió todavía, el backend devuelve 503 y este componente
 * muestra un mensaje accionable en vez de un iframe roto.
 *
 * NO rediseña el layout del motor canónico — ese HTML ya viene armado del
 * backend. Este componente solo lo sirve en un iframe y maneja el estado
 * "aun no hay datos" de forma graceful.
 */
export default function FundamentalsPage() {
  const [status, setStatus] = useState<Status>("loading");
  const [errorDetail, setErrorDetail] = useState<string>("");

  const dashboardUrl = `${API_URL}/api/fundamentals/screen/dashboard.html`;

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");

    fetch(dashboardUrl, { method: "GET" })
      .then((resp) => {
        if (cancelled) return;
        if (resp.ok) {
          setStatus("ready");
        } else {
          setStatus("unavailable");
          setErrorDetail(`HTTP ${resp.status}`);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("unavailable");
        setErrorDetail(err?.message ?? "error de red");
      });

    return () => {
      cancelled = true;
    };
  }, [dashboardUrl]);

  if (status === "loading") {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-6 animate-pulse space-y-3">
        <div className="h-6 bg-dark-border rounded w-64" />
        <div className="h-9 bg-dark-border rounded" />
        <div className="h-9 bg-dark-border rounded" />
        <div className="h-9 bg-dark-border rounded" />
      </div>
    );
  }

  if (status === "unavailable") {
    return (
      <div className="bg-dark-card border border-dark-border rounded p-6">
        <h3 className="text-sm font-bold text-tv-dim uppercase tracking-wide mb-2">
          Screening de fundamentales
        </h3>
        <p className="text-accent-yellow text-sm mb-2">
          El dashboard no está disponible todavía.
        </p>
        <p className="text-tv-dim text-xs font-mono">
          El cron nocturno (22:30) genera los artefactos. Si nunca corrió,
          lanzá <code className="text-accent-green">scripts/fundamentals_screen_daily.sh</code> manualmente
          o esperá al próximo ciclo.
          {errorDetail && (
            <span className="text-accent-red"> (diagnóstico: {errorDetail})</span>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-dark-card border border-dark-border rounded p-3">
        <h3 className="text-xs font-bold uppercase text-tv-dim mb-2 tracking-wide">
          Screening de fundamentales — motor canónico AAI
        </h3>
        <iframe
          src={dashboardUrl}
          title="Screening de fundamentales"
          className="w-full border-0 rounded"
          style={{ height: "calc(100vh - 220px)", minHeight: "600px" }}
        />
      </div>
    </div>
  );
}
