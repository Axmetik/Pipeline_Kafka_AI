import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 240000,
  expect: { timeout: 20000 },
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1000 },
    timezoneId: "Pacific/Honolulu",
    trace: "retain-on-failure",
  },
  webServer:
    process.env.E2E_REAL === "1"
      ? undefined
      : {
          command: "npm run dev -- --port 5173",
          url: "http://127.0.0.1:5173",
          reuseExistingServer: !process.env.CI,
        },
});
