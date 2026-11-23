import { describe, expect, it } from "vitest";
import type { Tariff } from "../types";
import { footnote } from "./footnote";

const TARIFF: Tariff = {
  valid_from: "2026-01-01",
  vat: 1.22,
  peak_start: 17,
  peak_end: 21,
  rates: { valle: 2.443, llano: 5.172, punta: 12.034 },
  rates_with_vat: { valle: 2.9805, llano: 6.3098, punta: 14.6815 },
};

describe("footnote", () => {
  it("only says what is calculated while the tariff is loading", () => {
    expect(footnote(undefined)).toBe("Solo se calcula el consumo de los enchufes, sin cargos fijos.");
  });

  it("names the year, the VAT and the Punta window of the tariff", () => {
    const text = footnote(TARIFF);
    expect(text).toContain("Precios 2026 del Plan Inteligente Hogares");
    expect(text).toContain("IVA incluido (22 %)");
    expect(text).toContain("Horario Punta de 17:00 a 21:00");
  });

  it("writes single-digit hours with two digits", () => {
    expect(footnote({ ...TARIFF, peak_start: 8, peak_end: 9 })).toContain("Horario Punta de 08:00 a 09:00");
  });
});
