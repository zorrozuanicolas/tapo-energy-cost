// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { ApiWarning, Bucket, ConsumptionResponse, OutletValue } from "./types";

// A small fake backend: two plugs, and a different set of totals for each view so a test can tell them apart.
const OUTLETS = [
  { id: 1, slug: "heladera", name: "Heladera" },
  { id: 2, slug: "escritorio", name: "Escritorio" },
];

type Values = Record<string, OutletValue>;

const DAY: Values = { "1": { kwh: 0.15, cost: 1.37 }, "2": { kwh: 0.4, cost: 2.52 } }; // 3,89 in total
const WEEK: Values = { "1": { kwh: 1, cost: 6 }, "2": { kwh: 2, cost: 12 } };
const YEAR: Values = { "1": { kwh: 100, cost: 600 }, "2": { kwh: 200, cost: 1200 } };
const LAST_MONTH: Values = { "1": { kwh: 9, cost: 56.8 }, "2": { kwh: 21, cost: 132.5 } }; // 189,30 in total

const bucket = (outlets: Values): Bucket => ({
  start: "2026-10-01T00:00:00-03:00",
  end: "2026-11-01T00:00:00-03:00",
  has_data: true,
  partial: false,
  band: null,
  rate_per_kwh: null,
  outlets,
});

function consumption(granularity: string): ConsumptionResponse {
  const base = { timezone: "America/Montevideo", outlets: OUTLETS, warnings: warnings };
  if (granularity === "day") return { ...base, granularity: "day", buckets: [], totals: WEEK };
  if (granularity === "month") {
    return { ...base, granularity: "month", buckets: [bucket({}), bucket(LAST_MONTH)], totals: YEAR };
  }
  return { ...base, granularity: "hour", buckets: [], totals: DAY };
}

const TARIFF = {
  valid_from: "2026-01-01",
  vat: 1.22,
  peak_start: 17,
  peak_end: 21,
  rates: { valle: 2.443, llano: 5.172, punta: 12.034 },
  rates_with_vat: { valle: 2.9805, llano: 6.3098, punta: 14.6815 },
};

// What the fake backend answers; each test may change it, and afterEach puts it back.
let earliest: string | null;
let warnings: ApiWarning[];
let consumptionFails: boolean;

beforeEach(() => {
  earliest = "2026-10-01";
  warnings = [];
  consumptionFails = false;
  // Only `Date` is faked, so timers keep working. 18:53 UTC is 15:53 in Montevideo.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-22T18:53:00Z"));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/consumption") {
        if (consumptionFails) return Response.json({ detail: "boom" }, { status: 500 });
        return Response.json(consumption(url.searchParams.get("granularity") ?? "hour"));
      }
      if (url.pathname === "/api/tariff") return Response.json(TARIFF);
      return Response.json({ earliest });
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

const detailTable = () => screen.findByRole("table", { name: "Detalle por enchufe" });
const heading = (name: string) => screen.findByRole("heading", { level: 1, name });
const summary = () => screen.getByRole("region", { name: "Resumen" });

describe("App", () => {
  it("shows today with its cards, its table and the tariff note", async () => {
    renderApp();
    expect(await heading("Jueves 22 de octubre")).toBeInTheDocument();
    expect(screen.getByText("Acumulado hasta las 15:53")).toBeInTheDocument();

    await detailTable();
    expect(within(summary()).getAllByRole("listitem")).toHaveLength(3); // two plugs and the total
    expect(within(summary()).getByText("$ 3,89")).toBeInTheDocument();
    expect(await screen.findByText(/Precios 2026 del Plan Inteligente Hogares/)).toBeInTheDocument();
  });

  it("shows a loading placeholder until the data arrives", async () => {
    renderApp();
    expect(screen.getByRole("status", { name: "Cargando datos" })).toBeInTheDocument();
    await detailTable();
    expect(screen.queryByRole("status", { name: "Cargando datos" })).not.toBeInTheDocument();
  });

  it("switches between the three tabs", async () => {
    const user = renderApp();
    await detailTable();

    await user.click(screen.getByRole("tab", { name: "Semanal" }));
    expect(await heading("Semana del 19 al 25 de octubre")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Semanal" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Semanal");

    await user.click(screen.getByRole("tab", { name: "Mensual" }));
    expect(await heading("Octubre de 2026")).toBeInTheDocument();
  });

  it("describes the selected month, not the twelve months, in the monthly tab", async () => {
    const user = renderApp();
    await detailTable();
    await user.click(screen.getByRole("tab", { name: "Mensual" }));
    await detailTable();

    expect(within(summary()).getByText("$ 189,30")).toBeInTheDocument(); // the last month
    expect(within(summary()).queryByText("$ 1.800,00")).not.toBeInTheDocument(); // the whole year
  });

  it("goes back in history and returns to the present", async () => {
    const user = renderApp();
    await detailTable();
    const back = screen.getByRole("button", { name: "Período anterior" });
    await waitFor(() => expect(back).toBeEnabled()); // the first day with data loads on its own

    await user.click(back);
    expect(await heading("Miércoles 21 de octubre")).toBeInTheDocument();
    expect(screen.getByText("Día completo")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Volver a hoy" }));
    expect(await heading("Jueves 22 de octubre")).toBeInTheDocument();
  });

  it("cannot go back before the first day with data", async () => {
    earliest = "2026-10-22";
    renderApp();
    await detailTable();
    await waitFor(() => expect(screen.getByLabelText("Ir al día")).toHaveAttribute("min", "2026-10-22"));
    expect(screen.getByRole("button", { name: "Período anterior" })).toBeDisabled();
  });

  it("warns when the holidays of a year are missing", async () => {
    warnings = [{ code: "missing_holidays", year: 2027 }];
    renderApp();
    expect(await screen.findByText(/Faltan los feriados de 2027/)).toBeInTheDocument();
  });

  it("warns when there is no tariff for some days", async () => {
    warnings = [{ code: "no_tariff", since: "2026-01-01" }];
    renderApp();
    expect(await screen.findByText(/No hay una tarifa configurada desde el 2026-01-01/)).toBeInTheDocument();
  });

  it("shows an error with a retry button when the server fails", async () => {
    consumptionFails = true;
    const user = renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar con el servidor.");

    consumptionFails = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await detailTable();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
