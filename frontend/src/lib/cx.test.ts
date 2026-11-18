import { expect, it } from "vitest";
import { cx } from "./cx";

it("joins the class names with a space", () => {
  expect(cx("p-2", "bg-ink")).toBe("p-2 bg-ink");
});

it("skips false, null, undefined and empty values", () => {
  expect(cx("p-2", false, null, undefined, "", "text-muted")).toBe("p-2 text-muted");
});

it("keeps a class only when its condition holds", () => {
  const active = true;
  const disabled = false;
  expect(cx("base", active && "bg-ink", disabled && "opacity-40")).toBe("base bg-ink");
});
