"""Read-only CLI inspection for Stage 5A; HTTP endpoints belong to Stage 5B."""
import argparse
import json
from datetime import datetime
from sqlalchemy import create_engine,select,func
from integration.settings import Settings
from storage.postgres import schema as s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id');parser.add_argument('--list-runs',action='store_true')
    args=parser.parse_args();settings=Settings.from_env();engine=create_engine(settings.database_url)
    try:
        with engine.connect() as c:
            if args.list_runs:
                result=[dict(r) for r in c.execute(select(s.runs.c.run_id,s.runs.c.topic,s.runs.c.created_at).order_by(s.runs.c.created_at.desc()).limit(20)).mappings()]
            else:
                run_id=args.run_id or settings.run_id
                result={'run_id':run_id,'counts':{}}
                for table in (s.measurements,s.forecasts,s.scores,s.episodes,s.errors,s.receipts):
                    result['counts'][table.name]=c.execute(select(func.count()).select_from(table).where(table.c.run_id==run_id)).scalar_one()
                result['checkpoints']=[dict(r) for r in c.execute(select(s.checkpoints.c.topic,s.checkpoints.c.partition,s.checkpoints.c.next_offset,s.checkpoints.c.updated_at).where(s.checkpoints.c.run_id==run_id)).mappings()]
                result['note']='Anomaly scores/episodes are experimental; no confirmed fault labels.'
        print(json.dumps(result,indent=2,default=lambda v:v.isoformat() if isinstance(v,datetime) else str(v)))
    finally: engine.dispose()


if __name__=='__main__': main()
