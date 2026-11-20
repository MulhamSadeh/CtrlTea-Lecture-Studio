"""PostgreSQL boundary for the existing small, parameterized SQL surface.

Ownership is enforced by transaction-local scope plus database RLS/FKs.
This is trusted server context, never a value taken from an HTTP header.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar

_workspace = ContextVar("ctrltea_workspace", default=None)
_connection = ContextVar("ctrltea_connection", default=None)
_privileged_scope = ContextVar("ctrltea_privileged_scope", default=False)

# Explicit legacy projections keep v1 JSON envelopes and project bundles stable.
LEGACY_COLUMNS = {
    "courses": "id,name,doctor,created",
    "lectures": "id,course_id,title,doc,revision,updated,theme",
    "revisions": "id,lecture_id,revision,doc,created,reason",
    "sources": "id,lecture_id,name,path,kind,priority,role,linked_id,digest,created",
    "pages": "source_id,number,raw,corrected,excluded,method",
    "jobs": "id,lecture_id,kind,status,payload,result,error,progress,created,updated",
    "author_runs": "id,lecture_id,section_ids,status,created,base_doc",
    "author_tasks": "run_id,section_id,status",
    "source_aliases": "lecture_id,original_id,source_id",
    "run_aliases": "lecture_id,original_id,run_id",
}


def backend():
    mode = os.environ.get("CTRLTEA_DB_BACKEND", "sqlite")
    if mode not in ("sqlite", "postgres"):
        raise ValueError("CTRLTEA_DB_BACKEND must be sqlite or postgres")
    return mode


def workspace_id():
    value = _workspace.get() or os.environ.get("CTRLTEA_WORKSPACE_ID")
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise ValueError("An explicit, safe CTRLTEA_WORKSPACE_ID is required")
    return value


@contextmanager
def workspace(value):
    if _connection.get() is not None:
        raise RuntimeError("Cannot switch workspace inside a transaction")
    token = _workspace.set(value)
    try:
        workspace_id()
        yield
    finally:
        _workspace.reset(token)


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    hidden = {"workspace_id", "is_legacy"}
    return lambda values: Row((k, v) for k, v in zip(names, values) if k not in hidden)


class PostgresConnection:
    def __init__(self, connection):
        self.raw = connection

    def execute(self, statement, args=()):
        # Only application-owned SQL reaches this adapter. Values remain bound.
        statement = statement.strip()
        if statement.upper() == "BEGIN":
            # PG transaction is already opened and scoped by connect().
            return self.raw.execute("SELECT 1")
        replace = re.match(r"INSERT OR (REPLACE|IGNORE) INTO (source_aliases|run_aliases)", statement, re.I)
        if replace:
            mode, table = replace.groups()
            statement = re.sub(r"INSERT OR (REPLACE|IGNORE)", "INSERT", statement, count=1, flags=re.I)
            target = "source_id" if table == "source_aliases" else "run_id"
            statement += " ON CONFLICT (workspace_id,lecture_id,original_id) " + (
                f"DO UPDATE SET {target}=EXCLUDED.{target}" if mode.upper() == "REPLACE" else "DO NOTHING"
            )
        match = re.match(r"INSERT INTO (\w+)\s+VALUES", statement, re.I)
        if match:
            table = match.group(1)
            if table not in LEGACY_COLUMNS:
                raise ValueError("New tables require explicit INSERT column lists")
            statement = statement[:match.end()-6] + "(" + LEGACY_COLUMNS[table] + ") VALUES" + statement[match.end():]
        # Translate only placeholders outside ordinary SQL string literals.
        parts = re.split(r"('(?:[^']|'')*')", statement)
        statement = ''.join(part if i % 2 else part.replace('?', '%s') for i, part in enumerate(parts))
        return self.raw.execute(statement, args)


@contextmanager
def postgres_connection(snapshot=False):
    import psycopg
    url = os.environ.get("CTRLTEA_DATABASE_URL")
    if not url:
        raise ValueError("CTRLTEA_DATABASE_URL is required; no SQLite fallback")
    with psycopg.connect(url, row_factory=row_factory, connect_timeout=10) as con:
        if snapshot:
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        role = con.execute("SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname=current_user").fetchone()
        owns = con.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='courses' AND pg_has_role(current_user,tableowner,'MEMBER')").fetchone()
        if role["rolsuper"] or role["rolbypassrls"] or role["rolcreaterole"] or owns:
            raise RuntimeError("Use a restricted runtime role, not a superuser/BYPASSRLS/table owner")
        con.execute("SELECT set_config('ctrltea.workspace_id',%s,true)", (workspace_id(),))
        con.execute("SET LOCAL lock_timeout='5s'")
        con.execute("SET LOCAL statement_timeout='30s'")
        ws = con.execute("SELECT id,state FROM workspaces WHERE id=%s", (workspace_id(),)).fetchone()
        if not ws:
            raise LookupError("Workspace not provisioned; use the offline database command")
        if ws["state"] == "suspended" and not _privileged_scope.get():
            raise RuntimeError("Workspace is suspended")
        if ws["state"] == "unclaimed" and os.environ.get("CTRLTEA_ALLOW_UNCLAIMED") != "1" and not _privileged_scope.get():
            raise RuntimeError("Unclaimed data is restricted; explicit local operator mode required")
        yield PostgresConnection(con)



def worker_guard(scope_id=None):
    """Keep the V1 worker architecture safe from accidental duplicate processes.

    A later worker task replaces this single-workspace deployment restriction.
    The lock connection lives until the original worker thread actually exits.
    """
    import hashlib
    import psycopg
    con = psycopg.connect(os.environ["CTRLTEA_DATABASE_URL"],autocommit=True,connect_timeout=10)
    key = int.from_bytes(hashlib.sha256(("worker:"+(scope_id or workspace_id())).encode()).digest()[:8],"big",signed=True)
    if not con.execute("SELECT pg_try_advisory_lock(%s)",(key,)).fetchone()[0]:
        con.close()
        raise RuntimeError("This workspace already has a running local worker; multiple API workers are not supported")
    return con
