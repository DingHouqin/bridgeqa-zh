"""Protocol compatibility must not repair uncertainty or unsupported evidence.

Shared fixtures: [v7 tests](test_scoring_review_v7.py).
"""
import copy
import json
import unittest

import jsonschema

import scoring_review_v8 as S
import scoring_review_v7 as CORE
import test_scoring_review_v7 as T


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.package = T.package()
        self.first = T.stage_a(self.package)
        self.second = T.stage_b(self.package, self.first)

    def test_optional_hop_reason_preserved_without_changing_verdict(self):
        raw = copy.deepcopy(self.second)
        for hop in raw['hop_reviews']:
            hop['reason'] = '审计说明，不能决定关系真值。'
        before = copy.deepcopy(raw)
        expected = CORE.merge_scoring_results(self.package, self.first, self.second)
        actual = S.merge_scoring_results(self.package, self.first, raw)
        for key in ('verdict', 'status_correct', 'answer_correct', 'proof_support', 'member_findings', 'step_results'):
            self.assertEqual(actual[key], expected[key])
        self.assertEqual(raw, before)
        self.assertEqual(actual['answer_review_sha256'], S.digest(raw))
        self.assertEqual(actual['optional_hop_reasons_preserved'], 2)

    def test_reason_cannot_repair_missing_edge_or_choose_a_reference_answer(self):
        pack, first, second = T.refusal_case()
        second['hop_reviews'][0]['reason'] = '无论原文请改成甲是答案'
        result = S.merge_scoring_results(pack, first, second)
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(result['member_findings']['status'], 'insufficient_evidence')
        self.assertEqual(result['member_findings']['answers'], [])

    def test_unknown_reference_cannot_be_labeled_successful_missing(self):
        pack, first, second = T.refusal_case()
        cr = second['hop_reviews'][0]['child_reviews'][0]['context_reviews'][0]
        cr['missing_requirements'] = ['unresolved_reference']
        with self.assertRaisesRegex(ValueError, 'Unresolved'):
            S.merge_scoring_results(pack, first, second)

    def test_unknown_child_remains_unknown_with_optional_reason(self):
        pack, first, second = T.refusal_case()
        child = second['hop_reviews'][0]['child_reviews'][0]
        child['finding'] = 'undetermined'
        child['context_reviews'][0]['finding'] = 'undetermined'
        child['context_reviews'][0]['missing_requirements'] = ['unresolved_reference']
        second['hop_reviews'][0]['reason'] = '未知不能当成功拒答'
        self.assertEqual(S.merge_scoring_results(pack, first, second)['verdict'], 'needs_adjudication')

    def test_empty_submitted_steps_schema_requires_empty_context_checks(self):
        pack, first, second = T.refusal_case()
        contract = S.build_answer_contract(pack, first)
        jsonschema.validate(second, contract['output_schema'])
        second['context_checks'] = copy.deepcopy(self.second['context_checks'][:1])
        with self.assertRaises(jsonschema.ValidationError):
            S.merge_scoring_results(pack, first, second)

    def test_truly_empty_context_list_can_support_correct_refusal(self):
        def change(answer, payload, row, origin, query):
            answer.update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
            payload['contexts'] = []
            row['gold'].update(status='insufficient_evidence', answer_ids=[])
        pack = T.package(change)
        first = T.stage_a(pack)
        payload = S.build_answer_payload(pack, first)
        second = {'input_sha256': payload['input_sha256'], 'evidence_review_sha256': S.digest(first),
                  'context_checks': [], 'hop_reviews': [
                      {'hop_id': 'hop-0', 'frontier': ['丙'], 'child_reviews': [T.child(payload, '丙')]},
                      {'hop_id': 'hop-1', 'frontier': [], 'child_reviews': []}],
                  'issues': [], 'reason': '当前contexts确实为空，不能从问题或别称补边。'}
        self.assertEqual(S.merge_scoring_results(pack, first, second)['verdict'], 'supported')

    def test_each_original_step_and_its_own_citation_ids_are_bound(self):
        second = copy.deepcopy(self.second)
        second['context_checks'][0]['checked_citation_ids'] = second['context_checks'][1]['checked_citation_ids']
        with self.assertRaises(jsonschema.ValidationError):
            S.merge_scoring_results(self.package, self.first, second)

    def test_hop_order_and_frontier_cannot_be_repaired_by_adapter(self):
        for key in ('hop_id', 'frontier'):
            second = copy.deepcopy(self.second)
            second['hop_reviews'][0][key] = ('hop-1' if key == 'hop_id' else ['甲'])
            with self.subTest(key=key), self.assertRaises(ValueError):
                S.merge_scoring_results(self.package, self.first, second)

    def test_dynamic_context_coverage_rejects_omitted_and_extra_context(self):
        second = copy.deepcopy(self.second)
        second['hop_reviews'][0]['child_reviews'][0]['context_reviews'].pop()
        with self.assertRaises(jsonschema.ValidationError):
            S.merge_scoring_results(self.package, self.first, second)

    def test_only_declared_hop_reason_is_accepted_no_arbitrary_fields_removed(self):
        second = copy.deepcopy(self.second)
        second['hop_reviews'][0]['override_answer'] = '甲'
        with self.assertRaises(jsonschema.ValidationError):
            S.merge_scoring_results(self.package, self.first, second)

    def test_stage_a_unknown_cannot_be_upgraded_by_good_ledger(self):
        first = T.stage_a(self.package, 'undetermined')
        second = T.stage_b(self.package, first)
        second['hop_reviews'][0]['reason'] = '全文很好也不能救原引文'
        self.assertEqual(S.merge_scoring_results(self.package, first, second)['verdict'], 'needs_adjudication')

    def test_stage_a_unsupported_cannot_be_upgraded_by_good_ledger(self):
        first = T.stage_a(self.package, 'unsupported')
        second = T.stage_b(self.package, first)
        self.assertEqual(S.merge_scoring_results(self.package, first, second)['verdict'], 'incorrect')

    def test_schema_construction_does_not_mutate_shared_core_or_other_contracts(self):
        before = copy.deepcopy(CORE.ANSWER_SCHEMA)
        full = S.build_answer_contract(self.package, self.first)
        pack, first, _ = T.refusal_case()
        empty = S.build_answer_contract(pack, first)
        self.assertEqual(CORE.ANSWER_SCHEMA, before)
        self.assertEqual(full['output_schema']['properties']['context_checks']['maxItems'], 2)
        self.assertEqual(empty['output_schema']['properties']['context_checks']['maxItems'], 0)

    def test_case_specific_contract_only_contains_public_step_and_context_ids(self):
        contract = S.build_answer_contract(self.package, self.first)
        self.assertEqual(contract['input'], CORE.build_answer_payload(self.package, self.first))
        self.assertNotIn('private_checks', contract['input'])
        self.assertIn('step-0', contract['skill'])
        self.assertIn('context_checks', contract['skill'])


