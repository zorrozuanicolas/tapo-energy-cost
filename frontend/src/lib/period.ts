import type { Granularity } from "../types";
import { cap, dayName, monthName } from "./names";

/**
 * Period maths. Dates are "civil dates" written as YYYY-MM-DD and handled in UTC, so the
 * result never depends on the time zone of the browser.
 */

/** The three tabs. The names are Spanish because they are also the labels the user sees. */
export type View = "hoy" | "semanal" | "mensual";

export interface PeriodRange {
  view: View;
  granularity: Granularity;
  from: string; // inclusive
  to: string; // exclusive
  ref: string; // the day (hoy, semanal) or the first day of the month (mensual) being looked at
}

const DAY_MS = 86_400_000;

/** Reads the date at the start of `value`, so an ISO datetime such as a bucket's `start` works too. */
export function parseDate(value: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) throw new RangeError(`Not a YYYY-MM-DD date: ${value}`);
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

const toIso = (date: Date) => date.toISOString().slice(0, 10);

export const addDays = (value: string, days: number) => toIso(new Date(parseDate(value).getTime() + days * DAY_MS));

/** First day of the month that is `months` away from the month of `value`. */
export function addMonths(value: string, months: number): string {
  const date = parseDate(value);
  return toIso(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + months, 1)));
}

/** The Monday of the week that contains `value` (weeks run from Monday to Sunday). */
export const mondayOf = (value: string) => addDays(value, -((parseDate(value).getUTCDay() + 6) % 7));

export const daysBetween = (from: string, to: string) =>
  Math.round((parseDate(to).getTime() - parseDate(from).getTime()) / DAY_MS);

/** Today's date (YYYY-MM-DD) in the given time zone. */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  // The en-CA locale writes dates as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** Current time (HH:MM) in the given time zone. */
export function timeIn(timeZone: string, now: Date = new Date()): string {
  // `hourCycle: "h23"` makes midnight 00:00; `hour12: false` can print it as 24:00.
  return new Intl.DateTimeFormat("es-UY", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(now);
}

/** The data to request for a view. `offset` is 0 for the current period, -1 for the one before… */
export function periodRange(view: View, offset: number, today: string): PeriodRange {
  if (view === "hoy") {
    const ref = addDays(today, offset);
    return { view, granularity: "hour", from: ref, to: addDays(ref, 1), ref };
  }
  if (view === "semanal") {
    const ref = addDays(today, offset * 7);
    const monday = mondayOf(ref);
    return { view, granularity: "day", from: monday, to: addDays(monday, 7), ref };
  }
  const ref = addMonths(today, offset);
  return { view, granularity: "month", from: addMonths(ref, -11), to: addMonths(ref, 1), ref };
}

/** The last day of the period before this one. */
export const previousPeriodEnd = (range: PeriodRange) =>
  addDays(range.view === "semanal" ? range.from : range.ref, -1);

/** The offset that contains a date picked in the date (or month) input. */
export function offsetForDate(view: View, picked: string, today: string): number {
  const date = picked.length === 7 ? `${picked}-01` : picked;
  if (view === "hoy") return daysBetween(today, date);
  if (view === "semanal") return Math.round(daysBetween(mondayOf(today), mondayOf(date)) / 7);
  const a = parseDate(today);
  const b = parseDate(date);
  return (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth());
}

/** What goes in the date input: a month for `mensual`, a day for the others. */
export const pickerValue = (range: PeriodRange) => pickerBound(range.view, range.ref);

/** Turns a date into the format of the input, for its `min` and `max`. */
export const pickerBound = (view: View, date: string) => (view === "mensual" ? date.slice(0, 7) : date);

const dayLabel = (value: string) => {
  const date = parseDate(value);
  return `${date.getUTCDate()} de ${monthName(date.getUTCMonth())}`;
};

export function periodTitle(range: PeriodRange, today: string, nowTime: string): { title: string; subtitle: string } {
  const isCurrent =
    range.view === "mensual" ? range.ref.slice(0, 7) === today.slice(0, 7) : range.from <= today && today < range.to;
  const ref = parseDate(range.ref);
  const year = ref.getUTCFullYear();
  const yearSuffix = year === parseDate(today).getUTCFullYear() ? "" : ` de ${year}`;

  if (range.view === "hoy") {
    return {
      title: `${cap(dayName(ref.getUTCDay()))} ${dayLabel(range.ref)}${yearSuffix}`,
      subtitle: isCurrent ? `Acumulado hasta las ${nowTime}` : "Día completo",
    };
  }

  if (range.view === "semanal") {
    const start = parseDate(range.from);
    const sunday = addDays(range.from, 6);
    const end = parseDate(sunday);
    const title =
      start.getUTCMonth() === end.getUTCMonth()
        ? `Semana del ${start.getUTCDate()} al ${end.getUTCDate()} de ${monthName(end.getUTCMonth())}`
        : `Semana del ${dayLabel(range.from)} al ${dayLabel(sunday)}`;
    const now = parseDate(today);
    return {
      title: title + yearSuffix,
      subtitle: isCurrent ? `Acumulado hasta hoy, ${dayName(now.getUTCDay())} ${now.getUTCDate()}` : "Semana completa",
    };
  }

  const lead = isCurrent ? `Acumulado hasta el ${dayLabel(today)}` : "Mes completo";
  return {
    title: `${cap(monthName(ref.getUTCMonth()))} de ${year}`,
    subtitle: `${lead} · gráfico de los 12 meses hasta este`,
  };
}
