"""Scoring regressions and false-positive controls; no provider calls."""
import copy
import unittest

from scoring import (CORE, SEMANTIC_SCHEMA, assess_structural, identity_index,
                     resolve_entity, semantic_payload, validate_semantic_review)


def fixture():
    q1 = '乙是丙的父亲。'
    q2 = '甲是乙的父亲。'
    alt = '乙的父亲名叫甲。'
    origin = {'entities': [
        {'id': 'A', 'name': '甲', 'aliases': ['甲老人', '老甲']},
        {'id': 'B', 'name': '乙', 'aliases': []},
        {'id': 'C', 'name': '丙', 'aliases': []},
        {'id': 'D', 'name': '丁', 'aliases': ['小丁']}],
        'facts': [
            {'id': 'F1', 'parent': 'B', 'child': 'C', 'parent_role': 'father', 'scope': '虚构',
             'evidence_sets': [[{'unit_id': 'T', 'quote': q1}]]},
            {'id': 'F2', 'parent': 'A', 'child': 'B', 'parent_role': 'father', 'scope': '虚构',
             'evidence_sets': [[{'unit_id': 'T', 'quote': q2}]]}]}
    row = {'materials': [{'unit_id': 'T', 'text': q1 + q2 + alt + '窗外有风。'}],
           'gold': {'status': 'answerable', 'answer_ids': ['A'], 'proofs': [{'entities': ['C', 'B', 'A'], 'facts': ['F1', 'F2']}]}}
    query = {'operation': 'parent_chain', 'start': 'C', 'steps': ['father', 'father'], 'scope': '虚构'}
    payload = CORE.project(row, '丙的父亲的父亲是谁？', {})
    context = payload['contexts'][0]['context_id']
    evidence = lambda q: {'context_id': context, 'quote': q}
    answer = {'status': 'answerable', 'answers': ['甲'], 'evidence': [evidence(q1), evidence(q2)],
              'steps': [{'from': '丙', 'relation': 'father', 'to': '乙', 'evidence': [evidence(q1)]},
                        {'from': '乙', 'relation': 'father', 'to': '甲', 'evidence': [evidence(q2)]}],
              'brief_reason': '按两条父子关系组合。'}
    return answer, payload, row, origin, query


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.origin = fixture()[3]

    def test_exact_canonical(self):
        self.assertEqual(resolve_entity('甲', self.origin)['entity_id'], 'A')

    def test_registered_alias(self):
        self.assertEqual(resolve_entity('老甲', self.origin)['entity_id'], 'A')

    def test_fullwidth_composed_alias(self):
        self.assertEqual(resolve_entity('甲老人（甲）', self.origin)['entity_id'], 'A')

    def test_ascii_composed_alias_reverse(self):
        self.assertEqual(resolve_entity('甲(甲老人)', self.origin)['entity_id'], 'A')

    def test_unknown_parenthetical_not_ignored(self):
        self.assertEqual(resolve_entity('甲（未知人物）', self.origin)['status'], 'unresolved')

    def test_conflicting_parenthetical_not_accepted(self):
        self.assertEqual(resolve_entity('甲（丁）', self.origin)['status'], 'conflicting')

    def test_ambiguous_alias_never_uses_gold_preference(self):
        self.origin['entities'][-1]['aliases'].append('老甲')
        self.assertEqual(resolve_entity('老甲', self.origin)['status'], 'ambiguous')
        self.assertEqual(resolve_entity('甲（老甲）', self.origin)['status'], 'ambiguous')

    def test_registered_parenthetical_name_is_whole_identity(self):
        self.origin['entities'].append({'id': 'W', 'name': '王氏（乙母）', 'aliases': ['王氏']})
        self.assertEqual(resolve_entity('王氏（乙母）', self.origin)['entity_id'], 'W')

    def test_substring_description_not_answer(self):
        self.assertEqual(resolve_entity('甲的侄女', self.origin)['status'], 'unresolved')

    def test_internal_whitespace_not_silently_removed(self):
        self.assertEqual(resolve_entity('甲 老人', self.origin)['status'], 'unresolved')

    def test_outer_whitespace_allowed(self):
        self.assertEqual(resolve_entity(' 甲老人 ', self.origin)['entity_id'], 'A')

    def test_nested_or_extra_name_not_accepted(self):
        self.assertEqual(resolve_entity('甲（甲老人（老甲））', self.origin)['status'], 'unresolved')
        self.assertEqual(resolve_entity('甲（甲老人）丁', self.origin)['status'], 'unresolved')

    def test_empty_or_nonstring_not_accepted(self):
        for value in ('', None, 15):
            self.assertEqual(resolve_entity(value, self.origin)['status'], 'unresolved')


