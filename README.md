# Kafka IoT pipeline

Existing flow: synthetic data / Intel Lab → Kafka → rules → Isolation Forest →
Autoencoder → CSV + Parquet. Energy forecasting, a database, API and dashboard
are future stages. This baseline preserves the current four-feature models.

## Setup

Run commands from the repository root. The baseline is verified with Python 3.13.2.

```sh
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose -f docker/docker-compose.yml up -d
```

Docker must be running. Compose starts Kafka and Kafka UI; Python processes run
on the host. Kafka UI is at http://localhost:8080. Check broker readiness before
starting the Python processes:

```sh
docker compose -f docker/docker-compose.yml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:29092 --list
```

## Finite demo

Use the same environment in both terminals. Choose a **new** topic, consumer group
and output directory for every independent demo. The values below are examples;
change the suffix on subsequent runs. This avoids mixing old offsets or files.

```sh
export KAFKA_TOPIC=iot-demo-001
export KAFKA_GROUP_ID=iot-demo-001
export PIPELINE_OUTPUT_DIR=data/demo-001
export PARQUET_BATCH_SIZE=10
```

Terminal 1:

```sh
python -m consumer.iot_consumer --max-messages 30 --idle-timeout-ms 60000
```

Terminal 2, with the same environment:

```sh
python -m producer.iot_producer --limit 30 --sleep 0 --seed 42 --start 2026-01-01T00:00:00+00:00
```

Expected: `accepted=30, rejected=0`, 30 rows in `iot_sensor_data.csv`, and 30 rows
across the Parquet files. The timestamp advances by two seconds per record,
independently of replay speed. Fixing seed and start reproduces the payloads.
This short demo exercises transport and storage; default models are still warming
up (500 records for Isolation Forest, 2000 for Autoencoder). The offline smoke
test below uses small windows to verify actual training and inference for both.

Without `--limit` / `--max-messages`, producer / consumer run continuously.
Ctrl-C flushes the consumer's remaining Parquet buffer. `--max-messages` counts
both accepted and rejected messages. An idle timeout exits even if fewer messages
arrive; check the printed counts.

## Configuration

Environment variables are read directly; `.env` files are not loaded automatically.

| Variable | Default |
| --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| `KAFKA_TOPIC` | `iot-sensor-data` |
| `KAFKA_GROUP_ID` | `iot-processing-group` |
| `PIPELINE_OUTPUT_DIR` | `data/processed` |
| `PARQUET_BATCH_SIZE` | `5000` |
| `INTEL_LAB_DATASET_PATH` | `data/raw/intel_lab_data.txt` |

Intel Lab input is not distributed in this repository. Supply its whitespace-separated
file with columns `date time epoch mote_id temperature humidity light voltage`, then:

```sh
python -m producer.intel_lab_producer --limit 100 --sleep 0.1
```

## Message and storage contract

Required fields: positive integer `sensor_id`, ISO 8601 `timestamp` containing date
and time, and finite numeric `temperature`, `humidity`, `light`, `voltage`.
Numeric strings are normalized to floats; booleans, NaN and infinity are rejected.
Additional input fields are ignored. New synthetic timestamps include UTC; legacy
Intel Lab timestamps retain their unspecified timezone without guessing it.

Invalid JSON, invalid UTF-8, null values and invalid records are appended to
`rejected.jsonl` with a reason, original payload encoded as Base64, and Kafka
`topic`, `partition`, `offset`. The next message is still processed. Storage or
model failures remain fatal instead of silently discarding valid records.

CSV and Parquet share the same ordered columns, including `light` and `voltage`.
An existing CSV with the old header is **not modified**: startup fails with a
message asking for a new `PIPELINE_OUTPUT_DIR`. No migration of old data is automatic.
Parquet filenames use UUIDs to avoid replacement on restart. Partitions use the
UTC date of writing, not the measurement date. Run one consumer writer per output directory.

## Checks

```sh
python -m unittest discover -s tests -v
```

These checks use temporary directories and real models with small training windows.
They cover validation, bad-message isolation, final flush, CSV/Parquet parity,
legacy CSV preservation, and Parquet restart collisions. The broker test is skipped
unless explicitly enabled:

