from kafka import KafkaProducer
import pandas as pd
import json
import time

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

TOPIC_NAME = "iot-sensor-data"

columns = [
    "date",
    "time",
    "epoch",
    "mote_id",
    "temperature",
    "humidity",
    "light",
    "voltage"
]

df = pd.read_csv(
    "data/raw/intel_lab_data.txt",
    sep=r"\s+",
    names=columns
)

print("Intel Lab Producer started...\n")

for _, row in df.iterrows():
    sensor_data = {
        "timestamp": f"{row['date']} {row['time']}",
        "sensor_id": int(row["mote_id"]),
        "temperature": float(row["temperature"]),
        "humidity": float(row["humidity"]),
        "light": float(row["light"]),
        "voltage": float(row["voltage"])
    }

    producer.send(TOPIC_NAME, sensor_data)

    print(f"Sent: {sensor_data}")

    time.sleep(1)