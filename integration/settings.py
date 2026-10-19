from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_file(path):
    if not path.exists():
        return {}
    return {line.split('=',1)[0].strip():line.split('=',1)[1].strip()
            for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith('#') and '=' in line}


@dataclass(frozen=True)
class Settings:
    database_url: str
    bootstrap_servers: str = '127.0.0.1:19092'
    topic: str = 'energy-mvp-demo-001'
    group_id: str = 'energy-mvp-demo-001'
    run_id: str = 'demo-001'
    artifact_manifest: Path = ROOT / 'artifacts/mvp/local/manifest.json'

    @classmethod
    def from_env(cls):
        values = {**env_file(ROOT / '.env.mvp'), **os.environ}
        url = values.get('MVP_DATABASE_URL')
        if not url:
            raise ValueError('MVP_DATABASE_URL missing. Run python -m integration.setup; see docs/stage5/5a-runbook.md')
        return cls(url,values.get('MVP_BOOTSTRAP_SERVERS','127.0.0.1:19092'),
                   values.get('MVP_TOPIC','energy-mvp-demo-001'),values.get('MVP_GROUP_ID','energy-mvp-demo-001'),
                   values.get('MVP_RUN_ID','demo-001'),Path(values.get('MVP_ARTIFACT_MANIFEST',ROOT / 'artifacts/mvp/local/manifest.json')))
