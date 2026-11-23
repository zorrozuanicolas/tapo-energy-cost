import { outletColor } from "../lib/colors";
import { cx } from "../lib/cx";
import { fmtKwh, fmtMoney } from "../lib/format";
import { type OutletValues, sumValues, valueFor } from "../lib/values";
import type { Outlet, OutletValue } from "../types";

interface SummaryCardProps {
  name: string;
  value: OutletValue;
  /** The colour of the plug, shown as a dot. */
  color?: string;
  inverted?: boolean;
}

function SummaryCard({ name, value, color, inverted = false }: SummaryCardProps) {
  const muted = inverted ? "text-surface/70" : "text-muted";
  return (
    <li
      className={cx("rounded-2xl border p-4", inverted ? "border-ink bg-ink text-surface" : "border-line bg-surface")}
    >
      <dl>
        <dt className={cx("flex items-center gap-2 text-sm font-bold", muted)}>
          {color && (
            <span aria-hidden="true" className="size-2.5 flex-none rounded-full" style={{ background: color }} />
          )}
          {name}
        </dt>
        <dd className="mt-2.5 text-3xl leading-tight font-extrabold tabular-nums">
          {fmtKwh(value.kwh)} <span className={cx("text-sm font-semibold", muted)}>kWh</span>
        </dd>
        <dd className="mt-1.5 text-lg font-bold tabular-nums">{fmtMoney(value.cost)}</dd>
      </dl>
    </li>
  );
}

interface SummaryCardsProps {
  outlets: readonly Outlet[];
  /** The totals of the period, keyed by plug id. */
  values: OutletValues;
}

/** One card per plug, and a last one with the total. */
export function SummaryCards({ outlets, values }: SummaryCardsProps) {
  return (
    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading" className="sr-only">
        Resumen
      </h2>
      <ul className="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-3">
        {outlets.map((outlet, index) => (
          <SummaryCard
            key={outlet.id}
            name={outlet.name}
            value={valueFor(values, outlet.id)}
            color={outletColor(index)}
          />
        ))}
        <SummaryCard name="Total" value={sumValues(outlets, values)} inverted />
      </ul>
    </section>
  );
}
