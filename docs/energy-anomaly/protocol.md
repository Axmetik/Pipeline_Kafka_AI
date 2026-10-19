# Stage 4 frozen experimental protocol

This document and configs/energy-anomaly-v1.json are committed before fitting,
calibration, injection generation or experimental evaluation. Approved plan:
[approved-plan.md](approved-plan.md). No test-driven changes are permitted.

## Data, feature contracts and fitting

Original UCI Appliances CSV checksum is pinned in JSON. Energy remains Wh per
600 seconds; naive dataset timestamps retain their original meaning.
Train targets: Jan 12 17:00–Apr 2 22:40 (11699); calibration Apr 2 22:50–Apr 16
15:30 (1973); validation Apr 16 15:40–Apr 30 08:20 (1973); test Apr 30 08:30–May
27 18:00 (3946). All dates are 2016. Boundaries refer to measurement/target time.

IF/AE score current observations using unchanged Stage 2 20-feature engineering.
RF uses unchanged Stage 3 21-feature engineering (seasonal time is forecast target
minus 24 hours). Residual is actual minus a forecast made at the previous interval;
no current actual may enter that forecast. Models compare on common ready times.
Original runtime feature code and Stage 2/3 artifacts/results are not modified.
Source identities, units, feature ordering, versions and horizon are bound in artifacts.

All preprocessing fits train only. IF: median imputation, StandardScaler, fixed
300 trees/max_samples256. AE: same preprocessing, 20→16→8→16→20, ReLU hidden,
linear output, MSE, Adam. Chronological internal train 85/15 chooses epoch count
(up to100, patience10, lr.001, batch128); fit preprocessing only internal fit during
this choice. Reinitialize and refit AE/preprocessing on full train for chosen epochs.
RF fixed Stage 3 parameters refit only Stage 4 train, median imputation. No refit
on calibration/validation. Seeds42, CPU, one thread; versions recorded.

IF score=negative score_samples; AE=mean squared reconstruction error; residual=
absolute error in Wh (signed error also saved). Thresholds use numpy linear quantiles
.99 primary, .995 and .98 sensitivity on unchanged calibration, with strict >.
No automatic contamination-based threshold or adaptive online fit.

## Injection protocol (before any experimental scores)

An independent copy of each validation/test partition is used per scenario, with
144 original preceding context rows. Original CSV never changes. For every type,
severity0/1/2 and seed run one scenario (90), plus5 mixed scenarios:95 per split.
Stuck strength is fixed; severity repetitions are retained and reported as such,
not as distinct amplitudes. Clean partition replay is a separate control.

Target modified points=floor(.02*N); durations are sampled uniformly inclusive from
JSON, truncated to remaining budget only if at least the minimum duration. Positions
are sampled uniformly among partition indices; events cannot overlap, cross split
boundaries or be within144 unmodified intervals of another event. Cap10000 placement
attempts per event; if no position fits, stop and report achieved count/prevalence.
For mixed scenarios cycle a seeded permutation of the six types, sample severity
uniformly for each event. No score-based placement. Low-activity context hours are
six lowest train median-energy hours, ties resolved by hour. Context event must
start during one of those hours. Transformations:

- spike: E + strength*train IQR;
- drop: E * multiplier;
- level_shift: E + strength*train IQR throughout event;
- drift: E + linearly increasing strength*train IQR (positive first increment);
- stuck: repeat the last available pre-event reading;
- context_load: E + strength*train IQR during the event.

Train IQR=linear Q75−Q25; floor1Wh. All modifications are nonnegative. Labels
identify intervention intervals, including coincident values unchanged by a stuck
transformation. Report both labeled and numerically changed counts. Missing,
invalid, duplicate and out-of-order messages are separate data-quality tests.

Detectors never see labels/original counterparts. Recompute history from modified
measurements, including all post-event effects. Do not clean history using labels.
Recovery tail=[end+1,end+144], clipped to split; exclude new events from tail masks.
Tail alarms count in background errors too, never hidden by exclusion.

## Evaluation and decision

Same ready timestamps for all detectors; also per-method readiness/warmup and
coverage. Precision/recall/F1/FPR use synthetic labels only and are conditional
on the unlabeled original background. Clean UCI alerts are background alarms,
not verified false positives. Report counts, alarms/day (observed eligible interval
exposure N*10 minutes), stratification by train-only P90 high load, and recovery tails.
High loads are not automatically anomalies.

An alarm episode is consecutive flagged intervals (gaps break episodes). Match
alarm episodes in time order to the earliest still-unmatched injection event that
overlaps it; at most one match per episode/event. Detection window exactly [start,end],
no tolerance after end. Event precision=matches/alarm episodes; recall=matches/events.
Delay is first flagged time in the matched overlap minus event onset, in minutes.
Missed events are recorded separately; they never receive zero delay. No point
adjustment. Undefined precision/F1 use zero, absent-event recall and delay use null.
Store individual event outcomes, scores, labels and forecasts; point/event scores,
median/p95 detection delay, missed fraction and wall-clock replay time separately.

At primary quantile select by macro-average validation event F1 over mixed seeds,
restricted to clean-validation background alarm rate<=1%; ties by mean matched-event
median delay (no detections→infinity), then background rate, then IF/AE/residual order.
If none qualify, report no deployment-ready winner. Save decision before any test
scores. All detectors/thresholds are reported on test irrespective of selection.

All windows and RF hyperparameters have historical Stage 3 exposure; this is NOT
an unseen independent holdout. Fresh injection seeds do not remove that limitation.
Synthetic detection does not establish accuracy on real operational faults.

## Outputs and verification

Persist config/protocol hashes, dataset/source/model hashes, software versions,
thresholds, train preprocessing, seeds, exact injection manifests, per-point Parquet,
event outcomes, CSV/JSON tables and PNG/SVG plots under docs/energy-anomaly/results/.
Large trusted model artifacts remain under ignored artifacts/energy-anomaly/v1/.

Unit checks: causality, seasonal/residual alignment, split and preprocessing isolation,
source/schema compatibility, injection determinism and boundary safety, event matching,
tail masks, serialization and offline/streaming parity. Real Kafka replay must match
offline scores on modified data, save nullable warmup statuses and flush Parquet.
New consumer has separate group/storage; no changes to production forecasting/IoT.
Restart state is in memory: replay144 predecessors with a new group for valid warmup;
commit/Parquet crash behavior remains non-transactional and is documented explicitly.
