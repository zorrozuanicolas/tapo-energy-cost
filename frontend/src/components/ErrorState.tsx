interface ErrorStateProps {
  onRetry: () => void;
}

export function ErrorState({ onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-2xl border border-line bg-surface p-5">
      <p className="font-bold">No se pudo conectar con el servidor.</p>
      <p className="mt-1 mb-3 text-sm text-muted">
        Revisá que la Raspberry Pi esté encendida y que el backend esté corriendo.
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="min-h-11 cursor-pointer rounded-xl border border-ink bg-ink px-4 text-sm font-bold text-surface"
      >
        Reintentar
      </button>
    </div>
  );
}
