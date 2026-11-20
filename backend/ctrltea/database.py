"""Offline schema/legacy migration commands. No HTTP/account-claim endpoint."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile

from .models import LectureDocument
from .persistence import LEGACY_COLUMNS, PostgresConnection, workspace

TABLE_ORDER = ("courses", "lectures", "sources", "pages", "revisions", "jobs",
               "author_runs", "author_tasks", "source_aliases", "run_aliases")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def inspect_sqlite(data_dir):
    """Read a stopped/consistent installation COPY; never call application init."""
    root = Path(data_dir).resolve()
    dbfile = root / "studio.sqlite3"
    if not dbfile.is_file():
        raise ValueError("A consistent studio.sqlite3 snapshot is required")
    if (root / "studio.sqlite3-wal").exists() and (root / "studio.sqlite3-wal").stat().st_size:
        raise ValueError("Take a consistent backup snapshot first; live WAL input is not accepted")
    original_db_hash = digest(dbfile)
    errors, rows = [], {}
    with closing(sqlite3.connect(dbfile.as_uri()+"?mode=ro&immutable=1", uri=True)) as con:
        con.row_factory = sqlite3.Row
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            errors.append("SQLite integrity check failed")
        for r in con.execute("PRAGMA foreign_key_check"):
            errors.append("Foreign key violation: " + str(tuple(r)))
        for table in TABLE_ORDER:
            columns = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            required = set(LEGACY_COLUMNS[table].split(","))
            missing = required-columns
            if table == "lectures":
                missing.discard("theme")
            if missing:
                errors.append(f"{table}: missing columns {sorted(missing)}")
                rows[table] = []
            else:
                rows[table] = [dict(r) for r in con.execute(f"SELECT * FROM {table}")]
    for row in rows["lectures"]:
        row.setdefault("theme", "cinnamon")
    source_by_id = {r["id"]:r for r in rows["sources"]}
    pages = {(r["source_id"], r["number"]) for r in rows["pages"]}
    for table, field in (("lectures","doc"),("revisions","doc"),("author_runs","base_doc")):
        for row in rows[table]:
            try:
                doc = LectureDocument.model_validate_json(row[field])
                lid = row["id"] if table == "lectures" else row["lecture_id"]
                for section in doc.sections:
                    for block in section.blocks:
                        for ref in block.refs:
                            source = source_by_id.get(ref.source_id)
                            if not source or source["lecture_id"] != lid or (ref.source_id,ref.page) not in pages:
                                errors.append(f"{table}/{row['id']}: invalid scoped page reference")
            except (ValueError, TypeError) as e:
                errors.append(f"{table}/{row['id']}: invalid legacy document ({type(e).__name__})")
    for row in rows["sources"]:
        linked = row.get("linked_id")
        if linked and (linked not in source_by_id or source_by_id[linked]["lecture_id"] != row["lecture_id"]):
            errors.append("Invalid linked source: " + row["id"])
    for table, target, field in (("source_aliases", source_by_id,"source_id"),
                                 ("run_aliases",{r["id"]:r for r in rows["author_runs"]},"run_id")):
        for row in rows[table]:
            if row[field] not in target or target[row[field]]["lecture_id"]!=row["lecture_id"]:
                errors.append(f"{table}: invalid scoped alias")
    files = []
    for folder in ("sources","exports","figures","math","bundles"):
        if not (root/folder).exists():
            continue
        for p in sorted((root/folder).rglob("*")):
            if p.is_symlink() or not p.resolve().is_relative_to(root):
                errors.append("Symlink/out-of-root asset rejected")
                continue
            if p.is_file():
                files.append({"path":p.relative_to(root).as_posix(),"sha256":digest(p),"bytes":p.stat().st_size})
    file_by_path = {r["path"]:r for r in files}
    for row in rows["sources"]:
        f = file_by_path.get(row["path"])
        path = PurePosixPath(row["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in row["path"]:
            errors.append("Unsafe source path: " + row["id"])
        if not f:
            errors.append("Missing attachment: " + row["id"])
        elif f["sha256"] != row["digest"]:
            errors.append("Attachment digest mismatch: " + row["id"])
    docs = {table:{r["id"]:hashlib.sha256(r[field].encode()).hexdigest() for r in rows[table]}
            for table,field in (("lectures","doc"),("revisions","doc"),("author_runs","base_doc"))}
    if digest(dbfile) != original_db_hash:
        raise ValueError("Input SQLite snapshot changed during inspection")
    fingerprint = hashlib.sha256(json.dumps({"db":digest(dbfile),"files":files},sort_keys=True).encode()).hexdigest()
    report = {"input_sha256":fingerprint,"sqlite_sha256":digest(dbfile),"counts":{t:len(r) for t,r in rows.items()},
              "text_hashes":docs,"files":files,"errors":errors,"status":"invalid" if errors else "verified",
              "dataset_provenance":"not_asserted","note":"Caller must identify whether this snapshot is a fixture or real installation.",
              "legacy_history_duplicates":len(rows['revisions'])-len({(r['lecture_id'],r['revision']) for r in rows['revisions']})}
    return report, rows


def admin_connection():
    import psycopg
    url = os.environ.get("CTRLTEA_MIGRATION_URL")
    if not url:
        raise ValueError("Explicit CTRLTEA_MIGRATION_URL required for offline operator commands")
    return psycopg.connect(url, connect_timeout=10)


def create_workspace(wid):
    with workspace(wid), admin_connection() as con:
        con.execute("SELECT set_config('ctrltea.workspace_id',%s,true)",(wid,))
        con.execute("INSERT INTO workspaces(id) VALUES(%s) ON CONFLICT(id) DO NOTHING",(wid,))


def import_sqlite(data_dir, wid, data_root, dry_run=False):
    report, rows = inspect_sqlite(data_dir)
    report["workspace_id"] = wid
    if dry_run or report["errors"]:
        return report
    from .persistence import row_factory
    root = Path(data_root).resolve()/"workspaces"
    root.mkdir(parents=True,exist_ok=True)
    destination = root/wid
    stage = None
    try:
        with workspace(wid), admin_connection() as con:
            con.row_factory = row_factory
            con.execute("SELECT set_config('ctrltea.workspace_id',%s,true)",(wid,))
            ws = con.execute("SELECT owner_user_id,state FROM workspaces WHERE id=%s FOR UPDATE",(wid,)).fetchone()
            if not ws or ws["state"]!="unclaimed" or ws["owner_user_id"] is not None:
                raise ValueError("Import requires an explicitly provisioned unclaimed workspace")
            receipt = con.execute("SELECT input_sha256,report FROM import_receipts WHERE workspace_id=%s",(wid,)).fetchone()
            if receipt:
                if receipt['input_sha256']!=report['input_sha256']:
                    raise ValueError("Workspace import already bound to different input")
                for f in report['files']:
                    if not (destination/f['path']).is_file() or digest(destination/f['path'])!=f['sha256']:
                        raise ValueError("Existing import's files require recovery")
                verify_rows(con, rows, wid)
                report['status']='already_imported'
                return report
            if any(con.execute(f"SELECT 1 FROM {t} WHERE workspace_id=%s LIMIT 1",(wid,)).fetchone() for t in TABLE_ORDER):
                raise ValueError("Import destination must be empty")
            if destination.exists():
                raise ValueError("Destination file directory already exists; use a new workspace/root")
            stage = Path(tempfile.mkdtemp(prefix="import-",dir=root))
            for f in report['files']:
                target=stage/f['path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(Path(data_dir)/f['path'],target)
                if digest(target)!=f['sha256']:
                    raise ValueError("Input attachment changed during import")
            for folder in ('sources','exports','figures','math','bundles'):
                (stage/folder).mkdir(exist_ok=True)
            adapter=PostgresConnection(con)
            for table in TABLE_ORDER:
                columns=LEGACY_COLUMNS[table].split(',')
                for row in rows[table]:
                    values=[row[c] for c in columns]
                    cols=columns.copy()
                    if table=='revisions':cols.append('is_legacy');values.append(1)
                    if table=='jobs' and row['status'] in ('queued','running'):
                        values[columns.index('status')]='failed'
                        values[columns.index('error')]=json.dumps({'message':'Legacy pending job quarantined; explicit authorized retry required','original_status':row['status']})
                    adapter.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' for _ in values)})",values)
            con.execute("SET CONSTRAINTS ALL IMMEDIATE")
            verify_rows(con,rows,wid)
            by_source={r['path']:r['lecture_id'] for r in rows['sources']}
            for f in report['files']:
                con.execute("INSERT INTO private_assets(workspace_id,id,lecture_id,kind,relative_path,sha256,bytes) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                            (wid,hashlib.sha256(f['path'].encode()).hexdigest(),by_source.get(f['path']),f['path'].split('/')[0],f['path'],f['sha256'],f['bytes']))
            provenance=json.dumps({'installation_sha256':report['input_sha256'],'ownership':'unclaimed','original_actors':'unknown'})
            for row in rows['lectures']:
                con.execute("INSERT INTO import_provenance(workspace_id,lecture_id,provenance) VALUES(%s,%s,%s)",(wid,row['id'],provenance))
            report['original_job_records']=rows['jobs']
            report['quarantined_jobs']=[{'id':r['id'],'original_status':r['status']} for r in rows['jobs'] if r['status'] in ('queued','running')]
            report['status']='imported'
            con.execute("INSERT INTO import_receipts(workspace_id,input_sha256,report) VALUES(%s,%s,%s)",(wid,report['input_sha256'],json.dumps(report)))
            stage.rename(destination)
        return report
    finally:
        # Once renamed, retain bytes even if COMMIT acknowledgement is lost.
        # A matching receipt resolves success; otherwise the private directory
        # is quarantined for operator recovery. Never delete possibly committed files.
        if stage and stage.exists():shutil.rmtree(stage)


def verify_rows(con, rows, wid):
    for table in TABLE_ORDER:
        columns=LEGACY_COLUMNS[table].split(',')
        actual=[dict(r) for r in con.execute(f"SELECT {','.join(columns)} FROM {table} WHERE workspace_id=%s",(wid,))]
        if len(actual)!=len(rows[table]):
            raise ValueError(f"Record count mismatch: {table}")
        key=lambda r:json.dumps([r[c] for c in columns if table!='jobs' or c not in ('status','error')],ensure_ascii=False)
        if sorted(map(key,actual))!=sorted(map(key,rows[table])):
            raise ValueError(f"Record preservation mismatch: {table}")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('upgrade')
    p=sub.add_parser('create-workspace');p.add_argument('--workspace',required=True)
    p=sub.add_parser('import-sqlite')
    p.add_argument('--data-dir',required=True);p.add_argument('--workspace',required=True)
    p.add_argument('--data-root',required=True);p.add_argument('--dry-run',action='store_true');p.add_argument('--report',required=True)
    args=parser.parse_args()
    if args.command=='upgrade':
        from alembic.config import Config
        from alembic import command
        config=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
        command.upgrade(config,'head')
    elif args.command=='create-workspace':create_workspace(args.workspace)
    else:
        try:
            report=import_sqlite(args.data_dir,args.workspace,args.data_root,args.dry_run)
        except Exception as error:
            report={'status':'failed','error_type':type(error).__name__,'errors':['Import did not commit; inspect the private input and runtime configuration.']}
            Path(args.report).write_text(json.dumps(report,indent=2),encoding='utf-8')
            raise SystemExit(2) from error
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if report['errors']:raise SystemExit(2)


if __name__=='__main__':
    main()
