# Experimental energy rules — standalone module, phase 1

Date: 2026-11-08. Base: `e285efd926c5f9682243a4f571b35ee141c5af15` (`origin/main`). Branch: `feature/energy-rule-detectors`.

User-approved scope: **standalone rules and controlled unit tests first**. No worker, Kafka, DB, API, Dashboard or Email integration. PR12 (product Dashboard) remains separate and unmerged; this branch is based on main and does not include its changes.

## Purpose and honest interpretation

Add simple, interpretable review signals alongside the existing research detectors in a future integration. Existing ML models, thresholds, combined Unanimous configuration, datasets and Stage2–8B results are unchanged. This implementation is not a new anomaly benchmark and does not establish an improvement in precision/recall/F1.

`processing/energy_rules.py` implements the existing energy-message-v1 input contract, normalizes kWh to Wh using the existing validator, and accepts **600-second interval energy** only. It requires no model or new dependencies, performs no I/O and does not read the wall clock. `EnergyRules.process(message)` is the streaming primitive; `evaluate(records, config)` uses exactly that primitive for batch evaluation.

## Rules and initial defaults

| Rule | Meaning | Default / trigger |
|---|---|---|
| `flatline` | Repeated energy readings; a data-quality review candidate, not proof of a stuck device | Last 6 consecutive intervals; min–max of that window ≤0 Wh (exact equality). Tolerance configurable. A gap clears the window |
| `interval_gap` | Discontinuity between received source measurement timestamps | After the first point, elapsed time differs from 600 seconds. Exact aligned gaps report missing intervals; fractional/short intervals report irregular cadence without inventing a missing count |
| `sustained_high` | Sustained consumption above historical same-hour context | At least 6 consecutive intervals strictly above the contextual threshold. Requires ≥18 eligible observations across ≥3 previous labelled dates in the last 7 calendar days, all in the same labelled hour |

These are **unvalidated engineering defaults**, not parameters selected for high accuracy. They need a separately approved calibration/evaluation protocol before any operational claim. Algorithm v2 and a SHA256 of the configuration identify `rule_version`; settings are immutable within an engine. Version v1 remains identifiable in Git and is not retroactively rewritten into experimental artifacts.

High threshold:

```text
median(previous-date same-hour Wh)
  + max(3 × 1.4826 × MAD, 50 Wh, 0.5 × median)
```

The current point, current-day points and future points are excluded from the contextual reference. Cadence-violating samples do not inflate reference coverage. When the first above-threshold point appears, freeze a separate reference for each of the 24 source-labelled hours using only the pre-candidate history. At an hour transition, use that hour’s frozen reference, never the previous hour’s threshold. Missing context returns `flag=null` and resets the candidate. End the candidate on a normal observation or cadence break. This avoids immediate threshold adaptation during that candidate. A single peak does not meet the duration requirement. No occupancy/work schedule or universal "night = anomalous" assumption is made.

A robust reference is not guaranteed to be normal: historical contamination, seasonality, legitimate changes in usage and limited coverage remain concerns. A long valid increase can remain flagged against a frozen reference; that is a review signal, not an instruction to reset a device or declare a fault.

## Time, readiness and scope

- UCI naive labels remain naive; no fabricated UTC or browser conversion. Offset-aware timestamps retain explicit offsets. Context uses the hour/date of the source label, not server local time. No assumed DST or occupancy schedule.
- Six energy intervals represent 3,600 seconds of interval energy; their measurement-label span is 3,000 seconds. Both are explicit in flatline evidence. Timestamp reference semantics (`dataset_label`/start/end) are preserved.
- Flatline counts observed consecutive intervals, not elapsed wall-clock downtime. Zero or quantized normal consumption can also trigger it and must not be presented as a confirmed stuck meter.
- The gap rule detects a gap **when the next record arrives**. It cannot detect a completely silent meter or infer replay completion. A wall-clock missing-data watchdog requires a later design that distinguishes live meters from historical replay.
- First gap assessment / insufficient plateau history / unavailable contextual reference use `flag=null`, `status=warmup`. A high candidate awaiting duration uses `observing`, `flag=false`; a completed condition is `ready`, `flag=true`.
- Each output is `experimental`, `review_signal_not_confirmed_fault`; no score is represented as a probability. There is no fabricated fault severity or automatic Email.
- State is independent per building/source, with at most `(context_days + 1) × 144` context-history entries, a `plateau_intervals`-entry flatline window and 24 frozen hourly summaries per source (context_days capped at31); the caller owns source lifecycle. Bounded history does not create durable recovery.
- Exact retries of the last message return a defensive copy without advancing state. Conflicting retries, duplicate timestamp/out-of-order input and source-semantic changes fail explicitly before changing state. Older duplicate deliveries require the worker's durable ledger; this in-memory primitive does not replace that ledger or verify global event-ID uniqueness.
- There is no automatic recovery/backfill, persisted rule episode, database write or change to Kafka offsets. A later integration must restore both context and frozen candidate state and preserve idempotency.

## Review corrections (2026-11-08)

