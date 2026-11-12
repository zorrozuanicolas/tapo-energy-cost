// Building an Intl.NumberFormat is comparatively slow and a chart formats hundreds of numbers, so keep one per
// number of decimals.
const formats = new Map<number, Intl.NumberFormat>();

function numberFormat(decimals: number): Intl.NumberFormat {
  let format = formats.get(decimals);
  if (!format) {
    format = new Intl.NumberFormat("es-UY", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    formats.set(decimals, format);
  }
  return format;
}

/** `1234.5` with 2 decimals is `1.234,50`: a comma for decimals and a point for thousands. */
export const fmtNumber = (value: number, decimals: number) => numberFormat(decimals).format(value);

export const fmtKwh = (value: number, decimals = 2) => fmtNumber(value, decimals);

export const fmtMoney = (value: number) => `$ ${fmtNumber(value, 2)}`;

/**
 * Whole-number percentages of `values` that add up to exactly 100 (largest remainder method): round every
 * share down, then give the points that are left to the shares with the biggest remainders, the first one
 * winning a tie. Gives zeros when there is nothing to share.
 */
export function sharePercents(values: number[]): number[] {
  const total = values.reduce((sum, v) => sum + v, 0);
  if (!(total > 0)) return values.map(() => 0); // also catches NaN

  const parts = values.map((value, index) => {
    const exact = (value / total) * 100;
    const floor = Math.floor(exact);
    return { index, floor, remainder: exact - floor };
  });
  const left = 100 - parts.reduce((sum, part) => sum + part.floor, 0);
  const winners = new Set(
    parts
      .toSorted((a, b) => b.remainder - a.remainder || a.index - b.index)
      .slice(0, left)
      .map((part) => part.index),
  );
  return parts.map((part) => part.floor + (winners.has(part.index) ? 1 : 0));
}
