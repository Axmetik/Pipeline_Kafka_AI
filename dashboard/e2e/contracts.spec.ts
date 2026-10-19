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
