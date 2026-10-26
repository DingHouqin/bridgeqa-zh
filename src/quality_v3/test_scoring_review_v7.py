"""Meaningful v7 regressions; scripted reviews do not validate a real model.

Shared input fixture: [test_scoring.py](test_scoring.py).
"""
import copy
import json
from pathlib import Path
import unittest

import scoring_review_v7 as S
from test_scoring import fixture


def package(change=None):
    args = fixture()
    if change:
        change(*args)
    return S.build_scoring_package(*args)


def stage_a(pack, support='supported'):
    reviews = []
    for inp in S.step_evidence_inputs(pack):
        step = inp['steps'][0]; claim = step['claim']; citations = step['submitted_citations']
        first = citations[0] if citations else {'citation_id': '', 'quote': ''}
        anchors = {key: {'citation_id': first['citation_id'], 'quote': first['quote']}
                   for key in S.ANCHOR_KEYS}
        reviews.append({'input_sha256': inp['input_sha256'], 'steps': [{
            'step_id': step['step_id'], 'child': claim['child'], 'parent': claim['parent'],
            'requested_role': claim['requested_role'], 'support': support,
            'used_citation_ids': [c['citation_id'] for c in citations],
            'checks': {key: support for key in S.CHECK_KEYS}, 'anchors': anchors,
            'reason': '仅核提交的本步片段。'}], 'issues': []})
    return S.combine_evidence_reviews(pack, reviews)


def citation(payload, quote, context=None):
    context = context or payload['contexts'][0]['context_id']
    return {'context_id': context, 'quote': quote}


def group(payload, quote, context=None):
    c = citation(payload, quote, context)
    return {'citations': [c], 'anchors': {key: copy.deepcopy(c) for key in S.ANCHOR_KEYS},
            'checks': {key: 'supported' for key in S.CHECK_KEYS}, 'reason': '组内有姓名、谓词和角色。'}


def edge(payload, parent, quote, role='father', context=None):
    return {'parent': parent, 'parent_role': role,
            'support_groups': [group(payload, quote, context)], 'reason': '引文支持所询边。'}


def child(payload, name, edges=None, unknown_context=None):
    edges = edges or []
    context_reviews = []
    for c in payload['contexts']:
        quotes = [q['quote'] for e in edges for g in e['support_groups'] for q in g['citations']
                  if q['context_id'] == c['context_id']]
        finding = 'undetermined' if c['context_id'] == unknown_context else 'support_component' if quotes else 'no_support'
        context_reviews.append({'context_id': c['context_id'], 'finding': finding,
                                'considered_quotes': quotes,
                                'missing_requirements': [] if finding == 'support_component' else ['relation_predicate'],
                                'reason': '已核本context中所需child与角色，未以人名共现补边。'})
    return {'child': name, 'finding': 'undetermined' if unknown_context else 'supported' if edges else 'missing',
            'context_reviews': context_reviews, 'edges': edges, 'reason': '逐来源核边。'}


def stage_b(pack, first):
    p = S.build_answer_payload(pack, first)
    return {'input_sha256': p['input_sha256'], 'evidence_review_sha256': S.digest(first),
            'context_checks': [{'step_id': s['step_id'], 'context_consistency': 'supported',
                                'checked_citation_ids': [c['citation_id'] for c in s['submitted_citations']],
                                'reason': '逐ID核原语境。'} for s in p['submitted_steps']],
            'hop_reviews': [
                {'hop_id': 'hop-0', 'frontier': ['丙'],
                 'child_reviews': [child(p, '丙', [edge(p, '乙', '乙是丙的父亲。')])]},
                {'hop_id': 'hop-1', 'frontier': ['乙'],
                 'child_reviews': [child(p, '乙', [edge(p, '甲', '甲是乙的父亲。')])]}],
            'issues': [], 'reason': '逐跳完整路径丙→乙→甲。'}


