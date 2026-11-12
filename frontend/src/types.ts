/**
 * Shapes of the JSON the backend sends. They mirror the response models in
 * `backend/app/schemas.py`: when one changes, change the other.
 */

export type Granularity = "hour" | "day" | "month";
export type Band = "valle" | "llano" | "punta";

export interface Outlet {
  id: number;
  slug: string;
  name: string;
}

export interface Health {
  status: "ok";
  outlets: Outlet[];
}

export interface OutletValue {
  kwh: number;
  cost: number; // pesos, VAT included
}

export interface Bucket {
  start: string; // ISO 8601 with the local UTC offset, e.g. 2026-10-22T14:00:00-03:00
  end: string;
  has_data: boolean;
  partial: boolean; // the hour, day or month is still in progress
  band: Band | null; // hour granularity only
  rate_per_kwh: number | null; // hour granularity only, VAT included
  // JSON object keys are always strings, so the outlet ids (integers in the backend) arrive as strings.
  outlets: Record<string, OutletValue>;
}

/** The holiday list has no entry for `year`, so holidays are priced as business days. */
export interface MissingHolidaysWarning {
  code: "missing_holidays";
  year: number;
}

/** Some hours are before the first tariff, so they have no cost. */
export interface NoTariffWarning {
  code: "no_tariff";
  since: string; // first affected local day, YYYY-MM-DD
}

export type ApiWarning = MissingHolidaysWarning | NoTariffWarning;

export interface ConsumptionResponse {
  granularity: Granularity;
  timezone: string;
  outlets: Outlet[];
  buckets: Bucket[];
  totals: Record<string, OutletValue>; // keyed by outlet id, like Bucket.outlets
  warnings: ApiWarning[];
}

export interface Tariff {
  valid_from: string; // YYYY-MM-DD
  vat: number;
  peak_start: number;
  peak_end: number;
  rates: Record<Band, number>; // without VAT
  rates_with_vat: Record<Band, number>;
}

export interface DataRange {
  earliest: string | null; // first local day with data, null if the database is empty
}

/** One event of the live stream (`/api/live`): the state of a plug at one moment. */
export interface LiveReading {
  outlet_id: number;
  power_w: number | null; // null when the plug could not be read
  online: boolean;
  ts: string; // ISO 8601, UTC
}
