"""Approved, read-only, static relation hints. See QA_Generator implementation docs.

No facts, materials, gold or solver requests are modified by this module.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVAL = 'QA_Generator/resources/relationship-libraries/approval.json'
SNAPSHOT = 'data/source-candidates/hongloumeng_relations/2026-10-21'
SCOPES = {'C01': 'candidate_match_omission_and_conflict_hints_only',
          'C02': 'additional_conflict_hints_only_with_known_errors_flagged'}
FILES = {'C01': 'lemon_kg/files/红楼梦人物关系.csv', 'C02': 'kgqa_hlm/files/raw_data/relation.txt'}
COMMITS = {'C01': 'c78453ed53bed482f63191ea67f6c2a80c6a3106',
           'C02': '8f772c491c65e70904dc0feaaa8479ff2df2faa3'}
POLICY = ('Only static comparison hints. Source evidence and scope take precedence; '
          'absence is not false. Do not fill facts, gold or deleted support. '
          'No inference of father/mother from son/daughter. No access for Blind Solver. '
          'Independence, source scope and temporal validity are not established.')


def load_approved_libraries(root=ROOT):
    root = Path(root).resolve()
    approval_bytes = (root / APPROVAL).read_bytes()
    approval = json.loads(approval_bytes)
    if approval['user_approval'] != 'approved' or not approval['generator_integration_enabled']:
        raise ValueError('Explicit library approval required')
    if approval['solver_access_allowed'] or approval['gold_enrichment_allowed']:
        raise ValueError('External-library isolation policy violated')
    enabled = [row for row in approval['candidates'] if row['enabled']]
    if len({r['id'] for r in enabled}) != len(enabled):
        raise ValueError('Duplicate approved library ID')
    libraries = []
    for row in enabled:
        key = row['id']
        if key not in SCOPES or row['approval'] != 'approved' or row.get('approved_scope') != SCOPES[key]:
            raise ValueError('Unapproved candidate or scope')
        if row['commit'] != COMMITS[key] or row['approved_file'] != FILES[key]:
            raise ValueError('Approved snapshot identity changed')
        raw = (root / SNAPSHOT / FILES[key]).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != row['approved_sha256']:
            raise ValueError('Approved relation file SHA-256 mismatch')
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        parsed = []
        for number, values in enumerate(rows, 1):
            if key == 'C01' and number == 1:
                if values != ['head', 'tail', 'relation', 'label']:
                    raise ValueError('Unexpected CSV header')
                continue
            if not values:
                continue
            if len(values) != (4 if key == 'C01' else 5) or not all(values):
                raise ValueError('Unexpected relation row')
            a, b, label = values[:3]
            if label in ('father', '父亲', 'mother', '母亲'):
                parent, child = a, b
                role = 'father' if label in ('father', '父亲') else 'mother'
            elif label in ('son', 'daughter', '儿子', '女儿'):
                parent, child, role = b, a, 'parent'
            else:
                continue
            parsed.append({'parent': parent, 'child': child, 'parent_role': role,
                           'source_row': number, 'raw': values,
                           'known_issue': key == 'C02' and (parent, child) == ('贾珍', '贾惜春')})
        libraries.append({'id': key, 'commit': row['commit'], 'scope': SCOPES[key],
                          'sha256': sha, 'records': parsed})
    if not libraries:
        raise ValueError('No approved libraries enabled')
    return {'approval_sha256': hashlib.sha256(approval_bytes).hexdigest(), 'libraries': libraries}


def compare_origin(origin, bundle, track='source'):
    """Compare exact unambiguous primary names only; produce hints, never a verdict."""
    report = {'version': 'external-relation-hints-v0.1', 'policy': POLICY,
              'approval_sha256': bundle['approval_sha256'], 'track': track,
              'libraries': [{k: v for k, v in lib.items() if k != 'records'} for lib in bundle['libraries']],
              'facts': [], 'potential_omissions': [], 'known_library_issues': [],
              'auto_accept': False, 'gold_modified': False}
    if track != 'source':
        report['status'] = 'not_comparable_non_source_track'
        return report
    entities = {e['id']: e for e in origin['entities']}
    # A primary name colliding with another entity's alias is also ambiguous.
    owners = collections.defaultdict(set)
    for entity in origin['entities']:
        for name in [entity['name']] + entity.get('aliases', []):
            owners[name].add(entity['id'])
    safe_names = {e['name'] for e in origin['entities'] if len(owners[e['name']]) == 1}
    known_pairs = {(entities[f['parent']]['name'], entities[f['child']]['name']) for f in origin['facts']}
    seen_issues = set()
    for f in origin['facts']:
        parent, child = entities[f['parent']]['name'], entities[f['child']]['name']
        item = {'fact_id': f['id'], 'parent': parent, 'child': child, 'parent_role': f['parent_role'],
                'local_scope': f['scope'], 'scope_and_time_verified': False, 'comparisons': []}
        temporal = any(f.get(k) is not None for k in ('time', 'valid_from', 'valid_to', 'validity', 'event_id', 'stage', 'conditions', 'temporal_scope'))
        for lib in bundle['libraries']:
            result = {'library': lib['id'], 'matches': [], 'conflict_hints': [], 'known_issue_rows': []}
            if parent not in safe_names or child not in safe_names or temporal:
                result['status'] = 'not_comparable_temporal_or_ambiguous_identity'
                item['comparisons'].append(result)
                continue
            for record in lib['records']:
                if record['child'] != child:
                    continue
                if record['known_issue']:
                    result['known_issue_rows'].append(record['source_row'])
                    marker = (lib['id'], record['source_row'])
                    if marker not in seen_issues:
                        report['known_library_issues'].append({'library': lib['id'], **record, 'excluded_from_comparison': True})
                        seen_issues.add(marker)
                    continue
                same_parent = record['parent'] == parent
                same_role = record['parent_role'] == f['parent_role']
                if same_parent and (same_role or record['parent_role'] == 'parent' or f['parent_role'] == 'parent'):
                    if lib['id'] == 'C01':
                        result['matches'].append({**record, 'role_verified': same_role, 'static_hint_only': True})
                elif ((same_role and f['parent_role'] != 'parent') or (same_parent and record['parent_role'] != 'parent' and f['parent_role'] != 'parent')):
                    result['conflict_hints'].append({**record, 'reason': 'possible_parent_or_role_difference_recheck_source'})
            result['status'] = ('conflict_hint' if result['conflict_hints'] else
                                'static_compatible_hint' if result['matches'] else
                                'conflict_hints_only_none_found' if lib['id'] == 'C02' else 'not_covered')
            item['comparisons'].append(result)
        report['facts'].append(item)
    # C01 omission hints are bounded to already extracted, unambiguous named entities.
    # They do not assert that the provided excerpts contain the relation.
    if not any(any(f.get(k) is not None for k in ('time', 'valid_from', 'valid_to', 'validity', 'event_id', 'stage', 'conditions', 'temporal_scope')) for f in origin['facts']):
        seen = set()
        for lib in bundle['libraries']:
            if lib['id'] != 'C01':
                continue
            for r in lib['records']:
                pair = (r['parent'], r['child'])
                if pair not in known_pairs and pair not in seen and all(n in safe_names for n in pair):
                    report['potential_omissions'].append({'library': 'C01', **r, 'requires_local_source_evidence': True})
                    seen.add(pair)
    report['status'] = 'advisory_only'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--facts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare_origin(json.loads(args.facts.read_text(encoding='utf-8')), load_approved_libraries())
    # Audit output must be new; preserve frozen experimental records.
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
