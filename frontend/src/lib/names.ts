/** Spanish names for the dates shown in the UI. */

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

// With `noUncheckedIndexedAccess` an array lookup may be undefined; an index out of range is a bug, so fail loudly.
function pick(list: readonly string[], index: number): string {
  const name = list[index];
  if (name === undefined) throw new RangeError(`No name for index ${index}`);
  return name;
}

/** `index` is 0 for January, like `Date.getUTCMonth()`. */
export const monthName = (index: number) => pick(MONTHS, index);

/** `index` is 0 for Sunday, like `Date.getUTCDay()`. */
export const dayName = (index: number) => pick(DAYS, index);

export const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
