import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import torch

from ai.anomaly_detector import AnomalyDetector
from ai.autoencoder_detector import AutoencoderAnomalyDetector
from config import Settings
from consumer.iot_consumer import ProcessingPipeline
from processing.message_schema import InvalidMessage, PROCESSED_FIELDS, decode_record
from producer.iot_producer import generate_records
from storage.csv_storage import CSVStorage
from storage.parquet_storage import ParquetStorage


def records(count=12):
    return list(generate_records(count, seed=7, start=datetime(2026, 1, 1, tzinfo=timezone.utc)))


class ContractTests(unittest.TestCase):
    def test_reproducible_generator_matches_contract(self):
        self.assertEqual(records(), records())
        for record in records():
            self.assertEqual(decode_record(json.dumps(record).encode()), record)

    def test_bad_messages_are_rejected(self):
        valid = records(1)[0]
        examples = [b'{broken', b'\xff', b'[]', b'null']
        for field, value in [('temperature', float('nan')), ('humidity', 'inf'),
                             ('light', None), ('voltage', True), ('sensor_id', 1.5),
                             ('timestamp', '2026-01-01'), ('timestamp', 'invalid')]:
            examples.append(json.dumps({**valid, field: value}).encode())
        missing = dict(valid)
        del missing['light']
        examples.append(json.dumps(missing).encode())
        for payload in examples:
            with self.subTest(payload=payload), self.assertRaises(InvalidMessage):
                decode_record(payload)

    def test_numeric_strings_are_normalized(self):
        record = records(1)[0]
        record['temperature'] = '24.5'
        self.assertEqual(decode_record(json.dumps(record).encode())['temperature'], 24.5)


class StorageTests(unittest.TestCase):
    def test_legacy_csv_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.csv'
            original = b'sensor_id,timestamp,temperature\n1,old,23\n'
            path.write_bytes(original)
            with self.assertRaisesRegex(ValueError, 'PIPELINE_OUTPUT_DIR'):
                CSVStorage(path)
            self.assertEqual(path.read_bytes(), original)

    def test_parquet_survives_reinitialization(self):
        with tempfile.TemporaryDirectory() as directory:
            for record in records(2):
                storage = ParquetStorage(directory, batch_size=1)
                storage.save(record)
            files = list(Path(directory).rglob('*.parquet'))
            self.assertEqual(len(files), 2)
            frame = pd.concat([pd.read_parquet(path) for path in files])
            self.assertEqual(sorted(frame.timestamp), sorted(row['timestamp'] for row in records(2)))

    def test_empty_csv_gets_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.csv'
            path.touch()
            CSVStorage(path)
            with path.open() as file:
                self.assertEqual(next(csv.reader(file)), list(PROCESSED_FIELDS))


class PipelineSmokeTests(unittest.TestCase):
    def test_models_rejections_final_flush_and_storage_parity(self):
        # Small windows exercise actual fit/inference, rather than only warm-up.
        torch.manual_seed(42)
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(output_dir=Path(directory), parquet_batch_size=5)
            forest = AnomalyDetector(window_size=6, min_train_size=6)
            encoder = AutoencoderAnomalyDetector(window_size=6, retrain_interval=6, epochs=2)
            pipeline = ProcessingPipeline(settings, forest, encoder)
            metadata = {'topic': 'test', 'partition': 0, 'offset': 5}
            for index, record in enumerate(records()):
                if index == 5:
                    self.assertFalse(pipeline.process(b'{bad JSON', metadata))
                    self.assertFalse(pipeline.process(None, metadata))
                self.assertTrue(pipeline.process(json.dumps(record).encode(), metadata))
            pipeline.close()
            self.assertTrue(forest.is_trained)
            self.assertTrue(encoder.is_trained)
            self.assertIsNotNone(encoder.threshold)
            csv_frame = pd.read_csv(Path(directory) / 'iot_sensor_data.csv')
            files = list((Path(directory) / 'parquet').rglob('*.parquet'))
            self.assertEqual(len(files), 3)  # Includes final two-record flush.
            parquet_frame = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
            self.assertEqual(len(csv_frame), 12)
            self.assertEqual(list(csv_frame.columns), list(parquet_frame.columns))
            pd.testing.assert_frame_equal(
                csv_frame.sort_values('timestamp').reset_index(drop=True),
                parquet_frame.sort_values('timestamp').reset_index(drop=True), check_dtype=False)
            rejected = [json.loads(line) for line in (Path(directory) / 'rejected.jsonl').read_text().splitlines()]
            self.assertEqual(len(rejected), 2)
            self.assertEqual(rejected[0]['offset'], 5)
            self.assertIn('Invalid JSON', rejected[0]['reason'])


if __name__ == '__main__':
    unittest.main()
