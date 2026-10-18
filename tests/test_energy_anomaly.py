import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from anomaly_helpers import fixture, small_config
from energy_helpers import energy_records, write_csv
from anomaly.features import collect, NAMES
from anomaly.artifacts import Bundle
from anomaly.residual import StreamDetector, score_batch
from anomaly.inject import inject, train_statistics
from anomaly.evaluate import metrics
from anomaly.calibrate import calibrate
from processing.message_schema import InvalidMessage


class AnomalyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.limit = threadpool_limits(1)
        cls.records, cls.frame, cls.x, cls.rx, cls.bundle, cls.config = fixture()

    @classmethod
    def tearDownClass(cls):
        cls.limit.restore_original_limits()

    def test_readiness_and_previous_target_seasonal_alignment(self):
        f, x, rx = self.frame, self.x, self.rx
        self.assertEqual(int((~f.feature_ready).sum()), 6)
        self.assertEqual(int((~f.residual_ready).sum()), 144)
        self.assertEqual(rx[144, -1], self.records[0]['energy']['value'])
        self.assertEqual(rx[144, 0], self.records[143]['energy']['value'])
        self.assertEqual(f.forecast_origin.iloc[144], self.records[143]['timestamp'])

    def test_current_actual_cannot_enter_its_forecast_and_future_cannot_change_scores(self):
        modified = copy.deepcopy(self.records)
        modified[300]['energy']['value'] = 9999
        f, x, rx = collect(modified)
        np.testing.assert_array_equal(rx[:301], self.rx[:301])
        old = score_batch(self.bundle, self.frame, self.x, self.rx)
        new = score_batch(self.bundle, f, x, rx)
        pd.testing.assert_frame_equal(old.iloc[:300], new.iloc[:300])
        self.assertEqual(old.prediction_wh.iloc[300], new.prediction_wh.iloc[300])
        self.assertNotEqual(old.residual.iloc[300], new.residual.iloc[300])
        self.assertNotEqual(rx[301, 0], self.rx[301, 0])
        # Explicit streaming check: forecast was materialized before input 300.
        a, b = StreamDetector(self.bundle), StreamDetector(self.bundle)
        for row in self.records[:300]:
            a.process(row); b.process(row)
        ra, rb = a.process(self.records[300]), b.process(modified[300])
        self.assertEqual(ra['prediction_wh'], rb['prediction_wh'])
        self.assertNotEqual(ra['residual'], rb['residual'])

    def test_offline_streaming_save_load_parity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bundle.joblib'
            self.bundle.save(path)
            loaded = Bundle.load(path)
        stream = StreamDetector(loaded)
        actual = pd.DataFrame([stream.process(row) for row in self.records])
        expected = score_batch(loaded, self.frame, self.x, self.rx)
        for name in [*NAMES, 'prediction_wh', 'signed_residual_wh']:
            np.testing.assert_allclose(actual[name], expected[name], rtol=1e-5, atol=1e-6, equal_nan=True)
        for name in NAMES:
            ready = actual[name].notna()
            np.testing.assert_array_equal(actual.loc[ready, name + '_flag'], expected.loc[ready, name] > loaded.thresholds['0.99'][name])

    def test_train_only_preprocessing_and_threshold_isolation(self):
        mask = slice(144, 240)
        np.testing.assert_allclose(self.bundle.ae_preprocessing.named_steps['imputer'].statistics_, np.nanmedian(self.x[mask], axis=0))
        np.testing.assert_allclose(self.bundle.rf.named_steps['imputer'].statistics_, np.nanmedian(self.rx[mask], axis=0))
        scores = score_batch(self.bundle, self.frame, self.x, self.rx)
        before = calibrate(scores.iloc[240:280], self.config['quantiles'])
        scores.loc[280:, list(NAMES)] = 1e10
        self.assertEqual(before, calibrate(scores.iloc[240:280], self.config['quantiles']))
        # Refit with poisoned later partitions: selected train produces same models.
        from anomaly.train import fit_models
        changed_x, changed_rx = self.x.copy(), self.rx.copy()
        changed_x[240:] = 9999; changed_rx[240:] = 9999
        train = (np.arange(len(scores)) >= 144) & (np.arange(len(scores)) < 240)
        repeated = fit_models(self.frame, changed_x, changed_rx, train, self.records[0], self.config)
        for name, values in repeated.current_scores(self.x[300:]).items():
            np.testing.assert_array_equal(values, self.bundle.current_scores(self.x[300:])[name])
        np.testing.assert_array_equal(repeated.forecast(self.rx[300:]), self.bundle.forecast(self.rx[300:]))

    def test_source_schema_gap_duplicate_and_restart(self):
        detector = StreamDetector(self.bundle)
        for row in self.records[:150]:
            detector.process(row)
        other = copy.deepcopy(self.records[150]); other['source_id'] = 'unknown'
        with self.assertRaises(InvalidMessage):
            detector.process(other)
        with self.assertRaises(InvalidMessage):
            detector.process(self.records[149])
        result = detector.process(self.records[151])
        self.assertTrue(result['gap_detected']); self.assertIsNone(result['residual'])
        self.assertFalse(result['feature_ready'])
        fresh = StreamDetector(self.bundle).process(self.records[151])
        self.assertFalse(fresh['residual_ready'])
        tampered = copy.deepcopy(self.bundle)
        tampered.metadata['rf_feature_names'] = tampered.metadata['feature_names']
        with self.assertRaises(ValueError):
            tampered.validate()

    def test_injection_determinism_boundaries_and_original_preservation(self):
        records = list(energy_records(900))
        original = copy.deepcopy(records)
        stats = {'iqr_wh': 20., 'low_hours': list(range(24))}
        a, labels, events, summary = inject(records, 144, self.config['injection'], stats, 'spike', 2, 201)
        b, labels2, events2, _ = inject(records, 144, self.config['injection'], stats, 'spike', 2, 201)
        self.assertEqual(records, original); self.assertEqual(a, b); self.assertEqual(events, events2)
        np.testing.assert_array_equal(labels, labels2)
        self.assertEqual(a[:144], records[:144]); self.assertLessEqual(summary['labeled_points'], int(.02 * 756))
        self.assertTrue(events)
        ordered = sorted(events, key=lambda e: e['start'])
        for earlier, later in zip(ordered, ordered[1:]):
            self.assertGreater(later['start'] - earlier['end'], 144)
        for e in events:
            self.assertGreaterEqual(e['start'], 0); self.assertLess(e['end'], len(labels))
            self.assertTrue(labels[e['start']:e['end'] + 1].all())

    def test_event_one_to_one_strict_window_and_recovery_tail(self):
        times = pd.date_range('2016-01-01', periods=10, freq='10min')
        events = [{'event_id': 0, 'type': 'spike', 'severity': 0, 'start': 2, 'end': 3},
                  {'event_id': 1, 'type': 'drop', 'severity': 0, 'start': 5, 'end': 6}]
        labels = [False, False, True, True, False, True, True, False, False, False]
        # One continuous alarm covering two events can match only one event.
        r, outcomes = metrics([False, False, False, True, True, True, True, True, False, False], labels, times, events)
        self.assertEqual(r['matched_events'], 1); self.assertEqual(r['missed_events'], 1)
        self.assertEqual(outcomes[0]['delay_minutes'], 10)
        self.assertIsNone(outcomes[1]['delay_minutes']); self.assertEqual(r['post_event_alarms'], 2)
        r, _ = metrics([False] * 7 + [True, False, False], labels, times, events)
        self.assertEqual(r['matched_events'], 0); self.assertIsNone(r['delay_median_minutes'])

    def test_runner_complete_small_fixture(self):
        from anomaly.run_experiment import run
        from producer.appliances_dataset import dataset_sha256
        config = small_config()
        records = list(energy_records(400))
        for key, index in [('train_start', 144), ('calibration_start', 220), ('validation_start', 280), ('test_start', 340), ('test_end', 399)]:
            config[key] = records[index]['timestamp']
        config['injection'].update(fraction=.1, minimum_gap=5, validation_seeds=[101], test_seeds=[201], severity_levels=[0],
                                   types={'spike': {'duration': [1, 1], 'strength': [2., 4., 6.]}})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); dataset = root / 'dataset.csv'; write_csv(dataset, 400)
            config['dataset_sha256'] = dataset_sha256(dataset)
            protocol = root / 'config.json'; protocol.write_text(json.dumps(config))
            run(dataset, root / 'results', root / 'models', protocol)
            self.assertTrue((root / 'results/report.md').exists())
            self.assertEqual(len(pd.read_parquet(root / 'results/scores/test-clean.parquet')), 60)
            selection = json.loads((root / 'results/selection.json').read_text())
            self.assertFalse(selection['uses_test'])
            self.assertEqual(len(list((root / 'results/plots').glob('*.png'))), 4)
            with self.assertRaises(ValueError):
                run(dataset, root / 'results', root / 'models', protocol)
