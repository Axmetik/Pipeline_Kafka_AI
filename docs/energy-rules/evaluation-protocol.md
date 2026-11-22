# Offline comparison protocol — proposed execution contract v1

Registered in Git before any new evaluation, 2026-11-08. **Not executed; new experiments, acquisition/adapters/model preparation and integration require separate approval.** This protocol fixes comparison, partition, calibration, matching and reporting rules; it does not authorize a large campaign or change previous results.

## 1. Questions and independent arms

1. Can simple review rules identify labelled temporal patterns at an acceptable signal burden?
2. How do they compare with individual IF, AE and forecast-residual detectors on the **same assessable observations/events**?
3. What does the existing Unanimous rule suppress or miss? Never infer benefit merely from fewer signals.

Publish rows independently for `flatline` (telemetry_quality), `sustained_high` (consumption_pattern), IF, AE, residual, and **unchanged Unanimous (all three original ML flags)**. `interval_gap` is a separate returned-gap evaluation, not part of a consumption-alarm OR. No automatic OR of rules and ML, no replacement of Unanimous, no probabilities or physical-fault severity.

- **Historical UCI arm:** original Stage4/7B scores, configurations and labels remain frozen. The previously viewed test and familiar injections are historical/exploratory comparisons only, never an independent unseen holdout. Any future rule outputs go in a new directory/version; old metrics are not recalculated in place. Live Docker artifacts have distinct identity and cannot inherit exact original benchmark numbers.
- **New labelled arm:** LEAD public labelled subset, at native **one-hour** cadence, conditional on documented rights, labels and a separately approved native-hourly rule/feature version. Current600s module intentionally rejects it. Public competition test without reference labels is not a local F1 holdout.
- **New company arm:** source-native/manual-issue telemetry-quality evaluation first;600s interval-consumption arm only after the adapter/causality checks in [compatibility assessment](dataset-compatibility.md). Manual positive issues do not imply exhaustive negative labels. Automatic issues are a separate agreement/sensitivity track, not independent truth for rule detectors.

No UCI model is applied to a new building. New weights/calibration/source binding and any native-cadence features must first be prepared under a separately approved protocol. This document neither trains them nor asserts that all comparison arms are currently runnable. Until that gate passes, publish **not prepared**, not missing results disguised as zero performance.

## 2. Data manifests and eligibility before model fitting

Freeze acquisition/license/version/checksum and source/meter/label mapping first. Raw files remain read-only. Separate raw, harmonized, corrected and derived versions; record the input lineage for every metric row. No label-based selection of easy meters or test periods.

Initial evaluation cap: at most20 eligible source identities per dataset, chosen by ascending SHA256 of `20261108|dataset_version|building_id|source_id`. Stop and document if fewer are eligible; do not replace a source because test performance is poor. Eligibility requires known units/cadence, usable reference labels for the target metric, at least90 calendar days and ≥90% valid observed coverage in the **training period only**. If a task has only sparse manual positives, retain it for positive-event recall/signal burden with precision explicitly unavailable.

Related meters must not be treated as independent buildings. Bootstrap/report grouping follows building or facility, not individual data points.

For each source, create an expected native-cadence grid over `[first_label, last_label + cadence)`, preserving the declared clock. For offset-aware data use absolute instants for cadence continuity and an explicitly configured source zone for contextual hour; for naive labels preserve naive time. DST and interval-start/end mapping are adapter gates. Do not guess UTC, manufacture10-minute points from hourly/15-minute data, or use the future to fill missing values.

## 3. Chronological partitions (no random row split)

For each accepted source, let N be the expected-grid length (including missing positions):

| Partition | Grid indices | Purpose |
|---|---|---|
| Train | `[0, floor(.50N))` | Fit preprocessing, feature scales and ML weights only |
| Calibration | `[floor(.50N), floor(.65N))` | Freeze score thresholds / rule amplitude calibration |
| Validation | `[floor(.65N), floor(.80N))` | Choose from the finite candidate set using the preregistered criterion |
| Test | `[floor(.80N), N)` | One final evaluation after selection; no tuning |

Freeze timestamp boundaries/source membership before fitting. Do not move boundaries to obtain better label balance. Events crossing a boundary are tagged boundary-censored, counted and excluded from the primary fully-contained-event table; report them separately. Do not silently drop them from the manifest or change boundaries.

Primary claim: chronological transfer within the assessed sources. A separate unseen-building arm is permitted only in a later approved execution plan: partition whole building/facility IDs before fitting, keep their weights/scalers/threshold fitting disjoint, and disclose any unlabeled prior context used to initialize an otherwise unseen source. A company submeter split cannot substantiate an unseen-building claim. No secondary arm is silently pooled into the primary result.

