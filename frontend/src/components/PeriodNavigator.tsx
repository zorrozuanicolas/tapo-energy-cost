import { useRef, useState } from "react";

import { cx } from "../lib/cx";
import { offsetForDate, type PeriodRange, pickerBound, pickerValue, previousPeriodEnd, type View } from "../lib/period";
import { Icon } from "./Icon";

const PICK_LABEL: Record<View, string> = {
  hoy: "Ir al día",
  semanal: "Ir a la semana de",
  mensual: "Ir al mes",
};

const TODAY_LABEL: Record<View, string> = {
  hoy: "Volver a hoy",
  semanal: "Esta semana",
  mensual: "Este mes",
};

interface ArrowButtonProps {
  direction: "previous" | "next";
  disabled: boolean;
  onClick: () => void;
}

function ArrowButton({ direction, disabled, onClick }: ArrowButtonProps) {
  const previous = direction === "previous";
  return (
    <button
      type="button"
      aria-label={previous ? "Período anterior" : "Período siguiente"}
      disabled={disabled}
      onClick={onClick}
      className="flex size-11 cursor-pointer items-center justify-center rounded-xl border border-control bg-surface text-ink"
    >
      <Icon name={previous ? "chevron-left" : "chevron-right"} />
    </button>
  );
}

interface PeriodNavigatorProps {
  view: View;
  /** 0 is the current period, -1 the one before it… It is never positive. */
  offset: number;
  range: PeriodRange;
  today: string;
  /** First day with data, or null while unknown or when there is none. */
  earliest: string | null;
  onOffsetChange: (offset: number) => void;
}

export function PeriodNavigator({ view, offset, range, today, earliest, onOffsetChange }: PeriodNavigatorProps) {
  const canGoBack = earliest !== null && previousPeriodEnd(range) >= earliest;
  const canGoForward = offset < 0;

  const pickerRef = useRef<HTMLInputElement>(null);
  // The focus ring and the highlighted segment of the field are for keyboard users: after a mouse click they
  // stay hidden until the keyboard is used again or the field loses focus.
  const [clicked, setClicked] = useState(false);

  const openPicker = () => {
    setClicked(true);
    pickerRef.current?.showPicker?.(); // missing in old browsers and in jsdom
  };

  const pick = (value: string) => {
    if (!value) return; // the input was cleared
    const target = offsetForDate(view, value, today);
    if (Number.isNaN(target)) return;
    onOffsetChange(Math.min(0, target)); // a typed date in the future stays at the current period
  };

  return (
    // biome-ignore lint/a11y/useSemanticElements: a <fieldset> is for form fields, not for a toolbar
    <div role="group" aria-label="Navegar por el historial" className="flex flex-wrap items-center gap-2">
      <ArrowButton direction="previous" disabled={!canGoBack} onClick={() => onOffsetChange(offset - 1)} />
      <ArrowButton direction="next" disabled={!canGoForward} onClick={() => onOffsetChange(offset + 1)} />
      {/* A click anywhere on the control opens the picker: the browser forwards a click on the label to the input.
          One focus ring goes around the whole control: the input's own ring would be a box inside the border. */}
      <label
        onPointerDown={() => setClicked(true)} // before the browser focuses the field, so nothing flashes while pressing
        className={cx(
          "flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-control bg-surface px-3 text-sm font-bold",
          !clicked && "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ink",
        )}
      >
        {PICK_LABEL[view]}
        <input
          ref={pickerRef}
          type={view === "mensual" ? "month" : "date"}
          data-clicked={clicked || undefined} // index.css hides the highlighted segment while this is set
          onClick={openPicker}
          onKeyDown={() => setClicked(false)}
          onBlur={() => setClicked(false)}
          value={pickerValue(range)}
          min={earliest ? pickerBound(view, earliest) : undefined}
          max={pickerBound(view, today)}
          onChange={(event) => pick(event.target.value)}
          className="min-h-9 cursor-pointer bg-transparent text-sm font-semibold text-ink focus-visible:outline-none"
        />
      </label>
      {offset !== 0 && (
        <button
          type="button"
          onClick={() => onOffsetChange(0)}
          className="min-h-11 cursor-pointer rounded-xl border border-ink bg-ink px-4 text-sm font-bold text-surface"
        >
          {TODAY_LABEL[view]}
        </button>
      )}
    </div>
  );
}
