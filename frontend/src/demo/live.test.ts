import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LiveReading } from "../types";
import { HOUR_MS, hourKwh, OUTLETS } from "./history";
import { demoReading, LIVE_INTERVAL_MS, subscribeLive } from "./live";

const HOUR_START = Date.parse("2026-11-26T10:00:00-03:00");
const NOW = Date.parse("2026-11-26T10:20:00-03:00");

describe("demoReading", () => {
  it.each(OUTLETS)("stays within 5 % of the hour's average power for $name", ({ id }) => {
    const average = (hourKwh(id, HOUR_START, HOUR_START + HOUR_MS) ?? Number.NaN) * 1000;

    for (let seconds = 0; seconds < 3600; seconds += 60) {
      const watts = demoReading(id, HOUR_START + seconds * 1000).power_w ?? Number.NaN;

      expect(watts).toBeGreaterThanOrEqual(average * 0.95 - 0.1); // 0.1 W for the rounding
      expect(watts).toBeLessThanOrEqual(average * 1.05 + 0.1);
    }
  });

  it("describes an online plug at that moment", () => {
    expect(demoReading(1, NOW)).toMatchObject({ outlet_id: 1, online: true, ts: "2026-11-26T13:20:00.000Z" });
  });

  it("gives the same reading for the same moment, and moves with time", () => {
    const readings = Array.from({ length: 10 }, (_, i) => demoReading(2, NOW + i * LIVE_INTERVAL_MS).power_w);

    expect(demoReading(2, NOW)).toEqual(demoReading(2, NOW));
    expect(new Set(readings).size).toBeGreaterThan(1);
  });
});

describe("subscribeLive", () => {
  // A simulated clock: the test moves the time forward without waiting.
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("sends every plug at once and again after each interval, until stopped", () => {
    const received: LiveReading[] = [];
    const stop = subscribeLive((reading) => received.push(reading));

    expect(received.map((reading) => reading.outlet_id)).toEqual([1, 2]);

    vi.advanceTimersByTime(LIVE_INTERVAL_MS);
    expect(received).toHaveLength(4);
    expect(received[2]?.ts).toBe("2026-11-26T13:20:03.000Z");

    stop();
    vi.advanceTimersByTime(10 * LIVE_INTERVAL_MS);
    expect(received).toHaveLength(4);
  });
});
