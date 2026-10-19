"""No URL/password in versioned configuration or logs."""
from alembic import context
from sqlalchemy import create_engine
from integration.settings import Settings
from storage.postgres.schema import metadata

def apply(connection):
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

provided = context.config.attributes.get('connection')
if provided is not None:
    apply(provided)
else:
    engine = create_engine(Settings.from_env().database_url)
    with engine.connect() as connection:
        apply(connection)
    engine.dispose()
