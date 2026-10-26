"""Build pending-reference review cases; never seal an independent audit gate.

Inputs and outputs are versioned development snapshots under
workspace/deletion-review-v2; see the module's experiment/review_cases helpers.
"""
import argparse
import collections
import copy
import importlib.util
from pathlib import Path

from experiment import ROOT, digest, read, save_new_or_same
from review_cases import project_review

WORK = ROOT / 'workspace/deletion-review-v2'


def _external_module():
    spec = importlib.util.spec_from_file_location(
        '_approved_external_relations', ROOT / 'src/multi_agent_v0/external_relations.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _variants(family):
    return {v['condition']: v for v in family['variants']}


def _rationale(family):
    return ('构造者说明：本题组合给定材料中逐步明确说明的父母关系，保留各事实陈述范围；'
            '基础题、主要干扰、无关添加及无关删除都应保留原答案和两步证明。'
            '必要支持删除后起点名称仍在，但完整支持链消失，应判证据不足。'
            '候选标注及上述说明均为待审声明，请对照每个成员实际材料独立检查。')


def _ref(family, valid, category='none', evidence=None):
    base = _variants(family)['base']
    return {'expected_verdict': 'pass' if valid else 'revise',
            'status': 'pending', 'independent_review_status': 'pending_independent_gpt',
            'major_defect': not valid, 'severity': 'none' if valid else 'major',
            'defect_category': category, 'track': 'source',
            'reference_author': 'root_GPT_draft_pending_independent_audit',
            'human_review': 'not_run',
            'evidence': evidence or {'condition': 'base', 'answer': base['gold']['answer_ids'],
                                     'proof': base['gold']['proofs'],
                                     'support': family['origin']['facts']}}


def _corrupt(family, index):
    """Only validation copies are mutated; original families remain byte-equivalent."""
    item = copy.deepcopy(family)
    rows = _variants(item)
    base = rows['base']
    original = copy.deepcopy(base['gold'])
    if index < 4:
        if index % 2 == 0:
            # Existing named start is deliberately substituted for its grandparent.
            base['gold']['answer_ids'] = [item['query']['start']]
            category = 'wrong_answer'
        else:
            base['gold'].update(status='insufficient_evidence', answer_ids=[], proofs=[])
            category = 'wrong_status'
        evidence = {'condition': 'base', 'correct_claim': original,
                    'corrupted_claim': copy.deepcopy(base['gold']),
                    'material_locations': [u['unit_id'] for u in base['materials']]}
    elif index < 8:
        # The two real facts are intentionally placed in the wrong proof order.
        base['gold']['proofs'][0]['facts'].reverse()
        category = 'wrong_evidence'
        evidence = {'condition': 'base', 'correct_proof': original['proofs'],
                    'corrupted_proof': copy.deepcopy(base['gold']['proofs']),
                    'reason': '声明事实次序不匹配起点到中间点再到答案的两步证明',
                    'support': item['origin']['facts']}
    else:
        target = rows['necessary_support_deleted_name_retained']
        actual = rows['irrelevant_deleted']
        target['materials'] = copy.deepcopy(actual['materials'])
        target['deletion_log'] = copy.deepcopy(actual['deletion_log'])
        # Deliberately retain the erroneous insufficient-evidence candidate claim.
        category = 'irrelevant_deletion'
        evidence = {'condition': 'necessary_support_deleted_name_retained',
                    'actual_deletion': copy.deepcopy(actual['deletion_log']),
                    'retained_answer_and_proof': copy.deepcopy(actual['gold']),
                    'reason': '只删除无关景物，完整父母链仍在，伪称必要删证'}
    return item, category, evidence


def build(families, synthetic_cases, synthetic_refs):
    if not 10 <= len(families) <= 12:
        raise ValueError('This first-batch builder requires 10–12 independently reviewable source families')
    if len(synthetic_cases) != 24 or len(synthetic_refs) != 24:
        raise ValueError('Expected 12 synthetic positive/negative pairs')
    before = digest(families)
    external = _external_module()
    bundle = external.load_approved_libraries(ROOT)
    cases, refs, mutations = [], {}, []
    edge_clusters, material_clusters = collections.defaultdict(list), collections.defaultdict(list)
    for index, family in enumerate(families):
        fid = family['family_id']
        hints = external.compare_origin(family['origin'], bundle, track='source')
        good_id, bad_id = fid + '-GOOD', fid + '-BAD'
        cases.append({'case_id': good_id, 'family_id': fid, 'track': 'source',
                      'candidate': copy.deepcopy(family), 'rationale': _rationale(family),
                      'external_relation_hints': hints})
        refs[good_id] = _ref(family, True)
        damaged, category, evidence = _corrupt(family, index)
        # Hints only compare the same candidate Origin facts, never candidate gold.
        cases.append({'case_id': bad_id, 'family_id': fid, 'track': 'source',
                      'candidate': damaged, 'rationale': _rationale(family),
                      'external_relation_hints': external.compare_origin(damaged['origin'], bundle, track='source')})
        refs[bad_id] = _ref(family, False, category, evidence)
        mutations.append({'case_id': bad_id, 'parent_case_id': good_id,
                          'category': category, 'changed_candidate_only': True})
        proof_ids = {f for p in _variants(family)['base']['gold']['proofs'] for f in p['facts']}
        for fact in family['origin']['facts']:
            if fact['id'] not in proof_ids:
                continue
            edge_clusters[fact['id']].append(fid)
            for uid in sorted({q['unit_id'] for group in fact['evidence_sets'] for q in group}):
                if fid not in material_clusters[uid]:
                    material_clusters[uid].append(fid)
    if digest(families) != before:
        raise AssertionError('Correct family input was mutated')
    cases.extend(copy.deepcopy(synthetic_cases))
    refs.update(copy.deepcopy(synthetic_refs))
    for ref in refs.values():
        ref['status'] = 'pending'
        ref['independent_review_status'] = 'pending_independent_gpt'
        ref.setdefault('severity', 'major' if ref['major_defect'] else 'none')
        ref.setdefault('human_review', 'not_run')
    if set(refs) != {c['case_id'] for c in cases}:
        raise ValueError('Duplicate IDs or reference coverage mismatch')
    for case in cases:
        for condition in ('A', 'B', 'C'):
            projection = project_review(case, condition)
            if any(k in projection for k in ('reference', 'expected_verdict', 'major_defect')):
                raise AssertionError('Reference leaked into review projection')
    counts = collections.Counter(m['category'] for m in mutations)
    manifest = {'version': 'development-batch-draft-v0.2',
                'independent_review_status': 'pending_independent_gpt', 'formal_release': False,
                'source_families': len(families), 'source_family_target': 12, 'source_family_minimum': 10,
                'source_family_shortfall': 12-len(families),
                'source_cases': 2*len(families), 'synthetic_cases': len(synthetic_cases),
                'total_cases': len(cases), 'scheduled_review_runs': len(cases)*3*3,
                'target_review_runs': 432, 'conditions': ['A', 'B', 'C'], 'repetitions': 3,
                'source_corruptions': dict(counts),
                'corruption_group_counts': {'wrong_answer_or_status': min(4, len(families)),
                                             'wrong_proof': min(4, max(0, len(families)-4)),
                                             'fake_necessary_deletion': max(0, len(families)-8)},
                'fake_necessary_deletion_target': 4,
                'source_proof_edge_clusters': dict(edge_clusters),
                'source_proof_material_clusters': dict(material_clusters),
                'statistical_units': 'family macro summaries; repeats are repeated measurements, not independent cases; shared source/edges must be reported',
                'mutations': mutations,
                'cases_sha256': digest(cases), 'references_sha256': digest(refs),
                'families_sha256': digest(families),
                'reference_gate_created': False}
    return cases, refs, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--families', type=Path, default=WORK/'source-families.draft-v4.json')
    parser.add_argument('--synthetic-cases', type=Path, default=WORK/'synthetic-cases.draft-v3.json')
    parser.add_argument('--synthetic-references', type=Path, default=WORK/'synthetic-references.draft-v3.json')
    parser.add_argument('--output', type=Path, default=WORK/'final-draft')
    args = parser.parse_args()
    families = read(args.families)
    cases, refs, manifest = build(families, read(args.synthetic_cases), read(args.synthetic_references))
    for name, value in [('cases.json', cases), ('refs.json', refs), ('families.json', families), ('build-manifest.json', manifest)]:
        save_new_or_same(args.output/name, value)
    print({k: manifest[k] for k in ('source_families','source_family_shortfall','total_cases','scheduled_review_runs','independent_review_status')})


if __name__ == '__main__':
    main()
