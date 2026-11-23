import type { LiveReading } from "../types";

/** The latest reading of each plug, by plug id. */
export type LiveReadings = Record<number, LiveReading>;

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

/**
 * The data of one event of the live stream as a reading, or null when it is not one. The stream is outside
 * our control, so every field is checked instead of trusting the shape: one odd event must not break the page.
 */
export function parseLiveReading(data: unknown): LiveReading | null {
  if (typeof data !== "string") return null;

  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (!isObject(value)) return null;

  const { outlet_id, power_w, online, ts } = value;
  if (typeof outlet_id !== "number" || typeof online !== "boolean" || typeof ts !== "string") return null;
  if (power_w !== null && typeof power_w !== "number") return null;
  return { outlet_id, power_w, online, ts };
}
