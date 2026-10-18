"""Versioned, inference-only energy forecasting artifact."""
import copy
import joblib
import numpy as np
from processing.energy_processor import FEATURE_NAMES, FEATURE_VERSION
from processing.energy_schema import parse_timestamp
from processing.message_schema import InvalidMessage


SOURCE_FIELDS = {"building_id", "source_id", "source_type", "energy_scope",
                 "interval_seconds", "timestamp_reference", "timezone", "timestamp_has_offset"}


def source_binding(record):
    """Identity and measurement semantics, not an authentication mechanism."""
    return {
        "building_id": record["building_id"], "source_id": record["source_id"],
        "source_type": record["source_type"], "energy_scope": record["energy"]["scope"],
        "interval_seconds": record["interval_seconds"],
        "timestamp_reference": record["timestamp_reference"], "timezone": record["timezone"],
        "timestamp_has_offset": parse_timestamp(record["timestamp"]).tzinfo is not None,
    }


def valid_binding(binding):
    return (isinstance(binding, dict) and set(binding) == SOURCE_FIELDS
            and all(isinstance(binding[key], str) and binding[key].strip()
                    for key in ("building_id", "source_id"))
            and binding["source_type"] in ("dataset", "smart_meter")
            and binding["energy_scope"] == "appliances"
            and type(binding["interval_seconds"]) is int and binding["interval_seconds"] == 600
            and binding["timestamp_reference"] in ("dataset_label", "interval_start", "interval_end")
            and (binding["timezone"] is None or isinstance(binding["timezone"], str))
            and type(binding["timestamp_has_offset"]) is bool)


class EnergyForecaster:
    def __init__(self, model, metadata):
        self.model = model
        self.metadata = copy.deepcopy(metadata)
        if metadata.get("feature_version") != FEATURE_VERSION or metadata.get("feature_names") != FEATURE_NAMES:
            raise ValueError("Incompatible feature schema in model artifact")
        if metadata.get("horizon_seconds") != 600:
            raise ValueError("Incompatible prediction horizon")

        bindings = metadata.get("allowed_sources")
        if not isinstance(bindings, list) or not bindings or not all(valid_binding(item) for item in bindings):
            raise ValueError("Model has no valid allowed_sources binding; retrain into a new experiment directory")
        self.allowed_sources = copy.deepcopy(bindings)

    def validate_source(self, record):
        if source_binding(record) not in self.allowed_sources:
            raise InvalidMessage("Source is not compatible with the model's allowed_sources")

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
