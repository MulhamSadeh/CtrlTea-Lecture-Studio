"""Adversarial ownership, races and actual upgrade coverage for Task04."""
import io,json,os,secrets,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ctrltea import accounts as a,store,persistence
from ctrltea.api import app
from ctrltea.models import LectureDocument,uid
from test_accounts import auth,team,operator,client,signup,login,link,lecture,BASE

pytestmark=pytest.mark.skipif(not os.environ.get('CTRLTEA_TEST_DATABASE_URL'),reason='Disposable PostgreSQL/auth-service fixture not configured')


def test_cross_user_write_and_download_matrix(team):
    course,row=lecture(team.bob);c=team.alice.client;wid=team.bob.me['workspace_id'];h={'X-Ctrltea-Workspace':wid}
    uploaded=team.bob.client.post('/api/lectures/'+row['id']+'/sources',files={'file':('private.txt',b'Private original source','text/plain')}).json()
    sid=uploaded['source']['id'];jid=uploaded['job']['id']
    for method,path,payload in [
      ('PUT','/api/courses/'+course['id'],{'name':'stolen'}),('DELETE','/api/courses/'+course['id'],None),
      ('POST','/api/courses/'+course['id']+'/lectures',{'title':'injected'}),
      ('PUT','/api/lectures/'+row['id'],{'document':row['document'],'revision':1}),
      ('DELETE','/api/lectures/'+row['id'],None),('PUT','/api/lectures/'+row['id']+'/theme',{'theme':'olive'}),
      ('POST','/api/lectures/'+row['id']+'/exports',{'draft':True}),
      ('POST','/api/lectures/'+row['id']+'/authoring/packet',{'section_ids':[]}),
      ('PUT','/api/sources/'+sid,{'priority':1,'role':'support'}),('DELETE','/api/sources/'+sid,None),
      ('PUT','/api/sources/'+sid+'/pages/1',{'corrected':'stolen','excluded':False}),
      ('POST','/api/sources/'+sid+'/extract',{}),('POST','/api/jobs/'+jid+'/retry',{})
    ]:
        r=c.request(method,path,json=payload,headers=h);assert r.status_code==404,(path,r.text)
    for path in ['/api/sources/'+sid+'/file','/api/sources/'+sid+'/pages','/api/sources/'+sid+'/pages/1/image']:
        assert c.get(path,params={'workspace':wid}).status_code==404
    assert c.post('/api/lectures/'+row['id']+'/sources',headers=h,files={'file':('inject.txt',b'X','text/plain')}).status_code==404
    assert team.bob.client.get('/api/lectures/'+row['id']).json()['document']==row['document']


def test_scoped_grant_does_not_expose_sibling_or_body_sources(team):
    _,allowed=lecture(team.bob);_,sibling=lecture(team.bob)
    uploaded=team.bob.client.post('/api/lectures/'+sibling['id']+'/sources',files={'file':('private.txt',b'Private sibling','text/plain')}).json()
    r=team.admin.client.post('/api/admin/grants',json={'user_id':team.alice.me['id'],'workspace_id':team.bob.me['workspace_id'],'resource_kind':'lecture','resource_id':allowed['id'],'permissions':['lectures.view','lectures.edit','sources.view','figures.preview']});assert r.status_code==200
    login(team.alice.client,team.alice.email,team.alice.password)
    h={'X-Ctrltea-Workspace':team.bob.me['workspace_id']}
    assert team.alice.client.get('/api/lectures/'+allowed['id'],headers=h).status_code==200
    assert team.alice.client.get('/api/lectures/'+sibling['id'],headers=h).status_code==404
    doc=allowed['document'];doc['sections'][0]['blocks'][0]['refs']=[{'source_id':uploaded['source']['id'],'page':1}]
    assert team.alice.client.put('/api/lectures/'+allowed['id'],json={'document':doc,'revision':1},headers=h).status_code==404
    assert team.alice.client.get('/api/sources/'+uploaded['source']['id']+'/file',headers=h).status_code==404


