import { describe, expect, it } from "vitest";

import { bandFor, hasHolidaysFor, isBusinessDay, rateWithVat, tariffFor } from "./billing";
import type { DemoTariff } from "./config";

const TARIFF: DemoTariff = {
  valid_from: "2026-01-01",
  vat: 1.22,
  peak_start: 17,
  peak_end: 21,
  rates: { punta: 10, llano: 5, valle: 2 },
};

const THURSDAY = "2026-11-26";
const SATURDAY = "2026-11-28";
const SUNDAY = "2026-11-29";
const MONDAY_HOLIDAY = "2026-11-02";

describe("tariffFor", () => {
  it("gives the tariff in force from its first day on", () => {
    expect(tariffFor("2026-01-01")?.valid_from).toBe("2026-01-01");
    expect(tariffFor(THURSDAY)?.valid_from).toBe("2026-01-01");
  });

  it("gives nothing before the first tariff", () => {
    expect(tariffFor("2025-12-31")).toBeUndefined();
  });

  it("changes to the next tariff on the day it starts", () => {
    const next: DemoTariff = { ...TARIFF, valid_from: "2026-07-01" };

    expect(tariffFor("2026-06-30", [TARIFF, next])).toBe(TARIFF);
    expect(tariffFor("2026-07-01", [TARIFF, next])).toBe(next);
  });
});

describe("isBusinessDay", () => {
  it("accepts a weekday that is not a holiday", () => {
    expect(isBusinessDay(THURSDAY)).toBe(true);
  });

  it.each([SATURDAY, SUNDAY, MONDAY_HOLIDAY])("rejects %s", (day) => {
    expect(isBusinessDay(day)).toBe(false);
  });
});

describe("bandFor", () => {
  it.each([
    [0, "valle"],
    [6, "valle"],
    [7, "llano"],
    [16, "llano"],
    [17, "punta"],
    [20, "punta"],
    [21, "llano"],
    [23, "llano"],
  ])("puts hour %i of a business day in %s", (hour, band) => {
    expect(bandFor(THURSDAY, hour, TARIFF)).toBe(band);
  });

  it.each([SATURDAY, SUNDAY, MONDAY_HOLIDAY])("has no punta on %s", (day) => {
    expect(bandFor(day, 18, TARIFF)).toBe("llano");
    expect(bandFor(day, 3, TARIFF)).toBe("valle");
  });
});

describe("rateWithVat", () => {
  it("adds the VAT to the band's rate", () => {
    expect(rateWithVat(TARIFF, "punta")).toBeCloseTo(12.2);
  });
});

describe("hasHolidaysFor", () => {
  it("knows which years have a holiday list", () => {
    expect(hasHolidaysFor(2026)).toBe(true);
    expect(hasHolidaysFor(2027)).toBe(false);
  });
});
