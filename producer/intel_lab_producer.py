from kafka import KafkaProducer
import pandas as pd
import json
import time
import argparse
import os
from config import Settings


SETTINGS = Settings.from_env()
TOPIC_NAME = SETTINGS.topic
DATASET_PATH = os.getenv("INTEL_LAB_DATASET_PATH", "data/raw/intel_lab_data.txt")

COLUMNS = [
    "date",
    "time",
    "epoch",
    "mote_id",
    "temperature",
    "humidity",
    "light",
    "voltage"
]


def create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=SETTINGS.bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8")
    )


def load_dataset(limit: int | None = None) -> pd.DataFrame:
    df = pd.read_csv(
        DATASET_PATH,
        sep=r"\s+",
        names=COLUMNS
    )

    df = df.dropna()

    if limit:
        df = df.head(limit)

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel Lab Dataset Kafka Producer")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Delay between messages in seconds. Use 0 for fast experiment mode."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of records to stream."
    )

    args = parser.parse_args()

    producer = create_producer()
    df = load_dataset(limit=args.limit)

    print(f"Intel Lab Producer started. Records to send: {len(df)}")
    print(f"Sleep between messages: {args.sleep} seconds\n")

    for _, row in df.iterrows():
        sensor_data = {
            "timestamp": f"{row['date']} {row['time']}",
            "sensor_id": int(row["mote_id"]),
            "temperature": float(row["temperature"]),
            "humidity": float(row["humidity"]),
            "light": float(row["light"]),
            "voltage": float(row["voltage"])
        }

        producer.send(TOPIC_NAME, sensor_data).get(timeout=30)

        if args.sleep > 0:
            time.sleep(args.sleep)

    producer.flush()
    producer.close()

    print("\nProducer finished sending data.")


if __name__ == "__main__":
    main()
