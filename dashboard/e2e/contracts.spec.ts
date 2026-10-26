import { test, expect } from "@playwright/test";
const result = (items: unknown[]) => ({
  items,
  next_cursor: null,
  order: "descending",
});
test("naive labels, target alignment, warmup, filters, experimental and offline recovery", async ({
  page,
}) => {
  const requests: string[] = [];
  let featureStatus = "warmup";
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    requests.push(url.href);
    let value: unknown = result([]);
    if (url.pathname.endsWith("/runs"))
      value = result([{ run_id: "run-a" }, { run_id: "run-b" }]);
    if (url.pathname.endsWith("/sources"))
      value = result(
        ["sensor-1", "sensor-2"].map((source_id) => ({
          building_id: "house",
          source_id,
          timestamp_has_offset: false,
        })),
      );
    if (url.pathname.endsWith("/pipeline-status"))
      value = {
        unique_measurements: 2,
        forecasts: 4,
        anomaly_scores: 6,
        duplicate_deliveries: 0,
        rejected_messages: 0,
        checkpoints: [{ next_offset: 2 }],
        recent_errors: [],
      };
    if (url.pathname.endsWith("/measurements"))
      value = result([
        {
          measurement_id: "m1",
          measurement_timestamp: "2016-01-11T17:10:00",
          energy_wh: 50,
          feature_status: featureStatus,
          received_at: "2026-10-19T00:01:00Z",
        },
        {
          measurement_id: "m0",
          measurement_timestamp: "2016-01-11T17:00:00",
          energy_wh: 40,
          feature_status: featureStatus,
          received_at: "2026-10-19T00:00:00Z",
        },
      ]);
    if (url.pathname.endsWith("/forecasts"))
      value = result([
        {
          forecast_id: "f1",
          purpose: "primary_forecast",
          forecast_origin: "2016-01-11T17:10:00",
          forecast_target_timestamp: "2016-01-11T17:20:00",
          predicted_energy_wh: null,
          status: "warmup",
        },
        {
          forecast_id: "f0",
          purpose: "primary_forecast",
          forecast_origin: "2016-01-11T17:00:00",
          forecast_target_timestamp: "2016-01-11T17:10:00",
          generated_at: "2026-10-19T00:00:01Z",
          predicted_energy_wh: 45,
          status: "ready",
          model_version: "hgb20-test",
        },
      ]);
    if (url.pathname.endsWith("/anomaly-scores"))
      value = result(
        ["isolation_forest", "autoencoder", "residual"].map((detector) => ({
          score_id: detector,
          measurement_id: "m1",
          measurement_timestamp: "2016-01-11T17:10:00",
          detector,
          score: null,
          threshold: 10,
          flag: null,
          status: "warmup",
          maturity: "experimental",
        })),
      );
    await route.fulfill({ json: value });
  });
  await page.goto("/");
  await expect(page.getByTestId("connection-status")).toContainText(
    "API на зв’язку",
  );
  await expect(
    page.getByText("Час датасету, часовий пояс не визначено"),
  ).toBeVisible();
  await expect(page.getByTestId("warmup-state")).toContainText("Прогрів");
  const row = page.getByRole("row").filter({ hasText: "2016-01-11 17:10:00" });
  await expect(row).toContainText("50");
  await expect(row).toContainText("45");
  await page.getByRole("button", { name: "Переглянути ↗" }).first().click();
  await expect(page.getByTestId("measurement-detail")).toContainText(
    "2016-01-11 17:00:00",
  );
  await expect(page.getByTestId("measurement-detail")).toContainText(
    "2026-10-19 00:00:01Z",
  );
  for (const d of ["isolation_forest", "autoencoder", "residual"])
    await expect(page.getByTestId("detector-" + d)).toContainText(
      "experimental",
    );
  await page.getByLabel("Запуск replay", { exact: true }).selectOption("run-a");
  await expect(page.getByLabel("Запуск replay", { exact: true })).toHaveValue(
    "run-a",
  );
  await page.getByLabel("Джерело", { exact: true }).selectOption("sensor-2");
  await expect
    .poll(() =>
      requests.some(
        (x) => x.includes("run_id=run-a") && x.includes("source_id=sensor-2"),
      ),
    )
    .toBeTruthy();
  featureStatus = "incompatible";
  await expect(page.getByTestId("warmup-state")).toContainText(
    "Несумісне джерело",
  );
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 503, json: { detail: "unavailable" } }),
  );
  await expect(page.getByRole("alert")).toContainText(
    "Зв’язок із API втрачено",
  );
  await page.unroute("**/api/**");
  await page.route("**/api/**", (route) =>
    route.fulfill({
      json: route.request().url().includes("pipeline-status")
        ? {
            unique_measurements: 0,
            forecasts: 0,
            anomaly_scores: 0,
            duplicate_deliveries: 0,
            rejected_messages: 0,
            checkpoints: [],
            recent_errors: [],
          }
        : result([]),
    }),
  );
  await expect(page.getByTestId("connection-status")).toContainText(
    "API на зв’язку",
  );
  await expect(page.getByTestId("empty-state")).toBeVisible();
  expect(
    requests
      .filter((x) => x.includes("/forecasts"))
      .every((x) => x.includes("purpose=primary_forecast")),
  ).toBeTruthy();
  expect(
    requests
      .filter((x) => x.includes("/measurements?"))
      .every((x) => x.includes("limit=144")),
  ).toBeTruthy();
});

