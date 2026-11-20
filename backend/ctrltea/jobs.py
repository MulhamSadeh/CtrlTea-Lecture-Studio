from __future__ import annotations

import json
import threading
from contextvars import copy_context
from . import persistence,accounts
import traceback
from . import store
from .sources import extract
from .exporter import export_lecture


class Worker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=copy_context().run, args=(self.run,), daemon=True, name="ctrltea-worker")

    def start(self):
        self.guard = persistence.worker_guard("authenticated" if accounts.enabled() else None) if persistence.backend() == "postgres" else None
        try:
            if self.guard and not accounts.enabled():
                with store.connect() as db:
                    db.execute("UPDATE jobs SET status='queued',updated=? WHERE status='running'", (store.now(),))
            elif self.guard:
                with accounts.db() as con:
                    spaces=con.execute("SELECT DISTINCT workspace_id AS id FROM jobs WHERE status='running'").fetchall()
                privilege=accounts.admin_scope.set(True)
                try:
                    for space in spaces:
                        with store.workspace(space['id']),store.connect() as db:
                            db.execute("UPDATE jobs SET status='queued',updated=? WHERE status='running'",(store.now(),))
                finally:accounts.admin_scope.reset(privilege)
            self.thread.start()
        except BaseException:
            if self.guard:
                self.guard.close()
            raise

    def run(self):
        try:
            self.loop()
        finally:
            if self.guard:
                self.guard.close()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    def progress(self, jid, value):
        with store.connect() as db:
            db.execute("UPDATE jobs SET progress=?,updated=? WHERE id=?", (value, store.now(), jid))

    def loop(self):
        while not self.stop_event.wait(0.25):
            if accounts.enabled():
                with accounts.db() as con:
                    spaces=con.execute("SELECT DISTINCT j.workspace_id AS id FROM jobs j JOIN workspaces w ON w.id=j.workspace_id WHERE j.status='queued' AND w.state IN ('private','unclaimed') ORDER BY id").fetchall()
                privilege=accounts.admin_scope.set(True)
                try:
                    for space in spaces:
                        if self.stop_event.is_set():break
                        with store.workspace(space['id']):
                            self.step()
                finally:accounts.admin_scope.reset(privilege)
            else:
                self.step()

    def step(self):
        with store.connect() as db:
            query = "SELECT *, requested_by AS job_actor FROM jobs" if accounts.enabled() else "SELECT * FROM jobs"
            row = db.execute(
                query + " WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if not row:
                return
            row = dict(row)
            db.execute(
                "UPDATE jobs SET status='running',updated=? WHERE id=?",
                (store.now(), row["id"]),
            )
        try:
            if accounts.enabled():
                current=accounts.job_principal(row.get('job_actor'))
                from .access import can
                cid=store.lecture(row['lecture_id'])['course_id']
                permission='lectures.export' if row['kind']=='export' else 'sources.extract'
                if not can(current,permission,persistence.workspace_id(),row['lecture_id'],cid):
                    raise ValueError('لم تعد المهمة مخوّلة لهذا الحساب')
            payload = json.loads(row["payload"])
            progress = lambda n: self.progress(row["id"], n)
            if row["kind"] == "extract":
                result = extract(payload["source_id"], progress)
            elif row["kind"] == "export":
                result = export_lecture(
                    row["lecture_id"], payload.get("draft", False), progress
                )
            else:
                raise ValueError("نوع مهمة غير مدعوم")
            if accounts.enabled():
                current=accounts.job_principal(row.get('job_actor'))
                if not can(current,permission,persistence.workspace_id(),row['lecture_id'],cid):
                    raise ValueError('سُحبت صلاحية المهمة قبل إتمامها')
            with store.transaction() as db:
                if persistence.backend() == "postgres":
                    if row["kind"] == "export":
                        for path in (store.DATA / "exports" / result["export_id"]).iterdir():
                            if path.is_file():
                                store.record_asset(path, row["lecture_id"])
                    else:
                        store.record_asset(store.source_path(payload["source_id"]), row["lecture_id"])
                db.execute(
                    "UPDATE jobs SET status='done',result=?,progress=100,updated=? WHERE id=?",
                    (json.dumps(result, ensure_ascii=False), store.now(), row["id"]),
                )
        except Exception as e:
            with store.connect() as db:
                db.execute(
                    "UPDATE jobs SET status='failed',error=?,updated=? WHERE id=?",
                    (
                        json.dumps(
                            {"message":str(e),"code":"job_failed"} if accounts.enabled() else {"message": str(e), "diagnostic": traceback.format_exc()},
                            ensure_ascii=False,
                        ),
                        store.now(),
                        row["id"],
                    ),
                )


def _enqueue(lid, kind, payload):
    # One pending extraction per source; duplicate export clicks share the job.
    existing = store.all_rows(
        "SELECT * FROM jobs WHERE lecture_id=? AND kind=? AND status IN ('queued','running')",
        (lid, kind),
    )
    encoded = json.dumps(payload, sort_keys=True)
    for j in existing:
        if j["payload"] == encoded and (not accounts.enabled() or j.get('requested_by')==accounts.actor.get()['id']):
            return j
    jid = store.uid()
    with store.connect() as db:
        db.execute(
            "INSERT INTO jobs(id,lecture_id,kind,status,payload,created,updated) VALUES(?,?,?,?,?,?,?)",
            (jid, lid, kind, "queued", encoded, store.now(), store.now()),
        )
    if accounts.enabled():
        with store.connect() as db:
            db.execute('UPDATE jobs SET requested_by=? WHERE id=?',(accounts.actor.get()['id'],jid))
    return store.one("SELECT * FROM jobs WHERE id=?", (jid,))


def enqueue(lid, kind, payload):
    with store.transaction() as db:
        suffix = " FOR UPDATE" if persistence.backend() == "postgres" else ""
        if not db.execute("SELECT id FROM lectures WHERE id=?" + suffix, (lid,)).fetchone():
            raise LookupError("المحاضرة غير موجودة")
        return _enqueue(lid, kind, payload)
