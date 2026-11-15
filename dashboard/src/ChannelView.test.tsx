import { afterEach, expect, it, vi } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import ChannelView, { channelSeriesURL } from "./ChannelView";
import { sourceHref } from "./sourceData";
const selection = { run: "r", building: "house / 1", source: "uci-appliances" };
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("preserves channel and full context in direct links and bounded queries", () => {
  const q = new URLSearchParams(
    sourceHref("source", { ...selection, channel: "zone-6" }).slice(1),
  );
  expect(q.get("channel")).toBe("zone-6");
  expect(q.get("building")).toBe(selection.building);
  const url = new URL(
    channelSeriesURL(selection, "lights", 144),
    "http://localhost",
  );
  expect(url.searchParams.get("run_id")).toBe("r");
  expect(url.searchParams.get("source_id")).toBe("uci-appliances");
  expect(url.searchParams.get("limit")).toBe("144");
});
it("requests measurements only, preserves null and naive labels, shows separate units", async () => {
  const fetch = vi.fn(async () => ({
    ok: true,
    json: async () => ({
      items: [
        {
          measurement_timestamp: "2016-05-01T08:20:00",
          received_at: "2026-11-15T00:00:00Z",
          time_basis: "dataset_naive",
          value: 0,
          secondary_value: null,
        },
      ],
      definition: {
        name: "Кухня",
        category: "zones",
        columns: ["T1", "RH_1"],
        units: ["°C", "%"],
      },
      statistics: [
        { count: 1, minimum: 0, maximum: 0, mean: 0 },
        { count: 0, minimum: null, maximum: null, mean: null },
      ],
    }),
  }));
  vi.stubGlobal("fetch", fetch);
  render(<ChannelView selection={selection} channel="zone-1" />);
  await waitFor(() => expect(screen.getByTestId("metric-T1")).toBeTruthy());
  expect(
    screen.getByText("Час датасету, часовий пояс не визначено"),
  ).toBeTruthy();
  expect(screen.getByTestId("metric-T1").textContent).toContain("0");
  expect(screen.getByTestId("metric-RH_1").textContent).toContain("—");
  expect(screen.getByTestId("metric-RH_1").textContent).toContain(
    "Є відсутні вимірювання: 1",
  );
  expect(
    screen.getByText(/Моделі Appliances тут не застосовуються/),
  ).toBeTruthy();
  for (const [path] of fetch.mock.calls as unknown as [string][]) {
    expect(path).toMatch(/^\/api\/channel-series\?/);
    expect(path).not.toContain("forecast");
  }
});
it("shows empty data rather than substituting another channel", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        items: [],
        definition: { name: "Освітлення", category: "lighting" },
        statistics: [],
      }),
    })),
  );
  render(<ChannelView selection={selection} channel="lights" />);
  await waitFor(() =>
    expect(screen.getByText("Немає збережених вимірювань каналу")).toBeTruthy(),
  );
});