```sh
RUN_KAFKA_SMOKE=1 python -m unittest discover -s tests -p test_kafka_smoke.py -v
```

The broker test creates and deletes a uniquely named test topic and writes only
temporary files. Kafka must be running and topic creation/deletion allowed.

## Current limitations

Kafka auto-commit and buffered Parquet remain unchanged: this stage does not provide
crash-safe delivery or deduplication. Abrupt termination may lose buffered Parquet
records or produce differences between storage formats. Model training remains
synchronous; Isolation Forest retrains per message after warm-up. Warm-up flags
are still `False`, not an explicit unknown status. These require a subsequent stage.

Existing analysis scripts use `data/processed` paths and are not yet parameterized.
They are preserved; use a matching dataset when running them. The storage comparison
script does not verify that historical CSV and Parquet contain identical records.

Stop services with `docker compose -f docker/docker-compose.yml down`.
The existing Compose configuration has no explicit persistent Kafka volume;
do not treat it as durable storage across container recreation.

## Energy Pipeline (stage 2)

Independent scenario: **Appliances CSV → Kafka → causal preprocessing → frozen
HistGradientBoostingRegressor + persistence → separate Parquet archives**.
The IoT commands, detectors and default storage schema above remain unchanged.

### Dataset and offline training

Use the same Python environment. Dependencies are already in `requirements.txt`.
The download command verifies HTTPS and refuses to overwrite an existing file:

```sh
python -m producer.download_appliances --output data/energy/raw/energydata_complete.csv
OMP_NUM_THREADS=1 python -m ai.train_energy_forecaster \
  --dataset data/energy/raw/energydata_complete.csv \
  --output artifacts/energy/appliances-hgb-bound-v1
```

Source: [UCI Appliances Energy Prediction](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction),
Candanedo (2017), DOI `10.24432/C5VC8G`, CC BY 4.0.
`Appliances` is **Wh per 10-minute interval**, not watts, and is not silently added
to `lights` or relabeled as whole-building consumption. `T1` and `RH_1` describe
the kitchen. Other CSV measurements are archived as additional parameters.
The random `rv1`/`rv2` fields are excluded, and airport weather is not used as a
model feature because its historical interpolation does not establish real-time availability.

The original timestamp labels have no assigned timezone. The adapter preserves
this with `timezone=null` and `timestamp_reference=dataset_label`. It does not
claim these are verified interval start/end timestamps. Row t is treated as
available before row t+1 for this replay experiment.

Each new experiment requires a new output directory. It produces:

- `model.joblib`: trusted local model and metadata; never load untrusted pickle/joblib files.
- `metadata.json`: model/feature versions, parameters, ordered features, seed,
  dataset SHA-256, software versions, train/test boundaries and replay range.
- `metrics.json`: actual MAE/RMSE in Wh for model and persistence, counts and quality report.
- `test_predictions.parquet`: held-out prediction origins, targets, actual values and predictions.

The first 80% of eligible **target times** train the model; the last 20% evaluate it.
There is no shuffle or automatic early stopping. The test is sequential one-step
forecasting with a frozen model: earlier observed test measurements can form later
features, but no test target is used in fitting. Persistence predicts the last
observed energy. Parameters are fixed before test evaluation.

### Contract, features and clocks

The machine-readable contract is `schemas/energy-message-v1.schema.json`.
Messages identify a building/source, source type (`dataset` or `smart_meter`),
measurement timestamp/reference, interval, energy value/unit/scope and environment.
Only interval energy in Wh/kWh is accepted; kWh is converted to Wh. W and
cumulative meter readings need an upstream adapter. This first trained model is
for `scope=appliances` and 600-second intervals. An explicit timezone label requires
an offset-bearing timestamp with a matching offset; naive dataset times stay naive.

`processing.energy_processor.EnergyProcessor` is the **single** feature implementation
for both training and Kafka inference. It uses current energy, 1–6 prior interval
lags, rolling mean/std over the latest 3/6 records (including current), current
kitchen temperature/humidity and missingness indicators, and cyclic hour/weekday
features plus a weekend indicator. No future weather or energy is used.