def refusal_case(text='乙是甲的父亲。窗外有风。'):
    def change(a, p, row, origin, q):
        a.update(status='insufficient_evidence', answers=[], evidence=[], steps=[])
        p['contexts'][0]['text'] = text
        row['gold'].update(status='insufficient_evidence', answer_ids=[])
    pack = package(change); first = stage_a(pack); p = S.build_answer_payload(pack, first)
    result = {'input_sha256': p['input_sha256'], 'evidence_review_sha256': S.digest(first),
              'context_checks': [],
              'hop_reviews': [{'hop_id': 'hop-0', 'frontier': ['丙'], 'child_reviews': [child(p, '丙')]},
                              {'hop_id': 'hop-1', 'frontier': [], 'child_reviews': []}],
              'issues': [], 'reason': '缺丙→父亲首跳，旁人的父子边不能救回。'}
    return pack, first, result


class BoundaryTests(unittest.TestCase):
    def test_explicit_query_start_and_child_parent_semantics(self):
        pack = package(); p = S.build_answer_payload(pack, stage_a(pack))
        self.assertEqual(p['query']['start'], 'C')
        self.assertEqual(p['query']['start_surface'], '丙')
        self.assertEqual(p['query']['start_resolution'], 'registered_entity_name')
        self.assertEqual(p['submitted_steps'][0]['claim'],
                         {'child': '丙', 'parent': '乙', 'requested_role': 'father', 'scope': '虚构'})
        self.assertEqual([h['requested_role'] for h in p['query_plan']], ['father', 'father'])

    def test_stage_a_actual_requests_each_contain_one_step_and_no_neighbor(self):
        pack = package()
        initial = S.step_evidence_inputs(pack)[0]
        changed = package(lambda a, *rest: a['steps'][1]['evidence'][0].update(quote='NEIGHBOR_SECRET'))
        self.assertEqual(initial, S.step_evidence_inputs(changed)[0])
        self.assertEqual(len(initial['steps']), 1)
        self.assertNotIn('NEIGHBOR_SECRET', json.dumps(initial))

    def test_reference_facts_rationale_and_fulltext_never_enter_stage_a(self):
        def change(a, p, row, origin, q):
            a['brief_reason'] = 'CANDIDATE_SECRET'
            p['contexts'][0]['text'] += 'UNSUBMITTED_SECRET'
            row['gold']['sentinel'] = 'REFERENCE_SECRET'
            origin['facts'][0]['sentinel'] = 'FACT_SECRET'
        pack = package(change)
        serialized = json.dumps(S.step_evidence_inputs(pack), ensure_ascii=False)
        for secret in ('CANDIDATE_SECRET', 'UNSUBMITTED_SECRET', 'REFERENCE_SECRET', 'FACT_SECRET'):
            self.assertNotIn(secret, serialized)

    def test_stage_b_hides_reference_and_reviewer_rationale(self):
        pack = package(lambda a, *rest: a.update(brief_reason='CANDIDATE_SECRET'))
        first = stage_a(pack); first['steps'][0]['reason'] = 'REVIEWER_SECRET'
        p = S.build_answer_payload(pack, first)
        serialized = json.dumps(p, ensure_ascii=False)
        for secret in ('CANDIDATE_SECRET', 'REVIEWER_SECRET', 'private_checks', 'reference_claims', 'answer_ids'):
            self.assertNotIn(secret, serialized)

    def test_relational_aliases_not_exported_but_normal_giamu_name_remains(self):
        def change(a, p, row, origin, q):
            origin['entities'][0]['aliases'] += ['乙父甲', '贾母']
            a['steps'][1]['evidence'][0]['quote'] = '乙父甲；贾母是乙的父亲。'
        serial = json.dumps(S.step_evidence_inputs(package(change)), ensure_ascii=False)
        # The submitted quote is faithfully retained; identity mappings alone must not leak the relation.
        bindings = [g for x in S.step_evidence_inputs(package(change)) for g in x['identity_aliases']]
        self.assertNotIn('乙父甲', json.dumps(bindings, ensure_ascii=False))
        self.assertIn('贾母', serial)

    def test_scope_by_step_authoritative_and_candidate_conflict_hard_fails(self):
        def change(a, p, row, origin, q):
            q['scope_by_step'] = ['现实', '回忆']
            a['steps'][0]['scope'] = '梦境'
        pack = package(change); first = stage_a(pack); second = stage_b(pack, first)
        self.assertEqual(pack['answer_input_base']['query_plan'][0]['scope'], '现实')
        result = S.merge_scoring_results(pack, first, second)
        self.assertEqual(result['verdict'], 'incorrect')
        self.assertIn('candidate_scope_conflicts_with_query', result['step_results'][0]['hard_defects'])

    def test_aggregate_response_cannot_impersonate_single_step_reviews(self):
        pack = package(); first = stage_a(pack)
        with self.assertRaises(ValueError):
            S.combine_evidence_reviews(pack, [first, first])

    def test_reversed_direction_in_reviewer_echo_rejected(self):
        pack = package(); first = stage_a(pack)
        first['steps'][0]['child'], first['steps'][0]['parent'] = '乙', '丙'
        with self.assertRaisesRegex(ValueError, 'reversed'):
            S.validate_evidence_review(first, pack['evidence_input'])

    def test_stage_a_anchor_cannot_borrow_adjacent_citation(self):
        pack = package(); first = stage_a(pack)
        first['steps'][0]['anchors']['child'] = {'citation_id': 'step-1-citation-0', 'quote': '乙'}
        with self.assertRaises(ValueError):
            S.validate_evidence_review(first, pack['evidence_input'])

    def test_relational_alias_cannot_pollute_identity_only_veto(self):
        pack = package(lambda a, p, row, origin, q: origin['entities'][0]['aliases'].append('乙是丙的父亲。'))
        a = stage_a(pack); result = S.merge_scoring_results(pack, a, stage_b(pack, a))
        self.assertFalse(pack['private_checks']['step_checks'][0]['all_identity_only'])
        self.assertEqual(result['verdict'], 'supported')

    def test_nonpossessive_birth_description_is_not_exported_as_identity(self):
        def change(a, p, row, origin, q):
            origin['entities'][0]['aliases'] += ['乙所出甲', '乙育有甲']
            a['steps'][1]['evidence'][0]['quote'] += '乙所出甲；乙育有甲'
        pack = package(change)
        forms = [g for p in S.step_evidence_inputs(pack) for g in p['identity_aliases']]
        self.assertNotIn('乙所出甲', json.dumps(forms, ensure_ascii=False))
        self.assertNotIn('乙育有甲', json.dumps(forms, ensure_ascii=False))

    def test_ordinary_name_containing_mother_remains_a_name_not_relation(self):
        def change(a, p, row, origin, q):
            origin['entities'][0]['aliases'].append('贾母')
            a['answers'] = ['贾母']; a['steps'][1]['to'] = '贾母'
            a['steps'][1]['evidence'][0]['quote'] = '贾母是乙的父亲。'
            p['contexts'][0]['text'] += '贾母是乙的父亲。'
        pack = package(change)
        self.assertIn('贾母', S._pure_identity_index({'entities': [{'id': 'A', 'name': '甲', 'aliases': ['贾母']}]}))
        self.assertFalse(pack['private_checks']['step_checks'][1]['all_identity_only'])

    def test_query_start_as_unique_surface_matches_id_namespace(self):
        pack = package(lambda a, p, row, origin, q: q.update(start='丙'))
        a = stage_a(pack); result = S.merge_scoring_results(pack, a, stage_b(pack, a))
        self.assertEqual(pack['private_checks']['path_shape'], 'correct')
        self.assertEqual(result['verdict'], 'supported')


