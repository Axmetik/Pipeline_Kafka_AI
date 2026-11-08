# Controlled comparison on historical Appliances data

Exploratory synthetic scenarios, not a new holdout or verification of real faults. All24 planned cases retained. No fitting, calibration or parameter selection. Existing local trusted bundle identity differs from archived Stage4 original binary; old metrics are not substituted.

## Target events (common-ready onset matching)

| Family | Method | Detected / target | Target coverage | Common coverage | Median detected delay,min | Pair episodes (whole streams / event windows) |
|---|---|---:|---:|---:|---:|---:|
| flatline | autoencoder | 0/6 | 100.0% | 100.0% | — | 30 / 0 |
| flatline | flatline | 4/6 | 100.0% | 100.0% | 35 | 36 / 0 |
| flatline | isolation_forest | 0/6 | 100.0% | 100.0% | — | 12 / 0 |
| flatline | residual | 0/6 | 100.0% | 100.0% | — | 51 / 3 |
| flatline | unanimous | 0/6 | 100.0% | 100.0% | — | 6 / 0 |
| sustained_high | autoencoder | 3/12 | 100.0% | 100.0% | 50 | 60 / 0 |
| sustained_high | isolation_forest | 1/12 | 100.0% | 100.0% | 60 | 24 / 0 |
| sustained_high | residual | 6/12 | 100.0% | 100.0% | 10 | 102 / 6 |
| sustained_high | sustained_high | 8/12 | 100.0% | 100.0% | 50 | 12 / 0 |
| sustained_high | unanimous | 0/12 | 100.0% | 100.0% | — | 12 / 0 |

Pair counts are sums over separately initialized case streams, including repeated historical context; they are neither unique-building alarm counts nor confirmed false positives. Episode onsets and flagged points are separately preserved in the detailed CSV. Missed-event delays are null; short below-duration cases remain in denominators.

## Returned gaps (not consumption-event recall)

| Case | Missing / reported intervals | First-return detection correct | Event-time delay from first missing,min |
|---|---:|---|---:|
| gap-04-n1 | 1 / 1 | True | 10 |
| gap-05-n3 | 3 / 3 | True | 30 |
| gap-06-n6 | 6 / 6 | True | 60 |

## Controls (event-window flagged points / new episode onsets)

| Control | Method | Modified flags / onsets | Raw pair flags / onsets |
|---|---|---:|---:|
| control-single-peak | flatline | 0 / 0 | 0 / 0 |
| control-single-peak | sustained_high | 0 / 0 | 0 / 0 |
| control-single-peak | isolation_forest | 0 / 0 | 0 / 0 |
| control-single-peak | autoencoder | 0 / 0 | 0 / 0 |
| control-single-peak | residual | 0 / 0 | 0 / 0 |
| control-single-peak | unanimous | 0 / 0 | 0 / 0 |
| control-morning-rise | flatline | 8 / 1 | 0 / 0 |
| control-morning-rise | sustained_high | 0 / 0 | 0 / 0 |
| control-morning-rise | isolation_forest | 0 / 0 | 0 / 0 |
| control-morning-rise | autoencoder | 0 / 0 | 0 / 0 |
| control-morning-rise | residual | 0 / 0 | 0 / 0 |
| control-morning-rise | unanimous | 0 / 0 | 0 / 0 |
| control-normal-zero | flatline | 7 / 1 | 0 / 0 |
| control-normal-zero | sustained_high | 0 / 0 | 0 / 0 |
| control-normal-zero | isolation_forest | 0 / 0 | 0 / 0 |
| control-normal-zero | autoencoder | 0 / 0 | 0 / 0 |
| control-normal-zero | residual | 0 / 0 | 0 / 0 |
| control-normal-zero | unanimous | 0 / 0 | 0 / 0 |

The morning schedule is explicitly modeled over context and observation records, not validated natural normality. The zero window is assumed benign: a flatline flag there may correctly describe repetition but is not a confirmed stuck-meter diagnosis. A one-point peak is not a sustained-high target. No control is relabeled as a successful anomaly detection.

## Files and reproducibility

`all-methods-all-cases.csv` retains every method/case, own and common coverage, strict matches, pre-existing overlap, paired-crossing diagnostics, tail signals and null delays. `controls.csv` and `returned-gaps.csv` keep tasks separate. `points/*.parquet` contains fresh original and altered scores, exact thresholds, nullable flags, previous-interval residual forecasts and full rule evidence. `provenance.json` records checksums, versions, preservation and parity; no old score files are input.

See the preregistered parent `plan.md`, `plan.json`, `scenarios.json`, and runner `diagnostics/rule_comparison.py`. Run in the exact existing inference image with read-only source/artifact/dataset mount, a new writable output directory, no network and single-thread policy. Output directory reuse is refused. No Worker, DB, API, Dashboard or Email process is used.

Offline/streaming parity: 150 modified event/tail records, all three scores/flags and previous-origin/target alignment match within the declared tolerance.

## Interpretation boundary

These counts concern predefined manipulations of one historical house with known but artificial event windows. They do not establish production accuracy, independent generalization, real failures or a universal winner. A short intervention may be intentionally too short for a duration rule. Flatline and high-consumption families have different target meanings and must not be pooled; returned gaps are a third separate task. All failures and pre-existing alarms are retained.
