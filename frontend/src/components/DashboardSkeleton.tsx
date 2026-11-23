/** Grey blocks where the cards and the table will be, while the first response is on its way. */
export function DashboardSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando datos" className="flex animate-pulse flex-col gap-4">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))] gap-3">
        <div className="h-32 rounded-2xl bg-seg" />
        <div className="h-32 rounded-2xl bg-seg" />
        <div className="h-32 rounded-2xl bg-seg" />
      </div>
      <div className="h-60 rounded-3xl bg-seg" />
    </div>
  );
}
