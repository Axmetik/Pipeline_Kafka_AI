from kafka import KafkaConsumer
import json

from processing.iot_processor import IoTProcessor
from storage.csv_storage import CSVStorage
from storage.parquet_storage import ParquetStorage
from ai.anomaly_detector import AnomalyDetector
from ai.autoencoder_detector import AutoencoderAnomalyDetector


TOPIC_NAME = "iot-sensor-data"

consumer = KafkaConsumer(
    TOPIC_NAME,
    bootstrap_servers="localhost:9092",
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="iot-processing-group",
    value_deserializer=lambda v: json.loads(v.decode("utf-8"))
)

processor = IoTProcessor()

isolation_forest_detector = AnomalyDetector(
    window_size=50
)

autoencoder_detector = AutoencoderAnomalyDetector(
    window_size=100,
    threshold_percentile=95
)

csv_storage = CSVStorage(
    file_path="data/processed/iot_sensor_data.csv"
)

parquet_storage = ParquetStorage(
    base_path="data/processed/parquet",
    batch_size=100
)

print("Processing consumer started. Waiting for messages...\n")

try:
    for message in consumer:
        raw_data = message.value

        processed_data = processor.process(raw_data)
        processed_data = isolation_forest_detector.detect(processed_data)
        processed_data = autoencoder_detector.detect(processed_data)

        csv_storage.save(processed_data)
        parquet_storage.save(processed_data)

        print(
            f"Processed | "
            f"sensor={processed_data['sensor_id']} | "
            f"temp={processed_data['temperature']} | "
            f"humidity={processed_data['humidity']} | "
            f"iforest_anomaly={processed_data['ai_anomaly']} | "
            f"ae_anomaly={processed_data['autoencoder_anomaly']} | "
            f"ae_error={processed_data['autoencoder_reconstruction_error']}"
        )

except KeyboardInterrupt:
    print("\nConsumer stopped by user.")

finally:
    parquet_storage.flush()
    consumer.close()
    print("Final parquet buffer flushed. Consumer closed.")