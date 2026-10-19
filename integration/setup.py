"""Generate local-only credentials without printing or committing them."""
from pathlib import Path
import secrets
import os
from integration.settings import ROOT


def main():
    path=ROOT / '.env.mvp'
    if path.exists():
        print('.env.mvp already exists; preserved. See docs/stage5/5a-runbook.md')
        return
    token=secrets.token_urlsafe(32)
    content=f'''POSTGRES_DB=energy_mvp
POSTGRES_USER=energy_mvp
POSTGRES_PASSWORD={token}
MVP_DATABASE_URL=postgresql+psycopg://energy_mvp:{token}@127.0.0.1:15432/energy_mvp
MVP_BOOTSTRAP_SERVERS=127.0.0.1:19092
MVP_TOPIC=energy-mvp-demo-001
MVP_GROUP_ID=energy-mvp-demo-001
MVP_RUN_ID=demo-001
MVP_ARTIFACT_MANIFEST=artifacts/mvp/local/manifest.json
'''
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as file:
        file.write(content)
    print('Created ignored .env.mvp with local credentials. Next: docker compose --env-file .env.mvp -p energy-mvp -f docker/docker-compose.mvp.yml up -d --wait')


if __name__=='__main__':
    main()
