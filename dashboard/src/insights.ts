import { label, timeKey, valueLabel } from "./data";
import type { Basis, Detector, Forecast, Measurement, Snapshot } from "./types";

export const detectorNames: Record<Detector, string> = {
  isolation_forest: "Isolation Forest",
  autoencoder: "Autoencoder",
  residual: "Residual Detector",
};
export const detectorIds = Object.keys(detectorNames) as Detector[];
export const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);
const energy = (v: unknown): v is number => finite(v) && v >= 0;

// Calendar arithmetic on naive labels, never a guessed browser/UTC timezone.
function seconds(value: string, basis: Basis): number {
  if (basis === "offset_aware") return Date.parse(timeKey(value, basis)) / 1000;
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$/.exec(value);
  if (!match) return NaN;
  const [, ys, mos, ds, hs, mis, ss, fraction] = match;
  const [y, mo, d, h, mi, s] = [ys, mos, ds, hs, mis, ss].map(Number);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const months = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    y < 1 ||
    mo < 1 ||
    mo > 12 ||
    d < 1 ||
    d > months[mo - 1] ||
    h > 23 ||
    mi > 59 ||
    s > 59
  )
    return NaN;
  const prior = y - 1;
  const days =
    prior * 365 +
    Math.floor(prior / 4) -
    Math.floor(prior / 100) +
    Math.floor(prior / 400) +
    months.slice(0, mo - 1).reduce((a, b) => a + b, 0) +
    d -
    1;
  return (
    days * 86400 + h * 3600 + mi * 60 + s + Number("0." + (fraction || "0"))
  );
}
export function elapsed(origin: string, target: string, basis: Basis): number {
  return seconds(target, basis) - seconds(origin, basis);
}
export function nextPrimary(
  measurement: Measurement | undefined,
  forecasts: Forecast[],
  basis: Basis,
): Forecast | undefined {
  if (!measurement) return undefined;
  return forecasts.find(
    (f) =>
      f.purpose === "primary_forecast" &&
      f.measurement_id === measurement.measurement_id &&
      elapsed(measurement.measurement_timestamp, f.forecast_origin, basis) ===
        0 &&
      elapsed(f.forecast_origin, f.forecast_target_timestamp, basis) === 600,
  );
}
export function chartTime(value: string): string {
  return (
    value.slice(8, 10) + "." + value.slice(5, 7) + " " + value.slice(11, 16)
  );
}
export function scoreTick(v: number): string {
  return finite(v)
    ? Math.abs(v) >= 10000 || (Math.abs(v) > 0 && Math.abs(v) < 0.001)
      ? v.toExponential(1)
      : valueLabel(v, 3)
    : "—";
}
const percent = (v: number, base: number) =>
  base > 0 ? ((v - base) / base) * 100 : null;
const difference = (p: number) =>
  Math.abs(p) < 0.05
    ? "практично на рівні"
    : `на ${valueLabel(Math.abs(p))}% ${p > 0 ? "вище" : "нижче"}`;
