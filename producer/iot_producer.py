"""Synthetic four-feature IoT producer with a reproducible finite demo mode."""
import argparse
import json
import random
import time
from datetime import datetime, timedelta, timezone

from kafka import KafkaProducer
from config import Settings


def generate_records(limit=None, seed=42, start=None):
    rng = random.Random(seed)
    start = start or datetime.now(timezone.utc)
    index = 0
    while limit is None or index < limit:
        yield {
            "sensor_id": rng.randint(1, 5),
            "timestamp": (start + timedelta(seconds=2 * index)).isoformat(),
            "temperature": round(rng.uniform(20.0, 35.0), 2),
            "humidity": round(rng.uniform(30.0, 80.0), 2),
            "light": round(rng.uniform(100.0, 800.0), 2),
            "voltage": round(rng.uniform(2.3, 3.0), 3),
        }
        index += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--start", help="ISO 8601 timestamp with timezone; fixes demo timestamps")
    args = parser.parse_args()
    if (args.limit is not None and args.limit < 1) or args.sleep < 0:
        parser.error("--limit must be positive and --sleep non-negative")
    try:
        start = datetime.fromisoformat(args.start) if args.start else None
        if start is not None and start.tzinfo is None:
            raise ValueError("--start needs a timezone")
    except ValueError as exc:
        parser.error(str(exc))
    settings = Settings.from_env()
    producer = KafkaProducer(
        bootstrap_servers=settings.bootstrap_servers,
        value_serializer=lambda value: json.dumps(value, allow_nan=False).encode("utf-8"),
    )
    try:
        for record in generate_records(args.limit, args.seed, start):
            producer.send(settings.topic, record).get(timeout=30)
            print(f"Sent: {record}")
            if args.sleep:
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("Producer stopped")
    finally:
        producer.close(timeout=30)


if __name__ == "__main__":
    main()
