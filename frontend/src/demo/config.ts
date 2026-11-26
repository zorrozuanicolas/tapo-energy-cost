import type { Tariff } from "../types";

/** A copy of `config/tariffs.yaml`, oldest first. `config.test.ts` fails if the two differ. */
export type DemoTariff = Omit<Tariff, "rates_with_vat">;

export const TARIFFS: DemoTariff[] = [
  {
    valid_from: "2026-01-01",
    vat: 1.22,
    peak_start: 17,
    peak_end: 21,
    rates: { punta: 12.034, llano: 5.172, valle: 2.443 },
  },
];

/** The dates in `config/holidays.yaml`. */
export const HOLIDAYS: ReadonlySet<string> = new Set([
  "2026-01-01",
  "2026-01-06",
  "2026-02-16",
  "2026-02-17",
  "2026-04-02",
  "2026-04-03",
  "2026-04-19",
  "2026-05-01",
  "2026-05-18",
  "2026-06-19",
  "2026-07-18",
  "2026-08-25",
  "2026-10-12",
  "2026-11-02",
  "2026-12-25",
]);