class TraversalContractTests(unittest.TestCase):
    def setUp(self):
        self.pack = package(); self.a = stage_a(self.pack); self.b = stage_b(self.pack, self.a)
        self.payload = S.build_answer_payload(self.pack, self.a)

    def test_valid_inverted_sentence_keeps_child_to_father_direction(self):
        result = S.merge_scoring_results(self.pack, self.a, self.b)
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(result['member_findings']['paths'], [['丙', '乙', '甲']])

    def test_missing_first_edge_blocks_later_hop_instead_of_familiar_person_bridge(self):
        pack, a, b = refusal_case('乙是甲的父亲。丙在园中写诗。')
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(result['member_findings']['status'], 'insufficient_evidence')
        self.assertEqual(result['member_findings']['paths'], [])

    def test_unnamed_daughter_and_named_greeting_do_not_fill_first_edge(self):
        pack, a, b = refusal_case('乙的夫人生了一位小姐。丙有喜信，丁前去道贺。乙的母亲是甲。')
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['verdict'], 'supported')

    def test_first_frontier_cannot_switch_to_familiar_parent(self):
        self.b['hop_reviews'][0]['frontier'] = ['乙']
        with self.assertRaisesRegex(ValueError, 'frontier'):
            S.validate_answer_review(self.b, self.payload)

    def test_later_frontier_cannot_jump_over_missing_edge(self):
        pack, a, b = refusal_case(); p = S.build_answer_payload(pack, a)
        b['hop_reviews'][1] = {'hop_id': 'hop-1', 'frontier': ['乙'], 'child_reviews': [child(p, '乙')]}
        with self.assertRaisesRegex(ValueError, 'frontier'):
            S.validate_answer_review(b, p)

    def test_hop_order_cannot_reverse(self):
        self.b['hop_reviews'].reverse()
        with self.assertRaisesRegex(ValueError, 'order'):
            S.validate_answer_review(self.b, self.payload)

    def test_missing_hop_even_when_blocked_rejected(self):
        pack, a, b = refusal_case(); b['hop_reviews'].pop()
        with self.assertRaisesRegex(ValueError, 'blocked'):
            S.validate_answer_review(b, S.build_answer_payload(pack, a))

    def test_omitted_context_cannot_claim_exhaustive_missing(self):
        pack, a, b = refusal_case()
        b['hop_reviews'][0]['child_reviews'][0]['context_reviews'].clear()
        with self.assertRaisesRegex(ValueError, 'context'):
            S.validate_answer_review(b, S.build_answer_payload(pack, a))

    def test_duplicate_context_does_not_replace_full_coverage(self):
        c = self.b['hop_reviews'][0]['child_reviews'][0]['context_reviews'][0]
        self.b['hop_reviews'][0]['child_reviews'][0]['context_reviews'].append(copy.deepcopy(c))
        with self.assertRaises(ValueError):
            S.validate_answer_review(self.b, self.payload)

    def test_missing_edge_cannot_hide_undetermined_context_as_success(self):
        pack, a, b = refusal_case(); p = S.build_answer_payload(pack, a)
        cr = b['hop_reviews'][0]['child_reviews'][0]
        cr['finding'] = 'undetermined'; cr['context_reviews'][0]['finding'] = 'undetermined'
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['verdict'], 'needs_adjudication')
        self.assertEqual(result['member_findings']['status'], 'undetermined')

    def test_explicit_unresolved_or_conflict_label_cannot_claim_definite_missing(self):
        for requirement in ('unresolved_reference', 'conflicting_support'):
            pack, a, b = refusal_case()
            cr = b['hop_reviews'][0]['child_reviews'][0]['context_reviews'][0]
            cr['missing_requirements'] = [requirement]
            cr['reason'] = '相关代词主体无法确定，或存在未解冲突。'
            with self.subTest(requirement=requirement), self.assertRaisesRegex(ValueError, 'cannot be labeled'):
                S.merge_scoring_results(pack, a, b)

    def test_unknown_opaque_query_start_not_silently_replaced_by_familiar_name(self):
        def change(a, p, row, origin, q):
            a.update(status='insufficient_evidence', answers=[], steps=[], evidence=[])
            q['start'] = 'UNKNOWN-ENTITY-ID'
        pack = package(change); a = stage_a(pack); p = S.build_answer_payload(pack, a)
        b = {'input_sha256': p['input_sha256'], 'evidence_review_sha256': S.digest(a),
             'context_checks': [], 'hop_reviews': [
                 {'hop_id': 'hop-0', 'frontier': ['UNKNOWN-ENTITY-ID'],
                  'child_reviews': [child(p, 'UNKNOWN-ENTITY-ID')]},
                 {'hop_id': 'hop-1', 'frontier': [], 'child_reviews': []}],
             'issues': [], 'reason': '起点不可解释，不能改成丙。'}
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['member_findings']['status'], 'undetermined')
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_false_missing_with_positive_context_rejected(self):
        pack, a, b = refusal_case(); p = S.build_answer_payload(pack, a)
        cr = b['hop_reviews'][0]['child_reviews'][0]['context_reviews'][0]
        cr.update(finding='support_component', considered_quotes=['乙是甲的父亲。'])
        with self.assertRaises(ValueError):
            S.validate_answer_review(b, p)

    def test_group_missing_child_antecedent_not_repaired_by_reason(self):
        cr = self.b['hop_reviews'][0]['child_reviews'][0]
        g = cr['edges'][0]['support_groups'][0]
        g['citations'][0]['quote'] = '父亲。'
        for key in g['anchors']:
            g['anchors'][key]['quote'] = '父亲'
        g['reason'] = '此处孩子就是丙，所以可补上丙。'
        with self.assertRaisesRegex(ValueError, 'named child'):
            S.validate_answer_review(self.b, self.payload)

    def test_anchor_elsewhere_in_context_but_outside_group_rejected(self):
        g = self.b['hop_reviews'][0]['child_reviews'][0]['edges'][0]['support_groups'][0]
        g['anchors']['child']['quote'] = '甲是乙的父亲。'
        with self.assertRaisesRegex(ValueError, 'outside'):
            S.validate_answer_review(self.b, self.payload)

    def test_positive_name_cooccurrence_does_not_anchor_predicate(self):
        g = self.b['hop_reviews'][0]['child_reviews'][0]['edges'][0]['support_groups'][0]
        g['anchors']['predicate']['quote'] = '丙'
        with self.assertRaisesRegex(ValueError, 'kinship'):
            S.validate_answer_review(self.b, self.payload)

    def test_scope_unknown_cannot_be_in_positive_group(self):
        self.b['hop_reviews'][0]['child_reviews'][0]['edges'][0]['support_groups'][0]['checks']['scope'] = 'undetermined'
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            S.validate_answer_review(self.b, self.payload)

    def test_original_quote_context_check_must_cover_every_id(self):
        self.b['context_checks'][0]['checked_citation_ids'] = []
        with self.assertRaisesRegex(ValueError, 'original ID'):
            S.validate_answer_review(self.b, self.payload)

    def test_context_review_cannot_quote_absent_text(self):
        self.b['hop_reviews'][0]['child_reviews'][0]['context_reviews'][0]['considered_quotes'] = ['不存在的句子']
        with self.assertRaisesRegex(ValueError, 'absent'):
            S.validate_answer_review(self.b, self.payload)

    def test_stage_b_binding_rejects_other_request(self):
        self.b['input_sha256'] = 'another-request'
        with self.assertRaisesRegex(ValueError, 'binding'):
            S.validate_answer_review(self.b, self.payload)


