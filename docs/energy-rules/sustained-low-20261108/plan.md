# Sustained-low v1 — preregistered formula and controlled experiment

Registered before implementation/scoring. Exact frozen specification: plan.json; all32 scenarios: scenarios.json.

## Formula fixed before implementation

For eligible previous-date observations in the same labelled hour over7 dates, require18 points across3 dates. Let m be median Wh, d median absolute deviation. L = m - max(3*1.4826*d,10Wh,0.5*m). Require m>=20Wh and L>0. If reference below20Wh return null/low_reference_energy; if L<=0 return null/no_positive_lower_threshold. Otherwise low iff energy<L; confirm after6 consecutive low intervals. Missing context is null with reason. This avoids claiming lower-than-zero consumption is detectable. No calendar model.

Freeze24 separate hourly references before candidate onset; switch to each hour own frozen reference across hours/midnight. No current date/future self-reference; gap ends candidate. Per-source state and exact last-message retry idempotence; no persistent ledger integration. New module/config/version, frozen V2 untouched.

## Fixed cases and comparison

Known-six old drop cases are fresh-scored regression checks, separate from18 new consumption targets:12 drops (factors0.2/0.6, durations3/6/12 at May12 07:50 /May13 22:50),2 highs,2 short peaks,2 ramps. Six controls: raw, constant0/5Wh background, normal daily night decline200→20Wh, regular working-week200/off-hours+weekend20Wh, benign zero window. Profiles apply to history as well; environmental fields remain raw. One flatline and one gap are separate telemetry checks. All cases have7 calendar-date context and144 tail intervals.

Compare residual, high, low, residual|high and residual|high|low. True if any available positive, false only when all required negative/available, otherwise null; preserve sources/missing inputs. Episodes rebuilt independently: onset within inclusive first/last event labels, no earlier overlap or tail credit. New/known cohorts separate. Preserve all misses/nulls; report incremental/lost matches, component intersections, paired episode counts, coverage and detected-event delay. No parameter adjustment from results.

## Timing registered before execution

Five paired repeats on the identical144-record raw stream from May12 08:00. Deterministic alternating baseline/plus-low order. Monotonic perf_counter_ns for record p50/p95 and whole loop totals. Two scopes: rules-only with identical precomputed causal residual flags, and full StreamDetector (existing3 scorers/RF) + V2. Exact same pipeline decisions, plus just new low rule in treatment. Load/IO/clone/warmup outside timers. Prime causal histories on7 prior dates, restore equivalent snapshots outside each timer. Report each repeat, local environment, limits/threads and model hashes; do not confuse50min evidence wait with compute milliseconds. This is a short offline cost measurement, not the stopped Stage6 campaign.

## Preserved evidence

New32-case output directory only, raw per-point paired Parquet, episodes, metrics, component table, timing raw CSV/summary/environment, preselected plots and provenance. Compare original known-six scores only after fresh inference as a preservation check, never as substitution. Require exact batch/stream low parity, source/config checksums, regression tests and no changes to V2/ML/Unanimous or old scientific results. No new dataset, training, services, runtime integration or merge.
