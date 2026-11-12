import { describe, expect, test } from "vitest";
import {
  addDays,
  addMonths,
  daysBetween,
  mondayOf,
  offsetForDate,
  parseDate,
  periodRange,
  periodTitle,
  pickerBound,
  pickerValue,
  previousPeriodEnd,
  timeIn,
  todayIn,
  type View,
} from "./period";

// 2026-11-12 is a Thursday, so its week runs from Monday 9 to Sunday 15 November.
const TODAY = "2026-11-12";

describe("date arithmetic", () => {
  test("parseDate reads the first ten characters, so ISO datetimes work", () => {
    expect(parseDate("2026-10-22T14:00:00-03:00").getTime()).toBe(Date.UTC(2026, 9, 22));
  });

  test("parseDate rejects text that is not a date", () => {
    expect(() => parseDate("hoy")).toThrow();
    expect(() => parseDate("2026-1-5")).toThrow();
  });

  test("addDays crosses month and year boundaries", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  test("addDays knows leap years", () => {
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");
  });

  test("addMonths returns the first day of the target month", () => {
    expect(addMonths("2026-01-31", 1)).toBe("2026-02-01");
    expect(addMonths("2026-12-15", 1)).toBe("2027-01-01");
    expect(addMonths("2026-01-15", -1)).toBe("2025-12-01");
    expect(addMonths("2026-11-12", 0)).toBe("2026-11-01");
  });

  test("mondayOf gives the Monday of the week, with Sunday at the end of it", () => {
    expect(mondayOf("2026-11-09")).toBe("2026-11-09"); // Monday
    expect(mondayOf("2026-11-11")).toBe("2026-11-09"); // Wednesday
    expect(mondayOf("2026-11-15")).toBe("2026-11-09"); // Sunday
    expect(mondayOf("2026-11-16")).toBe("2026-11-16"); // next Monday
  });

  test("daysBetween counts calendar days", () => {
    expect(daysBetween("2026-11-12", "2026-11-12")).toBe(0);
    expect(daysBetween("2026-11-12", "2026-11-01")).toBe(-11);
    expect(daysBetween("2026-12-31", "2027-01-02")).toBe(2);
  });
});

describe("the clock in a time zone", () => {
  // 01:00 UTC on the 13th is 22:00 on the 12th in Montevideo (UTC-3).
  const now = new Date("2026-11-13T01:00:00Z");

  test("todayIn uses the zone, not UTC", () => {
    expect(todayIn("America/Montevideo", now)).toBe("2026-11-12");
    expect(todayIn("UTC", now)).toBe("2026-11-13");
  });

  test("timeIn gives HH:MM in the zone", () => {
    expect(timeIn("America/Montevideo", now)).toBe("22:00");
  });

  test("timeIn writes midnight as 00:00, not 24:00", () => {
    expect(timeIn("America/Montevideo", new Date("2026-11-13T03:00:00Z"))).toBe("00:00");
  });
});

describe("periodRange", () => {
  test("hoy is one day by hour", () => {
    expect(periodRange("hoy", 0, TODAY)).toEqual({
      view: "hoy",
      granularity: "hour",
      from: "2026-11-12",
      to: "2026-11-13",
      ref: "2026-11-12",
    });
    expect(periodRange("hoy", -1, TODAY)).toMatchObject({ from: "2026-11-11", to: "2026-11-12" });
  });

  test("semanal is Monday to the next Monday, by day", () => {
    expect(periodRange("semanal", 0, TODAY)).toEqual({
      view: "semanal",
      granularity: "day",
      from: "2026-11-09",
      to: "2026-11-16",
      ref: "2026-11-12",
    });
    expect(periodRange("semanal", -1, TODAY)).toMatchObject({
      from: "2026-11-02",
      to: "2026-11-09",
      ref: "2026-11-05",
    });
  });

  test("a week can span two months", () => {
    expect(periodRange("semanal", 0, "2026-10-30")).toMatchObject({ from: "2026-10-26", to: "2026-11-02" });
  });

  test("mensual is twelve months by month, ending with the one looked at", () => {
    expect(periodRange("mensual", 0, TODAY)).toEqual({
      view: "mensual",
      granularity: "month",
      from: "2025-12-01",
      to: "2026-12-01",
      ref: "2026-11-01",
    });
    expect(periodRange("mensual", -1, TODAY)).toMatchObject({
      from: "2025-11-01",
      to: "2026-11-01",
      ref: "2026-10-01",
    });
  });
});

describe("previousPeriodEnd", () => {
  test("is the last day of the period before", () => {
    expect(previousPeriodEnd(periodRange("hoy", 0, TODAY))).toBe("2026-11-11");
    expect(previousPeriodEnd(periodRange("semanal", 0, TODAY))).toBe("2026-11-08");
    expect(previousPeriodEnd(periodRange("mensual", 0, TODAY))).toBe("2026-10-31");
  });
});

describe("the date picker", () => {
  const views: View[] = ["hoy", "semanal", "mensual"];

  test.each(views)("offsetForDate undoes periodRange for %s", (view) => {
    for (const offset of [-14, -1, 0, 1]) {
      const picked = pickerValue(periodRange(view, offset, TODAY));
      expect(offsetForDate(view, picked, TODAY)).toBe(offset);
    }
  });

  test("a day picked in the middle of a week or month lands on its period", () => {
    expect(offsetForDate("hoy", "2026-11-01", TODAY)).toBe(-11);
    expect(offsetForDate("semanal", "2026-11-04", TODAY)).toBe(-1);
    expect(offsetForDate("mensual", "2026-03", TODAY)).toBe(-8);
  });

  test("the picker works with months for mensual and with days otherwise", () => {
    expect(pickerValue(periodRange("mensual", 0, TODAY))).toBe("2026-11");
    expect(pickerValue(periodRange("hoy", 0, TODAY))).toBe("2026-11-12");
    expect(pickerBound("mensual", "2026-11-12")).toBe("2026-11");
    expect(pickerBound("semanal", "2026-11-12")).toBe("2026-11-12");
  });
});

describe("periodTitle", () => {
  const title = (view: View, offset: number, today = TODAY) =>
    periodTitle(periodRange(view, offset, today), today, "14:30");

  test("hoy, current and past", () => {
    expect(title("hoy", 0)).toEqual({ title: "Jueves 12 de noviembre", subtitle: "Acumulado hasta las 14:30" });
    expect(title("hoy", -1)).toEqual({ title: "Miércoles 11 de noviembre", subtitle: "Día completo" });
  });

  test("a year other than the current one is written out", () => {
    expect(title("hoy", -365).title).toBe("Miércoles 12 de noviembre de 2025");
  });

  test("semanal inside one month", () => {
    expect(title("semanal", 0)).toEqual({
      title: "Semana del 9 al 15 de noviembre",
      subtitle: "Acumulado hasta hoy, jueves 12",
    });
    expect(title("semanal", -1)).toEqual({ title: "Semana del 2 al 8 de noviembre", subtitle: "Semana completa" });
  });

  test("semanal across two months names both", () => {
    expect(title("semanal", 0, "2026-10-30")).toEqual({
      title: "Semana del 26 de octubre al 1 de noviembre",
      subtitle: "Acumulado hasta hoy, viernes 30",
    });
  });

  test("mensual, current and past", () => {
    expect(title("mensual", 0)).toEqual({
      title: "Noviembre de 2026",
      subtitle: "Acumulado hasta el 12 de noviembre · gráfico de los 12 meses hasta este",
    });
    expect(title("mensual", -1)).toEqual({
      title: "Octubre de 2026",
      subtitle: "Mes completo · gráfico de los 12 meses hasta este",
    });
  });
});
