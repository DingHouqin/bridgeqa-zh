"""[Static publishing contract](specs/06_静态发布与文档.md), [run instructions](README.md)."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from server import APP, PROJECT, REGISTRY, load_bundle

def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n', encoding='utf-8')

def export(destination):
    destination=destination.resolve()
    workspace=(PROJECT/'workspace').resolve()
    if not destination.is_relative_to(workspace) or destination==workspace:
        raise ValueError('发布物只能写入workspace的专用子目录')
    if destination.exists() and any(destination.iterdir()) and not (destination/'.bridgeqa-export').is_file():
        raise ValueError('拒绝覆盖非本导出器创建的目录')
    if destination.is_symlink():
        raise ValueError('拒绝符号链接发布目录')
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    (destination/'.bridgeqa-export').write_text('generated\n',encoding='utf-8')
    shutil.copytree(APP/'web',destination,dirs_exist_ok=True)
    manifest=json.loads((APP/'web/documents.json').read_text(encoding='utf-8'))
    hashes={}
    for name in manifest['files']:
        source=(PROJECT/name).resolve()
        if not source.is_relative_to(PROJECT) or source.is_relative_to(workspace) or '.git' in source.parts or not source.is_file():
            raise ValueError('未允许的发布资料：'+name)
        target=destination/'files'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    for doc in manifest['documents']:
        if doc['source'] not in hashes:
            raise ValueError('文档不在发布清单：'+doc['source'])
    json_write(destination/'api/datasets.json',[{'id':key,'title':entry['title'],'topic':entry['topic']} for key,entry in REGISTRY.items()])
    for key in REGISTRY:
        json_write(destination/'api/datasets'/key/'bundle.json',load_bundle(key))
    (destination/'.nojekyll').touch()
    json_write(destination/'build.json',{'format_version':1,'revision':os.environ.get('GITHUB_SHA','local-working-copy'),'datasets':list(REGISTRY),'documents':len(manifest['documents']),'source_sha256':hashes})
    print(json.dumps({'output':str(destination),'datasets':len(REGISTRY),'documents':len(manifest['documents']),'files':len(hashes)},ensure_ascii=False))
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=PROJECT/'workspace/pages')
    export(parser.parse_args().output)
