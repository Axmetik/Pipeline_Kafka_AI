import os

import pandas as pd
import matplotlib.pyplot as plt


DATA_PATH = "data/processed/iot_sensor_data.parquet"
OUTPUT_DIR = "data/analysis"

os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_parquet(DATA_PATH)

df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

total_records = len(df)
ai_anomalies = df["ai_anomaly"].sum()
temperature_rule_anomalies = df["is_temperature_anomaly"].sum()
humidity_rule_anomalies = df["is_humidity_anomaly"].sum()

print("=== IoT Streaming Pipeline Analysis ===")
print(f"Total records: {total_records}")
print(f"AI anomalies: {ai_anomalies}")
print(f"Temperature rule anomalies: {temperature_rule_anomalies}")
print(f"Humidity rule anomalies: {humidity_rule_anomalies}")

if total_records > 0:
    print(f"AI anomaly rate: {ai_anomalies / total_records * 100:.2f}%")

summary = pd.DataFrame({
    "metric": [
        "total_records",
        "ai_anomalies",
        "temperature_rule_anomalies",
        "humidity_rule_anomalies",
        "ai_anomaly_rate_percent"
    ],
    "value": [
        total_records,
        ai_anomalies,
        temperature_rule_anomalies,
        humidity_rule_anomalies,
        round(ai_anomalies / total_records * 100, 2) if total_records else 0
    ]
})

summary.to_csv(f"{OUTPUT_DIR}/summary_metrics.csv", index=False)

plt.figure(figsize=(12, 6))
plt.plot(df["timestamp"], df["temperature"], label="Temperature")

anomaly_df = df[df["ai_anomaly"] == True]
plt.scatter(
    anomaly_df["timestamp"],
    anomaly_df["temperature"],
    label="AI anomaly"
)

plt.title("Temperature time-series with AI anomalies")
plt.xlabel("Timestamp")
plt.ylabel("Temperature")
plt.legend()
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/temperature_anomalies.png")
plt.close()

plt.figure(figsize=(12, 6))
plt.plot(df["timestamp"], df["humidity"], label="Humidity")

plt.scatter(
    anomaly_df["timestamp"],
    anomaly_df["humidity"],
    label="AI anomaly"
)

plt.title("Humidity time-series with AI anomalies")
plt.xlabel("Timestamp")
plt.ylabel("Humidity")
plt.legend()
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/humidity_anomalies.png")
plt.close()

print(f"\nSaved analysis to: {OUTPUT_DIR}")