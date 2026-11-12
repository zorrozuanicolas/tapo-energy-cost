import type { ConsumptionResponse, DataRange, Granularity, Health, Outlet, Tariff } from "./types";

// Empty in development and behind one proxy (same origin); the backend URL when it is elsewhere.
const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export const apiUrl = (path: string) => `${BASE}${path}`;

/** The backend answered with an error status. `detail` is its explanation, when it sent one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly detail?: string,
  ) {
    super(detail ? `${path} respondió ${status}: ${detail}` : `${path} respondió ${status}`);
    this.name = "ApiError";
  }
}

/** FastAPI sends errors as {"detail": "..."}; anything else (a proxy error page) has no detail. */
async function errorDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON.
  }
  return undefined;
}

async function get<T>(path: string, params?: Record<string, string>, signal?: AbortSignal): Promise<T> {
  const query = params ? `?${new URLSearchParams(params).toString()}` : "";
  const response = await fetch(apiUrl(path) + query, { signal });
  if (!response.ok) {
    throw new ApiError(response.status, path, await errorDetail(response));
  }
  return (await response.json()) as T;
}

export const fetchHealth = (signal?: AbortSignal) => get<Health>("/api/health", undefined, signal);

export const fetchOutlets = (signal?: AbortSignal) => get<Outlet[]>("/api/outlets", undefined, signal);

export const fetchRange = (signal?: AbortSignal) => get<DataRange>("/api/range", undefined, signal);

export const fetchTariff = (date: string, signal?: AbortSignal) => get<Tariff>("/api/tariff", { date }, signal);

export const fetchConsumption = (granularity: Granularity, from: string, to: string, signal?: AbortSignal) =>
  get<ConsumptionResponse>("/api/consumption", { granularity, from, to }, signal);
