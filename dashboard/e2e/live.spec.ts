import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const root = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const python = process.env.E2E_PYTHON || "python3";
const run = process.env.MVP_RUN_ID || "demo-001";
function demo(...args: string[]) {
  return execFileSync(python, ["-m", "integration.demo", ...args], {
    cwd: root,
    env: process.env,
    stdio: "pipe",
    timeout: 120000,
  });
}
function replay(limit: number, sleep: number) {
  const processHandle = spawn(
    python,
    [
      "-m",
      "integration.demo",
      "replay",
      "--limit",
      String(limit),
      "--sleep",
      String(sleep),
    ],
    { cwd: root, env: process.env, stdio: "pipe" },
  );
  let log = "";
  processHandle.stdout.on("data", (b) => {
    log += b.toString();
  });
  processHandle.stderr.on("data", (b) => {
    log += b.toString();
  });
  const finished = new Promise<void>((resolve, reject) => {
    processHandle.on("error", reject);
    processHandle.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(log.slice(-3000))),
    );
  });
  // Register rejection immediately while the browser waits, then await explicitly later.
  void finished.catch(() => {});
  return { finished, processHandle };
}

test("live Kafka replay, worker/dashboard restart, immutable forecasts and duplicate delivery", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_REAL !== "1",
    "Requires complete Docker MVP with trusted local artifacts",
  );
  execFileSync(python, ["-m", "integration.security_check"], {
    cwd: root,
    env: process.env,
    stdio: "pipe",
    timeout: 30000,
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/?run=" + encodeURIComponent(run));
  await expect(page.getByTestId("measurement-count")).toHaveText("0");
  await expect(page.getByTestId("empty-state")).toBeVisible();
  const producer = replay(300, 0.15);
  const count = async () =>
    Number(await page.getByTestId("measurement-count").textContent());
  await expect.poll(count, { timeout: 60000 }).toBeGreaterThan(10);
  const duringReplay = await count();
  expect(duringReplay).toBeLessThan(300);
  await expect(page.getByTestId("visible-count")).not.toHaveText(
    "0 точок у вікні",
  );
  const before = (
    await (
      await request.get(
        "/api/forecasts?run_id=" + encodeURIComponent(run) + "&limit=1000",
      )
    ).json()
  ).items;
  demo("restart");
  await producer.finished;
  await expect.poll(count, { timeout: 120000 }).toBe(300);
  await expect(page.getByTestId("forecast-count")).toHaveText("600");
  await expect(page.getByTestId("score-count")).toHaveText("900");
  await expect(page.getByTestId("checkpoint-next")).toHaveText("300");
  await expect(page.getByTestId("connection-status")).toContainText(
    "API на зв’язку",
  );
  await expect(page.getByTestId("forecast-chart").locator("svg")).toBeVisible();
  for (const d of ["isolation_forest", "autoencoder", "residual"]) {
    await expect(page.getByTestId("detector-" + d)).toContainText(
      "experimental",
    );
    await expect(page.getByTestId("detector-" + d)).toContainText("Готово");
  }
  const allForecasts = (
    await (
      await request.get(
        "/api/forecasts?run_id=" + encodeURIComponent(run) + "&limit=1000",
      )
    ).json()
  ).items;
  const saved = new Map(
    allForecasts.map((f: { forecast_id: string }) => [f.forecast_id, f]),
  );
  for (const f of before) expect(saved.get(f.forecast_id)).toEqual(f);
  expect(
    allForecasts.filter(
      (f: { purpose: string }) => f.purpose === "primary_forecast",
    ),
  ).toHaveLength(300);
  const models = await (
    await request.get("/api/models?run_id=" + encodeURIComponent(run))
  ).json();
  expect(
    models.items.find((m: { role: string }) => m.role === "primary_forecast")
      .feature_names,
  ).toHaveLength(20);
  expect(
    models.items.find((m: { role: string }) => m.role === "residual_reference")
      .feature_names,
  ).toHaveLength(21);
  const events = await (
    await request.get("/api/events?run_id=" + encodeURIComponent(run))
  ).json();
  expect(events.items.length).toBeGreaterThan(0);
  expect(
    events.items.every(
      (e: { maturity: string }) => e.maturity === "experimental",
    ),
  ).toBeTruthy();
  await expect(
    page.getByText("Час датасету, часовий пояс не визначено"),
  ).toBeVisible();
  const second = replay(300, 0);
  await second.finished;
  await expect(page.getByTestId("duplicate-count")).toHaveText("300", {
    timeout: 90000,
  });
  await expect(page.getByTestId("checkpoint-next")).toHaveText("600");
  await expect(page.getByTestId("measurement-count")).toHaveText("300");
  await expect(page.getByTestId("forecast-count")).toHaveText("600");
  expect(
    (
      await (
        await request.get(
          "/api/forecasts?run_id=" + encodeURIComponent(run) + "&limit=1000",
        )
      ).json()
    ).items,
  ).toEqual(allForecasts);
  demo("restart");
  await page.reload();
  await expect(page.getByTestId("measurement-count")).toHaveText("300");
  await expect(page.getByTestId("duplicate-count")).toHaveText("300");
  await expect(page.getByTestId("visible-count")).toHaveText(
    "144 точок у вікні",
  );
  expect(errors).toEqual([]);
  if (process.env.E2E_CAPTURE === "1") {
    const directory = resolve(root, "docs/stage5/screenshots");
    mkdirSync(directory, { recursive: true });
    await page.screenshot({
      path: resolve(directory, "5c-dashboard.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: resolve(directory, "5c-mobile.png"),
      fullPage: true,
    });
    writeFileSync(
      resolve(root, "docs/stage5/5c-e2e.json"),
      JSON.stringify(
        {
          run_id: run,
          during_replay_count: duringReplay,
          measurements: 300,
          forecasts: 600,
          scores: 900,
          duplicate_deliveries: 300,
          next_offset: 600,
          retained_forecasts_verified: before.length,
          events: events.items.length,
          browser_timezone: "Pacific/Honolulu",
          browser_errors: errors,
          worker_and_dashboard_restarts: 2,
        },
        null,
        2,
      ) + "\n",
    );
  }
});
