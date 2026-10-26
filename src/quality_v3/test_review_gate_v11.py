"""Independent trust and abstention boundaries, not natural-language accuracy."""
import copy
import json
import unittest

import review_gate_v11 as G
import scoring_review_v10 as S
import test_scoring_review_v7 as T7


def fixture(contexts=None):
    if contexts == []:
        args = list(T7.fixture())
        args[0].update(status='insufficient_evidence', answers=[], evidence=[], steps=[])
        args[1]['contexts'] = []
        package = S.build_scoring_package(*args)
        first = T7.stage_a(package)
        payload = S.build_answer_payload(package, first)
        flat = {'flat_input_sha256': payload['flat_input_sha256'],
            'hop_frontiers': [{'hop_id': h['hop_id'], 'frontier': ['丙'] if i == 0 else []}
                              for i, h in enumerate(payload['query_plan'])],
            'child_findings': [{'hop_id': 'hop-0', 'child': '丙', 'finding': 'missing',
                                'reason': '实际材料为空。'}],
            'context_reviews': [], 'edge_groups': [], 'context_checks': [],
            'issues': [], 'reason': '无给定材料，首跳缺证。'}
        contract = {'job': {'case_id': 'arbitrary-id', 'kind': 'scoring', 'arm': 'draft'},
            'split': 'development', 'package': package, 'evidence_inputs': []}
        draft = {'job': copy.deepcopy(contract['job']), 'split': 'development', 'status': 'completed',
            'single_step_reviews': [], 'evidence_review': first, 'answer_review': flat,
            'merged': S.merge_scoring_results(package, first, flat)}
        return contract, draft
    contexts = [{'context_id': 'C', 'text': '本页仅介绍乙。'}] if contexts is None else contexts
    source = {'version': 'native', 'task': 'current_member_edge_traversal_and_quote_context_review',
        'question': '乙的母亲是谁？',
        'query': {'operation': 'parent_chain', 'start': 'B', 'start_surface': '乙',
                  'steps': ['mother'], 'scope': 'given'},
        'query_plan': [{'hop_id': 'hop-0', 'requested_role': 'mother', 'scope': 'given'}],
        'contexts': contexts, 'candidate_final': {'status': 'insufficient_evidence', 'answers': []},
        'submitted_steps': [], 'identity_aliases': [], 'relation_definition': {}}
    contract = {'job': {'case_id': 'arbitrary-id', 'kind': 'scoring', 'arm': 'draft'},
                'split': 'development', 'package': {'answer_input_base': source}, 'evidence_inputs': []}
    draft = {'job': copy.deepcopy(contract['job']), 'split': 'development', 'status': 'completed',
        'evidence_review': {'steps': []},
        'merged': {'verdict': 'supported', 'member_findings': {
            'status': 'insufficient_evidence', 'answers': [], 'paths': [], 'uncertainty_encountered': False},
            'step_results': []}}
    return contract, draft


def raw(draft):
    return json.dumps(draft, ensure_ascii=False).encode('utf-8')


def signed(contract, data):
    request = G.review_request(contract, data)
    receipt = {'version': G.VERSION, 'scope': G.CORE_SCOPE,
        'request_sha256': request['request_sha256'], 'source_sha256': request['source_sha256'],
        'draft_bytes_sha256': request['draft_bytes_sha256'], 'decision': 'confirmed',
        'unresolved_facets': [], 'reviewer_identity': 'separate-source-reviewer',
        'reviewer_kind': 'independent_strong_agent', 'source_artifact_sha256': 'a' * 64,
        'reviewed_coverage': request['required_coverage'], 'confirmed_facets': request['required_facets'],
        'confirmed_core': G.core_projection(contract, json.loads(data))}
    return receipt, authorize(receipt)


def authorize(receipt):
    return {G.digest(receipt): {key: receipt[key] for key in ('source_artifact_sha256', 'reviewer_identity')}
            | {'actual_independent_source_review_verified': True}}


