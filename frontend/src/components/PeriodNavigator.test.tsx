// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { periodRange, type View } from "../lib/period";
import { PeriodNavigator } from "./PeriodNavigator";

const TODAY = "2026-10-22"; // a Thursday

interface Options {
  view?: View;
  offset?: number;
  earliest?: string | null;
}

function setup({ view = "hoy", offset = 0, earliest = "2026-10-01" }: Options = {}) {
  const onOffsetChange = vi.fn();
  render(
    <PeriodNavigator
      view={view}
      offset={offset}
      range={periodRange(view, offset, TODAY)}
      today={TODAY}
      earliest={earliest}
      onOffsetChange={onOffsetChange}
    />,
  );
  return { onOffsetChange, user: userEvent.setup() };
}

const back = () => screen.getByRole("button", { name: "Período anterior" });
const forward = () => screen.getByRole("button", { name: "Período siguiente" });

describe("PeriodNavigator arrows", () => {
  it("goes one period back and, from the past, one forward", async () => {
    const { onOffsetChange, user } = setup({ offset: -3 });
    await user.click(back());
    await user.click(forward());
    expect(onOffsetChange.mock.calls).toEqual([[-4], [-2]]);
  });

  it("cannot go forward from the current period", () => {
    setup({ offset: 0 });
    expect(forward()).toBeDisabled();
  });

  it("cannot go back before the first day with data", () => {
    setup({ earliest: "2026-10-22" }); // the day before today has no data
    expect(back()).toBeDisabled();
  });

  it("can go back to the first day with data", () => {
    setup({ earliest: "2026-10-21" });
    expect(back()).toBeEnabled();
  });

  it("cannot go back while the first day is unknown", () => {
    setup({ earliest: null });
    expect(back()).toBeDisabled();
  });
});

describe("PeriodNavigator return button", () => {
  it("is hidden on the current period", () => {
    setup({ offset: 0 });
    expect(screen.queryByRole("button", { name: "Volver a hoy" })).not.toBeInTheDocument();
  });

  it.each<[View, string]>([
    ["hoy", "Volver a hoy"],
    ["semanal", "Esta semana"],
    ["mensual", "Este mes"],
  ])("returns to the current period in the %s view", async (view, label) => {
    const { onOffsetChange, user } = setup({ view, offset: -2 });
    await user.click(screen.getByRole("button", { name: label }));
    expect(onOffsetChange).toHaveBeenCalledExactlyOnceWith(0);
  });
});

describe("PeriodNavigator picker", () => {
  it("picks a day", () => {
    const { onOffsetChange } = setup({ view: "hoy" });
    fireEvent.change(screen.getByLabelText("Ir al día"), { target: { value: "2026-10-20" } });
    expect(onOffsetChange).toHaveBeenCalledExactlyOnceWith(-2);
  });

  it("picks the week that contains a day", () => {
    const { onOffsetChange } = setup({ view: "semanal" });
    fireEvent.change(screen.getByLabelText("Ir a la semana de"), { target: { value: "2026-10-14" } });
    expect(onOffsetChange).toHaveBeenCalledExactlyOnceWith(-1);
  });

  it("picks a month", () => {
    const { onOffsetChange } = setup({ view: "mensual" });
    const input = screen.getByLabelText("Ir al mes");
    expect(input).toHaveAttribute("type", "month");
    fireEvent.change(input, { target: { value: "2026-08" } });
    expect(onOffsetChange).toHaveBeenCalledExactlyOnceWith(-2);
  });

  it("keeps a date in the future at the current period", () => {
    const { onOffsetChange } = setup({ view: "hoy" });
    fireEvent.change(screen.getByLabelText("Ir al día"), { target: { value: "2026-12-25" } });
    expect(onOffsetChange).toHaveBeenCalledExactlyOnceWith(0);
  });

  it("opens the picker when the label is clicked, not only the input", async () => {
    const showPicker = vi.fn();
    HTMLInputElement.prototype.showPicker = showPicker; // jsdom does not have it
    const { user } = setup({ view: "hoy" });
    await user.click(screen.getByText("Ir al día"));
    expect(showPicker).toHaveBeenCalledOnce();
  });

  describe("clicking the control while the calendar is open", () => {
    // The browser closes an open calendar on the press of the click, so the click that follows must not open it again.
    const setupWithPicker = () => {
      const showPicker = vi.fn();
      HTMLInputElement.prototype.showPicker = showPicker; // jsdom does not have it
      return { showPicker, ...setup({ view: "hoy" }) };
    };

    it("leaves it closed, and the click after that opens it again", async () => {
      const { showPicker, user } = setupWithPicker();
      const input = screen.getByLabelText("Ir al día");
      await user.click(input);
      await user.click(input);
      expect(showPicker).toHaveBeenCalledOnce();
      await user.click(input);
      expect(showPicker).toHaveBeenCalledTimes(2);
    });

    it("cancels the browser's own opening, which the calendar icon has and would open it a second time", () => {
      setupWithPicker();
      const notCancelled = fireEvent.click(screen.getByLabelText("Ir al día"));
      expect(notCancelled).toBe(false); // fireEvent returns false when preventDefault was called
    });

    it("leaves it closed when the click is on the label text", async () => {
      // Pressing the label takes the focus away from the input, which must not count as leaving the control.
      const { showPicker, user } = setupWithPicker();
      await user.click(screen.getByLabelText("Ir al día"));
      await user.click(screen.getByText("Ir al día"));
      expect(showPicker).toHaveBeenCalledOnce();
    });

    it("opens it again once a date has been chosen", async () => {
      const { showPicker, user } = setupWithPicker();
      const input = screen.getByLabelText("Ir al día");
      await user.click(input);
      fireEvent.change(input, { target: { value: "2026-10-10" } });
      await user.click(input);
      expect(showPicker).toHaveBeenCalledTimes(2);
    });

    it("opens it again after a key press", async () => {
      const { showPicker, user } = setupWithPicker();
      const input = screen.getByLabelText("Ir al día");
      await user.click(input);
      await user.keyboard("{Escape}");
      await user.click(input);
      expect(showPicker).toHaveBeenCalledTimes(2);
    });

    it("opens it again after the focus went elsewhere", async () => {
      const { showPicker, user } = setupWithPicker();
      const input = screen.getByLabelText("Ir al día");
      await user.click(input);
      await user.click(document.body);
      await user.click(input);
      expect(showPicker).toHaveBeenCalledTimes(2);
    });
  });

  it("marks the input as clicked until the keyboard is used", async () => {
    const { user } = setup({ view: "hoy" });
    const input = screen.getByLabelText("Ir al día");
    expect(input).not.toHaveAttribute("data-clicked");

    await user.click(input);
    expect(input).toHaveAttribute("data-clicked");

    await user.keyboard("{ArrowUp}");
    expect(input).not.toHaveAttribute("data-clicked");
  });

  it("limits the input between the first day with data and today", () => {
    setup({ view: "hoy", earliest: "2026-10-05" });
    const input = screen.getByLabelText("Ir al día");
    expect(input).toHaveAttribute("min", "2026-10-05");
    expect(input).toHaveAttribute("max", TODAY);
    expect(input).toHaveValue(TODAY);
  });
});
