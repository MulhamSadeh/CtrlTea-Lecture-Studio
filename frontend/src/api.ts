export type ValidationIssue={location:string;message:string;diagnostic?:string;path?:(string|number)[]};
let csrfToken="",workspace="";
export function configureSession(csrf:string,wid:string){csrfToken=csrf;workspace=wid;}
export function apiURL(path:string){
  const url=new URL(path.startsWith("/api/")?path:"/api"+path,window.location.origin);
  if(workspace)url.searchParams.set("workspace",workspace);
  return url.pathname+url.search;
}
export class ApiError extends Error{
  constructor(message:string,public errors:ValidationIssue[]=[],public status=0){super(message);}
}
export async function apiRaw(path:string,options:RequestInit={}){
  const headers=new Headers(options.headers);
  if(!(options.body instanceof FormData)&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  if(csrfToken)headers.set("X-CSRF-Token",csrfToken);
  if(workspace&&!headers.has("X-Ctrltea-Workspace"))headers.set("X-Ctrltea-Workspace",workspace);
  const response=await fetch(path.startsWith("/api/")?path:"/api"+path,{...options,headers,credentials:"same-origin"});
  if(!response.ok){
    let data:any={};try{data=await response.json();}catch{}
    const detail=Array.isArray(data.detail)?data.detail.map((x:any)=>`${x.loc?.slice(1).join(" / ")}: ${x.msg}`).join("\n"):data.detail;
    if(response.status===401&&csrfToken&&!path.endsWith("/auth/login"))window.dispatchEvent(new Event("ct-session-expired"));
    throw new ApiError(data.message||detail||"تعذر الاتصال بالتطبيق",data.errors||[],response.status);
  }
  return response;
}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{return (await apiRaw(path,options)).json();}
export async function download(path:string,name:string,body?:unknown){
  const response=await apiRaw(path,body===undefined?{}:{method:"POST",body:JSON.stringify(body)});
  const url=URL.createObjectURL(await response.blob());const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),15000);
}
