import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import FundamentalsPage from "../../components/views/FundamentalsPage";

// FundamentalsPage embebe el HTML del motor canónico vía iframe. Acá testeamos
// composición + degradación: la página NUNCA crashea aunque el endpoint cuelgue,
// devuelva 503 (cron no corrió) o la red esté caída.
const DASHBOARD_PATH = "/api/fundamentals/screen/dashboard.html";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

describe("FundamentalsPage — composición y degradación graceful", () => {
  it("endpoint colgado para siempre → skeleton visible, sin crash", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<FundamentalsPage />);
    // El skeleton de carga está en el DOM (animación pulse)
    expect(document.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("HTTP 200 → iframe presente con el src correcto del motor canónico", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    render(<FundamentalsPage />);
    await waitFor(() => {
      const iframe = screen.getByTitle("Screening de fundamentales");
      expect(iframe).toBeInTheDocument();
      expect(iframe.getAttribute("src")).toContain(DASHBOARD_PATH);
    });
  });

  it("HTTP 503 (cron no corrió) → mensaje accionable, sin crash ni iframe roto", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503 })
    );
    render(<FundamentalsPage />);
    await waitFor(() => {
      expect(screen.getByText(/El dashboard no está disponible todavía/)).toBeInTheDocument();
    });
    // NO debe haber iframe cuando el endpoint no está disponible
    expect(screen.queryByTitle("Screening de fundamentales")).not.toBeInTheDocument();
    // El mensaje debe ser accionable (mencionar el cron)
    expect(screen.getByText(/cron/)).toBeInTheDocument();
  });

  it("HTTP 404 → mensaje accionable, sin crash", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 })
    );
    render(<FundamentalsPage />);
    await waitFor(() => {
      expect(screen.getByText(/El dashboard no está disponible todavía/)).toBeInTheDocument();
    });
    expect(screen.queryByTitle("Screening de fundamentales")).not.toBeInTheDocument();
  });

  it("error de red (backend caído) → mensaje accionable con diagnóstico, sin crash", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("network down"))
    );
    render(<FundamentalsPage />);
    await waitFor(() => {
      expect(screen.getByText(/El dashboard no está disponible todavía/)).toBeInTheDocument();
    });
    // El diagnóstico de red debe ser visible
    expect(screen.getByText(/network down/)).toBeInTheDocument();
    expect(screen.queryByTitle("Screening de fundamentales")).not.toBeInTheDocument();
  });
});
