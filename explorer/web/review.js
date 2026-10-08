// [Shared review workflow](../specs/08_临时人工审查.md).
import {PEOPLE,TOPICS,assignment,units,datasetKey,blankReview,completionErrors} from './review-model.js';
export {PEOPLE,TOPICS,assignment,units};
const API='https://bridgeqa-human-review.spryox2.chatgpt.site/api/review';
let plan={},round='',records={},members={},connected=false,notice='正在连接共享审查记录…',listener=()=>{},pending=new Map(),conflict=null;
const timers=new Map();
export function setupReview(bundle,onUpdate){
  const next=datasetKey(bundle);listener=onUpdate;
  if(round===next)return;
  plan=assignment(bundle.records);round=next;records={};members={};connected=false;
  refreshReview();
}
async function request(path='',options={}){
  const response=await fetch(API+path+(path.includes('?')?'&':'?')+'round='+encodeURIComponent(round),{...options,cache:'no-store',headers:{'Content-Type':'application/json',...options.headers},signal:AbortSignal.timeout(15000)});
  const data=await response.json();
  if(!response.ok){const error=new Error(data.error||'共享存储暂时不可用');error.status=response.status;error.current=data.current;error.conflict=response.status===409&&Object.hasOwn(data,'current');throw error;}
  return data;
}
export async function refreshReview(){
  try{const data=await request();for(const [id,entry] of Object.entries(data.members)){if(entry.revision>=(members[id]?.revision||0))members[id]=entry;}
    for(const [id,entry] of Object.entries(data.records)){if(!pending.has(id)&&entry.revision>=(records[id]?.revision||0))records[id]=entry;}
    connected=true;if(!pending.size&&!conflict)notice='共享记录已同步 · 每5秒更新进度';
  }catch(e){connected=false;notice='无法同步：'+e.message+'。输入会保留，请重试保存。';}
  listener();
}
setInterval(()=>{if(round&&!document.hidden)refreshReview();},5000);
export const reviewConnection=()=>({connected,notice,conflict,pending:pending.size});
export const initialsFor=person=>members[person]?.value.initials||'';
export const reviewFor=row=>records[row.id]?.value||blankReview(row,plan[row.id]);
export const reviewOwner=id=>plan[id];
export const reviewStatus=id=>pending.has(id)?'draft':records[id]?.value.status||'todo';
export function progressFor(rows,person){const own=rows.filter(r=>plan[r.id]===person);return {total:own.length,complete:own.filter(r=>reviewStatus(r.id)==='complete').length,draft:own.filter(r=>reviewStatus(r.id)==='draft').length};}
export async function saveInitials(person,initials){
  if(!/^[a-zA-Z]{1,12}$/.test(initials)){notice='姓名简写请输入1–12位英文字母，例如 abc';listener();return false;}
  try{const entry=await request('/members/'+person,{method:'PUT',body:JSON.stringify({expectedRevision:members[person]?.revision||0,value:{initials}})});members[person]=entry;notice=person+' 的姓名简写已同步';listener();return true;}
  catch(e){await refreshReview();notice=e.conflict?'姓名简写刚被其他设备修改，已刷新，请核对后重新填写':e.message;listener();return false;}
}
export function updateReview(row,mutate){
  const review=structuredClone(reviewFor(row));mutate(review);review.initials=initialsFor(plan[row.id]);review.status='draft';
  const revision=records[row.id]?.revision||0;records[row.id]={value:review,revision};pending.set(row.id,{row,value:review});
  notice='正在保存草稿…';clearTimeout(timers.get(row.id));timers.set(row.id,setTimeout(()=>flushReview(row.id),650));
  listener();
}
const saving=new Map();
export async function flushReview(id){
  clearTimeout(timers.get(id));
  if(saving.has(id)){await saving.get(id);if(pending.has(id)&&!conflict)return flushReview(id);return false;}
  const item=pending.get(id);if(!item)return true;if(conflict?.id===id)return false;
  const value=structuredClone(item.value),revision=records[id]?.revision||0;
  const operation=(async()=>{
    try{const entry=await request('/records/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({expectedRevision:revision,value})});
      if(pending.get(id)?.value===item.value){records[id]=entry;pending.delete(id);}else records[id].revision=entry.revision;
      connected=true;notice=pending.size?'仍有草稿等待保存…':'已保存到共享数据库';return true;
    }catch(e){notice=e.conflict?'该题已被其他设备修改；你的输入已保留，请选择保留哪份':('保存失败：'+e.message+'；输入已保留，可重试或导出');
      if(e.conflict)conflict={id,remote:e.current};else connected=false;return false;
    }finally{saving.delete(id);listener();}
  })();saving.set(id,operation);return operation;
}
export async function finishReview(row){
  const value=structuredClone(reviewFor(row));value.initials=initialsFor(plan[row.id]);
  const errors=completionErrors(value,units(row).map(u=>u.key));
  if(errors.length){notice=errors.join('；');listener();return false;}
  value.status='complete';records[row.id]={value,revision:records[row.id]?.revision||0};pending.set(row.id,{row,value});return flushReview(row.id);
}
export async function retrySaves(){for(const id of pending.keys())await flushReview(id);await refreshReview();}
export async function resolveConflict(useLocal){if(!conflict)return;const {id,remote}=conflict;conflict=null;
  if(useLocal){records[id].revision=remote?.revision||0;await flushReview(id);}else{pending.delete(id);if(remote)records[id]=remote;else delete records[id];notice='已采用其他设备保存的版本';listener();}}
export function exportReview(){return {format:'bridgeqa-human-review-v1',round,assignments:plan,members,records,unsaved:[...pending.keys()],exportedAt:new Date().toISOString()};}
window.addEventListener('beforeunload',e=>{if(pending.size){e.preventDefault();e.returnValue='';}});
