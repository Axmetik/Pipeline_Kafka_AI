# Sustained-low: preregistered controlled experiment

All32 cases retained. New18 consumption events and known-six regression drops are separate. No fitting/calibration/parameter selection. Same historical house/previously viewed period, synthetic labels, not real fault validation.

| Cohort | Method | Detected / target | Event coverage | Stream availability | Median delay,min | Paired episodes: full / event | New paired crossings |
|---|---|---:|---:|---:|---:|---:|---:|
| known_regression | residual | 0/6 | 100.0% | 88.5% | — | 33 / 2 | 0 |
| known_regression | residual_high_low_or | 0/6 | 50.0% | 50.3% | — | 33 / 2 | 0 |
| known_regression | residual_high_or | 0/6 | 100.0% | 65.5% | — | 33 / 2 | 0 |
| known_regression | sustained_high | 0/6 | 100.0% | 65.4% | — | 0 / 0 | 0 |
| known_regression | sustained_low | 0/6 | 50.0% | 50.1% | — | 0 / 0 | 0 |
| new | residual | 2/18 | 100.0% | 88.5% | 0 | 162 / 0 | 2 |
| new | residual_high_low_or | 8/18 | 60.2% | 52.6% | 50 | 204 / 0 | 5 |
| new | residual_high_or | 6/18 | 100.0% | 65.6% | 50 | 204 / 0 | 6 |
| new | sustained_high | 4/18 | 100.0% | 65.4% | 60 | 51 / 0 | 4 |
| new | sustained_low | 2/18 | 50.0% | 51.7% | 50 | 0 / 0 | 2 |

new: actual combined added vs residual|high=2, lost=0; low-only component matches=2. Episodes reconstructed, not component totals summed.

known_regression: actual combined added vs residual|high=0, lost=0; low-only component matches=0. Episodes reconstructed, not component totals summed.

## Controls (onsets / flagged points in control window)

| Case | Method | Modified | Raw pair | Event coverage |
|---|---|---:|---:|---:|
| control-raw | residual | 0 / 0 | 0 / 0 | 100.0% |
| control-raw | sustained_high | 0 / 0 | 0 / 0 | 100.0% |
| control-raw | sustained_low | 0 / 0 | 0 / 0 | 50.0% |
| control-raw | residual_high_or | 0 / 0 | 0 / 0 | 100.0% |
| control-raw | residual_high_low_or | 0 / 0 | 0 / 0 | 50.0% |
| control-zero-background | residual | 0 / 0 | 0 / 0 | 100.0% |
| control-zero-background | sustained_high | 0 / 0 | 0 / 0 | 100.0% |
| control-zero-background | sustained_low | 0 / 0 | 0 / 0 | 0.0% |
| control-zero-background | residual_high_or | 0 / 0 | 0 / 0 | 100.0% |
| control-zero-background | residual_high_low_or | 0 / 0 | 0 / 0 | 0.0% |
| control-low-background | residual | 0 / 0 | 0 / 0 | 100.0% |
| control-low-background | sustained_high | 0 / 0 | 0 / 0 | 100.0% |
| control-low-background | sustained_low | 0 / 0 | 0 / 0 | 0.0% |
| control-low-background | residual_high_or | 0 / 0 | 0 / 0 | 100.0% |
| control-low-background | residual_high_low_or | 0 / 0 | 0 / 0 | 0.0% |
| control-normal-night | residual | 0 / 0 | 0 / 0 | 100.0% |
| control-normal-night | sustained_high | 0 / 0 | 0 / 0 | 100.0% |
| control-normal-night | sustained_low | 0 / 0 | 0 / 0 | 100.0% |
| control-normal-night | residual_high_or | 0 / 0 | 0 / 0 | 100.0% |
| control-normal-night | residual_high_low_or | 0 / 0 | 0 / 0 | 100.0% |
| control-regular-nonwork | residual | 0 / 0 | 0 / 0 | 100.0% |
| control-regular-nonwork | sustained_high | 0 / 0 | 0 / 0 | 100.0% |
| control-regular-nonwork | sustained_low | 1 / 7 | 0 / 0 | 100.0% |
| control-regular-nonwork | residual_high_or | 0 / 0 | 0 / 0 | 100.0% |
| control-regular-nonwork | residual_high_low_or | 1 / 7 | 0 / 0 | 100.0% |
| control-benign-zero | residual | 0 / 0 | 0 / 0 | 100.0% |
| control-benign-zero | sustained_high | 0 / 0 | 0 / 0 | 100.0% |
| control-benign-zero | sustained_low | 1 / 1 | 0 / 0 | 50.0% |
| control-benign-zero | residual_high_or | 0 / 0 | 0 / 0 | 100.0% |
| control-benign-zero | residual_high_low_or | 1 / 1 | 0 / 0 | 50.0% |

## Gaps: separate telemetry task

[
  {
    "scenario_id": "telemetry-interval_gap",
    "known_missing_intervals": 3,
    "detected_missing_intervals": 3,
    "expected_detection_timestamp": "2016-05-14T14:30:00",
    "actual_detection_timestamp": "2016-05-14T14:30:00",
    "gap_signals": 1,
    "correct": true,
    "delay_from_first_missing_minutes": 30,
    "semantics": "returned_gap_not_silence_watchdog"
  }
]

See cases.csv for every target/miss and unavailable count; contributions.csv for each component/union overlap; unavailable-reasons.csv for reasons; episodes.csv for exact onsets and tails. Flatline and gaps are never consumption events. Paired UCI episodes are not confirmed false positives, and repeated context is not independent physical exposure.
Low has no work calendar: legitimate scheduled closures and benign zeros can trigger. Background below20Wh or nonpositive computed lower threshold yields null, not a negative decision. Union true/false/null preserves provenance and can be less available when low is unknown; positives from other methods remain positive.
Delay is dataset-time minutes for detected events only. Six observations represent60min of interval energy and50min between labels, distinct from compute milliseconds. Timing CSV contains five paired repetitions, record p50/p95 and loop totals; model loading, warmup, clone and file IO are outside timers. See timing-environment.json and parent report for interpretation.
Existing V2/ML/Unanimous sources and artifacts are checksum-protected; known-six previous scores are read solely AFTER fresh inference for exact regression verification, never substitution. Low batch and streaming results compared exactly on every record of every pair.
