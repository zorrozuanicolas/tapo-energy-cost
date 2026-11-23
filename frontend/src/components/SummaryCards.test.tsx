// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Outlet } from "../types";
import { SummaryCards } from "./SummaryCards";

const OUTLETS: Outlet[] = [
  { id: 1, slug: "heladera", name: "Heladera" },
  { id: 2, slug: "escritorio", name: "Escritorio" },
];

const VALUES = { "1": { kwh: 0.15, cost: 1.37 }, "2": { kwh: 0.4, cost: 2.52 } };

/** The text of a card's name, kWh and cost, in that order. */
const cardTexts = (card: HTMLElement) => [
  within(card).getByRole("term").textContent,
  ...within(card)
    .getAllByRole("definition")
    .map((definition) => definition.textContent),
];

describe("SummaryCards", () => {
  it("shows a card per plug and then the total", () => {
    render(<SummaryCards outlets={OUTLETS} values={VALUES} />);
    const cards = within(screen.getByRole("region", { name: "Resumen" })).getAllByRole("listitem");
    expect(cards.map(cardTexts)).toEqual([
      ["Heladera", "0,15 kWh", "$ 1,37"],
      ["Escritorio", "0,40 kWh", "$ 2,52"],
      ["Total", "0,55 kWh", "$ 3,89"],
    ]);
  });

  it("shows zeros for a plug that used nothing", () => {
    render(<SummaryCards outlets={OUTLETS} values={{ "1": VALUES["1"] }} />);
    expect(screen.getAllByRole("listitem").map(cardTexts)[1]).toEqual(["Escritorio", "0,00 kWh", "$ 0,00"]);
  });

  it("shows only the total when there are no plugs", () => {
    render(<SummaryCards outlets={[]} values={{}} />);
    expect(screen.getAllByRole("listitem").map(cardTexts)).toEqual([["Total", "0,00 kWh", "$ 0,00"]]);
  });
});
