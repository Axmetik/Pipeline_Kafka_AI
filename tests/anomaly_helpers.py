import json
from pathlib import Path
import numpy as np
from energy_helpers import energy_records
from anomaly.features import collect
from anomaly.train import fit_models
from anomaly.residual import score_batch
from anomaly.calibrate import calibrate


def small_config():
    config = json.loads((Path(__file__).resolve().parents[1] / 'configs/energy-anomaly-v1.json').read_text())
    config['rf']['n_estimators'] = 3
    config['isolation_forest'].update(n_estimators=3, max_samples=32)
    config['autoencoder'].update(max_epochs=2, patience=1)
    return config


def fixture():
    records = list(energy_records(360))
    # Nonlinear values and missing environmental readings exercise preprocessing.
    for i, r in enumerate(records):
        r['energy']['value'] = float(30 + (i % 37) * 3)
        if i % 5 == 0:
            r['environment']['temperature_c'] = None
    frame, x, rx = collect(records)
    config = small_config()
    train = (np.arange(len(frame)) >= 144) & (np.arange(len(frame)) < 240)
    bundle = fit_models(frame, x, rx, train, records[0], config)
    scores = score_batch(bundle, frame, x, rx)
    bundle.thresholds = calibrate(scores.iloc[240:280], config['quantiles'])
    return records, frame, x, rx, bundle, config
