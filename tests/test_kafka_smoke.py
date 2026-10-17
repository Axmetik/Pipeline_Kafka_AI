"""Opt-in broker test: RUN_KAFKA_SMOKE=1 python -m unittest discover -s tests -p test_kafka_smoke.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import pandas as pd
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from config import Settings
from producer.iot_producer import generate_records


@unittest.skipUnless(os.getenv('RUN_KAFKA_SMOKE') == '1', 'Set RUN_KAFKA_SMOKE=1 with a running Kafka broker')
class KafkaSmokeTests(unittest.TestCase):
    def test_transport_consumer_rejection_and_storage(self):
        settings = Settings.from_env()
        topic = f'pipeline-smoke-{uuid4().hex}'
        admin = KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
        producer = None
        created = False
        try:
            admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
            created = True
            producer = KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
            for index, record in enumerate(generate_records(12)):
                if index == 5:
                    producer.send(topic, b'{invalid').get(timeout=30)
                producer.send(topic, json.dumps(record).encode()).get(timeout=30)
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [sys.executable, '-m', 'consumer.iot_consumer', '--max-messages', '13', '--idle-timeout-ms', '15000'],
                    cwd=Path(__file__).resolve().parents[1],
                    env={**os.environ, 'KAFKA_TOPIC': topic, 'KAFKA_GROUP_ID': topic,
                         'PIPELINE_OUTPUT_DIR': directory, 'PARQUET_BATCH_SIZE': '5'},
                    capture_output=True, text=True, timeout=90,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('accepted=12, rejected=1', result.stdout)
                csv_frame = pd.read_csv(Path(directory) / 'iot_sensor_data.csv')
                parquet_frame = pd.concat([pd.read_parquet(path) for path in Path(directory).rglob('*.parquet')])
                self.assertEqual(len(csv_frame), 12)
                pd.testing.assert_frame_equal(
                    csv_frame.sort_values('timestamp').reset_index(drop=True),
                    parquet_frame.sort_values('timestamp').reset_index(drop=True), check_dtype=False)
        finally:
            if producer is not None:
                producer.close(timeout=30)
            if created:
                admin.delete_topics([topic])
            admin.close()
