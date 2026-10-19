// [GitHub review storage](../../data/human-review/README.md).
import {PEOPLE,assignment,units,validateReview,datasetKey} from './review-model.js';
export const REPOSITORY='DingHouqin/bridgeqa-zh';
export const REPOSITORY_URL='https://github.com/'+REPOSITORY;
export function reviewDirectory(bundle){return 'data/human-review/'+bundle.id+'/'+bundle.version+'-'+bundle.review_fingerprint;}
export function encodeJSON(value){const bytes=new TextEncoder().encode(JSON.stringify(value,null,2)+'\n');let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(text);}
export const decodeJSON=value=>JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value.replace(/\s/g,'')),c=>c.charCodeAt(0))));
export function createGithubStore(bundle,{fetcher=fetch,getToken=()=>''}={}){
  const round=datasetKey(bundle),plan=assignment(bundle.records),rows=new Map(bundle.records.map(row=>[row.id,row]));
  let queue=Promise.resolve();
  async function api(path,options={}){
    const token=getToken();
    const response=await fetcher('https://api.github.com'+path,{...options,cache:'no-store',headers:{Accept:'application/vnd.github+json',...(token?{Authorization:'Bearer '+token}:{}),...(options.body?{'Content-Type':'application/json'}:{})},signal:AbortSignal.timeout(20000)});
    let data;try{data=await response.json();}catch{throw new Error('GitHub返回了无法识别的响应（HTTP '+response.status+'）');}
    if(!response.ok){const error=new Error(response.status===401?'GitHub授权无效或已过期，请重新连接':response.status===403?(response.headers.get('x-ratelimit-remaining')==='0'?'GitHub读取额度已用完，请连接GitHub或稍后重试':'GitHub拒绝写入，请检查协作者权限和Token权限'):response.status===404?'找不到GitHub审查文件或没有访问权限':data.message||'GitHub请求失败（HTTP '+response.status+'）');error.status=response.status;throw error;}
    return data;
  }
  async function readPerson(person){
    const path='/repos/'+REPOSITORY+'/contents/'+reviewDirectory(bundle)+'/'+person+'.json';
    const file=await api(path+'?ref=main');const value=decodeJSON(file.content);
    if(value.format!=='bridgeqa-github-review-v1'||value.round!==round||value.person!==person||!value.records)throw new Error('GitHub审查文件与当前题库不一致');
    for(const [id,entry] of Object.entries(value.records)){
      const row=rows.get(id);if(!row||plan[id]!==person||!Number.isSafeInteger(entry.revision)||entry.revision<1)throw new Error('GitHub审查记录不合法');
      entry.value=validateReview(entry.value,person,units(row).map(u=>u.key));
    }
    return {path,sha:file.sha,value};
  }
  async function read(){
    const files=await Promise.all(PEOPLE.map(readPerson)),members={},records={};
    for(const {value} of files){if(value.member)members[value.person]=value.member;Object.assign(records,value.records);}
    return {round,members,records};
  }
  async function writeNow(endpoint,body){
    if(!getToken())throw new Error('评价已保留在本机；请先在页面连接GitHub，才能上传');
    const match=endpoint.match(/^\/(members|records)\/([^/]+)$/);if(!match)throw new Error('保存路径不合法');
    const [,kind,id]=match,person=kind==='members'?id:plan[id];if(!PEOPLE.includes(person))throw new Error('负责人或题号未登记');
    const value=kind==='records'?validateReview(body.value,person,units(rows.get(id)).map(u=>u.key)):{initials:body.value.initials};
    if(kind==='members'&&!/^[a-zA-Z]{1,12}$/.test(value.initials))throw new Error('姓名简写请输入1–12位英文字母');
    for(let attempt=0;attempt<3;attempt++){
      const file=await readPerson(person),current=kind==='members'?file.value.member:file.value.records[id];
      if((current?.revision||0)!==body.expectedRevision){const e=new Error('该评价已在GitHub更新，请选择保留哪份');e.conflict=true;e.current=current||null;throw e;}
      const entry={value,revision:body.expectedRevision+1,updatedAt:new Date().toISOString()};
      if(kind==='members')file.value.member=entry;else file.value.records[id]=entry;
      try{
        await api(file.path,{method:'PUT',body:JSON.stringify({message:'review: '+person+' '+(kind==='members'?'署名':id+' '+value.status),branch:'main',sha:file.sha,content:encodeJSON(file.value)})});return entry;
      }catch(e){if(![409,422].includes(e.status)||attempt===2)throw e;}
    }
  }
  const write=(path,body)=>{const task=queue.then(()=>writeNow(path,body));queue=task.catch(()=>{});return task;};
  async function authorize(){
    const user=await api('/user');const repo=await api('/repos/'+REPOSITORY);
    if(!repo.permissions?.push)throw new Error('该GitHub账号没有仓库写入权限，请先请仓库所有者添加为协作者');
    return user.login;
  }
  return {read,write,authorize};
}
