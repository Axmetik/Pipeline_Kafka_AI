# Stage 3 verification

- Protocol committed before execution: `09d2c93`.
- Experiment implementation: `0f7776c`, clean tracked working tree when run.
- Full dataset: 19,735 rows, checksum matched, no rejected records.
- Common targets: 11,699 train / 3,946 validation / 3,946 test.
- Final local command: `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python tests/run_suite.py --suite all`.
- Result: **33 tests passed**, including 31 unit tests and 2 real Kafka smoke tests
  (Energy replay→forecast→Parquet and existing IoT transport/storage).
- New tests cover target-relative daily lag, continuity and source isolation,
  causal features, disjoint chronological splits, train-fitted imputation,
  deterministic selection/refit, train-only peak threshold, and end-to-end
  report/prediction/figure output on a small synthetic fixture.
- Separate full-artifact audit reconstructed both baselines from the original
  CSV, checked all 3,946 unique test target/origin pairs, and reproduced every
  overall/peak metric from saved per-row forecasts (tolerance 1e-12).
- All four PNG figures visually inspected; SVG equivalents saved.
- Production paths `producer/`, `consumer/`, `processing/`, `ai/`, `storage/`,
  `config.py`, and `docker/` have no changes relative to Stage 2 (`c8ce78f`).
- One intervening local rerun failed its two Kafka tests while network permission
  was unavailable. After restoring the session permission, the full suite passed.
- GitHub Actions runs the unit and Kafka jobs on every push. The final run URL
  is provided with the delivery; this file does not claim a pending run passed.

See [results](results/report.md) and [interpretation](results/interpretation.md).