class ReviewGateTests(unittest.TestCase):
    def test_empty_closed_source_publishes_insufficiency_only(self):
        c, d = fixture([])
        out = G.route(c, raw(d), closed_world=True)
        self.assertEqual(out['status'], 'automatically_determined_core')
        self.assertEqual(out['conclusion']['source_status'], 'insufficient_evidence')
        self.assertFalse(out['formal_release'])
        self.assertFalse(out['original_draft_certified'])

    def test_caller_must_declare_closed_world(self):
        c, d = fixture([])
        self.assertEqual(G.route(c, raw(d))['status'], 'requires_review')

    def test_any_actual_context_even_empty_text_requires_review(self):
        for text in ('', ' ', '没有找到支持', '乙的母亲是甲。'):
            c, d = fixture([{'context_id': 'C', 'text': text}])
            self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_nonempty_model_success_or_reference_agreement_does_not_clear(self):
        c, d = fixture()
        d['merged'].update(private_reference_disagreement=False, confidence=1.0,
                           automatic_release_eligible=True)
        self.assertIsNone(G.route(c, raw(d), closed_world=True)['conclusion'])

    def test_wrong_query_or_zero_hops_never_auto(self):
        for key, value in [('operation', 'external_knowledge'), ('start', ''),
                           ('start_surface', ''), ('steps', []), ('steps', ['sibling'])]:
            c, d = fixture([])
            c['package']['answer_input_base']['query'][key] = value
            self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_candidate_answers_or_evidence_are_not_empty_refusal(self):
        for field, value in [('answers', ['甲']), ('evidence', ['伪证'])]:
            c, d = fixture([])
            c['package']['answer_input_base']['candidate_final'][field] = value
            self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_submitted_steps_block_empty_auto(self):
        c, d = fixture([])
        c['package']['answer_input_base']['submitted_steps'] = [{'step_id': 'step-0'}]
        self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_extra_semantic_base_field_blocks_empty_auto(self):
        c, d = fixture([])
        c['package']['answer_input_base']['background'] = '乙的母亲是甲。'
        self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_wrong_draft_does_not_auto_replace_with_correct_empty_result(self):
        c, d = fixture([])
        d['merged']['member_findings']['answers'] = ['甲']
        self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_empty_wire_hash_frontier_and_merged_fields_must_revalidate(self):
        changes = [lambda d: d['evidence_review'].update(input_sha256='0' * 64),
            lambda d: d['answer_review']['hop_frontiers'][0].update(frontier=['错误主体']),
            lambda d: d['merged'].update(proof_support='undetermined'),
            lambda d: d['merged'].update(status_correct='incorrect', answer_correct='incorrect')]
        for change in changes:
            c, d = fixture([])
            change(d)
            self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')

    def test_unknown_status_and_invalid_core_types_cannot_be_confirmed(self):
        for member in ({'status': 'undetermined'}, {'answers': '甲'}, {'paths': '甲'}):
            c, d = fixture()
            d['merged']['member_findings'].update(member)
            with self.assertRaises((TypeError, ValueError)):
                G.core_projection(c, d)

    def test_source_artifact_binding_cannot_be_missing_empty_or_non_sha(self):
        c, d = fixture()
        original, _ = signed(c, raw(d))
        for value in (None, '', 'short'):
            receipt = copy.deepcopy(original)
            receipt['source_artifact_sha256'] = value
            self.assertEqual(G.route(c, raw(d), receipt=receipt,
                trusted_registry=authorize(receipt))['status'], 'requires_review')

    def test_forged_receipt_without_operator_registry_is_not_approval(self):
        c, d = fixture()
        receipt, _ = signed(c, raw(d))
        self.assertEqual(G.route(c, raw(d), receipt=receipt)['status'], 'requires_review')

    def test_exact_approved_receipt_publishes_core_only(self):
        c, d = fixture()
        d['reason'] = '未经认证的自由理由'
        receipt, registry = signed(c, raw(d))
        out = G.route(c, raw(d), receipt=receipt, trusted_registry=registry)
        self.assertEqual(out['status'], 'independently_reviewed_core')
        self.assertNotIn('reason', out['conclusion'])
        self.assertFalse(out['original_draft_certified'])

    def test_changed_raw_bytes_invalidate_even_semantically_same_json(self):
        c, d = fixture()
        receipt, registry = signed(c, raw(d))
        self.assertEqual(G.route(c, raw(d) + b'\n', receipt=receipt,
                                 trusted_registry=registry)['status'], 'requires_review')

    def test_changed_source_invalidates_receipt(self):
        c, d = fixture()
        receipt, registry = signed(c, raw(d))
        c['package']['answer_input_base']['contexts'][0]['text'] = '乙的母亲未确认。'
        self.assertEqual(G.route(c, raw(d), receipt=receipt,
                                 trusted_registry=registry)['status'], 'requires_review')

    def test_each_missing_receipt_requirement_fails_closed(self):
        c, d = fixture()
        original, _ = signed(c, raw(d))
        for key, value in [('reviewed_coverage', []), ('confirmed_facets', []),
                           ('scope', 'selected_groups_only'), ('decision', 'rejected'),
                           ('unresolved_facets', ['scope']),
                           ('reviewer_identity', 'original_deepseek_flash_delivery')]:
            receipt = copy.deepcopy(original)
            receipt[key] = value
            self.assertEqual(G.route(c, raw(d), receipt=receipt,
                trusted_registry=authorize(receipt))['status'], 'requires_review', key)

    def test_stale_or_incomplete_authority_fails_closed(self):
        c, d = fixture()
        receipt, registry = signed(c, raw(d))
        registry[G.digest(receipt)]['actual_independent_source_review_verified'] = False
        self.assertEqual(G.route(c, raw(d), receipt=receipt,
                                 trusted_registry=registry)['status'], 'requires_review')

    def test_protocol_failure_and_pending_cannot_be_cleared_by_receipt(self):
        c, d = fixture()
        receipt, registry = signed(c, raw(d))
        for status in ('protocol_failure', 'technical_failure', 'running'):
            changed = copy.deepcopy(d)
            changed['status'] = status
            self.assertEqual(G.route(c, raw(changed), receipt=receipt,
                trusted_registry=registry)['status'], 'requires_review')
        d['merged']['verdict'] = 'needs_adjudication'
        self.assertEqual(G.route(c, raw(d))['status'], 'requires_review')

    def test_mismatched_job_split_and_duplicate_json_fail_closed(self):
        c, d = fixture([])
        d['split'] = 'other'
        self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'requires_review')
        duplicate = b'{"job":{},"job":{}}'
        self.assertEqual(G.route(c, duplicate, closed_world=True)['status'], 'requires_review')

    def test_no_mutation_or_case_id_whitelist(self):
        for case_id in ('heldout-new-name', 'not-an-old-known-success'):
            c, d = fixture([])
            c['job']['case_id'] = d['job']['case_id'] = case_id
            before = copy.deepcopy(c), raw(d)
            self.assertEqual(G.route(c, raw(d), closed_world=True)['status'], 'automatically_determined_core')
            self.assertEqual((c, raw(d)), before)


if __name__ == '__main__':
    unittest.main()
