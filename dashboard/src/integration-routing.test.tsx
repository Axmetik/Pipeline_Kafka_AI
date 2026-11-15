import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import App from "./App";
vi.mock("./useMonitor", () => ({
  useMonitor: () => ({
    data: null,
    connection: "loading",
    updated: null,
    newMeasurements: null,
  }),
}));
// Route glue is tested independently of source/API rendering, covered by focused tests.
vi.mock("./SourcesWorkspace", () => ({
  default: ({ route }: { route: string }) => (
    <div data-testid="catalog-route">{route}</div>
  ),
}));
beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  window.scrollTo = vi.fn();
});
afterEach(() => {
  cleanup();
  history.replaceState(null, "", "/");
});
it("retains product Analytics and the persisted rule panel after the merges", () => {
  history.replaceState(null, "", "/?run=r&building=b&source=s#detectors");
  render(<App />);
  expect(screen.getByTestId("page-analytics")).toBeTruthy();
  expect(screen.getByTestId("rule-panel")).toBeTruthy();
  const href = screen
    .getByRole("link", { name: "Пристрої та джерела" })
    .getAttribute("href")!;
  const q = new URLSearchParams(href.slice(1));
  expect(q.get("run")).toBe("r");
  expect(q.get("building")).toBe("b");
  expect(q.get("source")).toBe("s");
});
it("retains hybrid episodes within the product Events view", () => {
  history.replaceState(null, "", "/?run=r#events");
  render(<App />);
  expect(screen.getByTestId("page-events")).toBeTruthy();
  expect(screen.getByTestId("hybrid-events")).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Тип історії" }), {
    target: { value: "hybrid" },
  });
  expect(screen.getByTestId("hybrid-events")).toBeTruthy();
});
it("preserves catalog/channel deep links and returns to product routes on popstate", () => {
  history.replaceState(
    null,
    "",
    "/?view=source&run=r&building=b&source=s&channel=zone-6",
  );
  render(<App />);
  expect(screen.getByTestId("catalog-route").textContent).toContain(
    "channel=zone-6",
  );
  history.pushState(null, "", "/?run=r&building=b&source=s#overview");
  fireEvent(window, new PopStateEvent("popstate"));
  expect(screen.getByTestId("page-overview")).toBeTruthy();
  expect(screen.queryByTestId("catalog-route")).toBeNull();
});
