/**
 * Fake hourly consumption for the demo, with the same shapes as `backend/app/seed.py`. Nothing is
 * stored: the value of an hour is calculated from the plug and the hour, so it never changes.
 */

import type { Outlet } from "../types";
import { isBusinessDay } from "./billing";

export const OUTLETS: Outlet[] = [
  { id: 1, slug: "heladera", name: "Heladera" },
  { id: 2, slug: "escritorio", name: "Escritorio" },
];

export const FIRST_DAY = "2026-01-01"; // the first day with data: where the first tariff starts
export const HOUR_MS = 3_600_000;
const UTC_OFFSET_HOURS = -3; // Montevideo, which has had no summer time since 2015
const FIRST_HOUR_MS = Date.parse(`${FIRST_DAY}T00:00:00-03:00`);

/** The Montevideo day (YYYY-MM-DD) and hour (0-23) of a moment. */
export function localTime(ms: number): { day: string; hour: number } {
  const shifted = new Date(ms + UTC_OFFSET_HOURS * HOUR_MS).toISOString();
  return { day: shifted.slice(0, 10), hour: Number(shifted.slice(11, 13)) };
}

/** A number from 0 up to 1 that looks random, but is always the same for the same seed. */
export function noise(seed: number): number {
  let x = Math.imul(seed ^ (seed >>> 16), 0x45d9f3b);
  x = Math.imul(x ^ (x >>> 16), 0x45d9f3b);
  return ((x ^ (x >>> 16)) >>> 0) / 4_294_967_296;
}

function fullHourKwh(outletId: number, hourStartMs: number): number {
  // Two different random numbers for each plug and hour.
  const seed = (hourStartMs / HOUR_MS) * 4 + outletId * 2;
  const first = noise(seed);
  const second = noise(seed + 1);

  if (outletId === 1) {
    // A fridge: steady, with small variations and the odd harder-working hour.
    return 0.038 + 0.04 * first + (second > 0.97 ? 0.05 : 0);
  }
  // A desk: busy during working hours, and some evening use on days off.
  const { day, hour } = localTime(hourStartMs);
  const active = isBusinessDay(day)
    ? (hour >= 9 && hour <= 13) || (hour >= 15 && hour <= 19) || (hour === 14 && second > 0.5)
    : hour >= 11 && hour <= 22 && second > 0.45;
  return active ? 0.11 + 0.1 * first : 0.004 + 0.004 * first;
}

/**
 * The energy of one plug in the hour that starts at `hourStartMs`, or undefined if there is no data:
 * before the history starts, or in the future. The hour in progress has only the part that has passed.
 */
export function hourKwh(outletId: number, hourStartMs: number, nowMs: number): number | undefined {
  if (hourStartMs < FIRST_HOUR_MS || hourStartMs >= nowMs) return undefined;
  const elapsed = Math.min(1, (nowMs - hourStartMs) / HOUR_MS);
  return fullHourKwh(outletId, hourStartMs) * elapsed;
}
