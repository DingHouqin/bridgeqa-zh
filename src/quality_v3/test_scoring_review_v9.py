"""Flat selectors preserve semantic failures; scripted reviews are not model QA.

Shared inputs and native test reviews: [v7 tests](test_scoring_review_v7.py).
"""
import copy
import json
import unittest

import jsonschema

import scoring_review_v9 as S
import scoring_review_v8 as PREVIOUS
import test_scoring_review_v7 as T


def flatten(native, payload):
    """Test-only fixture encoder; never used to repair actual model output."""
    def uid(citation):
        found = [u['unit_id'] for u in payload['unit_catalog']
                 if u['context_id'] == citation['context_id'] and u['quote'] == citation['quote']]
        if len(found) != 1:
            raise AssertionError('Fixture quote must identify exactly one complete source unit')
        return found[0]
    flat = {'flat_input_sha256': payload['flat_input_sha256'], 'hop_frontiers': [],
            'child_findings': [], 'context_reviews': [], 'edge_groups': [],
            'context_checks': copy.deepcopy(native['context_checks']),
            'issues': copy.deepcopy(native['issues']), 'reason': native['reason']}
    for hop in native['hop_reviews']:
        flat['hop_frontiers'].append({k: copy.deepcopy(hop[k]) for k in ('hop_id', 'frontier')})
        for child in hop['child_reviews']:
            prefix = {'hop_id': hop['hop_id'], 'child': child['child']}
            flat['child_findings'].append({**prefix, 'finding': child['finding'], 'reason': child['reason']})
            for cr in child['context_reviews']:
                flat['context_reviews'].append({**prefix,
                    **{k: copy.deepcopy(cr[k]) for k in ('context_id', 'finding', 'missing_requirements', 'reason')},
                    'considered_unit_ids': list(dict.fromkeys(uid({'context_id': cr['context_id'], 'quote': q})
                                                            for q in cr['considered_quotes']))})
            for edge in child['edges']:
                for group in edge['support_groups']:
                    flat['edge_groups'].append({**prefix, 'parent': edge['parent'],
                        'parent_role': edge['parent_role'], 'group_unit_ids': [uid(c) for c in group['citations']],
                        **{key + '_unit_id': uid(group['anchors'][key]) for key in S.CORE.ANCHOR_KEYS},
                        **{'check_' + key: group['checks'][key] for key in S.CORE.CHECK_KEYS},
                        'reason': group['reason']})
    return flat


