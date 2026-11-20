import os
from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

url = os.environ.get("CTRLTEA_MIGRATION_URL")
if not url:
    raise RuntimeError("CTRLTEA_MIGRATION_URL must be explicitly supplied")
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
with engine.connect() as connection:
    with connection.begin():
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(814032601)")
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
