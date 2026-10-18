"""Offline-only fitting. Callers provide exclusively the train partition."""
import hashlib
import json
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from ai.energy_forecaster import source_binding
from benchmark.models import make_model
from benchmark.features import BENCHMARK_FEATURES
from processing.energy_processor import FEATURE_NAMES
from processing.energy_schema import validate_energy
from anomaly.detectors import preprocessing, fit_ae
from anomaly.features import FEATURE_VERSION, RF_FEATURE_VERSION
from anomaly.artifacts import Bundle


def fit_models(frame, x, rf_x, train_mask, source_record, config):
    mask = train_mask & frame.feature_ready & frame.residual_ready
    if not mask.any():
        raise ValueError('No common train rows')
    xtrain = x[mask]
    forest = Pipeline([('preprocessing', preprocessing()),
                       ('model', IsolationForest(**config['isolation_forest'], random_state=config['seed'], n_jobs=1))])
    forest.fit(xtrain)
    ae_prep, ae, ae_info = fit_ae(xtrain, config['autoencoder'], config['seed'])
    rf = make_model('random_forest', config['rf'], config['seed'])
    rf.fit(rf_x[mask], frame.loc[mask, 'actual_energy_wh'].to_numpy())
    fingerprint = hashlib.sha256(xtrain.tobytes() + rf_x[mask].tobytes() + json.dumps(config, sort_keys=True).encode()).hexdigest()
    metadata = {'model_version': 'energy-anomaly-v1-' + fingerprint[:16],
                'feature_names': FEATURE_NAMES, 'feature_version': FEATURE_VERSION,
                'rf_feature_names': BENCHMARK_FEATURES, 'rf_feature_version': RF_FEATURE_VERSION,
                'horizon_seconds': 600, 'allowed_sources': [source_binding(validate_energy(source_record))],
                'training_fingerprint': fingerprint, 'train_count': int(mask.sum()),
                'train_first': frame.loc[mask, 'measurement_timestamp'].iloc[0],
                'train_last': frame.loc[mask, 'measurement_timestamp'].iloc[-1],
                'ae_training': ae_info}
    return Bundle(forest, ae_prep, ae, rf, metadata)
