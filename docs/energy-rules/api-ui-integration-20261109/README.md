# Rules + hybrid: read-only API and Dashboard integration

Implementation and checks: 2026-11-09. Final diff review and documentation: 2026-11-14.
Branch: `feature/energy-rule-detectors`. Base: `9595503c04b9b3c79986acdbc1dc6ea3214f8175`.

## Integrated components

- `GET /api/rule-assessments`: persisted `sustained_high`, `flatline`, `interval_gap` flags, statuses, evidence and configuration versions.
- `GET /api/hybrid-decisions`: persisted experimental `residual OR sustained_high`, nullable decision, coverage and input provenance.
- `GET /api/hybrid-events`: persisted hybrid episodes, contributor union, versions and closing reason.
- Dashboard analytics: current hybrid signal and explanation, availability/coverage, sustained-high context; telemetry-quality indicators separately.
- Dashboard Events: separate hybrid history alongside unchanged ML and Unanimous views. Signal provenance distinguishes residual, sustained_high and both.

API uses the existing read-only PostgreSQL connection. It does not run models or rules, recompute OR/episodes, migrate or backfill data.
Common filters: `run_id`, `building_id`, `source_id`, `start` inclusive, `end` exclusive, `time_basis`, `status`; stable descending cursor pagination, default 100 and maximum 1000 records. Episode time filters apply to episode onset, consistently with existing event endpoints, not overlap.

## Availability and interpretation

- `not_connected`: optional rule tables are absent or only partly installed; HTTP 200 with an empty page and explicit explanation.
- `no_data`: tables exist but no persisted records for the selected source/run and time basis; the channel may be disabled or waiting for data.
- `available`: persisted records exist in that source/run and time basis. Time/status filters can still yield an empty page. This does not prove that the worker is currently enabled or alive.

Missing/null decisions remain unavailable, never false. Historical results are readable even when the worker layer is subsequently disabled. No new heartbeat or enablement registry was introduced.

The existing polling loop fetches bounded optional pages (three assessments per visible measurement, one hybrid decision, at most 50 episodes). The quality table shows the most recent six relevant indicators/unavailable assessments, including current negative assessments; it is not a complete history. Full pages are available through cursor API.
Dataset-naive labels remain unchanged. Flatline includes legitimate repeated/zero consumption; interval gaps are detected only after the next measurement, not by a silence watchdog. All new signals are experimental and are not confirmed faults.

## Completed checks (existing results; no rerun on 2026-11-14)

| Check | Result |
| --- | --- |
| New API tests on isolated real PostgreSQL | 3 passed, no skips |
| Targeted frontend files | 14 tests passed in 4 files |
| TypeScript / production build | Passed (`npm run build` runs `tsc -b` then Vite) |
| Python syntax | 7 changed/new Python files parsed successfully |
| Short isolated Processor → PostgreSQL → FastAPI → production UI smoke | Passed; 440 synthetic measurements |
| Browser errors in smoke | None |

API coverage: missing/partial optional schema, empty installed schema, nullable/false/true flags, evidence and versions, source/run/building/time filtering, pagination and cursor binding, naive/offset-aware timestamps, invalid query limits and preserved Unanimous response.
Frontend coverage: availability versus negative state, provenance, experimental label, telemetry separation, naive labels, bounded source-scoped requests, existing polling cancellation/backoff/selection behavior and forecast alignment.

Commands used for the prior targeted checks:

```sh
# Against a disposable PostgreSQL, with RUN_API_INTEGRATION=1 and MVP_TEST_DATABASE_URL:
python -m unittest discover -s tests -p 'test_rule_api.py' -v
npm --prefix dashboard run test -- --run src/RulePanel.test.tsx src/rule-data.test.ts src/data.test.ts src/useMonitor.test.ts
npm --prefix dashboard run build
# Explicit isolated smoke; requires existing backend/PostgreSQL images and Chrome:
python3 tests/rule_ui_smoke.py
```

The smoke used real Processor transactions, PostgreSQL, read-only FastAPI and a production frontend build, with deterministic model doubles. Three prior synthetic days provide unchanged-rule historical context; two new records are added while the browser is open. Polling shows both contributors, then a gap on the next record and a closed hybrid episode. Browser timezone was Pacific/Honolulu to check naive display semantics. This is functional integration evidence, not a new anomaly-quality experiment or a Kafka transport test.

See [machine-readable smoke result](smoke.json), [analytics screenshot](analytics.png) and [events screenshot](events.png). Screenshots contain synthetic fixture data, not results from a new ML experiment. Temporary test services were removed; no existing demo containers or volumes were modified.

Vite emitted its bundle-size warning (>500 kB); production build succeeded. Full suite, full E2E campaign and new scientific experiments were not run. Prior temporary plain-text test logs are no longer available; counts above are recorded from the successful tool outputs, with `smoke.json` and screenshots retained.

## Final scope and safety review

The committed scope is API/schema contracts, Dashboard loading/display, targeted test fixtures, suite classification and this report/screenshots. Notification request formatting was restored to avoid an unrelated Email diff. No Worker, database migration, detector/model, threshold, Unanimous, low-candidate or Email behavior changes are included. Existing diagnostic directories outside this report remain untouched and excluded from this commit.

The staged diff is checked for whitespace errors and common credential/private-key/token patterns. No `.env`, credential files, model artifacts or datasets are included. The only test DB URL is generated for an isolated PostgreSQL with temporary trust authentication and no host-published database port; the UI facade binds its host port to 127.0.0.1.

No merge, deployment, rebuild of the demo, new replay or training is part of this finalization.
