"""Shared runtime settings. Paths are relative to the working directory."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bootstrap_servers: str = "localhost:9092"
    topic: str = "iot-sensor-data"
    group_id: str = "iot-processing-group"
    output_dir: Path = Path("data/processed")
    parquet_batch_size: int = 5000

    @classmethod
    def from_env(cls):
        batch_size = int(os.getenv("PARQUET_BATCH_SIZE", "5000"))
        if batch_size < 1:
            raise ValueError("PARQUET_BATCH_SIZE must be positive")
        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            topic=os.getenv("KAFKA_TOPIC", "iot-sensor-data"),
            group_id=os.getenv("KAFKA_GROUP_ID", "iot-processing-group"),
            output_dir=Path(os.getenv("PIPELINE_OUTPUT_DIR", "data/processed")),
            parquet_batch_size=batch_size,
        )


@dataclass(frozen=True)
class EnergySettings:
    bootstrap_servers: str = "localhost:9092"
    topic: str = "energy-measurements"
    group_id: str = "energy-processing-group"
    output_dir: Path = Path("data/energy/processed")
    parquet_batch_size: int = 5000

    @classmethod
    def from_env(cls):
        batch_size = int(os.getenv("ENERGY_PARQUET_BATCH_SIZE", "5000"))
        if batch_size < 1:
            raise ValueError("ENERGY_PARQUET_BATCH_SIZE must be positive")
        return cls(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            topic=os.getenv("ENERGY_KAFKA_TOPIC", "energy-measurements"),
            group_id=os.getenv("ENERGY_KAFKA_GROUP_ID", "energy-processing-group"),
            output_dir=Path(os.getenv("ENERGY_OUTPUT_DIR", "data/energy/processed")),
            parquet_batch_size=batch_size,
        )
