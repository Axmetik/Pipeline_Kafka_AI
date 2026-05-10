from kafka import KafkaConsumer
import json

TOPIC_NAME = "iot-sensor-data"

consumer = KafkaConsumer(
    TOPIC_NAME,
    bootstrap_servers="localhost:9092",
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="iot-consumer-group",
    value_deserializer=lambda v: json.loads(v.decode("utf-8"))
)

print("Consumer started. Waiting for messages...\n")

for message in consumer:
    data = message.value

    print(
        f"Received | "
        f"sensor_id={data['sensor_id']} | "
        f"timestamp={data['timestamp']} | "
        f"temperature={data['temperature']} | "
        f"humidity={data['humidity']}"
    )