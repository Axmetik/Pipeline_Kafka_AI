# Stage 4 verification

- Frozen protocol commit: `65e2b4e`; implementation experiment commit: `6d7bf26`.
- Full offline experiment completed on the checksum-pinned19,735-row dataset.
- Targets:11,699 train /1,973 calibration /1,973 validation /3,946 test.
-95 synthetic scenarios per evaluated split;190 manifests and all per-point
  scores/forecasts/labels saved. Primary threshold99%; alternatives99.5%,98%.
- Local full test suite: **42 passing tests** (39 unit,3 actual Kafka smoke tests).
  Command: `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python tests/run_suite.py --suite all`.
- Actual trained-model Kafka replay:644 accepted,1 malformed message rejected,
  500 common ready targets. All scores match offline within declared tolerance
  and all primary-threshold flags match exactly. IF/residual absolute difference0;
  AE maximum difference2.980232238769531e-7 from batch/single-row floating arithmetic.
- [Kafka verification report](kafka-verification.json) and exact injected
  [replay interventions](kafka-injections.json) are preserved separately from the
  frozen offline experiment checksum manifest.
- All four PNG figures visually inspected; equivalent SVGs are saved.
- [Artifact audit](artifact-audit.json) verifies output hashes, exact injected
  values/labels, recalculated point/event metric rows, calibration quantiles,
  validation selection and original dataset checksum. CSV floating roundtrip
  comparisons use tolerance1e-10; this does not alter any saved metric.
- Production forecasting/IoT source paths and all Stage2/3 result/protocol files
  are unchanged relative to merged main `4331bf1`.
- Runtime history/pending forecasts remain in memory; automatic Kafka commits
  and buffered Parquet are non-transactional. Warmup after restart, possible
  duplicate/lost rows and predecessor replay are documented in README.
- CI runs existing and new unit/Kafka suites on push; final run URL is supplied
  with delivery. No merge to main is performed for Stage4.

See [experiment report](results/report.md) and [interpretation](interpretation.md).
