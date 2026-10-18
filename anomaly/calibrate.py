"""Threshold fitting is separate from model fitting."""
import numpy as np
from anomaly.features import NAMES


def calibrate(scores, quantiles):
    if scores.empty or not np.isfinite(scores[list(NAMES)].to_numpy()).all():
        raise ValueError('Calibration requires common finite scores')
    return {str(q): {name: float(np.quantile(scores[name], q, method='linear')) for name in NAMES}
            for q in quantiles}
