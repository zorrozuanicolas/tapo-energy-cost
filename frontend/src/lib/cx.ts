/** Joins class names, skipping the falsy ones: `cx("p-2", active && "bg-ink")`. */
export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(" ");
