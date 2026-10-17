"""Append invalid messages with their Kafka position for diagnosis/replay."""
import base64
import json
from pathlib import Path


class RejectedStorage:
    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, payload, reason, metadata=None):
        record = {
            "reason": reason,
            "raw_base64": base64.b64encode(payload).decode("ascii") if payload is not None else None,
            **(metadata or {}),
        }
        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
