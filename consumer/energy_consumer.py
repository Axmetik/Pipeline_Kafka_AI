"""Energy inference: no model fitting in the Kafka consumer."""
import argparse
import json
from datetime import datetime, timezone

from kafka import KafkaConsumer
from threadpoolctl import threadpool_limits

from config import EnergySettings
from ai.energy_forecaster import EnergyForecaster
from processing.energy_schema import decode_energy
from processing.energy_processor import EnergyProcessor
from processing.message_schema import InvalidMessage
from storage.energy_storage import energy_storages
from storage.rejected_storage import RejectedStorage


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class EnergyPipeline:
    def __init__(self, settings, forecaster):
        self.forecaster = forecaster
        self.processor = EnergyProcessor()
        self.measurements, self.forecasts = energy_storages(settings)
        self.rejected = RejectedStorage(settings.output_dir / "rejected.jsonl")
        self.accepted = self.rejected_count = self.predicted = 0

    def process(self, payload, metadata=None):
        received = utc_now()
        try:
            record = decode_energy(payload)
            self.forecaster.validate_source(record)
            result = self.processor.process(record)
        except InvalidMessage as exc:
            self.rejected.save(payload, str(exc), metadata)
            self.rejected_count += 1
            return False
        features = result["features"]
        prediction = self.forecaster.predict(features) if features is not None else None
        baseline = features["energy_wh"] if features is not None else None
        self.measurements.save({
            "event_id": record["event_id"], "building_id": record["building_id"],
            "source_id": record["source_id"], "source_type": record["source_type"],
            "measurement_timestamp": result["forecast_origin"], "received_at_utc": received,
            "timezone": record["timezone"], "timestamp_reference": record["timestamp_reference"],
            "interval_seconds": 600, "energy_scope": record["energy"]["scope"],
            "actual_energy_wh": record["energy"]["value"],
            "temperature_c": record["environment"]["temperature_c"],
            "relative_humidity_pct": record["environment"]["relative_humidity_pct"],
            "quality_flags_json": json.dumps(record["quality_flags"]),
            "additional_parameters_json": json.dumps(record["additional_parameters"], allow_nan=False),
            "feature_status": result["status"], "gap_detected": result["gap_detected"],
        })
        self.forecasts.save({
            "event_id": record["event_id"], "building_id": record["building_id"],
            "source_id": record["source_id"], "forecast_origin": result["forecast_origin"],
            "forecast_generated_at_utc": utc_now(),
            "forecast_target_timestamp": result["forecast_target_timestamp"],
            "timezone": record["timezone"], "timestamp_reference": record["timestamp_reference"],
            "horizon_seconds": 600, "predicted_energy_wh": prediction,
            "baseline_energy_wh": baseline, "status": result["status"],
            "model_version": self.forecaster.metadata["model_version"],
        })
        self.accepted += 1
        self.predicted += int(features is not None)
        return True

    def close(self):
        try:
            self.measurements.flush()
        finally:
            self.forecasts.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-messages", type=int)
    parser.add_argument("--idle-timeout-ms", type=int, default=0)
    args = parser.parse_args()
    if (args.max_messages is not None and args.max_messages < 1) or args.idle_timeout_ms < 0:
        parser.error("Invalid message limit or timeout")
    settings = EnergySettings.from_env()
    pipeline = EnergyPipeline(settings, EnergyForecaster.load(args.model))
    consumer = None
    try:
        consumer = KafkaConsumer(settings.topic, bootstrap_servers=settings.bootstrap_servers,
                                 group_id=settings.group_id, auto_offset_reset="earliest",
                                 enable_auto_commit=True,
                                 consumer_timeout_ms=args.idle_timeout_ms or float("inf"))
        with threadpool_limits(limits=1):
            for message in consumer:
                pipeline.process(message.value, {"topic": message.topic, "partition": message.partition, "offset": message.offset})
                if args.max_messages is not None and pipeline.accepted + pipeline.rejected_count >= args.max_messages:
                    break
    except KeyboardInterrupt:
        print("Energy consumer interrupted")
    finally:
        try:
            pipeline.close()
        finally:
            if consumer is not None:
                consumer.close()
    print(f"Energy consumer: accepted={pipeline.accepted}, rejected={pipeline.rejected_count}, predicted={pipeline.predicted}")


if __name__ == "__main__":
    main()
