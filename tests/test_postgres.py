"""Real PostgreSQL integration. Opt-in only: always use disposable databases."""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from ctrltea import store, sources, bundles, authoring, persistence
from ctrltea.database import create_workspace, import_sqlite, inspect_sqlite, digest
from ctrltea.models import LectureDocument, Section, Block, uid

pytestmark = pytest.mark.skipif(not os.environ.get('CTRLTEA_TEST_DATABASE_URL'), reason='Disposable PostgreSQL URL not configured')


@pytest.fixture
def pg(tmp_path, monkeypatch):
    monkeypatch.setenv('CTRLTEA_DB_BACKEND','postgres')
    monkeypatch.setenv('CTRLTEA_DATABASE_URL',os.environ['CTRLTEA_TEST_DATABASE_URL'])
    monkeypatch.setenv('CTRLTEA_ALLOW_UNCLAIMED','1')
    wid='test_'+uid()
    create_workspace(wid)
    monkeypatch.setenv('CTRLTEA_WORKSPACE_ID',wid)
    monkeypatch.setattr(store,'_DATA_ROOT',tmp_path/'private')
    store.init()
    return wid


def seed():
    cid,lid=uid(),uid()
    doc=LectureDocument(title='Private lecture',sections=[Section(title='Basics',blocks=[Block(kind='equation',latex=r'\frac{1}{2}+x=3')])])
    with store.connect() as db:
        db.execute('INSERT INTO courses VALUES(?,?,?,?)',(cid,'Course','Doctor',store.now()))
        db.execute('INSERT INTO lectures(id,course_id,title,doc,updated) VALUES(?,?,?,?,?)',(lid,cid,doc.title,doc.model_dump_json(),store.now()))
    return cid,lid,doc


def test_initialization_and_repeatable_migration(pg):
    from alembic.config import Config
    from alembic import command
    command.upgrade(Config(str(store.ROOT/'alembic.ini')),'head')
    assert store.one('SELECT version_num FROM alembic_version')['version_num']=='0002_accounts'
    assert not (store.DATA/'studio.sqlite3').exists()


def test_crud_raw_json_and_revisions(pg):
    cid,lid,doc=seed()
    raw=store.one('SELECT doc FROM lectures WHERE id=?',(lid,))['doc']
    assert raw==doc.model_dump_json()
    changed=doc.model_dump();changed['title']='Edited'
    assert store.save_document(lid,changed,0)['revision']==1
    assert store.one('SELECT doc FROM revisions WHERE lecture_id=?',(lid,))['doc']==raw
    with pytest.raises(store.Conflict):store.save_document(lid,changed,0)
    with store.connect() as db:db.execute('DELETE FROM courses WHERE id=?',(cid,))
    assert not store.all_rows('SELECT id FROM lectures WHERE id=?',(lid,))


def test_rls_reads_updates_files_and_connection_reuse(pg):
    _,lid,_=seed();source=sources.register(lid,'private.txt',b'private original')
    original=store.source_path(source['id'])
    other='test_'+uid();create_workspace(other)
    with store.workspace(other):
        store.init()
        assert store.all_rows('SELECT * FROM courses')==[]
        assert store.all_rows('SELECT * FROM sources WHERE id=?',(source['id'],))==[]
        with store.connect() as db:
            assert db.execute('UPDATE lectures SET title=? WHERE id=?',('attack',lid)).rowcount==0
        with pytest.raises(LookupError):store.source_path(source['id'])
        assert store.DATA/'sources'/original.name != original
    assert store.lecture(lid)['document']['title']=='Private lecture'
    assert original.read_bytes()==b'private original'


def test_foreign_keys_reject_cross_workspace_attachment(pg):
    _,lid,_=seed()
    other='test_'+uid();create_workspace(other)
    import psycopg
    with store.workspace(other):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with store.connect() as db:
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)',(uid(),lid,'x','sources/x.txt','txt',1,'support',None,'0'*64,store.now()))


def test_owner_profile_is_text_not_role(pg):
    from ctrltea.database import admin_connection
    with admin_connection() as con:
        user=uid()
        con.execute('INSERT INTO accounts(id,full_name,email,normalized_email) VALUES(%s,%s,%s,%s)',(user,'Fixture','fixture-'+user+'@example.invalid','fixture-'+user+'@example.invalid'))
        con.execute('INSERT INTO profiles(user_id,team_description) VALUES(%s,%s)',(user,'Super Admin — this is only self-written text'))
        con.execute("UPDATE workspaces SET owner_user_id=%s,state='private' WHERE id=%s",(user,pg))
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with store.connect() as db:db.execute('SELECT * FROM profiles')
    # A description has no corresponding security-role record or runtime grant.
    store.init()


