"""Transactional ledger, domain records and checkpoint. PostgreSQL only."""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json

from sqlalchemy import select,insert,update,text,and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from storage.postgres import schema as s
from integration.runtime import clock,now,RecoveryError
from processing.energy_schema import parse_timestamp,validate_energy
from ai.energy_forecaster import source_binding


class RepositoryError(RuntimeError):
    pass


def identity(*values):
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def where_source(table,run,record):
    return and_(table.c.run_id==run,table.c.building_id==record['building_id'],table.c.source_id==record['source_id'])


class Repository:
    def __init__(self,engine,settings):
        self.engine,self.settings=engine,settings
        self.registry={}
        try:
            with engine.connect() as c:
                version=c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                if version!='0002_combined':
                    raise RepositoryError('Unsupported DB revision; apply reviewed Alembic migrations')
        except RepositoryError:
            raise
        except Exception:
            raise RepositoryError('PostgreSQL unavailable or schema missing. Run alembic upgrade head; see docs/stage5/5a-runbook.md') from None

    @contextmanager
    def worker_lock(self):
        token=int.from_bytes(hashlib.sha256((self.settings.group_id+'|'+self.settings.topic).encode()).digest()[:8],signed=True)
        with self.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            locked=connection.execute(text('SELECT pg_try_advisory_lock(:key)'),{'key':token}).scalar_one()
            if not locked:
                raise RepositoryError('Another worker owns this consumer group/topic')
            pid=connection.execute(text('SELECT pg_backend_pid()')).scalar_one()
            def heartbeat():
                if connection.execute(text('SELECT pg_backend_pid()')).scalar_one()!=pid:
                    raise RepositoryError('Worker ownership connection changed; stopping')
            try:
                yield heartbeat
            finally:
                if not connection.invalidated:
                    connection.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':token})

    def initialize(self,artifacts,cluster_id):
        self.registry={row['role']:row for row in artifacts.registry()}
        values={'run_id':self.settings.run_id,'group_id':self.settings.group_id,'topic':self.settings.topic,
                'cluster_id':cluster_id,'manifest_sha256':artifacts.manifest_sha256,
                'config':{'worker_schema':'mvp-worker-v1','partitions':[0],'artifact_ids':{k:v['model_id'] for k,v in self.registry.items()}}}
        with self.engine.begin() as c:
            for row in self.registry.values():
                c.execute(pg_insert(s.models).values(**row).on_conflict_do_nothing())
                old=c.execute(select(s.models).where(s.models.c.model_id==row['model_id'])).mappings().one()
                if any(old[k]!=v for k,v in row.items()):
                    raise RepositoryError('Registered model metadata differs; cannot silently replace artifacts')
            existing=c.execute(select(s.runs).where(s.runs.c.run_id==self.settings.run_id)).mappings().first()
            if existing:
                if any(existing[k]!=v for k,v in values.items()):
                    raise RepositoryError('Run identity, cluster, group, topic or artifact context changed; use a new run/group')
            else:
                other=c.execute(select(s.runs.c.run_id).where(s.runs.c.group_id==self.settings.group_id)).scalar()
                if other:
                    raise RepositoryError('Consumer group already belongs to another run')
                c.execute(insert(s.runs).values(**values))

    def checkpoint_filter(self):
        return and_(s.checkpoints.c.group_id==self.settings.group_id,s.checkpoints.c.topic==self.settings.topic,s.checkpoints.c.partition==0)

    def checkpoint(self,c=None,lock=False):
        query=select(s.checkpoints).where(self.checkpoint_filter())
        if lock:
            query=query.with_for_update()
        if c is None:
            with self.engine.connect() as own:
                return own.execute(query).mappings().first()
        return c.execute(query).mappings().first()

    def create_checkpoint(self,next_offset=0):
        with self.engine.begin() as c:
            old=self.checkpoint(c,lock=True)
            if old:
                if old['run_id']!=self.settings.run_id:
                    raise RepositoryError('Checkpoint belongs to another run')
                return
            if c.execute(select(s.receipts.c.offset).where(s.receipts.c.group_id==self.settings.group_id).limit(1)).first():
                raise RepositoryError('DB ledger exists without checkpoint; manual recovery required')
            c.execute(insert(s.checkpoints).values(group_id=self.settings.group_id,topic=self.settings.topic,
                      partition=0,run_id=self.settings.run_id,next_offset=next_offset))

    def receipt(self,c,offset):
        return c.execute(select(s.receipts).where(s.receipts.c.group_id==self.settings.group_id,
                         s.receipts.c.topic==self.settings.topic,s.receipts.c.partition==0,s.receipts.c.offset==offset)).mappings().first()

    def existing_event(self,c,record):
        return c.execute(select(s.measurements).where(where_source(s.measurements,self.settings.run_id,record),
                         s.measurements.c.event_id==record['event_id'])).mappings().first()

    def source_problem(self,c,record):
        binding=source_binding(record)
        previous=c.execute(select(s.sources).where(s.sources.c.building_id==record['building_id'],s.sources.c.source_id==record['source_id'])).mappings().first()
        if previous and previous['binding']!=binding:
            return 'source_conflict','Measurement semantics changed for existing source'
        latest=c.execute(select(s.measurements.c.measurement_timestamp).where(where_source(s.measurements,self.settings.run_id,record))
                         .order_by(s.measurements.c.kafka_offset.desc()).limit(1)).scalar()
        if latest and parse_timestamp(record['timestamp'])<=parse_timestamp(latest):
            return 'out_of_order','New event is duplicate-time or out-of-order; history unchanged'
        if not previous:
            c.execute(insert(s.sources).values(building_id=record['building_id'],source_id=record['source_id'],binding=binding))
        return None

    def finish(self,c,offset,digest,outcome,measurement_id=None,error=None):
        c.execute(insert(s.receipts).values(group_id=self.settings.group_id,topic=self.settings.topic,partition=0,
                  offset=offset,run_id=self.settings.run_id,payload_sha256=digest,outcome=outcome,measurement_id=measurement_id))
        if error:
            c.execute(insert(s.errors).values(error_id=identity(self.settings.group_id,self.settings.topic,offset),
                      run_id=self.settings.run_id,topic=self.settings.topic,partition=0,offset=offset,**error))
        c.execute(update(s.checkpoints).where(self.checkpoint_filter()).values(next_offset=offset+1,last_payload_sha256=digest,updated_at=now()))

    def persist(self,c,offset,raw,record,normalized_sha,result):
        mid=identity(self.settings.run_id,record['building_id'],record['source_id'],record['event_id'])
        stamp=clock(record['timestamp'])
        c.execute(insert(s.measurements).values(measurement_id=mid,run_id=self.settings.run_id,
                  building_id=record['building_id'],source_id=record['source_id'],event_id=record['event_id'],kafka_offset=offset,
                  measurement_timestamp=parse_timestamp(record['timestamp']).isoformat(),measurement_time_local=stamp['local'],
                  measurement_time_utc=stamp['utc'],time_basis=stamp['basis'],timezone=record['timezone'],
                  timestamp_reference=record['timestamp_reference'],interval_seconds=record['interval_seconds'],energy_wh=record['energy']['value'],
                  environment=record['environment'],wire_record=raw,normalized_sha256=normalized_sha,compatible=result['compatible'],
                  feature_status=result['feature_status'],gap_detected=result['gap_detected']))
        for forecast in result['forecasts']:
            fid=identity(mid,forecast['model_id'],forecast['purpose'])
            c.execute(insert(s.forecasts).values(forecast_id=fid,run_id=self.settings.run_id,measurement_id=mid,**forecast))
        for score in result['scores']:
            reference=None
            if score['detector']=='residual' and score['prediction_wh'] is not None:
                reference=c.execute(select(s.forecasts).join(s.measurements,s.forecasts.c.measurement_id==s.measurements.c.measurement_id)
                    .where(where_source(s.measurements,self.settings.run_id,record),s.forecasts.c.model_id==self.registry['residual_reference']['model_id'],
                           s.forecasts.c.forecast_origin==score['forecast_origin'],s.forecasts.c.forecast_target_timestamp==score['forecast_target_timestamp'])).mappings().one_or_none()
                if (reference is None or reference['predicted_energy_wh']!=score['prediction_wh']
                        or reference['generated_at']!=score['reference_generated_at']):
                    raise RecoveryError('Residual does not refer to the exact previously committed forecast')
            c.execute(insert(s.scores).values(score_id=identity(mid,score['model_id'],score['threshold_version']),
                      run_id=self.settings.run_id,measurement_id=mid,
                      reference_forecast_id=reference['forecast_id'] if reference else None,**score))
            self.update_episode(c,mid,record,score,result['gap_detected'])
        from storage.postgres.combined import persist_combined
        persist_combined(self,c,mid,record,result['scores'],result['gap_detected'])
        return mid

    def update_episode(self,c,mid,record,score,gap):
        query=select(s.episodes).where(where_source(s.episodes,self.settings.run_id,record),
                s.episodes.c.model_id==score['model_id'],s.episodes.c.threshold_version==score['threshold_version'],s.episodes.c.status=='open')
        old=c.execute(query.with_for_update()).mappings().first()
        contiguous=bool(old and parse_timestamp(record['timestamp'])-parse_timestamp(old['end_timestamp'])==timedelta(seconds=600))
        if old and (score['flag'] is not True or not contiguous or gap):
            reason='gap' if not contiguous or gap else ('below_threshold' if score['flag'] is False else 'unknown')
            c.execute(update(s.episodes).where(s.episodes.c.episode_id==old['episode_id']).values(status='closed',closed_reason=reason,updated_at=now()))
            old=None
        if score['flag'] is not True:
            return
        if old:
            c.execute(update(s.episodes).where(s.episodes.c.episode_id==old['episode_id']).values(
                end_measurement_id=mid,end_timestamp=record['timestamp'],flagged_points=old['flagged_points']+1,updated_at=now()))
        else:
            c.execute(insert(s.episodes).values(episode_id=identity(mid,score['model_id'],score['threshold_version']),
                run_id=self.settings.run_id,building_id=record['building_id'],source_id=record['source_id'],
                model_id=score['model_id'],detector=score['detector'],model_version=score['model_version'],feature_version=score['feature_version'],
                threshold_version=score['threshold_version'],maturity='experimental',start_measurement_id=mid,end_measurement_id=mid,
                start_timestamp=record['timestamp'],end_timestamp=record['timestamp'],flagged_points=1,status='open'))

    def histories(self):
        with self.engine.connect() as c:
            keys=c.execute(select(s.measurements.c.building_id,s.measurements.c.source_id)
                           .where(s.measurements.c.run_id==self.settings.run_id,s.measurements.c.compatible.is_(True)).distinct()).all()
            result=[]
            for building,source in keys:
                condition=and_(s.measurements.c.run_id==self.settings.run_id,s.measurements.c.building_id==building,
                               s.measurements.c.source_id==source,s.measurements.c.compatible.is_(True))
                rows=list(c.execute(select(s.measurements).where(condition).order_by(s.measurements.c.kafka_offset.desc()).limit(144)).mappings())
                rows.reverse()
                for row in rows:
                    if identity(validate_energy(row['wire_record'])) != row['normalized_sha256']:
                        raise RecoveryError('Committed history fingerprint mismatch; refusing model-state recovery')
                pending=list(c.execute(select(s.forecasts).where(s.forecasts.c.measurement_id==rows[-1]['measurement_id'])).mappings())
                result.append(([row['wire_record'] for row in rows],pending))
            return result
