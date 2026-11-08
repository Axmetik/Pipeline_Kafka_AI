"""Optional rule layer with its own revision ledger; never migrates base tables."""
from alembic import context
from sqlalchemy import create_engine,text
from integration.settings import Settings

def apply(connection):
    if connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()!='0003_email':
        raise RuntimeError('Apply reviewed base migrations first')
    context.configure(connection=connection,version_table='alembic_rule_layer_version')
    with context.begin_transaction():context.run_migrations()

provided=context.config.attributes.get('connection')
if provided is not None:apply(provided)
else:
    engine=create_engine(Settings.from_env().database_url)
    with engine.begin() as c:apply(c)
    engine.dispose()