def test_avatar_is_reencoded_private_and_svg_rejected(team):
    from PIL import Image
    c=team.alice.client
    assert c.post('/api/account/avatar',files={'file':('evil.svg',b'<svg onload="alert(1)"/>','image/svg+xml')}).status_code==422
    assert c.post('/api/account/avatar',files={'file':('huge.png',b'X'*(2*1024*1024+1),'image/png')}).status_code==422
    image=io.BytesIO();Image.new('RGB',(12,12),'red').save(image,'PNG')
    assert c.post('/api/account/avatar',files={'file':('portrait.png',image.getvalue(),'image/png')}).status_code==200
    r=team.bob.client.get('/api/members/'+team.alice.me['id']+'/avatar');assert r.status_code==200 and r.headers['content-type']=='image/png'
    assert client().get('/api/members/'+team.alice.me['id']+'/avatar').status_code==401
    assert team.admin.client.put('/api/admin/members/'+team.alice.me['id'],json={'state':'disabled'}).status_code==200
    assert team.bob.client.get('/api/members/'+team.alice.me['id']+'/avatar').status_code==404
    assert team.admin.client.get('/api/members/'+team.alice.me['id']+'/avatar').status_code==200


def test_idle_session_rotation_secure_cookie_and_no_fixation(auth,monkeypatch):
    c=client();email='rotate-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink);me=login(c,email,pwd);old=c.cookies.get(a.cookie_name())
    login(c,email,pwd);assert old!=c.cookies.get(a.cookie_name())
    stale=client();stale.cookies.set(a.cookie_name(),old);assert stale.get('/api/auth/me').status_code==401
    with operator() as con:con.execute("UPDATE sessions SET last_seen=now()-interval '13 hours' WHERE user_id=%s",(me['id'],))
    assert c.get('/api/courses').status_code==401
    monkeypatch.setenv('CTRLTEA_COOKIE_SECURE','1');monkeypatch.setenv('CTRLTEA_PUBLIC_ORIGIN','https://localhost:8765')
    secure=TestClient(app,base_url='https://localhost:8765',headers={'Origin':'https://localhost:8765'})
    r=secure.post('/api/auth/login',json={'email':email,'password':pwd});assert r.status_code==200
    cookie=r.headers['set-cookie'];assert cookie.startswith('__Host-ct_session=') and 'Secure' in cookie and 'HttpOnly' in cookie
    assert secure.get('/api/auth/me').status_code==200
    with operator() as con:
        hashes=[r['token_hash'] for r in con.execute('SELECT token_hash FROM sessions WHERE user_id=%s',(me['id'],))]
    assert secure.cookies.get('__Host-ct_session') not in hashes


def test_password_change_invalidates_old_recovery_link(team):
    c=team.alice.client;c.post('/api/auth/forgot',json={'email':team.alice.email});token=link(team.auth.sink,team.alice.email,'reset')
    pwd=secrets.token_urlsafe(24)
    assert c.post('/api/auth/password',json={'current_password':team.alice.password,'password':pwd,'confirm_password':pwd}).status_code==200
    assert client().post('/api/auth/reset',json={'token':token,'password':pwd,'confirm_password':pwd}).status_code==400


def test_suspension_cancels_outstanding_tokens(team):
    c=team.alice.client;c.post('/api/auth/forgot',json={'email':team.alice.email});token=link(team.auth.sink,team.alice.email,'reset')
    assert team.admin.client.put('/api/admin/members/'+team.alice.me['id'],json={'state':'disabled'}).status_code==200
    assert team.admin.client.put('/api/admin/members/'+team.alice.me['id'],json={'state':'active'}).status_code==200
    assert client().post('/api/auth/reset',json={'token':token,'password':team.alice.password,'confirm_password':team.alice.password}).status_code==400


