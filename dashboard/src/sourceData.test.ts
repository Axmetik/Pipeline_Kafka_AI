import { afterEach, expect, it, vi } from "vitest";
import {
  loadSourceDetail,
  sourceHref,
  sourceDescription,
  timeContext,
} from "./sourceData";
import { loadSourceSeries } from "./data";
const selection = { run: "r", building: "b / 1", source: "shared-id" };
afterEach(() => vi.unstubAllGlobals());
it("preserves full composite identity in direct links", () => {
  const q = new URLSearchParams(sourceHref("source", selection).slice(1));
  expect(q.get("building")).toBe(selection.building);
  expect(q.get("source")).toBe(selection.source);
  expect(q.get("run")).toBe("r");
});
it("does not silently substitute a different source on a deep link", async () => {
  const fetch = vi.fn(async () => ({
    ok: true,
    json: async () => ({
      items: [{ building_id: "other", source_id: "shared-id" }],
    }),
  }));
  vi.stubGlobal("fetch", fetch);
  expect(
    await loadSourceDetail(selection, 72, new AbortController().signal),
  ).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("scopes every analytic request and preserves unavailable values", async () => {
  const paths: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const u = new URL(path, "http://localhost");
      paths.push(u);
      return {
        ok: true,
        json: async () => ({
          items: u.pathname.endsWith("forecasts")
            ? [{ predicted_energy_wh: null, status: "warmup" }]
            : [],
          next_cursor: null,
        }),
      };
    }),
  );
  const data = await loadSourceSeries(
    selection,
    "dataset_naive",
    72,
    new AbortController().signal,
  );
  expect(data.forecasts[0].predicted_energy_wh).toBeNull();
  for (const u of paths) {
    expect(u.searchParams.get("run_id")).toBe("r");
    expect(u.searchParams.get("building_id")).toBe(selection.building);
    expect(u.searchParams.get("source_id")).toBe(selection.source);
    expect(Number(u.searchParams.get("limit"))).toBeLessThanOrEqual(216);
  }
  expect(
    paths
      .find((u) => u.pathname.endsWith("forecasts"))
      ?.searchParams.get("purpose"),
  ).toBe("primary_forecast");
});
it("describes aggregate dataset energy rather than inventing appliances", () => {
  const source = {
    source_type: "dataset",
    energy_scope: "appliances",
    timestamp_has_offset: false,
  } as Parameters<typeof sourceDescription>[0];
  expect(sourceDescription(source)).toContain(
    "Розподілу за окремими приладами немає",
  );
  expect(timeContext(source)).toContain("часовий пояс не визначено");
});
