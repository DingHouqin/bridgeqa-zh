"""Meaningful positive/negative workflow invariants; run via unittest, no API.

Fixtures here are explicitly fictional, not source-derived benchmark records.
"""
import copy
import json
import subprocess
import unittest
from pathlib import Path

import jsonschema
from contracts import SCHEMAS
from core import (active_facts, build_family, check_solver, digest, project, remove_quotes,
                  solve, supervisor_gate, validate_composer, validate_origin, validate_projection)
from core import validate_origin_for_composition, query_options
from formatting import parse_with_closing_repair, normalize_origin_annotations


def fixture():
    units = [{'unit_id': 'u1', 'text': '乙是丙的父亲。甲是乙的父亲。无关风景。'},
             {'unit_id': 'u2', 'text': '丁是戊的父亲。'}, {'unit_id': 'u3', 'text': '当天窗外下雨。'}]
    names = ['甲', '乙', '丙', '丁', '戊']
    origin = {'entities': [{'id': n, 'name': n, 'aliases': []} for n in names], 'warnings': [], 'facts': [
        {'id': 'f1', 'parent': '乙', 'child': '丙', 'parent_role': 'father', 'scope': 'n', 'expression': 'direct',
         'evidence_sets': [[{'unit_id': 'u1', 'quote': '乙是丙的父亲。'}]]},
        {'id': 'f2', 'parent': '甲', 'child': '乙', 'parent_role': 'father', 'scope': 'n', 'expression': 'direct',
         'evidence_sets': [[{'unit_id': 'u1', 'quote': '甲是乙的父亲。'}]]},
        {'id': 'f3', 'parent': '丁', 'child': '戊', 'parent_role': 'father', 'scope': 'n', 'expression': 'direct',
         'evidence_sets': [[{'unit_id': 'u2', 'quote': '丁是戊的父亲。'}]]}]}
    query = {'operation': 'parent_chain', 'start': '丙', 'steps': ['father', 'father'], 'scope': 'n'}
    composer = {'candidate_id': 'fictional-fixture', 'question': '丙的父亲的父亲是谁？', 'base_unit_ids': ['u1'],
        'query': query, 'proposed_answer_ids': ['甲'], 'proof_fact_ids': ['f1', 'f2'],
        'multi_hop_rationale': '需要先求丙父再求其父。', 'shortcut_risks': []}
    difficult = {'mechanism': 'entity_confusion', 'distractor_unit_ids': ['u2'], 'irrelevant_unit_ids': ['u3'],
        'deletions': [{'unit_id': 'u1', 'quote': '乙是丙的父亲。'}], 'expected_trap_answer_ids': ['丁'],
        'wrong_path_explanation': '错把戊的父亲当作目标。', 'invariants': ['保持合法基础证明']}
    return units, origin, query, composer, difficult


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.units, self.origin, self.query, self.composer, self.difficult = fixture()

    def test_real_two_step_dependency(self):
        result = validate_composer(self.composer, self.origin, self.units)
        self.assertEqual(result['answer_ids'], ['甲'])
        self.assertEqual(result['proofs'][0]['facts'], ['f1', 'f2'])
        for deleted in ('f1', 'f2'):
            self.assertEqual(solve(self.query, [f for f in self.origin['facts'] if f['id'] != deleted])['status'], 'insufficient_evidence')

    def test_wrong_direction_cannot_solve(self):
        self.origin['facts'][0]['parent'], self.origin['facts'][0]['child'] = '丙', '乙'
        with self.assertRaises(ValueError): validate_composer(self.composer, self.origin, self.units)

    def test_scope_cannot_be_silently_merged(self):
        self.origin['facts'][0]['scope'] = 'rumor'
        self.assertEqual(solve(self.query, self.origin['facts'])['status'], 'insufficient_evidence')

    def test_mother_not_father(self):
        self.origin['facts'][0]['parent_role'] = 'mother'
        self.assertEqual(solve(self.query, self.origin['facts'])['status'], 'insufficient_evidence')

    def test_no_self_ancestor_cycle(self):
        self.origin['facts'][1]['parent'] = '丙'
        self.assertEqual(solve(self.query, self.origin['facts'])['status'], 'insufficient_evidence')

    def test_unknown_quote_rejected(self):
        self.origin['facts'][0]['evidence_sets'][0][0]['quote'] = '不存在的引文'
        with self.assertRaises(ValueError): validate_origin(self.origin, self.units)

    def test_duplicate_ids_rejected(self):
        self.origin['entities'].append(copy.deepcopy(self.origin['entities'][0]))
        with self.assertRaises(ValueError): validate_origin(self.origin, self.units)

    def test_short_alias_is_not_a_complete_alternative_support(self):
        self.origin['facts'][0]['evidence_sets'].append([{'unit_id': 'u1', 'quote': '乙'}])
        with self.assertRaises(ValueError): validate_origin(self.origin, self.units)

    def test_disconnected_extraction_stops_before_composer(self):
        self.origin['facts'] = [self.origin['facts'][0], self.origin['facts'][2]]
        with self.assertRaises(ValueError): validate_origin_for_composition(self.origin, self.units)

    def test_query_options_preserve_roles_and_order(self):
        options = query_options(self.origin, self.units)
        self.assertEqual(options, [{'query': self.query, 'answer_ids': ['甲'], 'proof_fact_ids': ['f1', 'f2']}])

    def test_deleted_text_gets_new_hash_and_parent_provenance(self):
        self.units[0]['modern_sha256'] = 'frozen-source-hash'
        family = build_family(self.composer, self.difficult, self.origin, self.units)
        changed = family['variants'][-1]['materials'][0]
        self.assertEqual(changed['source_modern_sha256'], 'frozen-source-hash')
        self.assertNotEqual(changed['modern_sha256'], 'frozen-source-hash')

    def test_same_name_different_entities_remain_distinct(self):
        self.origin['entities'][0]['aliases'] = ['甲']
        self.origin['entities'][1]['aliases'] = ['乙']
        self.origin['entities'][0]['name'] = '王氏'
        self.origin['entities'][1]['name'] = '王氏'
        self.assertEqual(validate_origin(self.origin, self.units)['entities'], 5)

    def test_closing_only_json_repair_preserves_quoted_facts(self):
        broken = '{"evidence_sets":[[{"quote":"原句里的]和}不能改"}]} '
        parsed, edits = parse_with_closing_repair(broken)
        self.assertEqual(parsed, {'evidence_sets': [[{'quote': '原句里的]和}不能改'}]]})
        self.assertEqual([e['inserted'] for e in edits], [']'])

    def test_unclosed_string_is_not_guessed(self):
        with self.assertRaises(ValueError): parse_with_closing_repair('{"quote":"缺失内容')

    def test_annotation_normalization_preserves_facts_and_warning(self):
        original = copy.deepcopy(self.origin)
        original['facts'][0]['note'] = '必须保留的疑问'
        normalized, edits = normalize_origin_annotations(original)
        self.assertEqual(normalized['facts'], self.origin['facts'])
        self.assertIn('必须保留的疑问', normalized['warnings'][0])
        self.assertEqual(len(edits), 1)
        self.assertIn('note', original['facts'][0])

    def test_four_member_invariants(self):
        family = build_family(self.composer, self.difficult, self.origin, self.units)
        self.assertEqual(len(family['variants']), 4)
        self.assertEqual([r['gold']['answer_ids'] for r in family['variants']], [['甲'], ['甲'], ['甲'], []])
        self.assertEqual(family['variants'][-1]['materials'][0]['text'], '甲是乙的父亲。无关风景。')

    def test_duplicate_evidence_survives_deleting_one_quote(self):
        self.units[0]['text'] += '丙的父亲是乙。'
        self.origin['facts'][0]['evidence_sets'].append([{'unit_id': 'u1', 'quote': '丙的父亲是乙。'}])
        with self.assertRaises(ValueError): build_family(self.composer, self.difficult, self.origin, self.units)

    def test_multi_span_delete_cuts_alternative_support(self):
        self.units[0]['text'] += '丙的父亲是乙。'
        self.origin['facts'][0]['evidence_sets'].append([{'unit_id': 'u1', 'quote': '丙的父亲是乙。'}])
        self.difficult['deletions'].append({'unit_id': 'u1', 'quote': '丙的父亲是乙。'})
        family = build_family(self.composer, self.difficult, self.origin, self.units)
        self.assertEqual(family['variants'][-1]['gold']['status'], 'insufficient_evidence')

    def test_alternative_ancestor_proof_cannot_be_ignored(self):
        self.units[0]['text'] += '丁也是丙的父亲。甲是丁的父亲。'
        self.origin['facts'] += [
            dict(self.origin['facts'][0], id='f4', parent='丁', evidence_sets=[[{'unit_id': 'u1', 'quote': '丁也是丙的父亲。'}]]),
            dict(self.origin['facts'][1], id='f5', child='丁', evidence_sets=[[{'unit_id': 'u1', 'quote': '甲是丁的父亲。'}]])]
        self.assertEqual(len(solve(self.query, self.origin['facts'])['proofs']), 2)
        with self.assertRaises(ValueError): build_family(self.composer, self.difficult, self.origin, self.units)

    def test_new_answer_from_distractor_rejected(self):
        self.units[1]['text'] += '戊是丙的父亲。'
        self.origin['facts'].append(dict(self.origin['facts'][0], id='f4', parent='戊', evidence_sets=[[{'unit_id': 'u2', 'quote': '戊是丙的父亲。'}]]))
        with self.assertRaises(ValueError): build_family(self.composer, self.difficult, self.origin, self.units)

    def test_overlap_deletions_use_original_offsets(self):
        result, _ = remove_quotes([{'unit_id': 'x', 'text': 'ABCDEFGH'}], [{'unit_id': 'x', 'quote': 'BCD'}, {'unit_id': 'x', 'quote': 'DEF'}])
        self.assertEqual(result[0]['text'], 'AGH')

    def test_ambiguous_deletion_location_rejected(self):
        with self.assertRaises(ValueError): remove_quotes([{'unit_id': 'x', 'text': 'AAxAA'}], [{'unit_id': 'x', 'quote': 'AA'}])

    def test_empty_passage_rejected(self):
        with self.assertRaises(ValueError): remove_quotes([{'unit_id': 'x', 'text': 'AA'}], [{'unit_id': 'x', 'quote': 'AA'}])

    def test_blind_projection_excludes_gold_and_tags(self):
        row = build_family(self.composer, self.difficult, self.origin, self.units)['variants'][0]
        payload = project(row, self.composer['question'], SCHEMAS['blind-solver'])
        self.assertTrue(validate_projection(payload))
        payload['gold'] = row['gold']
        with self.assertRaises(ValueError): validate_projection(payload)

    def test_context_metadata_leak_rejected(self):
        row = build_family(self.composer, self.difficult, self.origin, self.units)['variants'][0]
        payload = project(row, self.composer['question'], SCHEMAS['blind-solver'])
        payload['contexts'][0]['condition'] = 'base'
        with self.assertRaises(ValueError): validate_projection(payload)

    def test_correct_answer_with_wrong_path_fails(self):
        row = build_family(self.composer, self.difficult, self.origin, self.units)['variants'][0]
        payload = project(row, self.composer['question'], SCHEMAS['blind-solver'])
        cid = payload['contexts'][0]['context_id']
        ev = [{'context_id': cid, 'quote': '乙是丙的父亲。'}]
        answer = {'status': 'answerable', 'answers': ['甲'], 'evidence': ev,
                  'steps': [{'from': '丙', 'relation': 'father', 'to': '丁', 'evidence': ev}, {'from': '丁', 'relation': 'father', 'to': '甲', 'evidence': ev}], 'brief_reason': 'fixture'}
        checks = check_solver(answer, payload, row, self.origin, self.query)
        self.assertTrue(checks['answer_and_status_correct'])
        self.assertFalse(checks['strict_structural_success'])

    def test_real_quote_but_unrelated_to_proof_fails(self):
        row = build_family(self.composer, self.difficult, self.origin, self.units)['variants'][0]
        payload = project(row, self.composer['question'], SCHEMAS['blind-solver'])
        ev = [{'context_id': payload['contexts'][0]['context_id'], 'quote': '无关风景。'}]
        answer = {'status': 'answerable', 'answers': ['甲'], 'evidence': ev,
                  'steps': [{'from': '丙', 'relation': 'father', 'to': '乙', 'evidence': ev}, {'from': '乙', 'relation': 'father', 'to': '甲', 'evidence': ev}], 'brief_reason': 'fixture'}
        checks = check_solver(answer, payload, row, self.origin, self.query)
        self.assertTrue(checks['path_matches_permitted_proof'])
        self.assertFalse(checks['strict_structural_success'])

    def test_valid_quote_overlap_need_not_be_full_containment(self):
        self.origin['facts'][1]['evidence_sets'] = [[{'unit_id': 'u1', 'quote': '乙是丙的父亲。甲是乙的父亲。'}]]
        row = build_family(self.composer, self.difficult, self.origin, self.units)['variants'][0]
        payload = project(row, self.composer['question'], SCHEMAS['blind-solver'])
        cid = payload['contexts'][0]['context_id']
        ev1 = [{'context_id': cid, 'quote': '乙是丙的父亲。'}]
        ev2 = [{'context_id': cid, 'quote': '甲是乙的父亲。无关风景。'}]
        answer = {'status': 'answerable', 'answers': ['甲'], 'evidence': ev1 + ev2,
            'steps': [{'from': '丙', 'relation': 'father', 'to': '乙', 'evidence': ev1},
                      {'from': '乙', 'relation': 'father', 'to': '甲', 'evidence': ev2}], 'brief_reason': 'fixture'}
        self.assertTrue(check_solver(answer, payload, row, self.origin, self.query)['strict_structural_success'])

    def test_false_supervisor_pass_rejected(self):
        review = {'verdict': 'pass', 'checks': [{'name': 'x', 'passed': False, 'evidence': 'wrong'}], 'issues': [], 'required_changes': []}
        with self.assertRaises(ValueError): supervisor_gate(review, ['x'])

    def test_schema_forbids_hidden_gold(self):
        answer = {'entities': [], 'facts': [], 'warnings': [], 'gold': 'secret'}
        with self.assertRaises(jsonschema.ValidationError): jsonschema.validate(answer, SCHEMAS['origin'])

    def test_python_node_path_results_agree(self):
        program = "import {solvePath} from './plugin/logic.mjs'; let s=''; for await(const c of process.stdin)s+=c; process.stdout.write(JSON.stringify(solvePath(JSON.parse(s))));"
        cases = [self.origin['facts'], self.origin['facts'][1:]]
        for facts in cases:
            result = subprocess.run(['node', '--input-type=module', '-e', program], input=json.dumps({'facts': facts, 'query': self.query}),
                capture_output=True, text=True, cwd=Path(__file__).parent, check=True)
            self.assertEqual(json.loads(result.stdout), solve(self.query, facts))


if __name__ == '__main__':
    unittest.main(verbosity=2)
