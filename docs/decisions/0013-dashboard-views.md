# 0013. Dashboard views

- Status: accepted
- Date: 2026-11-23

## Context

The frontend foundation exists ([0012](0012-frontend-stack.md)): tooling, types, an API client and the date and
number helpers. This decision covers the screen built on top of it, in two steps. The first step is the data and
the page shell: tabs, a period navigator, summary cards and a table per plug. The second step is the consumption
chart and the live power.

The screen answers two questions: how much did each plug use and cost in a period (today, a week, a month),
and what is each plug drawing right now. The data comes from REST for history ([0007](0007-rest-api.md)) and from
Server-Sent Events for live power ([0009](0009-live-stream.md)).

The constraints are the usual ones: one person has to be able to understand and explain every piece, the page has
to be accessible, and CI rejects a change that breaks a test, the lint or the strict type check.

## Decision

### Data and state

- **TanStack Query for server data.** One hook per endpoint, with a lifetime that fits the data. The current
  period is refetched every 30 s and counts as stale after 10 s. A past period never changes, so it is fetched once
  and kept. The tariff is cached for an hour and the first day with data for five minutes. Every request receives
  the query's `AbortSignal`, so moving to another period cancels the request still in flight.
- **Very little state of our own.** `App` holds three values: the tab, how many periods back and what the chart
  shows. Everything else is derived on each render. They live in `App`, not in the chart, so that the choice
  survives a change of tab or period (the chart is replaced by a placeholder while the next period loads).
- **A stale choice falls back instead of breaking.** If the chosen plug is no longer in the data, the chart shows
  every plug. This is computed during the render, not corrected with an effect.
- **The monthly tab describes one month.** It draws twelve months, but the cards and the table show the selected
  one, which is the last bar.

### The chart

- **Hand-drawn bars in HTML and CSS, with no chart library.** The chart is one kind of graphic: bars of kWh per
  hour, day or month. Each slot is a `<button>` whose `aria-label` says everything the tooltip says, so the chart
  works with a keyboard and a screen reader. Hover, focus and tap all show the tooltip, which is hidden from
  assistive technology because the label already carries the same text.
- **The logic is pure and the component only draws.** `lib/chart.ts` builds the scale, the texts, the bars, the
  tooltip rows and the spoken label for every slot, and has its own tests. `ConsumptionChart` turns that into
  elements. There is no `useMemo`: building a model of at most 24 slots on each render costs less than keeping a
  cache valid.
- **Overlay or one plug.** With several plugs, the bars of a slot overlap: the biggest is the widest and sits at the
  back, so every plug stays visible. A row of buttons above the chart (`aria-pressed`, inside a `<fieldset>`)
  chooses the overlay or a single plug, and the scale follows the plugs that are shown.
- **Colours are design tokens.** They are declared in `@theme static` in `index.css`: surfaces, text, the three
  tariff bands and one colour per plug. `static` is needed because the plug and band colours are only used from
  inline styles, where Tailwind cannot see them.
- **The tabs follow the ARIA tab pattern**: a tab list with one tab in the tab order and arrow keys, Home and End
  to move, and a labelled panel.

### Live power

- **A hook over `EventSource`.** `useLive` opens the stream, keeps the latest reading of each plug and closes the
  stream when the component goes away. The browser reconnects by itself, and the server sends the latest reading
  of each plug again when it does ([0009](0009-live-stream.md)).
- **Events are checked, not trusted.** `JSON.parse` returns `any`, and a type assertion would hide a wrong shape.
  `parseLiveReading` checks each field and ignores an event that is not a reading.
- **A `connected` flag hides old readings.** It is true between the stream's `open` and `error` events. While it
  is false the cards say nothing about live power, because the last value would look current.
- **Live power is shown on every tab and period.** Whether a plug is online does not depend on the period being
  looked at, so tying the line to "today" would hide a true and useful fact. The line reads "Ahora" ("now"), and
  the totals above it say which period they cover. The stream stays open on every tab: it costs one small event
  every 10 s, and the line is already there when returning to a tab.

### The date picker

- **Clicking the control toggles the calendar.** The browser closes an open calendar on the press of a click, so
  the click that follows used to open it again. The component keeps a flag, in a ref because nothing is drawn from
  it, and does nothing on a click while it is set. It also cancels the calendar icon's own opening, which would
  otherwise happen a second time. A press on the label, which moves the focus out of the field, is not treated as
  leaving the control.

### Tests

- **jsdom and Testing Library, chosen per file** with a `// @vitest-environment jsdom` comment, so the pure tests
  stay in Node.
- **One test renders the whole `App`** against a fake `fetch` and a fake `EventSource`. It covers what the pieces
  cannot show alone: that the tab, the period, the chart's choice and the live power work together.

## Alternatives considered

- **A chart library** (Recharts, Chart.js, visx): less drawing code, and zoom or brush for free. It would be a
  dependency to learn and to restyle for one kind of graphic, and its accessibility would be harder to control than
  a button per bar.
- **Redux, Zustand or Context for the state**: three values and a server cache do not need a store. TanStack Query
  holds the server data.
- **Choosing the plug through the rows of the table**: one place to look instead of two. But a table row that
  doubles as a control is awkward to make accessible, and the overlay needs a button of its own anyway. The table
  stays a plain `<table>`.
- **Live power from polling the REST API**: no stream to manage. But the backend already has one, and polling
  every 10 s from every open tab would cost more requests than one event stream.
- **Showing live power only for the current day**: the first plan. It ties a fact about the plug to a period that
  has nothing to do with it.
- **Telling "stream down" apart with a visible message on each card**: it would be noise next to totals that are
  still correct. The line is a bonus, so it just disappears.
- **A date-picker library**: a calendar we draw ourselves, with none of the native quirks. It is a lot of
  accessible code for what a native field already does, and the quirks are cosmetic or fixed above.

## Consequences

- The chart has no zoom, brush or export. If they are needed, a library becomes worth its cost.
- The position of the tooltip and the heights of the bars are not covered by tests, because jsdom does no layout.
  They were checked by eye in the browser against the real backend.
- The date picker depends on how Chrome and Edge behave, which no test can reproduce, because the calendar is
  browser interface. Firefox and Safari were not tried. A change in the browser could bring the old behaviour back.
- The OpenAPI schema still describes `/api/live` as JSON instead of an event stream, which only affects `/docs`.
- With the stream down, the cards lose the live line, and nothing tells the user why.
- The tests that drive the whole page need fakes for `fetch` and `EventSource`, which have to follow the real
  shapes by hand.
