// [Static path contract](../specs/06_静态发布与文档.md).
export const siteURL=path=>new URL(String(path).replace(/^\/+/,''),new URL('./',location.href)).href;
export function rewriteSiteLinks(root){
  for(const a of root.querySelectorAll('a[href^="/"]')){
    const href=a.getAttribute('href');
    if(!href.startsWith('//')) a.href=siteURL(href);
  }
}
