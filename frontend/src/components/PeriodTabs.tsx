import type { KeyboardEvent } from "react";

import { cx } from "../lib/cx";
import type { View } from "../lib/period";

const VIEWS: readonly { id: View; label: string }[] = [
  { id: "hoy", label: "Hoy" },
  { id: "semanal", label: "Semanal" },
  { id: "mensual", label: "Mensual" },
];

/** Id of the panel these tabs control; the panel itself lives in `App`. */
export const PERIOD_PANEL_ID = "period-panel";

export const tabId = (view: View) => `tab-${view}`;

/** The tab a key moves to, or null when the key is not one of the tab-list keys. */
function targetIndex(key: string, current: number, count: number): number | null {
  switch (key) {
    case "ArrowRight":
      return (current + 1) % count;
    case "ArrowLeft":
      return (current - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

interface PeriodTabsProps {
  view: View;
  onChange: (view: View) => void;
}

export function PeriodTabs({ view, onChange }: PeriodTabsProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = targetIndex(
      event.key,
      VIEWS.findIndex((item) => item.id === view),
      VIEWS.length,
    );
    const target = index === null ? undefined : VIEWS[index];
    if (!target) return;
    event.preventDefault();
    onChange(target.id);
    event.currentTarget.querySelector<HTMLElement>(`#${tabId(target.id)}`)?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label="Período"
      onKeyDown={handleKeyDown}
      className="flex w-full max-w-sm gap-1 rounded-2xl bg-seg p-1"
    >
      {VIEWS.map((item) => {
        const selected = item.id === view;
        return (
          <button
            key={item.id}
            id={tabId(item.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={PERIOD_PANEL_ID}
            // Roving tabindex: Tab enters the list once, the arrow keys move inside it.
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={cx(
              "min-h-11 flex-1 cursor-pointer rounded-xl text-base font-bold",
              selected ? "bg-ink text-surface" : "text-seg-text",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