class StructuralTests(unittest.TestCase):
    def score(self, change=None):
        args = fixture()
        if change:
            change(*args)
        return assess_structural(*args)

    def test_valid_proxy_never_equals_semantic_acceptance(self):
        result = self.score()
        self.assertTrue(result['structural_proxy_success'])
        self.assertEqual(result['provisional_outcome'], 'needs_semantic_review')
        self.assertFalse(result['automatic_release_eligible'])

    def test_composed_alias_repairs_answer_match_separate_from_legacy(self):
        def change(a, *rest): a['answers'] = ['甲老人（甲）']
        result = self.score(change)
        self.assertEqual(result['final_answer_match'], 'correct')
        self.assertFalse(result['legacy']['answer_and_status_correct'])

    def test_top_level_wrong_answer_not_saved_by_correct_steps(self):
        def change(a, *rest): a['answers'] = ['乙']
        result = self.score(change)
        self.assertEqual(result['path_match'], 'correct')
        self.assertEqual(result['final_answer_match'], 'incorrect')
        self.assertEqual(result['provisional_outcome'], 'incorrect')
        self.assertIsNotNone(result['top_level_answer_contradiction'])

    def test_unknown_answer_not_automatically_wrong(self):
        result = self.score(lambda a, *rest: a.update(answers=['未登记称呼']))
        self.assertEqual(result['final_answer_match'], 'needs_semantic_review')

    def test_explicit_conflicting_answer_is_not_gold_preferred(self):
        result = self.score(lambda a, *rest: a.update(answers=['甲（丁）']))
        self.assertEqual(result['final_answer_match'], 'incorrect')

    def test_unsupported_equal_status_routes_without_invented_rejection(self):
        a, p, row, origin, q = fixture()
        row['gold'].update(status='ambiguous', answer_ids=['A'])
        a.update(status='ambiguous', answers=['甲'], steps=[])
        result = assess_structural(a, p, row, origin, q)
        self.assertEqual(result['provisional_outcome'], 'needs_semantic_review')

    def test_nonoverlap_alternative_expression_routes_to_review(self):
        def change(a, p, *rest):
            a['steps'][1]['evidence'] = [{'context_id': p['contexts'][0]['context_id'], 'quote': '乙的父亲名叫甲。'}]
        result = self.score(change)
        self.assertTrue(result['evidence_quotes_located'])
        self.assertFalse(result['reference_span_coverage_proxy'])
        self.assertEqual(result['evidence_semantic_status'], 'needs_semantic_review')
        self.assertEqual(result['provisional_outcome'], 'needs_semantic_review')

    def test_same_context_unrelated_quote_does_not_prove_semantics(self):
        def change(a, p, *rest):
            a['steps'][1]['evidence'] = [{'context_id': p['contexts'][0]['context_id'], 'quote': '窗外有风。'}]
        result = self.score(change)
        self.assertFalse(result['structural_proxy_success'])
        self.assertEqual(result['evidence_semantic_status'], 'needs_semantic_review')

    def test_forged_quote_fails_location(self):
        result = self.score(lambda a, *rest: a['steps'][1]['evidence'][0].update(quote='甲是丙的父亲。'))
        self.assertFalse(result['evidence_quotes_located'])
        self.assertEqual(result['provisional_outcome'], 'incorrect')

    def test_other_member_context_id_rejected(self):
        result = self.score(lambda a, *rest: a['steps'][0]['evidence'][0].update(context_id='BASE-ONLY'))
        self.assertFalse(result['evidence_quotes_located'])

    def test_empty_quote_is_not_location_success(self):
        result = self.score(lambda a, *rest: a['evidence'][0].update(quote=''))
        self.assertFalse(result['evidence_quotes_located'])

    def test_missing_step_citations_not_accepted(self):
        result = self.score(lambda a, *rest: a['steps'][0].update(evidence=[]))
        self.assertFalse(result['step_citations_present'])
        self.assertEqual(result['provisional_outcome'], 'incorrect')

    def test_reversed_path_not_accepted(self):
        result = self.score(lambda a, *rest: a['steps'][0].update(**{'from': '乙', 'to': '丙'}))
        self.assertEqual(result['path_match'], 'incorrect')

    def test_role_mismatch_not_accepted(self):
        result = self.score(lambda a, *rest: a['steps'][0].update(relation='mother'))
        self.assertEqual(result['path_match'], 'incorrect')

    def test_unregistered_complete_maternal_alternative_routes_to_semantic_review(self):
        def change(a, p, row, origin, q):
            extra = '丁是丙的母亲。甲是丁的父亲。'
            row['materials'][0]['text'] += extra
            p['contexts'][0]['text'] += extra
            q['steps'][0] = 'parent'
            context = p['contexts'][0]['context_id']
            a['steps'] = [
                {'from': '丙', 'relation': 'mother', 'to': '丁', 'evidence': [{'context_id': context, 'quote': '丁是丙的母亲。'}]},
                {'from': '丁', 'relation': 'father', 'to': '甲', 'evidence': [{'context_id': context, 'quote': '甲是丁的父亲。'}]}]
        result = self.score(change)
        self.assertEqual(result['path_shape'], 'correct')
        self.assertEqual(result['path_match'], 'needs_semantic_review')
        self.assertEqual(result['provisional_outcome'], 'needs_semantic_review')
        self.assertFalse(result['structural_proxy_success'])

    def test_invented_alternative_with_real_but_unrelated_quotes_is_never_auto_accepted(self):
        def change(a, p, row, origin, q):
            a['steps'][0]['to'] = '丁'
            a['steps'][1]['from'] = '丁'
            for step in a['steps']:
                step['evidence'] = [{'context_id': p['contexts'][0]['context_id'], 'quote': '窗外有风。'}]
        result = self.score(change)
        self.assertEqual(result['path_shape'], 'correct')
        self.assertEqual(result['path_match'], 'needs_semantic_review')
        self.assertFalse(result['structural_proxy_success'])
        self.assertFalse(result['automatic_release_eligible'])

    def test_parent_query_accepts_father_specific_steps(self):
        result = self.score(lambda a, p, row, origin, q: q.update(steps=['parent', 'parent']))
        self.assertEqual(result['path_shape'], 'correct')
        self.assertEqual(result['path_match'], 'correct')

    def test_parent_query_accepts_mother_specific_registered_step(self):
        def change(a, p, row, origin, q):
            q['steps'][0] = 'parent'
            origin['facts'][0]['parent_role'] = 'mother'
            for obj in (p['contexts'][0], row['materials'][0]):
                obj['text'] = obj['text'].replace('乙是丙的父亲。', '乙是丙的母亲。')
            origin['facts'][0]['evidence_sets'][0][0]['quote'] = '乙是丙的母亲。'
            a['steps'][0]['relation'] = 'mother'
            a['steps'][0]['evidence'][0]['quote'] = '乙是丙的母亲。'
            a['evidence'][0]['quote'] = '乙是丙的母亲。'
        result = self.score(change)
        self.assertEqual(result['path_shape'], 'correct')
        self.assertEqual(result['path_match'], 'correct')

    def test_disconnected_alternative_is_mechanically_wrong(self):
        result = self.score(lambda a, *rest: a['steps'][0].update(to='丁'))
        self.assertEqual(result['path_shape'], 'incorrect')
        self.assertEqual(result['provisional_outcome'], 'incorrect')

    def test_wrong_known_target_of_alternative_is_mechanically_wrong(self):
        result = self.score(lambda a, *rest: a['steps'][1].update(to='丁'))
        self.assertEqual(result['path_shape'], 'incorrect')
        self.assertEqual(result['provisional_outcome'], 'incorrect')

    def test_correct_refusal_keeps_semantic_review(self):
        a, p, row, origin, q = fixture()
        row['gold'] = {'status': 'insufficient_evidence', 'answer_ids': [], 'proofs': []}
        a.update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
        result = assess_structural(a, p, row, origin, q)
        self.assertEqual(result['final_answer_match'], 'correct')
        self.assertEqual(result['provisional_outcome'], 'needs_semantic_review')

    def test_wrong_refusal_hard_failure(self):
        result = self.score(lambda a, *rest: a.update(status='insufficient_evidence', answers=[], steps=[], evidence=[]))
        self.assertEqual(result['provisional_outcome'], 'incorrect')

    def test_duplicate_target_answer_not_set_collapsed_to_success(self):
        result = self.score(lambda a, *rest: a.update(answers=['甲', '甲']))
        self.assertEqual(result['final_answer_match'], 'incorrect')

    def test_duplicate_context_ids_rejected(self):
        args = fixture()
        args[1]['contexts'].append(copy.deepcopy(args[1]['contexts'][0]))
        with self.assertRaises(ValueError): assess_structural(*args)


