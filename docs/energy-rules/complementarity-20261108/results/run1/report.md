# ML–rules complementarity: controlled historical comparison

All33 preregistered cases retained. Fresh paired inference, existing compatible artifacts only; no training or threshold/config changes. Same previously studied UCI house/period, not a new independent holdout. Synthetic labels do not prove physical faults.

## Consumption events only (22)

| Method | Detected / target | Missed | Coverage: event / stream | Median delay,min | Raw pair episodes: all / event | New paired crossings |
|---|---:|---:|---:|---:|---:|---:|
| autoencoder | 2/22 | 20 | 100.0% / 99.5% | 70 | 121 / 3 | 0 |
| isolation_forest | 1/22 | 21 | 100.0% / 99.5% | 70 | 0 / 0 | 1 |
| ml_high_or | 11/22 | 11 | 100.0% / 65.4% | 30 | 231 / 9 | 7 |
| ml_or | 8/22 | 14 | 100.0% / 88.5% | 15 | 231 / 9 | 4 |
| residual | 8/22 | 14 | 100.0% / 88.5% | 15 | 121 / 6 | 4 |
| sustained_high | 6/22 | 16 | 100.0% / 65.4% | 50 | 0 / 0 | 6 |
| unanimous | 0/22 | 22 | 100.0% / 88.5% | — | 0 / 0 | 0 |

## Contribution (component event matches, not sum of union metrics)

ML_OR only: **5**; sustained_high only: **3**; both: **3**; neither: **11**.
Actual recomputed ML+high OR adds **3** and loses **0** event matches relative to ML_OR. Net change: **+3**.
Union-episode match differs from component-event set union in **0** cases.

## Per-family detected counts

| Family | Method | Detected / target | Median delay,min |
|---|---|---:|---:|
| drop | autoencoder | 0/6 | — |
| drop | isolation_forest | 0/6 | — |
| drop | ml_high_or | 0/6 | — |
| drop | ml_or | 0/6 | — |
| drop | residual | 0/6 | — |
| drop | sustained_high | 0/6 | — |
| drop | unanimous | 0/6 | — |
| flatline | autoencoder | 0/6 | — |
| flatline | flatline | 4/6 | 40 |
| flatline | isolation_forest | 0/6 | — |
| flatline | ml_or | 0/6 | — |
| flatline | residual | 0/6 | — |
| flatline | unanimous | 0/6 | — |
| gradual_change | autoencoder | 1/6 | 70 |
| gradual_change | isolation_forest | 0/6 | — |
| gradual_change | ml_high_or | 3/6 | 30 |
| gradual_change | ml_or | 2/6 | 30 |
| gradual_change | residual | 2/6 | 30 |
| gradual_change | sustained_high | 2/6 | 70 |
| gradual_change | unanimous | 0/6 | — |
| short_peak | autoencoder | 0/4 | — |
| short_peak | isolation_forest | 0/4 | — |
| short_peak | ml_high_or | 4/4 | 0 |
| short_peak | ml_or | 4/4 | 0 |
| short_peak | residual | 4/4 | 0 |
| short_peak | sustained_high | 0/4 | — |
| short_peak | unanimous | 0/4 | — |
| sustained_high | autoencoder | 1/6 | 70 |
| sustained_high | isolation_forest | 1/6 | 70 |
| sustained_high | ml_high_or | 4/6 | 40 |
| sustained_high | ml_or | 2/6 | 30 |
| sustained_high | residual | 2/6 | 30 |
| sustained_high | sustained_high | 4/6 | 50 |
| sustained_high | unanimous | 0/6 | — |

## Controls: new episode onsets / flagged points in control window

