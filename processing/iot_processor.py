from typing import Dict, Any


class IoTProcessor:
    def __init__(self):
        self.min_temperature = 20.0
        self.max_temperature = 35.0
        self.min_humidity = 30.0
        self.max_humidity = 80.0

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        temperature = float(data["temperature"])
        humidity = float(data["humidity"])

        data["is_temperature_anomaly"] = not (
            self.min_temperature <= temperature <= self.max_temperature
        )

        data["is_humidity_anomaly"] = not (
            self.min_humidity <= humidity <= self.max_humidity
        )

        return data