import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { buildInsights } from "../src/insights";
import type { Snapshot } from "../src/types";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const python = process.env.E2E_PYTHON || "python3";
const stateFile = resolve(root, "artifacts/mvp/showcase-last.json");
const state = () =>
  existsSync(stateFile)
    ? JSON.parse(readFileSync(stateFile, "utf8"))
    : { run_id: "" };
const digest = (path: string) =>
  createHash("sha256").update(readFileSync(path)).digest("hex");

test("one command twice: live automatic selection, preserved models and restart", async ({
  page,
  request,
}) => {
  test.skip(process.env.E2E_SHOWCASE !== "1", "Requires prepared Docker stack");
  test.setTimeout(420000);
  const manifest = resolve(
    root,
    process.env.MVP_DOCKER_ARTIFACT_MANIFEST ||
      "artifacts/mvp/docker/manifest.json",
  );
  const metadata = JSON.parse(readFileSync(manifest, "utf8"));
  const paths = [
    manifest,
    ...Object.values(
      metadata.artifacts as Record<string, { path: string }>,
    ).map((entry) => resolve(manifest, "..", entry.path)),
  ];
  const hashes = paths.map(digest);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  let navigations = 0;
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations++;
  });
  const results: object[] = [];
  let priorForecasts: unknown[] = [];
  let priorRun = "";
  for (let repetition = 0; repetition < 2; repetition++) {
    const previous = state().run_id;
    const args =
      repetition === 0
        ? ["-m", "integration.demo", "showcase"]
        : [
            "-m",
            "integration.demo",
            "showcase",
            "--limit",
            "300",
            "--sleep",
            "0.2",
          ];
    const processHandle = spawn(python, args, {
      cwd: root,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let log = "";
    processHandle.stdout.on("data", (data) => {
      log += data.toString();
    });
    processHandle.stderr.on("data", (data) => {
      log += data.toString();
    });
    const finished = new Promise<void>((done, fail) => {
      processHandle.once("error", fail);
      processHandle.once("exit", (code) =>
        code === 0 ? done() : fail(new Error(log.slice(-5000))),
      );
    });
    void finished.catch(() => {});
    try {
      await expect
        .poll(() => state().run_id, { timeout: 60000 })
        .not.toBe(previous);
      const run = state().run_id;
      expect(state().topic).toBe(run);
      expect(state().group_id).toBe(run);
      expect(state().sleep).toBe(repetition === 0 ? 0.5 : 0.2);
      await expect(page.getByLabel("Запуск replay")).toHaveValue(run, {
        timeout: 90000,
      });
      const count = async () =>
        Number(await page.getByTestId("measurement-count").textContent());
      await expect.poll(count, { timeout: 90000 }).toBeGreaterThan(10);
      const intermediate = await count();
      expect(intermediate).toBeLessThan(300);
      await expect(page.getByTestId("visible-count")).not.toHaveText(
        "0 точок у вікні",
      );
      await finished;
      await expect.poll(count, { timeout: 60000 }).toBe(300);
      await expect(page.getByTestId("forecast-count")).toHaveText("600");
      await expect(page.getByTestId("score-count")).toHaveText("900");
      await expect(page.getByTestId("checkpoint-next")).toHaveText("300");
      for (const detector of ["isolation_forest", "autoencoder", "residual"]) {
        await expect(page.getByTestId("detector-" + detector)).toContainText(
          "experimental",
        );
        await expect(page.getByTestId("detector-" + detector)).toContainText(
          "Готово",
        );
      }
      await expect(page.getByTestId("demo-status")).toContainText(
        "Стан відтворення невідомий",
      );
      const query = new URLSearchParams({
        run_id: run,
        building_id: "uci-appliances-house",
        source_id: "uci-appliances-energy",
        time_basis: "dataset_naive",
      });
      // Use exactly the source selected in the real browser, not a test fixture.
      query.set(
        "building_id",
        await page.getByLabel("Будівля", { exact: true }).inputValue(),
      );
      query.set(
        "source_id",
        await page.getByLabel("Джерело", { exact: true }).inputValue(),
      );
      const read = async (path: string, limit: number) =>
        (
          await (
            await request.get(`/api/${path}?${query}&limit=${limit}`)
          ).json()
        ).items;
      const [measurements, primary, scores] = await Promise.all([
        read("measurements", 144),
        read("forecasts", 1000),
        read("anomaly-scores", 432),
      ]);
      const expected = buildInsights({
        measurements,
        forecasts: primary,
        scores,
        basis: "dataset_naive",
      } as Snapshot);
      const panel = page.getByTestId("energy-insights");
      await expect(panel).toContainText(expected.summary[0]);
      await expect(panel).toContainText(expected.summary[1]);
      await expect(panel).toContainText(expected.summary[2]);
      await panel.locator("summary").click();
      await expect(page.getByTestId("forecast-insight")).toHaveText(
        expected.forecast,
      );
      await expect(page.getByTestId("consumption-insight")).toHaveText(
        expected.consumption + " " + expected.trend,
      );
      for (const detector of expected.detectors)
        await expect(page.getByTestId("insight-" + detector.id)).toHaveText(
          detector.text,
        );
      await expect(page.getByTestId("next-forecast")).toContainText(
        expected.next!.forecast_target_timestamp.replace("T", " "),
      );
      await panel.locator("summary").click();
      const combinedPage = await (
        await request.get("/api/combined-decisions?" + query + "&limit=1000")
      ).json();
      expect(combinedPage.items).toHaveLength(300);
      const latestDecision = combinedPage.items.find(
        (d: { measurement_id: string }) =>
          d.measurement_id === measurements[0].measurement_id,
      );
      await expect(page.getByTestId("combined-current")).toContainText(
        `${latestDecision.trigger_count} із 3`,
      );
      expect(latestDecision.rule).toBe("unanimous");
      const beforeDecisions = combinedPage.items;
      const beforeCombinedEvents = await (
        await request.get("/api/combined-events?" + query + "&limit=1000")
      ).json();
      const forecastPage = await (
        await request.get("/api/forecasts?run_id=" + run + "&limit=1000")
      ).json();
      const forecasts = forecastPage.items;
      expect(forecasts).toHaveLength(600);
      expect(
        forecasts.filter(
          (f: { purpose: string }) => f.purpose === "primary_forecast",
        ),
      ).toHaveLength(300);
      execFileSync(python, ["-m", "integration.demo", "restart"], {
        cwd: root,
        env: process.env,
        stdio: "pipe",
        timeout: 60000,
      });
      expect(
        (
          await (
            await request.get(
              "/api/combined-decisions?" + query + "&limit=1000",
            )
          ).json()
        ).items,
      ).toEqual(beforeDecisions);
      expect(
        (
          await (
            await request.get("/api/combined-events?" + query + "&limit=1000")
          ).json()
        ).items,
      ).toEqual(beforeCombinedEvents.items);
      const restored = await (
        await request.get("/api/forecasts?run_id=" + run + "&limit=1000")
      ).json();
      expect(restored.items).toEqual(forecasts);
      if (priorRun) {
        const previous = await (
          await request.get("/api/forecasts?run_id=" + priorRun + "&limit=1000")
        ).json();
        expect(previous.items).toEqual(priorForecasts);
      }
      expect(paths.map(digest)).toEqual(hashes);
      expect(log).toContain("Docker build і підготовку моделей пропущено");
      expect(state().phase).toBe("complete");
      expect(state().results.duplicate_deliveries).toBe(0);
      expect(state().results.rejected_messages).toBe(0);
      results.push({
        run_id: run,
        insights: expected.summary,
        forecast_target: expected.next!.forecast_target_timestamp,
        intermediate,
        measurements: 300,
        forecasts: 600,
        scores: 900,
        duplicates: 0,
        rejected: 0,
        checkpoint: 300,
        immutable_forecasts: forecasts.length,
      });
      priorRun = run;
      priorForecasts = forecasts;
    } finally {
      if (processHandle.exitCode === null) {
        processHandle.kill("SIGINT");
        await finished.catch(() => {});
      }
      if (log) console.log(log);
    }
  }
  expect(navigations).toBe(0);
  expect(errors).toEqual([]);
  const report = {
    runs: results,
    automatic_selection: true,
    page_reloads_during_replays: navigations,
    models_unchanged: true,
    browser_errors: errors,
  };
  mkdirSync(resolve(root, "artifacts/mvp/showcase-verification"), {
    recursive: true,
  });
  writeFileSync(
    resolve(root, "artifacts/mvp/showcase-verification/e2e.json"),
    JSON.stringify(report, null, 2),
  );
  await page.screenshot({
    path: resolve(root, "artifacts/mvp/showcase-verification/dashboard.png"),
    fullPage: true,
  });
  await page.screenshot({
    path: resolve(
      root,
      "artifacts/mvp/showcase-verification/dashboard-top.png",
    ),
  });
  // Compact real-data preview for reviewers unable to download ZIP artifacts.
  // The same public UCI data and UI are retained in the full PNG artifacts.
  await page.evaluate(() => window.scrollTo(0, 0));
  const preview = await page.screenshot({ type: "jpeg", quality: 55 });
  console.log("DASHBOARD_PREVIEW_JPEG_BASE64=" + preview.toString("base64"));
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("energy-insights")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: resolve(
      root,
      "artifacts/mvp/showcase-verification/dashboard-mobile.png",
    ),
    fullPage: true,
  });
  console.log("SHOWCASE_VERIFIED " + JSON.stringify(report));
});
