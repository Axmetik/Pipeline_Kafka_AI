"""Validate trusted artifacts and create an empty one-partition topic before worker start."""
from kafka.admin import KafkaAdminClient,NewTopic
from integration.artifacts import load_manifest,ArtifactError
from integration.settings import Settings


def main():
    settings=Settings.from_env()
    load_manifest(settings.artifact_manifest)
    admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    try:
        if settings.topic not in admin.list_topics():
            admin.create_topics([NewTopic(settings.topic,num_partitions=1,replication_factor=1)])
        if len(admin.describe_topics([settings.topic])[0]['partitions'])!=1:
            raise ValueError('MVP topic must have exactly one partition')
    finally: admin.close()
    print('Trusted artifacts verified; single-partition topic ready (no measurements sent)')

if __name__=='__main__':
    try: main()
    except (ArtifactError,ValueError) as exc: raise SystemExit(str(exc)) from None
