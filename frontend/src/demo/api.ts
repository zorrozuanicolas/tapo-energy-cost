/**
 * The fake backend of the demo: it answers with the same shapes as the real one, priced as
 * `backend/app/aggregation.py` does, from the made-up hours of `history.ts`.
 */

import { ApiError } from "../api";
import { addDays, addMonths } from "../lib/period";
import type { Bucket, ConsumptionResponse, DataRange, Granularity, OutletValue, Tariff } from "../types";
import { bandFor, hasHolidaysFor, rateWithVat, tariffFor } from "./billing";
import { FIRST_DAY, HOUR_MS, hourKwh, localTime, OUTLETS } from "./history";

const midnight = (day: string) => Date.parse(`${day}T00:00:00-03:00`);
const round = (value: number, digits: number) => Number(value.toFixed(digits));

/** A moment written as the backend does: local time with its offset. */
function isoLocal(ms: number): string {
  const { day, hour } = localTime(ms);
  return `${day}T${String(hour).padStart(2, "0")}:00:00-03:00`;
}

export const demoRange = (): DataRange => ({ earliest: FIRST_DAY });

export function demoTariff(date: string): Tariff {
  const tariff = tariffFor(date);
  if (!tariff) throw new ApiError(404, "/api/tariff", `No tariff configured for ${date}`);
  return {
    ...tariff,
    rates_with_vat: {
      punta: round(rateWithVat(tariff, "punta"), 4),
      llano: round(rateWithVat(tariff, "llano"), 4),
      valle: round(rateWithVat(tariff, "valle"), 4),
    },
  };
}

interface Span {
  start: number;
  end: number;
}

/** The hours, days or months of the local range [from, to). Months are always whole. */
function spans(granularity: Granularity, from: string, to: string): Span[] {
  const result: Span[] = [];
  if (granularity === "hour") {
    for (let start = midnight(from); start < midnight(to); start += HOUR_MS) {
      result.push({ start, end: start + HOUR_MS });
    }
    return result;
  }
  const step = granularity === "day" ? addDays : addMonths;
  for (let day = granularity === "day" ? from : addMonths(from, 0); day < to; day = step(day, 1)) {
    result.push({ start: midnight(day), end: midnight(step(day, 1)) });
  }
  return result;
}

/** One value per plug, in the order of `OUTLETS`, keyed by plug id and rounded as the backend does. */
function byOutlet(values: OutletValue[]): Record<string, OutletValue> {
  return Object.fromEntries(
    OUTLETS.map((outlet, i) => [
      outlet.id,
      { kwh: round(values[i]?.kwh ?? 0, 6), cost: round(values[i]?.cost ?? 0, 4) },
    ]),
  );
}

const zeros = () => OUTLETS.map(() => ({ kwh: 0, cost: 0 }));

/** kWh and cost (VAT included) of each plug for each hour, day or month of [from, to). */
export function demoConsumption(
  granularity: Granularity,
  from: string,
  to: string,
  nowMs: number = Date.now(),
): ConsumptionResponse {
  // Rounded only at the end, so the totals do not drift from the data.
  const totals = zeros();
  const pricedYears = new Set<number>();

  const buckets = spans(granularity, from, to).map(({ start, end }): Bucket => {
    const sums = zeros();
    let hasData = false;
    // Every hour is priced on its own, with its tariff and band, then added up.
    for (let hour = start; hour < end; hour += HOUR_MS) {
      const local = localTime(hour);
      const tariff = tariffFor(local.day);
      OUTLETS.forEach((outlet, i) => {
        const kwh = hourKwh(outlet.id, hour, nowMs);
        const sum = sums[i];
        const total = totals[i];
        // The history starts with the first tariff, so an hour with data always has one.
        if (kwh === undefined || !tariff || !sum || !total) return;
        const cost = kwh * rateWithVat(tariff, bandFor(local.day, local.hour, tariff));
        sum.kwh += kwh;
        sum.cost += cost;
        total.kwh += kwh;
        total.cost += cost;
        hasData = true;
        pricedYears.add(Number(local.day.slice(0, 4)));
      });
    }

    // Only an hour has one band and one price.
    const local = localTime(start);
    const tariff = granularity === "hour" ? tariffFor(local.day) : undefined;
    const band = tariff ? bandFor(local.day, local.hour, tariff) : null;
    return {
      start: isoLocal(start),
      end: isoLocal(end),
      has_data: hasData,
      partial: start <= nowMs && nowMs < end,
      band,
      rate_per_kwh: tariff && band ? round(rateWithVat(tariff, band), 4) : null,
      outlets: byOutlet(sums),
    };
  });

  return {
    granularity,
    timezone: "America/Montevideo",
    outlets: OUTLETS,
    buckets,
    totals: byOutlet(totals),
    warnings: [...pricedYears]
      .filter((year) => !hasHolidaysFor(year))
      .sort()
      .map((year) => ({ code: "missing_holidays", year })),
  };
}
