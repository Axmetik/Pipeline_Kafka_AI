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
