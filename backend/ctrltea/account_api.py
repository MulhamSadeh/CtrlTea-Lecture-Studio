from pathlib import Path
import hashlib,hmac,io,json,os,secrets
from datetime import timedelta
from fastapi import APIRouter,Request,Response,HTTPException,UploadFile,File
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,SecretStr,Field
from . import accounts as a,store,persistence
from .models import uid
router=APIRouter()


class Input(BaseModel):model_config=ConfigDict(extra='forbid')
class Email(Input):email:str=Field(max_length=320)
class Login(Email):password:SecretStr=Field(max_length=128)
class Register(Login):full_name:str=Field(max_length=200);confirm_password:SecretStr=Field(max_length=128)
class Token(Input):token:SecretStr=Field(max_length=256)
class Reset(Token):password:SecretStr=Field(max_length=128);confirm_password:SecretStr=Field(max_length=128)
class Profile(Input):full_name:str;team_description:str;version:int
class Password(Input):current_password:SecretStr=Field(max_length=128);password:SecretStr=Field(max_length=128);confirm_password:SecretStr=Field(max_length=128)
class MemberChange(Input):role:str|None=None;state:str|None=None
class PermissionChanges(Input):changes:dict[str,bool|None]
class Grant(Input):user_id:str;workspace_id:str;resource_kind:str;resource_id:str;permissions:list[str]
class Claim(Input):workspace_id:str;user_id:str


def user(request):return request.state.principal
def rate(request,kind,email=None,maximum=10,seconds=900):
    a.limit(kind+'.ip',request.client.host if request.client else 'unknown',maximum*3,seconds)
    if email:a.limit(kind+'.email',a.normalize(email),maximum,seconds)
def generic():return {'message':'إذا كانت البيانات مؤهلة، ستصلك رسالة تتضمن الخطوة التالية.'}


@router.get('/api/auth/status')
def auth_status():return {'enabled':a.enabled()}


@router.post('/api/auth/register',status_code=202)
def register_account(data:Register,request:Request):
    rate(request,'register',data.email,5,3600)
    a.register(data.full_name,data.email,data.password.get_secret_value(),data.confirm_password.get_secret_value())
    return generic()


@router.post('/api/auth/verify')
def verify_account(data:Token,request:Request):
    rate(request,'verify',maximum=30)
    a.verify(data.token.get_secret_value());return {'message':'تم تفعيل البريد؛ يمكنك تسجيل الدخول الآن.'}


@router.post('/api/auth/resend',status_code=202)
def resend_verification(data:Email,request:Request):
    rate(request,'resend',data.email,3,3600);a.request_link(data.email,'verify');return generic()


@router.post('/api/auth/forgot',status_code=202)
def forgot_password(data:Email,request:Request):
    rate(request,'forgot',data.email,3,3600);a.request_link(data.email,'reset');return generic()


@router.post('/api/auth/reset')
def reset_account_password(data:Reset,request:Request):
    rate(request,'reset',maximum=20)
    a.reset_password(data.token.get_secret_value(),data.password.get_secret_value(),data.confirm_password.get_secret_value())
    return {'message':'تم تغيير كلمة المرور وإبطال الجلسات السابقة؛ سجّل الدخول مجددًا.'}


def set_session(response,raw):
    response.set_cookie(a.cookie_name(),raw,max_age=7*24*3600,secure=a.secure_cookie(),httponly=True,samesite='lax',path='/')


@router.post('/api/auth/login')
def login_account(data:Login,request:Request,response:Response):
    rate(request,'login',data.email,5)
    raw=a.login(data.email,data.password.get_secret_value(),request.headers.get('user-agent',''),request.cookies.get(a.cookie_name()))
    set_session(response,raw)
    return {'message':'تم تسجيل الدخول','csrf':a.csrf(raw)}


@router.get('/api/auth/me')
def me(request:Request):
    account=user(request)
    return {**a.safe_user(account),'csrf':a.csrf(request.cookies[a.cookie_name()]),'permissions':sorted(account['permissions'])}


