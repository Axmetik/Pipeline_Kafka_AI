"""Durable bounded retry. SMTP runs only here, never in the Kafka transaction."""
import argparse
from datetime import timedelta
import json
import smtplib
import ssl
import time
from uuid import uuid4
from sqlalchemy import select,update,and_,or_,text,create_engine
from storage.postgres import schema as s
from notifications.config import EmailConfig
from notifications.message import render


def smtp_send(message,cfg):
    factory=smtplib.SMTP_SSL if cfg.security=='ssl' else smtplib.SMTP
    extra={'context':ssl.create_default_context()} if cfg.security=='ssl' else {}
    with factory(cfg.host,cfg.port,timeout=cfg.timeout,**extra) as client:
        if cfg.security=='starttls': client.starttls(context=ssl.create_default_context())
        if cfg.username: client.login(cfg.username,cfg.password)
        refused=client.send_message(message)
        if refused: raise smtplib.SMTPRecipientsRefused(refused)


def category(exc):
    if isinstance(exc,smtplib.SMTPAuthenticationError): return 'smtp_authentication',False
    if isinstance(exc,smtplib.SMTPRecipientsRefused):
        temporary=all(400<=value[0]<500 for value in exc.recipients.values())
        return ('smtp_temporary' if temporary else 'smtp_recipient'),temporary
    if isinstance(exc,smtplib.SMTPResponseException):
        return ('smtp_temporary',True) if 400<=exc.smtp_code<500 else ('smtp_permanent',False)
    if isinstance(exc,(TimeoutError,OSError,smtplib.SMTPServerDisconnected)): return 'smtp_connection',True
    if isinstance(exc,(ValueError,UnicodeError)): return 'message_invalid',False
    return 'delivery_internal',False


def backoff(attempt): return min(30*2**(attempt-1),900)


def claim(engine,cfg):
    if not cfg.enabled: return None
    with engine.begin() as c:
        now=c.execute(text('SELECT clock_timestamp()')).scalar_one()
        due=or_(and_(s.notifications.c.status.in_(['pending','retrying']),s.notifications.c.next_retry_at<=now),
                and_(s.notifications.c.status=='sending',s.notifications.c.claimed_until<=now))
        row=c.execute(select(s.notifications).where(due,s.notifications.c.run_id==cfg.run_id,
            s.notifications.c.building_id==cfg.building_id,s.notifications.c.source_id==cfg.source_id)
            .order_by(s.notifications.c.created_at,s.notifications.c.notification_id).with_for_update(skip_locked=True).limit(1)).mappings().first()
        if row is None: return None
        q=update(s.notifications).where(s.notifications.c.notification_id==row['notification_id'])
        if row['config_fingerprint']!=cfg.fingerprint or row['recipient']!=cfg.recipient or not cfg.accepts(row['kind'],row['run_id'],row['building_id'],row['source_id']):
            c.execute(q.values(status='suppressed',suppression_reason='configuration_changed',claim_token=None,claimed_until=None))
            return {'notification_id':row['notification_id'],'status':'suppressed'}
        if row['attempt_count']>=cfg.max_attempts:
            c.execute(q.values(status='failed',error_category='attempt_limit',claim_token=None,claimed_until=None))
            return {'notification_id':row['notification_id'],'status':'failed'}
        token=uuid4().hex
        c.execute(q.values(status='sending',attempt_count=row['attempt_count']+1,claim_token=token,
                           claimed_until=now+timedelta(seconds=cfg.lease_seconds)))
        return {'notification_id':row['notification_id'],'claim_token':token,'status':'sending'}


def deliver(engine,cfg,task,transport=smtp_send):
    if task['status']!='sending': return task
    # A row lock spans only notifier SMTP I/O (timeout bounded), not worker rows.
    # SKIP LOCKED also prevents reclaiming an active sender even beyond lease expiry.
    with engine.begin() as c:
        row=c.execute(select(s.notifications).where(s.notifications.c.notification_id==task['notification_id']).with_for_update()).mappings().one()
        if row['status']!='sending' or row['claim_token']!=task['claim_token']: return {'status':'claim_lost'}
        now=c.execute(text('SELECT clock_timestamp()')).scalar_one()
        q=update(s.notifications).where(s.notifications.c.notification_id==row['notification_id'])
        try:
            transport(render(row,cfg,now),cfg)
        except Exception as exc:
            error,retry=category(exc)
            status='retrying' if retry and row['attempt_count']<cfg.max_attempts else 'failed'
            c.execute(q.values(status=status,error_category=error,next_retry_at=now+timedelta(seconds=backoff(row['attempt_count'])),claim_token=None,claimed_until=None))
        else:
            status='sent'
            c.execute(q.values(status=status,sent_at=c.execute(text('SELECT clock_timestamp()')).scalar_one(),error_category=None,claim_token=None,claimed_until=None))
        return {'notification_id':row['notification_id'],'status':status}


def tick(engine,cfg,transport=smtp_send):
    task=claim(engine,cfg)
    return deliver(engine,cfg,task,transport) if task else None


def main():
    from integration.settings import Settings
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--once',action='store_true');a=p.parse_args()
    cfg=EmailConfig.from_env()
    if not cfg.enabled: print('Email notifications disabled');return
    engine=create_engine(Settings.from_env().database_url,pool_pre_ping=True,hide_parameters=True,connect_args={'connect_timeout':3})
    try:
        while True:
            try:
                result=tick(engine,cfg)
                if result: print(json.dumps(result),flush=True)
            except Exception:
                # No driver/SMTP exception strings: may contain credentials or addresses.
                print('{"status":"notifier_error","error_category":"database_or_delivery_unavailable"}',flush=True)
                result=None
            if a.once: break
            if result is None: time.sleep(2)
    finally: engine.dispose()

if __name__=='__main__': main()
