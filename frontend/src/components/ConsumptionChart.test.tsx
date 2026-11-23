// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ChartMode } from "../lib/chart";
import type { Bucket, Granularity, Outlet, Tariff } from "../types";
import { ConsumptionChart } from "./ConsumptionChart";

const OUTLETS: Outlet[] = [
  { id: 1, slug: "heladera", name: "Heladera" },
  { id: 2, slug: "escritorio", name: "Escritorio" },
];

const BUCKETS: Bucket[] = [
  {
    start: "2026-10-22T14:00:00-03:00",
    end: "2026-10-22T15:00:00-03:00",
    has_data: true,
    partial: false,
    band: "llano",
    rate_per_kwh: 6.5,
    outlets: { "1": { kwh: 1, cost: 6 }, "2": { kwh: 0.5, cost: 3 } },
  },
  {
    start: "2026-10-22T15:00:00-03:00",
    end: "2026-10-22T16:00:00-03:00",
    has_data: false,
    partial: false,
    band: "llano",
    rate_per_kwh: 6.5,
    outlets: {},
  },
];

const TARIFF: Tariff = {
  valid_from: "2026-01-01",
  vat: 0.22,
  peak_start: 17,
  peak_end: 22,
  rates: { valle: 3.4, llano: 5.3, punta: 8 },
  rates_with_vat: { valle: 4.1, llano: 6.5, punta: 9.8 },
};

const FIRST_SLOT = "14:00 – 15:00: Heladera 1,000 kWh, $ 6,00; Escritorio 0,500 kWh, $ 3,00; Total 1,500 kWh, $ 9,00";

function renderChart({
  granularity = "hour",
  mode = "all",
  tariff = TARIFF,
  onModeChange = vi.fn(),
}: {
  granularity?: Granularity;
  mode?: ChartMode;
  tariff?: Tariff;
  onModeChange?: (mode: ChartMode) => void;
} = {}) {
  render(
    <ConsumptionChart
      buckets={BUCKETS}
      outlets={OUTLETS}
      granularity={granularity}
      mode={mode}
      onModeChange={onModeChange}
      tariff={tariff}
    />,
  );
  return { onModeChange };
}

describe("ConsumptionChart", () => {
  it("has a button per slot that says what it holds", () => {
    renderChart();
    expect(screen.getByRole("button", { name: FIRST_SLOT })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "15:00 – 16:00: sin datos" })).toBeInTheDocument();
  });

  it("titles the chart by what a bar means", () => {
    renderChart({ granularity: "day" });
    expect(screen.getByRole("heading", { name: "Consumo por día" })).toBeInTheDocument();
    expect(screen.getByText(/costo de ese día/)).toBeInTheDocument();
  });

  describe("what to show", () => {
    it("marks the chosen option as pressed", () => {
      renderChart({ mode: 2 });
      expect(screen.getByRole("button", { name: "Escritorio", pressed: true })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Superpuesto", pressed: false })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Heladera", pressed: false })).toBeInTheDocument();
    });

    it("asks for the overlay or for one plug when clicked", async () => {
      const { onModeChange } = renderChart({ mode: 1 });
      const user = userEvent.setup();
      await user.click(screen.getByRole("button", { name: "Superpuesto" }));
      expect(onModeChange).toHaveBeenLastCalledWith("all");
      await user.click(screen.getByRole("button", { name: "Escritorio" }));
      expect(onModeChange).toHaveBeenLastCalledWith(2);
    });

    it("draws only the chosen plug", () => {
      renderChart({ mode: 2 });
      expect(screen.getByRole("button", { name: "14:00 – 15:00: Escritorio 0,500 kWh, $ 3,00" })).toBeInTheDocument();
    });
  });

  describe("tooltip", () => {
    it("shows the band, the plugs and the total while the pointer is over a slot", async () => {
      renderChart();
      const user = userEvent.setup();
      expect(screen.queryByText("Llano · $ 6,500 por kWh")).not.toBeInTheDocument();

      await user.hover(screen.getByRole("button", { name: FIRST_SLOT }));
      expect(screen.getByText("14:00 – 15:00")).toBeInTheDocument();
      expect(screen.getByText("Llano · $ 6,500 por kWh")).toBeInTheDocument();
      expect(screen.getByText("Total")).toBeInTheDocument();
      expect(screen.getByText("$ 9,00")).toBeInTheDocument();

      await user.unhover(screen.getByRole("button", { name: FIRST_SLOT }));
      expect(screen.queryByText("14:00 – 15:00")).not.toBeInTheDocument();
    });

    it("shows when a slot gets the keyboard focus, and hides when it loses it", () => {
      renderChart();
      const slot = screen.getByRole("button", { name: FIRST_SLOT });
      act(() => slot.focus());
      expect(screen.getByText("Llano · $ 6,500 por kWh")).toBeInTheDocument();
      act(() => slot.blur());
      expect(screen.queryByText("Llano · $ 6,500 por kWh")).not.toBeInTheDocument();
    });

    it("shows when a slot is tapped", async () => {
      renderChart();
      await userEvent.setup().click(screen.getByRole("button", { name: FIRST_SLOT }));
      expect(screen.getByText("Llano · $ 6,500 por kWh")).toBeInTheDocument();
    });

    it("does not show for a slot without data", async () => {
      renderChart();
      await userEvent.setup().hover(screen.getByRole("button", { name: "15:00 – 16:00: sin datos" }));
      expect(screen.queryByText("15:00 – 16:00")).not.toBeInTheDocument();
    });
  });

  describe("band legend", () => {
    it("explains the bands of the hourly chart with the rates", () => {
      renderChart();
      expect(screen.getByText("Valle · 00–07 h · $ 4,100/kWh")).toBeInTheDocument();
      expect(screen.getByText("Llano · resto del día · $ 6,500/kWh")).toBeInTheDocument();
      expect(screen.getByText("Punta · 17–22 h · $ 9,800/kWh")).toBeInTheDocument();
    });

    it("is not shown for days or months", () => {
      renderChart({ granularity: "day" });
      expect(screen.queryByText(/Valle/)).not.toBeInTheDocument();
    });

    it("is not shown before the tariff has loaded", () => {
      render(
        <ConsumptionChart
          buckets={BUCKETS}
          outlets={OUTLETS}
          granularity="hour"
          mode="all"
          onModeChange={vi.fn()}
          tariff={undefined}
        />,
      );
      expect(screen.queryByText(/Valle/)).not.toBeInTheDocument();
    });
  });
});
