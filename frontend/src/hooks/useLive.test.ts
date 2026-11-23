// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiUrl } from "../api";
import type { LiveReading } from "../types";
import { useLive } from "./useLive";

/** Stands in for the browser's EventSource: the test decides what the server sends. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  readonly close = vi.fn();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  send(data: string) {
    act(() => this.onmessage?.(new MessageEvent("message", { data })));
  }
}

const source = () => {
  const [first] = FakeEventSource.instances;
  if (!first) throw new Error("No EventSource was created");
  return first;
};

const reading = (overrides: Partial<LiveReading> = {}): LiveReading => ({
  outlet_id: 1,
  power_w: 80,
  online: true,
  ts: "2026-11-23T15:00:00Z",
  ...overrides,
});

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useLive", () => {
  it("opens the live stream of the API, once", () => {
    renderHook(() => useLive());
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(source().url).toBe(apiUrl("/api/live"));
  });

  it("starts with no readings and not connected", () => {
    const { result } = renderHook(() => useLive());
    expect(result.current).toEqual({ readings: {}, connected: false });
  });

  it("is connected while the stream is open", () => {
    const { result } = renderHook(() => useLive());
    act(() => source().onopen?.());
    expect(result.current.connected).toBe(true);
    act(() => source().onerror?.());
    expect(result.current.connected).toBe(false);
    act(() => source().onopen?.()); // the browser reconnected by itself
    expect(result.current.connected).toBe(true);
  });

  it("keeps the latest reading of each plug", () => {
    const { result } = renderHook(() => useLive());
    source().send(JSON.stringify(reading({ outlet_id: 1, power_w: 80 })));
    source().send(JSON.stringify(reading({ outlet_id: 2, power_w: 5 })));
    source().send(JSON.stringify(reading({ outlet_id: 1, power_w: 95 })));
    expect(result.current.readings).toEqual({
      1: reading({ outlet_id: 1, power_w: 95 }),
      2: reading({ outlet_id: 2, power_w: 5 }),
    });
  });

  it("keeps a plug that went offline, with no power", () => {
    const { result } = renderHook(() => useLive());
    const offline = reading({ power_w: null, online: false });
    source().send(JSON.stringify(offline));
    expect(result.current.readings[1]).toEqual(offline);
  });

  it("ignores events that are not readings", () => {
    const { result } = renderHook(() => useLive());
    source().send("{oops");
    source().send(JSON.stringify({ outlet_id: "1" }));
    expect(result.current.readings).toEqual({});
  });

  it("closes the stream when the component goes away", () => {
    const { unmount } = renderHook(() => useLive());
    expect(source().close).not.toHaveBeenCalled();
    unmount();
    expect(source().close).toHaveBeenCalledOnce();
  });
});
