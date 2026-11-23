import type { Tariff } from "../types";
import { fmtNumber } from "./format";

const BASE = "Solo se calcula el consumo de los enchufes, sin cargos fijos.";

const pad = (hour: number) => String(hour).padStart(2, "0");

/** The note under the dashboard. It says which prices are used once the tariff has loaded. */
export function footnote(tariff: Tariff | undefined): string {
  if (!tariff) return BASE;
  const year = tariff.valid_from.slice(0, 4);
  const vat = fmtNumber((tariff.vat - 1) * 100, 0);
  return (
    `Precios ${year} del Plan Inteligente Hogares de UTE (tarifa residencial triple horario), ` +
    `con IVA incluido (${vat} %). ${BASE} ` +
    `Horario Punta de ${pad(tariff.peak_start)}:00 a ${pad(tariff.peak_end)}:00, solo en días hábiles; ` +
    `los fines de semana y feriados esas horas se facturan como Llano.`
  );
}