The same causal `process` primitive must generate offline and incremental results. At time t, context may use earlier measurements (including earlier validation/test observations), never current/future values or validation/test labels. Updating past-only online context is distinct from refitting weights/thresholds. At each partition boundary preserve past-only history; do not reset merely to improve results. At source start/gaps record genuine warm-up.

## 4. Calibration and finite selection

Keep a fixed-default rules baseline as a separately named row. Defaults are engineering values, not already validated settings. Do not tune native-hourly settings by pretending six hourly records represent one hour: preregister durations in seconds and their exact cadence conversion in the adapter-specific manifest before execution.

Future calibrated rules candidates:

- Flatline duration:30/60/120 minutes, but only exactly representable durations with at least two observations at the native cadence are eligible; nonrepresentable candidates are marked inapplicable, never rounded secretly. Tolerance: exact0, plus documented meter resolution **only if verified using documentation/train data** (at most6 combinations). Never infer resolution from test peaks.
- Sustained-high duration:30/60/120 minutes (same native-cadence/two-observation rule, so an hourly arm can use120min, not a silently rounded30/60min duration); MAD multiplier2/3/4; relative margin fixed0.5. Absolute margin per source is `max(0, q99(energy − causal same-hour median))` on eligible calibration reference points, with no future input (at most9 combinations). Insufficient normal/known calibration coverage makes a calibrated source ineligible; no test fallback.
- Freeze history/minimum-coverage policy, hourly-profile cutoff, threshold strictness and labels before calibration. Retain the default non-calibrated margin row separately. Derived margins/configurations get their own hashes; do not overwrite original defaults.
- IF/AE/residual: training preprocessing only; thresholds are the99th percentile of their eligible calibration scores.98th/99.5th are preregistered sensitivity rows, not substitutes selected after seeing test. Existing original weights/thresholds are unchanged; new-dataset models require separate preparation as above.
- Unanimous: retain the rule requiring3/3 available original ML flags. No new voting/threshold search, and no addition of rule signals to its inputs.

For fully labelled validation data, select **within each configurable method** by highest macro event F1 among candidates with normal-reference flagged-point fraction ≤1%; ties: lower alarm-episode rate, then shorter median detected-event delay (undefined ranks last), then lexicographic config ID. If none meets the budget, record **no eligible configuration**, not a successful fallback. On partially labelled company data, do not tune precision/F1 using presumed negatives: keep fixed defaults and report recall/burden only, or stop that selection arm.

No test results, old UCI test plots or held-out labels select new parameters. Do not refit ML weights after validation, and do not rerun alternative settings on test to choose the winner. Missing classes/zero positive events are reported; the selection cannot manufacture positive evidence.

## 5. Common observations, coverage and missingness

For each method publish all nullable outputs and its own availability (`flag is not null`), warm-up duration/points and reasons for exclusions. `observing` with a defined false flag is assessable; null context is not a negative prediction.

The primary comparison uses identical **received, valid and fully labelled points** on which all compared applicable methods are available; Unanimous needs all3ML inputs. Exclude gap events from this common consumption table. Per-method full-coverage tables are secondary and clearly use different denominators. If common support is empty, report unavailable rather than a zero score.

Report both:

- model availability / valid received points;
- availability / all expected-grid positions, with missing, invalid, unlabelled and warm-up counts separately.

A positive event fully covered by the common set is eligible for conditional event metrics. Partially covered events, zero-covered events and boundary-censored events are listed explicitly, not silently discarded. Also show end-to-end recall across all fully reference-labelled non-boundary events, with nondetections due to missing/context coverage counted as misses and identified separately. This prevents common-support filtering from hiding difficult events.

Never fill a gap with normal zeros or carry predictions/flags across an unknown interval. Retain imputation/provenance masks. For company change-of-value raw channels, a regular expected grid is not assumed until the acquisition contract establishes it; otherwise returned-gap recall is not applicable.

## 6. Event and alarm matching (new protocol, not an edit to Stage4)

Reference events: maximal contiguous positive-label runs for the same source and label/task type. A missing/unlabelled position breaks a run; preserve the original issue ID across fragments where available and report fragmentation. Native issue YAML intervals require a preregistered channel/label-to-interval mapping. Do not choose that mapping by detector results.

