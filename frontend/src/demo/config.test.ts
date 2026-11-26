import { describe, expect, it } from "vitest";
import { parse } from "yaml";

// The backend's configuration files, as text. They are the originals that `config.ts` copies.
import holidaysYaml from "../../../config/holidays.yaml?raw";
import tariffsYaml from "../../../config/tariffs.yaml?raw";
import { HOLIDAYS, TARIFFS } from "./config";

interface TariffsFile {
  tariffs: {
    valid_from: string;
    vat: number;
    peak_window: { start: number; end: number };
    rates: Record<string, number>;
  }[];
}

type HolidaysFile = Record<string, { date: string }[]>;

describe("the demo's copy of the configuration", () => {
  it("has the tariffs of config/tariffs.yaml", () => {
    const file = parse(tariffsYaml) as TariffsFile;
    const expected = file.tariffs
      .map(({ valid_from, vat, peak_window, rates }) => ({
        valid_from,
        vat,
        peak_start: peak_window.start,
        peak_end: peak_window.end,
        rates,
      }))
      .sort((a, b) => a.valid_from.localeCompare(b.valid_from));

    expect(TARIFFS).toEqual(expected);
  });

  it("has the holidays of config/holidays.yaml", () => {
    const file = parse(holidaysYaml) as HolidaysFile;
    const expected = Object.values(file)
      .flat()
      .map((holiday) => holiday.date);

    expect([...HOLIDAYS].sort()).toEqual(expected.sort());
  });
});
