# Product P0 — baseline and impact assessment

Date: 2026-11-01. Baseline main `e285efd926c5f9682243a4f571b35ee141c5af15`, clean worktree before branch `feature/product-dashboard-p1`.

## Verified baseline

- Stage8A scientific/architecture review and Stage8B actual demonstration are frozen evidence: `docs/stage8a/` and `docs/stage8b/`. Historical300→600forecast rows→900scores, model-bound source, low anomaly quality and trusted-vs-benchmark model identity differences remain valid constraints, not targets for improvement in P1.
- Existing Graphite theme and React19/TypeScript/Recharts/Lucide/Vite are sufficient. No new dependency or routing framework is needed.
- `App.tsx` currently contains ~950 lines of layout, chart rendering, filters, selection and detail state. `data.ts`, `useMonitor.ts`, `insights.ts`, `combined.ts`, `InsightsPanel`, `CombinedPanel`, `NotificationsPanel` already provide reusable domain behavior.
- API remains read-only. Snapshot queries scope run/building/source; pipeline counts are **run-wide**, not selected-building totals. `/api/sources?run_id=…` excludes sources without measurements in that run. Global `/api/sources` can list registered sources for a portfolio. Source metadata exists; human building names, addresses, floor area, tariffs and confirmed-fault severity do not.
- Current E2E assumes one long visible page. Existing assertions must navigate to the relevant page and open advanced details while retaining their scientific/data assertions and test IDs. Frozen screenshots must not be overwritten by test output.

## P1 component and data plan

1. Lightweight hash navigation: Overview / Buildings / Analytics / Events. Shared shell, source filters and one existing `useMonitor` instance preserve selection and polling between pages. Preserve `?run&building&source` links; handle browser history and legacy `#detectors`/`#models` deep links.
2. Extract presentational `ForecastChart`, `ScoreChart`, measurement/timestamp table, pipeline status, model registry, KPI cards and source filters from App. Pages compose these; App owns routing and shared state only. Keep `align`, `nextPrimary`, time formatting, score scales, thresholds and null handling unchanged.
3. Overview: selected building/source context, actual interval energy and next forecast, explicit run-wide measurement count, loaded event summary, chart, existing Insights, valid target-aligned comparison table and analytics/event links. No confidence, savings or fault-risk KPI.
4. Buildings: bounded global source catalogue using the existing endpoint, cancellation/retry and honest loading/error/partial-catalogue states. Group by building ID, display metadata actually returned by API. Mark source presence in the selected run; disable opening a source absent from that run rather than silently showing another building. Compatibility only comes from actual selected-source measurement status, never from `energy.scope` or another source's model readiness. Registered buildings with no data show an explicit empty state; absent building registry cannot be fabricated.
5. Analytics: existing consumption/forecast chart, Insights and timestamp comparison; advanced disclosure holds per-detector independent scales/experimental labels, combined evaluation, model versions/thresholds and pipeline diagnostics. No change to inference/API.
6. Events: available individual/combined episodes and email delivery history, read-only source/time/status/detail views. Distinguish dataset event time from UTC notification creation; do not globally sort these incomparable clocks. Open statistical episodes are review candidates, not verified faults or invented severity. No acknowledge/edit controls without a persistence contract.
7. Preview P1 on a separate localhost Vite port using an optional dev proxy target to the existing nginx/API. Keep the verified8088 Dashboard, worker, DB and Mailpit running; no rebuild/replay/training required for frontend review.

## Compatibility and safety gates

- No edits to backend, API contracts, Kafka/recovery/checkpoint, models, thresholds, dataset, existing experiments or Stage6 checkout. Preserve all existing volumes/artifacts and compare protected file hashes with Stage8B before/after.
- Retain IDs/accessible control names where the controls are reused; visibility changes are intentional navigation changes. Versioned historical screenshot/evidence files remain unchanged.
- Keep dataset-naive timestamps literal, Wh/600s units, HGB20 primary vs RF21 residual, null/warm-up/incompatible states and unknown worker liveness. Current model binding is not generalized by the portfolio UI.
- Portfolio pagination must disclose any bounded catalogue truncation. Local page controls are presentation only; run-wide counters and last50/20 histories must retain their scopes.

## Validation plan

- Preserve current28 unit tests; add product component/selection/portfolio/summary/navigation tests including empty, unsupported metadata, null and incompatible states.
- TypeScript, production build; existing browser contracts and Graphite layout checks adapted to navigation without weakening calculations/data assertions.
- New browser coverage for four pages, URL/back/forward, building/source selection, advanced disclosure, event detail/status and unavailable API. Verify the new frontend against actual read-only API and capture four real-data screenshots; fixtures remain test-only.
- Existing full live/recovery E2E assertions get navigation-only updates; no manual replay/training campaign on user data. Automatic CI remains the existing safety net; no checks bypass.
- Deliver report, changed files/commits, results/limitations and P2 tariff/cost plan only. No P2 implementation, public deployment or merge without separate approval.

This assessment is committed **before** major frontend refactoring. P1 is authorized by the accompanying task; no extra architecture approval gate is inferred.
