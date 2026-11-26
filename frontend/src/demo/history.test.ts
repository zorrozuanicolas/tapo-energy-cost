import { describe, expect, it } from "vitest";

import { TARIFFS } from "./config";
import { FIRST_DAY, HOUR_MS, hourKwh, localTime, noise, OUTLETS } from "./history";

const at = (local: string) => Date.parse(`${local}-03:00`);
const NOW = at("2026-11-26T15:30:00");
const FRIDGE = 1;
const DESK = 2;

describe("localTime", () => {
  it("gives the Montevideo day and hour around midnight", () => {
    expect(localTime(Date.parse("2026-11-27T02:59:59Z"))).toEqual({ day: "2026-11-26", hour: 23 });
    expect(localTime(Date.parse("2026-11-27T03:00:00Z"))).toEqual({ day: "2026-11-27", hour: 0 });
  });
});

describe("noise", () => {
  it("stays from 0 up to 1, and differs between neighbouring seeds", () => {
    const values = Array.from({ length: 1000 }, (_, seed) => noise(seed));

    expect(Math.min(...values)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...values)).toBeLessThan(1);
    expect(new Set(values).size).toBe(1000);
  });
});

describe("hourKwh", () => {
  it("always gives the same value for the same plug and hour", () => {
    const hour = at("2026-11-26T10:00:00");

    expect(hourKwh(FRIDGE, hour, NOW)).toBe(hourKwh(FRIDGE, hour, NOW + 24 * HOUR_MS));
  });

  it("starts the history with the first tariff", () => {
    const first = at(`${FIRST_DAY}T00:00:00`);

    expect(FIRST_DAY).toBe(TARIFFS[0]?.valid_from);
    expect(hourKwh(FRIDGE, first, NOW)).toBeDefined();
    expect(hourKwh(FRIDGE, first - HOUR_MS, NOW)).toBeUndefined();
  });

  it("has nothing for an hour that has not started", () => {
    expect(hourKwh(FRIDGE, at("2026-11-26T16:00:00"), NOW)).toBeUndefined();
    expect(hourKwh(FRIDGE, NOW, NOW)).toBeUndefined();
  });

  it("counts only the part of the current hour that has passed", () => {
    const hour = at("2026-11-26T15:00:00");
    const whole = hourKwh(FRIDGE, hour, hour + HOUR_MS) ?? Number.NaN;

    expect(hourKwh(FRIDGE, hour, NOW)).toBeCloseTo(whole / 2, 10);
  });

  it("keeps the fridge within its range all day", () => {
    for (let hour = 0; hour < 24; hour++) {
      const kwh = hourKwh(FRIDGE, at("2026-11-25T00:00:00") + hour * HOUR_MS, NOW);

      expect(kwh).toBeGreaterThanOrEqual(0.038);
      expect(kwh).toBeLessThan(0.128);
    }
  });

  it("has a desk that is busy on a working morning and idle at night", () => {
    expect(hourKwh(DESK, at("2026-11-25T10:00:00"), NOW)).toBeGreaterThanOrEqual(0.11);
    expect(hourKwh(DESK, at("2026-11-25T03:00:00"), NOW)).toBeLessThan(0.01);
  });

  it("leaves the desk idle on the morning of a day off", () => {
    expect(hourKwh(DESK, at("2026-11-22T10:00:00"), NOW)).toBeLessThan(0.01); // a Sunday
    expect(hourKwh(DESK, at("2026-11-02T10:00:00"), NOW)).toBeLessThan(0.01); // a holiday
  });

  it("has data for every plug in the list", () => {
    for (const outlet of OUTLETS) {
      expect(hourKwh(outlet.id, at("2026-11-25T10:00:00"), NOW)).toBeGreaterThan(0);
    }
  });
});
