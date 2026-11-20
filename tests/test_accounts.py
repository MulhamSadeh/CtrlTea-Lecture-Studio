"""Real account/security integration; disposable PostgreSQL and local mail only."""
import json,os,re,secrets,time
from pathlib import Path
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from ctrltea import accounts as a,store,persistence
from ctrltea.api import app
from ctrltea.models import LectureDocument,Section,Block,uid

pytestmark=pytest.mark.skipif(not os.environ.get('CTRLTEA_TEST_DATABASE_URL'),reason='Disposable PostgreSQL/auth-service fixture not configured')
BASE='http://localhost:8765'


def operator():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(os.environ['CTRLTEA_MIGRATION_URL'],row_factory=dict_row)


def link(sink,email,kind):
    found=[]
    for path in Path(sink).glob('*.eml'):
        mail=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        if mail['To']==email:
            match=re.search('#'+kind+r'=([A-Za-z0-9_-]+)',mail.get_body(preferencelist=('plain',)).get_content())
            if match:found.append((path.stat().st_mtime_ns,match.group(1)))
    assert found,'Expected a private local test message; no external delivery was used'
    return max(found)[1]


def client():return TestClient(app,base_url=BASE,headers={'Origin':BASE})


def signup(c,email,password,sink,verify=True):
    r=c.post('/api/auth/register',json={'full_name':'عضو تجريبي','email':email,'password':password,'confirm_password':password})
    assert r.status_code==202,r.text
    if verify:
        r=c.post('/api/auth/verify',json={'token':link(sink,email,'verify')});assert r.status_code==200,r.text


def login(c,email,password):
    r=c.post('/api/auth/login',json={'email':email,'password':password});assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf']
    me=c.get('/api/auth/me');assert me.status_code==200,me.text
    return me.json()


