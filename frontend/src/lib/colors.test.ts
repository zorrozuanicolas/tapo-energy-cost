import { describe, expect, it } from "vitest";
import { bandColor, outletColor } from "./colors";

describe("outletColor", () => {
  it("gives each of the first plugs its own colour", () => {
    expect([0, 1, 4].map(outletColor)).toEqual([
      "var(--color-outlet-1)",
      "var(--color-outlet-2)",
      "var(--color-outlet-5)",
    ]);
  });

  it("starts over after the fifth plug", () => {
    expect(outletColor(5)).toBe(outletColor(0));
    expect(outletColor(7)).toBe(outletColor(2));
  });

  it("rejects an index that cannot be a position", () => {
    expect(() => outletColor(-1)).toThrow(RangeError);
    expect(() => outletColor(1.5)).toThrow(RangeError);
  });
});

describe("bandColor", () => {
  it("points to the token of each band", () => {
    expect(bandColor("valle")).toBe("var(--color-band-valle)");
    expect(bandColor("llano")).toBe("var(--color-band-llano)");
    expect(bandColor("punta")).toBe("var(--color-band-punta)");
  });
});
