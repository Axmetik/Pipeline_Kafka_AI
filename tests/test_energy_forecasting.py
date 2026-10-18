import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from energy_helpers import write_csv, energy_records
from ai.train_energy_forecaster import train_experiment, build_samples, metrics
from ai.energy_forecaster import EnergyForecaster
from consumer.energy_consumer import EnergyPipeline
from config import EnergySettings
from producer.appliances_dataset import iter_appliances


class EnergyForecastTests(unittest.TestCase):
    def test_metrics_known_values(self):
        result = metrics([10, 20], [12, 16])
        self.assertEqual(result['mae_wh'], 3)
        self.assertAlmostEqual(result['rmse_wh'], np.sqrt(10))

    def test_training_loading_replay_parity_and_separate_archives(self):
        with tempfile.TemporaryDirectory() as directory, threadpool_limits(limits=1):
            root = Path(directory)
            csv = root / 'dataset.csv'
            write_csv(csv)
            report = train_experiment(csv, root / 'run', max_iter=5)
            model = EnergyForecaster.load(root / 'run/model.joblib')
            model.save(root / 'copy.joblib')
            loaded = EnergyForecaster.load(root / 'copy.joblib')
            frame, _ = build_samples(iter_appliances(csv))
            np.testing.assert_array_equal(model.predict_many(frame), loaded.predict_many(frame))
            pipeline = EnergyPipeline(EnergySettings(output_dir=root / 'stream', parquet_batch_size=5), loaded)
            for index, record in enumerate(iter_appliances(csv)):
                if index == 10:
                    self.assertFalse(pipeline.process(b'{bad'))
                    # Duplicate measurement does not change history or enter archives.
                    self.assertFalse(pipeline.process(json.dumps(previous).encode()))
                self.assertTrue(pipeline.process(json.dumps(record).encode()))
                previous = record
            pipeline.close()
            measurements = pd.concat([pd.read_parquet(p) for p in (root / 'stream/measurements').rglob('*.parquet')])
            forecasts = pd.concat([pd.read_parquet(p) for p in (root / 'stream/forecasts').rglob('*.parquet')])
            self.assertEqual(len(measurements), 100)
            self.assertEqual(len(forecasts), 100)
            self.assertNotIn('predicted_energy_wh', measurements.columns)
            self.assertNotIn('actual_energy_wh', forecasts.columns)
            self.assertEqual(forecasts.predicted_energy_wh.isna().sum(), 6)
            self.assertTrue(measurements.timezone.isna().all())
            self.assertTrue(forecasts.forecast_generated_at_utc.str.endswith('+00:00').all())
            expected = pd.read_parquet(root / 'run/test_predictions.parquet')
            joined = expected.merge(forecasts, on=['building_id', 'source_id', 'forecast_origin', 'forecast_target_timestamp'], suffixes=('_offline', '_stream'), validate='one_to_one')
            self.assertEqual(len(joined), report['test_samples'])
            np.testing.assert_allclose(joined.predicted_energy_wh_offline, joined.predicted_energy_wh_stream)
            np.testing.assert_allclose(joined.baseline_energy_wh_offline, joined.baseline_energy_wh_stream)
            self.assertEqual(report['persistence']['mae_wh'], 1)
            self.assertTrue((root / 'run/metadata.json').exists())
            with self.assertRaises(ValueError):
                train_experiment(csv, root / 'run', max_iter=5)

    def test_test_data_does_not_affect_fit(self):
        with tempfile.TemporaryDirectory() as directory, threadpool_limits(limits=1):
            root = Path(directory)
            csv = root / 'original.csv'
            write_csv(csv)
            train_experiment(csv, root / 'first', max_iter=5)
            first = EnergyForecaster.load(root / 'first/model.joblib')
            modified = pd.read_csv(csv)
            boundary = first.metadata['test_target_start']
            modified.loc[modified.date >= boundary, 'Appliances'] = 100000
            changed = root / 'changed.csv'
            modified.to_csv(changed, index=False)
            train_experiment(changed, root / 'second', max_iter=5)
            second = EnergyForecaster.load(root / 'second/model.joblib')
            frame, _ = build_samples(iter_appliances(csv))
            np.testing.assert_array_equal(first.predict_many(frame), second.predict_many(frame))

    def test_source_binding_blocks_other_buildings_and_semantics_before_history(self):
        with tempfile.TemporaryDirectory() as directory, threadpool_limits(limits=1):
            root = Path(directory)
            csv = root / 'input.csv'
            write_csv(csv)
            train_experiment(csv, root / 'run', max_iter=5)
            model = EnergyForecaster.load(root / 'run/model.joblib')
            record = next(iter_appliances(csv))
            from copy import deepcopy
            from unittest.mock import patch
            pipeline = EnergyPipeline(EnergySettings(output_dir=root / 'stream'), model)
            cases = []
            for key, value in [('building_id', 'another-house'), ('source_id', 'another-source'),
                               ('source_type', 'smart_meter'), ('timestamp_reference', 'interval_end'),
                               ('interval_seconds', 300), ('timestamp', record['timestamp'] + '+00:00')]:
                changed = deepcopy(record)
                changed[key] = value
                cases.append(changed)
            for changed in cases:
                with self.subTest(record=changed), patch.object(model, 'predict', side_effect=AssertionError('Must not predict')):
                    self.assertFalse(pipeline.process(json.dumps(changed).encode()))
            self.assertEqual(pipeline.processor.histories, {})
            self.assertEqual(pipeline.measurements.buffer, [])
            self.assertEqual(pipeline.forecasts.buffer, [])
            self.assertTrue(pipeline.process(json.dumps(record).encode()))
            pipeline.close()
            rejects = [json.loads(line) for line in (root / 'stream/rejected.jsonl').read_text().splitlines()]
            self.assertEqual(len(rejects), len(cases))
            self.assertTrue(all('allowed_sources' in item['reason'] for item in rejects))
            self.assertEqual(model.metadata['allowed_sources'][0]['building_id'], 'appliances-house-1')

    def test_unbound_legacy_artifact_fails_closed(self):
        import joblib
        with tempfile.TemporaryDirectory() as directory, threadpool_limits(limits=1):
            root = Path(directory)
            csv = root / 'input.csv'
            write_csv(csv)
            train_experiment(csv, root / 'run', max_iter=5)
            artifact = joblib.load(root / 'run/model.joblib')
            artifact['metadata'].pop('allowed_sources')
            joblib.dump(artifact, root / 'legacy.joblib')
            with self.assertRaisesRegex(ValueError, 'retrain'):
                EnergyForecaster.load(root / 'legacy.joblib')
