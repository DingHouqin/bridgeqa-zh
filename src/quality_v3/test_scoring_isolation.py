"""Evidence-boundary regressions; scripted findings are not model validation.

Legacy fixture: [test_scoring.py](test_scoring.py).
"""
import copy
import json
import unittest

from scoring_isolation import (ANSWER_SCHEMA, EVIDENCE_SCHEMA, build_answer_payload,
                               build_scoring_package, combine_evidence_reviews,
                               digest, merge_scoring_results, step_evidence_inputs,
                               validate_answer_review, validate_evidence_review)
from test_scoring import fixture


def package(change=None):
    inputs = fixture()
    if change:
        change(*inputs)
    return build_scoring_package(*inputs)


def evidence_review(pack, support='supported'):
    return {'input_sha256': pack['evidence_input']['input_sha256'],
            'steps': [{'step_id': s['step_id'], 'support': support,
                       'used_citation_ids': [c['citation_id'] for c in s['submitted_citations']],
                       'reason': '核查所提交关系。'} for s in pack['evidence_input']['steps']],
            'issues': []}


def answer_review(pack, first, consistency='supported'):
    p = build_answer_payload(pack, first)
    return {'input_sha256': p['input_sha256'], 'evidence_review_sha256': digest(first),
            'status_correct': 'correct', 'answer_correct': 'correct',
            'context_checks': [{'step_id': s['step_id'], 'context_consistency': consistency,
                                'checked_citation_ids': [c['citation_id'] for c in s['submitted_citations']],
                                'reason': '原引用语境已核。'} for s in p['submitted_steps']],
            'answer_evidence': [{'context_id': p['contexts'][0]['context_id'], 'quote': '甲是乙的父亲。'}],
            'issues': [], 'reason': '全文答案判断与步骤证据分开。'}


def single_reviews(pack, support='supported'):
    return [{'input_sha256': item['input_sha256'],
             'steps': [{'step_id': item['steps'][0]['step_id'], 'support': support,
                        'used_citation_ids': [c['citation_id'] for c in item['steps'][0]['submitted_citations']],
                        'reason': '仅核本步所见片段。'}], 'issues': []}
            for item in step_evidence_inputs(pack)]