There are three separate time concepts:

- `measurement_timestamp` / `forecast_origin`: original event time t of the latest known measurement.
- `forecast_generated_at_utc`: actual wall-clock time the prediction was produced during replay.
- `forecast_target_timestamp`: t + 600 seconds in the source timestamp convention.

`received_at_utc` separately records ingestion. Source timestamps are stored as
strings to preserve naive vs offset-bearing semantics without silently imposing UTC.

Invalid energy, JSON, schema or timestamps go to `rejected.jsonl`. Missing/nonfinite
temperature or humidity and humidity outside 0–100% become null with quality flags;
HGB handles missing values. Large valid energy values are not clipped as anomalies.
Histories are isolated per building/source. Duplicate or out-of-order timestamps
are rejected; a gap resets history. Seven consecutive measurements are needed,
so the first six have `insufficient_history` and null predictions. Model output
is clipped at zero to respect nonnegative consumption. Late-event buffering,
persistent deduplication and automatic resampling are not implemented.

### Kafka replay

Start Kafka using the earlier Compose instructions. Set these variables in both
producer and consumer terminals (use new names/directories for independent runs):

```sh
export ENERGY_KAFKA_TOPIC=energy-demo-001
export ENERGY_KAFKA_GROUP_ID=energy-demo-001
export ENERGY_OUTPUT_DIR=data/energy/demo-001
export ENERGY_PARQUET_BATCH_SIZE=1000
```

Consumer:

```sh
OMP_NUM_THREADS=1 python -m consumer.energy_consumer \
  --model artifacts/energy/appliances-hgb-bound-v1/model.joblib \
  --max-messages 100 --idle-timeout-ms 60000
```

Producer:

```sh
python -m producer.energy_producer \
  --dataset data/energy/raw/energydata_complete.csv --limit 100 --sleep 0
```

`--start`/`--end` select inclusive event-time bounds. `--speed 60` replays source-time
differences 60 times faster; alternatively `--sleep` sets a fixed delay between
messages. Original timestamps are never replaced by wall-clock times. Kafka keys
are building/source pairs. The CSV must already be strictly chronological.

Energy uses separate environment variables above; only `KAFKA_BOOTSTRAP_SERVERS`
is shared with IoT. Its default output is `data/energy/processed`, topic
`energy-measurements`, group `energy-processing-group`, batch size 5000.

`measurements/` contains facts and quality flags; `forecasts/` contains prediction
origins, target times, generation times, status, model version, and ML/baseline
predictions. Facts and predictions are joined by building/source and target time;
future actual values are not fabricated or backfilled into forecast files.
Both archives use explicit nullable Arrow schemas, including for all-null warm-up
batches, and UUID filenames. Their directory partitions use the UTC date of writing.

### End-to-end verification

```sh
OMP_NUM_THREADS=1 RUN_KAFKA_SMOKE=1 python -m unittest discover -s tests -v

OMP_NUM_THREADS=1 python -m ai.verify_energy_replay \
  --dataset data/energy/raw/energydata_complete.csv \
  --experiment artifacts/energy/appliances-hgb-bound-v1 \
  --output artifacts/energy/replay-bound-v1 --full-dataset --inject-invalid
```

The verifier uses the **actual producer and consumer CLI commands**, creates and
deletes a unique Kafka topic, saves logs/archives/report, and compares every held-out
prediction with offline results. Without `--full-dataset`, it replays the held-out
period plus six earlier observations needed for warm-up. `--inject-invalid` checks
bad-message isolation. Output directories must be new. A final forecast beyond
the dataset has no matching actual and is excluded from evaluation. Full replay
also produces in-sample historical forecasts; only held-out targets count in metrics.

### Remaining scope and limitations

Energy feature vectors are ready for future Isolation Forest/Autoencoder adapters;
energy anomaly training/calibration is deferred as agreed. Existing IoT detectors
still run in the IoT scenario. No database, API or dashboard is introduced.