Alarm episodes: maximal consecutive `flag=true` observations at native cadence per source/method. False, null or a cadence break closes the episode; do not bridge gaps. Episode start is the **first actual true output**, not the earlier beginning of a duration candidate or a retrospectively backdated label.

Detection window is the inclusive reference `[start,end]`, with **no post-event grace window**. An alarm episode can count only if its onset lies within that event/window. An episode already open before the injection/event is **not** a new detection, even when it overlaps the event. This deliberately differs from the archived Stage4 overlap matcher.

Match alarms chronologically to the earliest unmatched eligible event on the same source/task containing that onset. One alarm can match at most one event and one event at most one alarm. Other alarms remain unmatched (including redundant episodes in an already detected event); report redundant vs background unmatched separately. Split/tie behavior is deterministic by `(timestamp, source_id, event_id)`.

Do not use post-event tails as event true positives. For synthetic paired controls, separately count new rule/ML signals during the injection and after it; the altered history continues to affect downstream context/forecasts. Run all methods on the same injected scenario manifest and unchanged paired control, without changing original measurements. A matched signal also present in the paired unchanged stream is reported as a non-incremental coincidence, not proof of injection sensitivity. Preserve primary and paired-diagnostic tables separately.

## 7. Metrics and denominators

For each dataset/source/task/method/configuration on eligible fully labelled support:

- Event precision = matched alarms / all alarm episodes. Unmatched episodes are event-level errors, split into redundant and outside-positive episodes; these are not the same as point false-positive labels.
- Event recall = detected reference events / eligible reference events. F1 is harmonic precision/recall. With positive events but no alarms, precision/recall/F1 are0 by declared convention. With no positive events, recall/F1 are unavailable; no-alarm/no-event precision is unavailable.
- Signal burden = episode onsets per effective **source-day** of eligible observation, where effective days = summed eligible interval seconds /86,400. Also report flagged points/day and calendar-span rate with explicit denominators. Do not call a count of flagged points a count of events.
- Coverage as above, plus counts of events missed for coverage vs eligible-but-undetected.
- Detection delay = alarm-onset timestamp minus reference onset, in dataset/event-time minutes for **matched events only**, with median/p95/min/max and all values. Missed events have null delay, not zero. Report cadence quantization; this is not wall-clock system latency.
- Where exhaustive negatives exist, include point false-alarm fraction as a supplementary metric and distinguish it from unmatched alarm episodes. Where labels are incomplete, report unmatched/unlabelled alarms as such; precision/F1/FPR are unavailable, not confirmed false positives.

Publish per-source results and macro averages over eligible sources, plus separately labelled micro pooled counts. Report denominator/source counts, exclusions and undefined values. A one-facility dataset does not supply independent-building confidence intervals. Any later bootstrap is building/facility-level with its seed, not a misleading sample of millions of correlated points.

## 8. Separate returned-gap task

Reference gaps come from known missing grid positions or manually supported acquisition outages, not from an assumed fixed rate on change-of-value channels. Define gap onset as the first expected missing timestamp. Match a returned-gap signal to its uniquely preceding gap when the next record arrives; only one match per gap. Delay = next received measurement label minus first missing label. Nonintegral cadence anomalies are a separate class with missing-count unknown.

Leading missing data without a known prior record, trailing silence without a return record and outages spanning dataset boundaries are **unobservable/right-censored** for this module; report counts/duration separately. Do not claim watchdog detection or silently give the module credit for such cases. Precision/recall for this task use only labelled observable returned gaps, with its own coverage and episode definitions, never the energy-anomaly denominator.

## 9. Reproducibility and execution gate

Future result directory (new, never Stage4/7B overwrite) must contain:

- protocol commit/hash, dataset/label/source/split manifests, acquisition and transformation provenance;
- seed20261108, code/environment versions, algorithm/config/model/feature/threshold IDs and checksums;
- chronological per-point outputs (including nulls), event/alarm lists and one-to-one match records;
- `metrics_by_source.csv`, `metrics_macro_micro.csv`, `coverage.csv`, `returned_gaps.csv`, missed/censored events and paired diagnostic tables;
- plots of hourly reference vs actual, raw/modified trajectories, flags/thresholds, signal burden and event delay with missed-event counts;
- a Markdown report separating historical/exploratory UCI, new labelled evaluation, partial-label agreement and controlled unit tests.

Before execution, approve the exact artifacts/native-cadence adapters, rule candidate/config manifest and newly prepared model protocol; confirm labels/rights/time semantics gates; commit protocol and freeze test access. No experiment, model fit, automatic threshold change, runtime integration, download or broad campaign was performed in preparing this document.
