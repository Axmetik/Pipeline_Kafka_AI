import glob
import os
import time

import pandas as pd


CSV_PATH = "data/processed/iot_sensor_data.csv"
PARQUET_BASE_PATH = "data/processed/parquet"
OUTPUT_PATH = "data/analysis/storage_comparison.csv"

ANALYTICAL_COLUMNS = [
    "timestamp",
    "sensor_id",
    "temperature",
    "humidity",
    "ai_anomaly",
    "autoencoder_anomaly",
    "autoencoder_reconstruction_error"
]


def get_file_size_kb(file_path: str) -> float:
    return os.path.getsize(file_path) / 1024


def get_folder_size_kb(folder_path: str) -> float:
    total_size = 0

    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith(".parquet"):
                total_size += os.path.getsize(os.path.join(root, file))

    return total_size / 1024


def get_parquet_files(base_path: str) -> list[str]:
    parquet_files = glob.glob(f"{base_path}/**/*.parquet", recursive=True)

    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in: {base_path}")

    return parquet_files


def load_partitioned_parquet(base_path: str, columns: list[str] | None = None) -> pd.DataFrame:
    parquet_files = get_parquet_files(base_path)
    dataframes = [pd.read_parquet(file, columns=columns) for file in parquet_files]
    return pd.concat(dataframes, ignore_index=True)


def measure_time(function) -> float:
    start = time.perf_counter()
    function()
    end = time.perf_counter()
    return end - start


def main() -> None:
    os.makedirs("data/analysis", exist_ok=True)

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")

    if not os.path.exists(PARQUET_BASE_PATH):
        raise FileNotFoundError(f"Parquet folder not found: {PARQUET_BASE_PATH}")

    csv_size = get_file_size_kb(CSV_PATH)
    parquet_size = get_folder_size_kb(PARQUET_BASE_PATH)

    csv_full_read_time = measure_time(lambda: pd.read_csv(CSV_PATH))
    parquet_full_read_time = measure_time(lambda: load_partitioned_parquet(PARQUET_BASE_PATH))

    csv_column_read_time = measure_time(lambda: pd.read_csv(CSV_PATH, usecols=ANALYTICAL_COLUMNS))
    parquet_column_read_time = measure_time(
        lambda: load_partitioned_parquet(PARQUET_BASE_PATH, columns=ANALYTICAL_COLUMNS)
    )

    size_reduction_percent = (
        (1 - parquet_size / csv_size) * 100 if csv_size else 0
    )

    comparison = pd.DataFrame([
        {
            "format": "CSV",
            "file_size_kb": round(csv_size, 2),
            "full_read_time_seconds": round(csv_full_read_time, 6),
            "analytical_columns_read_time_seconds": round(csv_column_read_time, 6),
            "size_reduction_percent_vs_csv": 0
        },
        {
            "format": "Partitioned Parquet",
            "file_size_kb": round(parquet_size, 2),
            "full_read_time_seconds": round(parquet_full_read_time, 6),
            "analytical_columns_read_time_seconds": round(parquet_column_read_time, 6),
            "size_reduction_percent_vs_csv": round(size_reduction_percent, 2)
        }
    ])

    comparison.to_csv(OUTPUT_PATH, index=False)

    print("=== Storage Format Comparison ===")
    print(comparison.to_string(index=False))
    print(f"\nSaved comparison to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()