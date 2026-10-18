"""One causal feature implementation shared by offline training and streaming."""
from collections import deque
from datetime import timedelta
import math

import numpy as np
from processing.energy_schema import parse_timestamp
from processing.message_schema import InvalidMessage

FEATURE_VERSION = "energy-features-v1"
FEATURE_NAMES = ["energy_wh", *[f"lag_{i}_wh" for i in range(1, 7)],
                 "rolling_3_mean", "rolling_3_std", "rolling_6_mean", "rolling_6_std",
                 "temperature_c", "relative_humidity_pct", "temperature_missing", "humidity_missing",
                 "hour_sin", "hour_cos", "weekday_sin", "weekday_cos", "is_weekend"]


class EnergyProcessor:
    def __init__(self):
        self.histories = {}
        self.last_times = {}
        self.semantics = {}

    def process(self, record):
        if record["interval_seconds"] != 600:
            raise InvalidMessage("This model supports only 600-second intervals")
        key = (record["building_id"], record["source_id"])
        timestamp = parse_timestamp(record["timestamp"])
        signature = (record["energy"]["scope"], record["timestamp_reference"],
                     timestamp.tzinfo is not None, record["timezone"])
        if key in self.semantics and self.semantics[key] != signature:
            raise InvalidMessage("Measurement semantics changed within source")
        previous = self.last_times.get(key)
        if previous is not None and timestamp <= previous:
            raise InvalidMessage("Duplicate or out-of-order measurement timestamp")
        history = self.histories.setdefault(key, deque(maxlen=7))
        gap = previous is not None and timestamp - previous != timedelta(seconds=600)
        if gap:
            history.clear()
        history.append(record["energy"]["value"])
        self.last_times[key] = timestamp
        self.semantics[key] = signature
        features = None
        if len(history) == 7:
            values = list(history)
            env = record["environment"]
            hour = timestamp.hour + timestamp.minute / 60
            day = timestamp.weekday()
            features = {"energy_wh": values[-1]}
            features.update({f"lag_{i}_wh": values[-1-i] for i in range(1, 7)})
            for window in (3, 6):
                features[f"rolling_{window}_mean"] = float(np.mean(values[-window:]))
                features[f"rolling_{window}_std"] = float(np.std(values[-window:]))
            features.update({
                "temperature_c": env["temperature_c"] if env["temperature_c"] is not None else float("nan"),
                "relative_humidity_pct": env["relative_humidity_pct"] if env["relative_humidity_pct"] is not None else float("nan"),
                "temperature_missing": int(env["temperature_c"] is None),
                "humidity_missing": int(env["relative_humidity_pct"] is None),
                "hour_sin": math.sin(2 * math.pi * hour / 24),
                "hour_cos": math.cos(2 * math.pi * hour / 24),
                "weekday_sin": math.sin(2 * math.pi * day / 7),
                "weekday_cos": math.cos(2 * math.pi * day / 7),
                "is_weekend": int(day >= 5),
            })
        return {"record": record, "features": features,
                "status": "ready" if features is not None else "insufficient_history",
                "gap_detected": gap,
                "forecast_origin": timestamp.isoformat(),
                "forecast_target_timestamp": (timestamp + timedelta(seconds=600)).isoformat()}
