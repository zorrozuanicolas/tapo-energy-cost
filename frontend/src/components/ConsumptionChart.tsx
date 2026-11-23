import { type CSSProperties, useState } from "react";

import { BAND_LABEL, buildChart, type ChartMode, pad } from "../lib/chart";
import { bandColor, outletColor } from "../lib/colors";
import { cx } from "../lib/cx";
import { fmtNumber } from "../lib/format";
import type { Band, Bucket, Granularity, Outlet, Tariff } from "../types";

const TITLE: Record<Granularity, string> = {
  hour: "Consumo por hora",
  day: "Consumo por día",
  month: "Consumo por mes",
};

const UNIT: Record<Granularity, string> = { hour: "esa hora", day: "ese día", month: "ese mes" };

interface ModeButtonProps {
  label: string;
  /** A CSS background for the dot: a colour or a gradient. */
  dot: string;
  active: boolean;
  onClick: () => void;
}

function ModeButton({ label, dot, active, onClick }: ModeButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        "flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-3.5 text-sm font-bold",
        active ? "border-ink bg-ink text-surface" : "border-control bg-surface text-ink",
      )}
    >
      <span
        aria-hidden="true"
        className="size-2.5 flex-none rounded-full ring-2 ring-surface"
        style={{ background: dot }}
      />
      {label}
    </button>
  );
}

/**
 * Where the tooltip goes: centred over the slot, but pinned to the left or right edge of the plot near the
 * ends so it is never cut off. `fraction` is the middle of the slot, 0 to 1.
 */
function tooltipPlacement(fraction: number): { style: CSSProperties; className: string } {
  if (fraction < 0.28) return { style: { left: `${fraction * 100}%` }, className: "-translate-x-2.5" };
  if (fraction > 0.72) return { style: { right: `${(1 - fraction) * 100}%` }, className: "translate-x-2.5" };
  return { style: { left: `${fraction * 100}%` }, className: "-translate-x-1/2" };
}

interface BandLegendProps {
  tariff: Tariff;
}

/** Which hours each tariff band covers and what it costs. */
function BandLegend({ tariff }: BandLegendProps) {
  const bands: { band: Band; hours: string }[] = [
    { band: "valle", hours: "00–07 h" },
    { band: "llano", hours: "resto del día" },
    { band: "punta", hours: `${pad(tariff.peak_start)}–${pad(tariff.peak_end)} h` },
  ];
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 pl-10 text-xs text-muted">
      {bands.map(({ band, hours }) => (
        <li key={band} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 flex-none rounded-sm" style={{ background: bandColor(band) }} />
          {`${BAND_LABEL[band]} · ${hours} · $ ${fmtNumber(tariff.rates_with_vat[band], 3)}/kWh`}
        </li>
      ))}
    </ul>
  );
}

interface ConsumptionChartProps {
  buckets: readonly Bucket[];
  outlets: readonly Outlet[];
  granularity: Granularity;
  /** "all" overlays every plug; a number shows only that plug. */
  mode: ChartMode;
  onModeChange: (mode: ChartMode) => void;
  /** Only used by the hourly chart, to explain the colour strip. */
  tariff: Tariff | undefined;
}