| Control | Method | Modified | Untouched pair |
|---|---|---:|---:|
| control-raw-morning | isolation_forest | 0 / 0 | 0 / 0 |
| control-raw-morning | autoencoder | 0 / 0 | 0 / 0 |
| control-raw-morning | residual | 0 / 0 | 0 / 0 |
| control-raw-morning | ml_or | 0 / 0 | 0 / 0 |
| control-raw-morning | sustained_high | 0 / 0 | 0 / 0 |
| control-raw-morning | ml_high_or | 0 / 0 | 0 / 0 |
| control-raw-morning | unanimous | 0 / 0 | 0 / 0 |
| control-raw-morning | flatline | 1 / 1 | 1 / 1 |
| control-raw-morning | interval_gap | 0 / 0 | 0 / 0 |
| control-modeled-morning | isolation_forest | 0 / 0 | 0 / 0 |
| control-modeled-morning | autoencoder | 0 / 0 | 0 / 0 |
| control-modeled-morning | residual | 0 / 0 | 0 / 0 |
| control-modeled-morning | ml_or | 0 / 0 | 0 / 0 |
| control-modeled-morning | sustained_high | 0 / 0 | 0 / 0 |
| control-modeled-morning | ml_high_or | 0 / 0 | 0 / 0 |
| control-modeled-morning | unanimous | 0 / 0 | 0 / 0 |
| control-modeled-morning | flatline | 1 / 8 | 1 / 1 |
| control-modeled-morning | interval_gap | 0 / 0 | 0 / 0 |
| control-benign-zero | isolation_forest | 0 / 0 | 0 / 0 |
| control-benign-zero | autoencoder | 0 / 0 | 0 / 0 |
| control-benign-zero | residual | 0 / 0 | 0 / 0 |
| control-benign-zero | ml_or | 0 / 0 | 0 / 0 |
| control-benign-zero | sustained_high | 0 / 0 | 0 / 0 |
| control-benign-zero | ml_high_or | 0 / 0 | 0 / 0 |
| control-benign-zero | unanimous | 0 / 0 | 0 / 0 |
| control-benign-zero | flatline | 1 / 7 | 1 / 1 |
| control-benign-zero | interval_gap | 0 / 0 | 0 / 0 |

## Returned gaps — separate telemetry check

| Case | Missing / reported | First return | Correct |
|---|---:|---|---|
| gap-n1 | 1 / 1 | 2016-05-10T08:10:00 | True |
| gap-n3 | 3 / 3 | 2016-05-10T14:30:00 | True |

## Interpretation and reproduction

Flatline targets and returned gaps are excluded from every consumption total above. Repeated benign zero and normal plateaus may produce a correct repetition signal without a fault. Raw UCI paired episodes are not verified false positives. Counts include duplicated historical context across independently initialized case streams, not unique physical days/buildings.
All episodes are reconstructed separately for each OR on full nullable streams. A pre-existing episode does not receive overlap credit. Delay is dataset-time minutes for detected events only; misses have null delay. New paired crossing means raw-pair flag is explicitly false at the matched modified onset; unavailable raw flag is separately unknown.
Coverage is decision availability, not availability of every union input: a known positive makes OR true even with missing inputs. points/* stores required/available/missing/positive contributors for both unions at every timestamp. Summary includes common-ready onset diagnostic, unavailable counts and signal rates; cases.csv retains every method/case and missed event. No cases are filtered out for incomplete coverage.
Plots show true markers and unavailable crosses. Orange shading extends through the energy duration of the final interval; event matching ends at its label, with no extra grace.
The local trusted bundle differs from archived original Stage4 binary; its version, exact thresholds and hashes are recorded. No archived scores are loaded. Historical24-case outputs remain unchanged and are not pooled.
Reproduction: use the frozen plan/manifest in the parent directory, exact image ID, read-only repo/artifacts/dataset mount, no network and single-thread policy. Run python -m diagnostics.rule_complementarity --output NEW_EMPTY_DIRECTORY. Never reuse run1. See the parent README for exact Docker command and interpretation.

Combination finds additional event matches in this fixed set; this is a limited complementarity result, not proof of operational precision or universal superiority.
