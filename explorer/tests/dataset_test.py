"""[Site data checks](../specs/04_技术与运行.md). No local HTTP service."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from site_data import PROJECT, load_bundle

class DatasetTest(unittest.TestCase):
    def test_bundle_matches_registered_data(self):
        bundle=load_bundle('pilot_literature_history_v0')
        source=PROJECT/'data/pilot_literature_history_v0/benchmark.jsonl'
        rows=[json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(bundle['records'], rows)
        self.assertEqual(bundle['summary']['records'],86)
        self.assertEqual(bundle['summary']['oracle_tasks'],58)
        self.assertEqual(bundle['fingerprint'],hashlib.sha256(source.read_bytes()).hexdigest())
    def test_unknown_dataset_is_rejected(self):
        for key in ['not_registered','../data','/data/pilot_literature_history_v0']:
            with self.assertRaises(KeyError):load_bundle(key)

if __name__=='__main__':unittest.main()
