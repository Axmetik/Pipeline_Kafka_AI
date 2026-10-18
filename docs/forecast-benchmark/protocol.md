# Stage 3 — protocol fixed before execution

This protocol is committed before running the benchmark. No test-based parameter
adjustments, feature searches or reruns for a more favorable ranking are permitted.
The machine-readable protocol is `benchmark/protocol.json`.

- Dataset: original UCI Appliances Energy Prediction CSV, SHA-256
  `2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d`.
- Target: Appliances interval energy in Wh, horizon 10 minutes. Original naive
  timestamps are preserved; no timezone is inferred.
- Common eligible targets require 144 consecutive ten-minute history observations
  and an observed next target. Gaps reset history; no fallback replaces a missing
  seasonal value. All four models use exactly the same target IDs.
- Train targets: 2016-01-12 17:00 through 2016-04-02 22:40 (11,699 expected).
- Validation: 2016-04-02 22:50 through 2016-04-30 08:20 (3,946 expected).
- Test: 2016-04-30 08:30 through 2016-05-27 18:00 (3,946 expected).
- **The Stage 2 test results were already viewed. This is a reused test set, not a
  previously unseen independent holdout.** This limits unbiased generalization claims.
- One-step sequential evaluation: previously observed validation/test energy may
  enter later feature history; future values never enter earlier features or fitting.

## Models and fixed features

Persistence predicts E(t) for target tau=t+10min. Seasonal Naive predicts
E(tau-24h), checking exact timestamps and uninterrupted history. This is 144 steps
behind the target, or 143 behind the last observed origin, not a naive shift(144)
of the current-origin feature row.

Both ML models receive the same 20 Stage 2 features plus the seasonal reference.
Reuse EnergyProcessor without modifying the active Energy/IoT inference code.
Both use an explicit sklearn Pipeline with median SimpleImputer (keep_empty_features)
and the estimator; existing missingness indicators remain included. Imputation is
fit only on train during validation search, then train+validation for final refit.
Targets are never imputed. Predictions are clipped at zero consistently with Stage 2.

RF: 12 configurations: n_estimators=[200,400], max_depth=[12,None],
min_samples_leaf=[1,5,10]; random_state=42, n_jobs=1.
HGB: 16 configurations: learning_rate=[0.05,0.1], max_iter=[100,200],
max_leaf_nodes=[15,31], l2_regularization=[0,1]; random_state=42,
early_stopping=False, squared_error loss. One CPU thread for all models.

Select each family's parameters only by validation MAE, then validation RMSE,
then fixed candidate order for exact ties. Choose the recommended family among
all four methods by the same validation ordering, before test evaluation.
Freeze and save selection; refit both selected ML configurations on train+validation.
Report test results for all four; do not change selection based on the test ranking.

## Metrics, peaks and timing

MAE and RMSE in Wh; signed error=prediction-actual.
Relative improvement=100*(persistence error-model error)/persistence error;
negative values mean worse performance, zero denominator yields null.
Peak threshold is the 90th percentile of train targets (linear quantile), fixed
before evaluation/refit. A peak means actual>threshold. Report count, MAE, RMSE,
mean signed error and underprediction fraction. High loads are not labeled anomalies.

Prediction timing excludes data reading, feature construction, fitting, model load,
Kafka and Parquet. Use 256 evenly spaced test feature rows (or all if fewer),
10 warm-up calls and 5 single-row passes per model. Include ML preprocessing in
predict time. Report median and p95 in microseconds; record hardware/software.
Timing is descriptive and is not used to select a model. Wall-clock timings are
not expected to reproduce bit-for-bit even when predictions do.

Plots: first seven test days; top three actual-load peak episodes separated by
at least six hours with +/-3-hour windows; signed-error distributions; MAE/RMSE
and latency comparisons. Peak plots are selected using actual loads, not favorable
model errors. Save PNG and SVG.

## Outputs and scope

Save configs, protocol hash, seed, code Git revision/tree snapshot hash, library
versions, split manifests, all validation trials, chosen configurations, train-only
peak threshold, all per-observation test predictions, metrics, timing data, plots
and Markdown report. Models are local artifacts, excluded from Git. Compact tables,
plots and report are versioned in docs/forecast-benchmark/results/.

No changes to current Energy Kafka inference, IoT, anomaly detectors, database,
API or dashboard. Integration of a recommended model is a later approved task.
