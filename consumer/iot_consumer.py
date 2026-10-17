import argparse

from kafka import KafkaConsumer
from config import Settings
from processing.iot_processor import IoTProcessor
from processing.message_schema import decode_record, InvalidMessage
from storage.csv_storage import CSVStorage
from storage.parquet_storage import ParquetStorage
from storage.rejected_storage import RejectedStorage
from ai.anomaly_detector import AnomalyDetector
from ai.autoencoder_detector import AutoencoderAnomalyDetector


class ProcessingPipeline:
    def __init__(self, settings, isolation_forest=None, autoencoder=None):
        self.processor = IoTProcessor()
        self.isolation_forest = isolation_forest or AnomalyDetector(
            window_size=500, contamination=0.03, min_train_size=500)
        self.autoencoder = autoencoder or AutoencoderAnomalyDetector()
        self.csv = CSVStorage(settings.output_dir / "iot_sensor_data.csv")
        self.parquet = ParquetStorage(
            str(settings.output_dir / "parquet"), settings.parquet_batch_size)
        self.rejected = RejectedStorage(settings.output_dir / "rejected.jsonl")

    def process(self, payload, metadata=None):
        try:
            if payload is None:
                raise InvalidMessage("Null Kafka value is not a sensor record")
            record = decode_record(payload)
        except InvalidMessage as exc:
            self.rejected.save(payload, str(exc), metadata)
            print(f"Rejected: {exc}")
            return False
        record = self.processor.process(record)
        record = self.isolation_forest.detect(record)
        record = self.autoencoder.detect(record)
        self.csv.save(record)
        self.parquet.save(record)
        return True

    def close(self):
        self.parquet.flush()


def main():
    parser = argparse.ArgumentParser(description="Process IoT Kafka messages")
    parser.add_argument("--max-messages", type=int, help="Stop after N received messages, including rejected ones")
    parser.add_argument("--idle-timeout-ms", type=int, default=0, help="Exit after inactivity; 0 waits indefinitely")
    args = parser.parse_args()
    if (args.max_messages is not None and args.max_messages < 1) or args.idle_timeout_ms < 0:
        parser.error("--max-messages must be positive and --idle-timeout-ms non-negative")
    settings = Settings.from_env()
    pipeline = ProcessingPipeline(settings)
    consumer = None
    accepted = rejected = 0
    try:
        consumer = KafkaConsumer(
            settings.topic, bootstrap_servers=settings.bootstrap_servers,
            auto_offset_reset="earliest", enable_auto_commit=True,
            group_id=settings.group_id,
            consumer_timeout_ms=args.idle_timeout_ms or float("inf"),
        )
        print(f"Consumer started: topic={settings.topic}, output={settings.output_dir}")
        for message in consumer:
            metadata = {"topic": message.topic, "partition": message.partition, "offset": message.offset}
            if pipeline.process(message.value, metadata):
                accepted += 1
                print(f"Processed: partition={message.partition}, offset={message.offset}, accepted={accepted}")
            else:
                rejected += 1
            if args.max_messages is not None and accepted + rejected >= args.max_messages:
                break
    except KeyboardInterrupt:
        print("Consumer stopped by user")
    finally:
        try:
            pipeline.close()
        finally:
            if consumer is not None:
                consumer.close()
        print(f"Finished: accepted={accepted}, rejected={rejected}")


if __name__ == "__main__":
    main()
