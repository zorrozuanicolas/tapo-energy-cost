// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Live } from "../hooks/useLive";
import type { LiveReading, Outlet } from "../types";
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

  describe("live power", () => {
    const reading = (outletId: number, overrides: Partial<LiveReading> = {}): LiveReading => ({
      outlet_id: outletId,
      power_w: 83.4,
      online: true,
      ts: "2026-11-23T15:00:00Z",
      ...overrides,
    });
    const connected = (...readings: LiveReading[]): Live => ({
      readings: Object.fromEntries(readings.map((r) => [r.outlet_id, r])),
      connected: true,
    });
    const cards = () => screen.getAllByRole("listitem").map(cardTexts);

    it("says what each plug is drawing now, in whole watts, and nothing on the total", () => {
      const live = connected(reading(1, { power_w: 1234.4 }), reading(2, { power_w: 5.6 }));
      render(<SummaryCards outlets={OUTLETS} values={VALUES} live={live} />);
      expect(cards()).toEqual([
        ["Heladera", "0,15 kWh", "$ 1,37", "Ahora: 1.234 W"],
        ["Escritorio", "0,40 kWh", "$ 2,52", "Ahora: 6 W"],
        ["Total", "0,55 kWh", "$ 3,89"],
      ]);
    });

    it("says a plug has no connection when it is offline or has no power", () => {
      const live = connected(reading(1, { online: false, power_w: null }), reading(2, { online: true, power_w: null }));
      render(<SummaryCards outlets={OUTLETS} values={VALUES} live={live} />);
      expect(cards().map((card) => card[3])).toEqual(["Sin conexión", "Sin conexión", undefined]);
    });

    it("says nothing about a plug that has not reported yet", () => {
      render(<SummaryCards outlets={OUTLETS} values={VALUES} live={connected(reading(1))} />);
      expect(cards().map((card) => card[3])).toEqual(["Ahora: 83 W", undefined, undefined]);
    });

    it("says nothing while the stream is down, because the readings are old", () => {
      const live: Live = { ...connected(reading(1), reading(2)), connected: false };
      render(<SummaryCards outlets={OUTLETS} values={VALUES} live={live} />);
      expect(cards().map((card) => card.length)).toEqual([3, 3, 3]);
    });

    it("says nothing when live data was not asked for", () => {
      render(<SummaryCards outlets={OUTLETS} values={VALUES} />);
      expect(cards().map((card) => card.length)).toEqual([3, 3, 3]);
    });
  });
});