@router.post('/api/auth/logout')
def logout_account(request:Request,response:Response):
    with a.db() as con:con.execute('DELETE FROM sessions WHERE id=%s',(user(request)['session_id'],))
    response.delete_cookie(a.cookie_name(),path='/',secure=a.secure_cookie(),httponly=True,samesite='lax')
    return {'message':'تم تسجيل الخروج'}


@router.post('/api/auth/reauth')
def reauthenticate(data:Login,request:Request,response:Response):
    account=user(request)
    if a.normalize(data.email)!=account['email']:raise HTTPException(403,'أكد الحساب الحالي')
    rate(request,'reauth',data.email,5)
    raw=a.login(account['email'],data.password.get_secret_value(),request.headers.get('user-agent',''),request.cookies[a.cookie_name()])
    set_session(response,raw);return {'csrf':a.csrf(raw),'message':'تم تأكيد الجلسة'}


@router.post('/api/auth/password')
def change_password(data:Password,request:Request,response:Response):
    account=user(request);rate(request,'password',account['email'],5)
    a.password_check(data.password.get_secret_value(),data.confirm_password.get_secret_value())
    from argon2.exceptions import VerificationError
    with a.db() as con:
        con.execute('SELECT id FROM accounts WHERE id=%s FOR UPDATE',(account['id'],))
        hashed=con.execute('SELECT password_hash FROM credentials WHERE user_id=%s',(account['id'],)).fetchone()['password_hash']
        try:a.hasher.verify(hashed,data.current_password.get_secret_value())
        except VerificationError:raise HTTPException(403,'كلمة المرور الحالية غير صحيحة')
        con.execute('UPDATE credentials SET password_hash=%s WHERE user_id=%s',(a.hasher.hash(data.password.get_secret_value()),account['id']))
        a.invalidate(con,account['id'])
        con.execute('UPDATE auth_tokens SET consumed_at=now() WHERE user_id=%s AND consumed_at IS NULL',(account['id'],))
    a.audit('password.changed',account['id'])
    try:a.mailer.send(account['email'],'تغيير كلمة المرور','تم تغيير كلمة المرور؛ أُبطلت جلسات الحساب السابقة.')
    except Exception:a.audit('mail.notification',account['id'],'failed')
    response.delete_cookie(a.cookie_name(),path='/');return {'message':'تم التغيير؛ سجّل الدخول مجددًا.'}


@router.get('/api/auth/sessions')
def my_sessions(request:Request):
    with a.db() as con:
        rows=con.execute('SELECT id,created_at,last_seen,expires_at,device FROM sessions WHERE user_id=%s AND expires_at>now() ORDER BY created_at DESC',(user(request)['id'],)).fetchall()
    return [{**row,'current':row['id']==user(request)['session_id']} for row in rows]


@router.delete('/api/auth/sessions/{sid}')
def revoke_session(sid:str,request:Request):
    with a.db() as con:con.execute('DELETE FROM sessions WHERE id=%s AND user_id=%s',(sid,user(request)['id']))
    return {'ok':True}


@router.get('/api/account/profile')
def my_profile(request:Request):
    with a.db() as con:
        profile=con.execute('SELECT team_description,version,avatar_path IS NOT NULL AS has_avatar FROM profiles WHERE user_id=%s',(user(request)['id'],)).fetchone()
    return {**a.safe_user(user(request)),**profile}


@router.put('/api/account/profile')
def update_profile(data:Profile,request:Request):
    if not 2<=len(data.full_name.strip())<=200 or len(data.team_description)>3000:raise HTTPException(422,'راجع طول الاسم ووصف العمل (حتى 3000 محرف)')
    with a.db() as con:
        row=con.execute('UPDATE profiles SET team_description=%s,version=version+1 WHERE user_id=%s AND version=%s RETURNING version',(data.team_description,user(request)['id'],data.version)).fetchone()
        if not row:raise HTTPException(409,'تغيّر البروفايل؛ أعد تحميل أحدث نسخة')
        con.execute('UPDATE accounts SET full_name=%s WHERE id=%s',(data.full_name.strip(),user(request)['id']))
    return {'version':row['version'],'message':'حُفظ البروفايل؛ لم تتغير صلاحيات الحساب.'}


