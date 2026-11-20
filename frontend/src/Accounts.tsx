import React,{useEffect,useState,useMemo} from "react";
import {api,apiURL,configureSession} from "./api";
import {WorkspaceStorage,privateStorage,userPrefix,userDrafts,clearUserStorage} from "./workspaceStorage";
import "./accounts.css";

type Me={id:string;full_name:string;email:string;role:string;state:string;workspace_id:string;csrf:string;permissions:string[]};
type Member={id:string;full_name:string;email:string;role:string;state:string;workspace_id:string;email_verified_at:string|null;team_description:string};
type Pending={kind:string;token:string}|null;
const labels:Record<string,string>={login:"تسجيل الدخول",signup:"إنشاء حساب",verify:"تفعيل البريد",resend:"إعادة إرسال التفعيل",forgot:"نسيت كلمة المرور",reset:"كلمة مرور جديدة",bootstrap:"تفعيل دعوة الإدارة",admin_recovery:"استرداد الإدارة"};

function Field({label,value,onChange,type="text",autoComplete,required=true}:{label:string;value:string;onChange:(v:string)=>void;type?:string;autoComplete?:string;required?:boolean}){
  return <label className="account-field"><span>{label}</span><input required={required} type={type} value={value} onChange={e=>onChange(e.target.value)} autoComplete={autoComplete} dir={type==="email"||type==="password"?"ltr":undefined}/></label>;
}
function Notice({error,message}:{error:string;message:string}){return <>{error&&<p role="alert" className="account-error">{error}</p>}{message&&<p role="status" className="account-success">{message}</p>}</>;}