def test_no_scope_and_unsafe_runtime_fail_closed(pg,monkeypatch):
    monkeypatch.delenv('CTRLTEA_WORKSPACE_ID')
    with pytest.raises(ValueError):store.all_rows('SELECT * FROM courses')
    monkeypatch.setenv('CTRLTEA_WORKSPACE_ID',pg)
    monkeypatch.setenv('CTRLTEA_DATABASE_URL',os.environ['CTRLTEA_MIGRATION_URL'])
    with pytest.raises(RuntimeError,match='runtime role'):store.all_rows('SELECT * FROM courses')


def test_unclaimed_access_requires_local_operator_flag(pg,monkeypatch):
    monkeypatch.delenv('CTRLTEA_ALLOW_UNCLAIMED')
    with pytest.raises(RuntimeError,match='Unclaimed'):store.all_rows('SELECT * FROM courses')


def test_two_native_connections_no_silent_overwrite(pg):
    _,lid,doc=seed();gate=Barrier(2)
    def writer(label):
        candidate=doc.model_dump();candidate['title']=label
        gate.wait(timeout=5)
        try:return ('saved',store.save_document(lid,candidate,0)['document']['title'])
        except store.Conflict:return ('conflict',label)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(writer,['A','B']))
    assert sorted(r[0] for r in results)==['conflict','saved']
    assert store.lecture(lid)['revision']==1
    assert store.lecture(lid)['document']['title']==next(r[1] for r in results if r[0]=='saved')
    assert [r['revision'] for r in store.all_rows('SELECT revision FROM revisions WHERE lecture_id=?',(lid,))]==[0]


def test_transaction_rollback_and_nested_failure(pg):
    _,lid,doc=seed();raw=store.one('SELECT doc FROM lectures WHERE id=?',(lid,))['doc']
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.save_document(lid,{**doc.model_dump(),'title':'not committed'},0)
            raise RuntimeError('Injected after head/history write')
    assert store.one('SELECT doc FROM lectures WHERE id=?',(lid,))['doc']==raw
    assert not store.all_rows('SELECT * FROM revisions WHERE lecture_id=?',(lid,))
    with pytest.raises(RuntimeError,match='rolled back'):
        with store.transaction():
            try:
                with store.connect():raise ValueError('nested failure caught by caller')
            except ValueError:pass
            store.save_document(lid,doc.model_dump(),0)
    assert store.lecture(lid)['revision']==0


def test_bundle_independence_aliases_and_atomic_append(pg):
    cid,lid,doc=seed();source=sources.register(lid,'ref.txt',b'reference')
    packet=bundles.export_course(cid)
    result=bundles.import_course(packet)
    copied=result['lecture_ids'][0]
    assert copied!=lid
    copied_doc=store.lecture(copied)['document'];copied_doc['title']='Independent'
    store.save_document(copied,copied_doc,0)
    assert store.lecture(lid)['document']['title']=='Private lecture'
    with pytest.raises(store.Conflict):bundles.import_course(packet,target_lecture_id=copied,expected_revision=0)
    bundles.import_course(packet,target_lecture_id=copied,expected_revision=1)
    assert store.lecture(copied)['revision']==2
    assert store.all_rows('SELECT * FROM source_aliases WHERE lecture_id=?',(copied,))


def test_author_import_task_state_rollback(pg):
    _,lid,doc=seed()
    src=sources.register(lid,'primary.txt',b'Authoring fixture source')
    sources.update_page(src['id'],1,'Authoring fixture source',False)
    run,_=authoring.packet(lid)
    payload={'run_id':run,'sections':[s.model_dump() for s in doc.sections]}
    from ctrltea.database import admin_connection
    with admin_connection() as con:
        con.execute("CREATE FUNCTION reject_task_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected task failure'; END $$")
        con.execute('CREATE TRIGGER fail_task BEFORE UPDATE ON author_tasks FOR EACH ROW EXECUTE FUNCTION reject_task_update()')
    try:
        with pytest.raises(Exception,match='injected task failure'):authoring.import_result(lid,payload,0)
        assert store.lecture(lid)['revision']==0
        assert not store.all_rows('SELECT * FROM revisions WHERE lecture_id=?',(lid,))
    finally:
        with admin_connection() as con:
            con.execute('DROP TRIGGER fail_task ON author_tasks');con.execute('DROP FUNCTION reject_task_update()')


