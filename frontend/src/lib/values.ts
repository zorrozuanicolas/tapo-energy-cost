import type { ConsumptionResponse, Outlet, OutletValue } from "../types";
import type { View } from "./period";

/** What the API sends per plug: kWh and cost, keyed by the plug id written as a string. */
export type OutletValues = Record<string, OutletValue>;

/**
 * The values the cards and the list describe. The monthly view charts twelve months, but they
 * describe the selected one, which is the last bucket; the other views use the totals of the period.
 */
export const periodValues = (view: View, data: ConsumptionResponse): OutletValues =>
  view === "mensual" ? (data.buckets.at(-1)?.outlets ?? {}) : data.totals;

/** A plug with no entry used nothing in the period. */
const NO_VALUE: OutletValue = { kwh: 0, cost: 0 };

export const valueFor = (values: OutletValues, outletId: number): OutletValue => values[String(outletId)] ?? NO_VALUE;

/** The kWh and cost of all the given plugs together. */
export const sumValues = (outlets: readonly Outlet[], values: OutletValues): OutletValue =>
  outlets.reduce<OutletValue>(
    (sum, outlet) => {
      const value = valueFor(values, outlet.id);
      return { kwh: sum.kwh + value.kwh, cost: sum.cost + value.cost };
    },
    { kwh: 0, cost: 0 },
  );
