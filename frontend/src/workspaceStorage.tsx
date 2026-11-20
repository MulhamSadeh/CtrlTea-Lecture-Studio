import React from "react";
export function privateStorage(prefix:string){
  return {getItem:(key:string)=>localStorage.getItem(prefix+key),setItem:(key:string,value:string)=>localStorage.setItem(prefix+key,value),removeItem:(key:string)=>localStorage.removeItem(prefix+key)};
}
export const WorkspaceStorage=React.createContext(privateStorage(""));
export function userPrefix(id:string){return "ct-private:"+window.location.origin+":"+id+":";}
export function clearUserStorage(id:string){const prefix=userPrefix(id);for(const key of Object.keys(localStorage))if(key.startsWith(prefix))localStorage.removeItem(key);}
export function userDrafts(id:string){const prefix=userPrefix(id);return Object.fromEntries(Object.keys(localStorage).filter(key=>key.startsWith(prefix)&&(key.includes("ct-draft-")||key.includes("ct-source-"))).map(key=>[key,localStorage.getItem(key)]));}
