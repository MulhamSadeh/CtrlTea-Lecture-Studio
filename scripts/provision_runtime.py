"""Offline database-role provisioning, unrelated to application Super Admin."""
import os
import psycopg
from psycopg import sql

password=os.environ.get('CTRLTEA_RUNTIME_PASSWORD')
if not password or len(password)<20:
    raise SystemExit('Set a random CTRLTEA_RUNTIME_PASSWORD of at least20 characters')
with psycopg.connect(os.environ['CTRLTEA_MIGRATION_URL']) as db:
    if db.execute("SELECT 1 FROM pg_roles WHERE rolname='ctrltea_app'").fetchone():
        raise SystemExit('ctrltea_app already exists; rotate credentials deliberately, not automatically')
    db.execute(sql.SQL('CREATE ROLE ctrltea_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Literal(password)))
    db.execute('GRANT USAGE ON SCHEMA public TO ctrltea_app')
    db.execute('GRANT SELECT ON alembic_version,workspaces TO ctrltea_app')
    for table in ['courses','lectures','revisions','sources','pages','jobs','author_runs','author_tasks','source_aliases','run_aliases','private_assets','import_provenance']:
        db.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO ctrltea_app').format(sql.Identifier(table)))
print('Restricted database role provisioned. No application account or admin was created.')
