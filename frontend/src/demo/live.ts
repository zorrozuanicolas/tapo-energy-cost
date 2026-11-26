/** The live power of the demo: a timer in place of the backend's stream. */

import type { LiveReading } from "../types";
import { HOUR_MS, hourKwh, noise, OUTLETS } from "./history";

export const LIVE_INTERVAL_MS = 3000;

/** A made-up reading: the average power of the current hour, moving a little around it. */
export function demoReading(outletId: number, nowMs: number): LiveReading {
  const hourStart = nowMs - (nowMs % HOUR_MS);
  const wholeHour = hourKwh(outletId, hourStart, hourStart + HOUR_MS) ?? 0;
  const wobble = 0.95 + 0.1 * noise(Math.floor(nowMs / 1000) + outletId); // up to 5 % either way
  return {
    outlet_id: outletId,
    power_w: Math.round(wholeHour * 1000 * wobble * 10) / 10,
    online: true,
    ts: new Date(nowMs).toISOString(),
  };
}

/** Sends a reading of every plug now and then every few seconds. Returns a function that stops it. */
export function subscribeLive(onReading: (reading: LiveReading) => void): () => void {
  const send = () => {
    for (const outlet of OUTLETS) onReading(demoReading(outlet.id, Date.now()));
  };
  send();
  const timer = setInterval(send, LIVE_INTERVAL_MS);
  return () => clearInterval(timer);
}
