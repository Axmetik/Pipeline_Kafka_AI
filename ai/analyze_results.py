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


def safe_sum(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0

    return int(df[column].fillna(False).sum())


def safe_mean(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return 0.0

    return round(float(df[column].mean()), 6)


def safe_max(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return 0.0

    return round(float(df[column].max()), 6)


def save_summary(df: pd.DataFrame) -> None:
    total_records = len(df)

    iforest_anomalies = safe_sum(df, "ai_anomaly")
    autoencoder_anomalies = safe_sum(df, "autoencoder_anomaly")
    temperature_rule_anomalies = safe_sum(df, "is_temperature_anomaly")
    humidity_rule_anomalies = safe_sum(df, "is_humidity_anomaly")

    summary = pd.DataFrame({
        "metric": [
            "total_records",
            "iforest_anomalies",
            "iforest_anomaly_rate_percent",
            "autoencoder_anomalies",
            "autoencoder_anomaly_rate_percent",
            "temperature_rule_anomalies",
            "humidity_rule_anomalies",
            "avg_autoencoder_reconstruction_error",
            "max_autoencoder_reconstruction_error",
            "avg_iforest_anomaly_score",
            "min_iforest_anomaly_score",
            "avg_temperature",
            "avg_humidity",
            "avg_light",
            "avg_voltage"
        ],
        "value": [
            total_records,
            iforest_anomalies,
            round(iforest_anomalies / total_records * 100, 2) if total_records else 0,
            autoencoder_anomalies,
            round(autoencoder_anomalies / total_records * 100, 2) if total_records else 0,
            temperature_rule_anomalies,
            humidity_rule_anomalies,
            safe_mean(df, "autoencoder_reconstruction_error"),
            safe_max(df, "autoencoder_reconstruction_error"),
            safe_mean(df, "iforest_anomaly_score"),
            round(float(df["iforest_anomaly_score"].min()), 6) if "iforest_anomaly_score" in df.columns else 0.0,
            safe_mean(df, "temperature"),
            safe_mean(df, "humidity"),
            safe_mean(df, "light"),
            safe_mean(df, "voltage")
        ]
    })

    summary.to_csv(f"{OUTPUT_DIR}/summary_metrics.csv", index=False)

    print("=== IoT Streaming Pipeline Analysis ===")
    print(summary.to_string(index=False))


def save_anomaly_comparison(df: pd.DataFrame) -> None:
    comparison = pd.DataFrame({
        "method": [
            "Rule-based temperature",
            "Rule-based humidity",
            "Isolation Forest",
            "Autoencoder"
        ],
        "anomaly_count": [
            safe_sum(df, "is_temperature_anomaly"),
            safe_sum(df, "is_humidity_anomaly"),
            safe_sum(df, "ai_anomaly"),
            safe_sum(df, "autoencoder_anomaly")
        ]
    })

    comparison["anomaly_rate_percent"] = round(
        comparison["anomaly_count"] / len(df) * 100,
        2
    )

    comparison.to_csv(f"{OUTPUT_DIR}/anomaly_method_comparison.csv", index=False)

    plt.figure(figsize=(10, 6))
    plt.bar(comparison["method"], comparison["anomaly_count"])
    plt.title("Anomaly count by detection method")
    plt.xlabel("Detection method")
    plt.ylabel("Anomaly count")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/anomaly_method_comparison.png")
    plt.close()


def save_temperature_plot(df: pd.DataFrame) -> None:
    plt.figure(figsize=(12, 6))
    plt.plot(df["timestamp"], df["temperature"], label="Temperature")

    if "ai_anomaly" in df.columns:
        iforest_df = df[df["ai_anomaly"] == True]
        plt.scatter(
            iforest_df["timestamp"],
            iforest_df["temperature"],
            label="Isolation Forest anomaly"
        )

    if "autoencoder_anomaly" in df.columns:
        ae_df = df[df["autoencoder_anomaly"] == True]
        plt.scatter(
            ae_df["timestamp"],
            ae_df["temperature"],
            label="Autoencoder anomaly"
        )

    plt.title("Temperature time-series with detected anomalies")
    plt.xlabel("Timestamp")
    plt.ylabel("Temperature")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/temperature_anomalies_comparison.png")
    plt.close()


def save_reconstruction_error_plot(df: pd.DataFrame) -> None:
    if "autoencoder_reconstruction_error" not in df.columns:
        return

    plt.figure(figsize=(12, 6))
    plt.plot(
        df["timestamp"],
        df["autoencoder_reconstruction_error"],
        label="Autoencoder reconstruction error"
    )

    if "autoencoder_anomaly" in df.columns:
        ae_df = df[df["autoencoder_anomaly"] == True]
        plt.scatter(
            ae_df["timestamp"],
            ae_df["autoencoder_reconstruction_error"],
            label="Autoencoder anomaly"
        )

    plt.title("Autoencoder reconstruction error over time")
    plt.xlabel("Timestamp")
    plt.ylabel("Reconstruction error")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/autoencoder_reconstruction_error.png")
    plt.close()


def save_iforest_score_plot(df: pd.DataFrame) -> None:
    if "iforest_anomaly_score" not in df.columns:
        return

    plt.figure(figsize=(12, 6))
    plt.plot(
        df["timestamp"],
        df["iforest_anomaly_score"],
        label="Isolation Forest anomaly score"
    )

    if "ai_anomaly" in df.columns:
        iforest_df = df[df["ai_anomaly"] == True]
        plt.scatter(
            iforest_df["timestamp"],
            iforest_df["iforest_anomaly_score"],
            label="Isolation Forest anomaly"
        )

    plt.title("Isolation Forest anomaly score over time")
    plt.xlabel("Timestamp")
    plt.ylabel("Anomaly score")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/iforest_anomaly_score.png")
    plt.close()


def main() -> None:
    df = load_partitioned_parquet(PARQUET_BASE_PATH)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp")

    save_summary(df)
    save_anomaly_comparison(df)
    save_temperature_plot(df)
    save_reconstruction_error_plot(df)
    save_iforest_score_plot(df)

    print(f"\nSaved analysis to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()