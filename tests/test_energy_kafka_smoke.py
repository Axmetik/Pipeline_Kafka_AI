import os
import tempfile
import unittest
from pathlib import Path
from energy_helpers import write_csv
from ai.train_energy_forecaster import train_experiment
from ai.verify_energy_replay import verify_replay


@unittest.skipUnless(os.getenv('RUN_KAFKA_SMOKE') == '1', 'Set RUN_KAFKA_SMOKE=1 with a running Kafka broker')
class EnergyKafkaSmokeTests(unittest.TestCase):
    def test_real_producer_consumer_and_forecast_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / 'appliances.csv'
            write_csv(dataset, count=120)
            offline = train_experiment(dataset, root / 'run', max_iter=5)
            report = verify_replay(dataset, root / 'run', root / 'replay', inject_invalid=True)
            self.assertEqual(report['matched_test_predictions'], offline['test_samples'])
            self.assertTrue(report['offline_stream_predictions_equal'])
            self.assertEqual(report['rejected'], 1)
            self.assertEqual(report['ml'], offline['ml'])
            self.assertEqual(report['persistence'], offline['persistence'])
