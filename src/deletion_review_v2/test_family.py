"""Synthetic-only FamilyV2 regression fixtures; no model, network or source edits."""
import copy
import hashlib
import unittest

import jsonschema

from family import build_family, validate_family, graph_core, solve_scoped, remove_quotes_v2


def fact(fid, parent, child, quote, role='father'):
    return {'id': fid, 'parent': parent, 'child': child, 'parent_role': role,
            'scope': 'fictional-narrator', 'expression': 'direct',
            'evidence_sets': [[{'unit_id': 'base', 'quote': quote}]]}


def packet(redundant=False, alternate=False):
    text = '甲是乙的父亲。乙是丙的父亲。丙正在院子里读书。院墙旁开着白花。'
    facts = [fact('f1', '乙', '丙', '乙是丙的父亲。'), fact('f2', '甲', '乙', '甲是乙的父亲。')]
    necessary = [{'unit_id': 'base', 'quote': '乙是丙的父亲。'}]
    deletions = {
        'necessary_support_deleted_name_retained': necessary,
        'irrelevant_deleted': [{'unit_id': 'base', 'quote': '院墙旁开着白花。'}],
        'name_absent_deleted': necessary + [{'unit_id': 'base', 'quote': '丙正在院子里读书。'}],
    }
    not_applicable = {'redundant_support_deleted': 'No second support expression.',
                      'alternative_proof_preserved': 'No independent same-answer path.'}
    if redundant:
        text += '丙的父亲是乙。'
        facts[0]['evidence_sets'].append([{'unit_id': 'base', 'quote': '丙的父亲是乙。'}])
        deletions['necessary_support_deleted_name_retained'] = necessary + [{'unit_id': 'base', 'quote': '丙的父亲是乙。'}]
        deletions['name_absent_deleted'] = deletions['necessary_support_deleted_name_retained'] + [{'unit_id': 'base', 'quote': '丙正在院子里读书。'}]
        deletions['redundant_support_deleted'] = necessary
        del not_applicable['redundant_support_deleted']
    names = ['甲', '乙', '丙', '丁', '戊']
    if alternate:
        text += '庚是丙的母亲。甲是庚的父亲。'
        facts += [fact('f3', '庚', '丙', '庚是丙的母亲。', 'mother'), fact('f4', '甲', '庚', '甲是庚的父亲。')]
        names.append('庚')
        both = necessary + [{'unit_id': 'base', 'quote': '庚是丙的母亲。'}]
        deletions['necessary_support_deleted_name_retained'] = both
        deletions['name_absent_deleted'] = both + [{'unit_id': 'base', 'quote': '丙正在院子里读书。'}]
        deletions['alternative_proof_preserved'] = necessary
        del not_applicable['alternative_proof_preserved']
    return {
        'family_id': 'synthetic-regression', 'track': 'synthetic',
        'question': '根据本虚构材料，丙的父母之一的父亲是谁？' if alternate else '根据本虚构材料，丙的父亲的父亲是谁？',
        'origin': {'entities': [{'id': n, 'name': n, 'aliases': []} for n in names], 'facts': facts, 'warnings': []},
        'query': {'operation': 'parent_chain', 'start': '丙', 'steps': ['parent' if alternate else 'father', 'father'], 'scope': 'fictional-narrator'},
        'base_unit_ids': ['base'],
        'materials': [{'unit_id': 'base', 'text': text},
                      {'unit_id': 'distractor', 'text': '丁是戊的父亲。戊站在门外。'},
                      {'unit_id': 'irrelevant', 'text': '远处河水缓缓流淌。'}],
        'additions': {'main_distractor': ['distractor'], 'irrelevant_addition': ['irrelevant']},
        'deletions': deletions, 'optional_not_applicable': not_applicable,
    }


def rows(family):
    return {r['condition']: r for r in family['variants']}


