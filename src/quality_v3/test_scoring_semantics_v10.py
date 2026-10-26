"""Narrow role-guard regressions and explicitly offline old-response diagnostics.

Policy: [scoring_semantics_v10.py](scoring_semantics_v10.py).
The frozen v9 raw cases are diagnostics, never new target-model deliveries.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import scoring_semantics_v10 as P
import scoring_review_v7 as OLD
import scoring_review_v9 as S9
import scoring_review_v10 as S10
import test_scoring_review_v7 as T
import test_scoring_review_v9 as T9


class ParentTitleGuardTests(unittest.TestCase):
    def marker(self, quote, parent='贾政', child='元春', aliases=None, role='father'):
        if aliases is None:
            aliases = [{'equivalent_surfaces': ['贾政', '政老爹']}]
        return P._role_marker(quote, role, child, parent, aliases)

    def test_actual_parent_title_possessive_preserves_role_erased_by_identity_removal(self):
        quote = '政老爹的长女，'
        aliases = [{'equivalent_surfaces': ['贾政', '政老爹']}]
        self.assertFalse(OLD._role_marker(quote, 'father', '元春', '贾政', aliases))
        self.assertTrue(self.marker(quote))

    def test_explicit_parent_father_titles_require_possessive_kinship_phrase(self):
        for title in ('政老爹', '爹爹', '陈老爸', '爸爸'):
            for link in ('的', '之'):
                with self.subTest(title=title, link=link):
                    self.assertTrue(self.marker(title + link + '亲生女儿元春。', parent=title, aliases=[]))

    def test_metadata_title_not_present_in_actual_role_quote_does_not_help(self):
        self.assertFalse(self.marker('贾政的长女，'))
        self.assertFalse(self.marker('的长女，'))

    def test_ordinary_names_containing_father_or_mother_are_not_new_role_markers(self):
        for name in ('贾母', '周父', '陈老爹馆'):
            with self.subTest(name=name):
                self.assertFalse(self.marker(name + '的女儿元春。', parent=name, aliases=[]))
        self.assertFalse(self.marker('贾母与元春同来。', parent='贾母', aliases=[], role='mother'))

    def test_child_title_cannot_supply_parent_father_role(self):
        self.assertFalse(self.marker('元春老爹的女儿是甲。', parent='甲', child='元春老爹', aliases=[]))

    def test_pure_title_cooccurrence_or_nonkinship_possessive_remains_insufficient(self):
        for quote in ('政老爹与元春同来。', '政老爹的朋友元春。', '政老爹看见元春。', '政老爹。'):
            with self.subTest(quote=quote):
                self.assertFalse(self.marker(quote))

    def test_unregistered_other_title_does_not_change_existing_negative_marker_rule(self):
        quote = '邻家老爹的女儿元春。'
        aliases = [{'equivalent_surfaces': ['贾政', '政老爹']}]
        # The pre-existing lexical guard sees 爹; a marker is never entailment.
        # The new exception changes nothing here, and endpoint grounding below
        # still rejects a claimed parent not actually named in its own group.
        self.assertEqual(self.marker(quote), OLD._role_marker(quote, 'father', '元春', '贾政', aliases))

    def test_no_new_mother_title_exception_is_claimed(self):
        aliases = [{'equivalent_surfaces': ['许氏', '娘亲']}]
        self.assertFalse(P._role_marker('娘亲的儿子乙。', 'mother', '乙', '许氏', aliases))

    def title_case(self):
        args = T.fixture()
        args[3]['entities'][1].update(name='贾政', aliases=['政老爹'])
        args[3]['entities'][2].update(name='元春', aliases=[])
        args[0]['steps'][0].update({'from': '元春', 'to': '贾政'})
        args[0]['steps'][1]['from'] = '贾政'
        first_quote, second_quote = '政老爹的长女，名叫元春。', '甲是贾政的父亲。'
        args[0]['steps'][0]['evidence'][0]['quote'] = first_quote
        args[0]['steps'][1]['evidence'][0]['quote'] = second_quote
        args[0]['evidence'][0]['quote'] = first_quote; args[0]['evidence'][1]['quote'] = second_quote
        args[1]['contexts'][0]['text'] = first_quote + second_quote
        pack = S10.build_scoring_package(*args); first = T.stage_a(pack)
        native_payload = S10.PREVIOUS.build_answer_payload(pack, first)
        group = {'citations': [T.citation(native_payload, '政老爹的长女，'), T.citation(native_payload, '名叫元春。')],
            'anchors': {'child': T.citation(native_payload, '名叫元春。'),
                **{k: T.citation(native_payload, '政老爹的长女，') for k in ('parent', 'predicate', 'parent_role')}},
            'checks': {k: 'supported' for k in P.CHECK_KEYS}, 'reason': '父称呼实际在所引亲属短语中。'}
        edge = {'parent': '贾政', 'parent_role': 'father', 'support_groups': [group], 'reason': '实际父亲关系。'}
        native = {'input_sha256': native_payload['input_sha256'], 'evidence_review_sha256': P.digest(first),
            'context_checks': [{'step_id': s['step_id'], 'context_consistency': 'supported',
                'checked_citation_ids': [c['citation_id'] for c in s['submitted_citations']], 'reason': '核原位置。'}
                for s in native_payload['submitted_steps']],
            'hop_reviews': [{'hop_id': 'hop-0', 'frontier': ['元春'], 'child_reviews': [T.child(native_payload, '元春', [edge])]},
                {'hop_id': 'hop-1', 'frontier': ['贾政'],
                 'child_reviews': [T.child(native_payload, '贾政', [T.edge(native_payload, '甲', second_quote)])]}],
            'issues': [], 'reason': '从明确查询子辈遍历。'}
        return pack, first, native

    def test_explicit_flat_materialization_reaches_new_policy_without_old_gate(self):
        pack, first, native = self.title_case()
        with self.assertRaisesRegex(ValueError, 'parent-role anchor'):
            OLD.validate_answer_review(native, S10.PREVIOUS.build_answer_payload(pack, first))
        flat = T9.flatten(native, S10.build_answer_payload(pack, first))
        got = S10.merge_scoring_results(pack, first, flat)
        self.assertEqual(got['verdict'], 'supported')
        self.assertEqual(got['semantic_policy_version'], P.SEMANTIC_POLICY_VERSION)
        self.assertFalse(got['reference_used_for_verdict'])

    def test_parent_title_does_not_fill_missing_child_inside_positive_group(self):
        pack, first, native = self.title_case()
        group = native['hop_reviews'][0]['child_reviews'][0]['edges'][0]['support_groups'][0]
        group['citations'] = group['citations'][:1]
        group['anchors']['child'] = copy.deepcopy(group['anchors']['parent'])
        flat = T9.flatten(native, S10.build_answer_payload(pack, first))
        with self.assertRaisesRegex(ValueError, 'named child'):
            S10.merge_scoring_results(pack, first, flat)

    def test_title_word_cannot_replace_actual_named_parent_in_positive_group(self):
        pack, first, native = self.title_case()
        flat = T9.flatten(native, S10.build_answer_payload(pack, first))
        flat['edge_groups'][0]['parent'] = '丁'
        with self.assertRaisesRegex(ValueError, 'named parent'):
            S10.merge_scoring_results(pack, first, flat)

    def test_title_exception_cannot_upgrade_original_unknown_or_failed_scope_check(self):
        pack, _, native = self.title_case()
        first = T.stage_a(pack, 'undetermined')
        payload = S10.build_answer_payload(pack, first)
        flat = T9.flatten(native, payload)
        got = S10.merge_scoring_results(pack, first, flat)
        self.assertEqual(got['verdict'], 'needs_adjudication')
        flat['edge_groups'][0]['check_scope'] = 'unsupported'
        with self.assertRaisesRegex(ValueError, 'uncertain or failed'):
            S10.merge_scoring_results(pack, first, flat)


class ActualFrozenRawDiagnostics(unittest.TestCase):
    """No provider calls; old delivered failures stay failed in their batch."""
    def test_two_actual_v9_title_false_blocks_replay_only_with_same_native_input(self):
        root = Path(__file__).resolve().parents[2]
        batch = root / 'artifacts/quality-v3/contracts-v9-run-001'
        runtime = root / 'workspace/harness-prototype/runs/contracts-v9-run-001'
        if not (batch / 'request-contracts.frozen.json').exists():
            self.skipTest('Frozen v9 diagnostic artifacts are not present in this checkout')
        read = lambda p: json.loads(p.read_text(encoding='utf-8'))
        contracts = read(batch / 'request-contracts.frozen.json')
        jobs = read(batch / 'jobs.frozen.json')
        for cid in ('SCORE-DEV-1370fa583a9c6746', 'SCORE-DEV-164c521f6bf4905b'):
            with self.subTest(case_id=cid):
                jid = next(j for j, c in contracts.items() if c['job']['case_id'] == cid)
                worker = jobs.index(jid) % 4
                path = runtime / 'results' / (jid + '.json')
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                result = read(path)
                self.assertEqual(result['status'], 'protocol_failure')
                self.assertIn('parent-role anchor', result['message'])
                package, first, raw = contracts[jid]['package'], result['evidence_review'], result['answer_review']
                original = copy.deepcopy(raw)
                old_input = read(runtime / 'derived-contracts' / (jid + '-answer.json'))['input']
                with self.assertRaisesRegex(ValueError, 'parent-role anchor'):
                    S9.merge_scoring_results(package, first, raw)
                new_input = S10.build_answer_payload(package, first)
                self.assertEqual(new_input['native_input_sha256'], old_input['native_input_sha256'])
                self.assertEqual(new_input['unit_catalog'], old_input['unit_catalog'])
                self.assertEqual(new_input['contexts'], old_input['contexts'])
                # Only a copied protocol-binding hash changes for the new wire;
                # every model-authored semantic row and anchor selection stays.
                replay = copy.deepcopy(raw); replay['flat_input_sha256'] = new_input['flat_input_sha256']
                native = S10.materialize_answer_review(replay, new_input)
                native_payload = S10.PREVIOUS.build_answer_payload(package, first)
                with self.assertRaisesRegex(ValueError, 'parent-role anchor'):
                    OLD.validate_answer_review(native, native_payload)
                self.assertTrue(P.validate_answer_review(native, native_payload))
                self.assertEqual(S10.merge_scoring_results(package, first, replay)['verdict'], 'supported')
                self.assertEqual(raw, original)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
