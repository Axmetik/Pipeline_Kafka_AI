"""Trusted local artifacts with exact feature and source compatibility checks."""
import joblib
import numpy as np
from ai.energy_forecaster import source_binding, valid_binding
from benchmark.features import BENCHMARK_FEATURES
from processing.energy_processor import FEATURE_NAMES
from processing.message_schema import InvalidMessage
from anomaly.features import FEATURE_VERSION, RF_FEATURE_VERSION
from anomaly.detectors import ae_score


class Bundle:
    def __init__(self, forest, ae_preprocessing, ae, rf, metadata, thresholds=None):
        self.forest, self.ae_preprocessing, self.ae, self.rf = forest, ae_preprocessing, ae, rf
        self.metadata, self.thresholds = metadata, thresholds or {}
        self.validate()

    def validate(self):
        m = self.metadata
        if (m.get('feature_names') != FEATURE_NAMES or m.get('feature_version') != FEATURE_VERSION
                or m.get('rf_feature_names') != BENCHMARK_FEATURES or m.get('rf_feature_version') != RF_FEATURE_VERSION
                or m.get('horizon_seconds') != 600):
            raise ValueError('Incompatible anomaly/forecast feature schema')
        if not m.get('allowed_sources') or not all(valid_binding(b) for b in m['allowed_sources']):
            raise ValueError('Missing valid source binding')
        if self.rf.n_features_in_ != 21 or self.forest.n_features_in_ != 20:
            raise ValueError('Incompatible fitted dimensions')

    def validate_source(self, record):
        if source_binding(record) not in self.metadata['allowed_sources']:
            raise InvalidMessage('Source incompatible with anomaly artifact')

    def current_scores(self, x):
        return {'isolation_forest': -self.forest.score_samples(x),
                'autoencoder': ae_score(self.ae_preprocessing, self.ae, x)}

    def forecast(self, x):
        return np.maximum(0., self.rf.predict(x))

    def save(self, path):
        joblib.dump(self, path)

    @classmethod
    def load(cls, path):
        result = joblib.load(path)  # Only trusted artifacts produced by offline training.
        if not isinstance(result, cls):
            raise ValueError('Not an anomaly bundle')
        result.validate()
        if not result.thresholds:
            raise ValueError('Uncalibrated artifact')
        return result
