import React, {useEffect, useState} from "react";
import {Download, X} from "lucide-react";
import {api, download} from "./api";
import {Course, Lecture} from "./types";
import {FileDrop} from "./FileDrop";

type Preview={bundle_id:string;file_name:string;course:{name:string;doctor:string};
  lectures:{id:string;title:string;revision:number;sections:number;sources:number}[];sources:number;scope:string};

export function Transfers({courses, currentCourse, saveNow, onDone, onClose, act}: {
  courses:Course[];currentCourse:string;saveNow:()=>Promise<boolean>;
  onDone:(result:any)=>Promise<void>;onClose:()=>void;act:(fn:()=>Promise<any>)=>Promise<any>;
}) {
  const [tab,setTab]=useState("import"),[busy,setBusy]=useState(false);
  const [preview,setPreview]=useState<Preview|null>(null),[incoming,setIncoming]=useState<string[]>([]);
  const [destination,setDestination]=useState(currentCourse),[destinationLectures,setDestinationLectures]=useState<Lecture[]>([]),
    [targetLecture,setTargetLecture]=useState(""),[mode,setMode]=useState("new");
  const [exportCourse,setExportCourse]=useState(currentCourse||courses[0]?.id||""),
    [exportLectures,setExportLectures]=useState<Lecture[]>([]),[chosen,setChosen]=useState<string[]>([]),[scope,setScope]=useState("all");
  useEffect(()=>{
    let active=true;setTargetLecture("");setDestinationLectures([]);
    if(destination)act(async()=>{const rows=await api<Lecture[]>("/courses/"+destination+"/lectures");if(active)setDestinationLectures(rows);});
    return ()=>{active=false;};
  },[destination]);
  useEffect(()=>{
    let active=true;setChosen([]);setExportLectures([]);
    if(exportCourse)act(async()=>{const rows=await api<Lecture[]>("/courses/"+exportCourse+"/lectures");if(active)setExportLectures(rows);});
    return ()=>{active=false;};
  },[exportCourse]);
  const toggle=(list:string[],id:string)=>list.includes(id)?list.filter(value=>value!==id):[...list,id];
  return <div className="modal-backdrop" onMouseDown={()=>{if(!busy)onClose();}}>
    <section className="modal wide transfer-dialog" role="dialog" aria-modal="true" aria-labelledby="transfer-title" onMouseDown={e=>e.stopPropagation()}>
      <button className="modal-close icon-button" aria-label="إغلاق تبادل البيانات" disabled={busy} onClick={onClose}><X size={19}/></button>
      <h2 id="transfer-title">تبادل بيانات المواد والمحاضرات</h2>
      <p>أرسل حزمة ZIP للمطلوب فقط. تنقل المحتوى والمصادر وتصحيح النصوص وإعدادات المحاضرة، دون ملف قاعدة البيانات.</p>
      <div className="segmented"><button disabled={busy} className={tab==="import"?"active":""} onClick={()=>setTab("import")}>إضافة بيانات واردة</button>
        <button disabled={busy} className={tab==="export"?"active":""} onClick={()=>setTab("export")}>استخراج بيانات</button></div>
      {tab==="export"?<div className="transfer-content">
        <label className="field"><span>المادة المراد استخراجها</span><select disabled={busy} value={exportCourse} onChange={e=>setExportCourse(e.target.value)}>
          <option value="">اختر المادة</option>{courses.map(course=><option value={course.id} key={course.id}>{course.name}</option>)}</select></label>
        <label className="field"><span>نطاق الحزمة</span><select disabled={busy} value={scope} onChange={e=>setScope(e.target.value)}>
          <option value="all">المادة كاملة بجميع محاضراتها</option><option value="selected">محاضرة أو عدة محاضرات أحددها</option></select></label>
        {scope==="selected" && <div className="transfer-selection">
          <button className="text-button" disabled={busy} onClick={()=>setChosen(chosen.length===exportLectures.length?[]:exportLectures.map(l=>l.id))}>تحديد الكل / إلغاء التحديد</button>
          {exportLectures.map(lecture=><label className="checkbox" key={lecture.id}><input type="checkbox" disabled={busy} checked={chosen.includes(lecture.id)} onChange={()=>setChosen(toggle(chosen,lecture.id))}/>{lecture.title}</label>)}
          {!exportLectures.length && <p className="hint">لا توجد محاضرات بهذه المادة.</p>}
        </div>}
        <p className="hint">تتضمن الحزمة المصادر الأصلية، OCR وتصحيحاته واستثناءاته، الرسومات القابلة لإعادة التوليد، سجل التعديلات ومهام التأليف. يمكن إعادة توليد ملفات Word وPDF على الجهاز المستقبل. انتظر انتهاء رفع الملفات واستخراج نصوصها قبل التصدير.</p>
        <button className="button primary" disabled={busy||!exportCourse||(scope==="selected"&&!chosen.length)} onClick={()=>act(async()=>{
          setBusy(true);try{if(!(await saveNow()))return;await download("/courses/"+exportCourse+"/bundle",scope==="all"?"CtrlTea_Course_Data.zip":"CtrlTea_Lectures_Data.zip",scope==="selected"?{lecture_ids:chosen}:undefined);}finally{setBusy(false);}
        })}><Download size={17}/>{busy?"جارٍ تجهيز الحزمة…":"تنزيل حزمة البيانات"}</button>
      </div>:<div className="transfer-content">
        <FileDrop accept=".zip" disabled={busy} title={busy?"جارٍ قراءة الحزمة…":"أسقط حزمة البيانات هنا"} hint="حزمة ZIP مصدّرة من Ctrl+Tea — حتى 220 MB، أو انقر لاختيارها" onFiles={files=>act(async()=>{
          setBusy(true);setPreview(null);try{const form=new FormData();form.append("file",files[0]);const result=await api<Preview>("/transfers/preview",{method:"POST",body:form});
            setPreview(result);setIncoming(result.lectures.map(lecture=>lecture.id));setMode("new");}finally{setBusy(false);}
        })}/>
        {preview && <>
          <div className="transfer-summary"><strong>{preview.course.name}</strong><span>{preview.lectures.length} محاضرات · {preview.sources} مصادر</span></div>
          <p className="hint">المعاينة لا تضيف شيئًا إلى المحاضرات. اختر ما تريد ثم اضغط إضافة البيانات.</p>
          <div className="transfer-selection">
            <button className="text-button" disabled={busy} onClick={()=>setIncoming(incoming.length===preview.lectures.length?[]:preview.lectures.map(l=>l.id))}>تحديد الكل / إلغاء التحديد</button>
            {preview.lectures.map(lecture=><label className="checkbox" key={lecture.id}><input type="checkbox" disabled={busy} checked={incoming.includes(lecture.id)} onChange={()=>setIncoming(toggle(incoming,lecture.id))}/>
              <span>{lecture.title}<small>{lecture.sections} أقسام · {lecture.sources} مصادر</small></span></label>)}
          </div>
          <label className="field"><span>طريقة الإضافة</span><select disabled={busy} value={mode} onChange={e=>setMode(e.target.value)}>
            <option value="new">إضافة محاضرات جديدة دون استبدال الموجود</option><option value="append" disabled={incoming.length!==1}>إضافة أقسام محاضرة واحدة إلى محاضرة موجودة</option></select></label>
          <label className="field"><span>المادة الوجهة</span><select disabled={busy} value={destination} onChange={e=>setDestination(e.target.value)}>
            <option value="">إنشاء مادة جديدة باسم المادة الواردة</option>{courses.map(course=><option value={course.id} key={course.id}>{course.name}</option>)}</select></label>
          {mode==="append" && <>
            <label className="field"><span>المحاضرة التي ستضاف إليها الأقسام</span><select disabled={busy||!destination} value={targetLecture} onChange={e=>setTargetLecture(e.target.value)}>
              <option value="">اختر محاضرة موجودة</option>{destinationLectures.map(lecture=><option value={lecture.id} key={lecture.id}>{lecture.title}</option>)}</select></label>
            <p className="hint">تضاف الأقسام إلى نهاية المحاضرة مع مصادرها، وتبقى أقسامك وإعداداتك وسجلك السابق. لا يدمج سجل تعديلات المحاضرة الواردة أو مهام تأليفها في هذه الطريقة.</p>
          </>}
          <button className="button primary" disabled={busy||!incoming.length||(mode==="append"&&(incoming.length!==1||!targetLecture))} onClick={()=>act(async()=>{
            setBusy(true);try{if(!(await saveNow()))return;
              const latest=mode==="append"?await api<Lecture>("/lectures/"+targetLecture):null;
              const result=await api("/transfers/import",{method:"POST",body:JSON.stringify({bundle_id:preview.bundle_id,lecture_ids:incoming,
                target_course_id:mode==="new"?(destination||null):null,target_lecture_id:mode==="append"?targetLecture:null,expected_revision:latest?.revision??null})});
              await onDone(result);onClose();
            }finally{setBusy(false);}
          })}>{busy?"جارٍ إضافة البيانات…":"إضافة البيانات المحددة"}</button>
        </>}
      </div>}
    </section>
  </div>;
}
