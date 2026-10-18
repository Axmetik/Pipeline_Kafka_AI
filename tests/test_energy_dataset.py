import tempfile
import unittest
from pathlib import Path
import pandas as pd
from energy_helpers import write_csv
from producer.appliances_dataset import iter_appliances, dataset_sha256


class EnergyDatasetTests(unittest.TestCase):
    def test_mapping_limits_and_random_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.csv'
            write_csv(path, 12)
            frame = pd.read_csv(path)
            frame['rv1'] = 123
            frame['rv2'] = 456
            frame.to_csv(path, index=False)
            rows = list(iter_appliances(path, start='2016-01-01T00:20:00', limit=3))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]['energy']['value'], 3)
            self.assertEqual(rows[0]['energy']['unit'], 'Wh')
            self.assertEqual(rows[0]['interval_seconds'], 600)
            self.assertIsNone(rows[0]['timezone'])
            self.assertNotIn('rv1', rows[0]['additional_parameters'])
            self.assertEqual(rows[0]['environment']['temperature_c'], 20)
            self.assertEqual(len(dataset_sha256(path)), 64)

    def test_bad_csv_order_is_not_silently_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.csv'
            write_csv(path, 12)
            frame = pd.read_csv(path).iloc[::-1]
            frame.to_csv(path, index=False)
            with self.assertRaises(ValueError):
                list(iter_appliances(path))