function AuthForm({page,pending,onPage,onLogin}:{page:string;pending:Pending;onPage:(p:string)=>void;onLogin:()=>Promise<void>}){
  const [name,setName]=useState(""),[email,setEmail]=useState(""),[password,setPassword]=useState(""),[confirm,setConfirm]=useState("");
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(""),[error,setError]=useState("");
  useEffect(()=>{setError("");setMessage("");setPassword("");setConfirm("");},[page]);
  const submit=async(e:React.FormEvent)=>{
    e.preventDefault();setBusy(true);setError("");setMessage("");
    try{
      if(page==="login"){
        await api("/auth/login",{method:"POST",body:JSON.stringify({email,password})});await onLogin();
      }else if(page==="signup"){
        const r=await api("/auth/register",{method:"POST",body:JSON.stringify({full_name:name,email,password,confirm_password:confirm})});setMessage(r.message);setPassword("");setConfirm("");
      }else if(page==="forgot"||page==="resend"){
        setMessage((await api("/auth/"+page,{method:"POST",body:JSON.stringify({email})})).message);
      }else if(page==="verify"){
        if(!pending?.token)throw new Error("افتح رابط التفعيل من البريد، أو اطلب رابطًا جديدًا.");
        setMessage((await api("/auth/verify",{method:"POST",body:JSON.stringify({token:pending.token})})).message);
      }else if(page==="reset"){
        if(!pending?.token)throw new Error("افتح رابط الاستعادة من البريد.");
        setMessage((await api("/auth/reset",{method:"POST",body:JSON.stringify({token:pending.token,password,confirm_password:confirm})})).message);setPassword("");setConfirm("");
      }
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  };
  return <main className="account-welcome" dir="rtl"><section className="account-card">
    <img src="/ct-logo.png" alt="شعار Ctrl+Tea"/><p className="account-eyebrow">مساحتك الأكاديمية</p><h1>{labels[page]||labels.login}</h1>
    <form onSubmit={submit}>
      {page==="signup"&&<Field label="الاسم الكامل" value={name} onChange={setName} autoComplete="name"/>}
      {!["verify","reset"].includes(page)&&<Field label="البريد الإلكتروني" value={email} onChange={setEmail} type="email" autoComplete="email"/>}
      {["login","signup","reset"].includes(page)&&<Field label="كلمة المرور" value={password} onChange={setPassword} type="password" autoComplete={page==="login"?"current-password":"new-password"}/>}
      {["signup","reset"].includes(page)&&<><Field label="تأكيد كلمة المرور" value={confirm} onChange={setConfirm} type="password" autoComplete="new-password"/><p className="hint">عبارة مرور من 15 إلى128 محرفًا.</p></>}
      <Notice error={error} message={message}/><button disabled={busy} className="button primary">{busy?"جارٍ إتمام الطلب…":page==="verify"?"تأكيد تفعيل البريد":labels[page]}</button>
    </form>
    <nav className="account-links">{["login","signup","forgot","resend"].filter(p=>p!==page).map(p=><button key={p} onClick={()=>onPage(p)}>{labels[p]}</button>)}</nav>
  </section></main>;
}

function ProfilePage(){
  const [profile,setProfile]=useState<any>(null),[name,setName]=useState(""),[description,setDescription]=useState(""),[file,setFile]=useState<File|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const load=async()=>{const p=await api("/account/profile");setProfile(p);setName(p.full_name);setDescription(p.team_description);};
  useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  const save=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError("");try{
    await api("/account/profile",{method:"PUT",body:JSON.stringify({full_name:name,team_description:description,version:profile.version})});
    if(file){const body=new FormData();body.append("file",file);await api("/account/avatar",{method:"POST",body});setFile(null);}
    await load();setMessage("حُفظت معلوماتك. وصف العمل لا يغيّر صلاحياتك.");
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}};
  return <section className="account-panel"><h1>بروفايلي</h1>{profile?<form onSubmit={save}>
    {profile.has_avatar&&<img className="member-avatar" src={apiURL('/members/'+profile.id+'/avatar')+"&v="+profile.version} alt="صورتي"/>}
    <Field label="الاسم الكامل" value={name} onChange={setName}/>
    <p>البريد المتحقق منه: <b dir="ltr">{profile.email}</b></p><p>دور النظام: <b>{profile.role}</b> · حالة الحساب: {profile.state}</p>
    <p>تاريخ الإنشاء: {new Date(profile.created_at).toLocaleDateString("ar")}</p>
    <label className="account-field"><span>شو شغلتك ضمن Ctrl+Tea؟</span><textarea maxLength={3000} rows={5} value={description} onChange={e=>setDescription(e.target.value)} placeholder="اكتب وصف عملك بحرية؛ يمكن تعديله لاحقًا."/></label>
    <p className="hint">وصفك الشخصي منفصل عن صلاحيات النظام وعن تكليفات المحاضرات.</p>
    <label className="account-field"><span>صورة اختيارية (PNG / JPEG / WebP، حتى 2MB)</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
    <Notice error={error} message={message}/><button className="button primary" disabled={busy}>{busy?"جارٍ الحفظ…":"حفظ البروفايل"}</button><button type="button" className="button secondary" onClick={()=>{if(window.confirm('تحميل البروفايل المحفوظ واستبدال التعديلات غير المحفوظة؟'))load().catch(e=>setError(e.message));}}>تحميل أحدث بروفايل</button>
  </form>:<p role="status">جارٍ تحميل البروفايل…</p>}</section>;
}

