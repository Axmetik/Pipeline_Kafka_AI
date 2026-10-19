"""Actual broker replay with a separate process, including injected history effects."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import numpy as np
import pandas as pd
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from threadpoolctl import threadpool_limits
from config import EnergySettings
from producer.appliances_dataset import iter_appliances
from anomaly.artifacts import Bundle
from anomaly.features import collect, NAMES
from anomaly.residual import score_batch
from anomaly.inject import inject


def verify(records, model_path, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Replay output must be new')
    output.mkdir(parents=True)
    bundle = Bundle.load(model_path)
    with threadpool_limits(1):
        f, x, rx = collect(records, bundle.validate_source)
        expected = score_batch(bundle, f, x, rx)
    topic = 'anomaly-test-' + uuid4().hex
    settings = EnergySettings.from_env()
    admin = KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    created = False
    try:
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)]); created = True
        producer = KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
        try:
            producer.send(topic, b'{bad-json').get(timeout=30)
            for row in records:
                producer.send(topic, json.dumps(row, allow_nan=False).encode(), key=row['source_id'].encode()).get(timeout=30)
            producer.flush()
        finally:
            producer.close(timeout=30)
        env = {**os.environ, 'OMP_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        with (output / 'consumer.log').open('w') as log:
            subprocess.run([sys.executable, '-m', 'consumer.energy_anomaly_consumer', '--model', str(Path(model_path).resolve()),
                            '--topic', topic, '--group', topic, '--output', str((output / 'stream').resolve()),
                            '--batch-size', '50', '--max-messages', str(len(records) + 1), '--idle-timeout-ms', '15000'],
                           cwd=Path(__file__).resolve().parents[1], env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    finally:
        if created:
            admin.delete_topics([topic])
        admin.close()
    paths = list((output / 'stream/anomalies').rglob('*.parquet'))
    actual = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    keys = ['building_id', 'source_id', 'measurement_timestamp', 'event_id']
    joined = expected.merge(actual, on=keys, suffixes=('_offline', '_stream'), validate='one_to_one')
    assert len(joined) == len(records) == len(actual)
    max_errors = {}
    for name in [*NAMES, 'prediction_wh', 'signed_residual_wh']:
        a, b = joined[name + '_offline'].to_numpy(float), joined[name + '_stream'].to_numpy(float)
        np.testing.assert_allclose(a, b, rtol=1e-5, atol=1e-6, equal_nan=True)
        max_errors[name] = float(np.nanmax(np.abs(a - b)))
    for name in NAMES:
        ready = joined[name + '_offline'].notna()
        flags = joined.loc[ready, name + '_offline'] > bundle.thresholds['0.99'][name]
        np.testing.assert_array_equal(flags, joined.loc[ready, name + '_flag'])
        assert joined.loc[~ready, name + '_flag'].isna().all()
    rejected = len((output / 'stream/rejected.jsonl').read_text().splitlines())
    assert rejected == 1
    report = {'accepted': len(actual), 'rejected': rejected, 'offline_stream_scores_match': True,
              'flags_match': True, 'max_absolute_score_difference': max_errors,
              'ready': {n: int(expected[n].notna().sum()) for n in NAMES},
              'model_version': bundle.metadata['model_version']}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((args.results / 'protocol.json').read_text())
    stats = json.loads((args.results / 'train_statistics.json').read_text())
    records = list(iter_appliances(args.dataset))
    start = next(i for i, r in enumerate(records) if r['timestamp'] >= config['test_start'])
    records = records[start - 144:start + 500]
    modified, _, events, summary = inject(records, 144, config['injection'], stats, 'spike', 2, 201)
    report = verify(modified, args.model, args.output)
    (args.output / 'injections.json').write_text(json.dumps({'events': events, 'summary': summary}, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
