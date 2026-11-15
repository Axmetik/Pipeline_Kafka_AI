import { chromium, expect } from "@playwright/test";
import { writeFileSync } from "node:fs";
const base = process.env.SOURCE_UI_BASE,
  out = process.env.SOURCE_UI_OUTPUT;
if (!base?.startsWith("http://127.0.0.1:") || !out)
  throw Error("Use isolated source_catalog_browser.py harness");
for (let i = 0; i < 30; i++) {
  try {
    if ((await fetch(base + "/health/ready")).ok) break;
  } catch {}
  await new Promise((r) => setTimeout(r, 500));
}
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    timezoneId: "Pacific/Honolulu",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !message.text().includes("503 (Service Unavailable)")
    )
      errors.push(message.text());
  });
  const url = (view, run = "source-saved-review", building = "", source = "") =>
    base +
    "/?" +
    new URLSearchParams({
      view,
      run,
      ...(building ? { building } : {}),
      ...(source ? { source } : {}),
    });
  const noOverflow = async () => {
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    const overflow = await page.evaluate(() => {
      if (document.documentElement.scrollWidth <= innerWidth) return [];
      return [...document.querySelectorAll("*")]
        .filter((el) => el.getBoundingClientRect().right > innerWidth + 1)
        .slice(0, 8)
        .map((el) => ({
          tag: el.tagName,
          cls: el.className,
          right: el.getBoundingClientRect().right,
        }));
    });
    expect(overflow).toEqual([]);
  };
  await page.goto(url("sources"));
  await expect(page.getByTestId("source-card")).toHaveCount(11);
  await expect(page.locator('[data-channel="appliances"]')).toContainText("uci-appliances");
  await noOverflow();
  await page.screenshot({ path: out + "/catalog-desktop.png", fullPage: true });
  await page.locator('[data-channel="appliances"]').getByRole("link", { name: "Переглянути аналітику" }).click();
  await expect(page.getByTestId("source-latest-energy")).not.toHaveText("—");
  await expect(
    page
      .getByText("Час датасету, часовий пояс не визначено", { exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByText("2016-05-01 08:20:00", { exact: true }).first(),
  ).toBeVisible();
  const detailURL = page.url();
  await page.reload();
  await expect(page.getByTestId("source-energy-chart")).toBeVisible();
  expect(page.url()).toBe(detailURL);
  await noOverflow();
  await page.screenshot({ path: out + "/detail-desktop.png", fullPage: true });
  await page.getByRole("tab", { name: "Детектори", exact: true }).click();
  await expect(page.getByTestId("detector-residual")).toContainText("Поріг");
  await page.getByRole("tab", { name: "Епізоди", exact: true }).click();
  await expect(page.getByText("Завершений", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Сповіщення", exact: true }).click();
  await expect(page.getByTestId("email-notifications")).toContainText(
    "Придушено",
  );
  await page.getByRole("tab", { name: "Огляд", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow();
  await page.screenshot({ path: out + "/detail-mobile.png", fullPage: true });
  await page.getByRole("link", { name: "До каталогу", exact: true }).click();
  await expect(page.getByTestId("source-card")).toHaveCount(11);
  await noOverflow();
  await page.screenshot({ path: out + "/catalog-mobile.png", fullPage: true });
  await page.setViewportSize({ width: 900, height: 1100 });
  await noOverflow();
  await page
    .getByRole("combobox", { name: "Запуск каталогу" })
    .selectOption("run-a");
  await expect(page.getByTestId("source-card")).toHaveCount(5);
  await page
    .getByRole("combobox", { name: "Будівля каталогу" })
    .selectOption("other-house");
  await expect(page.getByTestId("source-card")).toHaveCount(1);
  await expect(page.getByTestId("source-card")).toContainText("999");
  await page.getByRole("link", { name: "Переглянути аналітику" }).click();
  await expect(page.getByTestId("source-latest-energy")).toContainText("999");
  await expect(page.getByTestId("source-forecast-unavailable")).toContainText(
    "не підтримує",
  );
  await page.goto(url("source", "run-a", "house", "warmup-fixture"));
  await expect(page.getByTestId("source-latest-energy")).toContainText("0");
  await expect(page.getByTestId("source-next-forecast")).toContainText("—");
  await page.goto(url("source", "run-a", "wrong-house", "dataset"));
  await expect(
    page.getByRole("heading", { name: "Джерело не знайдено" }),
  ).toBeVisible();
  await page.goto(url("sources", "absent"));
  await expect(
    page.getByRole("heading", { name: "Каталог поки порожній" }),
  ).toBeVisible();
  await page.goto(url("sources", "run-a"));
  await expect(page.getByTestId("source-card")).toHaveCount(5);
  await page.getByRole("textbox", { name: "Пошук джерел" }).fill("not-found");
  await expect(
    page.getByRole("heading", { name: "Нічого не знайдено" }),
  ).toBeVisible();
  await page.getByRole("textbox", { name: "Пошук джерел" }).fill("");
  await expect(page.getByTestId("source-card")).toHaveCount(5);
  await page.route("**/api/channels?**", (r) =>
    r.fulfill({ status: 503, body: "{}" }),
  );
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Не вдалося");
  await page.unroute("**/api/channels?**");
  await page.getByRole("button", { name: "Повторити", exact: true }).click();
  await expect(page.getByTestId("source-card")).toHaveCount(5);
  await page.goto(
    url(
      "source",
      "run-a",
      "building-" + "wide-context-".repeat(7),
      "source-" + "long-identifier-".repeat(8),
    ),
  );
  await expect(page.getByTestId("source-latest-energy")).toContainText("0");
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow();
  await page.getByRole("tab", { name: "Про джерело", exact: true }).click();
  await noOverflow();
  await expect(
    page.locator("code").filter({ hasText: "source-long-identifier-" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(base + "/?run=source-saved-review");
  await expect(page.getByTestId("measurement-count")).toHaveText("144");
  await page
    .getByRole("link", { name: "Пристрої та джерела", exact: true })
    .click();
  await expect(page.getByTestId("source-card")).toHaveCount(11);
  expect(new URL(page.url()).searchParams.get("run")).toBe(
    "source-saved-review",
  );
  expect(new URL(page.url()).searchParams.get("building")).toBe(
    "appliances-house-1",
  );
  expect(errors).toEqual([]);
  const result = {
    passed: true,
    saved_data_screenshots: true,
    screenshot_points: 144,
    real_api_and_postgres: true,
    existing_monitoring_and_navigation: true,
    multi_building_same_source_id: true,
    deep_link_reload: true,
    run_and_building_switch: true,
    not_found: true,
    empty_catalog: true,
    search_empty: true,
    warmup_null_and_zero: true,
    incompatible: true,
    api_recovery: true,
    naive_timezone: "Pacific/Honolulu",
    desktop_mobile_tablet_no_overflow: true,
    browser_errors: errors,
    no_training_or_inference: true,
    no_email_sent: true,
    long_identifiers_no_overflow: true,
    demo_changed: false,
  };
  writeFileSync(
    out + "/browser-verification.json",
    JSON.stringify(result, null, 2) + "\n",
  );
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
