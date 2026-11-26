import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import type { ConsumptionResponse } from "../types";
import { demoConsumption, demoRange, demoTariff } from "./api";
import { FIRST_DAY, OUTLETS } from "./history";

const NOW = Date.parse("2026-11-26T15:30:00-03:00"); // a Thursday

const today = () => demoConsumption("hour", "2026-11-26", "2026-11-27", NOW);
const sumOf = (response: ConsumptionResponse, id: string, field: "kwh" | "cost") =>
  response.buckets.reduce((sum, bucket) => sum + (bucket.outlets[id]?.[field] ?? 0), 0);

describe("demoRange and demoTariff", () => {
  it("says where the history starts", () => {
    expect(demoRange()).toEqual({ earliest: FIRST_DAY });
  });

  it("gives the tariff of a day, with and without VAT", () => {
    const tariff = demoTariff("2026-11-26");

    expect(tariff.rates.punta).toBe(12.034);
    expect(tariff.rates_with_vat).toEqual({ punta: 14.6815, llano: 6.3098, valle: 2.9805 });
  });

  it("answers 404 before the first tariff", () => {
    expect(() => demoTariff("2025-12-31")).toThrow(ApiError);
  });
});

describe("demoConsumption", () => {
  it("gives 24 hours for a day, written in local time", () => {
    const { buckets, granularity, outlets, timezone } = today();

    expect({ granularity, outlets, timezone }).toEqual({
      granularity: "hour",
      outlets: OUTLETS,
      timezone: "America/Montevideo",
    });
    expect(buckets).toHaveLength(24);
    expect(buckets[0]?.start).toBe("2026-11-26T00:00:00-03:00");
    expect(buckets[23]?.end).toBe("2026-11-27T00:00:00-03:00");
  });

  it("gives each hour its band and price", () => {
    const { buckets } = today();

    expect(buckets[3]).toMatchObject({ band: "valle", rate_per_kwh: 2.9805 });
    expect(buckets[10]).toMatchObject({ band: "llano", rate_per_kwh: 6.3098 });
    expect(buckets[18]).toMatchObject({ band: "punta", rate_per_kwh: 14.6815 });
  });

  it("marks the hour in progress, and has no data after it", () => {
    const { buckets } = today();

    expect(buckets.filter((bucket) => bucket.partial).map((bucket) => bucket.start)).toEqual([
      "2026-11-26T15:00:00-03:00",
    ]);
    expect(buckets[15]?.has_data).toBe(true);
    expect(buckets[16]?.has_data).toBe(false);
    expect(buckets[16]?.outlets["1"]).toEqual({ kwh: 0, cost: 0 });
  });

  it("prices each hour with its own rate", () => {
    const bucket = today().buckets[10];
    const value = bucket?.outlets["2"];

    expect(value?.cost).toBeCloseTo((value?.kwh ?? 0) * (bucket?.rate_per_kwh ?? 0), 3);
  });

  it("gives the days of a week, without band or price", () => {
    const { buckets } = demoConsumption("day", "2026-11-23", "2026-11-30", NOW);

    expect(buckets).toHaveLength(7);
    expect(buckets[0]).toMatchObject({ start: "2026-11-23T00:00:00-03:00", band: null, rate_per_kwh: null });
    expect(buckets.map((bucket) => bucket.partial)).toEqual([false, false, false, true, false, false, false]);
  });

  it("makes a day the sum of its hours", () => {
    const day = demoConsumption("day", "2026-11-26", "2026-11-27", NOW).buckets[0];
    const hours = today();

    expect(day?.outlets["1"]?.kwh).toBeCloseTo(sumOf(hours, "1", "kwh"), 4);
    expect(day?.outlets["2"]?.cost).toBeCloseTo(sumOf(hours, "2", "cost"), 2);
  });

  it("totals the whole range", () => {
    const week = demoConsumption("day", "2026-11-23", "2026-11-30", NOW);

    expect(week.totals["1"]?.kwh).toBeCloseTo(sumOf(week, "1", "kwh"), 4);
    expect(week.totals["2"]?.cost).toBeCloseTo(sumOf(week, "2", "cost"), 2);
  });

  it("gives whole months, even from the middle of one", () => {
    const { buckets } = demoConsumption("month", "2025-12-15", "2026-12-01", NOW);

    expect(buckets).toHaveLength(12);
    expect(buckets[0]).toMatchObject({ start: "2025-12-01T00:00:00-03:00", has_data: false });
    expect(buckets[11]).toMatchObject({ start: "2026-11-01T00:00:00-03:00", partial: true, has_data: true });
  });

  it("warns about a year without holidays, once it has data", () => {
    const later = Date.parse("2027-01-02T12:00:00-03:00");

    expect(today().warnings).toEqual([]);
    expect(demoConsumption("day", "2026-12-28", "2027-01-04", later).warnings).toEqual([
      { code: "missing_holidays", year: 2027 },
    ]);
    expect(demoConsumption("day", "2027-01-04", "2027-01-11", later).warnings).toEqual([]);
  });
});
