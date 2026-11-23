// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { WarningBanner } from "./WarningBanner";

it("names the year whose holidays are missing", () => {
  render(<WarningBanner warnings={[{ code: "missing_holidays", year: 2027 }]} />);
  expect(screen.getByRole("status")).toHaveTextContent("Faltan los feriados de 2027");
});

it("names the day since which there is no tariff", () => {
  render(<WarningBanner warnings={[{ code: "no_tariff", since: "2026-01-01" }]} />);
  expect(screen.getByRole("status")).toHaveTextContent("No hay una tarifa configurada desde el 2026-01-01");
});

it("shows one notice per warning", () => {
  render(
    <WarningBanner
      warnings={[
        { code: "missing_holidays", year: 2027 },
        { code: "no_tariff", since: "2026-01-01" },
      ]}
    />,
  );
  expect(screen.getAllByRole("status")).toHaveLength(2);
});

it("shows nothing when there are no warnings", () => {
  render(<WarningBanner warnings={[]} />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
