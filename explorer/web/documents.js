// [Document routing and publication](../specs/06_静态发布与文档.md).
import {siteURL} from './urls.js';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let catalog;
const cache=new Map();
export async function loadDocuments(){
  if(!catalog){const r=await fetch(siteURL('documents.json'));if(!r.ok)throw Error('文档目录读取失败');catalog=await r.json();}
  return catalog;
}
export const documentRoute=(slug,section='')=>'#/docs/'+slug+(section?'?section='+encodeURIComponent(section):'');
function sourcePath(source,target){
  const decoded=decodeURIComponent(target);
  return new URL(decoded,'https://source.invalid/'+source).pathname.slice(1);
}
export async function renderDocument(slug){
  const c=await loadDocuments(),entry=c.documents.find(d=>d.slug===slug);
  if(!entry)return {title:'章节未找到',html:'<section class="panel"><h2>章节未找到</h2><p>请从文档目录选择已登记的章节。</p><a href="'+documentRoute('index')+'">返回文档首页</a></section>'};
  if(!cache.has(entry.source)){
    const r=await fetch(siteURL('files/'+entry.source));if(!r.ok)throw Error('文档读取失败');cache.set(entry.source,await r.text());
  }
  if(!window.markdownit)throw Error('Markdown渲染器未加载');
  const md=window.markdownit({html:false,linkify:false}),headings=[],used=new Map();
  md.renderer.rules.heading_open=(tokens,i,options,env,self)=>{
    const label=tokens[i+1]?.content||'章节';
    const base=label.toLowerCase().replace(/[^\p{L}\p{N}_\-\s]/gu,'').trim().replace(/\s+/g,'-')||'section';
    const n=used.get(base)||0;used.set(base,n+1);const id=base+(n?'-'+n:'');
    tokens[i].attrSet('id',id);headings.push({id,label,level:Number(tokens[i].tag.slice(1))});return self.renderToken(tokens,i,options);
  };
  const box=document.createElement('div');box.innerHTML=md.render(cache.get(entry.source));
  for(const a of box.querySelectorAll('a[href]')){
    const href=a.getAttribute('href');
    if(/^(https?:|mailto:)/i.test(href)){a.target='_blank';a.rel='noopener';continue;}
    if(/^[a-z][\w+.-]*:/i.test(href)){a.replaceWith(document.createTextNode(a.textContent+'（仅限对应应用打开）'));continue;}
    const [target,fragment='']=href.split('#');
    if(!target){a.href=documentRoute(entry.slug,decodeURIComponent(fragment));continue;}
    const source=sourcePath(entry.source,target),linked=c.documents.find(d=>d.source===source||d.source===source.replace(/\/$/,'')+'/README.md');
    if(linked)a.href=documentRoute(linked.slug,decodeURIComponent(fragment));
    else if(c.files.includes(source))a.href=siteURL('files/'+source);
    else {a.href=c.repository_url+(source.endsWith('/')||!source.split('/').at(-1).includes('.')?'/tree/main/':'/blob/main/')+source.split('/').map(encodeURIComponent).join('/');a.target='_blank';a.rel='noopener';}
  }
  for(const img of box.querySelectorAll('img[src]')){
    const src=img.getAttribute('src');if(!/^https?:\/\//i.test(src))img.src=siteURL('files/'+sourcePath(entry.source,src));
  }
  const groups=[...new Set(c.documents.map(d=>d.group))];
  const menu=groups.map(g=>'<h3>'+esc(g)+'</h3>'+c.documents.filter(d=>d.group===g).map(d=>'<a '+(d.slug===slug?'aria-current="page"':'')+' href="'+documentRoute(d.slug)+'">'+esc(d.title)+'</a>').join('')).join('');
  const toc=headings.filter(x=>x.level>1&&x.level<4).map(x=>'<a href="'+documentRoute(slug,x.id)+'">'+esc(x.label)+'</a>').join('');
  return {title:entry.title,html:'<div class="docs-layout"><aside class="panel docs-menu"><h2>文档目录</h2>'+menu+'</aside><section class="panel docs-content"><div class="section-heading"><span class="badge">'+esc(entry.group)+'</span><a href="'+siteURL('files/'+entry.source)+'" target="_blank" rel="noopener">Markdown 原文 ↗</a></div>'+(toc?'<nav class="docs-toc" aria-label="本章目录">'+toc+'</nav>':'')+'<article class="markdown-body">'+box.innerHTML+'</article></section></div>'};
}