class SemanticContractTests(unittest.TestCase):
    def payload(self):
        return semantic_payload(*fixture())

    def review(self):
        p = self.payload()
        return {'verdict': 'supported', 'status_correct': 'correct', 'answer_correct': 'correct',
                'proof_support': 'supported', 'evidence': [{'context_id': p['contexts'][0]['context_id'], 'quote': '甲是乙的父亲。'}],
                'issues': [], 'reason': '材料支持两条父子关系及甲。'}

    def test_current_member_only_and_no_independent_audit_labels(self):
        p = self.payload()
        self.assertNotIn('gold', p)
        self.assertNotIn('independent_audit', p)
        self.assertNotIn('family', p)
        self.assertEqual(set(p['reference_claims']), {'status', 'answer_ids', 'proofs', 'facts'})

    def test_absent_reference_quote_not_leaked(self):
        args = fixture()
        args[1]['contexts'][0]['text'] = '窗外有风。'
        p = semantic_payload(*args)
        self.assertEqual(p['reference_claims']['facts'], [])
        self.assertEqual(p['visible_entity_bindings'], [])

    def test_valid_supported_review(self):
        self.assertTrue(validate_semantic_review(self.review(), self.payload()))

    def test_semantic_citation_from_other_member_rejected(self):
        review = self.review();review['evidence'][0]['context_id'] = 'OTHER'
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_supported_wrong_answer_contradiction_rejected(self):
        review = self.review();review['answer_correct'] = 'incorrect'
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_supported_undetermined_proof_rejected(self):
        review = self.review();review['proof_support'] = 'undetermined'
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_answerable_supported_without_citations_rejected(self):
        review = self.review();review['evidence'] = []
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_undetermined_cannot_be_supported(self):
        review = self.review();review.update(verdict='needs_adjudication', answer_correct='undetermined', proof_support='undetermined')
        self.assertTrue(validate_semantic_review(review, self.payload()))

    def test_incorrect_with_all_supported_dimensions_rejected(self):
        review = self.review();review['verdict'] = 'incorrect'
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_incorrect_with_no_error_and_not_applicable_proof_rejected(self):
        review = self.review();review.update(verdict='incorrect', proof_support='not_applicable')
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_uncertainty_alone_cannot_be_relabelled_incorrect(self):
        review = self.review();review.update(verdict='incorrect', answer_correct='undetermined', proof_support='undetermined')
        with self.assertRaises(ValueError): validate_semantic_review(review, self.payload())

    def test_definite_incorrect_dimension_can_coexist_with_other_uncertainty(self):
        review = self.review();review.update(verdict='incorrect', answer_correct='incorrect', proof_support='undetermined')
        self.assertTrue(validate_semantic_review(review, self.payload()))


if __name__ == '__main__':
    unittest.main()
