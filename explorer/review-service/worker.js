// [Synchronization contract](../specs/08_临时人工审查.md).
import {PEOPLE,validateReview} from './review-model.js';
import {ROUND,PLAN} from './plan.js';
const ORIGINS=new Set(['https://dinghouqin.github.io','http://127.0.0.1:8766','http://localhost:8766']);
const cors=request=>({...(ORIGINS.has(request.headers.get('Origin'))?{'Access-Control-Allow-Origin':request.headers.get('Origin'),'Vary':'Origin'}:{}),
  'Access-Control-Allow-Methods':'GET,PUT,OPTIONS','Access-Control-Allow-Headers':'Content-Type','Cache-Control':'no-store'});
const json=(request,value,status=200)=>Response.json(value,{status,headers:cors(request)});
const entry=row=>row?{value:JSON.parse(row.value),revision:row.revision,updatedAt:row.updated_at}:null;
async function read(db,kind,id){return entry(await db.prepare('SELECT value,revision,updated_at FROM review_entries WHERE round=? AND kind=? AND id=?').bind(ROUND,kind,id).first());}
export default {async fetch(request,env){
  const url=new URL(request.url);
  if(!url.pathname.startsWith('/api/review'))return new Response('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>BridgeQA 审查同步服务</title><body><p>此服务为现有网站的05人工审查提供共享记录。</p><a href="https://dinghouqin.github.io/bridgeqa-zh/#/review">进入05人工审查</a></body></html>',{headers:{'Content-Type':'text/html;charset=utf-8'}});
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors(request)});
  if(url.searchParams.get('round')!==ROUND)return json(request,{error:'题库版本不一致，请刷新网页；旧审查记录不会覆盖新题库'},409);
  try{
    if(!env.DB)throw new Error('Missing DB binding');
    if(request.method==='GET'&&url.pathname==='/api/review'){
      const data=await env.DB.prepare('SELECT kind,id,value,revision,updated_at FROM review_entries WHERE round=?').bind(ROUND).all();
      const members={},records={};for(const row of data.results)(row.kind==='members'?members:records)[row.id]=entry(row);
      return json(request,{round:ROUND,members,records});
    }
    const match=url.pathname.match(/^\/api\/review\/(members|records)\/([^/]+)$/);
    if(!match||request.method!=='PUT')return json(request,{error:'接口不存在'},404);
    const [,kind,rawId]=match,id=decodeURIComponent(rawId);
    if(kind==='members'?!PEOPLE.includes(id):!Object.hasOwn(PLAN,id))return json(request,{error:'负责人或题号未登记'},400);
    if(Number(request.headers.get('Content-Length'))>150000)return json(request,{error:'评价内容过长'},413);
    const raw=await request.text();if(raw.length>150000)return json(request,{error:'评价内容过长'},413);
    let body,value;
    try{body=JSON.parse(raw);if(!Number.isSafeInteger(body.expectedRevision)||body.expectedRevision<0)throw new Error('版本字段不合法');
      if(kind==='members'){if(!/^[a-zA-Z]{1,12}$/.test(body.value?.initials))throw new Error('姓名简写请输入1–12位英文字母');value={initials:body.value.initials};}
      else value=validateReview(body.value,PLAN[id].owner,PLAN[id].units);
    }catch(e){return json(request,{error:e.message||'评价格式不合法'},400);}
    const current=await read(env.DB,kind,id);
    if((current?.revision||0)!==body.expectedRevision)return json(request,{error:'记录已在另一设备更新',current},409);
    const updatedAt=new Date().toISOString();
    const result=await env.DB.prepare('INSERT INTO review_entries (round,kind,id,value,revision,updated_at) VALUES (?,?,?,?,1,?) ON CONFLICT(round,kind,id) DO UPDATE SET value=excluded.value,revision=review_entries.revision+1,updated_at=excluded.updated_at WHERE review_entries.revision=?')
      .bind(ROUND,kind,id,JSON.stringify(value),updatedAt,body.expectedRevision).run();
    if(!result.meta.changes)return json(request,{error:'记录已在另一设备更新',current:await read(env.DB,kind,id)},409);
    return json(request,{value,revision:body.expectedRevision+1,updatedAt});
  }catch(e){console.error('Review database operation failed',e.message);return json(request,{error:'共享存储暂时不可用；请保留输入并稍后重试'},503);}
}};
