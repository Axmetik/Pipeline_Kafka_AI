from kafka import KafkaProducer
import json
import time
import random
from datetime import datetime

# Підключення до Kafka
producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

TOPIC_NAME = "iot-sensor-data"

print("Producer started...\n")

while True:
    sensor_data = {
        "sensor_id": random.randint(1, 5),
        "timestamp": datetime.now().isoformat(),
        "temperature": round(random.uniform(20.0, 35.0), 2),
        "humidity": round(random.uniform(30.0, 80.0), 2)
    }

    producer.send(TOPIC_NAME, sensor_data)

    print(f"Sent: {sensor_data}")

    time.sleep(2)