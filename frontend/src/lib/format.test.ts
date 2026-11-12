import { describe, expect, test } from "vitest";
import { fmtKwh, fmtMoney, fmtNumber, sharePercents } from "./format";

describe("numbers", () => {
  test("fmtNumber uses a comma for decimals and a point for thousands", () => {
    expect(fmtNumber(1234.5, 2)).toBe("1.234,50");
    expect(fmtNumber(1234567.8, 1)).toBe("1.234.567,8");
    expect(fmtNumber(-3.5, 2)).toBe("-3,50");
  });

  test("fmtNumber always shows the requested decimals", () => {
    expect(fmtNumber(0, 2)).toBe("0,00");
    expect(fmtNumber(2, 0)).toBe("2");
    expect(fmtNumber(1.5, 3)).toBe("1,500");
  });

  test("fmtKwh rounds to two decimals by default", () => {
    expect(fmtKwh(1.234)).toBe("1,23");
    expect(fmtKwh(1.236)).toBe("1,24");
    expect(fmtKwh(0.5, 3)).toBe("0,500");
  });

  test("fmtMoney writes pesos with two decimals", () => {
    expect(fmtMoney(1234.5)).toBe("$ 1.234,50");
    expect(fmtMoney(0)).toBe("$ 0,00");
  });
});

describe("sharePercents", () => {
  const sum = (values: number[]) => values.reduce((total, v) => total + v, 0);

  test("simple shares", () => {
    expect(sharePercents([1, 3])).toEqual([25, 75]);
    expect(sharePercents([5])).toEqual([100]);
  });

  test("equal shares that do not divide 100 give the extra points to the first ones", () => {
    expect(sharePercents([1, 1, 1])).toEqual([34, 33, 33]);
    expect(sharePercents([1, 1, 1, 1, 1, 1, 1])).toEqual([15, 15, 14, 14, 14, 14, 14]);
  });

  test("the extra point goes to the biggest remainder, and ties go to the first", () => {
    // Exact shares: 28.57, 28.57, 42.86. The two points left go to 42.86 and then to the first 28.57.
    expect(sharePercents([1, 1, 1.5])).toEqual([29, 28, 43]);
  });

  test("always adds up to exactly 100", () => {
    const cases = [[1, 2, 3, 4, 5, 7], [0.1, 0.2, 0.3], [13, 17, 19, 23], [1e-6, 1, 1e6], [2, 0, 5, 0, 1]];
    for (const values of cases) {
      expect(sum(sharePercents(values))).toBe(100);
    }
  });

  test("a value of zero stays at zero", () => {
    expect(sharePercents([2, 0, 6])).toEqual([25, 0, 75]);
  });

  test("nothing to share gives zeros", () => {
    expect(sharePercents([])).toEqual([]);
    expect(sharePercents([0, 0])).toEqual([0, 0]);
    expect(sharePercents([-1, -2])).toEqual([0, 0]);
    expect(sharePercents([Number.NaN])).toEqual([0]);
  });
});
