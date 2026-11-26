import { useEffect, useState } from "react";

import { apiUrl } from "../api";
import { subscribeLive } from "../demo/live";
import { type LiveReadings, parseLiveReading } from "../lib/live";
import type { LiveReading } from "../types";

export interface Live {
  /** The latest reading of each plug, by plug id. Empty until the first one arrives. */
  readings: LiveReadings;
  /** Whether the stream is open. When it drops the readings are old, so they should not be shown as current. */
  connected: boolean;
}

/**
 * The live power of the plugs, from the Server-Sent Events stream. The browser reconnects by itself after a
 * drop, and the server then sends the latest reading of each plug again.
 */
export function useLive(): Live {
  const [readings, setReadings] = useState<LiveReadings>({});
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const receive = (reading: LiveReading) => setReadings((current) => ({ ...current, [reading.outlet_id]: reading }));

    if (import.meta.env.VITE_DEMO === "true") {
      setConnected(true);
      return subscribeLive(receive); // returns the function that stops the timer
    }
    const source = new EventSource(apiUrl("/api/live"));
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (event) => {
      const reading = parseLiveReading(event.data);
      if (reading) receive(reading);
    };
    return () => source.close();
  }, []);

  return { readings, connected };
}
