"""Separate inference-only consumer, group and Parquet output for Stage 4."""
import argparse
from pathlib import Path
from kafka import KafkaConsumer
from threadpoolctl import threadpool_limits
import torch
from config import EnergySettings
from anomaly.artifacts import Bundle
from anomaly.residual import StreamDetector
from processing.energy_schema import decode_energy
from processing.message_schema import InvalidMessage
from storage.energy_anomaly_storage import anomaly_storage
from storage.rejected_storage import RejectedStorage


class AnomalyPipeline:
    def __init__(self, bundle, output, batch_size=1000):
        self.detector = StreamDetector(bundle)
        self.archive = anomaly_storage(Path(output) / 'anomalies', batch_size)
        self.rejected = RejectedStorage(Path(output) / 'rejected.jsonl')
        self.accepted = self.rejected_count = 0

    def process(self, payload, metadata=None):
        try:
            record = decode_energy(payload)
            record.pop('quality_flags')  # Internal normalization metadata is not part of wire schema.
            result = self.detector.process(record)
        except InvalidMessage as exc:
            self.rejected.save(payload, str(exc), metadata)
            self.rejected_count += 1
            return False
        self.archive.save(result)
        self.accepted += 1
        return True

    def close(self):
        self.archive.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--topic')
    parser.add_argument('--group', default='energy-anomaly-v1')
    parser.add_argument('--output', type=Path, default=Path('data/energy/anomalies-v1'))
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--max-messages', type=int)
    parser.add_argument('--idle-timeout-ms', type=int, default=0)
    args = parser.parse_args()
    if args.batch_size < 1 or args.idle_timeout_ms < 0 or (args.max_messages is not None and args.max_messages < 1):
        parser.error('Invalid batch size, timeout or message count')
    torch.set_num_threads(1)
    settings = EnergySettings.from_env()
    pipeline = AnomalyPipeline(Bundle.load(args.model), args.output, args.batch_size)
    consumer = None
    try:
        consumer = KafkaConsumer(args.topic or settings.topic, bootstrap_servers=settings.bootstrap_servers,
                                 group_id=args.group, auto_offset_reset='earliest', enable_auto_commit=True,
                                 consumer_timeout_ms=args.idle_timeout_ms or float('inf'))
        with threadpool_limits(1):
            for message in consumer:
                pipeline.process(message.value, {'topic': message.topic, 'partition': message.partition, 'offset': message.offset})
                if args.max_messages and pipeline.accepted + pipeline.rejected_count >= args.max_messages:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pipeline.close()
        finally:
            if consumer:
                consumer.close()
    print(f'Anomaly consumer: accepted={pipeline.accepted}, rejected={pipeline.rejected_count}')


if __name__ == '__main__':
    main()
