import { useState } from "react";

import { DashboardSkeleton } from "./components/DashboardSkeleton";
import { ErrorState } from "./components/ErrorState";
import { OutletList } from "./components/OutletList";
import { PeriodNavigator } from "./components/PeriodNavigator";
import { PERIOD_PANEL_ID, PeriodTabs, tabId } from "./components/PeriodTabs";
import { SummaryCards } from "./components/SummaryCards";
import { WarningBanner } from "./components/WarningBanner";
import { useConsumption, useDataRange, useTariff } from "./hooks/queries";
import { TIMEZONE } from "./lib/config";
import { footnote } from "./lib/footnote";
import { periodRange, periodTitle, timeIn, todayIn, type View } from "./lib/period";
import { periodValues } from "./lib/values";

export default function App() {
  // The only state: which tab and how many periods back. Everything else is derived on each render.
  const [view, setView] = useState<View>("hoy");
  const [offset, setOffset] = useState(0);

  const today = todayIn(TIMEZONE);
  const range = periodRange(view, offset, today);
  const { title, subtitle } = periodTitle(range, today, timeIn(TIMEZONE));

  const consumption = useConsumption(range, offset === 0);
  const tariff = useTariff(range.ref);
  const dataRange = useDataRange();
  const { data } = consumption;
  const values = data ? periodValues(view, data) : {};

  const changeView = (next: View) => {
    setView(next);
    setOffset(0);
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 pt-6 pb-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-1 basis-64">
          <p className="text-xs font-bold tracking-widest text-muted uppercase">Consumo de enchufes</p>
          <h1 className="mt-1 text-3xl leading-tight font-extrabold">{title}</h1>
          <p className="mt-1.5 text-sm text-muted">{subtitle}</p>
        </div>
        <PeriodTabs view={view} onChange={changeView} />
      </header>

      <main>
        <div role="tabpanel" id={PERIOD_PANEL_ID} aria-labelledby={tabId(view)} className="flex flex-col gap-4">
          <PeriodNavigator
            view={view}
            offset={offset}
            range={range}
            today={today}
            earliest={dataRange.data?.earliest ?? null}
            onOffsetChange={setOffset}
          />

          {data && <WarningBanner warnings={data.warnings} />}
          {consumption.isPending && <DashboardSkeleton />}
          {consumption.isError && <ErrorState onRetry={() => consumption.refetch()} />}

          {data && (
            <>
              <SummaryCards outlets={data.outlets} values={values} />
              {/* The consumption chart goes here (next PR). */}
              <OutletList outlets={data.outlets} values={values} />
            </>
          )}
        </div>
      </main>

      <footer>
        <p className="px-1 text-xs leading-normal text-muted">{footnote(tariff.data)}</p>
      </footer>
    </div>
  );
}
