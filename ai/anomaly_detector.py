from collections import deque
from typing import Dict, Any

import numpy as np
from sklearn.ensemble import IsolationForest


class AnomalyDetector:
    def __init__(self, window_size: int = 50):
        self.window_size = window_size

        self.temperature_window = deque(maxlen=window_size)
        self.humidity_window = deque(maxlen=window_size)

        self.model = IsolationForest(
            contamination=0.1,
            random_state=42
        )

    def detect(self, data: Dict[str, Any]) -> Dict[str, Any]:
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])

        self.temperature_window.append(temperature)
        self.humidity_window.append(humidity)

        if len(self.temperature_window) < self.window_size:
            data["ai_anomaly"] = False
            return data

        features = np.column_stack([
            self.temperature_window,
            self.humidity_window
        ])

        self.model.fit(features)

        current_point = np.array([[temperature, humidity]])

        prediction = self.model.predict(current_point)

        data["ai_anomaly"] = prediction[0] == -1

        return data