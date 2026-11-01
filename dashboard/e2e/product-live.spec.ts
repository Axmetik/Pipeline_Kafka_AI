import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

// Opt-in, read-only verification of an existing replay. Never starts/restarts services or sends data.
test.skip(!process.env.E2E_PRODUCT_RUN, "Requires an existing run and read-only local API");
test("four product pages reflect the existing API without a new replay", async ({ page, request }) => {
  const run = process.env.E2E_PRODUCT_RUN!;
  const statusResponse = await request.get(`/api/pipeline-status?run_id=${encodeURIComponent(run)}`);
  expect(statusResponse.ok()).toBe(true);
  const before = await statusResponse.json();
  const sourcesResponse = await request.get(`/api/sources?run_id=${encodeURIComponent(run)}&limit=1000`);
  expect(sourcesResponse.ok()).toBe(true);
  const source = (await sourcesResponse.json()).items[0];
  expect(source).toBeTruthy();
  const query = new URLSearchParams({run_id: run, building_id: source.building_id,
    source_id: source.source_id, time_basis: source.timestamp_has_offset ? "offset_aware" : "dataset_naive", limit: "144"});
  const measurementsResponse = await request.get(`/api/measurements?${query}`);
  expect(measurementsResponse.ok()).toBe(true);
  const measurements = (await measurementsResponse.json()).items;
  expect(measurements.length).toBeGreaterThan(0);
  const forecastsResponse = await request.get(`/api/forecasts?${query}&purpose=primary_forecast`);
  expect(forecastsResponse.ok()).toBe(true);
  const forecasts = (await forecastsResponse.json()).items;
  expect(forecasts.every((f: {purpose:string}) => f.purpose === "primary_forecast")).toBe(true);
  const captured: string[] = [];
  const directory = path.resolve("../docs/product/p1/screenshots");
  async function capture(name: string) {
    if (process.env.E2E_PRODUCT_CAPTURE !== "1") return;
    await mkdir(directory, {recursive:true});
    await page.screenshot({path:path.join(directory, `${name}.png`), fullPage:true});
    captured.push(name);
  }
  const selected = new URLSearchParams({run, building:source.building_id, source:source.source_id});
  await page.goto(`/?${selected}#overview`);
  await expect(page.getByTestId("measurement-count")).toHaveText(String(before.unique_measurements));
  await expect(page.getByTestId("connection-status")).toContainText("API на зв’язку");
  const literalTime = measurements[0].measurement_timestamp.replace("T", " ");
  await expect(page.locator(".kpis")).toContainText(literalTime);
  if (!source.timestamp_has_offset) {
    await expect(page.getByText("Час датасету, часовий пояс не визначено", {exact:false}).first()).toBeVisible();
  }
  await expect(page.locator(".recharts-line").first()).toBeVisible();
  await capture("overview");
  await page.getByRole("link", {name:"Будівлі", exact:true}).click();
  await expect(page.getByTestId("building-card").filter({hasText:source.building_id})).toBeVisible();
  await capture("buildings");
  await page.getByRole("link", {name:"Аналітика", exact:true}).click();
  await expect(page.getByTestId("page-analytics")).toBeVisible();
  await expect(page.getByTestId("advanced-analytics")).not.toHaveAttribute("open");
  await expect(page.locator(".recharts-line").first()).toBeVisible();
  await capture("analytics");
  await page.getByTestId("advanced-analytics").locator("summary").click();
  for (const detector of ["isolation_forest", "autoencoder", "residual"]) {
    await expect(page.getByTestId(`detector-${detector}`)).toContainText("experimental");
  }
  await expect(page.getByTestId("checkpoint-next")).toContainText(String(before.checkpoints[0].next_offset));
  await capture("analytics-advanced");
  await page.getByRole("link", {name:"Події", exact:true}).click();
  await expect(page.getByTestId("page-events")).toBeVisible();
  await expect(page.locator("#events")).toContainText("experimental");
  await expect(page.getByTestId("email-notifications")).toBeVisible();
  await page.getByRole("link", {name:"Події", exact:true}).click();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await capture("events");
  const after = await (await request.get(`/api/pipeline-status?run_id=${encodeURIComponent(run)}`)).json();
  expect(after.unique_measurements).toBe(before.unique_measurements);
  expect(after.checkpoints).toEqual(before.checkpoints);
  expect(after.duplicate_deliveries).toBe(before.duplicate_deliveries);
  expect(after.rejected_messages).toBe(before.rejected_messages);
  if (process.env.E2E_PRODUCT_CAPTURE === "1") {
    await writeFile(path.join(directory, "provenance.json"), JSON.stringify({
      captured_at: new Date().toISOString(), run, source, timezone_under_test:"Pacific/Honolulu",
      measurements_in_window:measurements.length, primary_forecasts_in_window:forecasts.length,
      latest_measurement: measurements[0], pipeline_before:before, pipeline_after:after, captured,
      method:"Read-only existing API and real rendered React UI; no replay, training or service restart"
    }, null, 2)+"\n");
  }
});
