"""One deny-by-default policy for every legacy resource route."""
from fastapi import HTTPException,Request
from . import accounts,store,persistence

POLICY={
 'schema':'lectures.view','author_schema':'authoring.create','design':'lectures.view',
 'courses':'courses.view','create_course':'courses.create','edit_course':'courses.edit','delete_course':'courses.delete',
 'lectures':'lectures.view','create_lecture':'lectures.create','get_lecture':'lectures.view','save_lecture':'lectures.edit',
 'set_lecture_theme':'theme.edit','delete_lecture':'lectures.delete','revisions':'revisions.view','restore':'revisions.restore',
 'list_sources':'sources.view','upload_source':'sources.upload','word_preview':'sources.upload',
 'edit_source':'sources.edit','delete_source':'sources.delete','get_pages':'sources.view','add_transcript_page':'sources.edit',
 'correct_page':'sources.edit','image':'sources.view','source_file':'files.download','extract_source':'sources.extract',
 'author_packet':'authoring.create','runs':'authoring.create','author_preview':'authoring.import','author_import':'authoring.import',
 'checks':'lectures.view','check_math':'math.check','figure_preview':'figures.preview','figure':'lectures.view',
 'jobs':'jobs.view','retry':'jobs.retry','create_export':'lectures.export','list_exports':'lectures.view',
 'export_file':'files.download','export_page':'files.download','reviewed':'lectures.export',
 'selected_lecture_bundle':'transfers.export','single_lecture_bundle':'transfers.export','course_bundle':'transfers.export',
 'preview_transfer':'transfers.import','import_transfer':'transfers.import','project_import':'transfers.import',
 'trash_list':'resources.restore','trash_restore':'resources.restore'
}
PUBLIC={'register_account','login_account','verify_account','resend_verification','forgot_password','reset_account_password','auth_status','health'}
ACCOUNT_ROUTES={'me','logout_account','reauthenticate','change_password','my_sessions','revoke_session','my_profile','update_profile','upload_avatar','members','member_avatar','my_grants','accept_bootstrap'}


def can(user,permission,workspace_id,lid=None,cid=None):
    if user['role']=='SuperAdmin':return True
    if permission not in user['permissions']:return False
    if workspace_id==user['workspace_id']:return True
    with accounts.db() as con:
        grants=con.execute('SELECT resource_kind,resource_id,permissions FROM resource_grants WHERE user_id=%s AND workspace_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())',(user['id'],workspace_id)).fetchall()
    return any(permission in g['permissions'] and ((g['resource_kind']=='lecture' and lid==g['resource_id']) or (g['resource_kind']=='course' and cid==g['resource_id'])) for g in grants)


def resource_context(params):
    lid=params.get('lid');cid=params.get('cid')
    if params.get('sid'):
        lid=store.one('SELECT lecture_id FROM sources WHERE id=?',(params['sid'],))['lecture_id']
    if params.get('jid'):
        lid=store.one('SELECT lecture_id FROM jobs WHERE id=?',(params['jid'],))['lecture_id']
    if params.get('eid'):
        from .api import export_path
        import json
        lid=json.loads((export_path(params['eid'])/'report.json').read_text())['lecture_id']
    if lid:
        cid=store.one('SELECT course_id FROM lectures WHERE id=?',(lid,))['course_id']
    return lid,cid