class MergeSafetyTests(unittest.TestCase):
    def test_stage_b_full_truth_cannot_upgrade_unsupported_stage_a(self):
        pack = package(); a = stage_a(pack, 'unsupported'); b = stage_b(pack, a)
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['member_findings']['status'], 'answerable')
        self.assertEqual(result['answer_correct'], 'correct')
        self.assertEqual(result['proof_support'], 'unsupported')
        self.assertEqual(result['verdict'], 'incorrect')

    def test_stage_b_full_truth_cannot_upgrade_undetermined_stage_a(self):
        pack = package(); a = stage_a(pack, 'undetermined'); b = stage_b(pack, a)
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['proof_support'], 'undetermined')
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_missing_role_in_narrow_quote_stays_undetermined_despite_full_context(self):
        pack = package(); a = stage_a(pack); a['steps'][0]['checks']['parent_role'] = 'undetermined'
        b = stage_b(pack, a)
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_stage_b_can_downgrade_dream_fragment_despite_other_real_good_sentence(self):
        pack = package(); a = stage_a(pack); b = stage_b(pack, a)
        b['context_checks'][0]['context_consistency'] = 'unsupported'
        b['context_checks'][0]['reason'] = '原提交片段处在梦境；另段真句不能救回。'
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['answer_correct'], 'correct')
        self.assertEqual(result['verdict'], 'incorrect')

    def test_identity_only_submission_hard_fails_even_if_model_claims_supported(self):
        pack = package(lambda a, *rest: a['steps'][0]['evidence'][0].update(quote='丙'))
        a = stage_a(pack); b = stage_b(pack, a)
        result = S.merge_scoring_results(pack, a, b)
        self.assertEqual(result['verdict'], 'incorrect')
        self.assertIn('identity_only_does_not_express_relation', result['step_results'][0]['hard_defects'])

    def test_private_reference_cannot_turn_wrong_model_status_to_unknown_or_correct(self):
        pack, a, b = refusal_case('乙是丙的父亲。甲是乙的父亲。')
        # Simulate the actual historic failure: a reviewer asserts a complete chain.
        p = S.build_answer_payload(pack, a)
        b['hop_reviews'] = [
            {'hop_id': 'hop-0', 'frontier': ['丙'], 'child_reviews': [child(p, '丙', [edge(p, '乙', '乙是丙的父亲。')])]},
            {'hop_id': 'hop-1', 'frontier': ['乙'], 'child_reviews': [child(p, '乙', [edge(p, '甲', '甲是乙的父亲。')])]}]
        result = S.merge_scoring_results(pack, a, b)
        self.assertTrue(result['private_reference_disagreement'])
        self.assertEqual(result['verdict'], 'incorrect')
        self.assertEqual(result['raw_model_verdict'], 'incorrect')
        self.assertFalse(result['reference_used_for_verdict'])

    def test_private_wrong_reference_cannot_reject_supported_current_material(self):
        pack = package(lambda a, p, row, origin, q: row['gold'].update(status='insufficient_evidence', answer_ids=[]))
        a = stage_a(pack); b = stage_b(pack, a); result = S.merge_scoring_results(pack, a, b)
        self.assertTrue(result['private_reference_disagreement'])
        self.assertEqual(result['verdict'], 'supported')

    def test_gold_mutations_leave_model_requests_and_effective_verdict_unchanged(self):
        left = package()
        def change(a, p, row, origin, q):
            row['gold'] = {'status': 'insufficient_evidence', 'answer_ids': ['D'], 'proofs': []}
            origin['facts'] = [{'arbitrary': 'SECRET_PRIVATE_GRAPH'}]
        right = package(change)
        self.assertEqual(S.step_evidence_inputs(left), S.step_evidence_inputs(right))
        a = stage_a(left)
        self.assertEqual(S.build_answer_payload(left, a), S.build_answer_payload(right, a))
        b = stage_b(left, a)
        self.assertEqual(S.merge_scoring_results(left, a, b)['verdict'],
                         S.merge_scoring_results(right, a, b)['verdict'])

    def test_correct_steps_do_not_save_wrong_top_level_answer(self):
        def change(a, p, row, origin, q):
            a['answers'] = ['丁']; p['contexts'][0]['text'] += '丁在窗外。'
        pack = package(change); a = stage_a(pack); result = S.merge_scoring_results(pack, a, stage_b(pack, a))
        self.assertEqual(result['answer_correct'], 'incorrect')
        self.assertEqual(result['verdict'], 'incorrect')

    def test_unknown_final_alias_is_not_success_or_gold_selected(self):
        pack = package(lambda a, *rest: a.update(answers=['甲（未登记别称）']))
        a = stage_a(pack); result = S.merge_scoring_results(pack, a, stage_b(pack, a))
        self.assertEqual(result['verdict'], 'needs_adjudication')

    def test_unlocated_original_quote_hard_fails(self):
        pack = package(lambda a, *rest: a['steps'][0]['evidence'][0].update(quote='乙是丙的父亲。不存在'))
        a = stage_a(pack); result = S.merge_scoring_results(pack, a, stage_b(pack, a))
        self.assertEqual(result['verdict'], 'incorrect')

    def test_positive_stage_a_without_anchors_is_not_success(self):
        pack = package(); a = stage_a(pack)
        a['steps'][0]['anchors'] = {k: {'citation_id': '', 'quote': ''} for k in S.ANCHOR_KEYS}
        result = S.merge_scoring_results(pack, a, stage_b(pack, a))
        self.assertEqual(result['verdict'], 'needs_adjudication')


