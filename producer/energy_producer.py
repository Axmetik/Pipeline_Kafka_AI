"""Replay interval energy with original event times and configurable wall-clock speed."""
import argparse
import json
import math
import time

from kafka import KafkaProducer
from config import EnergySettings
from producer.appliances_dataset import iter_appliances


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--building-id", default="appliances-house-1")
    parser.add_argument("--source-id", default="uci-appliances")
    speed = parser.add_mutually_exclusive_group()
    speed.add_argument("--sleep", type=float, default=None, help="Fixed delay between messages; default 0")
    speed.add_argument("--speed", type=float, help="Replay multiplier: 60 means 600 seconds in 10 seconds")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.sleep is not None and (not math.isfinite(args.sleep) or args.sleep < 0):
        parser.error("--sleep must be finite and non-negative")
    if args.speed is not None and (not math.isfinite(args.speed) or args.speed <= 0):
        parser.error("--speed must be finite and positive")
    settings = EnergySettings.from_env()
    producer = KafkaProducer(bootstrap_servers=settings.bootstrap_servers,
                             value_serializer=lambda record: json.dumps(record, allow_nan=False).encode())
    sent = 0
    previous_time = None
    from processing.energy_schema import parse_timestamp
    try:
        for record in iter_appliances(args.dataset, args.building_id, args.source_id,
                                      args.start, args.end, args.limit):
            timestamp = parse_timestamp(record["timestamp"])
            if previous_time is not None:
                delay = (timestamp - previous_time).total_seconds() / args.speed if args.speed else (args.sleep or 0)
                if delay:
                    time.sleep(delay)
            key = json.dumps([record["building_id"], record["source_id"]]).encode()
            producer.send(settings.topic, record, key=key).get(timeout=30)
            sent += 1
            previous_time = timestamp
    finally:
        producer.close(timeout=30)
    print(f"Energy producer: sent={sent}, topic={settings.topic}")


if __name__ == "__main__":
    main()
