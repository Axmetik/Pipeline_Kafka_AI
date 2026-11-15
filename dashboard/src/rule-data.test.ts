import { afterEach, expect, it, vi } from "vitest";
import { load } from "./data";
afterEach(() => vi.unstubAllGlobals());
it("loads optional persisted pages with identical source scope and bounded limits", async () => {
  const paths: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      const u = new URL(path, "http://localhost");
      paths.push(u);
      const endpoint = u.pathname.split("/").at(-1);
      const items =
        endpoint === "runs"
          ? [{ run_id: "r" }]
          : endpoint === "sources"
            ? [
                {
                  building_id: "b",
                  source_id: "s",
                  timestamp_has_offset: false,
                },
              ]
            : [];
      return {
        ok: true,
        json: async () => ({
          items,
          next_cursor: null,
          order: "descending",
          channel_status: "not_connected",
          unique_measurements: 0,
        }),
      };
    }),
  );
  const result = await load(
    { run: "r", building: "b", source: "s" },
    72,
    new AbortController().signal,
  );
  expect(result.hybridDecisions?.channel_status).toBe("not_connected");
  expect(result.hybridDecisions?.items).toEqual([]);
  for (const endpoint of [
    "rule-assessments",
    "hybrid-decisions",
    "hybrid-events",
  ]) {
    const url = paths.find((x) => x.pathname === "/api/" + endpoint)!;
    expect(url.searchParams.get("run_id")).toBe("r");
    expect(url.searchParams.get("building_id")).toBe("b");
    expect(url.searchParams.get("source_id")).toBe("s");
    expect(url.searchParams.get("time_basis")).toBe("dataset_naive");
    expect(Number(url.searchParams.get("limit"))).toBeLessThanOrEqual(216);
  }
});
