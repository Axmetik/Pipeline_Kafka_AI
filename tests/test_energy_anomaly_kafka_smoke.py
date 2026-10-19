import copy
import os
import tempfile
import unittest
from pathlib import Path
from threadpoolctl import threadpool_limits
from anomaly_helpers import fixture
from anomaly.verify_kafka import verify


@unittest.skipUnless(os.getenv('RUN_KAFKA_SMOKE') == '1', 'Real Kafka required')
class AnomalyKafkaTests(unittest.TestCase):
    def test_injected_replay_matches_offline_scores_flags_and_parquet(self):
        with threadpool_limits(1), tempfile.TemporaryDirectory() as temp:
            records, _, _, _, bundle, _ = fixture()
            changed = copy.deepcopy(records[:180])
            changed[150]['energy']['value'] += 500
            root = Path(temp); model = root / 'bundle.joblib'; bundle.save(model)
            report = verify(changed, model, root / 'replay')
            self.assertEqual(report['accepted'], 180)
            self.assertEqual(report['rejected'], 1)
            self.assertEqual(report['ready']['residual'], 36)
            self.assertTrue(report['offline_stream_scores_match'])
            self.assertTrue(report['flags_match'])