/** Bars of kWh per hour, day or month. Hover, focus or tap a bar to see what it cost. */
export function ConsumptionChart({ buckets, outlets, granularity, mode, onModeChange, tariff }: ConsumptionChartProps) {
  // The only state of the chart: the slot under the pointer or the keyboard focus.
  const [hovered, setHovered] = useState<number | null>(null);

  const { ticks, slots } = buildChart(buckets, outlets, mode, granularity);
  const active = hovered === null ? undefined : slots[hovered];
  const placement = tooltipPlacement(((hovered ?? 0) + 0.5) / Math.max(slots.length, 1));

  const overlayDot =
    outlets.length > 1 ? `linear-gradient(90deg, ${outletColor(0)} 50%, ${outletColor(1)} 50%)` : outletColor(0);

  return (
    <section aria-labelledby="chart-heading" className="rounded-3xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 flex-auto basis-56">
          <h2 id="chart-heading" className="text-lg font-extrabold">
            {TITLE[granularity]}
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            En kWh. Pasá el cursor o tocá una barra para ver el costo de {UNIT[granularity]}.
          </p>
        </div>
        <fieldset className="flex min-w-0 flex-wrap gap-1.5">
          <legend className="sr-only">Qué mostrar en el gráfico</legend>
          <ModeButton
            label="Superpuesto"
            dot={overlayDot}
            active={mode === "all"}
            onClick={() => onModeChange("all")}
          />
          {outlets.map((outlet, index) => (
            <ModeButton
              key={outlet.id}
              label={outlet.name}
              dot={outletColor(index)}
              active={mode === outlet.id}
              onClick={() => onModeChange(outlet.id)}
            />
          ))}
        </fieldset>
      </div>

      <div className="mt-4 flex">
        <div aria-hidden="true" className="relative h-60 w-10 flex-none">
          {ticks.map((tick) => (
            <span
              key={tick.pct}
              className="absolute right-2 translate-y-1/2 text-xs text-muted tabular-nums"
              style={{ bottom: `${tick.pct}%` }}
            >
              {tick.label}
            </span>
          ))}
        </div>

        <div className="min-w-0 flex-1">
          <div className="relative h-60">
            {ticks.map((tick) => (
              <div
                key={tick.pct}
                aria-hidden="true"
                className="absolute inset-x-0 border-t border-grid"
                style={{ bottom: `${tick.pct}%` }}
              />
            ))}

            <div className="absolute inset-0 flex">
              {slots.map((slot, index) => (
                <button
                  key={slot.key}
                  type="button"
                  aria-label={slot.aria}
                  onMouseEnter={() => setHovered(index)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(index)}
                  onBlur={() => setHovered(null)}
                  onClick={() => setHovered(index)}
                  className={cx(
                    "relative h-full min-w-0 flex-1 cursor-pointer rounded-sm",
                    hovered === index ? "bg-ink/5" : "bg-transparent",
                  )}
                >
                  <span className="pointer-events-none absolute inset-0 flex justify-center">
                    <span className="relative block h-full w-5/6 max-w-12">
                      {slot.bars.map((bar, rank) => (
                        <span
                          key={bar.color}
                          className={cx(
                            "absolute bottom-0 block min-h-0.5 rounded-t-sm",
                            rank > 0 && "ring-2 ring-surface",
                          )}
                          style={{
                            left: `${(100 - bar.width) / 2}%`,
                            width: `${bar.width}%`,
                            height: `${bar.height}%`,
                            background: bar.color,
                          }}
                        />
                      ))}
                    </span>
                  </span>
                </button>
              ))}
            </div>

            {active?.hasData && (
              <div
                aria-hidden="true"
                className={cx(
                  "pointer-events-none absolute top-1.5 z-10 min-w-50 rounded-xl bg-ink px-3 py-2.5 text-surface shadow-lg",
                  placement.className,
                )}
                style={placement.style}
              >
                <p className="text-sm font-extrabold">{active.title}</p>
                {active.sub && <p className="mt-0.5 text-xs text-tip-muted">{active.sub}</p>}
                <ul className="mt-2 flex flex-col gap-1">
                  {active.rows.map((row) => (
                    <li key={row.name} className="flex items-center gap-2 text-xs tabular-nums">
                      <span
                        className="size-2 flex-none rounded-full"
                        style={row.color ? { background: row.color } : undefined}
                      />
                      <span className={cx("flex-auto", row.bold && "font-extrabold")}>{row.name}</span>
                      <span>{row.kwhText}</span>
                      <span className="min-w-16 text-right font-extrabold">{row.cost}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div aria-hidden="true" className="mt-1.5 flex">
            {slots.map((slot) => (
              <span key={slot.key} className="flex min-w-0 flex-1 justify-center text-xs text-muted">
                <span className="whitespace-nowrap">{slot.label}</span>
              </span>
            ))}
          </div>

          {granularity === "hour" && (
            <div aria-hidden="true" className="mt-1 flex overflow-hidden rounded-sm">
              {slots.map((slot) => (
                <span
                  key={slot.key}
                  className="h-2 min-w-0 flex-1"
                  style={slot.band ? { background: bandColor(slot.band) } : undefined}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {granularity === "hour" && tariff && <BandLegend tariff={tariff} />}
    </section>
  );
}
