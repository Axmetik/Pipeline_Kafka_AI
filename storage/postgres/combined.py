"""Derived result and DB-resident episode state; called inside the existing commit."""
from datetime import timedelta
from sqlalchemy import insert,select,update
from storage.postgres import schema as s
from processing.energy_schema import parse_timestamp

def persist_combined(repo,c,mid,record,scores,gap):
    from anomaly.combined import combine, NAMES
    from storage.postgres.repository import identity,where_source
    from integration.runtime import now
    decision=combine(scores)
    c.execute(insert(s.combined_decisions).values(decision_id=identity(mid,decision['rule_version']),
        measurement_id=mid,run_id=repo.settings.run_id,**decision))
    old=c.execute(select(s.combined_episodes).where(where_source(s.combined_episodes,repo.settings.run_id,record),
        s.combined_episodes.c.status=='open').with_for_update()).mappings().first()
    contiguous=bool(old and parse_timestamp(record['timestamp'])-parse_timestamp(old['end_timestamp'])==timedelta(seconds=600))
    changed=bool(old and (old['rule_version']!=decision['rule_version'] or old['input_versions']!=decision['input_versions']))
    if old and (decision['flag'] is not True or not contiguous or gap or changed):
        reason='context_changed' if changed else 'gap' if gap or not contiguous else 'below_rule' if decision['flag'] is False else 'unavailable'
        c.execute(update(s.combined_episodes).where(s.combined_episodes.c.episode_id==old['episode_id']).values(status='closed',closed_reason=reason,updated_at=now()))
        old=None
    if decision['flag'] is not True: return
    if old:
        union=[n for n in NAMES if n in set(old['triggered_methods'])|set(decision['triggered_methods'])]
        c.execute(update(s.combined_episodes).where(s.combined_episodes.c.episode_id==old['episode_id']).values(
            end_measurement_id=mid,end_timestamp=record['timestamp'],flagged_points=old['flagged_points']+1,
            max_trigger_count=max(old['max_trigger_count'],decision['trigger_count']),last_trigger_count=decision['trigger_count'],
            triggered_methods=union,updated_at=now()))
    else:
        episode_id=identity(mid,decision['rule_version'])
        c.execute(insert(s.combined_episodes).values(episode_id=episode_id,run_id=repo.settings.run_id,
            building_id=record['building_id'],source_id=record['source_id'],rule_version=decision['rule_version'],input_versions=decision['input_versions'],
            maturity='experimental',start_measurement_id=mid,end_measurement_id=mid,start_timestamp=record['timestamp'],end_timestamp=record['timestamp'],
            flagged_points=1,max_trigger_count=decision['trigger_count'],last_trigger_count=decision['trigger_count'],
            triggered_methods=decision['triggered_methods'],status='open'))

        from notifications.outbox import enqueue
        enqueue(c,'combined',{'episode_id':episode_id,'run_id':repo.settings.run_id,'rule_version':decision['rule_version']},mid,record,
            {k:decision[k] for k in ('trigger_count','triggered_methods','input_versions')},repo.email_config)
