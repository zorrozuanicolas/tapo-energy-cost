import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError, fetchConsumption, fetchTariff } from "./api";

function stubFetch(response: Response) {
  const fake = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fake);
  return fake;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("requests", () => {
  test("fetchConsumption sends the query and returns the parsed body", async () => {
    const body = {
      granularity: "day",
      timezone: "America/Montevideo",
      outlets: [],
      buckets: [],
      totals: {},
      warnings: [],
    };
    const fake = stubFetch(json(body));

    const result = await fetchConsumption("day", "2026-11-02", "2026-11-09");

    expect(fake).toHaveBeenCalledOnce();
    expect(fake.mock.calls[0]?.[0]).toBe("/api/consumption?granularity=day&from=2026-11-02&to=2026-11-09");
    expect(result).toEqual(body);
  });

  test("fetchTariff sends the date parameter", async () => {
    const fake = stubFetch(json({ vat: 0.22 }));

    await fetchTariff("2026-11-12");

    expect(fake.mock.calls[0]?.[0]).toBe("/api/tariff?date=2026-11-12");
  });

  test("the abort signal reaches fetch", async () => {
    const fake = stubFetch(json({ earliest: null }));
    const { fetchRange } = await import("./api");
    const controller = new AbortController();

    await fetchRange(controller.signal);

    expect(fake.mock.calls[0]?.[1]).toEqual({ signal: controller.signal });
  });
});

describe("errors", () => {
  test("an error with a detail becomes an ApiError that keeps it", async () => {
    stubFetch(json({ detail: "range too large" }, 400));

    const error = await fetchConsumption("hour", "2026-01-01", "2026-12-31").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 400,
      path: "/api/consumption",
      detail: "range too large",
      message: "/api/consumption respondió 400: range too large",
    });
  });

  test("an error without JSON (a proxy page) has no detail", async () => {
    stubFetch(new Response("<html>Bad Gateway</html>", { status: 502 }));

    const error = await fetchTariff("2026-11-12").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 502, detail: undefined, message: "/api/tariff respondió 502" });
  });
});

describe("VITE_API_URL", () => {
  test("is prefixed to the path and a trailing slash is dropped", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.example.com/");
    const fake = stubFetch(json({ earliest: null }));
    // BASE is read when the module loads, so load a fresh copy that sees the variable.
    const { fetchRange, apiUrl } = await import("./api");

    await fetchRange();

    expect(apiUrl("/api/range")).toBe("https://api.example.com/api/range");
    expect(fake.mock.calls[0]?.[0]).toBe("https://api.example.com/api/range");
  });
});
