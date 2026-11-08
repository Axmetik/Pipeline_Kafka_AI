# Small controlled offline comparison — registered before execution

Date2026-11-08. See `plan.json` for frozen input hashes/configuration and `scenarios.json` for **all24** exact cases. No result-based selection or rerun with changed parameters.

- Six flatline events: hold the preceding observed energy for3/6/12 intervals, starting07:50 or14:00. Short events are intentionally below the six-observation requirement. A natural pre-existing plateau may prevent a new episode onset; retain that nondetection.
- Twelve sustained-high events: +100/+300Wh, durations3/6/12, starts07:50 or22:50, including hour transitions. Duration/strength are intervention definitions, not guaranteed rule positives.
- Three returned-gap events: remove1/3/6 records at different times, including midnight. Match missing-count and detection at the first returned record separately from consumption detection.
- Three controls: one +300Wh point, a **modeled** normal morning schedule, and twelve assumed-benign zero-energy intervals. For the morning control only, replace energy throughout the full context/evaluation stream by50Wh before08h and200Wh from08h onward, while retaining the original timestamps/environment. This tests context handling; it is not a naturally verified normal UCI profile. All other edits affect the declared event window only.

Each case has its own untouched raw UCI pair, a seven-calendar-day context beginning at midnight, and144 post-event intervals. Histories and previous-interval forecasts advance on the actual modified stream. No resetting at event onset, no substituting old scores or clean forecasts. The same source-bound existing artifact is used throughout.

ML scores are freshly computed using existing causal `collect` plus `score_batch`; no fitting. An independent streamed-parity check on one preregistered high case (`high-04-0750-n6-add300`) compares all modified event and tail scores against fresh `StreamDetector` output, including prior forecasts (timestamp formation fields excluded). This parity check is not a new scenario or parameter search.

Primary comparisons: flatline vs IF/AE/residual/Unanimous over the six flatline cases; sustained_high vs those four over the twelve high cases. For each family use identical common-ready timestamp masks and onset-only one-to-one event matching. Build episodes before applying the common mask: masking must not fabricate a new onset. Also report method-specific coverage and strict detections, target-window coverage and misses, including events shorter than the rule duration. Null flags are unavailable, never false negatives disguised as normal predictions.

Onset must be within `[start,last_modified_label]`; no post-event grace and no credit for an alarm already open before the event. One event per case; detected-event delay is in event-time minutes. Record overlaps without new onset separately. For gap episodes, detection is at the first returned timestamp and the count is the known removed-record count; do not report these as consumption event TP.

Report all control-window flags/new onsets with no anomaly TP label. A flatline signal on benign repeated zero may describe the pattern correctly but cannot diagnose a stuck meter. Untouched-pair alarms are not confirmed false positives (UCI has no fault ground truth).

Expected outputs: per-point Parquet (fresh scores/thresholds/nullable flags, rules evidence, predictions), all-event and control CSVs, method/family summary CSVs with exact denominators, gap-count/timing checks, characteristic plots (selected **before** execution: flatline3/6/12 at07:50; high6/+300 at07:50; morning/zero controls; three gaps), provenance/preservation hashes and Markdown report. No existing results overwritten. Refuse missing/incompatible artifacts; do not retrain as a fallback.
