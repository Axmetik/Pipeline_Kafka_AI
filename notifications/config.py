"""Explicit opt-in, exact delivery scope and no credential-bearing repr/logs."""
from dataclasses import dataclass, field
from email.utils import parseaddr
import hashlib
import json
import os


def boolean(value):
    if str(value).lower() not in ('true','false'): raise ValueError('Expected true or false')
    return str(value).lower()=='true'


def address(value):
    if not value or '\r' in value or '\n' in value or parseaddr(value)[1]!=value or value.count('@')!=1 or any(c.isspace() for c in value):
        raise ValueError('Expected one plain email address')
    local,domain=value.split('@')
    if not local or not domain or len(value)>254: raise ValueError('Invalid email address')
    value.encode('ascii')  # SMTPUTF8 is not part of this MVP.
    return value


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool=False
    mode: str='individual'
    host: str='mailpit'
    port: int=1025
    username: str=field(default='',repr=False)
    password: str=field(default='',repr=False)
    security: str='none'
    sender: str=''
    recipient: str=''
    run_id: str=''
    building_id: str=''
    source_id: str=''
    cooldown_minutes: int=30
    real_delivery: bool=False
    timeout: int=10
    max_attempts: int=5
    lease_seconds: int=120

    @classmethod
    def from_env(cls,env=None):
        e=os.environ if env is None else env
        cfg=cls(enabled=boolean(e.get('EMAIL_NOTIFICATIONS_ENABLED','false')),
            mode=e.get('EMAIL_ALERT_MODE','individual'),host=e.get('EMAIL_SMTP_HOST','mailpit'),
            port=int(e.get('EMAIL_SMTP_PORT','1025')),username=e.get('EMAIL_SMTP_USERNAME',''),password=e.get('EMAIL_SMTP_PASSWORD',''),
            security=e.get('EMAIL_SMTP_SECURITY','none'),sender=e.get('EMAIL_FROM',''),recipient=e.get('EMAIL_TO',''),
            run_id=e.get('EMAIL_RUN_ID',''),building_id=e.get('EMAIL_BUILDING_ID',''),source_id=e.get('EMAIL_SOURCE_ID',''),
            cooldown_minutes=int(e.get('EMAIL_COOLDOWN_MINUTES','30')),
            real_delivery=boolean(e.get('EMAIL_REAL_DELIVERY_ENABLED','false')))
        return cfg.validate()

    def validate(self):
        if self.mode not in ('individual','combined','both') or self.security not in ('none','starttls','ssl'):
            raise ValueError('Invalid email mode or SMTP security')
        if not 1<=self.port<=65535 or not 0<=self.cooldown_minutes<=10080 or not 1<=self.timeout<=30 or self.lease_seconds<=self.timeout*3 or self.max_attempts<1:
            raise ValueError('Invalid email limits')
        if self.enabled:
            address(self.sender);address(self.recipient)
            if not all((self.run_id,self.building_id,self.source_id)): raise ValueError('Email requires exact EMAIL_RUN_ID/BUILDING_ID/SOURCE_ID')
            if bool(self.username)!=bool(self.password): raise ValueError('SMTP username and password must be paired')
            local=self.host in ('mailpit','localhost','127.0.0.1','::1')
            if not local and (not self.real_delivery or self.security=='none'):
                raise ValueError('External SMTP requires EMAIL_REAL_DELIVERY_ENABLED=true and TLS')
            if self.username and self.security=='none': raise ValueError('SMTP authentication requires TLS')
        return self

    def accepts(self,kind,run,building,source):
        return self.enabled and (run,building,source)==(self.run_id,self.building_id,self.source_id) and self.mode in (kind,'both')

    @property
    def fingerprint(self):
        # Credentials are excluded: rotation may resume the same queued deliveries.
        fields=('mode','host','port','security','sender','recipient','run_id','building_id','source_id','cooldown_minutes','real_delivery')
        return hashlib.sha256(json.dumps({k:getattr(self,k) for k in fields},sort_keys=True).encode()).hexdigest()
