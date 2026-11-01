import { test, expect, type Page } from "@playwright/test";

test.use({ actionTimeout: 10000 });
test.setTimeout(60000);

// Browser-test fixtures only. Product screenshots use the existing real PostgreSQL/API.
async function productFixture(
  page: Page,
  options = { catalogueError: false, offline: false },
) {
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
      building_id: "office",
      source_id: "meter-2",
      source_type: "smart_meter",
      interval_seconds: 600,
      timezone: null,
      timestamp_has_offset: false,
    },
  ];
  const queries: string[] = [];
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    queries.push(u.href);
    const endpoint = u.pathname.split("/").at(-1)!;
    const global = endpoint === "sources" && !u.searchParams.has("run_id");
    if (options.offline || (global && options.catalogueError)) {
      await route.fulfill({ status: 503, json: { detail: "test offline" } });
      return;
    }
    const office = u.searchParams.get("source_id") === "meter-2";
    const t = [
      "2016-01-11T17:20:00",
      "2016-01-11T17:10:00",
      "2016-01-11T17:00:00",
    ];
    const measurements = t.map((measurement_timestamp, i) => ({
      measurement_id: `m${i}`,
      measurement_timestamp,
      energy_wh: office ? 100 : 50 + i * 10,
      interval_seconds: 600,
      feature_status: office ? "incompatible" : "ready",
      received_at: "2026-11-01T10:00:00Z",
      time_basis: "dataset_naive",
    }));
    const values: Record<string, unknown[]> = {
      runs: [{ run_id: "run-a" }, { run_id: "run-b" }],
      sources: global
        ? [
            ...sources,
            {
              building_id: "archive",
              source_id: "old-source",
              source_type: "dataset",
              interval_seconds: 600,
              timezone: null,
              timestamp_has_offset: false,
            },
          ]
        : sources,
      measurements,
      forecasts: measurements.map((m, i) => ({
        forecast_id: `f${i}`,
        measurement_id: m.measurement_id,
        forecast_origin: m.measurement_timestamp,
        forecast_target_timestamp: ["2016-01-11T17:30:00", ...t][i],
        purpose: "primary_forecast",
        generated_at: "2026-11-01T10:00:01Z",
        predicted_energy_wh: office ? null : 60,
        status: office ? "incompatible" : "ready",
        model_version: "hgb-fixture",
      })),
      "anomaly-scores": ["isolation_forest", "autoencoder", "residual"].map(
        (detector) => ({
          score_id: detector,
          measurement_id: "m0",
          measurement_timestamp: t[0],
          detector,
          score: null,
          threshold: 1,
          flag: null,
          status: "warmup",
          maturity: "experimental",
        }),
      ),
      events: [
        {
          episode_id: "episode-test",
          detector: "autoencoder",
          start_timestamp: t[1],
          end_timestamp: t[0],
          flagged_points: 2,
          status: "open",
          maturity: "experimental",
          model_version: "ae-test",
          threshold_version: "q99-test",
        },
      ],
      "combined-decisions": [
        {
          decision_id: "decision",
          measurement_id: "m0",
          measurement_timestamp: t[0],
          rule: "unanimous",
          rule_version: "unanimous-test",
          coverage_count: 0,
          available_trigger_count: 0,
          trigger_count: null,
          flag: null,
          status: "warmup",
          triggered_methods: [],
          maturity: "experimental",
        },
      ],
      "combined-events": [],
      models: [],
      notifications: [
        {
          notification_id: "email",
          episode_id: "episode-test",
          kind: "individual",
          method: "autoencoder",
          created_at: "2026-11-01T10:00:00Z",
          status: "suppressed",
          attempt_count: 0,
          suppression_reason: "delivery_disabled",
          error_category: null,
        },
      ],
    };
    await route.fulfill({
      json:
        endpoint === "pipeline-status"
          ? {
              worker_status: "unknown",
              unique_measurements: 3,
              forecasts: 6,
              anomaly_scores: 9,
              duplicate_deliveries: 0,
              rejected_messages: 0,
              checkpoints: [{ next_offset: 3 }],
              recent_errors: [],
              last_processed_at: "2026-11-01T10:00:00Z",
            }
          : {
              items: values[endpoint] ?? [],
              next_cursor: null,
              order: "descending",
            },
    });
  });
  return queries;
}
test("four product views, catalogue selection, URL and back navigation", async ({
  page,
}) => {
  const queries = await productFixture(page);
  await page.goto("/?run=run-a");
  await expect(page.getByTestId("page-overview")).toBeVisible();
  await expect(page.getByTestId("measurement-count")).toHaveText("3");
  await expect(page.getByTestId("next-forecast")).toContainText(
    "2016-01-11 17:30:00",
  );
  await expect(page.getByTestId("advanced-analytics")).toHaveCount(0);
  await page.getByRole("link", { name: "Будівлі", exact: true }).click();
  await expect(page.getByTestId("building-card")).toHaveCount(3);
  await expect(
    page.getByRole("button", {
      name: "Відкрити archive / old-source",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(page.getByText("Сумісність ще не перевірена")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Відкрити office / meter-2", exact: true })
    .click();
  await expect(page.getByTestId("page-analytics")).toBeVisible();
  await expect(page.getByLabel("Будівля", { exact: true })).toHaveValue(
    "office",
  );
  await expect(page.getByTestId("warmup-state")).toContainText(
    "модель не застосовується",
  );
  await expect(page.getByTestId("next-forecast")).toContainText("—");
  await expect(page).toHaveURL(/source=meter-2#analytics/);
  await expect(page.getByTestId("detector-residual")).toHaveCount(0);
  await page.getByTestId("advanced-analytics").locator("summary").click();
  await expect(page.getByTestId("detector-residual")).toContainText(
    "experimental",
  );
  await expect(page.locator(".pipeline .unknown")).toHaveText("Невідомий");
  await page.goBack();
  await expect(page.getByTestId("page-buildings")).toBeVisible();
  await page.getByRole("link", { name: "Події", exact: true }).click();
  await expect(page.getByTestId("page-events")).toBeVisible();
  await expect(
    page.getByText("Пріоритет фізичної несправності не визначено.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.locator(".row-details summary").click();
  await expect(page.getByText("Модель: ae-test")).toBeVisible();
  await page.getByLabel("Тип історії").selectOption("email");
  await expect(page.getByTestId("email-notifications")).toContainText(
    "Придушено",
  );
  await expect(page.locator("#events")).toHaveCount(0);
  expect(
    queries
      .filter((q) => q.includes("/forecasts?"))
      .every((q) => q.includes("purpose=primary_forecast")),
  ).toBe(true);
});
test("portfolio failure/retry and API outage retain honest states", async ({
  page,
}) => {
  const options = { catalogueError: true, offline: false };
  await productFixture(page, options);
  await page.goto("/?run=run-a#buildings");
  await expect(page.getByRole("alert")).toContainText(
    "Не вдалося завантажити портфель",
  );
  options.catalogueError = false;
  await page.getByRole("button", { name: "Оновити портфель" }).click();
  await expect(page.getByTestId("building-card")).toHaveCount(3);
  await page.getByRole("link", { name: "Огляд", exact: true }).click();
  options.offline = true;
  await expect(page.getByRole("alert")).toContainText(
    "Зв’язок із API втрачено",
  );
  await expect(page.getByTestId("measurement-count")).toHaveText("3");
  options.offline = false;
  await expect(page.getByTestId("connection-status")).toContainText(
    "API на зв’язку",
  );
});
test("visible window is retained across views and legacy deep links open advanced", async ({
  page,
}) => {
  const queries = await productFixture(page);
  await page.goto("/?run=run-a#analytics");
  await page.getByLabel("Видиме вікно").selectOption("72");
  await expect
    .poll(() =>
      queries.some(
        (q) => q.includes("/measurements?") && q.includes("limit=72"),
      ),
    )
    .toBe(true);
  await page.getByRole("link", { name: "Будівлі", exact: true }).click();
  await expect(page.getByTestId("building-card")).toHaveCount(3);
  await page.getByRole("link", { name: "Аналітика", exact: true }).click();
  await expect(page.getByLabel("Видиме вікно")).toHaveValue("72");
  await page.goto("/?run=run-a#models");
  await expect(page.locator("#models")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Аналітика", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});
test("all product views fit a mobile viewport without page overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await productFixture(page);
  await page.goto("/?run=run-a");
  for (const name of ["Огляд", "Будівлі", "Аналітика", "Події"]) {
    await page.getByRole("link", { name, exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