class FlatScoringTests(unittest.TestCase):
    def setUp(self):
        self.package = S.build_scoring_package(*T.fixture())
        self.first = T.stage_a(self.package)
        self.payload = S.build_answer_payload(self.package, self.first)
        self.native = T.stage_b(self.package, self.first)
        self.flat = flatten(self.native, self.payload)

    def merge(self, flat=None):
        return S.merge_scoring_results(self.package, self.first, self.flat if flat is None else flat)

    def test_whole_units_and_findings_preserve_core_result_without_mutating_inputs(self):
        before = copy.deepcopy((self.package, self.first, self.flat, self.payload))
        got = self.merge()
        expected = PREVIOUS.merge_scoring_results(self.package, self.first, self.native)
        for key in ('verdict', 'status_correct', 'answer_correct', 'proof_support', 'step_results', 'member_findings'):
            self.assertEqual(got[key], expected[key])
        self.assertEqual((self.package, self.first, self.flat, self.payload), before)
        expanded = S.materialize_answer_review(self.flat, self.payload)
        self.assertEqual(got['answer_review_sha256'], S.digest(self.flat))
        self.assertEqual(got['native_answer_review_sha256'], S.digest(expanded))
        self.assertFalse(got['protocol_adapter_repairs_semantic_content'])
        self.assertEqual(got['flat_rows_materialized']['edge_groups'], 2)

    def test_public_projection_hides_candidate_and_stage_a_verdicts(self):
        first = copy.deepcopy(self.first)
        first['steps'][0]['support'] = 'undetermined'
        first['steps'][0]['reason'] = 'STAGE_A_JUDGMENT_SECRET'
        contract = S.build_answer_contract(self.package, first)
        serial = json.dumps(contract['input'], ensure_ascii=False)
        for token in ('candidate_final', 'evidence_findings', 'STAGE_A_JUDGMENT_SECRET', 'private_checks'):
            self.assertNotIn(token, serial)
        self.assertIn('submitted_steps', serial)
        self.assertIn('native_input_sha256', serial)

    def test_private_reference_and_facts_cannot_change_flat_contract(self):
        args = T.fixture()
        args[2]['gold'].update(status='insufficient_evidence', answer_ids=[], extra='PRIVATE_SECRET')
        args[3]['facts'] = []
        changed = S.build_scoring_package(*args)
        first = T.stage_a(changed)
        self.assertEqual(S.build_answer_contract(changed, first), S.build_answer_contract(self.package, self.first))

    def test_stage_a_inputs_still_ignore_other_step_and_unsubmitted_context(self):
        args = T.fixture()
        args[0]['steps'][1]['evidence'][0]['quote'] = 'OTHER_STEP_SECRET'
        args[1]['contexts'][0]['text'] += 'UNSUBMITTED_SOURCE_SECRET'
        changed = S.build_scoring_package(*args)
        self.assertEqual(S.step_evidence_inputs(changed)[0], S.step_evidence_inputs(self.package)[0])

    def test_catalog_complete_nonoverlapping_exact_with_punctuation_and_duplicate_occurrences(self):
        args = T.fixture()
        args[1]['contexts'][0]['text'] = '甲问：“谁？”乙说：甲。\r\n甲。'
        pack = S.build_scoring_package(*args)
        payload = S.build_answer_payload(pack, T.stage_a(pack))
        units = payload['unit_catalog']; text = payload['contexts'][0]['text']
        self.assertEqual(''.join(u['quote'] for u in units), text)
        self.assertEqual(units[0]['start'], 0)
        self.assertEqual(units[-1]['end'], len(text))
        self.assertTrue(all(left['end'] == right['start'] for left, right in zip(units, units[1:])))
        for unit in units:
            self.assertEqual(text[unit['start']:unit['end']], unit['quote'])
        self.assertEqual(len({u['unit_id'] for u in units}), len(units))

    def test_optional_issues_only_defaults_audit_metadata(self):
        flat = copy.deepcopy(self.flat); flat.pop('issues')
        got = self.merge(flat)
        self.assertTrue(got['optional_issues_defaulted'])
        self.assertEqual(got['verdict'], self.merge()['verdict'])
        self.assertEqual(S.materialize_answer_review(flat, self.payload)['issues'], [])

    def test_missing_semantic_field_is_never_defaulted(self):
        for table, field in (('child_findings', 'finding'), ('edge_groups', 'check_scope'),
                             ('context_reviews', 'missing_requirements')):
            flat = copy.deepcopy(self.flat); del flat[table][0][field]
            with self.subTest(table=table), self.assertRaises(jsonschema.ValidationError):
                self.merge(flat)

    def test_unknown_stage_a_cannot_be_upgraded_by_positive_flat_traversal(self):
        first = T.stage_a(self.package, 'undetermined')
        payload = S.build_answer_payload(self.package, first)
        flat = flatten(T.stage_b(self.package, first), payload)
        got = S.merge_scoring_results(self.package, first, flat)
        self.assertEqual(got['verdict'], 'needs_adjudication')
        self.assertEqual(got['proof_support'], 'undetermined')

    def test_unsupported_stage_a_cannot_be_upgraded_by_positive_flat_traversal(self):
        first = T.stage_a(self.package, 'unsupported')
        payload = S.build_answer_payload(self.package, first)
        flat = flatten(T.stage_b(self.package, first), payload)
        self.assertEqual(S.merge_scoring_results(self.package, first, flat)['verdict'], 'incorrect')

    def test_supported_proposal_with_unknown_check_is_rejected_not_repaired(self):
        flat = copy.deepcopy(self.flat); flat['edge_groups'][0]['check_parent_role'] = 'undetermined'
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.merge(flat)

    def test_invented_unit_and_cross_group_anchor_rejected(self):
        flat = copy.deepcopy(self.flat); flat['edge_groups'][0]['group_unit_ids'] = ['INVENTED']
        with self.assertRaises(jsonschema.ValidationError):
            self.merge(flat)
        flat = copy.deepcopy(self.flat)
        flat['edge_groups'][0]['child_unit_id'] = flat['edge_groups'][1]['child_unit_id']
        with self.assertRaisesRegex(ValueError, 'inside its own'):
            self.merge(flat)

    def test_tampered_input_catalog_rejected_even_with_rehashed_envelope(self):
        payload = copy.deepcopy(self.payload)
        payload['unit_catalog'].pop()
        payload['flat_input_sha256'] = S.digest({k: v for k, v in payload.items() if k != 'flat_input_sha256'})
        with self.assertRaisesRegex(ValueError, 'exactly partition'):
            S.answer_schema(payload)

    def test_response_from_changed_current_source_cannot_merge(self):
        args = T.fixture(); args[1]['contexts'][0]['text'] += '另一段文字。'
        pack = S.build_scoring_package(*args); first = T.stage_a(pack)
        with self.assertRaises(jsonschema.ValidationError):
            S.merge_scoring_results(pack, first, self.flat)

    def test_every_hop_is_present_in_order_including_blocked_hops(self):
        flat = copy.deepcopy(self.flat); flat['hop_frontiers'].reverse()
        with self.assertRaisesRegex(ValueError, 'in order'):
            self.merge(flat)
        flat = copy.deepcopy(self.flat); flat['hop_frontiers'].pop()
        with self.assertRaises(jsonschema.ValidationError):
            self.merge(flat)

    def test_reachable_frontier_cannot_skip_missing_or_follow_candidate_wrong_bridge(self):
        flat = copy.deepcopy(self.flat); flat['hop_frontiers'][1]['frontier'] = ['丁']
        flat['child_findings'][1]['child'] = '丁'
        flat['context_reviews'][1]['child'] = '丁'; flat['edge_groups'][1]['child'] = '丁'
        with self.assertRaisesRegex(ValueError, 'Reachable frontier'):
            self.merge(flat)

    def test_orphan_and_duplicate_child_rows_are_rejected(self):
        flat = copy.deepcopy(self.flat); flat['child_findings'].append(copy.deepcopy(flat['child_findings'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate flat child'):
            self.merge(flat)
        flat = copy.deepcopy(self.flat); flat['child_findings'][0]['child'] = '丁'
        with self.assertRaisesRegex(ValueError, 'Orphan'):
            self.merge(flat)

    def test_all_context_rows_required_and_no_orphans_or_duplicates(self):
        flat = copy.deepcopy(self.flat); flat['context_reviews'].pop()
        with self.assertRaisesRegex(ValueError, 'every current context'):
            self.merge(flat)
        flat = copy.deepcopy(self.flat); flat['context_reviews'][0]['child'] = '丁'
        with self.assertRaisesRegex(ValueError, 'Orphan flat context'):
            self.merge(flat)
        flat = copy.deepcopy(self.flat); flat['context_reviews'].append(copy.deepcopy(flat['context_reviews'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate flat child/context'):
            self.merge(flat)

    def test_orphan_positive_group_is_rejected_not_discarded(self):
        flat = copy.deepcopy(self.flat); flat['edge_groups'][0]['child'] = '丁'
        with self.assertRaisesRegex(ValueError, 'Orphan flat edge'):
            self.merge(flat)

    def test_exact_duplicate_group_footprint_rejected_not_counted_twice(self):
        flat = copy.deepcopy(self.flat)
        duplicate = copy.deepcopy(flat['edge_groups'][0]); duplicate['reason'] = '改理由仍是相同原片段'
        flat['edge_groups'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'Duplicate flat support footprint'):
            self.merge(flat)

    def test_multiple_distinct_support_groups_for_same_parent_are_preserved(self):
        flat = copy.deepcopy(self.flat)
        alt = next(u['unit_id'] for u in self.payload['unit_catalog'] if u['quote'] == '乙的父亲名叫甲。')
        extra = copy.deepcopy(flat['edge_groups'][1]); extra['group_unit_ids'] = [alt]
        extra.update({k + '_unit_id': alt for k in S.CORE.ANCHOR_KEYS})
        flat['edge_groups'].append(extra); flat['context_reviews'][1]['considered_unit_ids'].append(alt)
        expanded = S.materialize_answer_review(flat, self.payload)
        edge = expanded['hop_reviews'][1]['child_reviews'][0]['edges'][0]
        self.assertEqual(len(edge['support_groups']), 2)
        self.assertEqual(self.merge(flat)['flat_rows_materialized']['edge_groups'], 3)

    def test_positive_group_must_be_visible_in_its_own_context_review(self):
        flat = copy.deepcopy(self.flat); flat['context_reviews'][0]['considered_unit_ids'] = []
        with self.assertRaisesRegex(ValueError, 'quotation|traced'):
            self.merge(flat)

    def test_original_citation_coverage_remains_bound_to_its_own_step(self):
        flat = copy.deepcopy(self.flat)
        flat['context_checks'][0]['checked_citation_ids'] = flat['context_checks'][1]['checked_citation_ids']
        with self.assertRaises(jsonschema.ValidationError):
            self.merge(flat)

    def test_unknown_child_remains_pending_and_no_missing_default_exists(self):
        pack, first, native = T.refusal_case()
        cr = native['hop_reviews'][0]['child_reviews'][0]
        cr['finding'] = 'undetermined'; cr['context_reviews'][0]['finding'] = 'undetermined'
        cr['context_reviews'][0]['missing_requirements'] = ['unresolved_reference']
        flat = flatten(native, S.build_answer_payload(pack, first))
        self.assertEqual(S.merge_scoring_results(pack, first, flat)['verdict'], 'needs_adjudication')
        flat['child_findings'][0]['finding'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'missing edge'):
            S.merge_scoring_results(pack, first, flat)

    def test_empty_contexts_and_empty_steps_can_deliver_a_true_refusal(self):
        args = T.fixture()
        args[0].update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
        args[1]['contexts'] = []
        pack = S.build_scoring_package(*args); first = T.stage_a(pack)
        payload = S.build_answer_payload(pack, first)
        flat = {'flat_input_sha256': payload['flat_input_sha256'],
            'hop_frontiers': [{'hop_id': 'hop-0', 'frontier': ['丙']}, {'hop_id': 'hop-1', 'frontier': []}],
            'child_findings': [{'hop_id': 'hop-0', 'child': '丙', 'finding': 'missing', 'reason': '当前无材料。'}],
            'context_reviews': [], 'edge_groups': [], 'context_checks': [], 'reason': '确实缺首跳。'}
        self.assertEqual(S.merge_scoring_results(pack, first, flat)['verdict'], 'supported')
        self.assertEqual(payload['unit_catalog'], [])

    def test_input_schema_does_not_mutate_frozen_previous_schema(self):
        before = copy.deepcopy(PREVIOUS.ANSWER_SCHEMA)
        S.answer_schema(self.payload)
        self.assertEqual(PREVIOUS.ANSWER_SCHEMA, before)

    def test_source_traversal_can_find_real_parent_instead_of_candidate_wrong_bridge(self):
        args = T.fixture()
        args[0]['steps'][0]['to'] = '丁'
        args[0]['steps'][1]['from'] = '丁'
        pack = S.build_scoring_package(*args)
        first = T.stage_a(pack, 'unsupported')
        native = T.stage_b(pack, first)
        flat = flatten(native, S.build_answer_payload(pack, first))
        got = S.merge_scoring_results(pack, first, flat)
        self.assertEqual(got['member_findings']['paths'], [['丙', '乙', '甲']])
        self.assertEqual(got['member_findings']['answers'], ['甲'])
        self.assertEqual(got['proof_support'], 'unsupported')
        self.assertEqual(got['verdict'], 'incorrect')
        self.assertEqual(flat['edge_groups'][0]['parent'], '乙')

    def test_withdrawn_first_edge_does_not_downgrade_independent_valid_mother_step(self):
        args = T.fixture()
        args[0]['steps'][1].update(relation='mother')
        args[0]['steps'][1]['evidence'][0]['quote'] = '甲是乙的母亲。'
        args[0]['evidence'][1]['quote'] = '甲是乙的母亲。'
        args[4]['steps'][1] = 'mother'
        args[1]['contexts'][0]['text'] = '此前关于乙是丙的父亲的说法已经撤销。甲是乙的母亲。'
        pack = S.build_scoring_package(*args); first = T.stage_a(pack)
        native_payload = PREVIOUS.build_answer_payload(pack, first)
        native = {'input_sha256': native_payload['input_sha256'],
            'evidence_review_sha256': S.digest(first),
            'context_checks': [{'step_id': step['step_id'],
                'context_consistency': 'unsupported' if i == 0 else 'supported',
                'checked_citation_ids': [c['citation_id'] for c in step['submitted_citations']],
                'reason': '只核该步自身原位置；首跳撤销不否定另一母边。'}
                for i, step in enumerate(native_payload['submitted_steps'])],
            'hop_reviews': [{'hop_id': 'hop-0', 'frontier': ['丙'],
                'child_reviews': [T.child(native_payload, '丙')]},
                {'hop_id': 'hop-1', 'frontier': [], 'child_reviews': []}],
            'issues': [], 'reason': '当前首跳确定撤销，不能跳过首跳继续，但原母边仍独立合法。'}
        flat = flatten(native, S.build_answer_payload(pack, first))
        got = S.merge_scoring_results(pack, first, flat)
        self.assertEqual([s['original_context_consistency'] for s in got['step_results']],
                         ['unsupported', 'supported'])
        self.assertEqual(got['step_results'][1]['effective_support'], 'supported')
        self.assertEqual(got['member_findings']['status'], 'insufficient_evidence')

    def test_two_real_branches_are_preserved_and_both_traversed(self):
        args = T.fixture()
        args[1]['contexts'][0]['text'] += '丁是丙的父亲。甲是丁的父亲。'
        pack = S.build_scoring_package(*args); first = T.stage_a(pack)
        native = T.stage_b(pack, first); native_payload = PREVIOUS.build_answer_payload(pack, first)
        first_child = native['hop_reviews'][0]['child_reviews'][0]
        first_child['edges'].append(T.edge(native_payload, '丁', '丁是丙的父亲。'))
        first_child['context_reviews'][0]['considered_quotes'].append('丁是丙的父亲。')
        native['hop_reviews'][1]['frontier'].append('丁')
        native['hop_reviews'][1]['child_reviews'].append(
            T.child(native_payload, '丁', [T.edge(native_payload, '甲', '甲是丁的父亲。')]))
        flat = flatten(native, S.build_answer_payload(pack, first))
        got = S.merge_scoring_results(pack, first, flat)
        self.assertEqual(got['member_findings']['paths'], [['丙', '乙', '甲'], ['丙', '丁', '甲']])
        self.assertEqual(got['member_findings']['answers'], ['甲'])
        self.assertEqual(got['flat_rows_materialized']['edge_groups'], 4)

    def test_same_text_in_different_context_cannot_substitute_context_identity(self):
        args = T.fixture()
        args[1]['contexts'].append({'context_id': 'other-context', 'text': '乙是丙的父亲。'})
        pack = S.build_scoring_package(*args); first = T.stage_a(pack)
        native = T.stage_b(pack, first)
        flat = flatten(native, S.build_answer_payload(pack, first))
        other = next(u['unit_id'] for u in S.build_answer_payload(pack, first)['unit_catalog']
                     if u['context_id'] == 'other-context')
        flat['context_reviews'][0]['considered_unit_ids'].append(other)
        with self.assertRaisesRegex(ValueError, 'another context'):
            S.merge_scoring_results(pack, first, flat)

    def test_supported_child_cannot_silently_lose_its_positive_group(self):
        flat = copy.deepcopy(self.flat); flat['edge_groups'].pop(0)
        with self.assertRaisesRegex(ValueError, 'positive edges'):
            self.merge(flat)

    def test_schema_instance_does_not_share_frontier_and_unit_selector_definitions(self):
        schema = S.answer_schema(self.payload)
        self.assertEqual(schema['properties']['hop_frontiers']['items']['properties']['frontier']['items'], S.STR)
        self.assertIn('enum', schema['properties']['context_reviews']['items']['properties']['considered_unit_ids']['items'])

    def test_unsupported_extra_fields_are_rejected_not_silently_removed(self):
        flat = copy.deepcopy(self.flat); flat['edge_groups'][0]['override_verdict'] = 'supported'
        with self.assertRaises(jsonschema.ValidationError):
            self.merge(flat)


if __name__ == '__main__':
    unittest.main()