class ProjectionTests(unittest.TestCase):
    def test_first_stage_allowlist_hides_reference_explanations_fulltext_and_answer(self):
        a, p, row, origin, q = fixture()
        a['brief_reason'] = 'SECRET_CANDIDATE_EXPLANATION'
        a['extra_reference'] = 'SECRET_FAKE_REFERENCE'
        p['contexts'][0]['text'] += 'SECRET_UNSUBMITTED_TEXT'
        row['gold']['extra_gold'] = 'SECRET_GOLD'
        origin['facts'][0]['extra_fact'] = 'SECRET_FACT'
        a['answers'] = ['SECRET_FINAL_ANSWER']
        result = build_scoring_package(a, p, row, origin, q)
        first = result['evidence_input']
        self.assertEqual(set(first), {'version', 'task', 'steps', 'identity_aliases',
                                      'relation_direction', 'input_sha256'})
        serialized = json.dumps(first, ensure_ascii=False)
        for secret in ('SECRET_CANDIDATE_EXPLANATION', 'SECRET_FAKE_REFERENCE',
                       'SECRET_UNSUBMITTED_TEXT', 'SECRET_GOLD', 'SECRET_FACT', 'SECRET_FINAL_ANSWER'):
            self.assertNotIn(secret, serialized)
        for field in ('gold', 'reference_claims', 'candidate_response', 'contexts', 'query'):
            self.assertNotIn(field, first)

    def test_second_stage_hides_candidate_and_first_reviewer_explanations(self):
        p = package(lambda a, *rest: a.update(brief_reason='CANDIDATE_SECRET'))
        first = evidence_review(p)
        first['steps'][0]['reason'] = 'REVIEWER_REPLACEMENT_PROOF'
        first['issues'] = ['REVIEWER_SECRET_ISSUE']
        second = build_answer_payload(p, first)
        serialized = json.dumps(second, ensure_ascii=False)
        for secret in ('CANDIDATE_SECRET', 'REVIEWER_REPLACEMENT_PROOF', 'REVIEWER_SECRET_ISSUE',
                       'reference_claims', 'private_checks', 'answer_ids'):
            self.assertNotIn(secret, serialized)

    def test_scope_by_step_survives_projection(self):
        p = package(lambda a, payload, row, origin, q:
                    q.update(scope_by_step=['现实', '梦境']))
        self.assertEqual([s['claim']['scope'] for s in p['evidence_input']['steps']], ['现实', '梦境'])

    def test_scope_by_step_dict_survives_projection(self):
        p = package(lambda a, payload, row, origin, q:
                    q.update(scope_by_step={'0': '现实', '1': '虚构'}))
        self.assertEqual(p['evidence_input']['steps'][0]['claim']['scope'], '现实')

    def test_candidate_scope_cannot_override_authoritative_query(self):
        p = package(lambda a, payload, row, origin, q: a['steps'][0].update(scope='梦境'))
        self.assertEqual(p['evidence_input']['steps'][0]['claim']['scope'], '虚构')
        self.assertTrue(p['private_checks']['step_checks'][0]['scope_conflict'])

    def test_candidate_scope_cannot_override_scope_by_step(self):
        def change(a, payload, row, origin, q):
            q['scope_by_step'] = ['现实', '梦境']
            a['steps'][0]['scope'] = '梦境'
        p = package(change)
        self.assertEqual(p['evidence_input']['steps'][0]['claim']['scope'], '现实')
        self.assertTrue(p['private_checks']['step_checks'][0]['scope_conflict'])

    def test_only_visible_unique_aliases_exported_without_entity_ids(self):
        def change(a, payload, row, origin, q):
            a['steps'][1]['to'] = '老甲'
            origin['entities'][0]['aliases'].append('NEVER_VISIBLE_ALIAS')
        p = package(change)
        bindings = p['evidence_input']['identity_aliases']
        self.assertIn({'equivalent_surfaces': ['甲', '老甲']}, bindings)
        self.assertNotIn('entity_id', json.dumps(bindings))
        self.assertNotIn('NEVER_VISIBLE_ALIAS', json.dumps(bindings))

    def test_ambiguous_alias_not_exported_as_unique(self):
        def change(a, payload, row, origin, q):
            a['steps'][1]['to'] = '老甲'
            origin['entities'][-1]['aliases'].append('老甲')
        p = package(change)
        self.assertNotIn('老甲', json.dumps(p['evidence_input']['identity_aliases'], ensure_ascii=False))
        self.assertEqual(p['private_checks']['path_shape'], 'needs_semantic_review')

    def test_relational_alias_not_exported_as_identity_lookup(self):
        def change(a, payload, row, origin, q):
            origin['entities'][0]['aliases'].append('乙的父亲')
            a['steps'][1]['to'] = '乙的父亲'
        p = package(change)
        self.assertEqual(p['evidence_input']['identity_aliases'], [])

    def test_relation_alias_without_de_or_zhi_not_exported(self):
        for alias in ('乙父甲', '乙母甲', '乙所生甲'):
            def change(a, payload, row, origin, q):
                origin['entities'][0]['aliases'].append(alias)
                a['steps'][1]['to'] = alias
            p = package(change)
            for item in [p['evidence_input']] + step_evidence_inputs(p):
                self.assertNotIn(alias, json.dumps(item['identity_aliases'], ensure_ascii=False))

    def test_reported_tangmei_father_alias_not_exported(self):
        # Actual audit counterexample: [implementation audit](../../workspace/quality-v3/evidence-contract-v5/independent-implementation-audit.json).
        def change(a, payload, row, origin, q):
            origin['entities'][0].update(name='周远', aliases=['唐梅父周远'])
            origin['entities'][1].update(name='唐梅', aliases=[])
            a['steps'][1].update(**{'from': '唐梅', 'to': '唐梅父周远'})
            a['steps'][1]['evidence'][0]['quote'] = '唐梅的父亲是周远'
            payload['contexts'][0]['text'] += '唐梅的父亲是周远'
        p = package(change)
        self.assertEqual(p['evidence_input']['identity_aliases'], [])

    def test_conventional_unique_jia_mu_name_preserved(self):
        def change(a, payload, row, origin, q):
            origin['entities'][0].update(name='贾母', aliases=['史太君'])
            a['steps'][1]['to'] = '史太君'
            a['steps'][1]['evidence'][0]['quote'] = '乙的母亲是贾母'
            payload['contexts'][0]['text'] += '乙的母亲是贾母'
        p = package(change)
        self.assertIn({'equivalent_surfaces': ['贾母', '史太君']},
                      step_evidence_inputs(p)[1]['identity_aliases'])

    def test_no_origin_facts_or_evidence_sets_dependency(self):
        p = package(lambda a, payload, row, origin, q: origin.update(facts=[]))
        self.assertEqual(len(p['evidence_input']['steps']), 2)

    def test_original_inputs_not_modified(self):
        inputs = fixture()
        before = copy.deepcopy(inputs)
        build_scoring_package(*inputs)
        self.assertEqual(inputs, before)

    def test_duplicate_context_ids_rejected(self):
        def change(a, p, *rest): p['contexts'].append(copy.deepcopy(p['contexts'][0]))
        with self.assertRaises(ValueError): package(change)

    def test_private_package_tampering_rejected(self):
        p = package()
        first = evidence_review(p)
        p['private_checks']['path_shape'] = 'incorrect'
        with self.assertRaises(ValueError): build_answer_payload(p, first)