def legacy_space():
    wid='legacy_'+uid();lid=uid();cid=uid();sid=uid();raw=LectureDocument(title='Preserved legacy').model_dump_json(indent=2)
    with operator() as con:con.execute("INSERT INTO workspaces(id,state) VALUES(%s,'unclaimed')",(wid,))
    privilege=a.admin_scope.set(True)
    try:
        with store.workspace(wid):
            for folder in ('sources','exports','figures','math','bundles'):(store.DATA/folder).mkdir(parents=True,exist_ok=True)
            file=store.DATA/'sources/legacy.txt';file.write_bytes(b'Immutable legacy source')
            with store.transaction() as db:
                db.execute('INSERT INTO courses VALUES(?,?,?,?)',(cid,'Legacy course','',store.now()))
                db.execute('INSERT INTO lectures(id,course_id,title,doc,revision,updated) VALUES(?,?,?,?,?,?)',(lid,cid,'Preserved legacy',raw,7,store.now()))
                db.execute('INSERT INTO revisions(id,lecture_id,revision,doc,created,reason,is_legacy) VALUES(?,?,?,?,?,?,?)',(uid(),lid,2,raw,store.now(),'unknown legacy',1))
                db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,lid,'legacy.txt','sources/legacy.txt','txt',1,'support',None,__import__('hashlib').sha256(file.read_bytes()).hexdigest(),store.now()))
                db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?)',(sid,1,'original','corrected',0,'text'))
                db.execute('INSERT INTO source_aliases VALUES(?,?,?)',(lid,'old_source',sid))
                store.record_asset(file,lid)
    finally:a.admin_scope.reset(privilege)
    return wid,lid,sid,raw


def test_legacy_assignment_preserves_ids_files_history_and_replay(team):
    wid,lid,sid,raw=legacy_space();body={'workspace_id':wid,'user_id':team.bob.me['id']}
    assert team.alice.client.post('/api/admin/legacy/assign',json=body).status_code==403
    r=team.admin.client.post('/api/admin/legacy/assign',json=body);assert r.status_code==200,r.text
    assert team.bob.client.get('/api/auth/me').status_code==401
    me=login(team.bob.client,team.bob.email,team.bob.password);assert me['workspace_id']==wid
    assert team.bob.client.get('/api/lectures/'+lid).json()['revision']==7
    assert team.bob.client.get('/api/sources/'+sid+'/file').content==b'Immutable legacy source'
    with operator() as con:assert con.execute('SELECT doc FROM lectures WHERE workspace_id=%s AND id=%s',(wid,lid)).fetchone()['doc']==raw
    assert len(team.bob.client.get('/api/lectures/'+lid+'/revisions').json())==1
    assert team.admin.client.post('/api/admin/legacy/assign',json=body).status_code==409


def test_legacy_nonempty_destination_and_concurrent_claims(team):
    lecture(team.alice);wid,*_=legacy_space()
    assert team.admin.client.post('/api/admin/legacy/assign',json={'workspace_id':wid,'user_id':team.alice.me['id']}).status_code==409
    def assign(member):return team.admin.client.post('/api/admin/legacy/assign',json={'workspace_id':wid,'user_id':member.me['id']}).status_code
    # Only one of two verified empty destinations can claim the same workspace.
    extra=client();email='claim-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24);signup(extra,email,pwd,team.auth.sink)
    from types import SimpleNamespace
    other=SimpleNamespace(me=login(extra,email,pwd))
    with ThreadPoolExecutor(2) as pool:codes=list(pool.map(assign,[team.bob,other]))
    assert sorted(codes)==[200,409]


def test_concurrent_last_admin_protection(team):
    with operator() as con:con.execute("UPDATE accounts SET role='Member' WHERE role='SuperAdmin' AND id<>%s",(team.admin.me['id'],))
    assert team.admin.client.put('/api/admin/members/'+team.alice.me['id'],json={'role':'SuperAdmin'}).status_code==200
    login(team.alice.client,team.alice.email,team.alice.password)
    def demote(pair):
        source,target=pair
        return source.client.put('/api/admin/members/'+target.me['id'],json={'role':'Member'}).status_code
    with ThreadPoolExecutor(2) as pool:codes=list(pool.map(demote,[(team.admin,team.alice),(team.alice,team.admin)]))
    assert sorted(codes)==[200,409]
    with operator() as con:assert con.execute("SELECT count(*) AS n FROM accounts WHERE role='SuperAdmin' AND state='active'").fetchone()['n']==1


