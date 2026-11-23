import { describe, expect, it } from "vitest";
import type { Bucket, Outlet } from "../types";
import { buildChart, describeBucket, niceScale } from "./chart";

const FRIDGE: Outlet = { id: 1, slug: "heladera", name: "Heladera" };
const DESK: Outlet = { id: 2, slug: "escritorio", name: "Escritorio" };

const hourly = (overrides: Partial<Bucket> = {}): Bucket => ({
  start: "2026-10-22T14:00:00-03:00",
  end: "2026-10-22T15:00:00-03:00",
  has_data: true,
  partial: false,
  band: "llano",
  rate_per_kwh: 6.5,
  outlets: {},
  ...overrides,
});

describe("niceScale", () => {
  it("rounds the top up to a round number", () => {
    const { top, ticks } = niceScale(0.37);
    expect(top).toBeCloseTo(0.4);
    expect(ticks.map((tick) => tick.label)).toEqual(["0,0", "0,1", "0,2", "0,3", "0,4"]);
  });

  it("puts the ticks at even distances, from 0 to 100", () => {
    expect(niceScale(10).ticks.map((tick) => tick.pct)).toEqual([0, 50, 100]);
  });

  it("writes whole numbers without decimals", () => {
    expect(niceScale(10).ticks.map((tick) => tick.label)).toEqual(["0", "5", "10"]);
  });

  it("never puts the top below the data", () => {
    for (const max of [0.0123, 0.5, 1, 1.2, 7, 33, 480]) {
      expect(niceScale(max).top).toBeGreaterThanOrEqual(max);
    }
  });

  it("still gives an axis when there is no data", () => {
    for (const max of [0, -1]) {
      const { top, ticks } = niceScale(max);
      expect(top).toBeCloseTo(0.1);
      expect(ticks.length).toBeGreaterThan(1);
    }
  });
});

describe("describeBucket", () => {
  it("names an hour and says its band and rate", () => {
    expect(describeBucket(hourly({ band: "valle", rate_per_kwh: 4.123 }), "hour")).toEqual({
      label: "",
      title: "14:00 – 15:00",
      sub: "Valle · $ 4,123 por kWh",
    });
  });

  it("labels only every third hour on the axis", () => {
    const label = (hour: number) =>
      describeBucket(hourly({ start: `2026-10-22T${String(hour).padStart(2, "0")}:00:00-03:00` }), "hour").label;
    expect([0, 1, 2, 3, 15, 22, 23].map(label)).toEqual(["00", "", "", "03", "15", "", ""]);
  });

  it("closes the last hour of the day at 00:00", () => {
    expect(describeBucket(hourly({ start: "2026-10-22T23:00:00-03:00" }), "hour").title).toBe("23:00 – 00:00");
  });

  it("adds that the hour is in progress", () => {
    expect(describeBucket(hourly({ partial: true }), "hour").sub).toBe("Llano · $ 6,500 por kWh · En curso");
  });

  it("has no second line for a finished hour without a band", () => {
    expect(describeBucket(hourly({ band: null, rate_per_kwh: null }), "hour").sub).toBe("");
  });

  it("names a day", () => {
    const day = hourly({ start: "2026-10-22T00:00:00-03:00", band: null, rate_per_kwh: null });
    expect(describeBucket(day, "day")).toEqual({ label: "Jue 22", title: "Jueves 22 de octubre", sub: "" });
    expect(describeBucket({ ...day, partial: true }, "day").sub).toBe("En curso");
  });

  it("names a month", () => {
    const month = hourly({ start: "2026-10-01T00:00:00-03:00", band: null, rate_per_kwh: null });
    expect(describeBucket(month, "month")).toEqual({ label: "Oct", title: "Octubre 2026", sub: "" });
  });
});

