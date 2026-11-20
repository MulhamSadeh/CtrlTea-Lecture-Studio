"""Real Arabic account/admin browser flow. Disposable local PostgreSQL only.

Requires CTRLTEA_E2E_DISPOSABLE=1, migrated test DB/service roles and local mail.
No external email or public deployment. Install Playwright Chromium separately.
"""
import json,os,re,secrets,subprocess,sys,time
from pathlib import Path
from email import policy
from email.parser import BytesParser
from urllib.request import urlopen


def main():
    if os.environ.get('CTRLTEA_E2E_DISPOSABLE')!='1' or os.environ.get('CTRLTEA_MAIL_PROVIDER')!='local':
        raise SystemExit('Explicit disposable database acknowledgement and local mail provider required')
    from playwright.sync_api import sync_playwright,expect
    from ctrltea.models import uid
    project=Path(__file__).resolve().parents[1]
    base='http://localhost:8765';env={**os.environ,'CTRLTEA_AUTH_MODE':'required','CTRLTEA_DB_BACKEND':'postgres','CTRLTEA_PUBLIC_ORIGIN':base,'CTRLTEA_COOKIE_SECURE':'0'}
    env['CTRLTEA_DATABASE_URL']=os.environ['CTRLTEA_TEST_DATABASE_URL']
    output=Path(os.environ.get('CTRLTEA_E2E_OUTPUT',project/'output/account-e2e'));output.mkdir(parents=True,exist_ok=True)
    sink=Path(env['CTRLTEA_MAIL_SINK']);checks=[]
    def check(name):checks.append({'check':name,'status':'PASS'});print('PASS:',name,flush=True)
    def mail_link(email,kind):
        found=[]
        for path in sink.glob('*.eml'):
            m=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
            if m['To']==email:
                token=re.search('#'+kind+r'=([A-Za-z0-9_-]+)',m.get_body(preferencelist=('plain',)).get_content())
                if token:found.append((path.stat().st_mtime_ns,token.group(1)))
        assert found,kind
        return base+'/#'+kind+'='+max(found)[1]
    with (output/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','ctrltea.api:app','--host','127.0.0.1','--port','8765','--no-access-log'],cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(120):
                try:
                    with urlopen(base+'/api/health',timeout=.3) as r:
                        if r.status==200:break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Local account server failed to start')
            with sync_playwright() as playwright:
                kwargs={'headless':True,'args':['--disable-dev-shm-usage','--no-zygote']}
                if hasattr(os,'geteuid') and os.geteuid()==0:kwargs['args'].append('--no-sandbox')
                if os.environ.get('CTRLTEA_E2E_BROWSER'):kwargs['executable_path']=os.environ['CTRLTEA_E2E_BROWSER']
                browser=playwright.chromium.launch(**kwargs)
                errors=[];contexts=[]
                def register(name):
                    context=browser.new_context(viewport={'width':1280,'height':900});contexts.append(context)
                    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    email='e2e-'+uid()+'@example.com';pwd=secrets.token_urlsafe(24)
                    page.goto(base);page.get_by_role('button',name='إنشاء حساب',exact=True).click()
                    page.get_by_label('الاسم الكامل',exact=True).fill(name);page.get_by_label('البريد الإلكتروني',exact=True).fill(email)
                    page.get_by_label('كلمة المرور',exact=True).fill(pwd);page.get_by_label('تأكيد كلمة المرور',exact=True).fill(pwd)
                    page.get_by_role('button',name='إنشاء حساب',exact=True).click();expect(page.get_by_role('status')).to_contain_text('إذا كانت البيانات')
                    page.goto(mail_link(email,'verify'));page.get_by_role('button',name='تأكيد تفعيل البريد',exact=True).click()
                    expect(page.get_by_role('status')).to_contain_text('تم تفعيل البريد')
                    page.get_by_role('button',name='تسجيل الدخول',exact=True).click()
                    page.get_by_label('البريد الإلكتروني',exact=True).fill(email);page.get_by_label('كلمة المرور',exact=True).fill(pwd)
                    page.get_by_role('button',name='تسجيل الدخول',exact=True).click();expect(page.get_by_role('button',name='بروفايلي',exact=True)).to_be_visible()
                    return page,email,pwd
                alice,email,pwd=register('Alice عضو الاختبار');check('UI registration, mailbox verification and login')
                alice.get_by_role('button',name='مقرر جديد',exact=True).click();alice.get_by_label('اسم المقرر',exact=True).fill('Alice Private Course')
                alice.get_by_role('button',name='حفظ المقرر',exact=True).click();expect(alice.get_by_role('heading',name='Alice Private Course',exact=True).first).to_be_visible()
                alice.get_by_role('button',name='محاضرة جديدة',exact=True).click();alice.get_by_label('عنوان المحاضرة',exact=True).fill('Browser private lecture')
                alice.get_by_role('button',name='إنشاء المحاضرة',exact=True).click();expect(alice.locator('.modal')).to_have_count(0)
                me=alice.request.get(base+'/api/auth/me').json();courses=alice.request.get(base+'/api/courses').json();course=courses[0]
                lecture=alice.request.get(base+'/api/courses/'+course['id']+'/lectures').json()[0]
                check('Existing editor course/lecture UI works with authenticated API')
                alice.get_by_role('button',name='بروفايلي',exact=True).click();description='أنا أؤلف المحاضرات <script>window.xss=true</script>'
                alice.get_by_label('شو شغلتك ضمن Ctrl+Tea؟',exact=True).fill(description);alice.get_by_role('button',name='حفظ البروفايل',exact=True).click()
                expect(alice.get_by_role('status')).to_contain_text('حُفظت معلوماتك');assert alice.evaluate('window.xss') is None
                alice.get_by_role('button',name='دليل الفريق',exact=True).click();expect(alice.get_by_text(description,exact=True)).to_be_visible();assert alice.evaluate('window.xss') is None
                alice.set_viewport_size({'width':390,'height':844});alice.screenshot(path=str(output/'mobile-profile.png'),full_page=True)
                assert alice.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
                alice.set_viewport_size({'width':1280,'height':900});check('Profile self-description, escaped directory rendering and mobile RTL layout')
                bob,bobmail,bobpwd=register('Bob عضو مستقل')
                assert bob.request.get(base+'/api/lectures/'+lecture['id']+'?workspace='+me['workspace_id']).status==404
                expect(bob.get_by_text('Alice Private Course',exact=True)).to_have_count(0);check('Separate real browser contexts preserve workspace privacy')
                admin,adminmail,adminpwd=register('مسؤول الاختبار')
                env['PYTHONPATH']=str(project/'backend')
                subprocess.run([sys.executable,'-m','ctrltea.bootstrap','invite','--email',adminmail],cwd=project,env=env,check=True,stdout=subprocess.DEVNULL)
                admin.goto(mail_link(adminmail,'bootstrap'));admin.get_by_role('button',name='تأكيد تفعيل صلاحية المسؤول العام',exact=True).click()
                expect(admin.get_by_text('فُعّلت الإدارة؛ سجّل الدخول مجددًا لتحديث الجلسة',exact=True)).to_be_visible()
                admin.get_by_label('البريد الإلكتروني',exact=True).fill(adminmail);admin.get_by_label('كلمة المرور',exact=True).fill(adminpwd)
                admin.get_by_role('button',name='تسجيل الدخول',exact=True).click();admin.get_by_role('button',name='إدارة المنصة',exact=True).click()
                expect(admin.get_by_role('heading',name='لوحة المسؤول العام',exact=True)).to_be_visible();check('Protected operator bootstrap and actual Super Admin dashboard')
                row=admin.get_by_role('row').filter(has=admin.get_by_text(email,exact=True));row.get_by_role('button',name='فتح المساحة',exact=True).click()
                expect(admin.locator('.admin-workspace-banner')).to_contain_text('Alice عضو الاختبار')
                expect(admin.get_by_role('heading',name='Alice Private Course',exact=True).first).to_be_visible()
                admin.screenshot(path=str(output/'admin-workspace.png'),full_page=True)
                admin.get_by_role('button',name='العودة إلى إدارة المنصة',exact=True).click();check('Admin opens member content under own identity with explicit banner')
                admin.get_by_role('button',name='منح موارد محددة',exact=True).click()
                bobme=bob.request.get(base+'/api/auth/me').json()
                admin.get_by_label('المستفيد',exact=True).select_option(bobme['id'])
                admin.get_by_label('المساحة المالكة للمورد',exact=True).select_option(me['workspace_id'])
                admin.get_by_label('المورد',exact=True).select_option(lecture['id'])
                admin.get_by_label('عرض المحاضرات',exact=True).check();admin.get_by_role('button',name='منح الوصول',exact=True).click()
                expect(admin.get_by_text('حُفظ المنح وأُبطلت جلسات المستفيد لتحديث صلاحياته.',exact=True)).to_be_visible()
                assert bob.request.post(base+'/api/auth/login',data={'email':bobmail,'password':bobpwd}).status==200
                assert bob.request.get(base+'/api/lectures/'+lecture['id']+'?workspace='+me['workspace_id']).status==200
                admin.once('dialog',lambda dialog:dialog.accept());admin.get_by_role('button',name='سحب',exact=True).click()
                expect(admin.get_by_text('مسحوب',exact=False)).to_be_visible()
                assert bob.request.post(base+'/api/auth/login',data={'email':bobmail,'password':bobpwd}).status==200
                assert bob.request.get(base+'/api/lectures/'+lecture['id']+'?workspace='+me['workspace_id']).status==404
                check('Real resource-picker grant and revocation UI with scoped backend access')
                admin.get_by_role('button',name='الأعضاء والصلاحيات',exact=True).click()
                row=admin.get_by_role('row').filter(has=admin.get_by_text(email,exact=True));row.get_by_role('button',name='إدارة العضو',exact=True).click()
                admin.get_by_label('إنشاء مادة',exact=True).select_option('deny');admin.get_by_role('button',name='حفظ الصلاحيات',exact=True).click()
                expect(admin.get_by_text('حُفظت الصلاحيات.',exact=True)).to_be_visible()
                # Trigger an ordinary protected request after server revocation.
                alice.get_by_role('button',name='بروفايلي',exact=True).click()
                expect(alice.get_by_role('heading',name='تسجيل الدخول',exact=True)).to_be_visible();check('Permission UI revokes active browser session and shows functional login')
                row=admin.get_by_role('row').filter(has=admin.get_by_text(bobmail,exact=True));row.get_by_role('button',name='إدارة العضو',exact=True).click()
                admin.once('dialog',lambda dialog:dialog.accept());admin.get_by_role('button',name='تعليق الحساب',exact=True).click()
                expect(admin.get_by_role('row').filter(has=admin.get_by_text(bobmail,exact=True))).to_contain_text('disabled')
                row=admin.get_by_role('row').filter(has=admin.get_by_text(bobmail,exact=True));row.get_by_role('button',name='إدارة العضو',exact=True).click()
                admin.once('dialog',lambda dialog:dialog.accept());admin.get_by_role('button',name='إعادة التنشيط',exact=True).click()
                expect(admin.get_by_role('row').filter(has=admin.get_by_text(bobmail,exact=True))).to_contain_text('active')
                admin.get_by_role('button',name='النشاط الإداري',exact=True).click();expect(admin.get_by_role('cell',name='permissions.changed',exact=True).first).to_be_visible();check('Suspension/reactivation and visible administrative audit')
                # Public Arabic recovery page, email link, new password and login.
                alice.get_by_role('button',name='نسيت كلمة المرور',exact=True).click();alice.get_by_label('البريد الإلكتروني',exact=True).fill(email)
                alice.get_by_role('button',name='نسيت كلمة المرور',exact=True).click();expect(alice.get_by_role('status')).to_contain_text('إذا كانت البيانات')
                alice.goto(mail_link(email,'reset'));newpwd=secrets.token_urlsafe(24)
                alice.get_by_label('كلمة المرور',exact=True).fill(newpwd);alice.get_by_label('تأكيد كلمة المرور',exact=True).fill(newpwd)
                alice.get_by_role('button',name='كلمة مرور جديدة',exact=True).click();expect(alice.get_by_role('status')).to_contain_text('تم تغيير كلمة المرور')
                alice.get_by_role('button',name='تسجيل الدخول',exact=True).click();alice.get_by_label('البريد الإلكتروني',exact=True).fill(email)
                alice.get_by_label('كلمة المرور',exact=True).fill(newpwd);alice.get_by_role('button',name='تسجيل الدخول',exact=True).click()
                expect(alice.get_by_role('button',name='بروفايلي',exact=True)).to_be_visible();check('Arabic forgot/reset-password mail flow and new-password login')
                alice.get_by_role('button',name='خروج',exact=True).click()
                if alice.get_by_role('dialog').count():alice.get_by_role('button',name='الخروج وحذف المسودات المحلية',exact=True).click()
                expect(alice.get_by_role('heading',name='تسجيل الدخول',exact=True)).to_be_visible()
                assert not errors,errors
                check('Logout and no uncaught frontend JavaScript errors')
                result={'status':'PASS','browser':browser.version,'checks':checks,'external_email':'NOT RUN: local sink only','screenshots':'Internal QA only; excluded from deliverables'}
                (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
                browser.close()
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':main()
