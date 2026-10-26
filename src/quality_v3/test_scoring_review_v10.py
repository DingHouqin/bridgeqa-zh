"""Query display binding without inferred edges or repaired uncertainty.

Scripted review fixtures: [v9 tests](test_scoring_review_v9.py).
"""
import copy
import json
import unittest

import jsonschema

import scoring_review_v10 as S
import scoring_review_v9 as OLD
import test_scoring_review_v9 as T9
import test_scoring_review_v7 as T7


class QueryDisplayTests(unittest.TestCase):
    def setUp(self):
        self.args = T7.fixture()
        self.package = S.build_scoring_package(*self.args)
        self.first = T7.stage_a(self.package)
        self.payload = S.build_answer_payload(self.package, self.first)
        self.native = T7.stage_b(self.package, self.first)
        self.flat = T9.flatten(self.native, self.payload)

    def merge(self, flat=None):
        return S.merge_scoring_results(self.package, self.first, self.flat if flat is None else flat)

    def test_backend_query_id_removed_from_exact_public_input_and_notes(self):
        args = copy.deepcopy(self.args)
        args[3]['entities'][2]['id'] = 'BACKEND_QUERY_CHILD_ID_X91'
        args[4]['start'] = 'BACKEND_QUERY_CHILD_ID_X91'
        pack = S.build_scoring_package(*args); first = T7.stage_a(pack)
        contract = S.build_answer_contract(pack, first)
        serial = json.dumps(contract, ensure_ascii=False)
        self.assertNotIn('BACKEND_QUERY_CHILD_ID_X91', serial)
        self.assertNotIn('start', contract['input']['query'])
        self.assertEqual(contract['input']['query']['start_surface'], '丙')
        self.assertEqual(pack['answer_input_base']['query']['start'], 'BACKEND_QUERY_CHILD_ID_X91')
        self.assertNotIn('从原query.start遍历', contract['skill'])

    def test_actual_native_semantics_and_hash_preserved_without_mutating_model_rows(self):
        before = copy.deepcopy((self.package, self.first, self.flat, self.payload))
        got = self.merge()
        native = S.materialize_answer_review(self.flat, self.payload)
        expected = S.PREVIOUS.merge_scoring_results(self.package, self.first, self.native)
        for key in ('verdict', 'status_correct', 'answer_correct', 'proof_support', 'member_findings', 'step_results'):
            self.assertEqual(got[key], expected[key])
        self.assertEqual(got['answer_review_sha256'], S.digest(self.flat))
        self.assertEqual(got['native_answer_review_sha256'], S.digest(native))
        self.assertEqual((self.package, self.first, self.flat, self.payload), before)
        self.assertTrue(got['public_query_backend_start_omitted'])
        self.assertFalse(got['protocol_adapter_repairs_semantic_content'])

    def test_old_flat_binding_does_not_silently_merge_with_new_public_projection(self):
        old_payload = OLD.build_answer_payload(self.package, self.first)
        old_flat = T9.flatten(self.native, old_payload)
        self.assertNotEqual(old_payload['flat_input_sha256'], self.payload['flat_input_sha256'])
        with self.assertRaises(jsonschema.ValidationError):
            self.merge(old_flat)

    def test_first_frontier_cannot_use_backend_id_or_grammatical_parent_subject(self):
        for bad in ('C', '乙'):
            flat = copy.deepcopy(self.flat); flat['hop_frontiers'][0]['frontier'] = [bad]
            with self.subTest(bad=bad), self.assertRaises(jsonschema.ValidationError):
                self.merge(flat)

    def test_first_hop_child_is_query_subject_in_every_flat_table(self):
        for table in ('child_findings', 'context_reviews', 'edge_groups'):
            flat = copy.deepcopy(self.flat); flat[table][0]['child'] = '乙'
            with self.subTest(table=table), self.assertRaises(jsonschema.ValidationError):
                self.merge(flat)

    def test_first_hop_query_const_does_not_guess_parent_or_change_later_frontier(self):
        schema = S.answer_schema(self.payload)
        edge = schema['properties']['edge_groups']['items']['properties']
        self.assertEqual(edge['parent'], OLD.STR)
        self.assertNotIn('const', schema['properties']['hop_frontiers']['items']['properties']['frontier'])
        flat = copy.deepcopy(self.flat)
        flat['hop_frontiers'][1]['frontier'] = ['丁']
        flat['child_findings'][1]['child'] = '丁'
        flat['context_reviews'][1]['child'] = '丁'; flat['edge_groups'][1]['child'] = '丁'
        with self.assertRaisesRegex(ValueError, 'Reachable frontier'):
            self.merge(flat)

    def test_wrong_candidate_bridge_does_not_limit_true_full_source_parent(self):
        args = copy.deepcopy(self.args)
        args[0]['steps'][0]['to'] = '丁'; args[0]['steps'][1]['from'] = '丁'
        pack = S.build_scoring_package(*args); first = T7.stage_a(pack, 'unsupported')
        flat = T9.flatten(T7.stage_b(pack, first), S.build_answer_payload(pack, first))
        result = S.merge_scoring_results(pack, first, flat)
        self.assertEqual(result['member_findings']['paths'], [['丙', '乙', '甲']])
        self.assertEqual(result['proof_support'], 'unsupported')

    def test_query_const_does_not_supply_a_missing_group_subject(self):
        flat = copy.deepcopy(self.flat)
        uid = flat['edge_groups'][1]['group_unit_ids'][0]
        flat['edge_groups'][0]['group_unit_ids'] = [uid]
        flat['edge_groups'][0].update({k + '_unit_id': uid for k in S.CORE.ANCHOR_KEYS})
        flat['context_reviews'][0]['considered_unit_ids'] = [uid]
        with self.assertRaisesRegex(ValueError, 'named child'):
            self.merge(flat)

    def test_stage_a_unknown_is_never_upgraded_by_query_schema(self):
        first = T7.stage_a(self.package, 'undetermined')
        flat = T9.flatten(T7.stage_b(self.package, first), S.build_answer_payload(self.package, first))
        result = S.merge_scoring_results(self.package, first, flat)
        self.assertEqual(result['verdict'], 'needs_adjudication')
        self.assertEqual(result['proof_support'], 'undetermined')

    def test_literal_unregistered_query_start_still_uses_visible_name(self):
        args = copy.deepcopy(self.args)
        args[4]['start'] = '丙'
        args[3]['entities'] = [e for e in args[3]['entities'] if e['id'] != 'C']
        pack = S.build_scoring_package(*args)
        self.assertEqual(S.build_answer_payload(pack, T7.stage_a(pack))['query']['start_surface'], '丙')
        self.assertEqual(S.build_answer_payload(pack, T7.stage_a(pack))['query']['start_resolution'], 'literal_query_start')

    def test_pure_identity_projection_still_filters_relational_canonical_description(self):
        args = copy.deepcopy(self.args)
        args[3]['entities'][2].update(name='丙（乙之子）', aliases=['丙'])
        pack = S.build_scoring_package(*args); first = T7.stage_a(pack)
        contract = S.build_answer_contract(pack, first)
        self.assertNotIn('丙（乙之子）', json.dumps(contract, ensure_ascii=False))
        self.assertEqual(contract['input']['query']['start_surface'], '丙')
        flat = T9.flatten(T7.stage_b(pack, first), contract['input'])
        self.assertEqual(S.merge_scoring_results(pack, first, flat)['verdict'], 'supported')

    def test_unresolved_opaque_start_stays_pending_without_identity_inference(self):
        args = copy.deepcopy(self.args)
        args[3]['entities'][2].update(name='丙（乙之子）', aliases=[])
        args[0].update(status='insufficient_evidence', answers=[], evidence=[], steps=[])
        args[1]['contexts'][0]['text'] = '乙是甲的父亲。窗外有风。'
        pack = S.build_scoring_package(*args); first = T7.stage_a(pack)
        payload = S.build_answer_payload(pack, first); start = payload['query']['start_surface']
        flat = {'flat_input_sha256': payload['flat_input_sha256'],
            'hop_frontiers': [{'hop_id': 'hop-0', 'frontier': [start]}, {'hop_id': 'hop-1', 'frontier': []}],
            'child_findings': [{'hop_id': 'hop-0', 'child': start, 'finding': 'missing', 'reason': '没有可绑定的身份。'}],
            'context_reviews': [{'hop_id': 'hop-0', 'child': start, 'context_id': c['context_id'],
                'finding': 'no_support', 'considered_unit_ids': [], 'missing_requirements': ['relation_predicate'],
                'reason': '仍未绑定查询身份，程序应保留未决。'} for c in payload['contexts']],
            'edge_groups': [], 'context_checks': [], 'reason': '不能从后台ID补姓名或边。'}
        self.assertTrue(start.startswith('UNRESOLVED_ENTITY_'))
        self.assertEqual(payload['query']['start_resolution'], 'unresolved')
        self.assertEqual(S.merge_scoring_results(pack, first, flat)['verdict'], 'needs_adjudication')

    def test_truly_empty_contexts_remain_valid_true_refusal(self):
        args = copy.deepcopy(self.args)
        args[0].update(status='insufficient_evidence', answers=[], evidence=[], steps=[])
        args[1]['contexts'] = []
        pack = S.build_scoring_package(*args); first = T7.stage_a(pack)
        payload = S.build_answer_payload(pack, first)
        flat = {'flat_input_sha256': payload['flat_input_sha256'],
            'hop_frontiers': [{'hop_id': 'hop-0', 'frontier': ['丙']}, {'hop_id': 'hop-1', 'frontier': []}],
            'child_findings': [{'hop_id': 'hop-0', 'child': '丙', 'finding': 'missing', 'reason': '当前无任何材料。'}],
            'context_reviews': [], 'edge_groups': [], 'context_checks': [], 'reason': '真空材料缺首边。'}
        self.assertEqual(S.merge_scoring_results(pack, first, flat)['verdict'], 'supported')

    def test_private_reference_changes_do_not_change_exact_public_contract(self):
        args = copy.deepcopy(self.args)
        args[2]['gold'].update(status='insufficient_evidence', answer_ids=['PRIVATE_SECRET'])
        args[3]['facts'] = []; args[0]['brief_reason'] = 'FREE_REASON_SECRET'
        pack = S.build_scoring_package(*args); first = T7.stage_a(pack)
        self.assertEqual(S.build_answer_contract(pack, first), S.build_answer_contract(self.package, self.first))

    def test_stage_a_still_isolated_from_full_source_and_neighbor_step(self):
        args = copy.deepcopy(self.args)
        args[0]['steps'][1]['evidence'][0]['quote'] = 'OTHER_STEP_SECRET'
        args[1]['contexts'][0]['text'] += 'UNSUBMITTED_SECRET'
        pack = S.build_scoring_package(*args)
        self.assertEqual(S.step_evidence_inputs(pack)[0], S.step_evidence_inputs(self.package)[0])

    def test_missing_rows_are_not_added_and_old_schema_is_not_mutated(self):
        before = copy.deepcopy(OLD.ANSWER_SCHEMA)
        S.answer_schema(self.payload)
        self.assertEqual(OLD.ANSWER_SCHEMA, before)
        flat = copy.deepcopy(self.flat); flat['context_reviews'].pop(0)
        with self.assertRaises(jsonschema.ValidationError):
            self.merge(flat)

    def test_schema_binds_every_hop_order_without_guessing_later_frontier(self):
        schema = S.answer_schema(self.payload)
        jsonschema.validate(self.flat, schema)
        self.assertEqual([item['properties']['hop_id']['const']
                          for item in schema['properties']['hop_frontiers']['prefixItems']], ['hop-0', 'hop-1'])
        flat = copy.deepcopy(self.flat); flat['hop_frontiers'].reverse()
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(flat, schema)

    def test_schema_requires_exactly_one_known_first_child_and_each_known_context(self):
        schema = S.answer_schema(self.payload)
        for table in ('child_findings', 'context_reviews'):
            for edit in ('missing', 'duplicate'):
                flat = copy.deepcopy(self.flat)
                if edit == 'missing':
                    flat[table].pop(0)
                else:
                    flat[table].append(copy.deepcopy(flat[table][0]))
                with self.subTest(table=table, edit=edit), self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(flat, schema)

    def test_schema_disallows_each_kind_of_stray_row_under_self_declared_empty_hop(self):
        schema = S.answer_schema(self.payload)
        for table in ('child_findings', 'context_reviews', 'edge_groups'):
            flat = copy.deepcopy(self.flat); flat['hop_frontiers'][1]['frontier'] = []
            for other in ('child_findings', 'context_reviews', 'edge_groups'):
                if other != table:
                    flat[other] = [r for r in flat[other] if r['hop_id'] != 'hop-1']
            with self.subTest(table=table), self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(flat, schema)

    def test_schema_empty_hop_self_consistency_does_not_assert_actual_frontier_is_empty(self):
        flat = copy.deepcopy(self.flat); flat['hop_frontiers'][1]['frontier'] = []
        for table in ('child_findings', 'context_reviews', 'edge_groups'):
            flat[table] = [r for r in flat[table] if r['hop_id'] != 'hop-1']
        # Internally coherent model declaration is schema-valid, but conflicts
        # with its preceding actual edge; the semantic core still rejects it.
        jsonschema.validate(flat, S.answer_schema(self.payload))
        with self.assertRaisesRegex(ValueError, 'Reachable frontier'):
            self.merge(flat)


if __name__ == '__main__':
    unittest.main()
