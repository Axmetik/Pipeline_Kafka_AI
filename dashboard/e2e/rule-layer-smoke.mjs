// One explicit isolated smoke; not part of the full E2E campaign.
import { chromium, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
const base = process.env.RULE_UI_BASE;
if (
  !base?.startsWith("http://127.0.0.1:") ||
  !process.env.RULE_UI_CONTAINER?.startsWith("rule-ui-")
)
  throw Error("Requires isolated harness");
for (let i = 0; i < 30; i++) {
  try {
    if ((await fetch(base + "/health/ready")).ok) break;
  } catch {}
  await new Promise((r) => setTimeout(r, 500));
}
const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
    timezoneId: "Pacific/Honolulu",
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/?run=rule-ui-synthetic-fixture");
  await expect(page.getByTestId("measurement-count")).toHaveText("438");
  await expect(page.getByTestId("hybrid-current")).toContainText(
    "Sustained high",
  );
  await page.getByTestId("rule-panel").scrollIntoViewIfNeeded();
  await page
    .getByTestId("rule-panel")
    .screenshot({ path: process.env.RULE_UI_OUTPUT + "/analytics.png" });
  execFileSync(
    "docker",
    [
      "exec",
      process.env.RULE_UI_CONTAINER,
      "python",
      "tests/rule_ui_fixture.py",
      "advance",
    ],
    { stdio: "pipe" },
  );
  await expect(page.getByTestId("measurement-count")).toHaveText("439");
  await expect(page.getByTestId("hybrid-current")).toContainText(
    "Residual (відхилення від RF21) + Sustained high",
  );
  const response = await (
    await page.request.get(
      base + "/api/hybrid-decisions?run_id=rule-ui-synthetic-fixture&limit=1",
    )
  ).json();
  expect(response.items[0].triggered_inputs).toEqual([
    "residual",
    "sustained_high",
  ]);
  await page
    .getByTestId("rule-panel")
    .screenshot({ path: process.env.RULE_UI_OUTPUT + "/analytics.png" });
  execFileSync(
    "docker",
    [
      "exec",
      process.env.RULE_UI_CONTAINER,
      "python",
      "tests/rule_ui_fixture.py",
      "gap",
    ],
    { stdio: "pipe" },
  );
  await expect(page.getByTestId("measurement-count")).toHaveText("440");
  await expect(page.getByTestId("rule-panel")).toContainText(
    "Пропущені інтервали: 1",
  );
  await expect(page.getByTestId("hybrid-events")).toContainText("closed");
  await expect(page.getByTestId("hybrid-events")).toContainText(
    "Residual (відхилення від RF21) + Sustained high",
  );
  await page.getByTestId("hybrid-events").scrollIntoViewIfNeeded();
  await page
    .getByTestId("hybrid-events")
    .screenshot({ path: process.env.RULE_UI_OUTPUT + "/events.png" });
  expect(errors).toEqual([]);
  const summary = {
    passed: true,
    fixture:
      "synthetic; deterministic model doubles; no experimental quality estimates",
    measurements: 440,
    live_polling: true,
    hybrid_both_origins: true,
    gap_on_next_record: true,
    closed_episode: true,
    api: "real read-only FastAPI + isolated PostgreSQL",
    host_binding: "127.0.0.1 only",
    production_ui: true,
    browser_timezone: "Pacific/Honolulu",
    page_errors: errors,
    existing_demo_modified: false,
  };
  writeFileSync(
    process.env.RULE_UI_OUTPUT + "/smoke.json",
    JSON.stringify(summary, null, 2) + "\n",
  );
  console.log(JSON.stringify(summary));
} finally {
  await browser.close();
}
