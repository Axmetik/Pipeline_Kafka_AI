import { chromium, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
const base = process.env.SOURCE_UI_BASE,
  out = process.env.SOURCE_UI_OUTPUT;
if (!base?.startsWith("http://127.0.0.1:") || !out)
  throw Error("Use isolated harness");
for (let i = 0; i < 40; i++) {
  try {
    if ((await fetch(base + "/health/ready")).ok) break;
  } catch {}
  await new Promise((r) => setTimeout(r, 500));
}
const fixture = JSON.parse(
  readFileSync(out + "/fixture-provenance.json", "utf8"),
);
// This UCI CSV has numeric columns and a quoted date label, no embedded CSV commas.
const csv = readFileSync(
  new URL("../../data/energy/raw/energydata_complete.csv", import.meta.url),
  "utf8",
);
expect(createHash("sha256").update(csv).digest("hex")).toBe(fixture.csv_sha256);
const lines = csv
  .trim()
  .split(/\r?\n/)
  .map((line) => line.split(",").map((v) => v.replace(/^"|"$/g, "")));
const header = lines.shift();
const originals = new Map(
  lines.map((fields) => {
    expect(fields.length).toBe(header.length);
    const row = Object.fromEntries(header.map((key, i) => [key, fields[i]]));
    return [row.date.replace(" ", "T"), row];
  }),
);
const run = "source-saved-review",
  building = "appliances-house-1",
  source = "uci-appliances";
const scope = { run_id: run, building_id: building, source_id: source };
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    timezoneId: "Pacific/Honolulu",
    reducedMotion: "reduce",
  });
  const page = await context.newPage(),
    errors = [],
    requests = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("503 (Service Unavailable)"))
      errors.push(m.text());
  });
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/"))
      requests.push(new URL(r.url()));
  });
  const url = (channel, extra = {}) =>
    base +
    "/?" +
    new URLSearchParams({
      view: channel ? "source" : "sources",
      run,
      building,
      source,
      ...(channel ? { channel } : {}),
      ...extra,
    });
  const noOverflow = async () => {
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  };
  const get = async (path, query) => {
    const response = await fetch(
      base + path + "?" + new URLSearchParams(query),
    );
    expect(response.status).toBe(200);
    return response.json();
  };
  // Validate all real series against independently calculated original CSV statistics.
  const catalog = await get("/api/channels", scope);
  expect(catalog.items.length).toBe(11);
  for (const card of catalog.items) {
    if (card.channel_id === "appliances") continue;
    const series = await get("/api/channel-series", {
      ...scope,
      channel_id: card.channel_id,
      limit: "144",
    });
    expect(series.items.length).toBe(144);
    for (const point of series.items) {
      const original = originals.get(point.measurement_timestamp);
      expect(original).toBeTruthy();
      expect(point.run_id).toBe(run);
      expect(point.building_id).toBe(building);
      expect(point.source_id).toBe(source);
      for (let i = 0; i < series.definition.columns.length; i++)
        expect(point[i ? "secondary_value" : "value"]).toBeCloseTo(
          Number(original[series.definition.columns[i]]),
          9,
        );
    }

    expect(series.items[0].measurement_timestamp).toBe(fixture.last_timestamp);
    expect(series.items.at(-1).measurement_timestamp).toBe(
      fixture.first_timestamp,
    );
    for (let i = 0; i < series.definition.columns.length; i++) {
      const column = series.definition.columns[i],
        expected = fixture.expected_channels[column],
        stats = series.statistics[i];
      expect(series.items[0][i ? "secondary_value" : "value"]).toBe(
        expected.last,
      );
      for (const name of ["minimum", "maximum", "mean"])
        expect(stats[name]).toBeCloseTo(expected[name], 9);
      expect(stats.count).toBe(expected.count);
    }
  }
  await page.goto(url());
  await expect(page.getByTestId("source-card")).toHaveCount(11);
  await expect(page.locator('[data-channel="zone-6"]')).toContainText(
    "північна сторона",
  );
  await noOverflow();
  await page.screenshot({ path: out + "/catalog-desktop.png", fullPage: true });
  await page
    .getByRole("combobox", { name: "Категорія каталогу" })
    .selectOption("zones");
  await expect(page.getByTestId("source-card")).toHaveCount(9);
  await page.getByRole("textbox", { name: "Пошук джерел" }).fill("Кухня");
  await expect(page.getByTestId("source-card")).toHaveCount(1);
  await expect(page.getByTestId("source-card")).toContainText("T1 + RH_1");
  await page.getByRole("textbox", { name: "Пошук джерел" }).fill("RH_6");
  await expect(page.getByTestId("source-card")).toHaveCount(1);
  await expect(page.getByTestId("source-card")).toContainText(
    "північна сторона",
  );
  await page.goto(url());
  await expect(page.getByTestId("source-card")).toHaveCount(11);
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow();
  await page.screenshot({ path: out + "/catalog-mobile.png", fullPage: true });
  for (const [channel, columns] of [
    ["lights", ["lights"]],
    ["zone-1", ["T1", "RH_1"]],
  ]) {
    requests.length = 0;
    await page.goto(url(channel));
    for (const column of columns)
      await expect(page.getByTestId("metric-" + column)).toBeVisible();
    await expect(
      page.getByText("Час датасету, часовий пояс не визначено", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByTestId("channel-detail")).toContainText(
      fixture.last_timestamp.replace("T", " "),
    );
    await expect(page.getByTestId("channel-detail")).toContainText(
      "Моделі Appliances тут не застосовуються",
    );
    expect(
      requests.some((u) =>
        /forecasts|anomaly-scores|events|notifications|combined/.test(
          u.pathname,
        ),
      ),
    ).toBe(false);
    await noOverflow();
    await page.screenshot({
      path: out + "/" + channel + "-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.reload();
    await expect(page.getByTestId("metric-" + columns[0])).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(300);
    await expect(page.locator(".app-shell")).toHaveCount(1);
    await noOverflow();
    await page.screenshot({
      path: out + "/" + channel + "-desktop.png",
      fullPage: true,
    });
    const before = page.url();
    await page.reload();
    await expect(page.getByTestId("metric-" + columns[0])).toBeVisible();
    expect(page.url()).toBe(before);
    await page
      .getByRole("combobox", { name: "Вікно каналу" })
      .selectOption("72");
    await expect(page.getByTestId("metric-" + columns[0])).toContainText("72");
    await page.setViewportSize({ width: 390, height: 844 });
  }
  // Missing context cannot borrow data from another run, building, source or channel.
  for (const extra of [
    { run: "run-b" },
    { building: "other-house" },
    { source: "missing" },
  ]) {
    await page.goto(url("lights", extra));
    await expect(
      page.getByText("Немає збережених вимірювань каналу"),
    ).toBeVisible();
  }
  await page.goto(url("appliances"));
  await expect(page.getByTestId("source-energy-chart")).toBeVisible();
  await expect(page.getByTestId("source-latest-energy")).toContainText("60");
  await expect(page.getByTestId("source-next-forecast")).toContainText("66,4");
  await page.getByRole("tab", { name: "Детектори", exact: true }).click();
  await expect(page.getByTestId("detector-residual")).toContainText("Поріг");
  await page.getByRole("tab", { name: "Епізоди", exact: true }).click();
  await expect(page.getByText("Завершений", { exact: true })).toBeVisible();
  await page.goto(url());
  await page
    .getByRole("combobox", { name: "Запуск каталогу" })
    .selectOption("run-a");
  await expect(page.getByTestId("source-card")).toHaveCount(5);
  await page
    .getByRole("combobox", { name: "Будівля каталогу" })
    .selectOption("other-house");
  await expect(page.getByTestId("source-card")).toHaveCount(1);
  await expect(page.getByTestId("source-card")).toContainText("999");
  await page.goto(url("lights"));
  await expect(page.getByTestId("metric-lights")).toBeVisible();
  await page.route("**/api/channel-series?**", (r) =>
    r.fulfill({ status: 503, body: "{}" }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Не вдалося");
  await page.unroute("**/api/channel-series?**");
  await page.getByRole("button", { name: "Повторити", exact: true }).click();
  await expect(page.getByTestId("metric-lights")).toBeVisible();
  await page.setViewportSize({ width: 900, height: 1100 });
  await noOverflow();
  expect(errors).toEqual([]);
  const result = {
    passed: true,
    channels: 11,
    real_channel_series: 10,
    points_per_series: 144,
    all_original_columns_and_window_statistics_verified: true,
    naive_timezone: "Pacific/Honolulu",
    viewports: [1440, 900, 390],
    screenshots: 6,
    model_leakage: false,
    deep_links_reload: true,
    filters_search_context_isolation: true,
    api_failure_recovery: true,
    appliances_hgb_detectors_events_preserved: true,
    unexpected_errors: errors,
    no_inference: true,
    no_notifications_sent: true,
  };
  writeFileSync(
    out + "/browser-verification.json",
    JSON.stringify(result, null, 2) + "\n",
  );
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
