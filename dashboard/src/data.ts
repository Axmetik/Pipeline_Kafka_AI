import type {
  Basis,
  Forecast,
  Measurement,
  Page,
  Selection,
  Snapshot,
  Run,
  Source,
  Score,
  Episode,
  Model,
  Status,
  CombinedDecision,
  CombinedEpisode,
} from "./types";

// A naive dataset label is never passed to Date/Date.parse, even for sorting.
export function timeKey(value: string, basis: Basis): string {
  if (basis === "dataset_naive") return value;
  if (!/(Z|[+-]\d\d:\d\d)$/.test(value)) throw new Error("Offset is required");
  return new Date(value).toISOString();
}
export function label(value: string | null | undefined): string {
  return value ? value.replace("T", " ").replace(/\.\d+(?=Z|[+-]|$)/, "") : "—";
}
export function valueLabel(
  value: number | null | undefined,
  digits = 1,
): string {
  return value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat("uk-UA", { maximumFractionDigits: digits }).format(
        value,
      );
}
export function align(
  measurements: Measurement[],
  forecasts: Forecast[],
  basis: Basis,
) {
  const points = new Map<
    string,
    {
      timestamp: string;
      actual: number | null;
      forecast: number | null;
      measurement?: Measurement;
      prediction?: Forecast;
    }
  >();
  for (const m of measurements)
    points.set(timeKey(m.measurement_timestamp, basis), {
      timestamp: m.measurement_timestamp,
      actual: m.energy_wh,
      forecast: null,
      measurement: m,
    });
  const origins = new Set(
    measurements.map((m) => timeKey(m.measurement_timestamp, basis)),
  );
  for (const f of forecasts) {
    if (f.purpose !== "primary_forecast") continue;
    const key = timeKey(f.forecast_target_timestamp, basis);
    // Keep forecasts aligned to targets, including the one next-interval forecast.
    if (!points.has(key) && !origins.has(timeKey(f.forecast_origin, basis)))
      continue;
    const point = points.get(key) ?? {
      timestamp: f.forecast_target_timestamp,
      actual: null,
      forecast: null,
    };
    points.set(key, {
      ...point,
      forecast: f.predicted_energy_wh,
      prediction: f,
    });
  }
  return [...points.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, point]) => point);
}
export async function fetchJSON<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(path, { signal, cache: "no-store" });
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json() as Promise<T>;
}
export async function load(
  selection: Selection,
  windowSize: number,
  signal: AbortSignal,
): Promise<Snapshot> {
  const runs = (await fetchJSON<Page<Run>>("/api/runs?limit=1000", signal))
    .items;
  const run = selection.run || runs.at(-1)?.run_id || "";
  const sources = run
    ? (
        await fetchJSON<Page<Source>>(
          "/api/sources?" + new URLSearchParams({ run_id: run, limit: "1000" }),
          signal,
        )
      ).items
    : [];
  const building = sources.some((s) => s.building_id === selection.building)
    ? selection.building
    : sources[0]?.building_id || "";
  const source =
    sources.find(
      (s) => s.building_id === building && s.source_id === selection.source,
    ) ?? sources.find((s) => s.building_id === building);
  const chosen = { run, building, source: source?.source_id || "" };
  const basis: Basis = source?.timestamp_has_offset
    ? "offset_aware"
    : "dataset_naive";
  const status = await fetchJSON<Status>(
    "/api/pipeline-status?" + new URLSearchParams(run ? { run_id: run } : {}),
    signal,
  );
  if (!run || !source)
    return {
      runs,
      sources,
      selection: chosen,
      measurements: [],
      forecasts: [],
      scores: [],
      events: [],
      moreEvents: false,
      models: [],
      combined: [],
      combinedEvents: [],
      moreCombinedEvents: false,
      status,
      basis,
    };
  const params = {
    run_id: run,
    building_id: building,
    source_id: source.source_id,
    time_basis: basis,
  };
  const query = (extras: Record<string, string>) =>
    new URLSearchParams({ ...params, ...extras }).toString();
  const [
    measurements,
    forecasts,
    scores,
    events,
    models,
    combined,
    combinedEvents,
  ] = await Promise.all([
    fetchJSON<Page<Measurement>>(
      "/api/measurements?" + query({ limit: String(windowSize) }),
      signal,
    ),
    fetchJSON<Page<Forecast>>(
      "/api/forecasts?" +
        query({ limit: String(windowSize + 1), purpose: "primary_forecast" }),
      signal,
    ),
    fetchJSON<Page<Score>>(
      "/api/anomaly-scores?" + query({ limit: String(windowSize * 3) }),
      signal,
    ),
    fetchJSON<Page<Episode>>("/api/events?" + query({ limit: "50" }), signal),
    fetchJSON<Page<Model>>(
      "/api/models?" + new URLSearchParams({ run_id: run, limit: "100" }),
      signal,
    ),
    fetchJSON<Page<CombinedDecision>>(
      "/api/combined-decisions?" + query({ limit: String(windowSize) }),
      signal,
    ),
    fetchJSON<Page<CombinedEpisode>>(
      "/api/combined-events?" + query({ limit: "50" }),
      signal,
    ),
  ]);
  const ids = new Set(measurements.items.map((m) => m.measurement_id));
  return {
    runs,
    sources,
    selection: chosen,
    basis,
    status,
    measurements: measurements.items,
    forecasts: forecasts.items,
    scores: scores.items.filter((s) => ids.has(s.measurement_id)),
    events: events.items,
    moreEvents: events.next_cursor !== null,
    models: models.items,
    combined: combined.items,
    combinedEvents: combinedEvents.items,
    moreCombinedEvents: combinedEvents.next_cursor !== null,
  };
}
