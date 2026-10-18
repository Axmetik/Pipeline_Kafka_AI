"""Causality, selection isolation and deterministic benchmark contract tests."""
import copy
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from energy_helpers import energy_records, write_csv
from benchmark.config import load_protocol
from benchmark.features import BenchmarkFeatures, BENCHMARK_FEATURES, build_samples, split_samples
from benchmark.models import make_model, predict
from benchmark.selection import tune_on_validation, refit_selected
from benchmark.evaluation import evaluate_predictions, peak_threshold


class BenchmarkTests(unittest.TestCase):
    def test_seasonal_uses_target_minus_day_not_origin_minus_day(self):
        rows = list(energy_records(146))
        processor = BenchmarkFeatures()
        for raw in rows[:143]:
            self.assertIsNone(processor.process(raw)['features'])
        first = processor.process(rows[143])
        self.assertEqual(first['features']['seasonal_energy_wh'], 1)
        self.assertEqual(first['forecast_target_timestamp'], rows[144]['timestamp'])
        self.assertEqual(processor.process(rows[144])['features']['seasonal_energy_wh'], 2)

    def test_gap_requires_full_new_day_and_sources_are_isolated(self):
        rows = list(energy_records(400))
        processor = BenchmarkFeatures()
        for raw in rows[:150]:
            processor.process(raw)
        for raw in rows[151:294]:
            self.assertIsNone(processor.process(raw)['features'])
        self.assertIsNotNone(processor.process(rows[294])['features'])
        other = copy.deepcopy(rows[295]); other['source_id'] = 'other'
        self.assertIsNone(processor.process(other)['features'])
        self.assertIsNotNone(processor.process(rows[295])['features'])

    def test_future_values_cannot_change_earlier_features(self):
        rows = list(energy_records(350))
        changed = copy.deepcopy(rows)
        for row in changed[250:]:
            row['energy']['value'] = 9999
            row['environment']['temperature_c'] = -20
        before, _ = build_samples(rows)
        after, _ = build_samples(changed)
        # Include the target at index 250: its actual changes but its origin features cannot.
        mask = before.forecast_target_timestamp <= rows[250]['timestamp']
        pd.testing.assert_frame_equal(before.loc[mask, BENCHMARK_FEATURES], after.loc[mask, BENCHMARK_FEATURES])
        self.assertNotEqual(before.loc[mask, 'actual_energy_wh'].iloc[-1], after.loc[mask, 'actual_energy_wh'].iloc[-1])

    def fixture(self):
        rows = list(energy_records(350))
        frame, _ = build_samples(rows)
        protocol, _ = load_protocol()
        protocol.update(validation_start=rows[220]['timestamp'], test_start=rows[280]['timestamp'], test_end=rows[-1]['timestamp'])
        protocol['rf_grid'] = {'n_estimators': [5], 'max_depth': [2], 'min_samples_leaf': [1, 3]}
        protocol['hgb_grid'] = {'max_iter': [3], 'max_leaf_nodes': [3], 'learning_rate': [.1], 'l2_regularization': [0.]}
        return split_samples(frame, protocol), protocol

    def test_splits_are_disjoint_and_use_target_boundary(self):
        parts, protocol = self.fixture()
        self.assertEqual(parts['validation'].forecast_target_timestamp.iloc[0], protocol['validation_start'])
        self.assertLess(parts['validation'].forecast_origin.iloc[0], protocol['validation_start'])
        for a, b in [('train', 'validation'), ('validation', 'test'), ('train', 'test')]:
            self.assertFalse(set(parts[a].index) & set(parts[b].index))
            self.assertLess(parts[a].forecast_target_timestamp.max(), parts[b].forecast_target_timestamp.min())

    def test_imputer_learns_only_fit_rows_in_both_models(self):
        x = np.tile(np.arange(21, dtype=float), (40, 1))
        x[:, 0] = np.arange(40); x[:20, 0] = np.nan
        y = np.arange(40)
        for name, params in [('random_forest', {'n_estimators': 3}), ('hist_gradient_boosting', {'max_iter': 2})]:
            with threadpool_limits(1):
                model = make_model(name, params)
                model.fit(x, y)
                statistics = model.named_steps['imputer'].statistics_.copy()
                self.assertEqual(statistics[0], 29.5)
                predict(model, np.full((5, 21), 10000.))
                predict(model, np.full((5, 21), np.nan))
            np.testing.assert_array_equal(model.named_steps['imputer'].statistics_, statistics)

    def test_selection_and_refit_reproducible_and_test_independent(self):
        parts, protocol = self.fixture()
        snapshot = parts['test'].copy(deep=True)
        with threadpool_limits(1):
            first, trials = tune_on_validation(parts['train'], parts['validation'], protocol)
            # Drastically changing test cannot affect selection: it is never passed in.
            parts['test'].loc[:, 'actual_energy_wh'] = -9999
            second, again = tune_on_validation(parts['train'], parts['validation'], protocol)
            self.assertEqual(first, second); self.assertEqual(trials, again)
            combined = pd.concat([parts['train'], parts['validation']])
            models = refit_selected(combined, first, protocol['seed'])
            repeated = refit_selected(combined, first, protocol['seed'])
            x = snapshot[BENCHMARK_FEATURES].to_numpy(float)
            forecasts = {name: predict(model, x) for name, model in models.items()}
            for name, values in forecasts.items():
                np.testing.assert_array_equal(values, predict(repeated[name], x))
                self.assertEqual(len(values), len(snapshot))
            for name in ('random_forest', 'hist_gradient_boosting'):
                np.testing.assert_allclose(models[name].named_steps['imputer'].statistics_, np.nanmedian(combined[BENCHMARK_FEATURES].to_numpy(float), axis=0))
        overall, peaks = evaluate_predictions(snapshot.actual_energy_wh, forecasts, peak_threshold(parts['train'].actual_energy_wh))
        self.assertEqual({row['count'] for row in overall.values()}, {len(snapshot)})
        self.assertEqual(len({row['count'] for row in peaks.values()}), 1)
        self.assertFalse(first['selection_uses_test'])

    def test_runner_saves_selection_predictions_and_figures(self):
        from benchmark.run import run
        from producer.appliances_dataset import dataset_sha256
        _, protocol = self.fixture()
        protocol['timing'] = {'sample_count': 3, 'repeats': 1, 'warmup_calls': 1}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / 'data.csv'
            write_csv(dataset, count=350)
            protocol['dataset_sha256'] = dataset_sha256(dataset)
            output = root / 'results'
            with patch('benchmark.run.load_protocol', return_value=(protocol, 'fixture')):
                run(dataset, output, root / 'models')
                with self.assertRaises(ValueError):
                    run(dataset, output, root / 'models')
            predictions = pd.read_csv(output / 'test_predictions.csv')
            self.assertEqual(len(predictions), 70)
            for name in ('persistence', 'seasonal_naive', 'random_forest', 'hist_gradient_boosting'):
                self.assertFalse(predictions[name].isna().any())
            self.assertFalse(json.loads((output / 'selection.json').read_text())['selection_uses_test'])
            self.assertEqual(len(list((output / 'plots').glob('*.png'))), 4)
            self.assertIn('not an unseen independent holdout', (output / 'report.md').read_text())

    def test_peak_threshold_and_signed_error(self):
        threshold = peak_threshold([0, 10, 20, 30, 40])
        self.assertEqual(threshold, 36)
        _, peaks = evaluate_predictions([36, 40, 100], {'persistence': [30, 30, 90]}, threshold)
        self.assertEqual(peaks['persistence']['count'], 2)
        self.assertEqual(peaks['persistence']['mean_signed_error_wh'], -10)
        self.assertEqual(peaks['persistence']['underprediction_fraction'], 1)
        _, empty = evaluate_predictions([0], {'persistence': [0]}, threshold)
        self.assertIsNone(empty['persistence']['mae_wh'])
        self.assertIsNone(empty['persistence']['mae_wh_improvement_pct'])


if __name__ == '__main__':
    unittest.main()
