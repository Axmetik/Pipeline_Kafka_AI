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
        compression: str = "snappy",
        columns=None,
        arrow_schema=None
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.columns = list(PROCESSED_FIELDS) if columns is None else list(columns)
        self.arrow_schema = arrow_schema
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

        df = pd.DataFrame(self.buffer, columns=self.columns)

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

        options = {"schema": self.arrow_schema} if self.arrow_schema is not None else {}
        df.to_parquet(
            file_path,
            index=False,
            compression=self.compression,
            **options
        )

        print(f"Saved parquet batch: {file_path}")

        self.buffer.clear()