describe("buildChart", () => {
  const both = hourly({
    outlets: { "1": { kwh: 1, cost: 6 }, "2": { kwh: 0.5, cost: 3 } },
  });

  it("overlays the plugs, the biggest widest and first", () => {
    const [slot] = buildChart([both], [FRIDGE, DESK], "all", "hour").slots;
    expect(slot?.bars).toEqual([
      { color: "var(--color-outlet-1)", width: 100, height: 100 },
      { color: "var(--color-outlet-2)", width: 50, height: 50 },
    ]);
  });

  it("keeps each plug's colour whatever its size", () => {
    const swapped = hourly({ outlets: { "1": { kwh: 0.5, cost: 3 }, "2": { kwh: 1, cost: 6 } } });
    const [slot] = buildChart([swapped], [FRIDGE, DESK], "all", "hour").slots;
    expect(slot?.bars.map((bar) => bar.color)).toEqual(["var(--color-outlet-2)", "var(--color-outlet-1)"]);
  });

  it("lists every plug and a total in the tooltip", () => {
    const [slot] = buildChart([both], [FRIDGE, DESK], "all", "hour").slots;
    expect(slot?.rows).toEqual([
      { name: "Heladera", color: "var(--color-outlet-1)", kwhText: "1,000 kWh", cost: "$ 6,00", bold: false },
      { name: "Escritorio", color: "var(--color-outlet-2)", kwhText: "0,500 kWh", cost: "$ 3,00", bold: false },
      { name: "Total", color: null, kwhText: "1,500 kWh", cost: "$ 9,00", bold: true },
    ]);
  });

  it("gives every slot a spoken description", () => {
    const [slot] = buildChart([both], [FRIDGE, DESK], "all", "hour").slots;
    expect(slot?.aria).toBe(
      "14:00 – 15:00: Heladera 1,000 kWh, $ 6,00; Escritorio 0,500 kWh, $ 3,00; Total 1,500 kWh, $ 9,00",
    );
  });

  it("shows only the chosen plug, without a total, and scales to it", () => {
    const model = buildChart([both], [FRIDGE, DESK], 2, "hour");
    const [slot] = model.slots;
    expect(slot?.rows.map((row) => row.name)).toEqual(["Escritorio"]);
    expect(slot?.bars).toHaveLength(1);
    expect(slot?.bars[0]?.width).toBe(100);
    expect(model.top).toBeCloseTo(0.6); // the fridge's 1 kWh does not count
    expect(slot?.bars[0]?.height).toBeCloseTo(83.33, 1);
  });

  it("has no total row for a single plug", () => {
    const [slot] = buildChart([both], [FRIDGE], "all", "hour").slots;
    expect(slot?.rows.map((row) => row.name)).toEqual(["Heladera"]);
  });

  it("counts a plug with no entry as zero", () => {
    const only = hourly({ outlets: { "1": { kwh: 1, cost: 6 } } });
    const [slot] = buildChart([only], [FRIDGE, DESK], "all", "hour").slots;
    expect(slot?.rows[1]).toMatchObject({ name: "Escritorio", kwhText: "0,000 kWh", cost: "$ 0,00" });
    expect(slot?.bars.at(-1)?.height).toBe(0);
  });

  it("draws nothing for a bucket without data, and says so", () => {
    const empty = hourly({ has_data: false, band: null, rate_per_kwh: null });
    const [slot] = buildChart([empty], [FRIDGE, DESK], "all", "hour").slots;
    expect(slot).toMatchObject({ hasData: false, bars: [], rows: [], aria: "14:00 – 15:00: sin datos" });
  });

  it("ignores a bucket without data when it picks the scale", () => {
    const stale = hourly({ has_data: false, outlets: { "1": { kwh: 99, cost: 0 } } });
    expect(buildChart([stale], [FRIDGE], "all", "hour").top).toBeCloseTo(0.1);
  });

  it("writes two decimals for days and months, three for hours", () => {
    const day = hourly({ start: "2026-10-22T00:00:00-03:00", outlets: { "1": { kwh: 1.5, cost: 9 } } });
    expect(buildChart([day], [FRIDGE], "all", "day").slots[0]?.rows[0]?.kwhText).toBe("1,50 kWh");
    expect(buildChart([day], [FRIDGE], "all", "hour").slots[0]?.rows[0]?.kwhText).toBe("1,500 kWh");
  });

  it("keeps the band and uses the start as the key", () => {
    const [slot] = buildChart([both], [FRIDGE], "all", "hour").slots;
    expect(slot).toMatchObject({ band: "llano", key: "2026-10-22T14:00:00-03:00" });
  });

  it("gives an empty list for no buckets", () => {
    expect(buildChart([], [FRIDGE], "all", "hour").slots).toEqual([]);
  });
});