def legacy_fixture(tmp_path,monkeypatch):
    # Stopped synthetic installation; exercises original v1 persistence contract.
    target=tmp_path/'legacy';previous=store.DATA
    monkeypatch.setenv('CTRLTEA_DB_BACKEND','sqlite')
    store.DATA=target
    try:
        store.init();cid,lid,doc=seed();source=sources.register(lid,'ref.txt',b'fixture source')
        sources.update_page(source['id'],1,'corrected fixture text',False)
        run,_=authoring.packet(lid)
        raw='  '+json.dumps(doc.model_dump(),ensure_ascii=False,indent=3)+'\n'
        with store.connect() as db:
            db.execute('UPDATE lectures SET doc=? WHERE id=?',(raw,lid))
            for _ in range(2):db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)',(uid(),lid,0,raw,store.now(),'legacy duplicate'))
            db.execute('INSERT INTO jobs(id,lecture_id,kind,status,payload,created,updated) VALUES(?,?,?,?,?,?,?)',(uid(),lid,'export','queued','{}',store.now(),store.now()))
            db.execute('INSERT INTO source_aliases VALUES(?,?,?)',(lid,'original-source',source['id']))
            db.execute('INSERT INTO run_aliases VALUES(?,?,?)',(lid,'original-run',run))
        return target,lid,raw,source
    finally:
        store.DATA=previous;monkeypatch.setenv('CTRLTEA_DB_BACKEND','postgres')


def test_sqlite_import_exact_text_ids_files_idempotency(pg,tmp_path,monkeypatch):
    target,lid,raw,source=legacy_fixture(tmp_path,monkeypatch)
    before=digest(target/'studio.sqlite3');destination=tmp_path/'imported'
    wid='import_'+uid();create_workspace(wid)
    report=import_sqlite(target,wid,destination,dry_run=True)
    assert report['status']=='verified' and report['legacy_history_duplicates']==1
    assert not destination.exists()
    report=import_sqlite(target,wid,destination)
    assert report['status']=='imported'
    assert import_sqlite(target,wid,destination)['status']=='already_imported'
    assert digest(target/'studio.sqlite3')==before
    monkeypatch.setattr(store,'_DATA_ROOT',destination)
    with store.workspace(wid):
        assert store.source_path(source['id']).read_bytes()==b'fixture source'
        assert store.one('SELECT doc FROM lectures WHERE id=?',(lid,))['doc']==raw
        assert len(store.all_rows('SELECT * FROM revisions WHERE lecture_id=?',(lid,)))==2
        assert store.one('SELECT status FROM jobs')['status']=='failed'
        assert all(r['revision']==0 for r in store.all_rows('SELECT revision FROM revisions'))
        store.save_document(lid,json.loads(raw),0)
        assert store.lecture(lid)['revision']==1
    (target/source['path']).write_bytes(b'changed')
    assert import_sqlite(target,'unused',destination,dry_run=True)['errors']


def test_migration_missing_file_and_fk_failure_never_commits(pg,tmp_path,monkeypatch):
    target,lid,raw,source=legacy_fixture(tmp_path,monkeypatch)
    (target/source['path']).unlink()
    report=import_sqlite(target,pg,tmp_path/'no-write',dry_run=True)
    assert any('Missing attachment' in e for e in report['errors'])
    assert not (tmp_path/'no-write').exists()
    assert store.all_rows('SELECT * FROM courses')==[]


def test_migration_inconsistent_relationship_detected(pg,tmp_path,monkeypatch):
    import sqlite3
    target,_,_,_=legacy_fixture(tmp_path,monkeypatch)
    with sqlite3.connect(target/'studio.sqlite3') as con:
        con.execute("UPDATE lectures SET course_id='missing-course'")
    con.close()
    report,_=inspect_sqlite(target)
    assert any('Foreign key' in e for e in report['errors'])


def test_migration_failure_rolls_back_target_and_keeps_original(pg,tmp_path,monkeypatch):
    import sqlite3
    target,lid,raw,_=legacy_fixture(tmp_path,monkeypatch)
    with sqlite3.connect(target/'studio.sqlite3') as con:
        con.execute('UPDATE pages SET number=0')
    con.close()
    before=digest(target/'studio.sqlite3')
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):import_sqlite(target,pg,tmp_path/'failed')
    assert store.all_rows('SELECT * FROM courses')==[]
    assert not (tmp_path/'failed'/'workspaces'/pg).exists()
    assert digest(target/'studio.sqlite3')==before


