// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ErrorState } from "./ErrorState";

it("announces that the server cannot be reached", () => {
  render(<ErrorState onRetry={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("No se pudo conectar con el servidor.");
});

it("asks to try again when the button is pressed", async () => {
  const onRetry = vi.fn();
  render(<ErrorState onRetry={onRetry} />);
  await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar" }));
  expect(onRetry).toHaveBeenCalledOnce();
});