- `flatline` evaluates the last complete duration window, rather than discarding a valid suffix when an old extreme expires. With duration6/tolerance1, `0,1,2,2,2,2,2` is false at point6 and true at point7 (last window `1,2,2,2,2,2`). `consecutive_intervals` now counts observations in the bounded inspected window, capped at the configured duration; it is not lifetime episode length. Whole-window range still rejects transitive drift.
- `sustained_high` freezes all hour-specific contextual summaries at candidate onset. A07:50 candidate cannot apply its07h threshold to08h normal load. An08h threshold unavailable at the frozen cutoff produces null, not a borrowed threshold or normal result. Frozen-cutoff evidence remains explicit across hours and midnight; duration can continue only when each observation exceeds its own hour's available threshold.
- Categories remain `telemetry_quality` (flatline/gap) and `consumption_pattern` (sustained high). No watchdog, ML-score, model or runtime integration was added.
- Seven new regressions include the requested transitions/window case, missing08h context, sustained excess against different hourly thresholds, midnight contamination protection and a direct sliding-window oracle.

[Offline evaluation protocol](evaluation-protocol.md) and [dataset compatibility assessment](dataset-compatibility.md) are plans/preflight findings only, not executed experiments.

## Controlled checks (not measured detection quality)

| Constructed example | Expected result |
|---|---|
| Six equal readings | Flatline review signal at the sixth observation; earlier warm-up results unchanged |
| Gradual neighbor changes whose total range exceeds tolerance | Not a flatline; no transitive-tolerance drift |
| Zero consumption | May be a flatline candidate; explanation explicitly allows normal zero load |
| Two absent 10-minute positions | Two missing intervals reported at the next received measurement |
| Irregular 5/15/25-minute spacing | Cadence review signal, missing-count unknown |
| One high point then normal | No sustained-high signal |
| Six 200Wh intervals after a synthetic prior-day reference of100Wh | Sustained-high at sixth point; threshold150Wh fixed through the candidate (test uses explicitly relaxed context minimum only to shorten the fixture) |
| Normal high hour following a lower-load hour | Compared to its own previous-date same-hour reference |
| Insufficient previous dates / another source / expired context | Contextual result unknown, never silently false |
| Future suffix edited | Previously returned prefix results unchanged |

All fixtures are generated in memory by tests; no UCI/model files or experiment artifacts are loaded. No comparison to the original IF/AE/residual F1 is claimed. Batch/stream equality, input non-mutation, retry isolation, naive/aware labels, Wh conversion, invalid configuration and non-finite thresholds are tested.

## Verification performed

- New rule tests, including review regressions: **41 passed**.
- Existing energy schema tests: **4 passed**.
- Existing feature tests: **5 passed**.
- Total targeted/regression checks: **50 passed**. AST syntax validation passed for module/tests; `git diff --check` passed.
- No Kafka/Docker/browser E2E, training or real-dataset performance experiment was run for this phase. No current Dashboard claim or new scientific metrics are derived from unit-test success.

To repeat only these approved checks from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_energy_rules.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_energy_schema.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_energy_features.py' -v
```

The existing CI unit discovery (`tests/run_suite.py --suite unit`) automatically includes `test_energy_rules.py`; no CI selection or skip mechanism was changed. CI is not claimed successful until a run for the exact pushed commit has been checked.

## API for a later caller (example only)

```python
from processing.energy_rules import EnergyRules, RuleConfig

rules = EnergyRules(RuleConfig())
metadata = rules.metadata()  # store config/version with a future evaluation
assessment = rules.process(wire_message)  # existing validated wire contract
for item in assessment["signals"]:
    if item["flag"] is True:
        # A candidate for human review; not a confirmed fault.
        pass
```

## Next step — needs separate agreement

1. Review initial definitions/defaults and calibrate on designated training/calibration data with trustworthy labels; freeze the protocol before evaluating new holdout buildings/periods. Keep old Stage4/7B results intact.
2. Evaluate flatline separately as telemetry quality and sustained-high as behavior; preserve legitimate zero load, normal peaks and shift-work controls. Report event recall/precision/F1, review signals/day and event-time detection delay, including missed events. Synthetic examples remain separate from real labels.
3. If approved, design additive rule assessment/event tables, explicit version/config binding, state recovery and idempotent writes in the existing DB transaction. Do not reuse ML score scales or modify Unanimous.
4. Add read-only API and a separate rule-signals Dashboard section, with warm-up/unknown/experimental labels and no default Email policy. Verify crash/restart and offline/streaming parity before enabling it for a new run. Never silently backfill or change previously committed forecasts/scores.

## Completed controlled comparison (2026-11-08)

The separately preregistered 24-case comparison is complete: [report, tables, manifest and plots](controlled-20261108/README.md). All scores were recomputed on each modified stream and its untouched pair using existing compatible artifacts. Rules v2, model weights, thresholds and Unanimous remain unchanged. This synthetic historical comparison does not establish real fault-detection accuracy or authorize runtime integration.

## ML–rules complementarity (2026-11-08)

A new separately preregistered 33-case controlled comparison is complete: [contribution table, coverage, paired alarms, plots and limitations](complementarity-20261108/README.md). Consumption and telemetry-quality targets remain separate; every OR episode was reconstructed from fresh nullable decisions. Previous24-case results and frozen configurations remain unchanged. No runtime integration or merge.