class ConjunctionAndRoleTests(unittest.TestCase):
    def synthetic(self, text, relation='father'):
        a, p, row, origin, q = fixture()
        origin['entities'] = [{'id': 'C', 'name': '许蘅', 'aliases': []},
                              {'id': 'A', 'name': '沈澄', 'aliases': []}]
        origin['facts'] = []
        q.update(start='C', steps=[relation]); p['question'] = '许蘅的父亲是谁？'
        p['contexts'] = [{'context_id': 'a', 'text': text[0]}, {'context_id': 'b', 'text': text[1]}]
        row['gold'].update(answer_ids=['A'])
        a.update(answers=['沈澄'], evidence=[], steps=[
            {'from': '许蘅', 'relation': relation, 'to': '沈澄',
             'evidence': [{'context_id': 'a', 'quote': text[0]}, {'context_id': 'b', 'quote': text[1]}]}])
        pack = S.build_scoring_package(a, p, row, origin, q); first = stage_a(pack)
        ids = pack['evidence_input']['steps'][0]['submitted_citations']
        first['steps'][0]['anchors']['parent'] = {'citation_id': ids[1]['citation_id'], 'quote': text[1]}
        payload = S.build_answer_payload(pack, first)
        citations = [citation(payload, text[0], 'a'), citation(payload, text[1], 'b')]
        g = {'citations': citations,
             'anchors': {'child': citations[0], 'parent': citations[1],
                         'predicate': citations[0], 'parent_role': citations[0]},
             'checks': {key: 'supported' for key in S.CHECK_KEYS}, 'reason': '编号是跨片关联，需合取。'}
        e = {'parent': '沈澄', 'parent_role': relation, 'support_groups': [g], 'reason': '联合支持。'}
        b = {'input_sha256': payload['input_sha256'], 'evidence_review_sha256': S.digest(first),
             'context_checks': [{'step_id': 'step-0', 'context_consistency': 'supported',
                                 'checked_citation_ids': [c['citation_id'] for c in ids], 'reason': '原context均一致。'}],
             'hop_reviews': [{'hop_id': 'hop-0', 'frontier': ['许蘅'], 'child_reviews': [child(payload, '许蘅', [e])]}],
             'issues': [], 'reason': '一步父亲。'}
        return pack, first, b

    def test_cross_context_number_name_binding_must_stay_one_conjunction_group(self):
        pack, a, b = self.synthetic(('许蘅的父亲是编号父17的人。', '编号父17的人名叫沈澄。'))
        self.assertEqual(S.merge_scoring_results(pack, a, b)['verdict'], 'supported')

    def test_disconnected_identity_fragment_cannot_form_standalone_relation_group(self):
        pack, a, b = self.synthetic(('许蘅的父亲是编号父17的人。', '编号父17的人名叫沈澄。'))
        g = b['hop_reviews'][0]['child_reviews'][0]['edges'][0]['support_groups'][0]
        g['citations'] = [g['citations'][1]]
        with self.assertRaisesRegex(ValueError, 'outside'):
            S.validate_answer_review(b, S.build_answer_payload(pack, a))

    def test_generic_parent_does_not_establish_father_role(self):
        pack, a, b = self.synthetic(('许蘅是沈澄的女儿。', '沈澄和许蘅同住。'))
        # The generic parent relation is true; ordinary names are not male evidence.
        with self.assertRaisesRegex(ValueError, 'role anchor'):
            S.validate_answer_review(b, S.build_answer_payload(pack, a))

    def test_same_generic_relation_can_support_parent_query_without_gender(self):
        pack, a, b = self.synthetic(('许蘅是沈澄的女儿。', '沈澄和许蘅同住。'), relation='parent')
        self.assertEqual(S.merge_scoring_results(pack, a, b)['verdict'], 'supported')