@pytest.fixture
def auth(tmp_path,monkeypatch):
    monkeypatch.setenv('CTRLTEA_AUTH_MODE','required');monkeypatch.setenv('CTRLTEA_DB_BACKEND','postgres')
    monkeypatch.setenv('CTRLTEA_DATABASE_URL',os.environ['CTRLTEA_TEST_DATABASE_URL'])
    monkeypatch.setenv('CTRLTEA_MAIL_SINK',str(tmp_path/'mail'));monkeypatch.setenv('CTRLTEA_PROFILE_DIR',str(tmp_path/'profiles'))
    monkeypatch.setenv('CTRLTEA_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setattr(store,'_DATA_ROOT',tmp_path/'data')
    with operator() as con:
        con.execute('DELETE FROM auth_rate_limits')
    with client() as lifecycle:
        yield SimpleNamespace(lifecycle=lifecycle,sink=tmp_path/'mail',tmp=tmp_path)


@pytest.fixture
def team(auth):
    members=[]
    for tag in ('admin','alice','bob'):
        c=client();email=tag+'-'+uid()+'@example.com';password=secrets.token_urlsafe(24)
        signup(c,email,password,auth.sink)
        if tag=='admin':
            with operator() as con:con.execute("UPDATE accounts SET role='SuperAdmin' WHERE normalized_email=%s",(email,))
        me=login(c,email,password)
        members.append(SimpleNamespace(client=c,email=email,password=password,me=me))
    return SimpleNamespace(admin=members[0],alice=members[1],bob=members[2],auth=auth)


def lecture(member):
    c=member.client
    r=c.post('/api/courses',json={'name':'Private Course'});assert r.status_code==201,r.text
    course=r.json()
    r=c.post('/api/courses/'+course['id']+'/lectures',json={'title':'Private lecture'});assert r.status_code==201,r.text
    row=r.json();doc=LectureDocument(title='Private lecture',sections=[Section(title='Math',blocks=[Block(kind='equation',latex=r'\frac{1}{2}+x=3')])])
    r=c.put('/api/lectures/'+row['id'],json={'document':doc.model_dump(),'revision':0});assert r.status_code==200,r.text
    return course,r.json()


def test_registration_verification_login_logout(auth):
    c=client();email='new-'+uid()+'@example.com';password=secrets.token_urlsafe(24)
    signup(c,email,password,auth.sink,verify=False)
    assert c.post('/api/auth/login',json={'email':email,'password':password}).status_code==401
    assert c.get('/api/courses').status_code==401
    token=link(auth.sink,email,'verify')
    assert c.post('/api/auth/verify',json={'token':token}).status_code==200
    assert c.post('/api/auth/verify',json={'token':token}).status_code==400
    me=login(c,email,password)
    assert me['role']=='Member' and me['workspace_id']
    assert c.post('/api/auth/logout').status_code==200
    assert c.get('/api/courses').status_code==401
    with operator() as con:
        hashed=con.execute('SELECT c.password_hash FROM credentials c JOIN accounts a ON a.id=c.user_id WHERE normalized_email=%s',(email,)).fetchone()['password_hash']
    assert hashed.startswith('$argon2id$') and password not in hashed


@pytest.mark.parametrize('changes',[{'email':'not-an-email'},{'password':'weak','confirm_password':'weak'},{'confirm_password':'different'},{'role':'SuperAdmin'},{'workspace_id':'foreign'},{'full_name':''}])
def test_registration_validation_and_role_injection(auth,changes):
    password=secrets.token_urlsafe(24)
    payload={'full_name':'Test member','email':'valid-'+uid()+'@example.com','password':password,'confirm_password':password,**changes}
    r=client().post('/api/auth/register',json=payload)
    assert r.status_code==422
    assert password not in r.text
    if len(payload.get('confirm_password',''))>10:assert payload['confirm_password'] not in r.text


def test_duplicate_normalized_email_generic(auth):
    c=client();email='duplicate-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink,verify=False)
    r=c.post('/api/auth/register',json={'full_name':'Different','email':email.upper(),'password':pwd,'confirm_password':pwd})
    assert r.status_code==202
    with operator() as con:assert con.execute('SELECT count(*) AS n FROM accounts WHERE normalized_email=%s',(email,)).fetchone()['n']==1


def test_verification_expiry_and_resend(auth):
    c=client();email='expire-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink,verify=False);old=link(auth.sink,email,'verify')
    with operator() as con:con.execute("UPDATE auth_tokens SET expires_at=now()-interval '1 second' WHERE token_hash=%s",(a.token_hash(old),))
    assert c.post('/api/auth/verify',json={'token':old}).status_code==400
    assert c.post('/api/auth/resend',json={'email':email}).status_code==202
    fresh=link(auth.sink,email,'verify');assert fresh!=old
    assert c.post('/api/auth/verify',json={'token':fresh}).status_code==200


def test_password_reset_generic_single_use_and_session_revocation(auth):
    c=client();email='reset-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink);login(c,email,pwd)
    public=client()
    yes=public.post('/api/auth/forgot',json={'email':email});no=public.post('/api/auth/forgot',json={'email':'absent-'+uid()+'@example.com'})
    assert yes.status_code==no.status_code==202 and yes.json()==no.json()
    token=link(auth.sink,email,'reset');new=secrets.token_urlsafe(24)
    assert public.post('/api/auth/reset',json={'token':token,'password':new,'confirm_password':new}).status_code==200
    assert c.get('/api/auth/me').status_code==401
    assert public.post('/api/auth/reset',json={'token':token,'password':new,'confirm_password':new}).status_code==400
    assert public.post('/api/auth/login',json={'email':email,'password':pwd}).status_code==401
    login(public,email,new)


def test_expired_reset_and_provider_failure(auth,monkeypatch):
    c=client();email='mail-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink)
    c.post('/api/auth/forgot',json={'email':email});token=link(auth.sink,email,'reset')
    with operator() as con:con.execute("UPDATE auth_tokens SET expires_at=now()-interval '1 second' WHERE token_hash=%s",(a.token_hash(token),))
    assert c.post('/api/auth/reset',json={'token':token,'password':pwd,'confirm_password':pwd}).status_code==400
    def fail(*args,**kwargs):raise RuntimeError('simulated provider unavailable')
    monkeypatch.setattr(a.mailer,'send',fail)
    assert c.post('/api/auth/forgot',json={'email':email}).status_code==202
    with operator() as con:
        assert con.execute("SELECT 1 FROM security_audit WHERE action='mail.delivery' AND outcome='failed' LIMIT 1").fetchone()


def test_session_expiry_csrf_origin_and_cookie(auth):
    c=client();email='session-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink);me=login(c,email,pwd)
    assert c.post('/api/courses',json={'name':'blocked'},headers={'X-CSRF-Token':''}).status_code==403
    assert c.post('/api/courses',json={'name':'blocked'},headers={'Origin':'https://evil.example'}).status_code==403
    with operator() as con:con.execute("UPDATE sessions SET expires_at=now()-interval '1 second' WHERE user_id=%s",(me['id'],))
    assert c.get('/api/courses').status_code==401
    r=c.post('/api/auth/login',json={'email':email,'password':pwd})
    cookie=r.headers['set-cookie'].lower();assert 'httponly' in cookie and 'samesite=lax' in cookie and 'path=/' in cookie


def test_password_change_and_active_session_revocation(team):
    member=team.alice;c=member.client;other=client();login(other,member.email,member.password)
    sessions=c.get('/api/auth/sessions').json();sid=next(s['id'] for s in sessions if not s['current'])
    assert c.delete('/api/auth/sessions/'+sid).status_code==200
    assert other.get('/api/auth/me').status_code==401
    new=secrets.token_urlsafe(24)
    assert c.post('/api/auth/password',json={'current_password':member.password,'password':new,'confirm_password':new}).status_code==200
    assert c.get('/api/auth/me').status_code==401


def test_profile_description_directory_and_secret_projection(team):
    c=team.alice.client;p=c.get('/api/account/profile').json()
    text='Super Admin <script>window.bad=true</script> — أنا أكتب المحاضرات'
    r=c.put('/api/account/profile',json={'full_name':'Alice','team_description':text,'version':p['version']});assert r.status_code==200
    assert c.get('/api/auth/me').json()['role']=='Member'
    rows=team.bob.client.get('/api/members').json();row=next(r for r in rows if r['id']==team.alice.me['id'])
    assert row['team_description']==text and 'email' not in row and 'workspace_id' not in row
    assert c.put('/api/account/profile',json={'full_name':'Alice','team_description':'stale','version':p['version']}).status_code==409
    admin=team.admin.client.get('/api/admin/members').text
    assert all(word not in admin for word in ('password_hash','token_hash','csrf','password_reset'))
    assert c.put('/api/account/profile',json={'full_name':'Alice','team_description':text,'version':r.json()['version'],'role':'SuperAdmin'}).status_code==422


def test_member_cannot_admin_or_forge_scope(team):
    _,row=lecture(team.bob)
    alice=team.alice.client
    for path in ['/api/admin/members','/api/admin/audit','/api/admin/permissions','/api/admin/workspaces']:
        assert alice.get(path).status_code==403
    assert alice.put('/api/admin/members/'+team.alice.me['id'],json={'role':'SuperAdmin'}).status_code==403
    assert alice.get('/api/lectures/'+row['id']).status_code==404
    assert alice.get('/api/lectures/'+row['id'],headers={'X-Ctrltea-Workspace':team.bob.me['workspace_id']}).status_code==404


@pytest.mark.parametrize('route',[
 '/api/lectures/{lid}','/api/lectures/{lid}/revisions','/api/lectures/{lid}/sources','/api/lectures/{lid}/jobs','/api/lectures/{lid}/exports','/api/lectures/{lid}/bundle','/api/lectures/{lid}/authoring/runs'
])
def test_cross_user_route_matrix(team,route):
    _,row=lecture(team.bob);path=route.format(lid=row['id']);wid=team.bob.me['workspace_id']
    assert team.alice.client.get(path,headers={'X-Ctrltea-Workspace':wid}).status_code==404
    assert team.bob.client.get('/api/courses',headers={'X-Ctrltea-Workspace':team.alice.me['workspace_id']}).status_code==404
    assert team.admin.client.get(path,headers={'X-Ctrltea-Workspace':wid}).status_code==200


def test_superadmin_edit_export_files_sources_and_audit(team):
    _,row=lecture(team.bob);admin=team.admin.client;wid=team.bob.me['workspace_id'];headers={'X-Ctrltea-Workspace':wid}
    doc=row['document'];doc['title']='Admin edited own-identity'
    assert admin.put('/api/lectures/'+row['id'],json={'document':doc,'revision':1},headers=headers).status_code==200
    uploaded=team.bob.client.post('/api/lectures/'+row['id']+'/sources',files={'file':('source.txt',b'Private source bytes','text/plain')})
    assert uploaded.status_code==200,uploaded.text
    sid=uploaded.json()['source']['id']
    assert team.alice.client.get('/api/sources/'+sid+'/file',params={'workspace':wid}).status_code==404
    assert admin.get('/api/sources/'+sid+'/file',params={'workspace':wid}).content==b'Private source bytes'
    queued=admin.post('/api/lectures/'+row['id']+'/exports',json={'draft':True},headers=headers);assert queued.status_code==200,queued.text
    jid=queued.json()['id']
    for _ in range(300):
        rows=admin.get('/api/lectures/'+row['id']+'/jobs',headers=headers).json();job=next(j for j in rows if j['id']==jid)
        if job['status'] in ('done','failed'):break
        time.sleep(.1)
    assert job['status']=='done',job.get('error')
    eid=json.loads(job['result'])['export_id']
    assert admin.get('/api/exports/'+eid+'/pdf',params={'workspace':wid}).content.startswith(b'%PDF')
    assert admin.get('/api/exports/'+eid+'/docx',params={'workspace':wid}).content[:2]==b'PK'
    assert team.alice.client.get('/api/exports/'+eid+'/pdf',params={'workspace':wid}).status_code==404
    records=admin.get('/api/admin/audit').json()
    assert any(r['action']=='resource.access' and r['actor_id']==team.admin.me['id'] and r['workspace_id']==wid for r in records)


def test_permission_revocation_and_reviewer_privacy(team):
    admin=team.admin.client;alice=team.alice
    r=admin.put('/api/admin/members/'+alice.me['id']+'/permissions',json={'changes':{'courses.create':False}});assert r.status_code==200,r.text
    assert alice.client.get('/api/courses').status_code==401
    login(alice.client,alice.email,alice.password)
    assert alice.client.post('/api/courses',json={'name':'blocked'}).status_code==403
    assert admin.put('/api/admin/members/'+alice.me['id'],json={'role':'Reviewer'}).status_code==200
    login(alice.client,alice.email,alice.password)
    assert alice.client.get('/api/courses',headers={'X-Ctrltea-Workspace':team.bob.me['workspace_id']}).status_code==404


def test_resource_grant_and_revocation(team):
    _,row=lecture(team.bob);wid=team.bob.me['workspace_id'];admin=team.admin.client;alice=team.alice
    r=admin.post('/api/admin/grants',json={'user_id':alice.me['id'],'workspace_id':wid,'resource_kind':'lecture','resource_id':row['id'],'permissions':['lectures.view','revisions.view']})
    assert r.status_code==200,r.text;gid=r.json()['id']
    login(alice.client,alice.email,alice.password)
    assert alice.client.get('/api/lectures/'+row['id'],headers={'X-Ctrltea-Workspace':wid}).status_code==200
    assert alice.client.get('/api/courses',headers={'X-Ctrltea-Workspace':wid}).status_code==404
    assert alice.client.put('/api/lectures/'+row['id'],json={'document':row['document'],'revision':1},headers={'X-Ctrltea-Workspace':wid}).status_code==404
    assert admin.delete('/api/admin/grants/'+gid).status_code==200
    login(alice.client,alice.email,alice.password)
    assert alice.client.get('/api/lectures/'+row['id'],headers={'X-Ctrltea-Workspace':wid}).status_code==404


def test_suspension_reactivation_and_last_admin(team):
    admin=team.admin.client;alice=team.alice
    assert admin.put('/api/admin/members/'+alice.me['id'],json={'state':'disabled'}).status_code==200
    assert alice.client.get('/api/courses').status_code==401
    assert alice.client.post('/api/auth/login',json={'email':alice.email,'password':alice.password}).status_code==401
    assert admin.put('/api/admin/members/'+alice.me['id'],json={'state':'active'}).status_code==200
    login(alice.client,alice.email,alice.password)
    # Other test administrators exist in this disposable DB; isolate the count.
    with operator() as con:
        con.execute("UPDATE accounts SET role='Member' WHERE role='SuperAdmin' AND id<>%s",(team.admin.me['id'],))
    assert admin.put('/api/admin/members/'+team.admin.me['id'],json={'state':'disabled'}).status_code==409
    assert admin.put('/api/admin/members/'+team.admin.me['id'],json={'role':'Member'}).status_code==409


def test_initial_bootstrap_bound_single_use_and_recovery(auth):
    from ctrltea.bootstrap import invite
    c=client();email='owner-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink);me=login(c,email,pwd)
    assert me['role']=='Member'
    with operator() as con:con.execute('UPDATE bootstrap_state SET completed=false WHERE id=1')
    invite(email);token=link(auth.sink,email,'bootstrap')
    other=client();email2='other-'+uid()+'@example.com';signup(other,email2,pwd,auth.sink);login(other,email2,pwd)
    assert other.post('/api/auth/bootstrap/accept',json={'token':token}).status_code==400
    assert c.post('/api/auth/bootstrap/accept',json={'token':token}).status_code==200
    assert c.get('/api/auth/me').status_code==401
    assert login(c,email,pwd)['role']=='SuperAdmin'
    assert c.post('/api/auth/bootstrap/accept',json={'token':token}).status_code==400
    with pytest.raises(ValueError,match='closed'):invite(email)
    invite(email,recovery=True,reason='Disposable operator recovery test')
    recovery=link(auth.sink,email,'admin_recovery')
    assert c.post('/api/auth/bootstrap/accept',json={'token':recovery}).status_code==200


def test_bootstrap_expiry_and_unverified_operator_invitation(auth):
    from ctrltea.bootstrap import invite
    c=client();email='owner-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
    signup(c,email,pwd,auth.sink,verify=False)
    with pytest.raises(ValueError,match='Verify'):invite(email)
    c.post('/api/auth/verify',json={'token':link(auth.sink,email,'verify')});login(c,email,pwd)
    with operator() as con:con.execute('UPDATE bootstrap_state SET completed=false WHERE id=1')
    invite(email);token=link(auth.sink,email,'bootstrap')
    with operator() as con:con.execute("UPDATE auth_tokens SET expires_at=now()-interval '1 second' WHERE token_hash=%s",(a.token_hash(token),))
    assert c.post('/api/auth/bootstrap/accept',json={'token':token}).status_code==400


def test_recoverable_delete_restores_original_identifiers(team):
    course,row=lecture(team.bob);admin=team.admin.client;wid=team.bob.me['workspace_id'];headers={'X-Ctrltea-Workspace':wid}
    assert admin.delete('/api/courses/'+course['id'],headers=headers).status_code==200
    assert team.bob.client.get('/api/lectures/'+row['id']).status_code==404
    trash=admin.get('/api/trash',headers=headers).json();record=next(t for t in trash if t['resource_id']==course['id'])
    result=admin.post('/api/trash/'+record['id']+'/restore',json={},headers=headers);assert result.status_code==200,result.text
    restored=team.bob.client.get('/api/lectures/'+row['id']).json();assert restored['document']==row['document']


def test_rate_limits_audit_immutability_and_token_hashes(auth):
    email='limited-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24);c=client()
    signup(c,email,pwd,auth.sink)
    statuses=[c.post('/api/auth/login',json={'email':email,'password':'incorrect'}).status_code for _ in range(6)]
    assert statuses[:5]==[401]*5 and statuses[5]==429
    with a.db() as con:
        import psycopg
        with pytest.raises(psycopg.errors.InsufficientPrivilege):con.execute('DELETE FROM security_audit')
    raw=link(auth.sink,email,'verify')
    with operator() as con:
        token=con.execute('SELECT token_hash FROM auth_tokens WHERE token_hash=%s',(a.token_hash(raw),)).fetchone()['token_hash']
        audit=' '.join(str(r) for r in con.execute("SELECT action,target,metadata FROM security_audit WHERE created_at>now()-interval '5 minutes'"))
    assert raw!=token and raw not in audit and pwd not in audit
