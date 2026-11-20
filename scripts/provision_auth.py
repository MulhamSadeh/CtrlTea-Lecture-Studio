"""Offline provisioning of a restricted authentication-service DB role."""
import os
import psycopg
from psycopg import sql
from ctrltea.accounts import PERMISSIONS,FUTURE

password=os.environ.get('CTRLTEA_AUTH_DB_PASSWORD','')
if len(password)<20:raise SystemExit('Set a random CTRLTEA_AUTH_DB_PASSWORD >=20 characters')
with psycopg.connect(os.environ['CTRLTEA_MIGRATION_URL']) as con:
    if con.execute("SELECT 1 FROM pg_roles WHERE rolname='ctrltea_auth'").fetchone():
        raise SystemExit('ctrltea_auth already exists; rotate credentials through an explicit operator procedure')
    con.execute(sql.SQL('CREATE ROLE ctrltea_auth LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Literal(password)))
    con.execute('GRANT USAGE ON SCHEMA public TO ctrltea_auth')
    for table in ['accounts','profiles','credentials','auth_tokens','sessions','permission_overrides','resource_grants','auth_rate_limits','bootstrap_state']:
        con.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO ctrltea_auth').format(sql.Identifier(table)))
    con.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON workspaces TO ctrltea_auth')
    con.execute('GRANT SELECT ON alembic_version,system_roles,permission_catalog,role_permissions,import_receipts TO ctrltea_auth')
    con.execute('GRANT SELECT(workspace_id,status,requested_by) ON jobs TO ctrltea_auth')
    con.execute('GRANT SELECT,INSERT ON security_audit TO ctrltea_auth')
    con.execute('GRANT USAGE,SELECT ON SEQUENCE security_audit_id_seq TO ctrltea_auth')
    for name,(group,label) in PERMISSIONS.items():
        con.execute('INSERT INTO permission_catalog(name,group_name,label,future) VALUES(%s,%s,%s,%s) ON CONFLICT(name) DO NOTHING',(name,group,label,name in FUTURE))
        for role in ('SuperAdmin','Member','Reviewer'):
            reviewer={'courses.view','lectures.view','sources.view','files.download','revisions.view','lectures.export','jobs.view','jobs.retry','math.check','figures.preview','review.inspect','review.approve'}
            if role=='SuperAdmin' or (role=='Member' and name not in FUTURE) or (role=='Reviewer' and name in reviewer):
                con.execute('INSERT INTO role_permissions(role,permission) VALUES(%s,%s) ON CONFLICT DO NOTHING',(role,name))
    # Content remains on the original restricted runtime connection.
    con.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON trash_records TO {}').format(sql.Identifier(os.environ.get('CTRLTEA_RUNTIME_ROLE','ctrltea_app'))))
print('Restricted auth service provisioned; no platform administrator/account was created.')
