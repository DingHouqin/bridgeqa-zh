"""S1.4 fixed build-run path preflight, before any output mutation.

Input: run path/project root. Output: frozen canonical run directory or
ValueError. Protects existing identities; no claim about malicious concurrent
filesystem changes after preflight. Owner: S1.4.
"""
import os
import stat
from itertools import combinations
from pathlib import Path
from .validation import require

MAIN_FILES=('inputs.jsonl','predictions.jsonl','score.json','oracle-inputs.jsonl','oracle-reference.json','oracle-predictions.jsonl','oracle-score.json','run-manifest.json','state.json')
CONTROLLED_FILES=('inputs.jsonl','reference.json','predictions.jsonl','score.json','audit.json','run-manifest.json')
WEB_FILES=('index.html','app.js','styles.css','framework.svg','state.js')
BUILD_FILES=MAIN_FILES+tuple('controlled/'+name for name in CONTROLLED_FILES)+tuple('web/'+name for name in WEB_FILES)
CACHES={'.git','.venv','__pycache__','.pytest_cache','.ruff_cache','private','.local'}


def necessary_sources(root):
    """File identities of fixed inputs and the code/schema surfaces read by runs."""
    paths=[]
    for folder in ('data/pilot','data/controlled','docs/plan/draft/source-snapshots','resources/opencc','examples/v0.2'):
        paths.extend(p for p in (root/folder).rglob('*') if p.is_file())
    paths.extend((root/'src/bridgeqa').rglob('*.py'))
    paths.extend((root/'scripts').glob('*.py'))
    paths.extend((root/'schemas').rglob('*.json'))
    paths.extend(root/'web'/name for name in WEB_FILES if name!='state.js')
    paths.extend(root/name for name in ('README.md','AGENTS.md','pyproject.toml','uv.lock','.gitattributes','configs/midterm.json'))
    return [p for p in paths if p.is_file()]


def check_build_output(output,root):
    """One preflight for all 20 main/Oracle/controlled/state/web write targets."""
    root=Path(root).resolve();lexical=Path(output)
    if not lexical.is_absolute():lexical=Path.cwd()/lexical
    require(lexical!=root and lexical not in root.parents,'build output must not be project root or ancestor')
    try:relative=lexical.relative_to(root)
    except ValueError:relative=None
    if relative is not None:require(relative.parts and relative.parts[0]=='artifacts','build output inside protected project namespace')
    require(not CACHES.intersection(lexical.parts),'build output inside private/runtime namespace')
    targets=[lexical/name for name in BUILD_FILES]
    for target in targets:
        for item in (target,*target.parents):
            try:info=item.lstat()
            except FileNotFoundError:continue
            require(not (stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024)),'build output target or ancestor is a link/reparse point')
            if item==target:
                require(stat.S_ISREG(info.st_mode),'build output target must be a regular file')
                require(info.st_nlink==1,'build output target must have exactly one link')
            else:require(stat.S_ISDIR(info.st_mode),'build output ancestor must be a directory')
    canonical=lexical.resolve()
    require(canonical!=root and canonical not in root.parents,'build output conflicts with project root or ancestor')
    try:relative=canonical.relative_to(root)
    except ValueError:relative=None
    if relative is not None:require(relative.parts and relative.parts[0]=='artifacts','canonical build output inside protected project namespace')
    require(not CACHES.intersection(canonical.parts),'canonical build output inside private/runtime namespace')
    frozen=[p.resolve() for p in targets]
    for left,right in combinations(frozen,2):
        require(left!=right and left not in right.parents and right not in left.parents,'build output targets conflict')
        if left.exists() and right.exists():require(not left.samefile(right),'build output targets alias')
    sources=[(path,path.resolve()) for path in necessary_sources(root)]
    for target in frozen:
        for source,canonical_source in sources:
            require(target!=canonical_source,'build output aliases canonical required source')
            if target.exists():require(not target.samefile(source),'build output aliases required source')
    return canonical
