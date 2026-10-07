"""[Original restoration checks](../../data/pilot_literature_history_v0/原文恢复说明.md)."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src/pilot_literature_history_v0'))
from original_materials import QUOTES, validate_materials

ROWS = [json.loads(s) for s in (ROOT / 'data/pilot_literature_history_v0/benchmark.jsonl').read_text(encoding='utf-8').splitlines()]

def row(family, variant):
    return next(r for r in ROWS if r['family_id'] == family and r['variant'] == variant)

class OriginalMaterialTest(unittest.TestCase):
    def test_history_letter_is_literal_original_and_shared_by_three_hops(self):
        r = row('F-C01-H', 'control')
        text = QUOTES['H1-B']['text']
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
        for family, bridge in [('F-C04-H', '梁父即楚將項燕'), ('F-C04-L', '那洞中有一個神仙，稱名須菩提祖師')]:
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
        self.assertEqual(r['material_style'], 'mixed')
        self.assertEqual(r['gold']['answers'], ['玄栈山'])

    def test_named_original_aliases_are_replaced_in_the_actual_text(self):
        r = row('F-C01-H', 'unfamiliar_challenge')
        text = ''.join(d['text'] for d in r['input']['documents'])
        for name in ['項梁', '曹咎', '司馬欣', '櫟陽']:
            self.assertNotIn(name, text)
        for name in ['项梁', '曹咎', '司马欣', '栎阳']:
            self.assertIn(r['entity_mapping'][name], text)

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
