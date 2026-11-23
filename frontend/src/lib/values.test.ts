import { describe, expect, it } from "vitest";
import type { Bucket, ConsumptionResponse, Outlet } from "../types";
import { periodValues, sumValues, valueFor } from "./values";

const FRIDGE: Outlet = { id: 1, slug: "heladera", name: "Heladera" };
const DESK: Outlet = { id: 2, slug: "escritorio", name: "Escritorio" };

const bucket = (outlets: Bucket["outlets"]): Bucket => ({
  start: "2026-10-01T00:00:00-03:00",
  end: "2026-11-01T00:00:00-03:00",
  has_data: true,
  partial: false,
  band: null,
  rate_per_kwh: null,
  outlets,
});

const response = (totals: ConsumptionResponse["totals"], buckets: Bucket[]): ConsumptionResponse => ({
  granularity: "month",
  timezone: "America/Montevideo",
  outlets: [FRIDGE],
  buckets,
  totals,
  warnings: [],
});

describe("periodValues", () => {
  const year = { "1": { kwh: 100, cost: 600 } };
  const lastMonth = { "1": { kwh: 9, cost: 56.8 } };
  const data = response(year, [bucket({ "1": { kwh: 1, cost: 6 } }), bucket(lastMonth)]);

  it("uses the totals of the period in the daily and hourly views", () => {
    expect(periodValues("hoy", data)).toBe(year);
    expect(periodValues("semanal", data)).toBe(year);
  });

  it("uses the last month in the monthly view", () => {
    expect(periodValues("mensual", data)).toBe(lastMonth);
  });

  it("is empty in the monthly view when there are no buckets", () => {
    expect(periodValues("mensual", response(year, []))).toEqual({});
  });
});

describe("valueFor", () => {
  it("reads the entry whose key is the plug id as a string", () => {
    expect(valueFor({ "2": { kwh: 0.4, cost: 2.52 } }, 2)).toEqual({ kwh: 0.4, cost: 2.52 });
  });

  it("gives zeros for a plug with no entry", () => {
    expect(valueFor({ "1": { kwh: 1, cost: 6 } }, 2)).toEqual({ kwh: 0, cost: 0 });
  });
});

describe("sumValues", () => {
  it("adds the kWh and the cost of the plugs", () => {
    const values = { "1": { kwh: 1, cost: 6 }, "2": { kwh: 2, cost: 12 } };
    expect(sumValues([FRIDGE, DESK], values)).toEqual({ kwh: 3, cost: 18 });
  });

  it("counts a plug with no entry as zero", () => {
    expect(sumValues([FRIDGE, DESK], { "1": { kwh: 1, cost: 6 } })).toEqual({ kwh: 1, cost: 6 });
  });

  it("ignores entries of plugs that are not in the list", () => {
    expect(sumValues([FRIDGE], { "1": { kwh: 1, cost: 6 }, "9": { kwh: 5, cost: 30 } })).toEqual({ kwh: 1, cost: 6 });
  });

  it("is zero for no plugs", () => {
    expect(sumValues([], {})).toEqual({ kwh: 0, cost: 0 });
  });
});
