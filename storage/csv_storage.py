import csv
import os
from typing import Dict, Any


class CSVStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.fieldnames = [
            "sensor_id",
            "timestamp",
            "temperature",
            "humidity",
            "is_temperature_anomaly",
            "is_humidity_anomaly"
        ]

        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if not os.path.exists(self.file_path):
            with open(self.file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=self.fieldnames)
                writer.writeheader()

    def save(self, data: Dict[str, Any]) -> None:
        with open(self.file_path, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.fieldnames)
            writer.writerow(data)