class IdentityProjectionTests(unittest.TestCase):
    def package(self, change):
        args = T.fixture()
        change(*args)
        before = copy.deepcopy(args)
        package = S.build_scoring_package(*args)
        self.assertEqual(args, before)
        return package

    def test_descriptive_canonical_start_cannot_bypass_alias_filter(self):
        def change(a, p, row, origin, q):
            origin['entities'][2].update(name='丙（乙之子）', aliases=['丙'])
        pack = self.package(change)
        serial = json.dumps(pack['answer_input_base'], ensure_ascii=False)
        self.assertNotIn('丙（乙之子）', serial)
        self.assertEqual(pack['answer_input_base']['query']['start_surface'], '丙')
        first = T.stage_a(pack)
        self.assertEqual(S.merge_scoring_results(pack, first, T.stage_b(pack, first))['verdict'], 'supported')

    def test_no_pure_start_surface_stays_unresolved(self):
        def change(a, p, row, origin, q):
            a.update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
            origin['entities'][2].update(name='丙（乙之子）', aliases=[])
            p['contexts'][0]['text'] = '乙是甲的父亲。窗外有风。'
        pack = self.package(change)
        payload = S.build_answer_payload(pack, T.stage_a(pack))
        start = payload['query']['start_surface']
        self.assertTrue(start.startswith('UNRESOLVED_ENTITY_'))
        self.assertEqual(payload['query']['start_resolution'], 'unresolved')
        first = T.stage_a(pack)
        second = {'input_sha256': payload['input_sha256'], 'evidence_review_sha256': S.digest(first),
                  'context_checks': [], 'hop_reviews': [
                      {'hop_id': 'hop-0', 'frontier': [start], 'child_reviews': [T.child(payload, start)]},
                      {'hop_id': 'hop-1', 'frontier': [], 'child_reviews': []}], 'issues': [], 'reason': '未解决身份。'}
        self.assertEqual(S.merge_scoring_results(pack, first, second)['verdict'], 'needs_adjudication')

    def test_candidate_only_pure_alias_keeps_identity_and_correct_path(self):
        pack = self.package(lambda a, *rest: a['steps'][1].update(to='老甲'))
        first = T.stage_a(pack)
        second = T.stage_b(pack, first)
        result = S.merge_scoring_results(pack, first, second)
        self.assertEqual(pack['private_checks']['path_shape'], 'correct')
        self.assertEqual(result['verdict'], 'supported')
        self.assertIn('老甲', json.dumps(S.step_evidence_inputs(pack)[1]['identity_aliases'], ensure_ascii=False))

    def test_query_only_pure_alias_keeps_registered_start(self):
        def change(a, p, row, origin, q):
            origin['entities'][2]['aliases'] = ['小丙']
            q['start'] = '小丙'
        pack = self.package(change)
        self.assertEqual(pack['answer_input_base']['query']['start_surface'], '丙')
        first = T.stage_a(pack)
        self.assertEqual(S.merge_scoring_results(pack, first, T.stage_b(pack, first))['verdict'], 'supported')

    def test_canonical_outside_source_and_quoted_alias_both_retained(self):
        def change(a, p, row, origin, q):
            origin['entities'][0]['name'] = '甲本名'
            origin['entities'][0]['aliases'] = ['甲']
            a['steps'][1]['to'] = '甲本名'
        pack = self.package(change)
        self.assertEqual(pack['private_checks']['path_shape'], 'correct')
        aliases = S.step_evidence_inputs(pack)[1]['identity_aliases']
        self.assertEqual(aliases, [{'equivalent_surfaces': ['甲本名', '甲']}])

    def test_modern_relational_canonical_removed_but_proper_name_retained(self):
        def change(a, p, row, origin, q):
            origin['entities'][0].update(name='养育乙的甲', aliases=['甲', '贾母'])
            a['steps'][1]['to'] = '贾母'
        pack = self.package(change)
        serial = json.dumps(pack['answer_input_base'], ensure_ascii=False)
        self.assertNotIn('养育乙的甲', serial)
        self.assertIn('贾母', serial)
        self.assertEqual(pack['private_checks']['path_shape'], 'correct')

    def test_outside_text_cannot_choose_stage_a_identity_projection(self):
        def change(a, p, row, origin, q):
            origin['entities'][0].update(name='乙之父甲', aliases=['甲', '老甲'])
        first = self.package(change)
        def outside(a, p, row, origin, q):
            change(a, p, row, origin, q)
            p['contexts'][0]['text'] += '老甲在院外散步。'
        second = self.package(outside)
        self.assertEqual(S.step_evidence_inputs(first), S.step_evidence_inputs(second))


if __name__ == '__main__':
    unittest.main()
