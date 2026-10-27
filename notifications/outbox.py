"""Only called on INSERT of an episode, using the worker's existing transaction."""
from datetime import timedelta
import hashlib
import json
from sqlalchemy import select,insert,text
from storage.postgres import schema as s
from notifications.config import EmailConfig


def enqueue(c,kind,episode,mid,record,details,config=None):
    cfg=config or EmailConfig.from_env()
    if not cfg.accepts(kind,episode['run_id'],record['building_id'],record['source_id']): return None
    method=episode.get('detector',episode.get('rule_version'))
    if kind=='combined' and (not method.endswith('unanimous') or details.get('trigger_count')!=3): return None
    key=[kind,episode['episode_id'],cfg.recipient]
    ident=hashlib.sha256(json.dumps(key).encode()).hexdigest()
    # Serialize this category's cooldown across all worker processes, not only a source's current episode.
    scope=[episode['run_id'],record['building_id'],record['source_id'],kind,method,cfg.recipient]
    token=int.from_bytes(hashlib.sha256(json.dumps(scope).encode()).digest()[:8],signed=True)
    c.execute(text('SELECT pg_advisory_xact_lock(:token)'),{'token':token})
    if c.execute(select(s.notifications.c.notification_id).where(s.notifications.c.notification_id==ident)).first(): return ident
    stamp=c.execute(select(s.measurements.c.received_at,s.measurements.c.time_basis).where(s.measurements.c.measurement_id==mid)).mappings().one()
    now=c.execute(text('SELECT clock_timestamp()')).scalar_one()
    previous=c.execute(select(s.notifications.c.created_at).where(
        s.notifications.c.run_id==episode['run_id'],s.notifications.c.building_id==record['building_id'],
        s.notifications.c.source_id==record['source_id'],s.notifications.c.kind==kind,s.notifications.c.method==method,
        s.notifications.c.recipient==cfg.recipient,s.notifications.c.status!='suppressed').order_by(s.notifications.c.created_at.desc()).limit(1)).scalar()
    suppressed=bool(previous and now-previous<timedelta(minutes=cfg.cooldown_minutes))
    payload={'episode_id':episode['episode_id'],'run_id':episode['run_id'],'building_id':record['building_id'],
        'source_id':record['source_id'],'measurement_timestamp':record['timestamp'],'time_basis':stamp['time_basis'],
        'processed_at':stamp['received_at'].isoformat(),'energy_wh':record['energy']['value'],
        'interval_seconds':record['interval_seconds'],'kind':kind,'method':method,'experimental':True,**details}
    c.execute(insert(s.notifications).values(notification_id=ident,episode_id=episode['episode_id'],run_id=episode['run_id'],
        building_id=record['building_id'],source_id=record['source_id'],kind=kind,method=method,recipient=cfg.recipient,
        config_fingerprint=cfg.fingerprint,payload=payload,status='suppressed' if suppressed else 'pending',
        suppression_reason='cooldown' if suppressed else None,created_at=now,next_retry_at=now))
    return ident