@router.post('/api/account/avatar')
async def upload_avatar(request:Request,file:UploadFile=File(...)):
    from PIL import Image,UnidentifiedImageError
    content=await file.read(2*1024*1024+1)
    if len(content)>2*1024*1024:raise HTTPException(422,'الصورة أكبر من 2MB')
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width*image.height>16_000_000 or image.format not in ('PNG','JPEG','WEBP'):raise ValueError()
            picture=image.convert('RGB');picture.thumbnail((512,512))
            root=Path(os.environ['CTRLTEA_PROFILE_DIR']).resolve();root.mkdir(parents=True,exist_ok=True,mode=0o700)
            name=uid()+'.png';path=root/name;picture.save(path,format='PNG');path.chmod(0o600)
    except (UnidentifiedImageError,Image.DecompressionBombError,ValueError,OSError):raise HTTPException(422,'استخدم صورة PNG أوJPEG أوWebP صالحة')
    with a.db() as con:con.execute('UPDATE profiles SET avatar_path=%s,version=version+1 WHERE user_id=%s',(name,user(request)['id']))
    return {'message':'حُفظت الصورة'}


@router.get('/api/members')
def members(request:Request,q:str=''):
    with a.db() as con:
        return con.execute("SELECT a.id,a.full_name,a.role,p.team_description,p.avatar_path IS NOT NULL AS has_avatar FROM accounts a JOIN profiles p ON p.user_id=a.id WHERE a.state='active' AND a.email_verified_at IS NOT NULL AND a.full_name ILIKE %s ORDER BY a.full_name LIMIT 200",('%'+q[:100]+'%',)).fetchall()


@router.get('/api/members/{mid}/avatar')
def member_avatar(mid:str,request:Request):
    with a.db() as con:
        row=con.execute("SELECT p.avatar_path FROM profiles p JOIN accounts a ON a.id=p.user_id WHERE p.user_id=%s AND (a.state='active' OR a.id=%s OR %s)",(mid,user(request)['id'],user(request)['role']=='SuperAdmin')).fetchone()
    if not row or not row['avatar_path']:raise HTTPException(404,'الصورة غير موجودة')
    name=row['avatar_path']
    if '/' in name or '\\' in name:raise HTTPException(404,'الصورة غير موجودة')
    return FileResponse(Path(os.environ['CTRLTEA_PROFILE_DIR'])/name,media_type='image/png')


@router.get('/api/account/grants')
def my_grants(request:Request):
    with a.db() as con:return con.execute('SELECT id,workspace_id,resource_kind,resource_id,permissions,expires_at FROM resource_grants WHERE user_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())',(user(request)['id'],)).fetchall()


@router.get('/api/admin/members')
def admin_members(request:Request,q:str='',offset:int=0):
    if offset<0 or offset>1_000_000:raise HTTPException(422,'موضع الصفحة غير صالح')
    with a.db() as con:
        return con.execute('SELECT a.id,a.full_name,a.email,a.role,a.state,a.email_verified_at,a.created_at,w.id AS workspace_id,p.team_description FROM accounts a LEFT JOIN workspaces w ON w.owner_user_id=a.id LEFT JOIN profiles p ON p.user_id=a.id WHERE a.full_name ILIKE %s OR a.email ILIKE %s ORDER BY a.created_at DESC,a.id DESC LIMIT 200 OFFSET %s',('%'+q[:100]+'%','%'+q[:100]+'%',offset)).fetchall()


@router.get('/api/admin/permissions')
def admin_catalog(request:Request):
    with a.db() as con:return con.execute('SELECT * FROM permission_catalog ORDER BY group_name,name').fetchall()


@router.get('/api/admin/members/{mid}/permissions')
def admin_permissions(mid:str,request:Request):
    with a.db() as con:
        row=con.execute('SELECT role FROM accounts WHERE id=%s',(mid,)).fetchone()
        if not row:raise HTTPException(404,'الحساب غير موجود')
        base=[r['permission'] for r in con.execute('SELECT permission FROM role_permissions WHERE role=%s',(row['role'],))]
        overrides={r['permission']:r['enabled'] for r in con.execute('SELECT permission,enabled FROM permission_overrides WHERE user_id=%s',(mid,))}
    return {'role':row['role'],'base':base,'overrides':overrides}