class ActualFrozenRegressionTests(unittest.TestCase):
    """Replay trace mechanics on actual failures; reviews here are scripted.

    Sources: [v5 run-002 frozen cases](../../artifacts/quality-v3/evidence-contract-v5-run-002/cases.frozen.json).
    This neither relabels those cases nor predicts flash's next responses.
    """
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / 'artifacts/quality-v3/evidence-contract-v5-run-002/cases.frozen.json'
        cls.cases = {c['case_id']: c for c in json.loads(path.read_text(encoding='utf-8-sig')) if c['kind'] == 'scoring'}

    def test_actual_eight_old_false_blocks_keep_deleted_first_edge_missing(self):
        ids = ['6350dc95fb169af2', '7695a18b19a79b09', '8100b8a7d2734f60',
               'b1227d2d19aa66f4', 'c3c3b2dbc76375ca', 'c4a9b4fc32e2d043',
               'e4ecdc4e975b2738', 'f75df73a8243b7f8']
        for suffix in ids:
            with self.subTest(case=suffix):
                args = copy.deepcopy(self.cases['SCORE-DEV-' + suffix]['arguments'])
                pack = S.build_scoring_package(**args); a = stage_a(pack)
                p = S.build_answer_payload(pack, a)
                self.assertEqual(p['submitted_steps'], [])
                self.assertEqual(p['query']['start_surface'], args['query']['start'])
                b = {'input_sha256': p['input_sha256'], 'evidence_review_sha256': S.digest(a),
                     'context_checks': [], 'issues': [],
                     'hop_reviews': [{'hop_id': 'hop-0', 'frontier': [p['query']['start_surface']],
                                      'child_reviews': [child(p, p['query']['start_surface'])]},
                                     {'hop_id': 'hop-1', 'frontier': [], 'child_reviews': []}],
                     'reason': '逐来源审查缺首跳；作品身份、未命名小姐、会见和旁边的父母事实不能补边。'}
                result = S.merge_scoring_results(pack, a, b)
                self.assertEqual(result['verdict'], 'supported')
                self.assertEqual(result['member_findings']['status'], 'insufficient_evidence')
                self.assertEqual(len(b['hop_reviews'][0]['child_reviews'][0]['context_reviews']), len(p['contexts']))

    def test_actual_inversion_and_question_answer_quotes_keep_child_parent_roles(self):
        for case_id in ('R2-SC-C-05', 'R3-SC-C-05'):
            with self.subTest(case=case_id):
                args = copy.deepcopy(self.cases[case_id]['arguments'])
                pack = S.build_scoring_package(**args); a = stage_a(pack)
                p = S.build_answer_payload(pack, a)
                hops = []
                for index, step in enumerate(p['submitted_steps']):
                    claim = step['claim']; quote = step['submitted_citations'][0]
                    e = edge(p, claim['parent'], quote['quote'], role=claim['requested_role'], context=quote['context_id'])
                    hops.append({'hop_id': 'hop-' + str(index), 'frontier': [claim['child']],
                                 'child_reviews': [child(p, claim['child'], [e])]})
                b = {'input_sha256': p['input_sha256'], 'evidence_review_sha256': S.digest(a),
                     'context_checks': [{'step_id': s['step_id'], 'context_consistency': 'supported',
                                         'checked_citation_ids': [c['citation_id'] for c in s['submitted_citations']],
                                         'reason': '本提交句原语境成立。'} for s in p['submitted_steps']],
                     'hop_reviews': hops, 'issues': [], 'reason': '倒装/问答不改变child→parent。'}
                result = S.merge_scoring_results(pack, a, b)
                self.assertEqual(result['verdict'], 'supported')
                self.assertEqual(result['member_findings']['answers'], args['answer']['answers'])


if __name__ == '__main__':
    unittest.main()
