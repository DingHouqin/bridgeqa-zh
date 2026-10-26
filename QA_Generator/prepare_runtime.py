"""Prepare checked-in seed material; see [quick start](START_HERE.md).

No model calls. Optional downloads are limited to the two previously approved,
commit-pinned relation hints and are verified against the existing approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / 'data/multi_agent_runtime_v0'
TARGET = ROOT / 'workspace/hongloumeng-modernization-trial/resolved-validation'
RELATIONS = ROOT / 'data/source-candidates/hongloumeng_relations/2026-10-21'
APPROVAL = ROOT / 'QA_Generator/resources/relationship-libraries/approval.json'
SOURCES = {
    'C01': ('lemonhhh/-Dream-of-the-Red-Chamber-Knowledge', 'lemon_kg/files/红楼梦人物关系.csv', '红楼梦人物关系.csv'),
    'C02': ('chizhu/KGQA_HLM', 'kgqa_hlm/files/raw_data/relation.txt', 'raw_data/relation.txt'),
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def save_identical(path, raw):
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Output must remain inside this checkout')
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Existing file differs; preserve it and use a separate checkout: '+str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)

def prepare(download=False):
    # Existing offline regression tests own temporary children of this folder.
    (ROOT/'workspace/relation-library-audit').mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SEEDS/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['sha256'].items():
        if name not in ('P01.modern.json','P02.modern.json','gpt_review.json'):
            raise ValueError('Unknown seed file')
        raw = (SEEDS/name).read_bytes()
        if sha(raw) != expected:
            raise ValueError('Seed hash mismatch: '+name)
        save_identical(TARGET/name, raw)
    approval = json.loads(APPROVAL.read_text(encoding='utf-8'))
    if approval['user_approval'] != 'approved' or not approval['generator_integration_enabled']:
        raise ValueError('Previously approved relation integration is not enabled')
    missing = []
    for entry in approval['candidates']:
        if not entry['enabled']:
            continue
        repository, local, remote = SOURCES[entry['id']]
        if entry['repository'] != repository or entry['approved_file'] != local or entry['approval'] != 'approved':
            raise ValueError('Relation approval differs from the pinned allowed source')
        path = (RELATIONS/local).resolve()
        if not path.is_relative_to(RELATIONS.resolve()):
            raise ValueError('Relation path escaped allowed directory')
        if path.exists():
            raw = path.read_bytes()
        elif download:
            url = 'https://raw.githubusercontent.com/'+repository+'/'+entry['commit']+'/'+urllib.parse.quote(remote, safe='/')
            with urllib.request.urlopen(url, timeout=45) as response:
                raw = response.read(5_000_001)
            if len(raw)>5_000_000:
                raise ValueError('Relation snapshot exceeds expected bound')
        else:
            missing.append(entry['id'])
            continue
        if sha(raw) != entry['approved_sha256']:
            raise ValueError('Relation SHA-256 mismatch: '+entry['id'])
        save_identical(path,raw)
    return {'material_seed_files':3,'missing_relation_snapshots':missing,'generation_inputs_ready':not missing,'model_calls':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Prepare frozen seed inputs without calling any model.')
    parser.add_argument('--download-approved-relations',action='store_true',help='Download only approved C01/C02 commit-pinned files and verify their hashes.')
    result=prepare(parser.parse_args().download_approved_relations)
    print(json.dumps(result,ensure_ascii=False))
