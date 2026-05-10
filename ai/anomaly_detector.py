from collections import deque
from typing import Dict, Any

import numpy as np
from sklearn.ensemble import IsolationForest


class AnomalyDetector:
    def __init__(
        self,
        window_size: int = 500,
        contamination: float = 0.03,
        min_train_size: int = 500
    ):
        self.window_size = window_size
        self.contamination = contamination
        self.min_train_size = min_train_size

        self.temperature_window = deque(maxlen=window_size)
        self.humidity_window = deque(maxlen=window_size)
        self.light_window = deque(maxlen=window_size)
        self.voltage_window = deque(maxlen=window_size)

        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100
        )

        self.is_trained = False

    def detect(self, data: Dict[str, Any]) -> Dict[str, Any]:
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])
        light = float(data["light"])
        voltage = float(data["voltage"])

        self.temperature_window.append(temperature)
        self.humidity_window.append(humidity)
        self.light_window.append(light)
        self.voltage_window.append(voltage)

        current_window_size = len(self.temperature_window)

        if current_window_size < self.min_train_size:
            data["ai_anomaly"] = False
            data["iforest_anomaly_score"] = 0.0
            return data

        features = np.column_stack([
            self.temperature_window,
            self.humidity_window,
            self.light_window,
            self.voltage_window
        ])

        self.model.fit(features)
        self.is_trained = True

        current_point = np.array([[temperature, humidity, light, voltage]])

        prediction = self.model.predict(current_point)
        score = self.model.decision_function(current_point)[0]

        data["ai_anomaly"] = prediction[0] == -1
        data["iforest_anomaly_score"] = round(float(score), 6)

        return data