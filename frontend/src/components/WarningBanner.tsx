import type { ApiWarning } from "../types";

// No `default`: when the API gets a new warning code this stops compiling until it has a message.
function warningText(warning: ApiWarning): string {
  switch (warning.code) {
    case "missing_holidays":
      return `Faltan los feriados de ${warning.year} en config/holidays.yaml: los feriados se están calculando como días hábiles, con horario Punta.`;
    case "no_tariff":
      return `No hay una tarifa configurada desde el ${warning.since}: esos costos no se calcularon (config/tariffs.yaml).`;
  }
}

interface WarningBannerProps {
  warnings: readonly ApiWarning[];
}

/** The warnings the API sent with the data, one notice each. */
export function WarningBanner({ warnings }: WarningBannerProps) {
  return warnings.map((warning) => {
    const text = warningText(warning);
    return (
      <p
        key={text}
        role="status"
        className="rounded-xl border border-warning-border bg-warning-bg px-3.5 py-2.5 text-sm text-warning-text"
      >
        {text}
      </p>
    );
  });
}