def test_old_metadata_account_activates_without_losing_profile(auth):
    identifier=uid();email='old-account-'+uid()+'@example.com';password=secrets.token_urlsafe(24)
    with operator() as con:
        con.execute('INSERT INTO accounts(id,full_name,email,normalized_email) VALUES(%s,%s,%s,%s)',(identifier,'Existing member',email,email))
        con.execute('INSERT INTO profiles(user_id,team_description) VALUES(%s,%s)',(identifier,'Preserved self-written description'))
    c=client();assert c.post('/api/auth/resend',json={'email':email}).status_code==202
    assert c.post('/api/auth/verify',json={'token':link(auth.sink,email,'verify')}).status_code==200
    c.post('/api/auth/forgot',json={'email':email});token=link(auth.sink,email,'reset')
    assert c.post('/api/auth/reset',json={'token':token,'password':password,'confirm_password':password}).status_code==200
    assert login(c,email,password)['id']==identifier
    assert c.get('/api/account/profile').json()['team_description']=='Preserved self-written description'


def test_unpublished_export_not_exposed(team):
    _,row=lecture(team.bob);eid=uid();privilege=a.admin_scope.set(True)
    try:
        with store.workspace(team.bob.me['workspace_id']):
            directory=store.DATA/'exports'/eid;directory.mkdir(parents=True)
            (directory/'report.json').write_text(json.dumps({'lecture_id':row['id'],'created':store.now(),'export_id':eid}))
            (directory/'lecture.pdf').write_bytes(b'%PDF-unpublished-attempt')
    finally:a.admin_scope.reset(privilege)
    assert team.bob.client.get('/api/exports/'+eid+'/pdf').status_code==404
    assert team.bob.client.get('/api/lectures/'+row['id']+'/exports').json()==[]


def test_mail_transport_contract_and_failure_recovery(auth,monkeypatch):
    from ctrltea import mailer
    calls=[]
    class SMTP:
        def __init__(self,*args,**kwargs):calls.append('connect')
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def starttls(self,context):calls.append('tls')
        def login(self,*args):calls.append('login')
        def send_message(self,message):
            assert message.is_multipart() and message.get_body(preferencelist=('html',))
            calls.append('send')
    monkeypatch.setattr(mailer.smtplib,'SMTP',SMTP)
    monkeypatch.setenv('CTRLTEA_MAIL_PROVIDER','smtp');monkeypatch.setenv('CTRLTEA_SMTP_HOST','smtp.example.invalid')
    monkeypatch.setenv('CTRLTEA_MAIL_FROM','Ctrl+Tea <notify@example.com>');monkeypatch.setenv('CTRLTEA_SMTP_USER','synthetic');monkeypatch.setenv('CTRLTEA_SMTP_PASSWORD',secrets.token_urlsafe(24))
    mailer.send('test@example.com','Test','No external network transport used','verify=synthetic')
    assert calls==['connect','tls','login','send']
    # This is an adapter contract test, not evidence of real SMTP delivery.
    monkeypatch.setenv('CTRLTEA_MAIL_PROVIDER','local')
    c=client();email='retry-mail-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    original=mailer.send
    monkeypatch.setattr(mailer,'send',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('test outage')))
    signup(c,email,pwd,auth.sink,verify=False)
    monkeypatch.setattr(mailer,'send',original)
    assert c.post('/api/auth/resend',json={'email':email}).status_code==202
    assert c.post('/api/auth/verify',json={'token':link(auth.sink,email,'verify')}).status_code==200


