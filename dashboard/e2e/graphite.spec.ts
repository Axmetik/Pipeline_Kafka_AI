import { test, expect, type Page } from "@playwright/test";

// Deliberately synthetic UI fixtures; these are not experimental ML results.
const stamp = (i: number) =>
  i === 144
    ? "2016-05-01T00:00:00"
    : `2016-04-30T${String(Math.floor(i / 6)).padStart(2, "0")}:${String((i % 6) * 10).padStart(2, "0")}:00`;
const methods = ["isolation_forest", "autoencoder", "residual"];
const measurements = Array.from({ length: 144 }, (_, i) => ({
  measurement_id: `fixture-${i}`,
  measurement_timestamp: stamp(i),
  energy_wh: Math.round(70 + 24 * Math.sin(i / 7) + (i % 31 === 0 ? 100 : 0)),
  interval_seconds: 600,
  feature_status: "ready",
  time_basis: "dataset_naive",
  received_at: "2026-10-27T10:00:00Z",
  temperature_c: 21.4,
  relative_humidity_pct: 43,
})).reverse();
async function fixture(page: Page) {
  await page.route("**/api/**", async (route) => {
    const endpoint = new URL(route.request().url()).pathname.split("/").at(-1)!;
    const values: Record<string, unknown> = {
      runs: [{ run_id: "fixture-graphite-review-not-ml-results" }],
      sources: [
        {
          building_id: "Appliances demo",
          source_id: "uci-fixture",
          timestamp_has_offset: false,
        },
      ],
      measurements,
      forecasts: measurements.map((m, i) => ({
        forecast_id: `forecast-${i}`,
        measurement_id: m.measurement_id,
        purpose: "primary_forecast",
        forecast_origin: m.measurement_timestamp,
        forecast_target_timestamp: stamp(144 - i),
        generated_at: "2026-10-27T10:00:01Z",
        predicted_energy_wh: m.energy_wh * 0.92,
        status: "ready",
        model_version: "hgb20-fixture",
        feature_version: "energy-v1-20",
      })),
      "anomaly-scores": measurements.flatMap((m, i) =>
        methods.map((detector, d) => ({
          score_id: `${i}-${d}`,
          measurement_id: m.measurement_id,
          measurement_timestamp: m.measurement_timestamp,
          detector,
          score:
            i === 94 || i === 95
              ? [0.624, 18, 66][d]
              : [
                  0.42 + 0.05 * Math.sin(i / 7),
                  8 + 3 * Math.sin(i / 9),
                  25 + 16 * Math.sin(i / 5),
                ][d],
          threshold: [0.52, 15, 55][d],
          flag: i === 94 || i === 95,
          status: "ready",
          maturity: "experimental",
          model_version: `${detector}-fixture`,
          threshold_version: "q99-fixture",
        })),
      ),
      "combined-decisions": measurements.map((m, i) => ({
        decision_id: m.measurement_id,
        measurement_id: m.measurement_id,
        measurement_timestamp: m.measurement_timestamp,
        rule: "unanimous",
        rule_version: "unanimous-fixture",
        coverage_count: 3,
        available_trigger_count: i === 94 || i === 95 ? 3 : 0,
        trigger_count: i === 94 || i === 95 ? 3 : 0,
        triggered_methods: i === 94 || i === 95 ? methods : [],
        flag: i === 94 || i === 95,
        status: "ready",
        maturity: "experimental",
      })),
      "combined-events": [
        {
          episode_id: "combined-fixture",
          start_timestamp: stamp(48),
          end_timestamp: stamp(49),
          max_trigger_count: 3,
          last_trigger_count: 3,
          triggered_methods: methods,
          flagged_points: 2,
          status: "closed",
          rule_version: "unanimous-fixture",
          closed_reason: "below_threshold",
        },
      ],
      events: [
        {
          episode_id: "individual-fixture",
          detector: "autoencoder",
          start_timestamp: stamp(48),
          end_timestamp: stamp(49),
          status: "closed",
          flagged_points: 2,
          maturity: "experimental",
          model_version: "ae-fixture",
          threshold_version: "q99-fixture",
        },
      ],
      notifications: [
        {
          notification_id: "mail-fixture",
          episode_id: "combined-fixture",
          kind: "combined",
          method: "unanimous",
          created_at: "2026-10-27T10:00:00Z",
          status: "suppressed",
          attempt_count: 0,
          suppression_reason: "delivery_disabled",
          error_category: null,
        },
      ],
      models: ["primary_forecast", "residual_reference", ...methods].map(
        (role) => ({
          model_id: role,
          role,
          model_version: `${role}-fixture-version-for-layout-review`,
          feature_version:
            role === "primary_forecast" ? "energy-v1-20" : "energy-v2-21",
          threshold_version: role.includes("forecast") ? null : "q99-fixture",
          maturity: role === "primary_forecast" ? "baseline" : "experimental",
          feature_names: [],
        }),
      ),
    };
    await route.fulfill({
      json:
        endpoint === "pipeline-status"
          ? {
              worker_status: "unknown",
              unique_measurements: 300,
              forecasts: 600,
              anomaly_scores: 900,
              duplicate_deliveries: 0,
              rejected_messages: 0,
              checkpoints: [{ next_offset: 300, topic: "fixture-review" }],
              recent_errors: [],
              last_processed_at: "2026-10-27T10:00:00Z",
            }
          : {
              items: values[endpoint] ?? [],
              next_cursor: null,
              order: "descending",
            },
    });
  });
  await page.goto("/");
  await expect(page.getByTestId("connection-status")).toContainText(
    "API на зв’язку",
  );
  await expect(
    page.locator(".energy-plot .recharts-line-curve").first(),
  ).toBeVisible();
}
const shots = "../docs/dashboard-graphite-dark/screenshots/";
test("graphite desktop, chart styling, sections and active navigation", async ({
  page,
}) => {
  await fixture(page);
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgba(0, 0, 0, 0)",
  );
  await expect(page.locator(".card").first()).toHaveCSS(
    "background-color",
    "rgb(21, 31, 43)",
  );
  await expect(
    page.getByText("Час датасету, часовий пояс не визначено"),
  ).toBeVisible();
  await expect(
    page.getByTestId("detector-residual").locator(".score-unit"),
  ).toHaveText("Wh");
  await expect(page.locator(".kpi .unknown")).toContainText("Невідомий");
  await expect(
    page.locator('.energy-plot path[stroke="var(--forecast)"]'),
  ).toHaveAttribute("stroke-dasharray", /.+/);
  await page.screenshot({ path: shots + "desktop-full.png", fullPage: true });
  await page.locator(".kpis").screenshot({ path: shots + "kpi.png" });
  await page
    .locator(".main-chart")
    .screenshot({ path: shots + "forecast-chart.png" });
  await page
    .locator(".detector-grid")
    .screenshot({ path: shots + "detectors.png" });
  for (const id of ["energy-insights", "combined-panel", "email-notifications"])
    await page.getByTestId(id).screenshot({ path: shots + id + ".png" });
  const plot = await page.locator(".energy-plot").boundingBox();
  await page.mouse.move(plot!.x + plot!.width / 2, plot!.y + plot!.height / 2);
  await expect(
    page.locator(".energy-plot .recharts-default-tooltip"),
  ).toBeVisible();
  await expect(
    page.locator(".energy-plot .recharts-default-tooltip"),
  ).toHaveCSS("background-color", "rgb(27, 40, 54)");
  await page.locator('nav a[href="#models"]').click();
  await expect(page.locator('nav a[href="#models"]')).toHaveAttribute(
    "aria-current",
    "location",
  );
});
for (const width of [1920, 1280, 834, 390, 320])
  test(`responsive graphite ${width}px without page overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    await fixture(page);
    const overflow = await page.evaluate(() =>
      [...document.querySelectorAll("body *")]
        .filter(
          (n) =>
            n.getBoundingClientRect().right > innerWidth + 1 &&
            !n.closest(".table-scroll"),
        )
        .map(
          (n) =>
            `${n.tagName}.${n.className}: ${n.getBoundingClientRect().right}`,
        )
        .slice(0, 15),
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      overflow.join("\n"),
    ).toBe(true);
    for (const detector of methods)
      await expect(page.getByTestId(`detector-${detector}`)).toContainText(
        "experimental",
      );
    expect(
      await page
        .locator(".table-scroll")
        .evaluateAll((nodes) =>
          nodes.every(
            (n) =>
              n.scrollWidth <= n.clientWidth ||
              getComputedStyle(n).overflowX === "auto",
          ),
        ),
    ).toBe(true);
    if (width === 390)
      await page.screenshot({
        path: shots + "mobile-full.png",
        fullPage: true,
      });
  });

test("dark empty and API unavailable states retain their meaning", async ({
  page,
}) => {
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
        : { items: [], next_cursor: null, order: "descending" },
    }),
  );
  await page.goto("/");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await page.screenshot({ path: shots + "empty.png", fullPage: true });
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 503, json: { detail: "fixture unavailable" } }),
  );
  await expect(page.getByRole("alert")).toContainText(
    "Зв’язок із API втрачено",
  );
  await expect(page.getByRole("alert")).toHaveCSS(
    "background-color",
    "rgb(53, 35, 41)",
  );
  await page.screenshot({ path: shots + "offline.png", fullPage: true });
});
