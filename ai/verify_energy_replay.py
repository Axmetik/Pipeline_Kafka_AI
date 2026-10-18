"""Replay through a temporary Kafka topic and compare held-out results with offline predictions."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic

from ai.train_energy_forecaster import metrics
from config import EnergySettings
from producer.appliances_dataset import dataset_sha256, iter_appliances


def read_archive(path):
    files = list(Path(path).rglob('*.parquet'))
    if not files:
        raise ValueError(f"Empty archive: {path}")
    return pd.concat([pd.read_parquet(file) for file in files], ignore_index=True)


def verify_replay(dataset, experiment, output, full_dataset=False, inject_invalid=False):
    dataset, experiment, output = Path(dataset).resolve(), Path(experiment).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Replay output already exists; choose a new directory")
    metadata = json.loads((experiment / 'metadata.json').read_text())
    if dataset_sha256(dataset) != metadata['dataset_sha256']:
        raise ValueError("Dataset checksum differs from training experiment")
    start = None if full_dataset else metadata['replay_start']
    end = None if full_dataset else metadata['replay_end']
    count = sum(1 for _ in iter_appliances(dataset, start=start, end=end))
    if count == 0:
        raise ValueError("No records to replay")
    output.mkdir(parents=True)
    settings = EnergySettings.from_env()
    topic = f'energy-replay-{uuid4().hex}'
    env = {**os.environ, 'ENERGY_KAFKA_TOPIC': topic, 'ENERGY_KAFKA_GROUP_ID': topic,
           'ENERGY_OUTPUT_DIR': str(output / 'stream'), 'ENERGY_PARQUET_BATCH_SIZE': '1000',
           'OMP_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    root = Path(__file__).resolve().parents[1]
    admin = KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    created = False
    try:
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
        created = True
        if inject_invalid:
            producer = KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
            try:
                producer.send(topic, b'{invalid JSON').get(timeout=30)
            finally:
                producer.close(timeout=30)
        command = [sys.executable, '-m', 'producer.energy_producer', '--dataset', str(dataset), '--sleep', '0']
        if start:
            command += ['--start', start, '--end', end]
        with (output / 'producer.log').open('w') as log:
            subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        with (output / 'consumer.log').open('w') as log:
            subprocess.run([sys.executable, '-m', 'consumer.energy_consumer', '--model', str(experiment / 'model.joblib'),
                            '--max-messages', str(count + int(inject_invalid)), '--idle-timeout-ms', '20000'],
                           cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    finally:
        if created:
            admin.delete_topics([topic])
        admin.close()
    measurements = read_archive(output / 'stream/measurements')
    forecasts = read_archive(output / 'stream/forecasts')
    if len(measurements) != count or len(forecasts) != count:
        raise AssertionError('Replay row count differs from sent records')
    reject_path = output / 'stream/rejected.jsonl'
    rejected = len(reject_path.read_text().splitlines()) if reject_path.exists() else 0
    if rejected != int(inject_invalid):
        raise AssertionError(f'Unexpected rejected count: {rejected}')
    expected = pd.read_parquet(experiment / 'test_predictions.parquet')
    keys = ['building_id', 'source_id', 'forecast_origin', 'forecast_target_timestamp']
    joined = expected.merge(forecasts, on=keys, suffixes=('_offline', '_stream'), validate='one_to_one')
    joined = joined.merge(measurements[['building_id', 'source_id', 'measurement_timestamp', 'actual_energy_wh']],
                          left_on=['building_id', 'source_id', 'forecast_target_timestamp'],
                          right_on=['building_id', 'source_id', 'measurement_timestamp'],
                          suffixes=('_offline', '_stream'), validate='one_to_one')
    if len(joined) != len(expected):
        raise AssertionError('Not all held-out targets were matched to a forecast and measurement')
    np.testing.assert_allclose(joined.predicted_energy_wh_offline, joined.predicted_energy_wh_stream, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(joined.baseline_energy_wh_offline, joined.baseline_energy_wh_stream, rtol=0, atol=0)
    np.testing.assert_allclose(joined.actual_energy_wh_offline, joined.actual_energy_wh_stream, rtol=0, atol=0)
    report = {'model_version': metadata['model_version'], 'dataset_sha256': metadata['dataset_sha256'],
              'replay_mode': 'full_dataset' if full_dataset else 'held_out_with_warmup',
              'sent_valid': count, 'accepted': len(measurements), 'rejected': rejected,
              'forecast_rows': len(forecasts), 'ready_forecasts': int((forecasts.status == 'ready').sum()),
              'matched_test_predictions': len(joined), 'offline_stream_predictions_equal': True,
              'ml': metrics(joined.actual_energy_wh_stream, joined.predicted_energy_wh_stream),
              'persistence': metrics(joined.actual_energy_wh_stream, joined.baseline_energy_wh_stream)}
    (output / 'replay_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--full-dataset', action='store_true')
    parser.add_argument('--inject-invalid', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify_replay(args.dataset, args.experiment, args.output, args.full_dataset, args.inject_invalid), indent=2))


if __name__ == '__main__':
    main()
