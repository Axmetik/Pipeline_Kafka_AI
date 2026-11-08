# Preregistered ML–rules complementarity experiment

Registered 2026-11-08 **before scoring**. The executable specification is `plan.json` and all33 fixed cases are in `scenarios.json`.

## Scope

Fresh paired offline inference only on the current UCI house, using existing hash-verified CPU artifacts. No fitting, calibration, runtime integration, changes to frozen rules v2/Unanimous, or retrospective edits to the previous24 cases. Previously viewed historical period is not a blind holdout.

## Cases

Two predefined starts (May8 07:50 and May9 22:50), without inspecting new scores. Repetition:3/6/12 intervals; sustained excess:+200Wh for3/6/12; short peaks:+400Wh for1/2; drops:80% reduction for3/6/12; gradual changes:linear additions ending+300Wh for3/6/12. Every case uses seven prior calendar dates from midnight and144 following intervals. Three controls: unchanged raw morning, modeled normal morning50→200Wh with corresponding historical profile, assumed benign zero. Two returned-gap checks remove1/3 intervals. All33 cases retained.

## Decisions and matching

ML_OR = IF OR AE OR residual; ML_high_OR additionally includes sustained_high. True with any available positive input; false only if all required inputs available and negative; otherwise null. Preserve positive contributors, available and missing inputs on each point. Keep original Unanimous separately.

Reconstruct each method's episodes **including each OR**, on the full nullable stream before any common-ready mask. False/null or cadence breaks end an episode. An episode matches only if its onset lies inside inclusive first/last target labels; no earlier-overlap credit or after-event grace. One event per case; maximum one detection credit. Report own-available matches, common-ready diagnostics, coverage and unavailable counts; never silently drop a case. Missed delays are null.

Consumption comparison includes22 high/peak/drop/ramp events only. Count ML-only, rule-only, both and neither from separately matched ML_OR/sustained_high; compare actual combined episode matches separately because union can merge episodes. Count added **and lost** events relative to ML_OR. Preserve paired untouched-stream episode counts, flags, post-event signals and coincident raw alarms. Flatline6 targets and gap2 checks are separate telemetry-quality tasks; they do not contribute to consumption recall.

## Outputs and interpretation

New result directory only: complete point Parquet pairs, all case/method CSV, family summary, component-contribution table, controls/gaps, preselected plots, hashes, library/feature/model/threshold versions and Markdown report. Delays are dataset-time minutes; UCI labels remain timezone-naive. Raw UCI background signals are not confirmed false positives. A modeled zero/plateau can correctly trigger repetition without proving failure. No parameter selection from results; no claim of generalization to other buildings or real faults.
