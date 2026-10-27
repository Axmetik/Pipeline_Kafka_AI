# Graphite Dark Dashboard — implementation and visual review

## Scope

Frontend redesign from `a488faacdd04925c860c3d7ad2d19c0e99b8cfd7`, on `feature/dashboard-graphite-dark`.

Production modules changed:

- `dashboard/src/style.css`: one Graphite Dark theme with centralized color, radius, spacing and shadow tokens; sidebar, header, KPI cards, charts, tables, Insights, Combined Detection, Notifications, models, pipeline, details, error and empty states; focus outlines and responsive layouts.
- `dashboard/src/App.tsx`: Energy Intelligence wordmark, selected run context, section-aware navigation with `aria-current`, shared dark chart tooltips, themed axes/grids/thresholds and distinct detector accents and explicit Wh labels for residual scores/thresholds. Chart data, scales, ordering and formatters are unchanged.

`dashboard/e2e/graphite.spec.ts` adds seven browser checks and captures real Chromium screenshots from synthetic API fixtures. Existing contract tests are unchanged.

No backend, API, database, Kafka, ML, scientific results, notification delivery or polling changes. Existing `data-testid` values and control labels remain. HGB20 remains the primary forecast, RF21 remains the residual reference. Nulls, warm-up, incompatible sources, unknown worker status, forecast origin/target alignment and the 72/144/288-point selector retain their behavior. Naive dataset timestamps are never converted to a browser timezone by this redesign.

## Validation — 2026-10-27

| Check | Result |
| --- | --- |
| Frontend unit tests (`npm test`) | 28 passed, 6 files |
| TypeScript (`npm run typecheck`) | Passed, including new browser spec |
| Production build (`npm run build`) | Passed |
| Existing browser contracts | 2 passed |
| Graphite browser checks | 7 passed |
| Combined Chromium run | 9 passed, 25.5 s |
| Viewports | 1440 default, 1920, 1280, 834, 390 and 320 px |
| Page-wide horizontal overflow | None at tested widths; wide tables scroll inside their wrappers |
| Dark tooltip / forecast dash / section navigation | Passed |
| Empty / unavailable API / reconnect / warm-up / incompatible / source switching / target alignment | Covered by new visual-state checks and existing contracts |
| `git diff --check` | Passed |

The browser config uses `Pacific/Honolulu`; displayed UCI labels remain dataset wall-time. Browser fixture tests ran in the existing isolated `energy-dashboard-e2e:local` Chromium image, without starting Kafka, training, replay or the application stack. Existing Mailpit was left running. At 320 px, navigation uses two columns and KPIs one column. At tablet widths detector cards stack; desktop uses three independent panels.

The build reports a non-blocking JS chunk-size warning (~633 kB minified); no bundling or data-loading behavior was changed in this design task. CI status is recorded on the PR; local fixture checks do not substitute for the separate full-stack CI job.

## Reproduce frontend checks

From `dashboard/`:

```sh
npm ci
npm test
npm run typecheck
npm run build
npx playwright install chromium
npm run e2e -- e2e/contracts.spec.ts e2e/graphite.spec.ts
```

The last command uses mocked API responses in a real browser and writes screenshots under this directory. It does not send email or execute ML inference. Use these explicit specs for this focused review rather than starting a replay.

For an already configured local application, the redesigned UI is delivered by rebuilding its dashboard image through the existing documented Compose/demo flow. This task did not rebuild or restart the user's application services, apply migrations or alter local data.

## Screenshots and interpretation

All images below are **synthetic frontend fixtures, not measured model outputs or new scientific results**. Run identifier `fixture-graphite-review-not-ml-results` makes this explicit. The 144 visible points and historical episodes exist only in intercepted browser responses; no database records or original artifacts were changed. A 300-record pipeline counter intentionally demonstrates that the visible window is distinct from run totals. The disabled email fixture represents a suppressed notification, not a sent message.

- [Full desktop](screenshots/desktop-full.png)
- [KPI cards](screenshots/kpi.png) and [forecast chart](screenshots/forecast-chart.png)
- [Detector panels](screenshots/detectors.png)
- [Intelligent Energy Insights](screenshots/energy-insights.png)
- [Combined Detection](screenshots/combined-panel.png)
- [Email Notifications](screenshots/email-notifications.png)
- [Mobile](screenshots/mobile-full.png)
- [Empty](screenshots/empty.png) and [API unavailable](screenshots/offline.png)

The supplied text describes a separate reference image, but no reference image was attached to this request. Therefore no pixel-by-pixel comparison is claimed. Implementation follows the supplied palette and current section hierarchy, retaining all scientific explanations. No extra pages, Settings, theme toggle, fabricated KPI or normalized common detector scale were added. Secondary text is slightly brighter than the suggested palette where needed for readability.

Merge and Stage 8B remain subject to separate user approval. Stage 6 working copy, Docker volumes, datasets and ML artifacts are untouched.
