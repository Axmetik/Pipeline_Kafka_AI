"""Create the configured MVP topic, then reuse the unchanged Energy producer."""
import argparse
import os
import subprocess
import sys
from pathlib import Path
from kafka.admin import KafkaAdminClient,NewTopic
from integration.settings import Settings,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=300)
    parser.add_argument('--sleep',type=float,default=.1)
    args=parser.parse_args()
    if args.limit<1 or args.sleep<0:
        parser.error('Use a positive limit and nonnegative sleep')
    settings=Settings.from_env()
    admin=KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    try:
        if settings.topic not in admin.list_topics():
            admin.create_topics([NewTopic(settings.topic,num_partitions=1,replication_factor=1)])
        topics=admin.describe_topics([settings.topic])
        if len(topics[0]['partitions'])!=1:
            parser.error('MVP topic must have exactly one partition')
    finally:
        admin.close()
    env={**os.environ,'KAFKA_BOOTSTRAP_SERVERS':settings.bootstrap_servers,'ENERGY_KAFKA_TOPIC':settings.topic}
    subprocess.run([sys.executable,'-m','producer.energy_producer','--dataset',str(args.dataset),
                    '--limit',str(args.limit),'--sleep',str(args.sleep)],cwd=ROOT,env=env,check=True)


if __name__=='__main__':
    main()
