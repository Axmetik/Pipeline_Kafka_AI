import { fetchJSON, loadSourceSeries } from "./data";
import type { Page, Run, Source, Selection, Basis } from "./types";
export function sourceHref(
  view: "sources" | "source",
  selection: Partial<Selection> & { channel?: string; category?: string } = {},
) {
  const q = new URLSearchParams({ view });
  for (const [key, value] of Object.entries(selection))
    if (value) q.set(key, value);
  return "?" + q.toString();
}
export function navigate(href: string) {
  history.pushState(null, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}
export const sourceType = (s: Source) =>
  s.source_type === "dataset"
    ? "Джерело датасету"
    : s.source_type === "smart_meter"
      ? "Розумний лічильник"
      : "Джерело вимірювань";
export const sourceDescription = (s: Source) =>
  s.source_type === "dataset" && s.energy_scope === "appliances"
    ? "Сукупна інтервальна енергія побутового обладнання будівлі. Розподілу за окремими приладами немає."
    : s.source_type === "dataset"
      ? "Історичні вимірювання, відтворені як потік даних."
      : "Джерело інтервальних вимірювань. Виробник і місце встановлення не зазначені.";
export const timeContext = (s: Source) =>
  s.timestamp_has_offset
    ? "Час джерела з явним часовим зміщенням"
    : "Час датасету, часовий пояс не визначено";
export const intervalLabel = (s: Source) =>
  s.interval_seconds === 600 ? "10 хв" : `${s.interval_seconds} с`;
export const fetchRuns = (signal: AbortSignal) =>
  fetchJSON<Page<Run>>("/api/runs?limit=1000", signal);
export async function loadSourceDetail(
  selection: Selection,
  windowSize: number,
  signal: AbortSignal,
) {
  // No fallback to a different building/source for an invalid or stale deep link.
  if (!selection.run || !selection.building || !selection.source) return null;
  const result = await fetchJSON<Page<Source>>(
    "/api/sources?" +
      new URLSearchParams({
        run_id: selection.run,
        building_id: selection.building,
        source_id: selection.source,
        limit: "1",
      }),
    signal,
  );
  const source = result.items.find(
    (s) =>
      s.building_id === selection.building && s.source_id === selection.source,
  );
  if (!source) return null;
  const basis: Basis = source.timestamp_has_offset
    ? "offset_aware"
    : "dataset_naive";
  const series = await loadSourceSeries(selection, basis, windowSize, signal);
  return { source, basis, selection, ...series };
}
export type SourceDetail = NonNullable<
  Awaited<ReturnType<typeof loadSourceDetail>>
>;
