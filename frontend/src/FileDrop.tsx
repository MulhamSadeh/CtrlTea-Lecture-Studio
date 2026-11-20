import React, {useRef, useState} from "react";
import {Upload} from "lucide-react";

export function FileDrop({accept, multiple=false, disabled=false, title, hint, onFiles}: {
  accept:string; multiple?:boolean; disabled?:boolean; title:string; hint?:string;
  onFiles:(files:File[])=>void|Promise<unknown>;
}) {
  const input=useRef<HTMLInputElement>(null), depth=useRef(0);
  const [dragging,setDragging]=useState(false), [error,setError]=useState("");
  const receive=(files:File[])=>{
    if(disabled || !files.length)return;
    const extensions=accept.split(",").map(value=>value.trim().toLowerCase());
    if(!multiple && files.length>1){setError("أسقط ملفًا واحدًا في هذه المساحة.");return;}
    const invalid=files.filter(file=>!extensions.some(extension=>file.name.toLowerCase().endsWith(extension)));
    if(invalid.length){setError("صيغة ملف غير مدعومة: "+invalid.map(file=>file.name).join("، "));return;}
    setError("");
    Promise.resolve(onFiles(files)).catch(error=>setError((error as Error).message));
  };
  return <div className="file-drop-wrap">
    <label className={"file-drop "+(dragging?"dragging ":"")+(disabled?"disabled":"")}
      role="button" tabIndex={disabled?-1:0} aria-disabled={disabled} aria-label={title}
      onKeyDown={event=>{if(!disabled && ["Enter"," "].includes(event.key)){event.preventDefault();input.current?.click();}}}
      onDragEnter={event=>{event.preventDefault();event.stopPropagation();if(!disabled){depth.current++;setDragging(true);}}}
      onDragOver={event=>{event.preventDefault();event.stopPropagation();event.dataTransfer.dropEffect=disabled?"none":"copy";}}
      onDragLeave={event=>{event.preventDefault();event.stopPropagation();depth.current=Math.max(0,depth.current-1);if(!depth.current)setDragging(false);}}
      onDrop={event=>{event.preventDefault();event.stopPropagation();depth.current=0;setDragging(false);receive(Array.from(event.dataTransfer.files));}}>
      <Upload size={22}/><strong>{title}</strong><small>{hint || "اسحب الملفات وأفلتها هنا، أو انقر لاختيارها"}</small>
      <input ref={input} type="file" accept={accept} multiple={multiple} hidden disabled={disabled}
        onChange={event=>{receive(Array.from(event.target.files||[]));event.target.value="";}}/>
    </label>
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