@router.put('/api/admin/members/{mid}')
def admin_member_update(mid:str,data:MemberChange,request:Request):
    a.change_member(user(request),mid,data.role,data.state);return {'message':'حُدّث الحساب وأُبطلت جلساته السابقة'}


@router.put('/api/admin/members/{mid}/permissions')
def admin_permission_update(mid:str,data:PermissionChanges,request:Request):
    a.step_up(user(request))
    if any(name not in a.PERMISSIONS for name in data.changes):raise HTTPException(422,'صلاحية غير معروفة')
    with a.db() as con:
        if not con.execute('SELECT id FROM accounts WHERE id=%s FOR UPDATE',(mid,)).fetchone():raise HTTPException(404,'الحساب غير موجود')
        for name,value in data.changes.items():
            if value is None:con.execute('DELETE FROM permission_overrides WHERE user_id=%s AND permission=%s',(mid,name))
            else:con.execute('INSERT INTO permission_overrides(user_id,permission,enabled,granted_by) VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,permission) DO UPDATE SET enabled=EXCLUDED.enabled,granted_by=EXCLUDED.granted_by,updated_at=now()',(mid,name,value,user(request)['id']))
        a.invalidate(con,mid)
        con.execute('INSERT INTO security_audit(actor_id,action,target,outcome,metadata) VALUES(%s,%s,%s,%s,%s)',(user(request)['id'],'permissions.changed',mid,'success',json.dumps(data.changes)))
    return {'message':'حُفظت الصلاحيات؛ يلزم تسجيل دخول جديد للعضو'}


@router.post('/api/admin/grants')
def admin_grant(data:Grant,request:Request):
    a.step_up(user(request))
    if data.resource_kind not in ('course','lecture') or not data.permissions or any(p not in a.PERMISSIONS for p in data.permissions):raise HTTPException(422,'منح غير صالح')
    with store.workspace(data.workspace_id):
        if data.resource_kind=='course':store.one('SELECT id FROM courses WHERE id=?',(data.resource_id,))
        else:store.lecture(data.resource_id)
    with a.db() as con:
        if not con.execute("SELECT id FROM accounts WHERE id=%s AND state='active'",(data.user_id,)).fetchone():raise HTTPException(404,'العضو غير موجود')
        grant=uid()
        con.execute('INSERT INTO resource_grants(id,user_id,workspace_id,resource_kind,resource_id,permissions,granted_by) VALUES(%s,%s,%s,%s,%s,%s,%s)',(grant,data.user_id,data.workspace_id,data.resource_kind,data.resource_id,data.permissions,user(request)['id']))
        a.invalidate(con,data.user_id)
    a.audit('grant.created',grant,workspace_id=data.workspace_id);return {'id':grant}


@router.delete('/api/admin/grants/{gid}')
def admin_revoke_grant(gid:str,request:Request):
    a.step_up(user(request))
    with a.db() as con:
        row=con.execute('UPDATE resource_grants SET revoked_at=now() WHERE id=%s RETURNING user_id',(gid,)).fetchone()
        if row:a.invalidate(con,row['user_id'])
    a.audit('grant.revoked',gid);return {'ok':True}


@router.get('/api/admin/grants')
def admin_grants(request:Request):
    with a.db() as con:return con.execute('SELECT id,user_id,workspace_id,resource_kind,resource_id,permissions,created_at,revoked_at FROM resource_grants ORDER BY created_at DESC LIMIT 200').fetchall()


@router.get('/api/admin/workspaces')
def admin_workspaces(request:Request):
    with a.db() as con:return con.execute('SELECT w.id,w.owner_user_id,w.state,a.full_name,a.email FROM workspaces w LEFT JOIN accounts a ON a.id=w.owner_user_id ORDER BY w.created DESC').fetchall()


