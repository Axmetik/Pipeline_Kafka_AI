import os
from datetime import datetime, timezone
from uuid import uuid4
from processing.message_schema import PROCESSED_FIELDS
from typing import Dict, Any, List

import pandas as pd


class ParquetStorage:
    def __init__(
        self,
        base_path: str,
        batch_size: int = 5000,
        compression: str = "snappy"
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.base_path = base_path
        self.batch_size = batch_size
        self.compression = compression
        self.buffer: List[Dict[str, Any]] = []
        self.batch_counter = 0

        os.makedirs(self.base_path, exist_ok=True)

    def save(self, data: Dict[str, Any]) -> None:
        self.buffer.append(dict(data))

        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return

        df = pd.DataFrame(self.buffer, columns=PROCESSED_FIELDS)

        timestamp = datetime.now(timezone.utc)

        partition_path = os.path.join(
            self.base_path,
            f"year={timestamp.year}",
            f"month={timestamp.month:02d}",
            f"day={timestamp.day:02d}"
        )

        os.makedirs(partition_path, exist_ok=True)

        self.batch_counter += 1

        file_path = os.path.join(
            partition_path,
            f"batch_{uuid4().hex}.parquet"
        )

        df.to_parquet(
            file_path,
            index=False,
            compression=self.compression
        )

        print(f"Saved parquet batch: {file_path}")

        self.buffer.clear()