async def authorize(request:Request):
    if not accounts.enabled():
        yield
        return
    name=request.scope['route'].name
    supplied=request.headers.get('origin')
    if supplied and supplied.rstrip('/')!=accounts.origin():raise HTTPException(403,'مصدر الطلب غير مسموح')
    if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'مصدر الطلب غير مسموح')
    if name in PUBLIC:
        yield
        return
    raw=request.cookies.get(accounts.cookie_name())
    user=accounts.principal(raw)
    request.state.principal=user
    if request.method not in ('GET','HEAD','OPTIONS'):
        import hmac
        if not hmac.compare_digest(request.headers.get('x-csrf-token',''),accounts.csrf(raw)):
            raise HTTPException(403,'رمز حماية الطلب غير صالح؛ حدّث الجلسة')
    token=accounts.actor.set(user)
    admin_token=accounts.admin_scope.set(user['role']=='SuperAdmin')
    try:
        if name in ACCOUNT_ROUTES or name.startswith('admin_'):
            if name.startswith('admin_'):accounts.require_admin(user)
            yield
            return
        if name not in POLICY:raise HTTPException(403,'لا توجد صلاحية لهذا المسار')
        wid=request.headers.get('x-ctrltea-workspace') or request.query_params.get('workspace') or user['workspace_id']
        if not wid:raise HTTPException(403,'لا توجد مساحة مملوكة للحساب')
        # A supplied workspace is a selection request, never an authorization.
        with accounts.db() as con:
            ws=con.execute('SELECT id,owner_user_id,state FROM workspaces WHERE id=%s',(wid,)).fetchone()
        if not ws or (ws['state']!='private' and user['role']!='SuperAdmin'):raise HTTPException(404,'المورد غير موجود')
        with store.workspace(wid):
            request.state.workspace_id=wid
            try:lid,cid=resource_context(request.path_params)
            except (LookupError,ValueError):raise HTTPException(404,'المورد غير موجود')
            permission=POLICY[name]
            if not can(user,permission,wid,lid,cid):raise HTTPException(404 if wid!=user['workspace_id'] else 403,'لا تملك صلاحية الوصول إلى هذا المورد')
            if name in ('upload_source','word_preview') and not can(user,'sources.extract',wid,lid,cid):
                raise HTTPException(403,'رفع المصدر مع الاستخراج يحتاج صلاحية استخراج النص أيضًا')
            if name=='retry':
                row=store.one('SELECT kind FROM jobs WHERE id=?',(request.path_params['jid'],))
                needed='lectures.export' if row['kind']=='export' else 'sources.extract'
                if not can(user,needed,wid,lid,cid):raise HTTPException(403,'صلاحية تشغيل نوع المهمة غير متاحة')
            if request.method not in ('GET','HEAD') and 'application/json' in request.headers.get('content-type',''):
                body=await request.json()
                # Validate nested cross-resource references before a preview or
                # import can read a different lecture in a granted workspace.
                def references(value):
                    if isinstance(value,dict):
                        for key,item in value.items():
                            if key in ('source_id','linked_id') and isinstance(item,str) and item:
                                source=store.one('SELECT lecture_id FROM sources WHERE id=?',(item,))
                                parent=store.one('SELECT course_id FROM lectures WHERE id=?',(source['lecture_id'],))
                                if not can(user,'sources.view',wid,source['lecture_id'],parent['course_id']):raise HTTPException(404,'المصدر غير متاح')
                            else:references(item)
                    elif isinstance(value,list):
                        for item in value:references(item)
                # External author-result IDs may be aliases; original authoring
                # validator resolves them against this lecture, not globally.
                if name not in ('author_preview','author_import'):references(body)
                if name=='import_transfer':
                    target=body.get('target_lecture_id');course=body.get('target_course_id')
                    if target:
                        course=store.lecture(target)['course_id']
                    if target or course:
                        if not can(user,'lectures.import',wid,target,course):raise HTTPException(403,'وجهة الاستيراد غير متاحة')
            if wid!=user['workspace_id']:
                # Persist intent before a privileged read/write, plus outcome in middleware.
                accounts.audit('resource.access',lid or cid or name,workspace_id=wid,metadata={'route':name,'method':request.method,'owner':ws['owner_user_id']})
            store.DATA.mkdir(parents=True,exist_ok=True)
            for folder in ('sources','exports','figures','math','bundles'):(store.DATA/folder).mkdir(exist_ok=True)
            yield
    finally:
        accounts.admin_scope.reset(admin_token)
        accounts.actor.reset(token)


class SecurityHeaders:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not accounts.enabled():
            await self.app(scope,receive,send);return
        async def guarded_send(message):
            if message['type']=='http.response.start':
                headers=list(message.get('headers',[]))
                headers.extend([(b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY'),(b'referrer-policy',b'no-referrer'),(b'cache-control',b'no-store'),(b'content-security-policy',b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: blob:; frame-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")])
                message['headers']=headers
                state=scope.get('state',{});user=state.get('principal');route=scope.get('route')
                if route and scope['path'].startswith('/api/') and (scope['method'] not in ('GET','HEAD') or (user and user['role']=='SuperAdmin')):
                    from starlette.concurrency import run_in_threadpool
                    await run_in_threadpool(accounts.audit,'request.'+route.name,'',str(message['status']),user['id'] if user else None,state.get('workspace_id'))
            await send(message)
        await self.app(scope,receive,guarded_send)
