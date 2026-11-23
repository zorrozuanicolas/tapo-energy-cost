import type { Band, Bucket, Granularity, Outlet } from "../types";
import { outletColor } from "./colors";
import { fmtKwh, fmtMoney, fmtNumber } from "./format";
import { cap, dayName, dayShort, monthName, monthShort } from "./names";
import { parseDate } from "./period";
import { sumValues, valueFor } from "./values";

/**
 * The maths behind the consumption chart: the scale, and what every slot (one per hour, day or month)
 * shows. The component only draws the result.
 */

/** "all" overlays every plug; a number shows only the plug with that id. */
export type ChartMode = "all" | number;

export const BAND_LABEL: Record<Band, string> = { valle: "Valle", llano: "Llano", punta: "Punta" };

export interface Tick {
  label: string;
  /** Distance from the bottom of the plot, 0 to 100. */
  pct: number;
}

export interface Scale {
  /** The value at the top of the plot: a round number at or above the data. */
  top: number;
  ticks: Tick[];
}

const STEPS = [1, 2, 5, 10];

/** A round axis maximum and its tick marks, about four of them. */
export function niceScale(maxValue: number): Scale {
  const max = maxValue > 0 ? maxValue : 0.1; // an empty chart still gets an axis
  const raw = max / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const step = (STEPS.find((candidate) => normalized <= candidate) ?? 10) * magnitude;
  const count = Math.max(1, Math.ceil(max / step - 1e-9)); // the epsilon absorbs float noise in max / step
  const decimals = Math.min(4, Math.max(0, -Math.floor(Math.log10(step))));
  const ticks = Array.from({ length: count + 1 }, (_, i) => ({
    label: fmtNumber(step * i, decimals),
    pct: (i / count) * 100,
  }));
  return { top: step * count, ticks };
}

const pad = (n: number) => String(n).padStart(2, "0");

export interface BucketText {
  /** Under the bar. Empty when the axis would be too crowded. */
  label: string;
  /** The first line of the tooltip. */
  title: string;
  /** The second line of the tooltip. Empty when there is nothing to add. */
  sub: string;
}

/** The texts of one slot. A bucket's `start` carries the local date and hour, so they are read as written. */
export function describeBucket(bucket: Bucket, granularity: Granularity): BucketText {
  const date = parseDate(bucket.start);

  if (granularity === "hour") {
    const hour = Number(bucket.start.slice(11, 13));
    const parts: string[] = [];
    if (bucket.band && bucket.rate_per_kwh !== null) {
      parts.push(`${BAND_LABEL[bucket.band]} · $ ${fmtNumber(bucket.rate_per_kwh, 3)} por kWh`);
    }
    if (bucket.partial) parts.push("En curso");
    return {
      label: hour % 3 === 0 ? pad(hour) : "",
      title: `${pad(hour)}:00 – ${pad((hour + 1) % 24)}:00`,
      sub: parts.join(" · "),
    };
  }

  const sub = bucket.partial ? "En curso" : "";
  if (granularity === "day") {
    const day = date.getUTCDate();
    return {
      label: `${cap(dayShort(date.getUTCDay()))} ${day}`,
      title: `${cap(dayName(date.getUTCDay()))} ${day} de ${monthName(date.getUTCMonth())}`,
      sub,
    };
  }
  return {
    label: cap(monthShort(date.getUTCMonth())),
    title: `${cap(monthName(date.getUTCMonth()))} ${date.getUTCFullYear()}`,
    sub,
  };
}

/** One line of the tooltip. */
export interface TipRow {
  name: string;
  /** The colour of the dot; null for the total, which has none. */
  color: string | null;
  kwhText: string;
  cost: string;
  bold: boolean;
}

export interface Bar {
  color: string;
  /** Percent of the slot's bar area. */
  width: number;
  /** Percent of the plot height. */
  height: number;
}

export interface ChartSlot extends BucketText {
  key: string;
  hasData: boolean;
  band: Band | null;
  bars: Bar[];
  rows: TipRow[];
  /** What a screen reader says for the slot. */
  aria: string;
}

export interface ChartModel extends Scale {
  slots: ChartSlot[];
}

export function buildChart(
  buckets: readonly Bucket[],
  outlets: readonly Outlet[],
  mode: ChartMode,
  granularity: Granularity,
): ChartModel {
  // Keep the index in the full list: a plug keeps its colour whichever plugs are shown.
  const visible = outlets
    .map((outlet, index) => ({ outlet, index }))
    .filter(({ outlet }) => mode === "all" || mode === outlet.id);
  const shown = visible.map(({ outlet }) => outlet);
  const decimals = granularity === "hour" ? 3 : 2;
  const kwhText = (kwh: number) => `${fmtKwh(kwh, decimals)} kWh`;

  let maxValue = 0;
  for (const bucket of buckets) {
    if (!bucket.has_data) continue;
    for (const outlet of shown) maxValue = Math.max(maxValue, valueFor(bucket.outlets, outlet.id).kwh);
  }
  const scale = niceScale(maxValue);

  const slots = buckets.map((bucket): ChartSlot => {
    const text = describeBucket(bucket, granularity);

    if (!bucket.has_data) {
      return {
        ...text,
        key: bucket.start,
        hasData: false,
        band: bucket.band,
        bars: [],
        rows: [],
        aria: `${text.title}: sin datos`,
      };
    }

    const rows: TipRow[] = visible.map(({ outlet, index }) => {
      const value = valueFor(bucket.outlets, outlet.id);
      return {
        name: outlet.name,
        color: outletColor(index),
        kwhText: kwhText(value.kwh),
        cost: fmtMoney(value.cost),
        bold: false,
      };
    });
    if (mode === "all" && shown.length > 1) {
      const total = sumValues(shown, bucket.outlets);
      rows.push({ name: "Total", color: null, kwhText: kwhText(total.kwh), cost: fmtMoney(total.cost), bold: true });
    }

    // Overlaid bars: the biggest is the widest and sits at the back, the smaller ones in front of it.
    const bars = visible
      .map(({ outlet, index }) => ({ color: outletColor(index), kwh: valueFor(bucket.outlets, outlet.id).kwh }))
      .toSorted((a, b) => b.kwh - a.kwh)
      .map(({ color, kwh }, rank, all) => ({
        color,
        width: (100 * (all.length - rank)) / all.length,
        height: (kwh / scale.top) * 100,
      }));

    return {
      ...text,
      key: bucket.start,
      hasData: true,
      band: bucket.band,
      bars,
      rows,
      aria: `${text.title}: ${rows.map((row) => `${row.name} ${row.kwhText}, ${row.cost}`).join("; ")}`,
    };
  });

  return { ...scale, slots };
}
