import React, { useState, useEffect } from "react";
import type { ControlSpec } from "./types";

export const initialControl = (): ControlSpec => ({
  nodes: [
    { id: "u", kind: "input", x: 100, y: 200, math: "u(t)" },
    { id: "g", kind: "block", x: 400, y: 200, math: "G(s)" },
    { id: "y", kind: "output", x: 700, y: 200, math: "y(t)" },
  ],
  edges: [
    { start: "u", end: "g", start_port: "right", end_port: "left", sign: "", bends: [] },
    { start: "g", end: "y", start_port: "right", end_port: "left", sign: "", bends: [] },
  ],
});
const ports = ["left", "right", "top", "bottom", "lower_left", "lower_right"] as const;
const portNames = ["يسار", "يمين", "أعلى", "أسفل", "أسفل يسار الجامع", "أسفل يمين الجامع"];
function Bends({ value, onChange }: { value: {x:number;y:number}[]; onChange: (v:{x:number;y:number}[])=>void }) {
  const raw=JSON.stringify(value);
  const [text,setText]=useState(value.map(p=>`${p.x},${p.y}`).join("; "));
  const [error,setError]=useState("");
  useEffect(()=>{setText(value.map(p=>`${p.x},${p.y}`).join("; "));setError("");},[raw]);
  return <label className="field"><span>نقاط انعطاف المسار (x,y; x,y)</span><input dir="ltr" value={text} onChange={e=>setText(e.target.value)} onBlur={()=>{
    const pairs=text.trim()?text.split(";").map(s=>s.split(",").map(v=>v.trim())):[];
    if(pairs.some(p=>p.length!==2||p.some(v=>!v||!Number.isFinite(Number(v))||Number(v)<0||Number(v)>1000))) {setError("أدخل إحداثيين بين 0 و1000 لكل نقطة");return;}
    setError("");onChange(pairs.map(p=>({x:Number(p[0]),y:Number(p[1])})));
  }}/>{error&&<span role="alert">{error}</span>}</label>;
}
export function ControlDiagramEditor({spec,onChange}:{spec:ControlSpec;onChange:(s:ControlSpec)=>void}) {
  const node=(i:number,patch:Partial<ControlSpec["nodes"][number]>)=>onChange({...spec,nodes:spec.nodes.map((n,j)=>j===i?{...n,...patch}:n)});
  const edge=(i:number,patch:Partial<ControlSpec["edges"][number]>)=>onChange({...spec,edges:spec.edges.map((n,j)=>j===i?{...n,...patch}:n)});
  return <div className="subpanel"><p>راجع إشارات كل مدخل واتجاه الأسهم في المعاينة. التفرعات عقد مستقلة، والمسارات متعامدة دون تقاطعات.</p>
    {spec.nodes.map((n,i)=><details key={i}><summary>العقدة {n.id} · {n.kind}</summary><div className="form-grid">
      <label className="field"><span>المعرف</span><input dir="ltr" value={n.id} onChange={e=>node(i,{id:e.target.value})}/></label>
      <label className="field"><span>النوع</span><select value={n.kind} onChange={e=>node(i,{kind:e.target.value as typeof n.kind})}>{["input","output","block","sum","branch"].map((k,j)=><option key={k} value={k}>{["دخل","خرج","كتلة","جامع ×","تفرع"][j]}</option>)}</select></label>
      {(["x","y","width","height"] as const).map(k=><label className="field" key={k}><span>{({x:"الموضع الأفقي",y:"الموضع العمودي",width:"العرض",height:"الارتفاع"})[k]}</span><input type="number" value={n[k]??(k==="width"?100:80)} onChange={e=>node(i,{[k]:Number(e.target.value)})}/></label>)}
      <label className="field"><span>تسمية خارجية</span><input value={n.tag??""} onChange={e=>node(i,{tag:e.target.value})}/></label>
      <label className="field"><span>تسمية نصية</span><input value={n.label??""} onChange={e=>node(i,{label:e.target.value,math:""})}/></label>
      <label className="field"><span>تسمية رياضية (مثال: {"\\frac{2}{s}"})</span><input dir="ltr" value={n.math??""} onChange={e=>node(i,{math:e.target.value,label:""})}/></label>
      <button type="button" onClick={()=>onChange({...spec,nodes:spec.nodes.filter((_,j)=>j!==i)})}>حذف العقدة</button>
    </div></details>)}
    <button type="button" onClick={()=>{let id="n";while(spec.nodes.some(n=>n.id===id))id+="1";onChange({...spec,nodes:[...spec.nodes,{id,kind:"block",x:400,y:400,math:"G(s)"}]});}}>إضافة عقدة</button>
    {spec.edges.map((e,i)=><details key={i}><summary>التوصيل من {e.start} إلى {e.end}</summary><div className="form-grid">
      {(["start","end"] as const).map(k=><label className="field" key={k}><span>{k==="start"?"من العقدة":"إلى العقدة"}</span><select value={e[k]} onChange={v=>edge(i,{[k]:v.target.value})}>{spec.nodes.map(n=><option key={n.id} value={n.id}>{n.id}</option>)}</select></label>)}
      {(["start_port","end_port"] as const).map(k=><label className="field" key={k}><span>{k==="start_port"?"منفذ البداية":"منفذ النهاية"}</span><select value={e[k]} onChange={v=>edge(i,{[k]:v.target.value})}>{ports.map((p,j)=><option key={p} value={p}>{portNames[j]}</option>)}</select></label>)}
      <label className="field"><span>إشارة مدخل الجامع</span><select value={e.sign??""} onChange={v=>edge(i,{sign:v.target.value as "+"|"-"|""})}><option value="">لا توجد</option><option value="+">+</option><option value="-">−</option></select></label>
      <Bends value={e.bends??[]} onChange={bends=>edge(i,{bends})}/>
      <button type="button" onClick={()=>onChange({...spec,edges:spec.edges.filter((_,j)=>j!==i)})}>حذف التوصيل</button>
    </div></details>)}
    <button type="button" disabled={spec.nodes.length<2} onClick={()=>onChange({...spec,edges:[...spec.edges,{start:spec.nodes[0].id,end:spec.nodes[1].id,start_port:"right",end_port:"left",sign:"",bends:[]}]})}>إضافة توصيل</button>
  </div>;
}
