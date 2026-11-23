import { outletColor } from "../lib/colors";
import { fmtKwh, fmtMoney, sharePercents } from "../lib/format";
import { type OutletValues, sumValues, valueFor } from "../lib/values";
import type { Outlet } from "../types";

interface OutletListProps {
  outlets: readonly Outlet[];
  /** The totals of the period, keyed by plug id. */
  values: OutletValues;
}

/** What each plug used in the period and its share of the cost. */
export function OutletList({ outlets, values }: OutletListProps) {
  const shares = sharePercents(outlets.map((outlet) => valueFor(values, outlet.id).cost));
  const rows = outlets.map((outlet, index) => ({
    outlet,
    value: valueFor(values, outlet.id),
    share: shares[index] ?? 0,
    color: outletColor(index),
  }));
  const total = sumValues(outlets, values);
  const totalShare = shares.reduce((sum, share) => sum + share, 0); // 100, or 0 when nothing was spent

  return (
    <section className="rounded-3xl border border-line bg-surface p-5">
      <h2 id="outlet-list-heading" className="text-lg font-extrabold">
        Detalle por enchufe
      </h2>
      <table aria-labelledby="outlet-list-heading" className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-xs font-bold text-muted">
            <th scope="col" className="py-1.5 text-left">
              Enchufe
            </th>
            <th scope="col" className="py-1.5 text-right">
              kWh
            </th>
            <th scope="col" className="py-1.5 text-right">
              Costo
            </th>
            <th scope="col" className="w-2/5 py-1.5 pl-4 text-left">
              % del costo
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ outlet, value, share, color }) => (
            <tr key={outlet.id}>
              <th scope="row" className="py-2.5 text-left font-bold">
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className="size-2.5 flex-none rounded-full" style={{ background: color }} />
                  {outlet.name}
                </span>
              </th>
              <td className="py-2.5 text-right tabular-nums">{fmtKwh(value.kwh)}</td>
              <td className="py-2.5 text-right font-bold tabular-nums">{fmtMoney(value.cost)}</td>
              <td className="py-2.5 pl-4">
                <span className="text-xs font-bold tabular-nums">{share}%</span>
                <span aria-hidden="true" className="mt-1 block h-2 overflow-hidden rounded bg-track">
                  <span className="block h-full rounded" style={{ width: `${share}%`, background: color }} />
                </span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line font-extrabold">
            <th scope="row" className="pt-3 text-left">
              Total
            </th>
            <td className="pt-3 text-right tabular-nums">{fmtKwh(total.kwh)}</td>
            <td className="pt-3 text-right tabular-nums">{fmtMoney(total.cost)}</td>
            <td className="pt-3 pl-4 text-xs tabular-nums">{totalShare}%</td>
          </tr>
        </tfoot>
      </table>
    </section>
  );
}
