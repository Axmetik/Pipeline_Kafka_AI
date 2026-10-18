"""A common prediction API and explicit train-fitted preprocessing pipelines."""
import numpy as np
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from benchmark.features import BENCHMARK_FEATURES

MODEL_ORDER = ['persistence', 'seasonal_naive', 'random_forest', 'hist_gradient_boosting']


class Baseline:
    def __init__(self, name):
        self.name = name
        self.column = BENCHMARK_FEATURES.index('energy_wh' if name == 'persistence' else 'seasonal_energy_wh')

    def predict(self, features):
        return np.asarray(features)[:, self.column].copy()


def make_model(name, params=None, seed=42):
    params = params or {}
    if name in ('persistence', 'seasonal_naive'):
        return Baseline(name)
    if name == 'random_forest':
        estimator = RandomForestRegressor(random_state=seed, n_jobs=1, **params)
    elif name == 'hist_gradient_boosting':
        estimator = HistGradientBoostingRegressor(random_state=seed, early_stopping=False,
                                                  loss='squared_error', **params)
    else:
        raise ValueError(f'Unknown model: {name}')
    return Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
                     ('regressor', estimator)])


def predict(model, features):
    return np.maximum(0.0, model.predict(features))