def test_policy_inventory_and_oversized_secret_redaction(auth):
    from ctrltea.access import POLICY,PUBLIC,ACCOUNT_ROUTES
    from fastapi.routing import APIRoute
    for route in app.routes:
        if isinstance(route,APIRoute):assert route.name in POLICY|dict.fromkeys(PUBLIC)|dict.fromkeys(ACCOUNT_ROUTES) or route.name.startswith('admin_'),route.name
    secret='z'*1000
    r=client().post('/api/auth/login',json={'email':'x@example.com','password':secret})
    assert r.status_code==422 and secret not in r.text
    r=client().post('/api/auth/register',json={'full_name':'X member','email':'weak-'+uid()+'@example.com','password':'aaaaaaaaaaaaaaa','confirm_password':'aaaaaaaaaaaaaaa'})
    assert r.status_code==422


def test_source_and_lecture_trash_preserves_alias_correction_and_expiry(team):
    _,row=lecture(team.bob);c=team.bob.client;admin=team.admin.client;wid=team.bob.me['workspace_id'];h={'X-Ctrltea-Workspace':wid}
    upload=c.post('/api/lectures/'+row['id']+'/sources',files={'file':('keep.txt',b'Original retained bytes','text/plain')}).json()
    sid=upload['source']['id'];jid=upload['job']['id']
    import time
    for _ in range(100):
        job=next(j for j in c.get('/api/lectures/'+row['id']+'/jobs').json() if j['id']==jid)
        if job['status'] in ('done','failed'):break
        time.sleep(.05)
    assert c.put('/api/sources/'+sid+'/pages/1',json={'corrected':'Retain correction','excluded':True}).status_code==200
    privilege=a.admin_scope.set(True)
    try:
        with store.workspace(wid),store.connect() as db:db.execute('INSERT INTO source_aliases VALUES(?,?,?)',(row['id'],'retained-alias',sid))
    finally:a.admin_scope.reset(privilege)
    assert admin.delete('/api/sources/'+sid,headers=h).status_code==200
    records=admin.get('/api/trash',headers=h).json();trash=next(r for r in records if r['resource_id']==sid)
    assert admin.post('/api/trash/'+trash['id']+'/restore',headers=h,json={}).status_code==200
    assert c.get('/api/sources/'+sid+'/file').content==b'Original retained bytes'
    page=c.get('/api/sources/'+sid+'/pages').json()[0];assert page['corrected']=='Retain correction' and page['excluded']==1
    with operator() as con:assert con.execute('SELECT source_id FROM source_aliases WHERE workspace_id=%s AND original_id=%s',(wid,'retained-alias')).fetchone()['source_id']==sid
    assert admin.delete('/api/lectures/'+row['id'],headers=h).status_code==200
    record=next(r for r in admin.get('/api/trash',headers=h).json() if r['resource_id']==row['id'])
    assert admin.post('/api/trash/'+record['id']+'/restore',headers=h,json={}).status_code==200
    assert c.get('/api/lectures/'+row['id']).json()['document']==row['document']
    assert admin.post('/api/trash/'+record['id']+'/restore',headers=h,json={}).status_code==409
    assert admin.delete('/api/lectures/'+row['id'],headers=h).status_code==200
    latest=next(r for r in admin.get('/api/trash',headers=h).json() if r['resource_id']==row['id'] and not r['restored_at'])
    with operator() as con:con.execute("UPDATE trash_records SET expires_at=now()-interval '1 second' WHERE workspace_id=%s AND id=%s",(wid,latest['id']))
    assert admin.post('/api/trash/'+latest['id']+'/restore',headers=h,json={}).status_code==409


def test_authentication_default_fails_closed_without_postgres(monkeypatch):
    monkeypatch.delenv('CTRLTEA_AUTH_MODE',raising=False)
    monkeypatch.setenv('CTRLTEA_DB_BACKEND','sqlite')
    assert a.enabled()
    with pytest.raises(RuntimeError,match='requires PostgreSQL'):a.check_config()
    monkeypatch.setenv('CTRLTEA_AUTH_MODE','local')
    assert not a.enabled()  # Deliberately requested offline compatibility only.
