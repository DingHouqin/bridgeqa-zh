// [Shared review workflow](../specs/08_临时人工审查.md).
import {PEOPLE,TOPICS,assignment,units,datasetKey,blankReview,completionErrors,validateReview} from './review-model.js';
export {PEOPLE,TOPICS,assignment,units};
import {createGithubStore,REPOSITORY_URL} from './github-review-store.js';
export {REPOSITORY_URL};
let store,githubToken='',githubLogin='',lastPoll=0;
let plan={},round='',records={},members={},connected=false,notice='正在连接共享审查记录…',listener=()=>{},pending=new Map(),conflict=null;
const timers=new Map();
let lastSyncedAt=null,localError='',resumePending=false;
const cacheKey=()=> 'bridgeqa-review-cache-v1:'+round;
function checkpoint(){
  try{localStorage.setItem(cacheKey(),JSON.stringify({round,records,members,unsaved:[...pending.keys()],lastSyncedAt}));localError='';}
  catch{localError='本机备份失败，请立即导出记录，并保持页面开启。';}
}
function restoreCache(rows){
  try{
    const saved=JSON.parse(localStorage.getItem(cacheKey())||'null');if(!saved||saved.round!==round)return;
    const byId=new Map(rows.map(row=>[row.id,row]));
    for(const [id,entry] of Object.entries(saved.records||{})){
      const row=byId.get(id);if(!row||!Number.isSafeInteger(entry.revision)||entry.revision<0)continue;
      const value=validateReview(entry.value,plan[id],units(row).map(u=>u.key));records[id]={...entry,value};
      if(saved.unsaved?.includes(id)){pending.set(id,{row,value});feedback.set(id,{state:'error',message:'已恢复本机草稿，尚未上传；联网后将重试，冲突时由你选择版本。'});}
    }
    members=saved.members||{};lastSyncedAt=saved.lastSyncedAt||null;resumePending=pending.size>0;
    notice='已读取本机备份，正在读取GitHub记录…';
  }catch{localError='无法读取本机备份，请保留已有导出文件。';}
}
const feedback=new Map();
export const reviewFeedback=id=>feedback.get(id)||{state:'idle',message:'填写评价后可完成审查；也可随时保存为草稿。'};
const report=(id,state,message)=>{feedback.set(id,{state,message});listener();};
export function setupReview(bundle,onUpdate){
  const next=datasetKey(bundle);listener=onUpdate;
  if(round===next)return;
  for(const timer of timers.values())clearTimeout(timer);timers.clear();pending.clear();conflict=null;
  plan=assignment(bundle.records);round=next;records={};members={};connected=false;feedback.clear();lastSyncedAt=null;localError='';resumePending=false;
  store=createGithubStore(bundle,{getToken:()=>githubToken});lastPoll=0;
  rowsById=new Map(bundle.records.map(row=>[row.id,row]));
  restoreCache(bundle.records);
  refreshReview();
}
async function request(path='',options={}){
  return options.body?store.write(path,JSON.parse(options.body)):store.read();
}
export async function refreshReview(){
  lastPoll=Date.now();
  try{const data=await request();if(data.round!==round||!data.members||!data.records)throw new Error('共享记录响应不完整');
    for(const [id,entry] of Object.entries(data.members)){if(entry.revision>=(members[id]?.revision||0))members[id]=entry;}
    for(const [id,entry] of Object.entries(data.records)){if(!pending.has(id)&&entry.revision>=(records[id]?.revision||0))records[id]=entry;}
    connected=true;lastSyncedAt=new Date().toISOString();checkpoint();if(!conflict)notice=pending.size?'GitHub记录已读取，'+pending.size+'题待上传；'+(githubLogin?'可点击同步重试保存':'请连接GitHub后上传'):githubLogin?'GitHub记录已同步 · 每15秒更新进度':'GitHub记录已同步 · 未授权时每3分钟刷新，连接后可保存';
  }catch(e){connected=false;notice='无法同步：'+e.message+'。'+(lastSyncedAt?'当前显示本机备份；尚未上传的评价不计入共享进度。':'共享进度尚未读取，不能据此判断记录是否丢失。');}
  listener();
  if(connected&&resumePending&&githubToken){resumePending=false;for(const id of [...pending.keys()])await flushReview(id);}
}
setInterval(()=>{if(round&&!document.hidden&&Date.now()-lastPoll>=(githubToken?15000:180000))refreshReview();},5000);
export const reviewConnection=()=>({connected,notice:notice+(localError?' '+localError:''),conflict,pending:pending.size,lastSyncedAt,githubLogin});
export async function connectGithub(token){
  githubToken=token.trim();githubLogin='';
  if(!githubToken){notice='请填入你自己的GitHub Token';listener();return false;}
  try{githubLogin=await store.authorize();notice='已连接GitHub账号 '+githubLogin;await refreshReview();await retrySaves();return true;}
  catch(e){githubToken='';notice='GitHub连接失败：'+e.message;listener();return false;}
}
export function disconnectGithub(){githubToken='';githubLogin='';notice='已断开GitHub写入授权，本机草稿保留';listener();}
export const initialsFor=person=>members[person]?.value.initials||'';
export const reviewFor=row=>records[row.id]?.value||blankReview(row,plan[row.id]);
export const reviewOwner=id=>plan[id];
export const reviewStatus=id=>pending.has(id)?'draft':records[id]?.value.status||(lastSyncedAt?'todo':'unknown');
export function progressFor(rows,person){const own=rows.filter(r=>plan[r.id]===person);return {known:Boolean(lastSyncedAt),total:own.length,complete:own.filter(r=>reviewStatus(r.id)==='complete').length,draft:own.filter(r=>reviewStatus(r.id)==='draft').length};}
export async function saveInitials(person,initials){
  if(!/^[a-zA-Z]{1,12}$/.test(initials)){notice='姓名简写请输入1–12位英文字母，例如 abc';listener();return false;}
  try{const entry=await request('/members/'+person,{method:'PUT',body:JSON.stringify({expectedRevision:members[person]?.revision||0,value:{initials}})});members[person]=entry;checkpoint();notice=person+' 的姓名简写已同步';listener();return true;}
  catch(e){await refreshReview();notice=e.conflict?'姓名简写刚被其他设备修改，已刷新，请核对后重新填写':e.message;listener();return false;}
}
export function updateReview(row,mutate){
  const review=structuredClone(reviewFor(row));mutate(review);review.initials=initialsFor(plan[row.id])||review.initials;review.status='draft';
  const revision=records[row.id]?.revision||0;records[row.id]={value:review,revision};pending.set(row.id,{row,value:review});
  checkpoint();
  notice='正在保存草稿…';feedback.set(row.id,{state:'saving',message:'正在保存草稿…'});clearTimeout(timers.get(row.id));timers.set(row.id,setTimeout(()=>flushReview(row.id),2500));
  listener();
}
const saving=new Map();
export async function flushReview(id){
  clearTimeout(timers.get(id));
  if(saving.has(id)){const ok=await saving.get(id);if(!ok)return false;if(pending.has(id)&&!conflict)return flushReview(id);return !pending.has(id);}
  const item=pending.get(id);if(!item)return true;if(conflict?.id===id)return false;
  const value=structuredClone(item.value),revision=records[id]?.revision||0;
  if(reviewFeedback(id).state!=='invalid')report(id,'saving',value.status==='complete'?'正在提交本题审查…':'正在保存草稿…');
  const operation=(async()=>{
    try{const entry=await request('/records/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({expectedRevision:revision,value})});
      if(pending.get(id)?.value===item.value){records[id]=entry;pending.delete(id);}else records[id].revision=entry.revision;
      connected=true;checkpoint();notice=pending.size?'仍有草稿等待保存…':'已保存到GitHub仓库';
      if(!pending.has(id)&&reviewFeedback(id).state!=='invalid')feedback.set(id,{state:'success',message:value.status==='complete'?'本题审查已完成，已保存到GitHub并计入共享进度。':'草稿已保存到GitHub，可刷新或稍后继续。'});
      return true;
    }catch(e){checkpoint();notice=e.conflict?'该题已被其他设备修改；你的输入已保留，请选择保留哪份':('保存失败：'+e.message+'；'+(localError?'本机备份也未成功，请立即导出':'已保留在本机，尚未上传；可重试或导出'));
      feedback.set(id,{state:'error',message:notice});if(e.conflict)conflict={id,remote:e.current};else if(e.status!==401&&e.status!==403&&githubToken)connected=false;return false;
    }finally{saving.delete(id);listener();}
  })();saving.set(id,operation);return operation;
}
export async function finishReview(row){
  const value=structuredClone(reviewFor(row));value.initials=initialsFor(plan[row.id])||value.initials;
  const errors=completionErrors(value,units(row).map(u=>u.key));
  if(errors.length){notice=errors.map(error=>{for(const u of units(row))error=error.replace(u.key,u.label);return error;}).join('；');report(row.id,'invalid',notice);return false;}
  value.status='complete';feedback.delete(row.id);records[row.id]={value,revision:records[row.id]?.revision||0};pending.set(row.id,{row,value});checkpoint();return flushReview(row.id);
}
export async function saveDraft(row){updateReview(row,()=>{});return flushReview(row.id);}
export async function retrySaves(){for(const id of pending.keys())await flushReview(id);await refreshReview();}
export async function resolveConflict(useLocal){if(!conflict)return;const {id,remote}=conflict;conflict=null;
  if(useLocal){records[id].revision=remote?.revision||0;checkpoint();await flushReview(id);}else{pending.delete(id);if(remote)records[id]=remote;else delete records[id];checkpoint();notice='已采用其他设备保存的版本';report(id,'success',notice);}}
export function exportReview(){
  if(!Object.keys(records).length){notice='当前没有可导出的审查记录'+(lastSyncedAt?'。':'，共享服务尚未读取成功；空文件不能作为备份。');listener();return null;}
  return {format:'bridgeqa-human-review-v1',round,assignments:plan,members,records,unsaved:[...pending.keys()],lastSyncedAt,exportedAt:new Date().toISOString()};
}
export async function importReview(snapshot){
  if(snapshot?.format!=='bridgeqa-human-review-v1'||snapshot.round!==round||!snapshot.records)throw new Error('请选择同一题库导出的审查JSON文件');
  await refreshReview();if(!connected)throw new Error('请先成功读取GitHub记录，再导入，避免覆盖已有评价');
  const accepted=[],skipped=[];
  // Validate everything before staging any imported entry.
  for(const [id,entry] of Object.entries(snapshot.records)){
    if(!plan[id])throw new Error('导入文件包含未知题号：'+id);
    const row=rowsById.get(id),value=validateReview(entry.value,plan[id],units(row).map(u=>u.key));
    if(records[id]){if(JSON.stringify(records[id].value)!==JSON.stringify(value))skipped.push(id);continue;}
    accepted.push({row,value});
  }
  for(const item of accepted){const id=item.row.id;records[id]={value:item.value,revision:0};pending.set(id,item);}
  checkpoint();notice='已导入 '+accepted.length+' 题到本机，等待上传到GitHub。'+(skipped.length?'以下题目已有不同评价，保留原版：'+skipped.join('、'):'');listener();
  return {added:accepted.length,skipped};
}
let rowsById=new Map();
window.addEventListener('beforeunload',e=>{if(pending.size){e.preventDefault();e.returnValue='';}});
