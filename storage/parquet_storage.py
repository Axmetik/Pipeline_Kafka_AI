import os
from typing import Dict, Any, List

import pandas as pd


class ParquetStorage:
    def __init__(self, file_path: str, batch_size: int = 10):
        self.file_path = file_path
        self.batch_size = batch_size
        self.buffer: List[Dict[str, Any]] = []

        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def save(self, data: Dict[str, Any]) -> None:
        self.buffer.append(data)

        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return

        new_df = pd.DataFrame(self.buffer)

        if os.path.exists(self.file_path):
            existing_df = pd.read_parquet(self.file_path)
            result_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            result_df = new_df

        result_df.to_parquet(self.file_path, index=False)
        self.buffer.clear()