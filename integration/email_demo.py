"""One-command, local Mailpit demo. Does not train models or run browser E2E."""
import argparse
import os
from uuid import uuid4
from integration.demo import environment,compose_command
from integration.settings import ROOT
from integration.setup import main as setup
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('scenario',choices=['synthetic','replay'],default='synthetic',nargs='?');a=p.parse_args()
    setup()
    prefix='email-delivery-test-' if a.scenario=='synthetic' else 'email-ml-'
    run=prefix+uuid4().hex[:12]
    env={**environment(),'MVP_COMPOSE_PROJECT':os.getenv('EMAIL_COMPOSE_PROJECT','energy-email-demo'),
        'MVP_RUN_ID':run,'MVP_GROUP_ID':run,'MVP_TOPIC':run,'EMAIL_RUN_ID':run,
        'EMAIL_BUILDING_ID':'appliances-house-1','EMAIL_SOURCE_ID':'uci-appliances',
        'EMAIL_NOTIFICATIONS_ENABLED':'true','EMAIL_ALERT_MODE':'both','EMAIL_FROM':'energy@example.test',
        'EMAIL_TO':'viewer@example.test','EMAIL_SMTP_HOST':'mailpit','EMAIL_SMTP_PORT':'1025',
        'EMAIL_SMTP_USERNAME':'','EMAIL_SMTP_PASSWORD':'','EMAIL_SMTP_SECURITY':'none',
        'EMAIL_REAL_DELIVERY_ENABLED':'false','EMAIL_COOLDOWN_MINUTES':'30'}
    cmd=[*compose_command(env),'-f',str(ROOT/'docker/docker-compose.email.yml'),'--profile','notifications']
    def run_compose(*args): subprocess.run([*cmd,*args],env=env,cwd=ROOT,check=True)
    # Build backend only; no prepare/training, Dashboard or full E2E.
    run_compose('build','notifier')
    run_compose('up','-d','--wait','--wait-timeout','120','postgres','mailpit',*(['kafka'] if a.scenario=='replay' else []))
    run_compose('run','--rm','--no-deps','notifier','alembic','upgrade','head')
    run_compose('run','--rm','--no-deps','notifier','python','-m','notifications.demo',a.scenario)
    print('Mailpit: http://127.0.0.1:'+env.get('EMAIL_MAILPIT_WEB_PORT','8025'))
    print('Project '+env['MVP_COMPOSE_PROJECT']+'; volumes and Mailpit retained. No real email delivery.')

if __name__=='__main__': main()
