"""Rule assessments, hybrid episodes and source snapshots inside caller transaction."""
from datetime import timedelta
from sqlalchemy import select,insert,update,and_,text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from storage.postgres import schema as base
from storage.postgres import rules_schema as s
from storage.postgres.repository import identity,where_source,RepositoryError
from integration.runtime import now,RecoveryError
from processing.energy_schema import parse_timestamp


def require_schema(engine):
    try:
        with engine.connect() as c:
            revision=c.execute(text('SELECT version_num FROM alembic_rule_layer_version')).scalar_one()
        if revision!='0001_rules':raise RepositoryError('Unsupported optional rule-layer schema')
    except RepositoryError:raise
    except Exception:
        raise RepositoryError('Rule layer enabled but optional schema missing; run alembic -c alembic-rules.ini upgrade head') from None


def restore_rows(repo):
    with repo.engine.connect() as c:
        rows=[]
        saved_rows=list(c.execute(select(s.states).where(s.states.c.run_id==repo.settings.run_id)).mappings())
        keys={(x['building_id'],x['source_id']) for x in saved_rows}
        assessed=c.execute(select(base.measurements.c.building_id,base.measurements.c.source_id).join(
            s.assessments,s.assessments.c.measurement_id==base.measurements.c.measurement_id).where(
            base.measurements.c.run_id==repo.settings.run_id).distinct()).all()
        if any(tuple(k) not in keys for k in assessed):
            raise RecoveryError('Missing committed rule snapshot; refusing cold recovery')
        for saved in saved_rows:
            anchor=c.execute(select(base.measurements).where(base.measurements.c.measurement_id==saved['measurement_id'])).mappings().one()
            if (anchor['run_id'],anchor['building_id'],anchor['source_id'],anchor['kafka_offset'],anchor['measurement_timestamp'])!=(saved['run_id'],saved['building_id'],saved['source_id'],saved['last_offset'],saved['last_timestamp']):
                raise RecoveryError('Rule snapshot source/offset anchor mismatch')
            latest_assessed=c.execute(select(base.measurements.c.measurement_id).join(s.assessments,
                s.assessments.c.measurement_id==base.measurements.c.measurement_id).where(
                where_source(base.measurements,repo.settings.run_id,saved)).order_by(base.measurements.c.kafka_offset.desc()).limit(1)).scalar_one_or_none()
            if latest_assessed!=saved['measurement_id']:
                raise RecoveryError('Rule snapshot does not anchor latest committed assessment')
            latest=c.execute(select(base.measurements.c.measurement_id).where(where_source(base.measurements,repo.settings.run_id,saved)).order_by(base.measurements.c.kafka_offset.desc()).limit(1)).scalar_one()
            rows.append({**dict(saved),'event_id':anchor['event_id'],'wire_record':anchor['wire_record'],'stale':latest!=saved['measurement_id']})
        return rows


def persist(repo,c,offset,mid,record,result):
    run=repo.settings.run_id;version=result['layer_version']
    for signal in result['signals']:
        c.execute(insert(s.assessments).values(assessment_id=identity(mid,version,signal['rule']),measurement_id=mid,run_id=run,
            rule=signal['rule'],category=signal['category'],rule_version=result['rule_version'],layer_version=version,
            configuration=result['configuration'],flag=signal['flag'],status=signal['status'],evidence=signal['evidence'],
            activation=result['activation'],maturity='experimental'))
    versions={'residual':result['configuration']['inputs']['residual'],'sustained_high':result['rule_version']}
    decision=result['decision']
    c.execute(insert(s.decisions).values(decision_id=identity(mid,version),measurement_id=mid,run_id=run,channel='residual_or_sustained_high',
        layer_version=version,configuration=result['configuration'],input_versions=versions,maturity='experimental',**decision))
    old=c.execute(select(s.episodes).where(where_source(s.episodes,run,record),s.episodes.c.status=='open').with_for_update()).mappings().first()
    if old:
        contiguous=parse_timestamp(record['timestamp'])-parse_timestamp(old['end_timestamp'])==timedelta(seconds=600)
        reason=('configuration_changed' if old['layer_version']!=version else
                'activation_gap' if result['activation']=='activation_gap' else
                'gap' if not contiguous else 'negative' if decision['flag'] is False else 'unknown' if decision['flag'] is None else None)
        if reason:
            c.execute(update(s.episodes).where(s.episodes.c.episode_id==old['episode_id']).values(status='closed',closed_reason=reason,updated_at=now()))
            old=None
    if decision['flag'] is True:
        if old:
            c.execute(update(s.episodes).where(s.episodes.c.episode_id==old['episode_id']).values(
                end_measurement_id=mid,end_timestamp=record['timestamp'],flagged_points=old['flagged_points']+1,
                triggered_inputs=sorted(set(old['triggered_inputs'])|set(decision['triggered_inputs'])),updated_at=now()))
        else:
            c.execute(insert(s.episodes).values(episode_id=identity(mid,version,'hybrid'),run_id=run,building_id=record['building_id'],source_id=record['source_id'],
                layer_version=version,input_versions=versions,maturity='experimental',start_measurement_id=mid,end_measurement_id=mid,
                start_timestamp=record['timestamp'],end_timestamp=record['timestamp'],flagged_points=1,triggered_inputs=decision['triggered_inputs'],status='open'))
    values=dict(run_id=run,building_id=record['building_id'],source_id=record['source_id'],layer_version=version,
                state=result['state'],state_sha256=result['state_sha256'],measurement_id=mid,last_offset=offset,last_timestamp=parse_timestamp(record['timestamp']).isoformat())
    c.execute(pg_insert(s.states).values(**values).on_conflict_do_update(
        index_elements=['run_id','building_id','source_id'],set_={**values,'updated_at':now()}))
