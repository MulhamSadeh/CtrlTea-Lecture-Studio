from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .models import uid
from .theme import validate_theme
from . import persistence

ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = Path(os.environ.get("CTRLTEA_DATA_DIR", ROOT / "data")).resolve()


class ScopedDataPath:
    """Keep the engine's Path-based API; resolve privately from trusted context."""
    def path(self):
        if persistence.backend() == "postgres":
            return _DATA_ROOT / "workspaces" / persistence.workspace_id()
        return _DATA_ROOT

    def __truediv__(self, other):
        return self.path() / other

    def __str__(self):
        return str(self.path())

    def __fspath__(self):
        return str(self.path())

    def __getattr__(self, key):
        return getattr(self.path(), key)


DATA = ScopedDataPath()
workspace = persistence.workspace


class ConnectionState:
    def __init__(self, db):
        self.db = db
        self.scope = persistence.workspace_id() if persistence.backend() == "postgres" else None
        self.failed = False



def now():
    return datetime.now(timezone.utc).isoformat()


def init():
    DATA.mkdir(parents=True, exist_ok=True)
    for name in ("sources", "exports", "figures", "math", "bundles"):
        (DATA / name).mkdir(exist_ok=True)
    if persistence.backend() == "postgres":
        with connect() as db:
            version = db.execute("SELECT version_num FROM alembic_version").fetchone()
            if not version or version[0] not in ("0001_private","0002_accounts"):
                raise RuntimeError("Run the versioned migrations before starting PostgreSQL mode")
        return
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY, name TEXT NOT NULL, doctor TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lectures(id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE, title TEXT NOT NULL, doc TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE, revision INTEGER NOT NULL, doc TEXT NOT NULL, created TEXT NOT NULL, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE, name TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 1, role TEXT NOT NULL DEFAULT 'support', linked_id TEXT, digest TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pages(source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE, number INTEGER NOT NULL, raw TEXT NOT NULL DEFAULT '', corrected TEXT, excluded INTEGER NOT NULL DEFAULT 0, method TEXT NOT NULL DEFAULT '', PRIMARY KEY(source_id,number));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, result TEXT, error TEXT, progress INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS author_runs(id TEXT PRIMARY KEY, lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE, section_ids TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL, base_doc TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS author_tasks(run_id TEXT NOT NULL REFERENCES author_runs(id) ON DELETE CASCADE, section_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY(run_id,section_id));
        CREATE TABLE IF NOT EXISTS source_aliases(lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE, original_id TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE, PRIMARY KEY(lecture_id,original_id));
        CREATE TABLE IF NOT EXISTS run_aliases(lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE, original_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES author_runs(id) ON DELETE CASCADE, PRIMARY KEY(lecture_id,original_id));
        CREATE INDEX IF NOT EXISTS sources_lecture ON sources(lecture_id);
        CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
        """)
        # Additive, idempotent migration: no lecture JSON or history is rewritten.
        columns = {row["name"] for row in db.execute("PRAGMA table_info(lectures)")}
        if "theme" not in columns:
            db.execute(
                "ALTER TABLE lectures ADD COLUMN theme TEXT NOT NULL DEFAULT 'cinnamon' "
                "CHECK(theme IN ('cinnamon','honey','olive'))"
            )
        db.execute("UPDATE jobs SET status='queued', updated=? WHERE status='running'", (now(),))


@contextmanager
def connect(immediate=False, snapshot=False):
    existing = persistence._connection.get()
    if existing is not None:
        if persistence.backend() == "postgres" and existing.scope != persistence.workspace_id():
            raise RuntimeError("Cross-workspace nested transaction")
        try:
            yield existing.db
        except BaseException:
            existing.failed = True
            raise
        return
    if persistence.backend() == "postgres":
        with persistence.postgres_connection(snapshot=snapshot) as db:
            state = ConnectionState(db)
            token = persistence._connection.set(state)
            try:
                yield db
                if state.failed:
                    raise RuntimeError("Nested operation failed; transaction rolled back")
            finally:
                persistence._connection.reset(token)
    else:
        con = sqlite3.connect(DATA / "studio.sqlite3", timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        if immediate:
            con.execute("BEGIN IMMEDIATE")
        state = ConnectionState(con)
        token = persistence._connection.set(state)
        try:
            yield con
            if state.failed:
                raise RuntimeError("Nested operation failed; transaction rolled back")
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            persistence._connection.reset(token)
            con.close()


def transaction():
    return connect(immediate=True)


def all_rows(sql, args=()):
    with connect() as db:
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def one(sql, args=()):
    rows = all_rows(sql, args)
    if not rows:
        raise LookupError("العنصر المطلوب غير موجود")
    return rows[0]


def lecture(lid):
    row = one("SELECT * FROM lectures WHERE id=?", (lid,))
    row["document"] = json.loads(row.pop("doc"))
    return row


def set_theme(lid, theme):
    validate_theme(theme)
    with connect() as db:
        result = db.execute("UPDATE lectures SET theme=?,updated=? WHERE id=?", (theme, now(), lid))
        if not result.rowcount:
            raise LookupError("المحاضرة غير موجودة")
    # Do not return/save a content snapshot: theme changes are independent of editing.
    return one("SELECT id,theme,updated FROM lectures WHERE id=?", (lid,))


class Conflict(Exception):
    pass


def save_document(lid, document, revision, reason="تعديل"):
    text = json.dumps(document, ensure_ascii=False)
    with transaction() as db:
        suffix = " FOR UPDATE" if persistence.backend() == "postgres" else ""
        row = db.execute("SELECT revision,doc FROM lectures WHERE id=?" + suffix, (lid,)).fetchone()
        if not row:
            raise LookupError("المحاضرة غير موجودة")
        if revision != row["revision"]:
            raise Conflict("تغيرت المحاضرة في نافذة أخرى. احفظ نسخة محلية من تعديلاتك ثم أعد تحميلها.")
        db.execute(
            "INSERT INTO revisions(id,lecture_id,revision,doc,created,reason) VALUES(?,?,?,?,?,?)",
            (uid(), lid, revision, row["doc"], now(), reason),
        )
        changed = db.execute(
            "UPDATE lectures SET doc=?,title=?,revision=revision+1,updated=? WHERE id=? AND revision=?",
            (text, document["title"], now(), lid, revision),
        )
        if changed.rowcount != 1:
            raise Conflict("تغيرت نسخة المحاضرة؛ لم يُحفظ تعديلك")
        # Read our committed candidate inside this transaction, never a later writer's head.
        result = dict(db.execute("SELECT * FROM lectures WHERE id=?", (lid,)).fetchone())
        result["document"] = json.loads(result.pop("doc"))
    return result


def source_path(sid):
    row = one("SELECT * FROM sources WHERE id=?", (sid,))
    return DATA / row["path"]


def record_asset(path, lecture_id=None):
    """Index private generated/source files without altering the rendering engine."""
    if persistence.backend() != "postgres":
        return
    import hashlib
    path = Path(path)
    base = DATA.resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise ValueError("Asset must remain inside its private workspace")
    relative = path.resolve().relative_to(base).as_posix()
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    with connect() as db:
        db.execute(
            "INSERT INTO private_assets(id,lecture_id,kind,relative_path,sha256,bytes,workspace_id) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT (workspace_id,relative_path) DO UPDATE SET sha256=EXCLUDED.sha256,bytes=EXCLUDED.bytes",
            (hashlib.sha256(relative.encode()).hexdigest(),lecture_id,relative.split('/')[0],relative,h.hexdigest(),path.stat().st_size,persistence.workspace_id()),
        )


def effective_pages(lid):
    return all_rows(
        """SELECT p.*,s.id AS source_id,s.name,s.role,s.priority,s.linked_id FROM pages p
        JOIN sources s ON s.id=p.source_id WHERE s.lecture_id=? ORDER BY s.priority,p.number""",
        (lid,),
    )