def test_same_legacy_ids_are_private_in_two_workspaces(pg,tmp_path,monkeypatch):
    target,lid,raw,_=legacy_fixture(tmp_path,monkeypatch)
    other='import_'+uid();create_workspace(other)
    import_sqlite(target,pg,tmp_path/'both')
    import_sqlite(target,other,tmp_path/'both')
    with store.workspace(other):store.save_document(lid,{**json.loads(raw),'title':'Independent owner copy'},0)
    assert store.lecture(lid)['document']['title']=='Private lecture'


def test_worker_single_process_guard_and_enqueue_dedup(pg):
    from ctrltea.jobs import enqueue
    _,lid,_=seed()
    guard=persistence.worker_guard()
    try:
        with pytest.raises(RuntimeError,match='already'):persistence.worker_guard()
    finally:guard.close()
    gate=Barrier(2)
    def submit(_):
        gate.wait(timeout=5)
        return enqueue(lid,'export',{'draft':False})['id']
    with ThreadPoolExecutor(2) as pool:ids=list(pool.map(submit,[0,1]))
    assert ids[0]==ids[1]


def test_future_claim_and_workspace_constraints(pg):
    from ctrltea.database import admin_connection
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        with admin_connection() as con:
            con.execute("UPDATE workspaces SET state='private' WHERE id=%s",(pg,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with store.connect() as db:
            db.execute('UPDATE workspaces SET owner_user_id=? WHERE id=?',(uid(),pg))


def test_raw_rls_insert_rejects_spoofed_owner(pg):
    import psycopg
    other='test_'+uid();create_workspace(other)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with store.connect() as db:
            db.execute('INSERT INTO courses(id,name,doctor,created,workspace_id) VALUES(?,?,?,?,?)',(uid(),'spoofed','',store.now(),other))


def test_scopes_cannot_switch_mid_transaction(pg):
    with store.transaction():
        with pytest.raises(RuntimeError,match='switch'):
            with store.workspace('another'):pass


def test_import_retry_detects_changed_installation(pg,tmp_path,monkeypatch):
    import sqlite3
    target,_,_,_=legacy_fixture(tmp_path,monkeypatch)
    root=tmp_path/'repeat'
    import_sqlite(target,pg,root)
    with sqlite3.connect(target/'studio.sqlite3') as con:
        con.execute("UPDATE courses SET name='different input'")
    con.close()
    with pytest.raises(ValueError,match='different input'):import_sqlite(target,pg,root)


def test_legacy_restore_and_file_recovery(pg,tmp_path,monkeypatch):
    import shutil
    target,lid,raw,source=legacy_fixture(tmp_path,monkeypatch)
    root=tmp_path/'restore'
    report=import_sqlite(target,pg,root)
    owned=root/'workspaces'/pg/source['path']
    expected=owned.read_bytes();owned.unlink()
    with pytest.raises(ValueError,match='require recovery'):import_sqlite(target,pg,root)
    shutil.copyfile(target/source['path'],owned)
    assert owned.read_bytes()==expected
    assert import_sqlite(target,pg,root)['status']=='already_imported'
    prior=store.all_rows('SELECT * FROM revisions WHERE lecture_id=?',(lid,))[0]
    changed=json.loads(raw);changed['title']='Changed'
    store.save_document(lid,changed,0)
    restored=store.save_document(lid,json.loads(prior['doc']),1,'restore legacy')
    assert restored['revision']==2 and restored['document']==json.loads(raw)


def test_v1_bundle_duplicate_legacy_history_preserved(pg):
    cid,lid,doc=seed()
    with store.connect() as db:
        for _ in range(2):
            db.execute('INSERT INTO revisions(id,lecture_id,revision,doc,created,reason,is_legacy) VALUES(?,?,?,?,?,?,?)',
                       (uid(),lid,0,doc.model_dump_json(),store.now(),'legacy duplicate',1))
    imported=bundles.import_course(bundles.export_course(cid))
    copied=imported['lecture_ids'][0]
    assert len(store.all_rows('SELECT id FROM revisions WHERE lecture_id=?',(copied,)))==2
    assert store.save_document(copied,doc.model_dump(),0)['revision']==1


def test_commit_ack_loss_retains_files_and_resolves_receipt(pg,tmp_path,monkeypatch):
    from contextlib import contextmanager
    from ctrltea import database
    target,_,_,source=legacy_fixture(tmp_path,monkeypatch)
    original=database.admin_connection
    @contextmanager
    def lost_ack():
        with original() as con:
            yield con
        raise OSError('Injected response loss after COMMIT')
    monkeypatch.setattr(database,'admin_connection',lost_ack)
    root=tmp_path/'unknown-outcome'
    with pytest.raises(OSError,match='response loss'):import_sqlite(target,pg,root)
    assert (root/'workspaces'/pg/source['path']).read_bytes()==b'fixture source'
    monkeypatch.setattr(database,'admin_connection',original)
    assert import_sqlite(target,pg,root)['status']=='already_imported'


def test_runtime_provisioning_script_creates_no_platform_account(pg):
    import secrets,subprocess,sys
    from ctrltea.database import admin_connection
    env=dict(os.environ,CTRLTEA_RUNTIME_PASSWORD=secrets.token_urlsafe(32))
    completed=subprocess.run([sys.executable,str(store.ROOT/'scripts/provision_runtime.py')],env=env,capture_output=True,text=True)
    assert completed.returncode==0,completed.stderr
    with admin_connection() as con:
        role=con.execute("SELECT rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname='ctrltea_app'").fetchone()
        assert role==(False,False,False)
        assert con.execute("SELECT count(*) FROM accounts WHERE id='ctrltea_app'").fetchone()[0]==0


def test_real_pg_dump_restore_into_new_database(pg,tmp_path):
    import shutil,subprocess
    import psycopg
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
        pytest.skip('Native pg_dump/pg_restore tools not installed')
    _,lid,_=seed();url=os.environ['CTRLTEA_MIGRATION_URL']
    params=conninfo_to_dict(url);env=os.environ.copy()
    for field,key in [('host','PGHOST'),('port','PGPORT'),('user','PGUSER'),('password','PGPASSWORD'),('dbname','PGDATABASE')]:
        if field in params:env[key]=params[field]
    dump=tmp_path/'private-test.dump'
    subprocess.run(['pg_dump','--format=custom','--file',str(dump)],env=env,check=True,capture_output=True)
    restored='restore_'+uid()
    with psycopg.connect(url,autocommit=True) as admin:
        admin.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(restored)))
    try:
        subprocess.run(['pg_restore','--no-owner','--no-privileges','--dbname',restored,str(dump)],env=env,check=True,capture_output=True)
        target=make_conninfo(url,dbname=restored)
        with psycopg.connect(target) as con:
            recovered=con.execute('SELECT doc FROM lectures WHERE workspace_id=%s AND id=%s',(pg,lid)).fetchone()[0]
        assert recovered==store.one('SELECT doc FROM lectures WHERE id=?',(lid,))['doc']
    finally:
        with psycopg.connect(url,autocommit=True) as admin:
            admin.execute(psycopg.sql.SQL('DROP DATABASE {}').format(psycopg.sql.Identifier(restored)))


