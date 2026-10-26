import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import InsightsPanel from "./InsightsPanel";
import type { Snapshot } from "./types";
afterEach(cleanup);
const snapshot = (
  run: string,
  building: string,
  source: string,
  values: number[],
) =>
  ({
    selection: { run, building, source },
    basis: "dataset_naive",
    measurements: values
      .map((energy_wh, i) => ({
        measurement_id: `m${i}`,
        energy_wh,
        measurement_timestamp: `2016-01-11T17:${i === 0 ? "00" : "10"}:00`,
        interval_seconds: 600,
      }))
      .reverse(),
    forecasts: [],
    scores: [],
  }) as unknown as Snapshot;
it("renders changed replay/building/source/window data without retaining old insights", () => {
  const first = snapshot("a", "house", "meter-a", [40, 80]);
  const { rerender } = render(<InsightsPanel data={first} offline={false} />);
  expect(screen.getByTestId("consumption-insight")).toHaveTextContent("80 Wh");
  expect(screen.getByText(/house \/ meter-a/)).toBeInTheDocument();
  const second = snapshot("b", "office", "meter-b", [100, 20]);
  rerender(<InsightsPanel data={second} offline={false} />);
  expect(screen.getByTestId("consumption-insight")).toHaveTextContent("20 Wh");
  expect(screen.queryByText(/house \/ meter-a/)).toBeNull();
  expect(screen.getByText(/office \/ meter-b/)).toBeInTheDocument();
  rerender(
    <InsightsPanel
      data={snapshot("b", "office", "meter-b", [20])}
      offline={true}
    />,
  );
  expect(screen.getByTestId("consumption-insight")).toHaveTextContent(
    "щонайменше два",
  );
  expect(screen.getByText(/зв’язок із API втрачено/)).toBeInTheDocument();
  rerender(<InsightsPanel data={null} offline={false} />);
  expect(screen.queryByTestId("consumption-insight")).toBeNull();
  expect(screen.getByText("Очікуємо дані для аналізу.")).toBeInTheDocument();
});
