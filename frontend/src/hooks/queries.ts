import { useQuery } from "@tanstack/react-query";

import { fetchConsumption, fetchRange, fetchTariff } from "../api";
import type { PeriodRange } from "../lib/period";

const SECOND = 1_000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

/**
 * Consumption of a period. The current period is refreshed while the page is open; a past
 * period never changes, so it is fetched once and then served from the cache.
 */
export function useConsumption(range: PeriodRange, isCurrent: boolean) {
  return useQuery({
    queryKey: ["consumption", range.granularity, range.from, range.to],
    // `signal` aborts the request when the user moves to another period before it finishes.
    queryFn: ({ signal }) => fetchConsumption(range.granularity, range.from, range.to, signal),
    refetchInterval: isCurrent ? 30 * SECOND : false,
    staleTime: isCurrent ? 10 * SECOND : Number.POSITIVE_INFINITY,
  });
}

/** The tariff in force on a day (YYYY-MM-DD). It changes rarely, so it is cached for an hour. */
export function useTariff(date: string) {
  return useQuery({
    queryKey: ["tariff", date],
    queryFn: ({ signal }) => fetchTariff(date, signal),
    staleTime: HOUR,
  });
}

/** The first day with data, which is as far back as the navigator may go. */
export function useDataRange() {
  return useQuery({
    queryKey: ["range"],
    queryFn: ({ signal }) => fetchRange(signal),
    staleTime: 5 * MINUTE,
  });
}
