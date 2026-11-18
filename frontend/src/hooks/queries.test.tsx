// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api";
import { periodRange } from "../lib/period";
import type { ConsumptionResponse } from "../types";
import { useConsumption, useDataRange, useTariff } from "./queries";

const CONSUMPTION: ConsumptionResponse = {
  granularity: "hour",
  timezone: "America/Montevideo",
  outlets: [{ id: 1, slug: "heladera", name: "Heladera" }],
  buckets: [],
  totals: { "1": { kwh: 1.5, cost: 9.46 } },
  warnings: [],
};

const fetchMock = vi.fn<typeof fetch>();

const jsonResponse = (body: unknown, status = 200) => Response.json(body, { status });

/** The URLs requested so far, as "path?query" strings. */
const requested = () =>
  fetchMock.mock.calls.map(([input]) => {
    const url = new URL(String(input), "http://localhost");
    return url.pathname + url.search;
  });

let client: QueryClient;

// The client is created once per test (not inside the wrapper), so a re-render keeps its cache.
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  // A new cache per test, and no retries so an error shows up at once.
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("useConsumption", () => {
  const today = periodRange("hoy", 0, "2026-10-22");
  const yesterday = periodRange("hoy", -1, "2026-10-22");

  it("requests the range of the period and returns the data", async () => {
    fetchMock.mockResolvedValue(jsonResponse(CONSUMPTION));
    const { result } = renderHook(() => useConsumption(today, false), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(CONSUMPTION);
    expect(requested()).toEqual(["/api/consumption?granularity=hour&from=2026-10-22&to=2026-10-23"]);
  });

  it("fetches a new period but serves one it has already seen from the cache", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(CONSUMPTION));
    const { result, rerender } = renderHook(({ range }) => useConsumption(range, false), {
      wrapper,
      initialProps: { range: today },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    rerender({ range: yesterday });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(2);

    rerender({ range: today });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(2); // a finished period is never stale
  });

  it("reports an API error as an ApiError", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "rango no válido" }, 422));
    const { result } = renderHook(() => useConsumption(today, false), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error).toMatchObject({ status: 422, detail: "rango no válido" });
  });
});

describe("useTariff", () => {
  it("requests the tariff of a day", async () => {
    const tariff = { valid_from: "2026-01-01", vat: 1.22 };
    fetchMock.mockResolvedValue(jsonResponse(tariff));
    const { result } = renderHook(() => useTariff("2026-10-22"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(tariff);
    expect(requested()).toEqual(["/api/tariff?date=2026-10-22"]);
  });
});

describe("useDataRange", () => {
  it("requests the first day with data", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ earliest: "2026-10-01" }));
    const { result } = renderHook(() => useDataRange(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ earliest: "2026-10-01" });
    expect(requested()).toEqual(["/api/range"]);
  });
});
