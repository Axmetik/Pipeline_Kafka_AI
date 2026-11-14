"""Private smoke fixture: real Processor/DB, deterministic model doubles, no training.
Executed only in an isolated container by rule_ui_smoke.py, never against the demo.
"""
import json, os, sys
sys.path.insert(0, '/work/tests')
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from integration.settings import Settings
from integration.processor import Processor
from storage.postgres.repository import Repository
from test_rule_layer_postgres import Artifacts
from test_energy_rules import record

url = os.environ['MVP_DATABASE_URL']
engine = create_engine(url)
if sys.argv[1] == 'init':
    for filename in ('alembic.ini', 'alembic-rules.ini'):
        config = Config(filename)
        with engine.begin() as c:
            config.attributes['connection'] = c
            command.upgrade(config, 'head')
settings = Settings(url, run_id='rule-ui-synthetic-fixture', group_id='rule-ui-fixture', topic='rule-ui-fixture', energy_rules_enabled=True)
artifacts = Artifacts()
repo = Repository(engine, settings)
repo.initialize(artifacts, 'isolated-synthetic-fixture')
if sys.argv[1] == 'init': repo.create_checkpoint()
p = Processor(repo, artifacts)
def send(offset, index, energy):
    message = record(index, energy)
    p.process(offset, json.dumps(['house', 'meter']).encode(), json.dumps(message).encode())
if sys.argv[1] == 'init':
    for i in range(438): send(i, i, 100 if i < 432 else 200)
elif sys.argv[1] == 'advance': send(438, 438, 400)
elif sys.argv[1] == 'gap': send(439, 440, 100)
engine.dispose()
