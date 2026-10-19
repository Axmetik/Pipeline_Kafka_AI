"""Stage 5A: Kafka → causal scoring → atomic PostgreSQL → explicit Kafka commit."""
import argparse
import json
import time
from sqlalchemy import create_engine,select
from kafka import KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient
from kafka.structs import OffsetAndMetadata
from threadpoolctl import threadpool_limits
import torch
from integration.artifacts import load_manifest,ArtifactError
from integration.settings import Settings
from integration.checkpoints import reconcile,CheckpointError
from integration.processor import Processor,payload_digest
from storage.postgres.repository import Repository,RepositoryError
from storage.postgres.schema import receipts


def verify_journal(consumer,tp,repository,begin,next_offset):
    """Verify every retained processed record, not just one anchor or topic name."""
    if next_offset==0:
        return 0
    with repository.engine.connect() as c:
        expected=dict(c.execute(select(receipts.c.offset,receipts.c.payload_sha256).where(
            receipts.c.group_id==repository.settings.group_id,receipts.c.topic==tp.topic,
            receipts.c.partition==tp.partition,receipts.c.offset>=begin,receipts.c.offset<next_offset)).all())
    checkpoint=repository.checkpoint()
    if checkpoint['last_payload_sha256']!=expected.get(next_offset-1):
        raise CheckpointError('DB checkpoint digest differs from delivery ledger')
    if len(expected)!=next_offset-begin:
        raise CheckpointError('Incomplete DB delivery ledger for retained Kafka history')
    consumer.seek(tp,begin)
    position=begin;deadline=time.monotonic()+30
    while position<next_offset:
        messages=consumer.poll(timeout_ms=1000,max_records=min(500,next_offset-position)).get(tp,[])
        if not messages and time.monotonic()>deadline:
            raise CheckpointError('Cannot read committed Kafka journal for reconciliation')
        for message in messages:
            if message.offset!=position or payload_digest(message.key,message.value)!=expected.get(position):
                raise CheckpointError('Available Kafka journal differs from DB ledger; no silent seek past changed data')
            position+=1
    return next_offset-begin


def _run_worker(settings,max_messages=None,idle_timeout=None,failpoint=None):
    if max_messages is not None and max_messages<1:
        raise ValueError('max_messages must be positive')
    artifacts=load_manifest(settings.artifact_manifest)
    torch.set_num_threads(1)
    engine=create_engine(settings.database_url,pool_pre_ping=True)
    consumer=admin=None
    counts={'accepted':0,'message_duplicate':0,'offset_duplicate':0,'quarantined':0,'processed_deliveries':0}
    try:
        repo=Repository(engine,settings)
        with repo.worker_lock() as ownership:
            admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
            cluster=admin.describe_cluster().get('cluster_id')
            if not cluster:
                raise CheckpointError('Kafka cluster identity unavailable')
            repo.initialize(artifacts,cluster)
            consumer=KafkaConsumer(bootstrap_servers=settings.bootstrap_servers,group_id=settings.group_id,
                                   enable_auto_commit=False,auto_offset_reset='none')
            partitions=consumer.partitions_for_topic(settings.topic)
            if partitions!={0}:
                raise CheckpointError('MVP requires an existing single-partition topic; create it explicitly')
            tp=TopicPartition(settings.topic,0);consumer.assign([tp])
            begin,end=consumer.beginning_offsets([tp])[tp],consumer.end_offsets([tp])[tp]
            committed=consumer.committed(tp)
            checkpoint=repo.checkpoint()
            next_offset=reconcile(begin,end,committed,checkpoint['next_offset'] if checkpoint else None)
            verified=verify_journal(consumer,tp,repo,begin,next_offset)
            repo.create_checkpoint(next_offset)
            processor=Processor(repo,artifacts,failpoint)
            consumer.seek(tp,next_offset)
            # Also align a lagging/missing broker commit after verified DB recovery.
            if committed!=next_offset:
                consumer.commit({tp:OffsetAndMetadata(next_offset,'mvp-db',-1)})
            print(json.dumps({'state':'ready','run_id':settings.run_id,'topic':settings.topic,
                              'db_next_offset':next_offset,'verified_journal_records':verified,
                              'models':'HGB20 primary; RF21 residual; detectors experimental'}),flush=True)
            last_message=time.monotonic()
            with threadpool_limits(1):
                while max_messages is None or counts['processed_deliveries']<max_messages:
                    ownership()
                    messages=consumer.poll(timeout_ms=1000,max_records=1).get(tp,[])
                    if not messages:
                        if idle_timeout is not None and time.monotonic()-last_message>=idle_timeout:
                            break
                        continue
                    for message in messages:
                        outcome=processor.process(message.offset,message.key,message.value)
                        # Only reachable after a committed domain transaction/checkpoint.
                        consumer.commit({tp:OffsetAndMetadata(outcome['next_offset'],'mvp-db',-1)})
                        category=outcome['outcome']
                        counts[category if category in counts else 'quarantined']+=1
                        counts['processed_deliveries']+=1
                        next_offset=outcome['next_offset'];last_message=time.monotonic()
                        if counts['processed_deliveries']%50==0:
                            print(json.dumps({'state':'processing','db_next_offset':next_offset,**counts}),flush=True)
            report={'run_id':settings.run_id,'db_next_offset':next_offset,'verified_journal_records':verified,**counts}
            print(json.dumps({'state':'stopped',**report}),flush=True)
            return report
    finally:
        # Never auto-commit during error cleanup.
        if consumer is not None:
            consumer.close(autocommit=False)
        if admin is not None:
            admin.close()
        engine.dispose()


def run_worker(settings,max_messages=None,idle_timeout=None,failpoint=None):
    # Recovery, not just the steady-state loop, must use the same thread policy.
    with threadpool_limits(1):
        return _run_worker(settings,max_messages,idle_timeout,failpoint)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--max-messages',type=int)
    p.add_argument('--idle-timeout',type=float)
    a=p.parse_args()
    if a.idle_timeout is not None and a.idle_timeout<=0:
        p.error('idle-timeout must be positive')
    try:
        run_worker(Settings.from_env(),a.max_messages,a.idle_timeout)
    except (ArtifactError,RepositoryError,CheckpointError,ValueError) as exc:
        p.exit(2,str(exc)+'\n')
    except KeyboardInterrupt:
        p.exit(130,'Worker interrupted; committed DB checkpoint is preserved\n')
    except Exception as exc:
        # Do not print a DB URL or credentials in a traceback.
        p.exit(1,f'Worker stopped safely ({type(exc).__name__}). No automatic offset advance; see docs/stage5/5a-runbook.md\n')


if __name__=='__main__':
    main()