class FamilyV2Tests(unittest.TestCase):
    def test_mandatory_members_and_optional_explicit_status(self):
        family = build_family(packet())
        self.assertEqual(len(family['variants']), 6)
        self.assertEqual(rows(family)['base']['gold']['answer_ids'], ['甲'])
        self.assertFalse(family['optional_applicability']['redundant_support_deleted']['applicable'])
        self.assertFalse(family['eligible_for_locked_experiment'])

    def test_required_deletion_retains_name_but_removes_proof(self):
        cut = rows(build_family(packet()))['necessary_support_deleted_name_retained']
        self.assertEqual(cut['gold']['status'], 'insufficient_evidence')
        self.assertTrue(any(p['surface'] == '丙' for p in cut['name_positions']))
        self.assertEqual(cut['active_fact_ids'], ['f2'])

    def test_name_absent_is_different_from_required_deletion(self):
        row = rows(build_family(packet()))['name_absent_deleted']
        self.assertEqual(row['name_positions'], [])
        self.assertEqual(row['gold']['status'], 'insufficient_evidence')

    def test_irrelevant_removal_preserves_entire_proof(self):
        variants = rows(build_family(packet()))
        self.assertEqual(variants['irrelevant_deleted']['gold'], variants['base']['gold'])

    def test_source_text_and_packet_are_not_mutated(self):
        original = packet()
        before = copy.deepcopy(original)
        family = build_family(original)
        self.assertEqual(original, before)
        self.assertTrue(all(r['requires_text_review'] for r in family['variants']))
        self.assertFalse(family['formal_release'])

    def test_deletion_positions_reconstruct_and_hash_is_new(self):
        p = packet()
        result = rows(build_family(p))['necessary_support_deleted_name_retained']
        before = p['materials'][0]['text']
        log = result['deletion_log'][0]
        self.assertEqual(before[log['start']:log['end_exclusive']], log['removed_text'])
        after = before[:log['start']] + before[log['end_exclusive']:]
        self.assertEqual(result['materials'][0]['text'], after)
        self.assertEqual(result['materials'][0]['modern_sha256'], hashlib.sha256(after.encode()).hexdigest())
        self.assertEqual(result['materials'][0]['source_modern_sha256'], hashlib.sha256(before.encode()).hexdigest())

    def test_duplicate_support_is_not_an_independent_proof(self):
        result = rows(build_family(packet(redundant=True)))
        self.assertEqual(len(result['base']['gold']['proofs']), 1)
        self.assertEqual(result['base']['support_counts']['f1'], 2)
        self.assertEqual(result['redundant_support_deleted']['support_counts']['f1'], 1)
        self.assertEqual(result['redundant_support_deleted']['gold']['answer_ids'], ['甲'])

    def test_alternative_proof_survives_while_one_path_is_cut(self):
        result = rows(build_family(packet(alternate=True)))
        self.assertEqual(len(result['base']['gold']['proofs']), 2)
        self.assertEqual(len(result['alternative_proof_preserved']['gold']['proofs']), 1)
        self.assertEqual(result['alternative_proof_preserved']['gold']['answer_ids'], ['甲'])
        self.assertEqual(result['necessary_support_deleted_name_retained']['gold']['status'], 'insufficient_evidence')

    def test_repeated_support_must_remove_a_real_support(self):
        p = packet(redundant=True)
        p['deletions']['redundant_support_deleted'] = p['deletions']['irrelevant_deleted']
        with self.assertRaisesRegex(ValueError, 'remove one support'):
            build_family(p)

    def test_alternative_condition_must_remove_a_real_proof(self):
        p = packet(alternate=True)
        p['deletions']['alternative_proof_preserved'] = p['deletions']['irrelevant_deleted']
        with self.assertRaisesRegex(ValueError, 'remove a proof'):
            build_family(p)

    def test_required_deletion_cannot_leave_repeated_support(self):
        p = packet(redundant=True)
        p['deletions']['necessary_support_deleted_name_retained'] = [{'unit_id': 'base', 'quote': '乙是丙的父亲。'}]
        with self.assertRaisesRegex(ValueError, 'leaves a registered proof'):
            build_family(p)

    def test_semantic_residual_not_labeled_unanswerable(self):
        p = packet()
        # Deliberately change a registered quote without destroying its meaning.
        p['materials'][0]['text'] = p['materials'][0]['text'].replace('乙是丙的父亲。', '乙是丙的亲生父亲。')
        p['origin']['facts'][0]['evidence_sets'][0][0]['quote'] = '乙是丙的亲生父亲。'
        p['deletions']['necessary_support_deleted_name_retained'] = [{'unit_id': 'base', 'quote': '亲生'}]
        p['deletions'].pop('name_absent_deleted')
        p['optional_not_applicable']['name_absent_deleted'] = 'Not part of semantic residual fixture.'
        p['semantic_residual'] = {'necessary_support_deleted_name_retained': True}
        result = build_family(p)
        cut = rows(result)['necessary_support_deleted_name_retained']
        self.assertEqual(cut['registered_graph_gold']['status'], 'insufficient_evidence')
        self.assertEqual(cut['gold']['status'], 'unresolved')
        self.assertEqual(result['validation_status'], 'pending_semantic_review')
        self.assertFalse(result['eligible_for_locked_experiment'])

    def test_alias_only_does_not_satisfy_canonical_name_retention(self):
        p = packet()
        p['origin']['entities'][2]['aliases'] = ['小丙']
        p['materials'][0]['text'] = p['materials'][0]['text'].replace('丙正在院子里读书。', '小丙正在院子里读书。')
        # Substring names would satisfy this test accidentally; choose a disjoint alias.
        p['origin']['entities'][2]['aliases'] = ['幼童']
        p['materials'][0]['text'] = p['materials'][0]['text'].replace('小丙正在院子里读书。', '幼童正在院子里读书。')
        p['deletions'].pop('name_absent_deleted')
        p['optional_not_applicable']['name_absent_deleted'] = 'Not part of alias fixture.'
        with self.assertRaisesRegex(ValueError, 'retain the canonical'):
            build_family(p)

    def test_optional_omission_needs_reason(self):
        p = packet(); p['optional_not_applicable'].pop('alternative_proof_preserved')
        with self.assertRaisesRegex(ValueError, 'Missing explicit optional'):
            build_family(p)

    def test_optional_cannot_be_both_present_and_absent(self):
        p = packet(); p['optional_not_applicable']['name_absent_deleted'] = 'Not applicable'
        with self.assertRaisesRegex(ValueError, 'both applicable'):
            build_family(p)

    def test_quote_not_in_source_rejected(self):
        p = packet(); p['deletions']['irrelevant_deleted'][0]['quote'] = '不存在的文本。'
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            build_family(p)

    def test_repeated_ambiguous_deletion_quote_rejected(self):
        p = packet(); p['materials'][0]['text'] += '院墙旁开着白花。'
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            build_family(p)

    def test_deletion_cannot_empty_passage(self):
        p = packet(); p['deletions']['irrelevant_deleted'][0]['quote'] = p['materials'][0]['text']
        with self.assertRaisesRegex(ValueError, 'empty passage'):
            build_family(p)

    def test_frozen_hash_tampering_rejected(self):
        p = packet(); p['materials'][0]['modern_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            build_family(p)

    def test_duplicate_material_id_rejected(self):
        p = packet(); p['materials'].append(copy.deepcopy(p['materials'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build_family(p)

    def test_duplicate_entity_and_fact_id_rejected(self):
        for key in ('entities', 'facts'):
            with self.subTest(key=key):
                p = packet(); p['origin'][key].append(copy.deepcopy(p['origin'][key][0]))
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    build_family(p)

    def test_additions_must_be_disjoint_acquired_nonbase(self):
        for value in (['base'], ['unknown'], ['irrelevant']):
            with self.subTest(value=value):
                p = packet(); p['additions']['main_distractor'] = value
                with self.assertRaises(ValueError):
                    build_family(p)

    def test_immutable_reconstruction_detects_unlogged_edit(self):
        p = packet(); family = build_family(p)
        self.assertEqual(validate_family(family, p)['reconstruction'], 'pass')
        family['variants'][0]['materials'][0]['text'] += '额外内容。'
        with self.assertRaisesRegex(ValueError, 'frozen packet'):
            validate_family(family, p)

    def test_legacy_solver_contract_remains_unchanged(self):
        p = packet()
        result = graph_core().solve(p['query'], p['origin']['facts'])
        self.assertEqual(result['answer_ids'], ['甲'])
        self.assertEqual(result['world_semantics'], 'positive_evidence_only_within_frozen_extracted_graph')

    def test_explicit_step_scopes_compose_without_relabeling_facts(self):
        p = packet()
        p['origin']['facts'][0]['scope'] = 'character-statement'
        p['origin']['facts'][1]['scope'] = 'narrator'
        p['query']['scope'] = 'explicit_source_composition'
        p['query']['scope_by_step'] = ['character-statement', 'narrator']
        original = copy.deepcopy(p['origin'])
        family = build_family(p)
        self.assertEqual(rows(family)['base']['gold']['answer_ids'], ['甲'])
        self.assertEqual(family['origin'], original)
        self.assertEqual(family['query']['scope_by_step'], ['character-statement', 'narrator'])

    def test_undeclared_scope_cannot_be_used_for_a_step(self):
        p = packet()
        p['origin']['facts'][0]['scope'] = 'character-statement'
        p['origin']['facts'][1]['scope'] = 'narrator'
        p['query']['scope'] = 'explicit_source_composition'
        p['query']['scope_by_step'] = ['character-statement', 'different-speaker']
        self.assertEqual(solve_scoped(p['query'], p['origin']['facts'])['status'], 'insufficient_evidence')
        with self.assertRaisesRegex(ValueError, 'unique answer'):
            build_family(p)

    def test_step_scope_list_requires_exactly_two_nonempty_scopes(self):
        for value in ([], ['one'], ['one', 'two', 'three'], ['one', ''], None):
            with self.subTest(value=value):
                p = packet(); p['query']['scope_by_step'] = value
                with self.assertRaises(jsonschema.ValidationError):
                    build_family(p)

    def test_legacy_single_scope_does_not_silently_compose_sources(self):
        p = packet()
        p['origin']['facts'][1]['scope'] = 'narrator'
        self.assertEqual(solve_scoped(p['query'], p['origin']['facts'])['status'], 'insufficient_evidence')
        with self.assertRaisesRegex(ValueError, 'unique answer'):
            build_family(p)

    def test_full_unit_deletion_retains_name_in_other_source_unit(self):
        p = packet()
        p['materials'][0]['text'] = '甲是乙的父亲。乙是丙的父亲。'
        p['materials'].append({'unit_id':'name-context','text':'丙正在院子里读书。院墙旁开着白花。'})
        p['base_unit_ids'].append('name-context')
        p['deletions']['necessary_support_deleted_name_retained'] = [{'unit_id':'base','quote':p['materials'][0]['text']}]
        p['deletions']['irrelevant_deleted'] = [{'unit_id':'name-context','quote':'院墙旁开着白花。'}]
        p['deletions'].pop('name_absent_deleted')
        p['optional_not_applicable']['name_absent_deleted'] = 'Cannot remove all units in this fixture.'
        family = build_family(p)
        cut = rows(family)['necessary_support_deleted_name_retained']
        self.assertEqual(cut['gold']['status'],'insufficient_evidence')
        self.assertEqual([u['unit_id'] for u in cut['materials']],['name-context'])
        self.assertTrue(cut['deletion_log'][0]['unit_removed'])
        self.assertTrue(any(q['surface']=='丙' for q in cut['name_positions']))
        from pathlib import Path
        import importlib.util
        path=Path(__file__).resolve().parents[1]/'multi_agent_v0/contracts.py'
        spec=importlib.util.spec_from_file_location('_family_test_v0_contract',path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        payload=graph_core().project(cut,family['question'],module.SCHEMAS['blind-solver'])
        self.assertEqual(len(payload['contexts']),1)
        self.assertNotIn('甲是乙的父亲',payload['contexts'][0]['text'])
        self.assertTrue(payload['contexts'][0]['text'])

    def test_full_unit_and_overlapping_cuts_have_original_coordinates(self):
        base=[{'unit_id':'one','text':'甲乙丙丁戊己'}, {'unit_id':'keep','text':'保留段落'}]
        result,logs=remove_quotes_v2(base,[{'unit_id':'one','quote':'甲乙丙丁'}, {'unit_id':'one','quote':'丙丁戊己'}])
        self.assertEqual(result,[base[1]])
        self.assertEqual(logs[0]['start'],0)
        self.assertEqual(logs[0]['end_exclusive'],6)
        self.assertEqual(logs[0]['removed_text'],'甲乙丙丁戊己')
        self.assertTrue(logs[0]['unit_removed'])
        self.assertEqual(base[0]['text'],'甲乙丙丁戊己')

    def test_deleting_every_unit_rejected_without_empty_placeholder(self):
        with self.assertRaisesRegex(ValueError,'Cannot remove all base units'):
            remove_quotes_v2([{'unit_id':'only','text':'甲乙丙'}],[{'unit_id':'only','quote':'甲乙丙'}])


if __name__ == '__main__':
    unittest.main()