test("insights follow real API contracts, targets and scoped window counts", async ({
  page,
}) => {
  const queries: string[] = [];
  let exceed = true;
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.href);
    const run = url.searchParams.get("run_id");
    const source = url.searchParams.get("source_id");
    const last = run === "run-a" ? 20 : source === "meter-2" ? 40 : 80;
    let value: unknown = result([]);
    if (url.pathname.endsWith("/runs"))
      value = result([{ run_id: "run-a" }, { run_id: "run-b" }]);
    if (url.pathname.endsWith("/sources"))
      value = result(
        ["house", "office"].flatMap((building_id) =>
          ["meter-1", "meter-2"].map((source_id) => ({
            building_id,
            source_id,
            timestamp_has_offset: false,
            interval_seconds: 600,
          })),
        ),
      );
    if (url.pathname.endsWith("/pipeline-status"))
      value = {
        worker_status: "unknown",
        last_processed_at: "2026-10-26T12:00:00Z",
        unique_measurements: 300,
        forecasts: 600,
        anomaly_scores: 900,
        duplicate_deliveries: 0,
        rejected_messages: 0,
        checkpoints: [{ next_offset: 300 }],
        recent_errors: [],
      };
    if (url.pathname.endsWith("/measurements"))
      value = result([
        {
          measurement_id: "m1",
          measurement_timestamp: "2016-01-12T00:00:00",
          energy_wh: last,
          interval_seconds: 600,
          feature_status: "ready",
          received_at: "2026-10-26T12:00:00Z",
        },
        {
          measurement_id: "m0",
          measurement_timestamp: "2016-01-11T23:50:00",
          energy_wh: 40,
          interval_seconds: 600,
          feature_status: "ready",
          received_at: "2026-10-26T11:59:00Z",
        },
      ]);
    if (url.pathname.endsWith("/forecasts"))
      value = result([
        {
          forecast_id: "f1",
          measurement_id: "m1",
          purpose: "primary_forecast",
          forecast_origin: "2016-01-12T00:00:00",
          forecast_target_timestamp: "2016-01-12T00:10:00",
          predicted_energy_wh: 100,
          status: "ready",
        },
        {
          forecast_id: "f0",
          measurement_id: "m0",
          purpose: "primary_forecast",
          forecast_origin: "2016-01-11T23:50:00",
          forecast_target_timestamp: "2016-01-12T00:00:00",
          predicted_energy_wh: 45,
          status: "ready",
        },
      ]);
    if (url.pathname.endsWith("/anomaly-scores"))
      value = result(
        ["isolation_forest", "autoencoder", "residual"].map((detector) => ({
          score_id: detector,
          measurement_id: "m1",
          measurement_timestamp: "2016-01-12T00:00:00",
          detector,
          score:
            detector === "residual"
              ? null
              : exceed && detector === "isolation_forest"
                ? 11
                : 5,
          threshold: 10,
          flag:
            detector === "residual"
              ? null
              : exceed && detector === "isolation_forest",
          status: detector === "residual" ? "warmup" : "ready",
          maturity: "experimental",
        })),
      );
    if (url.pathname.endsWith("/events"))
      value = result([
        {
          episode_id: "old-event",
          detector: "isolation_forest",
          start_timestamp: "2016-01-11T10:00:00",
          end_timestamp: "2016-01-11T10:10:00",
          status: "closed",
          flagged_points: 1,
          maturity: "experimental",
        },
      ]);
    await route.fulfill({ json: value });
  });
  await page.goto("/");
  const insights = page.getByTestId("energy-insights");
  await expect(insights).toContainText("33,3% вище");
  await expect(insights).toContainText("Isolation Forest");
  await expect(page.getByTestId("next-forecast")).toContainText(
    "Цільовий час: 2016-01-12 00:10:00",
  );
  await expect(page.getByTestId("next-forecast")).toContainText("100");
  await expect(
    page.getByRole("row").filter({ hasText: "2016-01-12 00:00:00" }),
  ).toContainText("45");
  await expect(page.getByTestId("demo-status")).toContainText(
    "Стан відтворення невідомий",
  );
  await expect(page.getByTestId("demo-status")).toContainText(
    "2026-10-26 12:00:00Z",
  );
  await expect(
    page.getByTestId("forecast-chart").locator(".recharts-xAxis-tick-labels"),
  ).toContainText("12.01");
  await insights.locator("summary").click();
  await expect(page.getByTestId("forecast-insight")).toContainText("25% вище");
  await expect(page.getByTestId("insight-residual")).toContainText(
    "оцінювання ще недоступне",
  );
  exceed = false;
  await expect(page.getByTestId("detector-isolation_forest")).toContainText(
    "Перевищень у вибраному вікні: 0",
  );
  await expect(page.locator("#events")).toContainText("2016-01-11 10:00:00");
  await expect(page.locator("#events")).toContainText(
    "за весь вибраний запуск",
  );
  await page.getByLabel("Видиме вікно").selectOption("72");
  await expect
    .poll(() =>
      queries.some(
        (q) => q.includes("/measurements?") && q.includes("limit=72"),
      ),
    )
    .toBeTruthy();
  await page.getByLabel("Будівля", { exact: true }).selectOption("office");
  await expect(insights).toContainText("office / meter-1");
  await page.getByLabel("Джерело", { exact: true }).selectOption("meter-2");
  await expect(insights).toContainText("office / meter-2");
  await expect(insights).toContainText("практично на рівні середнього");
  await page.getByLabel("Запуск replay", { exact: true }).selectOption("run-a");
  await expect(insights).toContainText("33,3% нижче");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(insights).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
