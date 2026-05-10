import os
from datetime import datetime
from typing import Dict, Any, List

import pandas as pd


class ParquetStorage:
    def __init__(self, base_path: str, batch_size: int = 100):
        self.base_path = base_path
        self.batch_size = batch_size
        self.buffer: List[Dict[str, Any]] = []
        self.batch_counter = 0

        os.makedirs(self.base_path, exist_ok=True)

    def save(self, data: Dict[str, Any]) -> None:
        self.buffer.append(data)

        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return

        df = pd.DataFrame(self.buffer)

        timestamp = datetime.now()

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
            f"batch_{self.batch_counter:03d}.parquet"
        )

        df.to_parquet(file_path, index=False)

        print(f"Saved parquet batch: {file_path}")

        self.buffer.clear()