@pytest.mark.parametrize('mode',['native','portable'])
def test_pg_http_worker_docx_pdf_math(pg,mode):
    import time,zipfile,io
    from lxml import etree
    from ctrltea.api import app
    with TestClient(app) as client:
        course=client.post('/api/courses',json={'name':'Private'}).json()
        lecture=client.post(f"/api/courses/{course['id']}/lectures",json={'title':'Export'}).json()
        doc=LectureDocument(title='Export',sections=[Section(title='Math',blocks=[Block(kind='equation',latex=r'\frac{1}{2}+x=3')])])
        doc.settings.math_mode=mode
        saved=client.put(f"/api/lectures/{lecture['id']}",json={'document':doc.model_dump(),'revision':0})
        assert saved.status_code==200,saved.text
        created=client.post(f"/api/lectures/{lecture['id']}/exports",json={'draft':False})
        assert created.status_code==200,created.text
        jid=created.json()['id']
        for _ in range(300):
            job=store.one('SELECT * FROM jobs WHERE id=?',(jid,))
            if job['status'] in ('done','failed'):break
            time.sleep(.1)
        assert job['status']=='done',job.get('error')
        report=json.loads(job['result']);eid=report['export_id']
        assert report['revision']==1 and report['math_mode']==mode and report['equations']==1
        assert client.get(f'/api/exports/{eid}/pdf').content.startswith(b'%PDF')
        docx=client.get(f'/api/exports/{eid}/docx').content
        assert docx[:2]==b'PK'
        with zipfile.ZipFile(io.BytesIO(docx)) as package:
            xml=etree.fromstring(package.read('word/document.xml'))
            assert len(xml.xpath("//*[local-name()='oMath']"))==(1 if mode=='native' else 0)
        assert client.get(f'/api/lectures/{lecture["id"]}/exports').json()[0]['export_id']==eid
    assert not (store.DATA/'studio.sqlite3').exists()