Kafka auto-commit, in-memory feature history and buffered writes remain: a crash,
consumer rebalance or restart can lose history/buffered records or produce duplicates.
Use one consumer writer and an isolated output directory for this prototype.
The two archives are not transactional. The model was trained on one house and
has no demonstrated generalization to new buildings or physical meters.
Missing auxiliary values are handled, but missing energy is not imputed.
All existing outputs are kept; no automatic dataset/model migration occurs.

### Model/source compatibility (review follow-up)

New model artifacts contain `allowed_sources`, derived **only from sources present
in the training partition** and included in the model version hash. The binding
matches building ID, source ID, source type, energy scope, interval length,
timestamp reference, timezone label and whether the timestamp has an offset.
The standard Appliances artifact allows only `appliances-house-1` / `uci-appliances`
with the original dataset semantics. Sharing `energy.scope=appliances` is not enough.

The consumer checks compatibility before updating feature history, writing facts or
predicting. Incompatible messages are written to `rejected.jsonl` with a reason;
processing continues. Source identifiers are a compatibility contract, not device
authentication: a sender can still spoof labels unless a future ingestion layer
verifies them. Another house/meter needs an explicitly validated model/adaptation;
there is no wildcard source override.

Artifacts produced before this change have no source binding and are refused with
an actionable error. Retrain into a **new experiment directory** using the commands
above; do not edit the old artifact or assume unrestricted compatibility. Feature
engineering and estimator parameters have not changed, but model version changes
because the binding is now part of the configuration.

### Automated checks

`.github/workflows/tests.yml` runs on pushes, pull requests and manual dispatch:

- **Unit tests:** Python 3.13 on Ubuntu 24.04, no broker and no dataset download.
- **Kafka smoke tests:** separate job, Kafka 3.9.0 started using Compose, bounded
  readiness wait, both IoT and Energy broker tests, then broker cleanup.

CI installs `requirements-ci.txt` (a constrained test dependency subset) and
PyTorch 2.11.0 CPU wheels. The local equivalents using the existing environment are:

```sh
OMP_NUM_THREADS=1 python tests/run_suite.py --suite unit
OMP_NUM_THREADS=1 python tests/run_suite.py --suite kafka
OMP_NUM_THREADS=1 python tests/run_suite.py --suite all
```

The runner explicitly selects the suites and enables broker tests for `kafka`/`all`;
skipped tests or an empty selection fail rather than silently passing.

### Recovery limitations

See [recovery and delivery limits](docs/recovery-and-delivery.md) for exact failure
windows and a safe manual replay procedure. Offsets, feature history and Parquet
are not checkpointed together: crashes can cause **missing records, duplicates,
partial files and differences between measurement and forecast archives**. Normal
shutdown flushing does not establish crash-safe delivery.

## Stage 3: offline forecasting benchmark

The benchmark is separate from Energy Kafka inference and the IoT scenario.
Its [frozen protocol](docs/forecast-benchmark/protocol.md) compares persistence,
exact previous-day Seasonal Naive, Random Forest and HistGradientBoosting on
common chronological targets. Hyperparameters use validation only. The test
window was already inspected in Stage 2 and is **not an unseen holdout**.

```bash
OMP_NUM_THREADS=1 python -m benchmark.run \
  --dataset data/energy/raw/energydata_complete.csv \
  --output docs/forecast-benchmark/results \
  --models-output artifacts/forecast-benchmark/v1
python tests/run_suite.py --suite all
```

The dataset must match the protocol SHA-256. Output directories must not exist;
use new output paths to repeat an experiment. Dependencies are pinned in
`requirements.txt`; CI uses the corresponding test subset. The runner saves
validation decisions before test inference, fitted models under ignored
`artifacts/`, and all test predictions, metrics, timings, versions, configuration,
checksums, PNG/SVG figures and a Markdown report under the selected output path.
The report and tables from the full dataset are in
[docs/forecast-benchmark/results/report.md](docs/forecast-benchmark/results/report.md).
Prediction timings vary across machines. High-load observations are not labelled
as anomalies. Integration of the selected model requires a separate change.
