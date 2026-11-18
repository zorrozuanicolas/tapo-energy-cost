import type { Band } from "../types";

/**
 * Colours for data-driven styling (chart bars, dots). They return references to the tokens in
 * `index.css`, so the hex values live in one place only.
 */

const OUTLET_COLOR_COUNT = 5; // --color-outlet-1 … --color-outlet-5

/** The colour of a plug by its position in the list (0 is the first). It repeats after the fifth. */
export function outletColor(index: number): string {
  if (!Number.isInteger(index) || index < 0) throw new RangeError(`No colour for outlet index ${index}`);
  return `var(--color-outlet-${(index % OUTLET_COLOR_COUNT) + 1})`;
}

export const bandColor = (band: Band) => `var(--color-band-${band})`;
