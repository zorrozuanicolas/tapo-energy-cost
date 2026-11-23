// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Outlet } from "../types";
import { OutletList } from "./OutletList";

const OUTLETS: Outlet[] = [
  { id: 1, slug: "heladera", name: "Heladera" },
  { id: 2, slug: "escritorio", name: "Escritorio" },
];

const VALUES = { "1": { kwh: 0.15, cost: 1.37 }, "2": { kwh: 0.4, cost: 2.52 } };

/** Every body and footer row as [name, kWh, cost, share]; the header row is left out. */
function tableRows() {
  const table = screen.getByRole("table", { name: "Detalle por enchufe" });
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => [
      within(row).getByRole("rowheader").textContent,
      ...within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ]);
}

describe("OutletList", () => {
  it("shows what each plug used, its share of the cost and the total", () => {
    render(<OutletList outlets={OUTLETS} values={VALUES} />);
    expect(tableRows()).toEqual([
      ["Heladera", "0,15", "$ 1,37", "35%"],
      ["Escritorio", "0,40", "$ 2,52", "65%"],
      ["Total", "0,55", "$ 3,89", "100%"],
    ]);
  });

  it("names the columns", () => {
    render(<OutletList outlets={OUTLETS} values={VALUES} />);
    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Enchufe",
      "kWh",
      "Costo",
      "% del costo",
    ]);
  });

  it("shows 0% instead of NaN when nothing was spent", () => {
    render(<OutletList outlets={OUTLETS} values={{}} />);
    expect(tableRows()).toEqual([
      ["Heladera", "0,00", "$ 0,00", "0%"],
      ["Escritorio", "0,00", "$ 0,00", "0%"],
      ["Total", "0,00", "$ 0,00", "0%"],
    ]);
  });
});