class ReviewContractTests(unittest.TestCase):
    def test_valid_both_stages(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        self.assertTrue(validate_evidence_review(first, p['evidence_input']))
        self.assertTrue(validate_answer_review(second, build_answer_payload(p, first)))

    def test_missing_or_duplicate_step_rejected(self):
        p = package()
        for replacement in ([], [evidence_review(p)['steps'][0]] * 2):
            first = evidence_review(p); first['steps'] = replacement
            with self.assertRaises(ValueError): validate_evidence_review(first, p['evidence_input'])

    def test_cross_step_citation_borrowing_rejected(self):
        p = package(); first = evidence_review(p)
        first['steps'][0]['used_citation_ids'] = first['steps'][1]['used_citation_ids']
        with self.assertRaises(ValueError): validate_evidence_review(first, p['evidence_input'])

    def test_supported_without_citation_rejected(self):
        p = package(); first = evidence_review(p)
        first['steps'][0]['used_citation_ids'] = []
        with self.assertRaises(ValueError): validate_evidence_review(first, p['evidence_input'])

    def test_exposed_control_validates_against_canonical_input(self):
        p = package(); first = evidence_review(p)
        exposed = copy.deepcopy(p['evidence_input'])
        exposed['legacy_payload'] = {'reference_claims': 'deliberate information exposure control'}
        self.assertEqual(first['input_sha256'], exposed['input_sha256'])
        self.assertTrue(validate_evidence_review(first, p['evidence_input']))

    def test_stage_one_cannot_emit_new_quote(self):
        p = package(); first = evidence_review(p)
        first['steps'][0]['replacement_quote'] = '甲是乙的父亲。'
        with self.assertRaises(Exception): validate_evidence_review(first, p['evidence_input'])

    def test_input_binding_mismatch_rejected(self):
        p = package(); first = evidence_review(p); first['input_sha256'] = 'other'
        with self.assertRaises(ValueError): validate_evidence_review(first, p['evidence_input'])

    def test_context_check_requires_each_original_citation(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        second['context_checks'][0]['checked_citation_ids'] = []
        with self.assertRaises(ValueError): validate_answer_review(second, build_answer_payload(p, first))


class SingleStepIsolationTests(unittest.TestCase):
    def test_each_request_has_one_step_and_independent_hash(self):
        p = package(); inputs = step_evidence_inputs(p)
        self.assertEqual([len(item['steps']) for item in inputs], [1, 1])
        self.assertNotEqual(inputs[0]['input_sha256'], inputs[1]['input_sha256'])
        for item in inputs:
            self.assertEqual(item['input_sha256'], digest({k: v for k, v in item.items() if k != 'input_sha256'}))

    def test_neighbor_full_relation_cannot_be_seen_by_fragment_step(self):
        def change(a, payload, row, origin, q):
            a['steps'][0]['evidence'][0]['quote'] = '丙的父亲'
            a['steps'][1]['evidence'][0]['quote'] = '丙的父亲是乙。乙的父亲是甲。'
            payload['contexts'][0]['text'] += '丙的父亲是乙。乙的父亲是甲。'
        inputs = step_evidence_inputs(package(change))
        first = json.dumps(inputs[0], ensure_ascii=False)
        self.assertNotIn('丙的父亲是乙', first)
        self.assertNotIn('乙的父亲是甲', first)
        self.assertNotIn('step-1-citation', first)
        self.assertIn('丙的父亲是乙。乙的父亲是甲。', json.dumps(inputs[1], ensure_ascii=False))

    def test_neighbor_aliases_not_visible_to_first_step(self):
        def change(a, payload, row, origin, q): a['steps'][1]['to'] = '老甲'
        inputs = step_evidence_inputs(package(change))
        self.assertEqual(inputs[0]['identity_aliases'], [])
        self.assertIn({'equivalent_surfaces': ['甲', '老甲']}, inputs[1]['identity_aliases'])

    def test_combination_accepts_arbitrary_review_order_and_restores_step_order(self):
        p = package(); reviews = single_reviews(p)
        combined = combine_evidence_reviews(p, list(reversed(reviews)))
        self.assertEqual([s['step_id'] for s in combined['steps']], ['step-0', 'step-1'])
        self.assertTrue(validate_evidence_review(combined, p['evidence_input']))
        self.assertEqual(merge_scoring_results(p, combined, answer_review(p, combined))['verdict'], 'supported')

    def test_combination_rejects_missing_or_duplicate_step(self):
        p = package(); reviews = single_reviews(p)
        for supplied in (reviews[:1], [reviews[0], reviews[0]]):
            with self.assertRaises(ValueError): combine_evidence_reviews(p, supplied)

    def test_combination_rejects_aggregate_model_response(self):
        p = package()
        with self.assertRaises(ValueError): combine_evidence_reviews(p, [evidence_review(p)] * 2)

    def test_combination_rejects_forged_other_step_and_citation(self):
        p = package(); reviews = single_reviews(p)
        reviews[0]['steps'][0]['used_citation_ids'] = reviews[1]['steps'][0]['used_citation_ids']
        with self.assertRaises(ValueError): combine_evidence_reviews(p, reviews)

    def test_empty_refusal_combines_empty_review_list(self):
        def change(a, payload, row, origin, q):
            row['gold'] = {'status': 'insufficient_evidence', 'answer_ids': [], 'proofs': []}
            a.update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
        p = package(change)
        self.assertEqual(step_evidence_inputs(p), [])
        self.assertEqual(combine_evidence_reviews(p, [])['steps'], [])

    def test_projection_does_not_mutate_sealed_package(self):
        p = package(); before = copy.deepcopy(p)
        step_evidence_inputs(p)
        self.assertEqual(p, before)

    def test_context_check_cannot_substitute_other_step(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        second['context_checks'][0]['checked_citation_ids'] = second['context_checks'][1]['checked_citation_ids']
        with self.assertRaises(ValueError): validate_answer_review(second, build_answer_payload(p, first))

    def test_final_answer_evidence_from_other_member_rejected(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        second['answer_evidence'][0]['context_id'] = 'other-member'
        with self.assertRaises(ValueError): validate_answer_review(second, build_answer_payload(p, first))

    def test_final_answer_evidence_must_be_exact(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        second['answer_evidence'][0]['quote'] = '编造句子'
        with self.assertRaises(ValueError): validate_answer_review(second, build_answer_payload(p, first))

    def test_second_stage_bound_to_exact_prior_review(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        first['steps'][0]['reason'] += '修改'
        with self.assertRaises(ValueError): validate_answer_review(second, build_answer_payload(p, first))


class MergeTests(unittest.TestCase):
    def score(self, p=None, first=None, second=None):
        p = p or package(); first = first or evidence_review(p)
        second = second or answer_review(p, first)
        return merge_scoring_results(p, first, second)

    def test_supported_still_not_automatic_release(self):
        result = self.score()
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(result['proof_support'], 'supported')
        self.assertFalse(result['automatic_release_eligible'])

    def test_candidate_dream_scope_injection_is_hard_failure_despite_supported_models(self):
        def change(a, payload, row, origin, q):
            a['steps'][0]['scope'] = '梦境'
            a['steps'][0]['evidence'][0]['quote'] = '丙梦见乙是自己的父亲'
            payload['contexts'][0]['text'] += '丙梦见乙是自己的父亲'
            q['scope'] = '现实记载'
        p = package(change); combined = combine_evidence_reviews(p, single_reviews(p))
        result = self.score(p, combined, answer_review(p, combined))
        self.assertEqual(result['raw_model_verdict'], 'supported')
        self.assertEqual(result['verdict'], 'incorrect')
        self.assertIn('candidate_scope_conflicts_with_query_scope', result['step_results'][0]['hard_defects'])

    def test_pure_names_never_repaired_by_fulltext_answer_or_model_support(self):
        def change(a, p, *rest):
            a['steps'][0]['evidence'][0]['quote'] = '乙'
            a['steps'][1]['evidence'][0]['quote'] = '甲'
        p = package(change); result = self.score(p)
        self.assertEqual(result['answer_correct'], 'correct')
        self.assertEqual(result['proof_support'], 'unsupported')
        self.assertEqual(result['verdict'], 'incorrect')
        self.assertIn('identity_only_citations_do_not_express_relation', result['step_results'][0]['hard_defects'])

    def test_name_lists_and_composed_aliases_not_relations(self):
        for quote in ('甲、乙', '甲（老甲）'):
            def change(a, p, row, origin, q):
                p['contexts'][0]['text'] += quote
                a['steps'][1]['evidence'][0]['quote'] = quote
            self.assertEqual(self.score(package(change))['proof_support'], 'unsupported')

    def test_relation_bearing_short_quotes_are_not_name_guarded(self):
        def change(a, p, row, origin, q):
            p['contexts'][0]['text'] += '乙之父甲'
            a['steps'][1]['evidence'][0]['quote'] = '乙之父甲'
        result = self.score(package(change))
        self.assertEqual(result['proof_support'], 'supported')

    def test_normal_inverse_semantics_and_nonreference_quote_not_blocked(self):
        def change(a, p, row, origin, q):
            a['steps'][1]['evidence'][0]['quote'] = '乙的父亲名叫甲。'
        self.assertEqual(self.score(package(change))['proof_support'], 'supported')

    def test_conjunctive_submitted_quotes_can_be_used_together(self):
        def change(a, p, row, origin, q):
            context = p['contexts'][0]['context_id']
            p['contexts'][0]['text'] += '乙的父亲是那位老人。那位老人叫甲。'
            a['steps'][1]['evidence'] = [
                {'context_id': context, 'quote': '乙的父亲是那位老人。'},
                {'context_id': context, 'quote': '那位老人叫甲。'}]
        self.assertEqual(self.score(package(change))['proof_support'], 'supported')

    def test_used_name_only_citation_cannot_hide_behind_unused_good_quote(self):
        p = package(lambda a, payload, row, origin, q: a['steps'][0]['evidence'].append(
            {'context_id': payload['contexts'][0]['context_id'], 'quote': '乙'}))
        first = evidence_review(p)
        first['steps'][0]['used_citation_ids'] = [first['steps'][0]['used_citation_ids'][-1]]
        self.assertEqual(self.score(p, first)['proof_support'], 'unsupported')

    def test_unlocated_or_empty_quotes_hard_fail(self):
        for quote in ('', '不存在的关系句。'):
            p = package(lambda a, *rest: a['steps'][0]['evidence'][0].update(quote=quote))
            self.assertEqual(self.score(p)['proof_support'], 'unsupported')

    def test_missing_step_citation_hard_fails_with_valid_unsupported_review(self):
        p = package(lambda a, *rest: a['steps'][0].update(evidence=[]))
        first = evidence_review(p); first['steps'][0]['support'] = 'unsupported'
        self.assertEqual(self.score(p, first)['proof_support'], 'unsupported')

    def test_full_context_cannot_upgrade_undetermined_quote(self):
        p = package(); first = evidence_review(p, 'undetermined')
        result = self.score(p, first, answer_review(p, first, 'supported'))
        self.assertEqual(result['proof_support'], 'undetermined')
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_full_context_cannot_upgrade_unsupported_quote(self):
        p = package(); first = evidence_review(p, 'unsupported')
        result = self.score(p, first, answer_review(p, first, 'supported'))
        self.assertEqual(result['proof_support'], 'unsupported')

    def test_negated_or_dream_original_context_downgrades_even_with_good_answer_elsewhere(self):
        def change(a, p, row, origin, q):
            p['contexts'][0]['text'] = '梦里传言：“乙是丙的父亲。”这不是真实情况。' + p['contexts'][0]['text']
        p = package(change); first = evidence_review(p); second = answer_review(p, first)
        second['context_checks'][0]['context_consistency'] = 'unsupported'
        result = self.score(p, first, second)
        self.assertEqual(result['answer_correct'], 'correct')
        self.assertEqual(result['proof_support'], 'unsupported')

    def test_unknown_original_context_keeps_adjudication(self):
        p = package(); first = evidence_review(p)
        result = self.score(p, first, answer_review(p, first, 'undetermined'))
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_correct_steps_do_not_repair_incorrect_top_answer(self):
        p = package(lambda a, *rest: a.update(answers=['乙']))
        first = evidence_review(p); second = answer_review(p, first)
        second['answer_correct'] = 'incorrect'
        result = self.score(p, first, second)
        self.assertEqual(result['proof_support'], 'supported')
        self.assertEqual(result['verdict'], 'incorrect')

    def test_empty_top_evidence_does_not_invalidate_steps(self):
        p = package(lambda a, *rest: a.update(evidence=[]))
        self.assertEqual(self.score(p)['proof_support'], 'supported')

    def test_unknown_or_ambiguous_answer_keeps_adjudication(self):
        for answer in ('未登记姓名', '老甲'):
            def change(a, p, row, origin, q):
                a['answers'] = [answer]
                if answer == '老甲': origin['entities'][-1]['aliases'].append(answer)
            self.assertEqual(self.score(package(change))['verdict'], 'needs_adjudication')

    def test_known_composed_alias_does_not_require_exact_gold_surface(self):
        p = package(lambda a, *rest: a.update(answers=['甲老人（甲）']))
        self.assertEqual(self.score(p)['verdict'], 'supported')

    def test_reference_disagreement_not_auto_accepted(self):
        p = package(lambda a, *rest: a.update(answers=['乙']))
        result = self.score(p)
        self.assertTrue(result['private_reference_disagreement'])
        self.assertEqual(result['raw_model_verdict'], 'supported')
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_incorrect_model_answer_with_correct_reference_requires_adjudication(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        second['answer_correct'] = 'incorrect'
        result = self.score(p, first, second)
        self.assertEqual(result['raw_model_verdict'], 'incorrect')
        self.assertTrue(result['private_reference_disagreement'])
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_incorrect_model_status_with_correct_reference_requires_adjudication(self):
        p = package(); first = evidence_review(p); second = answer_review(p, first)
        second['status_correct'] = 'incorrect'
        result = self.score(p, first, second)
        self.assertTrue(result['private_reference_disagreement'])
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_hard_bad_quote_beats_reference_disagreement(self):
        p = package(lambda a, *rest: a['steps'][0]['evidence'][0].update(quote='乙'))
        first = evidence_review(p); second = answer_review(p, first)
        second['answer_correct'] = 'incorrect'
        result = self.score(p, first, second)
        self.assertTrue(result['private_reference_disagreement'])
        self.assertEqual(result['verdict'], 'incorrect')

    def test_correct_empty_refusal_can_pass_with_not_applicable_proof(self):
        def change(a, p, row, origin, q):
            row['gold'] = {'status': 'insufficient_evidence', 'answer_ids': [], 'proofs': []}
            p['contexts'][0]['text'] = '窗外有风。'
            a.update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
        p = package(change); first = evidence_review(p)
        second = answer_review(p, first); second['answer_evidence'] = []
        result = self.score(p, first, second)
        self.assertEqual(result['proof_support'], 'not_applicable')
        self.assertEqual(result['verdict'], 'supported')


if __name__ == '__main__':
    unittest.main()
