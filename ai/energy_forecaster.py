"""Versioned, inference-only energy forecasting artifact."""
import joblib
import numpy as np
from processing.energy_processor import FEATURE_NAMES, FEATURE_VERSION


class EnergyForecaster:
    def __init__(self, model, metadata):
        self.model = model
        self.metadata = metadata
        if metadata.get("feature_version") != FEATURE_VERSION or metadata.get("feature_names") != FEATURE_NAMES:
            raise ValueError("Incompatible feature schema in model artifact")
        if metadata.get("horizon_seconds") != 600:
            raise ValueError("Incompatible prediction horizon")

    @classmethod
    def load(cls, path):
        # joblib/pickle artifacts must come from a trusted local training run.
        artifact = joblib.load(path)
        return cls(artifact["model"], artifact["metadata"])

    def save(self, path):
        joblib.dump({"model": self.model, "metadata": self.metadata}, path)

    def predict(self, features):
        vector = np.asarray([[features[name] for name in FEATURE_NAMES]], dtype=float)
        return float(max(0.0, self.model.predict(vector)[0]))

    def predict_many(self, frame):
        return np.maximum(0.0, self.model.predict(frame[FEATURE_NAMES].to_numpy(dtype=float)))
