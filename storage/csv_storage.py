import csv
import os
from typing import Dict, Any
from processing.message_schema import PROCESSED_FIELDS


class CSVStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.fieldnames = list(PROCESSED_FIELDS)

        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if os.path.exists(self.file_path) and os.path.getsize(self.file_path):
            with open(self.file_path, newline="", encoding="utf-8") as file:
                if next(csv.reader(file), None) != self.fieldnames:
                    raise ValueError(
                        f"Incompatible CSV header: {self.file_path}. "
                        "Use a new PIPELINE_OUTPUT_DIR; existing data was not changed."
                    )
        else:
            with open(self.file_path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=self.fieldnames)
                writer.writeheader()

    def save(self, data: Dict[str, Any]) -> None:
        with open(self.file_path, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.fieldnames,
                extrasaction="raise"
            )
            writer.writerow(data)
