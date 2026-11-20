"""Account/session services. Authentication secrets never leave this module."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timedelta,timezone
import hashlib,hmac,json,os,secrets,time
from urllib.parse import urlsplit
import psycopg
from psycopg.rows import dict_row
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError,InvalidHashError
from email_validator import validate_email,EmailNotValidError
from fastapi import HTTPException
from .models import uid
from . import mailer,persistence

actor=ContextVar('ctrltea_actor',default=None)
admin_scope=persistence._privileged_scope
hasher=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2)
_dummy_hash=hasher.hash(secrets.token_urlsafe(24))

PERMISSIONS={
 'courses.view':('المواد','عرض المواد'), 'courses.create':('المواد','إنشاء مادة'),
 'courses.edit':('المواد','تعديل مادة'),'courses.delete':('المواد','حذف مادة'),
 'lectures.view':('المحاضرات','عرض المحاضرات'),'lectures.create':('المحاضرات','إنشاء محاضرة'),
 'lectures.edit':('المحاضرات','تعديل محاضرة'),'lectures.delete':('المحاضرات','حذف محاضرة'),
 'lectures.import':('المحاضرات','استيراد محتوى'),'lectures.export':('المحاضرات','تصدير Word وPDF'),
 'sources.view':('المصادر','عرض المصادر'),'sources.upload':('المصادر','رفع مصادر'),
 'sources.edit':('المصادر','تصحيح المصادر'),'sources.delete':('المصادر','حذف مصدر'),
 'sources.extract':('المصادر','استخراج النص وOCR'),'files.download':('الملفات','تنزيل الملفات'),
 'revisions.view':('السجل','عرض النسخ'),'revisions.restore':('السجل','استعادة نسخة'),
 'authoring.create':('التأليف','إنشاء حزمة تأليف'),'authoring.import':('التأليف','استيراد نتيجة التأليف'),
 'jobs.view':('المهام','عرض المهام'),'jobs.retry':('المهام','إعادة مهمة'),
 'theme.edit':('التنسيق','تغيير الثيم'),'figures.preview':('التنسيق','معاينة الرسوم'),
 'math.check':('التنسيق','فحص المعادلات'),'transfers.export':('النقل','استخراج حزم البيانات'),
 'transfers.import':('النقل','استيراد حزم البيانات'),'resources.restore':('السجل','استعادة المحذوفات'),
 'review.submit':('المراجعة — لاحقًا','إرسال للمراجعة'),'review.inspect':('المراجعة — لاحقًا','مراجعة مورد مكلّف'),
 'review.approve':('المراجعة — لاحقًا','اعتماد مراجعة'),'review.assign':('المراجعة — لاحقًا','إدارة تكليفات المراجعة'),
 'publish':('النشر — لاحقًا','نشر محاضرة معتمدة'),'sharing.manage':('المشاركة — لاحقًا','إدارة المشاركة')
}
FUTURE={'review.submit','review.inspect','review.approve','review.assign','publish','sharing.manage'}


def enabled():
    mode=os.environ.get('CTRLTEA_AUTH_MODE','required')
    if mode not in ('required','local'):raise RuntimeError('Invalid authentication mode')
    return mode=='required'


def origin():return os.environ.get('CTRLTEA_PUBLIC_ORIGIN','http://localhost:8765').rstrip('/')


def secure_cookie():return os.environ.get('CTRLTEA_COOKIE_SECURE','1')=='1'


def cookie_name():return '__Host-ct_session' if secure_cookie() else 'ct_session_dev'


def check_config():
    if persistence.backend()!='postgres':raise RuntimeError('Authenticated mode requires PostgreSQL')
    for key in ('CTRLTEA_AUTH_DATABASE_URL','CTRLTEA_DATABASE_URL','CTRLTEA_AUTH_SECRET','CTRLTEA_PROFILE_DIR','CTRLTEA_DATA_DIR'):
        if not os.environ.get(key):raise RuntimeError(key+' required')
    if len(os.environ['CTRLTEA_AUTH_SECRET'])<32:raise RuntimeError('Generate a random authentication secret >=32 characters')
    parsed=urlsplit(origin())
    if parsed.query or parsed.fragment or parsed.path not in ('','/') or not parsed.netloc or parsed.username or parsed.password or parsed.scheme not in ('http','https'):
        raise RuntimeError('Configure a canonical origin without path/query')
    if not secure_cookie() and parsed.hostname not in ('localhost','127.0.0.1','[::1]','::1'):
        raise RuntimeError('Insecure cookies are allowed only for explicit loopback development')
    if secure_cookie() and parsed.scheme!='https':raise RuntimeError('Secure-cookie mode requires an HTTPS public origin')
    if os.environ.get('CTRLTEA_MAIL_PROVIDER','local')=='local' and not os.environ.get('CTRLTEA_MAIL_SINK'):
        raise RuntimeError('Private CTRLTEA_MAIL_SINK required for local mail testing')
    with db() as con:
        if con.execute('SELECT version_num FROM alembic_version').fetchone()['version_num']!='0002_accounts':
            raise RuntimeError('Run Task04 migrations before starting authenticated mode')


@contextmanager
def db():
    with psycopg.connect(os.environ['CTRLTEA_AUTH_DATABASE_URL'],row_factory=dict_row,connect_timeout=10) as con:
        role=con.execute('SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user').fetchone()
        owns=con.execute("SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='accounts' AND pg_has_role(current_user,tableowner,'MEMBER')").fetchone()
        if any(role.values()) or owns:raise RuntimeError('Authentication service must use a restricted non-owner role')
        con.execute("SELECT set_config('ctrltea.auth_service','1',true)")
        con.execute("SET LOCAL lock_timeout='5s'")
        yield con


def now():return datetime.now(timezone.utc)
def token_hash(value):return hashlib.sha256(value.encode()).hexdigest()


def normalize(email):
    try:return validate_email(email.strip(),check_deliverability=False).normalized.casefold()
    except EmailNotValidError:raise HTTPException(422,'عنوان البريد الإلكتروني غير صالح')


def password_check(password,confirm):
    if password!=confirm:raise HTTPException(422,'تأكيد كلمة المرور لا يطابقها')
    if len(password)<15 or len(password)>128 or len(set(password))<4 or password.casefold() in ('passwordpassword','passwordpasswordpassword','123456789012345','qwertyqwertyqwerty','letmeinletmeinletmein'):
        raise HTTPException(422,'استخدم عبارة مرور قوية بين 15 و128 محرفًا')


def audit(action,target='',outcome='success',actor_id=None,workspace_id=None,metadata=None):
    who=actor.get()
    with db() as con:
        con.execute('INSERT INTO security_audit(actor_id,action,target,workspace_id,outcome,metadata) VALUES(%s,%s,%s,%s,%s,%s)',
                    (actor_id or (who['id'] if who else None),action,str(target),workspace_id,outcome,json.dumps(metadata or {})))


def limit(kind,value,maximum,seconds):
    key=hmac.new(os.environ['CTRLTEA_AUTH_SECRET'].encode(),(kind+':'+value).encode(),hashlib.sha256).hexdigest()
    slot=int(time.time())//seconds
    with db() as con:
        row=con.execute('INSERT INTO auth_rate_limits(key_hash,slot,hits) VALUES(%s,%s,1) ON CONFLICT(key_hash,slot) DO UPDATE SET hits=auth_rate_limits.hits+1 RETURNING hits',(key,slot)).fetchone()
    if row['hits']>maximum:raise HTTPException(429,'محاولات كثيرة؛ حاول لاحقًا',headers={'Retry-After':str(seconds)})


def issue(con,user,kind,minutes):
    con.execute('UPDATE auth_tokens SET consumed_at=now() WHERE user_id=%s AND kind=%s AND consumed_at IS NULL',(user,kind))
    token=secrets.token_urlsafe(32)
    con.execute('INSERT INTO auth_tokens(token_hash,user_id,kind,expires_at) VALUES(%s,%s,%s,%s)',(token_hash(token),user,kind,now()+timedelta(minutes=minutes)))
    return token


def deliver(user,email,kind,token):
    subjects={'verify':'تفعيل حسابك','reset':'إعادة تعيين كلمة المرور','bootstrap':'دعوة المسؤول العام','admin_recovery':'استرداد الإدارة'}
    try:
        mailer.send(email,subjects[kind],subjects[kind]+' في Ctrl+Tea. الرابط مؤقت ويُستخدم مرة واحدة.',kind+'='+token)
        audit('mail.delivery',user,metadata={'kind':kind,'provider':os.environ.get('CTRLTEA_MAIL_PROVIDER','local')})
    except Exception:
        # Hash is retained for security; a resend creates a new token. SMTP
        # delivery is not called successful and credentials/body are never logged.
        audit('mail.delivery',user,'failed',metadata={'kind':kind})
        return False
    return True


def register(full_name,email,password,confirm):
    email=normalize(email);password_check(password,confirm)
    full_name=full_name.strip()
    if not 2<=len(full_name)<=200:raise HTTPException(422,'الاسم الكامل مطلوب، بين محرفين و200 محرف')
    hashed=hasher.hash(password)
    with db() as con:
        # Unique normalized email is the race backstop; public response is generic.
        user=con.execute("INSERT INTO accounts(id,full_name,email,normalized_email) VALUES(%s,%s,%s,%s) ON CONFLICT(normalized_email) DO NOTHING RETURNING id",(uid(),full_name,email,email)).fetchone()
        if not user:return
        con.execute('INSERT INTO credentials(user_id,password_hash) VALUES(%s,%s)',(user['id'],hashed))
        con.execute('INSERT INTO profiles(user_id) VALUES(%s)',(user['id'],))
        token=issue(con,user['id'],'verify',60)
    audit('account.created',user['id'])
    deliver(user['id'],email,'verify',token)


def request_link(email,kind):
    email=normalize(email)
    with db() as con:
        user=con.execute('SELECT id,email,email_verified_at,state FROM accounts WHERE normalized_email=%s FOR UPDATE',(email,)).fetchone()
        if not user or user['state']=='disabled':return
        if kind=='verify' and user['email_verified_at']:return
        if kind=='reset' and not user['email_verified_at']:return
        token=issue(con,user['id'],kind,60 if kind=='verify' else 30)
    deliver(user['id'],user['email'],kind,token)


def consume(con,token,kind):
    owner=con.execute('SELECT user_id FROM auth_tokens WHERE token_hash=%s AND kind=%s',(token_hash(token),kind)).fetchone()
    if not owner:raise HTTPException(400,'الرابط غير صالح أو منتهي أو مستخدم سابقًا')
    con.execute('SELECT id FROM accounts WHERE id=%s FOR UPDATE',(owner['user_id'],))
    row=con.execute('SELECT * FROM auth_tokens WHERE token_hash=%s AND kind=%s FOR UPDATE',(token_hash(token),kind)).fetchone()
    if not row or row['consumed_at'] or row['expires_at']<=now():raise HTTPException(400,'الرابط غير صالح أو منتهي أو مستخدم سابقًا')
    con.execute('UPDATE auth_tokens SET consumed_at=now() WHERE token_hash=%s',(row['token_hash'],))
    return row['user_id']


def verify(token):
    with db() as con:
        user=consume(con,token,'verify')
        row=con.execute('SELECT state FROM accounts WHERE id=%s FOR UPDATE',(user,)).fetchone()
        if row['state']=='disabled':raise HTTPException(403,'الحساب موقوف')
        con.execute("UPDATE accounts SET email_verified_at=now(),state='active' WHERE id=%s",(user,))
        con.execute("INSERT INTO workspaces(id,owner_user_id,state) VALUES(%s,%s,'private') ON CONFLICT(owner_user_id) DO NOTHING",(uid(),user))
    audit('account.verified',user,actor_id=user)


def csrf(raw):return hmac.new(os.environ['CTRLTEA_AUTH_SECRET'].encode(),('csrf:'+raw).encode(),hashlib.sha256).hexdigest()


def login(email,password,device='',old_token=None):
    email=normalize(email)
    with db() as con:
        row=con.execute('SELECT a.*,c.password_hash FROM accounts a JOIN credentials c ON c.user_id=a.id WHERE normalized_email=%s',(email,)).fetchone()
    try:valid=hasher.verify(row['password_hash'] if row else _dummy_hash,password)
    except (VerificationError,InvalidHashError):valid=False
    if not row or not valid or not row['email_verified_at'] or row['state']!='active':
        audit('login',row['id'] if row else 'unknown','denied')
        raise HTTPException(401,'تعذر الدخول؛ تحقق من بياناتك وتفعيل البريد وحالة الحساب')
    raw=secrets.token_urlsafe(32)
    with db() as con:
        # Recheck status under lock after expensive password verification.
        current=con.execute('SELECT state,auth_version FROM accounts WHERE id=%s FOR SHARE',(row['id'],)).fetchone()
        if current['state']!='active' or current['auth_version']!=row['auth_version']:raise HTTPException(401,'الحساب غير متاح')
        if old_token:con.execute('DELETE FROM sessions WHERE token_hash=%s',(token_hash(old_token),))
        if hasher.check_needs_rehash(row['password_hash']):
            con.execute('UPDATE credentials SET password_hash=%s WHERE user_id=%s',(hasher.hash(password),row['id']))
        con.execute('INSERT INTO sessions(id,token_hash,user_id,auth_version,expires_at,device) VALUES(%s,%s,%s,%s,%s,%s)',(uid(),token_hash(raw),row['id'],current['auth_version'],now()+timedelta(days=7),device[:120]))
    audit('login',row['id'],actor_id=row['id'])
    return raw


def principal(raw):
    if not raw:raise HTTPException(401,'سجّل الدخول للمتابعة')
    with db() as con:
        row=con.execute('SELECT a.id,a.full_name,a.email,a.state,a.role,a.email_verified_at,a.created_at,a.auth_version,s.id AS session_id,s.auth_version AS session_version,s.expires_at,s.last_seen,s.reauthenticated_at,w.id AS workspace_id FROM sessions s JOIN accounts a ON a.id=s.user_id LEFT JOIN workspaces w ON w.owner_user_id=a.id WHERE s.token_hash=%s',(token_hash(raw),)).fetchone()
        if not row or row['state']!='active' or not row['email_verified_at'] or row['expires_at']<=now() or row['last_seen']<now()-timedelta(hours=12) or row['auth_version']!=row['session_version']:
            raise HTTPException(401,'انتهت الجلسة أو لم يعد الحساب متاحًا؛ سجّل الدخول')
        con.execute('UPDATE sessions SET last_seen=now() WHERE id=%s',(row['session_id'],))
        base={r['permission'] for r in con.execute('SELECT permission FROM role_permissions WHERE role=%s',(row['role'],))}
        for r in con.execute('SELECT permission,enabled FROM permission_overrides WHERE user_id=%s',(row['id'],)):
            if r['enabled']:base.add(r['permission'])
            else:base.discard(r['permission'])
    row['permissions']=set(PERMISSIONS) if row['role']=='SuperAdmin' else base
    return row


def safe_user(user):
    return {k:user[k] for k in ('id','full_name','email','role','state','email_verified_at','created_at','workspace_id') if k in user}


def reset_password(token,password,confirm):
    password_check(password,confirm);hashed=hasher.hash(password)
    with db() as con:
        user=consume(con,token,'reset')
        account=con.execute('SELECT email,state FROM accounts WHERE id=%s FOR UPDATE',(user,)).fetchone()
        if account['state']!='active':raise HTTPException(400,'لا يمكن إتمام العملية لهذا الحساب')
        # Task03 accounts may predate credentials. Verified-mail recovery also
        # activates those preserved identities without inventing a password.
        con.execute('INSERT INTO credentials(user_id,password_hash) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET password_hash=EXCLUDED.password_hash',(user,hashed))
        con.execute('UPDATE accounts SET auth_version=auth_version+1 WHERE id=%s',(user,))
        con.execute('DELETE FROM sessions WHERE user_id=%s',(user,))
        con.execute("UPDATE auth_tokens SET consumed_at=now() WHERE user_id=%s AND kind='reset'",(user,))
    audit('password.reset',user,actor_id=user)
    try:mailer.send(account['email'],'تغيير كلمة المرور','تم تغيير كلمة المرور وإبطال الجلسات السابقة. إذا لم تكن أنت، تواصل مع المسؤول.')
    except Exception:audit('mail.notification',user,'failed')


def require_admin(user):
    if user['role']!='SuperAdmin':raise HTTPException(403,'هذه العملية للمسؤول العام فقط')


def step_up(user):
    require_admin(user)
    if user['reauthenticated_at']<now()-timedelta(minutes=15):raise HTTPException(403,'أعد تأكيد كلمة المرور من إعدادات الحساب أولًا',headers={'X-Auth-Reason':'reauth_required'})


def invalidate(con,user):
    con.execute('UPDATE accounts SET auth_version=auth_version+1 WHERE id=%s',(user,))
    con.execute('DELETE FROM sessions WHERE user_id=%s',(user,))


def change_member(admin,target,role=None,state=None):
    step_up(admin)
    with db() as con:
        con.execute('SELECT pg_advisory_xact_lock(814032604)')
        row=con.execute('SELECT id,role,state,email_verified_at FROM accounts WHERE id=%s FOR UPDATE',(target,)).fetchone()
        if not row:raise HTTPException(404,'الحساب غير موجود')
        if role is not None and role not in ('SuperAdmin','Member','Reviewer'):raise HTTPException(422,'الدور غير معروف')
        if state is not None and state not in ('active','disabled'):raise HTTPException(422,'الحالة غير معروفة')
        new_role=role or row['role'];new_state=state or row['state']
        if row['role']=='SuperAdmin' and row['state']=='active' and (new_role!='SuperAdmin' or new_state!='active'):
            count=con.execute("SELECT count(*) AS n FROM accounts WHERE role='SuperAdmin' AND state='active' AND email_verified_at IS NOT NULL").fetchone()['n']
            if count<=1:raise HTTPException(409,'لا يمكن تعطيل أو خفض صلاحيات آخر مسؤول عام نشط')
        if new_state=='active' and not row['email_verified_at']:new_state='pending'
        con.execute('UPDATE accounts SET role=%s,state=%s WHERE id=%s',(new_role,new_state,target))
        invalidate(con,target)
        if new_state=='disabled':
            con.execute('UPDATE auth_tokens SET consumed_at=now() WHERE user_id=%s AND consumed_at IS NULL',(target,))
        con.execute('INSERT INTO security_audit(actor_id,action,target,outcome,metadata) VALUES(%s,%s,%s,%s,%s)',(admin['id'],'member.changed',target,'success',json.dumps({'role':new_role,'state':new_state})))


def job_principal(user_id):
    if not user_id:raise ValueError('المهمة القديمة تحتاج طلب تشغيل مخوّل جديد')
    with db() as con:
        row=con.execute("SELECT a.id,a.role,a.state,a.email_verified_at,w.id AS workspace_id FROM accounts a LEFT JOIN workspaces w ON w.owner_user_id=a.id WHERE a.id=%s",(user_id,)).fetchone()
        if not row or row['state']!='active' or not row['email_verified_at']:raise ValueError('الحساب غير مخوّل لتشغيل المهمة')
        permissions={r['permission'] for r in con.execute('SELECT permission FROM role_permissions WHERE role=%s',(row['role'],))}
        for item in con.execute('SELECT permission,enabled FROM permission_overrides WHERE user_id=%s',(user_id,)):
            if item['enabled']:permissions.add(item['permission'])
            else:permissions.discard(item['permission'])
    row['permissions']=set(PERMISSIONS) if row['role']=='SuperAdmin' else permissions
    return row
