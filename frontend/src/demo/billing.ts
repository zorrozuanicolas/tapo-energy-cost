/**
 * The tariff rules of `backend/app/billing.py`, for the demo that runs without a backend. A change
 * to the rules there must be made here too.
 */

import type { Band } from "../types";
import { type DemoTariff, HOLIDAYS, TARIFFS } from "./config";

const VALLE_END_HOUR = 7; // Valle is always 00:00 - 07:00

/** The tariff in force on a local day (YYYY-MM-DD), or undefined before the first one. */
export function tariffFor(day: string, tariffs: DemoTariff[] = TARIFFS): DemoTariff | undefined {
  return tariffs.findLast((tariff) => tariff.valid_from <= day);
}

export function isBusinessDay(day: string): boolean {
  const weekday = new Date(`${day}T00:00:00Z`).getUTCDay(); // 0 is Sunday, 6 is Saturday
  return weekday !== 0 && weekday !== 6 && !HOLIDAYS.has(day);
}

/** The band of a local hour (0-23) on a local day. */
export function bandFor(day: string, hour: number, tariff: DemoTariff): Band {
  if (hour < VALLE_END_HOUR) return "valle";
  const inPeak = hour >= tariff.peak_start && hour < tariff.peak_end;
  return inPeak && isBusinessDay(day) ? "punta" : "llano";
}

export function rateWithVat(tariff: DemoTariff, band: Band): number {
  return tariff.rates[band] * tariff.vat;
}

/** Without a holiday list for a year, its holidays are priced as business days. */
export function hasHolidaysFor(year: number): boolean {
  return [...HOLIDAYS].some((day) => day.startsWith(`${year}-`));
}
