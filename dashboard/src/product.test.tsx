import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, it, expect, vi } from "vitest";
import { pageFromHash, selectionQuery } from "./navigation";
import KpiCards from "./components/KpiCards";
import BuildingsPage from "./pages/BuildingsPage";
import EventsPage from "./pages/EventsPage";
import type { DashboardView } from "./components/view";
import type { Snapshot, Source } from "./types";
const sources = [
  {
    building_id: "house",
    source_id: "dataset-1",
    source_type: "dataset",
    interval_seconds: 600,
    timezone: null,
    timestamp_has_offset: false,
  },
  {
    building_id: "house",
    source_id: "unselected",
    source_type: "smart_meter",
    interval_seconds: 600,
    timezone: null,
    timestamp_has_offset: false,
  },
  {
    building_id: "archive",
    source_id: "meter-2",
    source_type: "dataset",
    interval_seconds: 600,
    timezone: null,
    timestamp_has_offset: false,
  },
] as Source[];
function view(): DashboardView {
  const data = {
    selection: { run: "run-a", building: "house", source: "dataset-1" },
    sources: [sources[0]],
    measurements: [
      {
        measurement_id: "m",
        energy_wh: 0,
        feature_status: "incompatible",
        measurement_timestamp: "2016-01-01T00:00:00",
        interval_seconds: 600,
      },
    ],
    events: [],
    forecasts: [],
    scores: [],
    combinedEvents: [],
    notifications: [],
    status: { unique_measurements: 300 },
  } as unknown as Snapshot;
  return {
    data,
    chosen: data.selection,
    latest: data.measurements[0],
    next: undefined,
    actualUnit: "Wh / 10 хв",
    choose: vi.fn(),
  } as unknown as DashboardView;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("product navigation contracts", () => {
  it("maps only known pages and preserves old model/detector links", () => {
    expect(pageFromHash("#models")).toBe("analytics");
    expect(pageFromHash("#detectors")).toBe("analytics");
    expect(pageFromHash("#buildings")).toBe("buildings");
    expect(pageFromHash("#unknown")).toBe("overview");
  });
  it("retains page and encodes selection in a shareable URL", () => {
    const q = selectionQuery(
      { run: "a & b", building: "house", source: "meter-1" },
      "#analytics",
    );
    expect(q).toBe("?run=a+%26+b&building=house&source=meter-1#analytics");
  });
});
it("keeps valid zero energy, missing forecast and run-wide counters distinct", () => {
  render(<KpiCards view={view()} />);
  expect(screen.getByTestId("next-forecast")).toHaveTextContent("—");
  expect(screen.getByTestId("measurement-count")).toHaveTextContent("300");
  expect(
    screen.getByText("Усі джерела вибраного запуску · не лише ця будівля"),
  ).toBeVisible();
  expect(screen.getAllByText("0")).toHaveLength(2);
});
it("does not show empty loading counters as zero", () => {
  const v = view();
  v.data = null;
  v.latest = undefined;
  render(<KpiCards view={v} />);
  expect(screen.getByTestId("measurement-count")).toHaveTextContent("—");
  expect(screen.getByTestId("next-forecast")).toHaveTextContent(
    "Очікуємо прогноз",
  );
});
it("portfolio shows only returned metadata and forbids absent run sources", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: sources, next_cursor: null }),
    }),
  );
  const v = view();
  const navigate = vi.fn();
  render(<BuildingsPage view={v} navigate={navigate} />);
  const selected = await screen.findByRole("button", {
    name: "Відкрити house / dataset-1",
  });
  expect(selected).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "Відкрити archive / meter-2" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Відкрити house / unselected" }),
  ).toBeDisabled();
  expect(screen.getByText("Несумісне джерело")).toBeVisible();
  expect(screen.getAllByText("Сумісність ще не перевірена")).toHaveLength(2);
  fireEvent.click(selected);
  expect(v.choose).toHaveBeenCalledWith({
    run: "run-a",
    building: "house",
    source: "dataset-1",
  });
  expect(navigate).toHaveBeenCalledWith("analytics");
});
it("portfolio exposes bounded catalogue and empty state without fake buildings", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], next_cursor: "more" }),
    }),
  );
  render(<BuildingsPage view={view()} navigate={vi.fn()} />);
  expect(await screen.findByTestId("portfolio-empty")).toBeVisible();
  expect(screen.getByText(/Показано перші 1000/)).toBeVisible();
  expect(screen.queryByTestId("building-card")).toBeNull();
});
it("portfolio retries failure and aborts its request on unmount", async () => {
  const fetchMock = vi
    .fn()
    .mockRejectedValueOnce(Error("offline"))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: sources, next_cursor: null }),
    });
  vi.stubGlobal("fetch", fetchMock);
  const { unmount } = render(
    <BuildingsPage view={view()} navigate={vi.fn()} />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Не вдалося");
  fireEvent.click(screen.getByRole("button", { name: "Оновити портфель" }));
  await screen.findAllByTestId("building-card");
  await waitFor(() =>
    expect(screen.getAllByTestId("building-card")).toHaveLength(2),
  );
  const signal = fetchMock.mock.calls.at(-1)![1].signal;
  unmount();
  expect(signal.aborted).toBe(true);
});
it("events separate threshold episodes from UTC email delivery", () => {
  const v = view();
  v.data!.events = [
    {
      episode_id: "e",
      detector: "autoencoder",
      start_timestamp: "2016-01-01T00:00:00",
      end_timestamp: "2016-01-01T00:00:00",
      flagged_points: 1,
      status: "open",
      maturity: "experimental",
      model_version: "ae-v1",
      threshold_version: "q99",
    },
  ];
  v.data!.notifications = [
    {
      notification_id: "mail",
      episode_id: "e",
      kind: "individual",
      method: "autoencoder",
      created_at: "2026-11-01T10:00:00Z",
      status: "failed",
      attempt_count: 1,
      error_category: "connection",
      suppression_reason: null,
    },
  ];
  render(<EventsPage view={v} />);
  expect(
    screen.getByText(/Пріоритет фізичної несправності не визначено/),
  ).toBeVisible();
  expect(screen.getByText("house / dataset-1")).toBeVisible();
  expect(screen.getByText(/Помилка · 1 спроб/)).toBeVisible();
  fireEvent.click(screen.getByText("Деталі", { exact: true }));
  expect(screen.getByText("Модель: ae-v1")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Тип історії"), {
    target: { value: "email" },
  });
  expect(screen.queryByText("Історія експериментальних подій")).toBeNull();
  expect(screen.getByTestId("email-notifications")).toBeVisible();
  expect(screen.getByText(/окремий годинник UTC/)).toBeVisible();
});