export function buildInsights(data: Snapshot) {
  const rows = [...data.measurements].sort((a, b) =>
    timeKey(a.measurement_timestamp, data.basis).localeCompare(
      timeKey(b.measurement_timestamp, data.basis),
    ),
  );
  const latest = rows.at(-1);
  const valid = rows.filter(
    (m) =>
      energy(m.energy_wh) &&
      m.interval_seconds > 0 &&
      m.interval_seconds === latest?.interval_seconds,
  );
  const mean = valid.length
    ? valid.reduce((s, m) => s + m.energy_wh, 0) / valid.length
    : null;
  const interval =
    latest?.interval_seconds === 600
      ? "10 хвилин"
      : `${latest?.interval_seconds ?? "—"} секунд`;
  const window = rows.length
    ? `${label(rows[0].measurement_timestamp)} — ${label(latest!.measurement_timestamp)}`
    : "вікно ще порожнє";
  const delta =
    latest && energy(latest.energy_wh) && mean !== null && valid.length >= 2
      ? percent(latest.energy_wh, mean)
      : null;
  let consumption =
    latest && energy(latest.energy_wh)
      ? `Останнє вимірювання: ${valueLabel(latest.energy_wh)} Wh за ${interval}.`
      : "Останнє споживання недоступне або некоректне.";
  consumption +=
    valid.length >= 2
      ? ` Середнє за вікно: ${valueLabel(mean)} Wh (${valid.length} зі ${rows.length} вимірювань з однаковим інтервалом).`
      : " Для порівняння із середнім потрібно щонайменше два коректні вимірювання.";
  if (delta !== null)
    consumption += ` Останнє значення ${difference(delta)} середнього.`;
  else if (mean === 0 && valid.length >= 2)
    consumption += " Відсоткове порівняння з нульовим середнім не визначене.";
  const recent = rows.slice(-6);
  const contiguous =
    recent.length === 6 &&
    recent.every(
      (m, i) =>
        energy(m.energy_wh) &&
        m.interval_seconds === latest?.interval_seconds &&
        (i === 0 ||
          elapsed(
            recent[i - 1].measurement_timestamp,
            m.measurement_timestamp,
            data.basis,
          ) === m.interval_seconds),
    );
  let trend =
    "Для оцінки короткої динаміки потрібно 6 послідовних вимірювань з однаковим інтервалом.";
  if (contiguous) {
    const avg = (items: Measurement[]) =>
      items.reduce((s, m) => s + m.energy_wh, 0) / items.length;
    const change = percent(avg(recent.slice(3)), avg(recent.slice(0, 3)));
    trend =
      change === null
        ? "Динаміку у відсотках не обчислено: попередні три значення мають нульове середнє."
        : `Середнє останніх трьох інтервалів ${difference(change)} середнього попередніх трьох. Це коротке порівняння, не довгострокова тенденція.`;
  }
  const next = nextPrimary(latest, data.forecasts, data.basis);
  const readyForecast =
    next?.status === "ready" && energy(next.predicted_energy_wh);
  const forecastDelta =
    readyForecast && latest && energy(latest.energy_wh)
      ? percent(next.predicted_energy_wh!, latest.energy_wh)
      : null;
  let forecast =
    "HGB20: відповідний прогноз наступного інтервалу ще недоступний.";
  if (next?.status === "warmup")
    forecast =
      "HGB20 накопичує необхідну історію вимірювань для формування прогнозу.";
  if (next?.status === "incompatible")
    forecast = "HGB20 не застосовується до цього джерела: несумісність моделі.";
  if (next?.status === "gap")
    forecast = "HGB20: прогноз недоступний через пропуск часової історії.";
  if (readyForecast)
    forecast =
      `На інтервал із цільовим часом ${label(next.forecast_target_timestamp)} HGB20 прогнозує ${valueLabel(next.predicted_energy_wh)} Wh за 10 хвилин.` +
      (forecastDelta === null
        ? " Відсоткове порівняння з останнім вимірюванням не визначене."
        : ` Це ${difference(forecastDelta)} останнього фактичного значення.`) +
      " Прогноз не є гарантією.";
  const ids = new Set(rows.map((m) => m.measurement_id));
  const detectors = detectorIds.map((id) => {
    const checked = new Map(
      data.scores
        .filter(
          (s) =>
            s.detector === id &&
            ids.has(s.measurement_id) &&
            s.status === "ready" &&
            finite(s.score) &&
            finite(s.threshold) &&
            typeof s.flag === "boolean",
        )
        .map((s) => [s.measurement_id, s]),
    );
    const flags = [...checked.values()].filter((s) => s.flag === true).length;
    return {
      id,
      checked: checked.size,
      flags,
      text: !checked.size
        ? `${detectorNames[id]}: оцінювання ще недоступне; перевірено 0 зі ${rows.length} вимірювань.`
        : `${detectorNames[id]}: ${flags ? `зафіксовано ${flags} перевищень порога` : "перевищень порога не зафіксовано"}; перевірено ${checked.size} зі ${rows.length} вимірювань вікна.`,
    };
  });
  const summary = [
    delta === null
      ? "Порівняння останнього споживання із середнім поки недоступне."
      : `Останнє споживання ${difference(delta)} середнього у видимому вікні.`,
    readyForecast
      ? forecastDelta === null
        ? "Прогноз наступного інтервалу доступний; відсоткова зміна не визначена."
        : `На наступний інтервал прогноз ${difference(forecastDelta)} останнього факту.`
      : "Відповідний прогноз наступного інтервалу ще не готовий.",
  ];
  const flagged = detectors.filter((d) => d.flags > 0);
  summary.push(
    flagged.length
      ? `Перегляньте інтервали перевищень: ${flagged.map((d) => detectorNames[d.id]).join(", ")}. Це незалежні експериментальні оцінки.`
      : detectors.some((d) => d.checked)
        ? "У доступних оцінках цього вікна перевищень не зафіксовано; перевіряйте покриття кожного методу."
        : "Оцінювання детекторами поки недоступне; відсутність оцінок не означає відсутність відхилень.",
  );
  return {
    consumption,
    trend,
    forecast,
    next,
    detectors,
    summary,
    window,
    latest,
    mean,
  };
}
