"""[Original restoration checks](../../data/pilot_literature_history_v0/原文恢复说明.md)."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/pilot_literature_history_v0'))
from original_materials import QUOTES, TRANSLATIONS, validate_materials

ROWS = [json.loads(s) for s in (ROOT / 'data/pilot_literature_history_v0/benchmark.jsonl').read_text(encoding='utf-8').splitlines()]

def row(family, variant):
    return next(r for r in ROWS if r['family_id'] == family and r['variant'] == variant)

class OriginalMaterialTest(unittest.TestCase):
    def test_all_current_materials_are_modern_and_source_quotes_are_not_model_context(self):
        for r in ROWS:
            self.assertEqual(r['material_style'], 'vernacular')
            self.assertTrue(all(a['register'] == 'vernacular' for a in r['material_annotations'].values()))
        self.assertIn('項梁嘗有櫟陽逮', QUOTES['H1-B']['text'])
        self.assertNotIn('項梁嘗有櫟陽逮', row('F-C01-H','control')['input']['documents'][0]['text'])

    def test_translation_preserves_sender_recipient_offices_and_kinship_roles(self):
        text = TRANSLATIONS['H1-B:0:31']['modern_text']
        self.assertIn('在蕲任监狱属官的曹咎写信给在栎阳任监狱属官的司马欣', text)
        text = TRANSLATIONS['H1-A:0:45']['modern_text']
        self.assertIn('最小的叔叔是项梁', text)
        self.assertIn('项梁的父亲就是楚国将领项燕', text)
        self.assertIn('项燕被秦国将领王翦杀害', text)
        self.assertIn('吴叔为代理王', TRANSLATIONS['H2-PDEPUTY:0:86']['modern_text'])

    def test_translated_deletion_fragments_do_not_restore_missing_bridges(self):
        r = row('F-C04-H', 'delete_all_bridge_supports')
        text = '\n'.join(d['text'] for d in r['input']['documents'])
        self.assertIn('项燕被秦国将领王翦杀害', text)
        self.assertNotIn('项梁的父亲', text)
        r = row('F-C04-L', 'delete_all_bridge_supports')
        text = '\n'.join(d['text'] for d in r['input']['documents'])
        self.assertIn('山中有一座斜月三星洞', text)
        self.assertNotIn('洞里有一位神仙，名叫须菩提祖师', text)

    def test_translated_counterfactual_kinship_changes_father_without_changing_killer(self):
        r = row('F-C08-H', 'challenge')
        text = next(d['text'] for d in r['input']['documents'] if d['id'] == r['fact_to_evidence']['e'])
        self.assertIn('卫嶂的父亲就是楚国将领项燕', text)
        self.assertIn('项燕被秦国将领王翦杀害', text)
        self.assertNotIn('项梁的父亲', text)

    def test_history_letter_is_translated_and_shared_by_three_hops(self):
        r = row('F-C01-H', 'control')
        text = TRANSLATIONS['H1-B:0:31']['modern_text']
        self.assertTrue(any(d['text'] == text for d in r['input']['documents']))
        self.assertEqual(len({r['fact_to_evidence'][fid] for fid in ('a', 'b', 'c')}), 1)
        self.assertFalse(any(d['text'] == f['text'] for d in r['input']['documents'] for f in r['facts']))

    def test_every_original_and_transformation_replays_and_tampering_is_rejected(self):
        for r in ROWS:
            validate_materials(r)
        bad = copy.deepcopy(row('F-C01-H', 'control'))
        bad['input']['documents'][0]['text'] += '假的古文'
        with self.assertRaises(AssertionError):
            validate_materials(bad)

    def test_bridge_deletion_removes_actual_source_support(self):
        for family, bridge in [('F-C04-H', '项梁的父亲就是楚国将领项燕'), ('F-C04-L', '洞里有一位神仙，名叫须菩提祖师')]:
            r = row(family, 'delete_all_bridge_supports')
            self.assertFalse(any(bridge in d['text'] for d in r['input']['documents']))
            self.assertEqual(r['gold']['status'], 'insufficient')
            one = row(family, 'delete_one_support')
            self.assertTrue(any(bridge in d['text'] for d in one['input']['documents']))
            self.assertEqual(one['gold']['status'], 'answerable')

    def test_counterfactual_swaps_actor_without_moving_the_cave_mountain(self):
        r = row('F-C08-L', 'challenge')
        ancient = next(d['text'] for d in r['input']['documents'] if d['id'] == r['fact_to_evidence']['e'])
        self.assertIn('斜月三星洞', ancient)
        self.assertIn('青砚子', ancient)
        self.assertNotIn('照云洞', ancient)
        bridge = next(d['text'] for d in r['input']['documents'] if d['id'] == r['fact_to_evidence']['b'])
        self.assertIn('须菩提祖师', bridge)
        self.assertIn('照云洞', bridge)
        self.assertEqual(r['material_style'], 'vernacular')
        self.assertEqual(r['gold']['answers'], ['玄栈山'])

    def test_named_original_aliases_are_replaced_in_the_actual_text(self):
        r = row('F-C01-H', 'unfamiliar_challenge')
        text = ''.join(d['text'] for d in r['input']['documents'])
        for name in ['項梁', '曹咎', '司馬欣', '櫟陽']:
            self.assertNotIn(name, text)
        for name in ['项梁', '曹咎', '司马欣', '栎阳']:
            self.assertIn(r['entity_mapping'][name], text)

    def test_anonymous_people_include_courtesy_names_and_context_only_people(self):
        r = row('F-C01-L', 'anonymous_challenge')
        text = '\n'.join(d['text'] for d in r['input']['documents'])
        for clue in ['奉先', '吕将军', '姓吕', '丁原', '丁建阳', '建阳']:
            self.assertNotIn(clue, text)
        self.assertIn(r['entity_mapping']['吕布'] + '将军', text)
        self.assertIn(r['entity_mapping']['丁原'] + '说', text)
        self.assertIn(r['entity_mapping']['李儒'] + '说', text)
        control_text = '\n'.join(d['text'] for d in row('F-C01-L', 'control')['input']['documents'])
        self.assertIn('奉先', control_text)
        self.assertIn('丁原', control_text)

    def test_naming_keeps_copying_conditions_and_generic_table_labels(self):
        for family, variant in [('F-C10-H', 'anonymous_challenge'), ('F-C10-L', 'unfamiliar_challenge')]:
            r = row(family, variant)
            self.assertNotIn('复抄', r['entity_mapping'])
            text = '\n'.join(d['text'] for d in r['input']['documents'])
            self.assertIn('复抄卷本', text)
            self.assertIn('首抄', r['input']['question'])
            condition = next(f for f in r['facts'] if f['fact_id'] == 'i')
            self.assertEqual(condition['subject'], '复抄')
        for family, variant in [('F-C06-H', 'anonymous_challenge'), ('F-C06-L', 'unfamiliar_challenge')]:
            r = row(family, variant)
            self.assertNotIn('本题卷本表', r['entity_mapping'])
            self.assertIn('本题卷本表', r['input']['question'])

    def test_alias_resolution_evidence_and_registers_remain_outside_model_input(self):
        r = row('F-C07-H', 'control')
        self.assertEqual(len(r['gold']['proofs'][0][0]['support_evidence_ids']), 2)
        for r in ROWS:
            self.assertEqual(set(r['input']), {'id', 'instruction', 'question', 'documents', 'output_contract'})
            self.assertTrue(all(set(d) == {'id', 'text'} for d in r['input']['documents']))
            if r['variant'] == 'no_context':
                self.assertEqual(r['material_label_scope'], 'prototype')
                self.assertEqual(r['input']['documents'], [])
        self.assertEqual(row('F-C06-H', 'control')['material_style'], 'vernacular')

if __name__ == '__main__':
    unittest.main()
