import glob
import os

import pandas as pd
import matplotlib.pyplot as plt


PARQUET_BASE_PATH = "data/processed/parquet"
OUTPUT_DIR = "data/analysis"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_partitioned_parquet(base_path: str) -> pd.DataFrame:
    parquet_files = glob.glob(f"{base_path}/**/*.parquet", recursive=True)

    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in: {base_path}")

    dataframes = [pd.read_parquet(file) for file in parquet_files]
    return pd.concat(dataframes, ignore_index=True)


def main() -> None:
    df = load_partitioned_parquet(PARQUET_BASE_PATH)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    total_records = len(df)
    ai_anomalies = int(df["ai_anomaly"].sum())
    temperature_rule_anomalies = int(df["is_temperature_anomaly"].sum())
    humidity_rule_anomalies = int(df["is_humidity_anomaly"].sum())

    summary = pd.DataFrame({
        "metric": [
            "total_records",
            "ai_anomalies",
            "temperature_rule_anomalies",
            "humidity_rule_anomalies",
            "ai_anomaly_rate_percent",
            "avg_temperature",
            "avg_humidity",
            "avg_light",
            "avg_voltage"
        ],
        "value": [
            total_records,
            ai_anomalies,
            temperature_rule_anomalies,
            humidity_rule_anomalies,
            round(ai_anomalies / total_records * 100, 2) if total_records else 0,
            round(df["temperature"].mean(), 2),
            round(df["humidity"].mean(), 2),
            round(df["light"].mean(), 2),
            round(df["voltage"].mean(), 4)
        ]
    })

    summary.to_csv(f"{OUTPUT_DIR}/summary_metrics.csv", index=False)

    print("=== IoT Streaming Pipeline Analysis ===")
    print(summary.to_string(index=False))

    anomaly_df = df[df["ai_anomaly"] == True]

    plt.figure(figsize=(12, 6))
    plt.plot(df["timestamp"], df["temperature"], label="Temperature")
    plt.scatter(anomaly_df["timestamp"], anomaly_df["temperature"], label="AI anomaly")
    plt.title("Temperature time-series with AI anomalies")
    plt.xlabel("Timestamp")
    plt.ylabel("Temperature")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/temperature_anomalies.png")
    plt.close()

    plt.figure(figsize=(12, 6))
    plt.plot(df["timestamp"], df["humidity"], label="Humidity")
    plt.scatter(anomaly_df["timestamp"], anomaly_df["humidity"], label="AI anomaly")
    plt.title("Humidity time-series with AI anomalies")
    plt.xlabel("Timestamp")
    plt.ylabel("Humidity")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/humidity_anomalies.png")
    plt.close()

    print(f"\nSaved analysis to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()