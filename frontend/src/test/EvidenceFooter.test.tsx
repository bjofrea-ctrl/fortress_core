import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { EvidenceFooter, veredictoOrEstado } from "../components/advisor/EvidenceFooter";
import type { EvidenceResponse } from "../api/client";

/**
 * Tests de CONTRATO del footer de evidencia (M6 ledger + B5 gate de potencia).
 *
 * El bug que esto ataja: el backend sirve entradas de trial SIN veredicto
 * (RESERVED / EXPIRED del Track A y, desde B5, INEJECUTABLE = diseño rechazado
 * por potencia insuficiente que nunca corrió). El footer leía
 * `f.ultimo_veredicto` a pelo y mostraba "undefined" (y antes de la corrección
 * en backend, el endpoint entero devolvía 500). Acá se fija que el estado real
 * es lo que se muestra, y que nunca se inventa un veredicto.
 */

function payload(over: Partial<EvidenceResponse> = {}): EvidenceResponse {
  return {
    total_trials: 51,
    n_inejecutables: 0,
    families: [
      {
        familia: "motor_signal",
        n_consumidos: 13,
        umbral_aplicado_ultimo: 0.95,
        status_ultimo: "COMPLETED",
        ultimo_veredicto: "NO_CUMPLE",
        ultima_seccion: "PLAN_MEJORA_MATEMATICA.md §48",
        n_trials_en_ledger: 13,
        n_sin_correr: 0,
      },
      {
        familia: "signal_diagnosis",
        n_consumidos: 29,
        umbral_aplicado_ultimo: 0.95,
        status_ultimo: "RESERVED",
        ultimo_veredicto: null,
        ultima_seccion: "PRE_REGISTRO_SANEAMIENTO_PALAS.md",
        n_trials_en_ledger: 29,
        n_sin_correr: 1,
      },
    ],
    recent: [],
    note: "Nota B5.",
    ...over,
  } as EvidenceResponse;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockEvidence(data: EvidenceResponse) {
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(data),
  } as unknown as Response);
}

describe("EvidenceFooter — entradas sin veredicto", () => {
  it("familia con veredicto → muestra el veredicto", async () => {
    mockEvidence(payload());
    render(<EvidenceFooter />);
    expect(await screen.findByText(/motor_signal: 13/)).toHaveTextContent("NO_CUMPLE");
  });

  it("familia sin veredicto → muestra el ESTADO, nunca 'undefined'", async () => {
    mockEvidence(payload());
    render(<EvidenceFooter />);
    const chip = await screen.findByText(/signal_diagnosis: 29/);
    expect(chip).toHaveTextContent("RESERVADO");
    expect(document.body.textContent).not.toContain("undefined");
  });

  it("B5: INEJECUTABLE se lee como INEJECUTABLE (rechazado, no refutado)", () => {
    expect(
      veredictoOrEstado({ ...payload().families[1], status_ultimo: "INEJECUTABLE" }),
    ).toBe("INEJECUTABLE");
  });

  it("EXPIRED se traduce; estado desconocido se muestra crudo; vacío no miente", () => {
    const base = payload().families[1];
    expect(veredictoOrEstado({ ...base, status_ultimo: "EXPIRED" })).toBe("EXPIRADO");
    expect(veredictoOrEstado({ ...base, status_ultimo: "FOO" })).toBe("FOO");
    expect(veredictoOrEstado({ ...base, status_ultimo: undefined })).toBe("SIN VEREDICTO");
  });

  it("contador B5 visible solo cuando hay rechazos por potencia", async () => {
    mockEvidence(payload({ n_inejecutables: 2 }));
    render(<EvidenceFooter />);
    expect(await screen.findByTestId("b5-inejecutables")).toHaveTextContent(
      "2 rechazados por potencia (B5)",
    );
  });

  it("cero rechazos → el contador no aparece (no se ocupa espacio con ruido)", async () => {
    mockEvidence(payload({ n_inejecutables: 0 }));
    render(<EvidenceFooter />);
    await waitFor(() => expect(screen.getByText(/51 trials en ledger/)).toBeInTheDocument());
    expect(screen.queryByTestId("b5-inejecutables")).not.toBeInTheDocument();
  });

  it("backend viejo sin los campos nuevos → no rompe (campos opcionales)", async () => {
    const viejo = JSON.parse(JSON.stringify(payload()));
    delete viejo.n_inejecutables;
    delete viejo.families[1].status_ultimo;
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(viejo),
    } as unknown as Response);
    render(<EvidenceFooter />);
    const chip = await screen.findByText(/signal_diagnosis: 29/);
    expect(chip).toHaveTextContent("SIN VEREDICTO");
    expect(screen.queryByTestId("b5-inejecutables")).not.toBeInTheDocument();
  });
});