function Settings({me,onLogout,onRefresh}:{me:Me;onLogout:()=>void;onRefresh:()=>Promise<void>}){
  const [current,setCurrent]=useState(""),[password,setPassword]=useState(""),[confirm,setConfirm]=useState(""),[sessions,setSessions]=useState<any[]>([]),[error,setError]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  const load=()=>api<any[]>("/auth/sessions").then(setSessions);
  useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  return <section className="account-panel"><h1>إعدادات الحساب والأمان</h1><Notice error={error} message={message}/>
    <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError("");try{
      await api("/auth/password",{method:"POST",body:JSON.stringify({current_password:current,password,confirm_password:confirm})});onLogout();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
      <h2>تغيير كلمة المرور</h2><Field label="كلمة المرور الحالية" value={current} onChange={setCurrent} type="password" autoComplete="current-password"/>
      <Field label="كلمة المرور الجديدة" value={password} onChange={setPassword} type="password" autoComplete="new-password"/>
      <Field label="تأكيد الجديدة" value={confirm} onChange={setConfirm} type="password" autoComplete="new-password"/>
      <button className="button primary" disabled={busy}>تغيير وإبطال الجلسات السابقة</button>
      {me.role==="SuperAdmin"&&<button className="button secondary" type="button" disabled={busy} onClick={async()=>{setBusy(true);try{await api("/auth/reauth",{method:"POST",body:JSON.stringify({email:me.email,password:current})});await onRefresh();setMessage("تم تأكيد كلمة المرور للعمليات الإدارية الحساسة.");}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>تأكيد الجلسة للعمليات الإدارية</button>}
    </form>
    <h2>الجلسات النشطة</h2><ul>{sessions.map(s=><li key={s.id}>{s.current?"هذه الجلسة":"جلسة أخرى"} — {s.device||"متصفح"} — {new Date(s.last_seen).toLocaleString("ar")} <button onClick={async()=>{try{await api('/auth/sessions/'+s.id,{method:'DELETE'});if(s.current)onLogout();else await load();}catch(e){setError((e as Error).message);}}}>إنهاء الجلسة</button></li>)}</ul>
  </section>;
}

function Directory(){
  const [rows,setRows]=useState<any[]>([]),[query,setQuery]=useState(""),[error,setError]=useState("");
  useEffect(()=>{api<any[]>("/members?q="+encodeURIComponent(query)).then(setRows).catch(e=>setError(e.message));},[query]);
  return <section className="account-panel"><h1>دليل فريق Ctrl+Tea</h1><Field label="البحث بالاسم" value={query} onChange={setQuery} required={false}/><Notice error={error} message=""/>
    <div className="member-grid">{rows.map(r=><article className="member-card" key={r.id}>{r.has_avatar&&<img className="member-avatar" src={apiURL('/members/'+r.id+'/avatar')} alt={r.full_name}/>}
      <h2>{r.full_name}</h2><span className="account-badge">دور النظام: {r.role}</span><p>{r.team_description||"لم يضف وصف عمله بعد."}</p>
    </article>)}</div><p className="hint">الدليل لا يعرض المواد أو الملفات الخاصة أو عناوين البريد.</p></section>;
}

function Permissions({member,catalog,onDone}:{member:Member;catalog:any[];onDone:()=>void}){
  const [model,setModel]=useState<any>(null),[changes,setChanges]=useState<Record<string,boolean|null>>({}),[error,setError]=useState(""),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  useEffect(()=>{api('/admin/members/'+member.id+'/permissions').then(setModel).catch(e=>setError(e.message));setChanges({});},[member.id]);
  return <section className="account-subpanel"><h2>صلاحيات {member.full_name}</h2><p>الافتراضي من دور النظام. المنح أو المنع الشخصي يُطبَّق على الخادم فورًا وتُبطل الجلسات السابقة.</p>
    <Notice error={error} message={message}/>{model&&<form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await api('/admin/members/'+member.id+'/permissions',{method:'PUT',body:JSON.stringify({changes})});setMessage('حُفظت الصلاحيات.');onDone();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
      <div className="permission-table"><table><thead><tr><th>المجموعة</th><th>الإجراء</th><th>دور النظام</th><th>التخصيص</th></tr></thead><tbody>{catalog.map(p=>{
        const value=Object.prototype.hasOwnProperty.call(changes,p.name)?changes[p.name]:(model.overrides[p.name]??null);
        return <tr key={p.name}><td>{p.group_name}</td><td>{p.label}{p.future&&<small> — بنية صلاحية لميزة لاحقة</small>}</td><td>{model.role==='SuperAdmin'||model.base.includes(p.name)?'مسموح':'غير مفعّل'}</td><td><select aria-label={p.label} disabled={model.role==='SuperAdmin'} value={value===null?'default':value?'allow':'deny'} onChange={e=>setChanges({...changes,[p.name]:e.target.value==='default'?null:e.target.value==='allow'})}><option value="default">حسب الدور</option><option value="allow">منح</option><option value="deny">منع</option></select></td></tr>;
      })}</tbody></table></div><button className="button primary" disabled={busy}>حفظ الصلاحيات</button>
    </form>}</section>;
}

function Admin({onOpen}:{onOpen:(id:string,label:string)=>void}){
  const [rows,setRows]=useState<Member[]>([]),[query,setQuery]=useState(""),[selected,setSelected]=useState<Member|null>(null),[catalog,setCatalog]=useState<any[]>([]),[audit,setAudit]=useState<any[]>([]),[spaces,setSpaces]=useState<any[]>([]),[grants,setGrants]=useState<any[]>([]);
  const [tab,setTab]=useState('members'),[error,setError]=useState(''),[message,setMessage]=useState(''),[role,setRole]=useState('Member'),[busy,setBusy]=useState(false);
  const [grantUser,setGrantUser]=useState(''),[grantWorkspace,setGrantWorkspace]=useState(''),[grantKind,setGrantKind]=useState('lecture'),[resource,setResource]=useState(''),[grantActions,setGrantActions]=useState<string[]>([]),[claimUser,setClaimUser]=useState(''),[claimSpace,setClaimSpace]=useState('');
  const [grantResources,setGrantResources]=useState<any[]>([]);
  useEffect(()=>{
    let cancelled=false;setResource('');setGrantResources([]);
    if(grantWorkspace){const options={headers:{'X-Ctrltea-Workspace':grantWorkspace}};
      api<any[]>('/courses',options).then(async courses=>grantKind==='course'?courses:((await Promise.all(courses.map(async course=>(await api<any[]>('/courses/'+course.id+'/lectures',options)).map(lecture=>({...lecture,name:course.name+' / '+lecture.title}))))).flat())).then(resources=>{if(!cancelled)setGrantResources(resources);}).catch(e=>{if(!cancelled)setError(e.message);});
    }
    return()=>{cancelled=true;};
  },[grantWorkspace,grantKind]);
  const load=async()=>{const [m,c,s,g]=await Promise.all([api<Member[]>('/admin/members?q='+encodeURIComponent(query)),api<any[]>('/admin/permissions'),api<any[]>('/admin/workspaces'),api<any[]>('/admin/grants')]);setRows(m);setSelected(previous=>previous?m.find(r=>r.id===previous.id)||null:null);setCatalog(c);setSpaces(s);setGrants(g);};
  useEffect(()=>{load().catch(e=>setError(e.message));},[query]);
  const act=async(fn:()=>Promise<any>)=>{setBusy(true);setError('');try{await fn();await load();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
  return <section className="account-panel admin-panel"><h1>لوحة المسؤول العام</h1><p>وصول إداري شامل بهويتك الحالية، مع تسجيل العمليات. لا تحتاج كلمة مرور أي عضو.</p>
    <nav className="account-tabs">{[['members','الأعضاء والصلاحيات'],['workspaces','المساحات والمطالبات'],['grants','منح موارد محددة'],['audit','النشاط الإداري']].map(([k,label])=><button key={k} className={tab===k?'selected':''} onClick={()=>{setTab(k);if(k==='audit')api<any[]>('/admin/audit').then(setAudit).catch(e=>setError(e.message));}}>{label}</button>)}</nav>
    <Notice error={error} message={message}/>
    {tab==='members'&&<><Field label="البحث باسم العضو أو بريده" value={query} onChange={setQuery} required={false}/><div className="permission-table"><table><thead><tr><th>العضو</th><th>البريد</th><th>التفعيل</th><th>الحالة</th><th>الدور</th><th>الإجراءات</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>{r.full_name}</td><td dir="ltr">{r.email}</td><td>{r.email_verified_at?'متحقق':'بانتظار التحقق'}</td><td>{r.state}</td><td>{r.role}</td><td><button onClick={()=>{setSelected(r);setRole(r.role);}}>إدارة العضو</button>{r.workspace_id&&<button onClick={()=>onOpen(r.workspace_id,r.full_name)}>فتح المساحة</button>}</td></tr>)}</tbody></table></div>
      {rows.length>=200&&<button onClick={()=>api<Member[]>('/admin/members?q='+encodeURIComponent(query)+'&offset='+rows.length).then(m=>setRows([...rows,...m])).catch(e=>setError(e.message))}>تحميل المزيد من الأعضاء</button>}
      {selected&&<><section className="account-subpanel"><h2>إدارة {selected.full_name}</h2><p>وصفه الذاتي: {selected.team_description||'لم يكتب وصفًا'}</p><label className="account-field"><span>دور النظام</span><select aria-label="دور النظام" value={role} onChange={e=>setRole(e.target.value)}><option>Member</option><option>Reviewer</option><option>SuperAdmin</option></select></label><button disabled={busy} className="button secondary" onClick={()=>{if(window.confirm('تأكيد تغيير الدور وإبطال جلسات العضو؟'))act(async()=>{await api('/admin/members/'+selected.id,{method:'PUT',body:JSON.stringify({role})});setMessage('حُدّث الدور.');});}}>تطبيق الدور</button><button disabled={busy} className="button danger" onClick={()=>{if(window.confirm(selected.state==='disabled'?'تأكيد إعادة تنشيط العضو؟':'تأكيد تعليق الحساب وإبطال جلساته؟'))act(async()=>{await api('/admin/members/'+selected.id,{method:'PUT',body:JSON.stringify({state:selected.state==='disabled'?'active':'disabled'})});setSelected(null);});}}>{selected.state==='disabled'?'إعادة التنشيط':'تعليق الحساب'}</button></section><Permissions key={selected.id+selected.role} member={selected} catalog={catalog} onDone={()=>{}}/></>}
    </>}
    {tab==='workspaces'&&<><div className="member-grid">{spaces.map(s=><article key={s.id} className="member-card"><h2>{s.full_name||'بيانات قديمة غير مُطالَب بها'}</h2><code>{s.id}</code><p>{s.state}</p><button onClick={()=>onOpen(s.id,s.full_name||'مساحة قديمة')}>فتح إداري</button></article>)}</div>
      <section className="account-subpanel"><h2>إسناد مساحة قديمة</h2><p>يلزم عضو متحقق ومساحة عضو فارغة؛ لا تُستبدل مساحة تحتوي عملًا.</p><label className="account-field"><span>المساحة غير المُطالَب بها</span><select aria-label="المساحة غير المُطالَب بها" value={claimSpace} onChange={e=>setClaimSpace(e.target.value)}><option value="">اختر</option>{spaces.filter(s=>s.state==='unclaimed').map(s=><option key={s.id} value={s.id}>{s.id}</option>)}</select></label><label className="account-field"><span>العضو المستفيد</span><select aria-label="العضو المستفيد" value={claimUser} onChange={e=>setClaimUser(e.target.value)}><option value="">اختر</option>{rows.filter(r=>r.email_verified_at&&r.state==='active').map(r=><option value={r.id} key={r.id}>{r.full_name} — {r.email}</option>)}</select></label><button disabled={!claimSpace||!claimUser||busy} className="button primary" onClick={()=>{if(window.confirm('تأكيد إسناد ملكية هذه المساحة للعضو المحدد؟'))act(async()=>{await api('/admin/legacy/assign',{method:'POST',body:JSON.stringify({workspace_id:claimSpace,user_id:claimUser})});setMessage('أُسندت الملكية وسُجلت العملية.');});}}>إسناد الملكية</button></section>
    </>}
    {tab==='grants'&&<><h2>منح مورد محدد</h2><p>المنح لا ينسخ محاضرة ولا يكشف باقي مساحة مالكها. واجهات المشاركة الكاملة تأتي لاحقًا.</p>
      <form onSubmit={e=>{e.preventDefault();act(async()=>{await api('/admin/grants',{method:'POST',body:JSON.stringify({user_id:grantUser,workspace_id:grantWorkspace,resource_kind:grantKind,resource_id:resource,permissions:grantActions})});setMessage('حُفظ المنح وأُبطلت جلسات المستفيد لتحديث صلاحياته.');});}}>
        <label className="account-field"><span>المستفيد</span><select aria-label="المستفيد" required value={grantUser} onChange={e=>setGrantUser(e.target.value)}><option value="">اختر</option>{rows.map(r=><option key={r.id} value={r.id}>{r.full_name}</option>)}</select></label>
        <label className="account-field"><span>المساحة المالكة للمورد</span><select aria-label="المساحة المالكة للمورد" required value={grantWorkspace} onChange={e=>setGrantWorkspace(e.target.value)}><option value="">اختر</option>{spaces.map(s=><option key={s.id} value={s.id}>{s.full_name||s.id}</option>)}</select></label>
        <label className="account-field"><span>نوع المورد</span><select aria-label="نوع المورد" value={grantKind} onChange={e=>setGrantKind(e.target.value)}><option value="lecture">محاضرة</option><option value="course">مادة</option></select></label>
        <label className="account-field"><span>المورد</span><select aria-label="المورد" required value={resource} onChange={e=>setResource(e.target.value)}><option value="">اختر من المساحة المحددة</option>{grantResources.map(r=><option key={r.id} value={r.id}>{r.name||r.title}</option>)}</select></label><fieldset><legend>الإجراءات المسموح بها على هذا المورد</legend>{catalog.filter(p=>!p.future).map(p=><label key={p.name} className="account-check"><input type="checkbox" checked={grantActions.includes(p.name)} onChange={e=>setGrantActions(e.target.checked?[...grantActions,p.name]:grantActions.filter(n=>n!==p.name))}/>{p.label}</label>)}</fieldset><button disabled={busy||!resource||!grantActions.length} className="button primary">منح الوصول</button>
      </form><h2>المنح الحالية</h2>{grants.map(g=><p key={g.id}><code>{g.resource_id}</code> — {rows.find(r=>r.id===g.user_id)?.full_name||g.user_id} — {g.revoked_at?'مسحوب':g.permissions.join('، ')} {!g.revoked_at&&<button disabled={busy} onClick={()=>{if(window.confirm('تأكيد سحب المنح؟'))act(()=>api('/admin/grants/'+g.id,{method:'DELETE'}));}}>سحب</button>}</p>)}</>}
    {tab==='audit'&&<><button onClick={()=>api<any[]>('/admin/audit').then(setAudit).catch(e=>setError(e.message))}>تحديث السجل</button><div className="permission-table"><table><thead><tr><th>الوقت</th><th>الفاعل</th><th>العملية</th><th>الهدف</th><th>المساحة</th><th>النتيجة</th></tr></thead><tbody>{audit.map(r=><tr key={r.id}><td>{new Date(r.created_at).toLocaleString('ar')}</td><td>{rows.find(m=>m.id===r.actor_id)?.full_name||r.actor_id||'عملية حساب عامة'}</td><td>{r.action}</td><td>{r.target}</td><td>{r.workspace_id}</td><td>{r.outcome}</td></tr>)}</tbody></table></div>{audit.length>0&&<button onClick={()=>api<any[]>('/admin/audit?before='+audit[audit.length-1].id).then(m=>setAudit([...audit,...m])).catch(e=>setError(e.message))}>تحميل الأقدم</button>}</>}
  </section>;
}

function TrashPage(){
  const [rows,setRows]=useState<any[]>([]),[error,setError]=useState(''),[message,setMessage]=useState('');
  const load=()=>api<any[]>('/trash').then(setRows);useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  return <section className="account-panel"><h1>المحذوفات القابلة للاستعادة</h1><Notice error={error} message={message}/>{rows.map(r=><article key={r.id} className="member-card"><b>{r.kind}</b> — <code>{r.resource_id}</code><p>مهلة الاستعادة: {new Date(r.expires_at).toLocaleString('ar')}</p>{r.restored_at?<p>مستعاد</p>:<button onClick={async()=>{try{if(!window.confirm('استعادة المورد بمعرّفاته الأصلية؟'))return;setMessage((await api('/trash/'+r.id+'/restore',{method:'POST'})).message);await load();}catch(e){setError((e as Error).message);}}}>استعادة</button>}</article>)}</section>;
}

export function AccountRoot({Editor}:{Editor:React.ComponentType}){
  const [enabled,setEnabled]=useState<boolean|null>(null),[me,setMe]=useState<Me|null>(null),[page,setPage]=useState('login'),[pending,setPending]=useState<Pending>(null),[workspace,setWorkspace]=useState(''),[label,setLabel]=useState('مساحتي'),[error,setError]=useState(''),[logoutDialog,setLogoutDialog]=useState(false);
  const refresh=async()=>{const m=await api<Me>('/auth/me');setError('');setMe(m);setWorkspace(m.workspace_id);configureSession(m.csrf,m.workspace_id);setPage(pending&&['bootstrap','admin_recovery'].includes(pending.kind)?pending.kind:'studio');};
  useEffect(()=>{
    const readLink=()=>{
      const hash=window.location.hash.slice(1),eq=hash.indexOf('='),kind=hash.slice(0,eq);
      if(eq<1||!['verify','reset','bootstrap','admin_recovery'].includes(kind))return '';
      try{setPending({kind,token:decodeURIComponent(hash.slice(eq+1))});setPage(kind);setError('');
        if(['verify','reset'].includes(kind)){setMe(null);configureSession('','');}
      }catch{setError('رابط غير صالح؛ اطلب رسالة جديدة.');setPage('login');}
      history.replaceState(null,'',location.pathname);return kind;
    };
    const initialLink=readLink();window.addEventListener('hashchange',readLink);
    api<{enabled:boolean}>('/auth/status').then(async status=>{setEnabled(status.enabled);if(status.enabled&&!['verify','reset'].includes(initialLink)){try{const m=await api<Me>('/auth/me');setMe(m);setWorkspace(m.workspace_id);configureSession(m.csrf,m.workspace_id);if(!initialLink)setPage('studio');}catch{}}}).catch(e=>setError(e.message));
    const expired=()=>{setMe(null);setPage('login');configureSession('','');setError('انتهت الجلسة؛ المسودات محفوظة لحسابك في هذا المتصفح. سجّل الدخول مجددًا.');};window.addEventListener('ct-session-expired',expired);return()=>{window.removeEventListener('ct-session-expired',expired);window.removeEventListener('hashchange',readLink);};
  },[]);
  const storage=useMemo(()=>privateStorage(me?userPrefix(me.id)+workspace+':':''),[me?.id,workspace]);
  const clear=()=>{if(me)clearUserStorage(me.id);setMe(null);setPage('login');configureSession('','');};
  const logout=async(exportDrafts=false)=>{try{if(exportDrafts&&me){const url=URL.createObjectURL(new Blob([JSON.stringify(userDrafts(me.id),null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='CtrlTea_local_drafts.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}await api('/auth/logout',{method:'POST'});clear();setLogoutDialog(false);}catch(e){setError((e as Error).message);}};
  if(enabled===false)return <Editor/>;
  if(enabled===null)return <main className="account-welcome"><p role="status">{error||'جارٍ الاتصال بـCtrl+Tea…'}</p></main>;
  if(!me){const authPage=['bootstrap','admin_recovery'].includes(page)?'login':page;return <><Notice error={error} message=""/>{['bootstrap','admin_recovery'].includes(page)&&<p className="invite-banner">سجّل الدخول بالحساب المتحقق منه المرتبط بدعوة الإدارة، ثم أكمل تفعيلها.</p>}<AuthForm page={authPage} pending={pending} onPage={setPage} onLogin={refresh}/></>;}
  return <div className="account-shell" dir="rtl"><header className="account-topbar"><a href="#" onClick={e=>{e.preventDefault();setPage('studio');}}><img src="/ct-logo.png" alt=""/><b>Ctrl+Tea</b></a><span>{me.full_name} <small>دور النظام: {me.role}</small></span><nav>{[['studio','المحاضرات'],['profile','بروفايلي'],['settings','إعدادات الحساب'],['directory','دليل الفريق'],['trash','المحذوفات']].map(([k,l])=><button key={k} className={page===k?'selected':''} onClick={()=>setPage(k)}>{l}</button>)}{me.role==='SuperAdmin'&&<button onClick={()=>setPage('admin')}>إدارة المنصة</button>}<button onClick={()=>{if(Object.keys(userDrafts(me.id)).length)setLogoutDialog(true);else logout();}}>خروج</button></nav></header>
    {workspace!==me.workspace_id&&<aside className="admin-workspace-banner" role="status">أنت تعمل بصلاحية Super Admin داخل مساحة: <strong>{label}</strong><code>{workspace}</code><button onClick={()=>{setWorkspace(me.workspace_id);configureSession(me.csrf,me.workspace_id);setLabel('مساحتي');setPage('admin');}}>العودة إلى إدارة المنصة</button></aside>}
    <Notice error={error} message=""/>
    {['bootstrap','admin_recovery'].includes(page)?<section className="account-panel"><h1>{labels[page]}</h1><p>هذه الدعوة مرتبطة ببريدك المتحقق منه وتُستخدم مرة واحدة.</p><button className="button primary" onClick={async()=>{try{const r=await api('/auth/bootstrap/accept',{method:'POST',body:JSON.stringify({token:pending?.token||''})});setError(r.message);setPending(null);setMe(null);setPage('login');configureSession('','');}catch(e){setError((e as Error).message);}}}>تأكيد تفعيل صلاحية المسؤول العام</button></section>:page==='studio'?<WorkspaceStorage.Provider value={storage}><Editor key={me.id+workspace}/></WorkspaceStorage.Provider>:page==='profile'?<ProfilePage/>:page==='settings'?<Settings me={me} onLogout={()=>{setMe(null);setPage('login');configureSession('','');setError('أُنهِيت الجلسة؛ تبقى مسوداتك الخاصة لهذا الحساب حتى تدخل مجددًا.');}} onRefresh={refresh}/>:page==='directory'?<Directory/>:page==='trash'?<TrashPage/>:page==='admin'&&me.role==='SuperAdmin'?<Admin onOpen={(id,name)=>{if(id!==workspace&&Object.keys(userDrafts(me.id)).length&&!window.confirm('المسودات محفوظة محليًا لكل مساحة. الانتقال إلى المساحة الإدارية المحددة؟'))return;setWorkspace(id);setLabel(name);configureSession(me.csrf,id);setPage('studio');}}/>:null}
    {logoutDialog&&<div className="modal-backdrop"><section className="account-card" role="dialog" aria-modal="true" aria-labelledby="logout-title"><h2 id="logout-title">مسودات محلية قبل الخروج</h2><p>ستُمسح بيانات الحساب المحلية عند الخروج. يمكنك تنزيل نسخة من مسوداتك أولًا.</p><button className="button primary" onClick={()=>logout(true)}>تنزيل النسخة والخروج</button><button className="button danger" onClick={()=>logout(false)}>الخروج وحذف المسودات المحلية</button><button className="button secondary" onClick={()=>setLogoutDialog(false)}>إلغاء</button></section></div>}
  </div>;
}