@router.get('/api/admin/audit')
def admin_audit(request:Request,before:int|None=None):
    with a.db() as con:return con.execute('SELECT id,actor_id,action,target,workspace_id,outcome,created_at,metadata FROM security_audit WHERE (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT 200',(before,before)).fetchall()


@router.post('/api/admin/legacy/assign')
def admin_assign_legacy(data:Claim,request:Request):
    a.step_up(user(request))
    with a.db() as con:
        con.execute('SELECT pg_advisory_xact_lock(814032605)')
        target=con.execute("SELECT id FROM accounts WHERE id=%s AND state='active' AND email_verified_at IS NOT NULL FOR UPDATE",(data.user_id,)).fetchone()
        ws=con.execute('SELECT state,owner_user_id FROM workspaces WHERE id=%s FOR UPDATE',(data.workspace_id,)).fetchone()
        if not target or not ws or ws['state']!='unclaimed' or ws['owner_user_id'] is not None:raise HTTPException(409,'المطالبة غير صالحة أو أُنجزت مسبقًا')
        previous=con.execute('SELECT id FROM workspaces WHERE owner_user_id=%s FOR UPDATE',(data.user_id,)).fetchone()
        if previous:
            with store.workspace(previous['id']):
                if any(store.all_rows('SELECT id FROM '+t+' LIMIT 1') for t in ('courses','lectures','sources','jobs','author_runs','private_assets','trash_records')):raise HTTPException(409,'مساحة العضو غير فارغة؛ يلزم استيراد مستقل لاحقًا')
                if any(p.is_file() for p in store.DATA.rglob('*')):raise HTTPException(409,'مساحة العضو تحتوي ملفات؛ لا تُستبدل تلقائيًا')
            con.execute('DELETE FROM workspaces WHERE id=%s',(previous['id'],))
        con.execute("UPDATE workspaces SET owner_user_id=%s,state='private' WHERE id=%s",(data.user_id,data.workspace_id))
        a.invalidate(con,data.user_id)
        con.execute('INSERT INTO security_audit(actor_id,action,target,workspace_id,outcome) VALUES(%s,%s,%s,%s,%s)',(user(request)['id'],'legacy.assigned',data.user_id,data.workspace_id,'success'))
    return {'message':'أُسندت المساحة مع الحفاظ على معرّفاتها وسجلها'}


@router.post('/api/auth/bootstrap/accept')
def accept_bootstrap(data:Token,request:Request):
    account=user(request)
    with a.db() as con:
        con.execute('SELECT pg_advisory_xact_lock(814032604)')
        token=con.execute('SELECT user_id,kind,expires_at,consumed_at FROM auth_tokens WHERE token_hash=%s FOR UPDATE',(a.token_hash(data.token.get_secret_value()),)).fetchone()
        if not token or token['user_id']!=account['id'] or token['kind'] not in ('bootstrap','admin_recovery') or token['consumed_at'] or token['expires_at']<=a.now():raise HTTPException(400,'دعوة الإدارة غير صالحة')
        state=con.execute('SELECT completed FROM bootstrap_state WHERE id=1 FOR UPDATE').fetchone()
        if token['kind']=='bootstrap' and state['completed']:raise HTTPException(409,'أُغلقت تهيئة الإدارة الأولية')
        if account['reauthenticated_at']<a.now()-timedelta(minutes=15):raise HTTPException(403,'أعد تسجيل الدخول قبل تفعيل الدعوة')
        con.execute("UPDATE accounts SET role='SuperAdmin' WHERE id=%s",(account['id'],))
        con.execute('UPDATE auth_tokens SET consumed_at=now() WHERE token_hash=%s',(a.token_hash(data.token.get_secret_value()),))
        con.execute('UPDATE bootstrap_state SET completed=true WHERE id=1')
        a.invalidate(con,account['id'])
        con.execute('INSERT INTO security_audit(actor_id,action,target,outcome) VALUES(%s,%s,%s,%s)',(account['id'],'admin.bootstrap',account['id'],'success'))
    return {'message':'فُعّلت الإدارة؛ سجّل الدخول مجددًا لتحديث الجلسة'}
