"""Upgrade an actual Task03 schema, not merely an empty Task04 database."""
import json,os,secrets,subprocess,sys
from pathlib import Path
import pytest
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from ctrltea.models import LectureDocument,uid

pytestmark=pytest.mark.skipif(not os.environ.get('CTRLTEA_MIGRATION_URL') or not os.environ.get('CTRLTEA_TEST_DATABASE_URL'),reason='Disposable PostgreSQL operator required')


def test_task03_to_task04_preserves_existing_science_metadata_and_duplicates(tmp_path):
    operator=os.environ['CTRLTEA_MIGRATION_URL'];name='task04_upgrade_'+uid()
    target=make_url(operator).set(database=name).render_as_string(hide_password=False)
    project=Path(__file__).resolve().parents[1];env={**os.environ,'CTRLTEA_MIGRATION_URL':target}
    raw='\n '+LectureDocument(title='Legacy untouched').model_dump_json(indent=2)+'\n'
    with psycopg.connect(operator,autocommit=True) as con:con.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        result=subprocess.run([sys.executable,'-m','alembic','upgrade','0001_private'],cwd=project,env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        with psycopg.connect(target) as con:
            con.execute("INSERT INTO accounts(id,full_name,email,normalized_email) VALUES('preserved-user','Existing member','existing@example.com','existing@example.com')")
            con.execute("INSERT INTO profiles(user_id,team_description) VALUES('preserved-user','Original self-written description')")
            con.execute("INSERT INTO workspaces(id,owner_user_id,state) VALUES('preserved-space','preserved-user','private')")
            con.execute("SELECT set_config('ctrltea.workspace_id','preserved-space',true)")
            con.execute("INSERT INTO courses(id,name,doctor,created) VALUES('course','Original course','Original doctor','legacy-time')")
            con.execute("INSERT INTO lectures(id,course_id,title,doc,revision,updated,theme) VALUES('lecture','course','Legacy untouched',%s,7,'legacy-time','olive')",(raw,))
            for identifier in ('history-a','history-b'):
                con.execute("INSERT INTO revisions(id,lecture_id,revision,doc,created,reason,is_legacy) VALUES(%s,'lecture',2,%s,'legacy-time','Original history',1)",(identifier,raw))
            con.execute("INSERT INTO sources(id,lecture_id,name,path,kind,digest,created) VALUES('source','lecture','original.txt','sources/original.txt','txt',%s,'legacy-time')",('a'*64,))
            con.execute("INSERT INTO pages(source_id,number,raw,corrected,method) VALUES('source',1,'Original raw text','Original correction','text')")
            con.execute("INSERT INTO author_runs(id,lecture_id,section_ids,status,created,base_doc) VALUES('run','lecture','[]','pending','legacy-time',%s)",(raw,))
            con.execute("INSERT INTO author_tasks(run_id,section_id,status) VALUES('run','new','pending')")
            con.execute("INSERT INTO source_aliases(lecture_id,original_id,source_id) VALUES('lecture','alias-source','source')")
            con.execute("INSERT INTO run_aliases(lecture_id,original_id,run_id) VALUES('lecture','alias-run','run')")
            con.execute("INSERT INTO jobs(id,lecture_id,kind,status,payload,created,updated) VALUES('job','lecture','export','failed','{}','legacy-time','legacy-time')")
            tables=['accounts','profiles','workspaces','courses','lectures','revisions','sources','pages','author_runs','author_tasks','source_aliases','run_aliases','jobs']
            before={}
            for table in tables:
                cols=[r[0] for r in con.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=%s ORDER BY ordinal_position',(table,))]
                rows=con.execute(sql.SQL('SELECT {} FROM {} ORDER BY 1,2').format(sql.SQL(',').join(map(sql.Identifier,cols)),sql.Identifier(table))).fetchall()
                before[table]=(cols,rows)
        for _ in range(2):
            result=subprocess.run([sys.executable,'-m','ctrltea.database','upgrade'],cwd=project,env=env,capture_output=True,text=True)
            assert result.returncode==0,result.stderr
        with psycopg.connect(target) as con:
            assert con.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='0002_accounts'
            for table,(cols,rows) in before.items():
                after=con.execute(sql.SQL('SELECT {} FROM {} ORDER BY 1,2').format(sql.SQL(',').join(map(sql.Identifier,cols)),sql.Identifier(table))).fetchall()
                assert after==rows,table
            assert con.execute('SELECT count(*) FROM credentials').fetchone()[0]==0
            assert con.execute("SELECT role,auth_version FROM accounts WHERE id='preserved-user'").fetchone()==('Member',0)
            assert con.execute('SELECT count(*) FROM revisions').fetchone()[0]==2
            # Destructive downgrade must refuse instead of discarding accounts.
        refused=subprocess.run([sys.executable,'-m','alembic','downgrade','0001_private'],cwd=project,env=env,capture_output=True,text=True)
        assert refused.returncode!=0 and 'restore' in (refused.stdout+refused.stderr).lower()
        with psycopg.connect(target) as con:assert con.execute('SELECT count(*) FROM lectures').fetchone()[0]==1
    finally:
        with psycopg.connect(operator,autocommit=True) as con:con.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
