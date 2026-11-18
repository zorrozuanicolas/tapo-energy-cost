// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { View } from "../lib/period";
import { PeriodTabs } from "./PeriodTabs";

function setup(view: View) {
  const onChange = vi.fn();
  render(<PeriodTabs view={view} onChange={onChange} />);
  return { onChange, user: userEvent.setup() };
}

describe("PeriodTabs", () => {
  it("shows the three views and marks the current one as selected", () => {
    setup("semanal");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Hoy", "Semanal", "Mensual"]);
    expect(screen.getByRole("tab", { name: "Semanal" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Hoy" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Mensual" })).toHaveAttribute("aria-selected", "false");
  });

  it("lets only the selected tab take the Tab key", () => {
    setup("semanal");
    expect(screen.getByRole("tab", { name: "Semanal" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Hoy" })).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tab", { name: "Mensual" })).toHaveAttribute("tabindex", "-1");
  });

  it("reports the view that was clicked", async () => {
    const { onChange, user } = setup("hoy");
    await user.click(screen.getByRole("tab", { name: "Mensual" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("mensual");
  });

  it.each<[string, View, View]>([
    ["{ArrowRight}", "hoy", "semanal"],
    ["{ArrowRight}", "mensual", "hoy"], // wraps around
    ["{ArrowLeft}", "semanal", "hoy"],
    ["{ArrowLeft}", "hoy", "mensual"], // wraps around
    ["{Home}", "mensual", "hoy"],
    ["{End}", "hoy", "mensual"],
  ])("moves with %s from %s to %s", async (key, from, to) => {
    const { onChange, user } = setup(from);
    screen.getByRole("tab", { selected: true }).focus();
    await user.keyboard(key);
    expect(onChange).toHaveBeenCalledExactlyOnceWith(to);
    expect(screen.getByRole("tab", { name: { hoy: "Hoy", semanal: "Semanal", mensual: "Mensual" }[to] })).toHaveFocus();
  });

  it("ignores other keys", async () => {
    const { onChange, user } = setup("hoy");
    screen.getByRole("tab", { selected: true }).focus();
    await user.keyboard("a{ArrowDown}");
    expect(onChange).not.toHaveBeenCalled();
  });
});
