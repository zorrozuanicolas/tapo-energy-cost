import { useEffect, useState } from "react";

import { apiUrl } from "../api";
import { type LiveReadings, parseLiveReading } from "../lib/live";

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
    const source = new EventSource(apiUrl("/api/live"));
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (event) => {
      const reading = parseLiveReading(event.data);
      if (reading) setReadings((current) => ({ ...current, [reading.outlet_id]: reading }));
    };
    return () => source.close();
  }, []);

  return { readings, connected };
}
